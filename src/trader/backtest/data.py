"""Backtest market-data replay sources and bar storage helpers."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Mapping, Sequence

from ..event_store import EventStore
from ..market_data import CryptoBarEvent, MarketDataEvent, MarketDataSource, StockBarEvent
from ..signals import Bar


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _BacktestBarSelection:
    """Decision for serving one symbol at one backtest timestamp."""

    bar: Bar | None
    warning: str | None
    warning_kind: str | None
    latest_ts: datetime | None = None


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


@dataclass
class _PriceState:
    bars_by_symbol: Mapping[str, Sequence[Bar]]
    allow_price_carry_forward: bool = True

    def __post_init__(self) -> None:
        """Normalize derived fields after initialization."""
        self._indices: dict[str, int] = {symbol: 0 for symbol in self.bars_by_symbol}
        self._last_prices: dict[str, float] = {}

    def advance(self, ts: datetime) -> Mapping[str, float]:
        """Advance internal price cursors to a replay timestamp.

        With carry-forward enabled, last known prices remain available until a
        newer bar is seen. Without carry-forward, only exact-timestamp prices
        are returned so valuation gaps stay visible.
        """
        advanced = _advance_price_cursors(
            self.bars_by_symbol,
            indices=self._indices,
            previous_prices=self._last_prices,
            target=ts,
            allow_price_carry_forward=self.allow_price_carry_forward,
        )
        self._indices = dict(advanced.indices)
        self._last_prices = dict(advanced.prices)
        return dict(self._last_prices)


@dataclass(frozen=True)
class _PriceAdvanceResult:
    """Updated price cursor state for one replay timestamp."""

    indices: Mapping[str, int]
    prices: Mapping[str, float]


def _select_backtest_bar(
    *,
    symbol: str,
    bars: Sequence[Bar],
    timestamps: Sequence[datetime],
    target: datetime,
    allow_latest_prior_bar: bool,
) -> _BacktestBarSelection:
    """Select the bar to serve for one symbol at one decision timestamp."""
    target_ts = _normalize_timestamp(target)
    if not timestamps:
        return _BacktestBarSelection(bar=None, warning=None, warning_kind=None)
    idx = bisect_left(timestamps, target_ts)
    if idx < len(timestamps) and timestamps[idx] == target_ts:
        return _BacktestBarSelection(bar=bars[idx], warning=None, warning_kind=None)
    if not allow_latest_prior_bar:
        return _BacktestBarSelection(
            bar=None,
            warning=f"Missing exact bar for {symbol} at {target_ts.isoformat()}; skipped symbol.",
            warning_kind="missing_exact",
        )
    latest_idx = idx - 1
    if latest_idx < 0:
        return _BacktestBarSelection(
            bar=None,
            warning=f"No prior bar available for {symbol} at {target_ts.isoformat()}; skipped symbol.",
            warning_kind="no_prior",
        )
    latest_ts = timestamps[latest_idx]
    return _BacktestBarSelection(
        bar=bars[latest_idx],
        warning=f"Used latest prior bar for {symbol} at {target_ts.isoformat()} from {latest_ts.isoformat()}.",
        warning_kind="latest_prior",
        latest_ts=latest_ts,
    )


def _build_market_event(
    *,
    asset_class: str,
    symbol: str,
    timeframe: str,
    bar: Bar,
    source: str,
    ingested_at: datetime,
) -> MarketDataEvent:
    """Convert a normalized bar into the stock or crypto event-store shape."""
    common = dict(
        symbol=symbol,
        timeframe=timeframe,
        ts=_normalize_timestamp(bar.ts),
        ingested_at=_normalize_timestamp(ingested_at),
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=float(bar.volume),
        trade_count=float(bar.trade_count) if bar.trade_count is not None else None,
        vwap=float(bar.vwap) if bar.vwap is not None else None,
        source=source,
    )
    if asset_class in {"crypto", "cryptocurrency"}:
        return CryptoBarEvent(**common)
    return StockBarEvent(**common)


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


def _build_symbol_schedule(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    start: datetime,
    end: datetime,
) -> dict[datetime, list[str]]:
    """Build replay timestamps from loaded bars inside the requested window."""
    start_ts = _normalize_timestamp(start)
    end_ts = _normalize_timestamp(end)
    schedule: dict[datetime, list[str]] = {}
    for symbol, bars in bars_by_symbol.items():
        for bar in bars:
            bar_ts = _normalize_timestamp(bar.ts)
            if bar_ts < start_ts or bar_ts > end_ts:
                continue
            schedule.setdefault(bar_ts, []).append(symbol)
    return schedule


def _row_to_bar(row: Sequence[object]) -> Bar:
    """Convert a SQL bar row into the internal latest-first Bar primitive."""
    return Bar(
        ts=_normalize_timestamp(row[0]),  # type: ignore[arg-type]
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        vwap=float(row[6]) if row[6] is not None else None,
        trade_count=float(row[7]) if row[7] is not None else None,
    )


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


def _latest_prices_from_bars(bars_by_symbol: Mapping[str, Sequence[Bar]]) -> dict[str, tuple[datetime, float]]:
    """Return latest in-memory close prices per symbol."""
    latest: dict[str, tuple[datetime, float]] = {}
    for symbol, bars in bars_by_symbol.items():
        price = _latest_price_from_bars(bars)
        if price is not None:
            latest[symbol] = price
    return latest


def _latest_price_from_bars(bars: Sequence[Bar]) -> tuple[datetime, float] | None:
    """Return latest close price from an in-memory bar sequence."""
    if not bars:
        return None
    bar = bars[-1]
    return _normalize_timestamp(bar.ts), float(bar.close)


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


def _advance_price_cursors(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    indices: Mapping[str, int],
    previous_prices: Mapping[str, float],
    target: datetime,
    allow_price_carry_forward: bool,
) -> _PriceAdvanceResult:
    """Advance price cursors without mutating caller-owned state."""
    target_ts = _normalize_timestamp(target)
    if allow_price_carry_forward:
        return _advance_price_cursors_with_carry_forward(
            bars_by_symbol,
            indices=indices,
            previous_prices=previous_prices,
            target=target_ts,
        )
    return _advance_price_cursors_exact(
        bars_by_symbol,
        indices=indices,
        target=target_ts,
    )


def _advance_price_cursors_exact(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    indices: Mapping[str, int],
    target: datetime,
) -> _PriceAdvanceResult:
    """Advance cursors and return only exact-timestamp prices."""
    next_indices: dict[str, int] = {}
    current_prices: dict[str, float] = {}
    for symbol, bars in bars_by_symbol.items():
        idx = indices.get(symbol, 0)
        while idx < len(bars) and _normalize_timestamp(bars[idx].ts) < target:
            idx += 1
        if idx < len(bars) and _normalize_timestamp(bars[idx].ts) == target:
            current_prices[symbol] = float(bars[idx].close)
            idx += 1
        next_indices[symbol] = idx
    return _PriceAdvanceResult(indices=next_indices, prices=current_prices)


def _advance_price_cursors_with_carry_forward(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    indices: Mapping[str, int],
    previous_prices: Mapping[str, float],
    target: datetime,
) -> _PriceAdvanceResult:
    """Advance cursors while keeping latest known prices available."""
    next_indices: dict[str, int] = {}
    current_prices = dict(previous_prices)
    for symbol, bars in bars_by_symbol.items():
        idx = indices.get(symbol, 0)
        while idx < len(bars) and _normalize_timestamp(bars[idx].ts) <= target:
            current_prices[symbol] = float(bars[idx].close)
            idx += 1
        next_indices[symbol] = idx
    return _PriceAdvanceResult(indices=next_indices, prices=current_prices)


def _normalize_timestamp(value: datetime) -> datetime:
    """Normalize timestamp values to UTC-aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _param_placeholder(connection: object) -> str:
    """Return the SQL parameter placeholder for the active backend."""
    module = connection.__class__.__module__
    if module.startswith("duckdb"):
        return "?"
    return "%s"


def _bar_event_table_name(asset_class: str) -> str:
    """Return the persisted bar-event table name for an asset class."""
    if asset_class in {"crypto", "cryptocurrency"}:
        return "crypto_bar_events"
    return "stock_bar_events"
