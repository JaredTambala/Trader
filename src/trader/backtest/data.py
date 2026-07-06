"""Backtest market-data replay sources and bar storage helpers."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Mapping, Sequence

from ..event_store import EventStore
from ..market_data import MarketDataEvent, MarketDataSource
from ..signals import Bar
from .data_queries import (
    _bar_event_table_name,
    _build_symbol_schedule,
    _param_placeholder,
    _row_to_bar,
)
from .replay import (
    _BacktestBarSelection,
    _build_market_event,
    _normalize_timestamp,
    _select_backtest_bar,
)


logger = logging.getLogger(__name__)


class BacktestMarketDataSource(MarketDataSource):
    """Market data source that serves historical bars at a controlled timestamp.

    The runner calls `set_as_of()` before each cycle. Fetching then returns one
    bar per configured symbol for that decision timestamp, optionally falling
    back to the latest earlier bar and recording a warning when exact alignment
    is unavailable.
    """

    def __init__(
        self,
        *,
        bars_by_symbol: Mapping[str, Sequence[Bar]],
        asset_class: str,
        timeframe: str,
        source: str = "backtest",
        symbols: Sequence[str] | None = None,
        allow_latest_prior_bar: bool = True,
        warnings: list[str] | None = None,
    ) -> None:
        """Prepare symbol-indexed bars for deterministic timestamp lookups.

        Args:
            bars_by_symbol: Historical bars keyed by canonical symbol.
            asset_class: Asset class used to choose stock versus crypto events.
            timeframe: Timeframe attached to generated market-data events.
            source: Source label persisted with generated events.
            symbols: Optional ordered universe; missing symbols are represented
                by empty bar lists.
            allow_latest_prior_bar: Whether fetch may fall back to older bars.
            warnings: Mutable warning list shared with the runner result.
        """
        if symbols is not None:
            bars_by_symbol = {symbol: bars_by_symbol.get(symbol, []) for symbol in symbols}
        self._bars_by_symbol = {symbol: list(bars) for symbol, bars in bars_by_symbol.items()}
        self._timestamps_by_symbol = {
            symbol: [_normalize_timestamp(bar.ts) for bar in bars]
            for symbol, bars in bars_by_symbol.items()
        }
        self._asset_class = asset_class.lower()
        self._timeframe = timeframe
        self._source = source
        self._as_of_ts: datetime | None = None
        self._allow_latest_prior_bar = allow_latest_prior_bar
        self._warnings = warnings if warnings is not None else []

    def set_as_of(self, as_of_ts: datetime) -> None:
        """Set the normalized decision timestamp used by subsequent `fetch()` calls.

        Backtest cycles call this before ingestion so the market-data source emits
        bars for the current simulated decision time, or applies the configured
        latest-prior fallback when exact bars are unavailable.
        """
        self._as_of_ts = _normalize_timestamp(as_of_ts)

    def fetch(self) -> Sequence[MarketDataEvent]:
        """Return historical market-data events for the current decision time.

        Returns:
            Stock or crypto bar events built from the exact timestamp when
            available. If configured, the latest earlier bar is used with a
            warning; otherwise symbols with missing exact bars are skipped.
        """
        if self._as_of_ts is None:
            return []
        events: list[MarketDataEvent] = []
        for symbol, bars in self._bars_by_symbol.items():
            timestamps = self._timestamps_by_symbol.get(symbol, [])
            selection = _select_backtest_bar(
                symbol=symbol,
                bars=bars,
                timestamps=timestamps,
                target=self._as_of_ts,
                allow_latest_prior_bar=self._allow_latest_prior_bar,
            )
            if selection.warning:
                self._log_bar_selection_warning(symbol, selection)
                self._append_warning(selection.warning)
            if selection.bar is None:
                continue
            events.append(
                _build_market_event(
                    asset_class=self._asset_class,
                    symbol=symbol,
                    timeframe=self._timeframe,
                    bar=selection.bar,
                    source=self._source,
                    ingested_at=self._as_of_ts,
                )
            )
        return events

    def _append_warning(self, message: str) -> None:
        """Add a warning once while preserving insertion order."""
        if message not in self._warnings:
            self._warnings.append(message)

    def _log_bar_selection_warning(self, symbol: str, selection: _BacktestBarSelection) -> None:
        """Log a market-data alignment warning selected by the pure lookup helper."""
        if self._as_of_ts is None:
            return
        if selection.warning_kind == "missing_exact":
            logger.warning(
                "Backtest exact-bar requirement failed symbol=%s decision_ts=%s; skipping",
                symbol,
                self._as_of_ts.isoformat(),
            )
            return
        if selection.warning_kind == "no_prior":
            logger.warning(
                "Backtest price misalignment symbol=%s decision_ts=%s latest_ts=<none>; skipping",
                symbol,
                self._as_of_ts.isoformat(),
            )
            return
        if selection.warning_kind == "latest_prior":
            logger.warning(
                "Backtest price misalignment symbol=%s decision_ts=%s latest_ts=%s; using latest bar",
                symbol,
                self._as_of_ts.isoformat(),
                selection.latest_ts.isoformat() if selection.latest_ts else "<none>",
            )


def _build_data_sources(
    *,
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    asset_class: str,
    timeframe: str,
    symbols: Sequence[str],
    allow_latest_prior_bar: bool,
    warnings: list[str],
) -> dict[str, BacktestMarketDataSource]:
    """Build per-symbol market-data sources sharing the same historical bars."""
    sources: dict[str, BacktestMarketDataSource] = {}
    for symbol in symbols:
        sources[symbol] = BacktestMarketDataSource(
            bars_by_symbol=bars_by_symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            symbols=(symbol,),
            allow_latest_prior_bar=allow_latest_prior_bar,
            warnings=warnings,
        )
    return sources


def _load_bars(
    event_store: EventStore,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    lookback_bars: int = 0,
) -> dict[str, list[Bar]]:
    """Load historical bars for each symbol with optional pre-window lookback.

    Bars inside `[start, end]` drive replay timestamps. `lookback_bars` prepends
    earlier bars for indicators that need warmup history without allowing those
    pre-window bars to create decision cycles.
    """
    table = _bar_event_table_name(asset_class)
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Backtest bar load skipped; event store has no connection")
        return {}
    start_ts = _normalize_timestamp(start)
    end_ts = _normalize_timestamp(end)
    bars_by_symbol: dict[str, list[Bar]] = {symbol: [] for symbol in symbols}
    if not hasattr(connection, "cursor"):
        logger.warning("Backtest bar load skipped; unsupported connection type")
        return bars_by_symbol
    placeholder = _param_placeholder(connection)
    with connection.cursor() as cursor:
        for symbol in symbols:
            cursor.execute(
                f"""
                SELECT ts, open, high, low, close, volume, vwap, trade_count
                FROM {table}
                WHERE symbol = {placeholder}
                  AND COALESCE(timeframe, '1Min') = {placeholder}
                  AND ts >= {placeholder}
                  AND ts <= {placeholder}
                ORDER BY ts ASC
                """,
                [symbol.upper(), timeframe, start_ts, end_ts],
            )
            rows = cursor.fetchall()
            bars = [_row_to_bar(row) for row in rows]
            if lookback_bars > 0:
                cursor.execute(
                    f"""
                    SELECT ts, open, high, low, close, volume, vwap, trade_count
                    FROM {table}
                    WHERE symbol = {placeholder}
                      AND COALESCE(timeframe, '1Min') = {placeholder}
                      AND ts < {placeholder}
                    ORDER BY ts DESC
                    LIMIT {placeholder}
                    """,
                    [symbol.upper(), timeframe, start_ts, lookback_bars],
                )
                pre_rows = cursor.fetchall()
                pre_bars = [_row_to_bar(row) for row in reversed(pre_rows)]
                bars = pre_bars + bars
            bars_by_symbol[symbol] = bars
            logger.debug("Loaded backtest bars symbol=%s count=%s", symbol, len(bars))
    return bars_by_symbol


def _fetch_latest_prices(
    event_store: EventStore,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
) -> dict[str, tuple[datetime, float]]:
    """Fetch latest known close prices for portfolio valuation."""
    table = _bar_event_table_name(asset_class)
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return {}

    latest: dict[str, tuple[datetime, float]] = {}
    for symbol in symbols:
        if not hasattr(connection, "cursor"):
            continue
        with connection.cursor() as cursor:
            placeholder = _param_placeholder(connection)
            cursor.execute(
                f"""
                SELECT ts, close
                FROM {table}
                WHERE symbol = {placeholder}
                  AND COALESCE(timeframe, '1Min') = {placeholder}
                ORDER BY ts DESC
                LIMIT 1
                """,
                [symbol.upper(), timeframe],
            )
            row = cursor.fetchone()
            if row:
                latest[symbol] = (_normalize_timestamp(row[0]), float(row[1]))  # type: ignore[arg-type]
    return latest


def _fetch_first_prices(
    event_store: EventStore,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    start: datetime,
) -> dict[str, float]:
    """Fetch the first persisted close at or after the backtest start."""
    table = _bar_event_table_name(asset_class)
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return {}

    first: dict[str, float] = {}
    for symbol in symbols:
        if not hasattr(connection, "cursor"):
            continue
        with connection.cursor() as cursor:
            placeholder = _param_placeholder(connection)
            cursor.execute(
                f"""
                SELECT close
                FROM {table}
                WHERE symbol = {placeholder}
                  AND COALESCE(timeframe, '1Min') = {placeholder}
                  AND ts >= {placeholder}
                ORDER BY ts ASC
                LIMIT 1
                """,
                [symbol.upper(), timeframe, start],
            )
            row = cursor.fetchone()
            if row:
                first[symbol] = float(row[0])
    return first


def _fetch_timestamps(
    event_store: EventStore,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    start: datetime,
    end: datetime,
) -> list[datetime]:
    """Fetch unique replay timestamps across symbols within the backtest window."""
    table = _bar_event_table_name(asset_class)
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Backtest lookup skipped; event store has no connection")
        return []

    timestamps: set[datetime] = set()
    for symbol in symbols:
        if hasattr(connection, "cursor"):
            with connection.cursor() as cursor:
                placeholder = _param_placeholder(connection)
                cursor.execute(
                    f"""
                    SELECT ts
                    FROM {table}
                    WHERE symbol = {placeholder}
                      AND COALESCE(timeframe, '1Min') = {placeholder}
                      AND ts >= {placeholder}
                      AND ts <= {placeholder}
                    ORDER BY ts ASC
                    """,
                    [symbol.upper(), timeframe, start, end],
                )
                rows = cursor.fetchall()
        else:
            rows = []
        timestamps.update(row[0] for row in rows)

    normalized = [_normalize_timestamp(ts) for ts in timestamps]
    return sorted(normalized)


__all__ = [
    "BacktestMarketDataSource",
    "_bar_event_table_name",
    "_build_data_sources",
    "_build_symbol_schedule",
    "_fetch_first_prices",
    "_fetch_latest_prices",
    "_fetch_timestamps",
    "_load_bars",
    "_param_placeholder",
    "_row_to_bar",
]
