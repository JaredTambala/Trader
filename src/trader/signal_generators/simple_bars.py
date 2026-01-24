"""Bar-based signal generator backed by the event store."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Mapping, Sequence

from trader.data import EventStore
from trader.signals import Bar, Signal
from trader.signal_generators.signal_generator import SignalGenerator


logger = logging.getLogger(__name__)


class SimpleBarsSignalGenerator(SignalGenerator):
    """Compute bar-based signals from persisted OHLCV bars."""

    def __init__(
        self,
        *,
        event_store: EventStore,
        symbols: Iterable[str],
        asset_class: str,
        timeframe: str,
        signals: Sequence[Signal],
    ) -> None:
        """Initialize the instance."""
        if not signals:
            raise ValueError("At least one Signal must be provided")
        self._event_store = event_store
        self._symbols = tuple(symbols)
        self._asset_class = asset_class.lower()
        self._timeframe = timeframe
        self._signals = tuple(signals)

    @property
    def signals(self) -> Sequence[Signal]:
        """Return configured signal definitions."""
        return self._signals

    @property
    def symbols(self) -> Sequence[str]:
        """Return the configured symbol universe."""
        return self._symbols

    @property
    def supports_symbol_generation(self) -> bool:
        """Report whether per-symbol signal generation is supported."""
        return True

    def generate(
        self,
        *,
        as_of_ts: datetime | None = None,
        run_id: str | None = None,
        cycle_id: str | None = None,
    ) -> Mapping[str, Mapping[str, float]]:
        """Generate signal events from available market data."""
        table = "crypto_bar_events" if self._asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
        max_window = max(signal.window for signal in self._signals)
        logger.info(
            "Signal generation start table=%s timeframe=%s symbols=%s window=%s as_of_ts=%s",
            table,
            self._timeframe,
            ",".join(self._symbols) if self._symbols else "<none>",
            max_window,
            as_of_ts.isoformat() if as_of_ts else "<latest>",
        )
        output: dict[str, dict[str, float]] = {}
        for symbol in self._symbols:
            bars = _fetch_recent_bars(
                self._event_store,
                table,
                symbol,
                self._timeframe,
                max_window,
                as_of_ts=as_of_ts,
            )
            logger.debug("Fetched bars symbol=%s count=%s", symbol, len(bars))
            if len(bars) < max_window:
                logger.warning(
                    "Skipping signal generation due to insufficient bars symbol=%s have=%s need=%s",
                    symbol,
                    len(bars),
                    max_window,
                )
                continue
            symbol_signals: dict[str, float] = {}
            for signal in self._signals:
                try:
                    subset = bars[: signal.window]
                    symbol_signals[signal.name] = float(signal.compute(subset))
                    _record_indicator_events(
                        self._event_store,
                        run_id=run_id,
                        cycle_id=cycle_id,
                        symbol=symbol,
                        signal=signal,
                        bars=subset,
                    )
                except Exception as exc:
                    logger.warning("Signal compute failed signal=%s symbol=%s: %s", signal.name, symbol, exc)
            if symbol_signals:
                output[symbol] = symbol_signals
        return output

    def generate_for_symbol(
        self,
        symbol: str,
        *,
        as_of_ts: datetime | None = None,
        run_id: str | None = None,
        cycle_id: str | None = None,
    ) -> Mapping[str, float] | None:
        """Generate signal events for a single symbol."""
        table = "crypto_bar_events" if self._asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
        max_window = max(signal.window for signal in self._signals)
        bars = _fetch_recent_bars(
            self._event_store,
            table,
            symbol,
            self._timeframe,
            max_window,
            as_of_ts=as_of_ts,
        )
        logger.debug("Fetched bars symbol=%s count=%s", symbol, len(bars))
        if len(bars) < max_window:
            logger.warning(
                "Skipping signal generation due to insufficient bars symbol=%s have=%s need=%s",
                symbol,
                len(bars),
                max_window,
            )
            return None
        symbol_signals: dict[str, float] = {}
        for signal in self._signals:
            try:
                subset = bars[: signal.window]
                symbol_signals[signal.name] = float(signal.compute(subset))
                _record_indicator_events(
                    self._event_store,
                    run_id=run_id,
                    cycle_id=cycle_id,
                    symbol=symbol,
                    signal=signal,
                    bars=subset,
                )
            except Exception as exc:
                logger.warning("Signal compute failed signal=%s symbol=%s: %s", signal.name, symbol, exc)
        return symbol_signals or None


def _fetch_recent_bars(
    event_store: EventStore,
    table: str,
    symbol: str,
    timeframe: str,
    limit: int,
    *,
    as_of_ts: datetime | None = None,
) -> list[Bar]:
    """Fetch recent OHLCV bars for a symbol/timeframe (latest first)."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return []

    if hasattr(connection, "cursor"):
        with connection.cursor() as cursor:
            query = f"""
                    SELECT ts, open, high, low, close, volume, vwap, trade_count
                    FROM {table}
                    WHERE symbol = %s AND COALESCE(timeframe, '1Min') = %s
                    ORDER BY ts DESC
                    LIMIT %s
                """
            params = [symbol.upper(), timeframe, limit]
            if as_of_ts is not None:
                query = f"""
                        SELECT ts, open, high, low, close, volume, vwap, trade_count
                        FROM {table}
                        WHERE symbol = %s AND COALESCE(timeframe, '1Min') = %s AND ts <= %s
                        ORDER BY ts DESC
                        LIMIT %s
                    """
                params = [symbol.upper(), timeframe, as_of_ts, limit]
            cursor.execute(query, params)
            return [_row_to_bar(row) for row in cursor.fetchall()]

    logger.warning("Bar fetch skipped; unsupported connection type")
    return []


def _record_indicator_events(
    event_store: EventStore,
    *,
    run_id: str | None,
    cycle_id: str | None,
    symbol: str,
    signal: Signal,
    bars: Sequence[Bar],
) -> None:
    """Persist indicator telemetry events for the current batch."""
    if not run_id or not cycle_id:
        return
    try:
        indicators = signal.indicator_values(bars)
    except Exception as exc:
        logger.warning(
            "Indicator values failed signal=%s symbol=%s: %s",
            signal.name,
            symbol,
            exc,
        )
        return
    for indicator_name, value, bar_ts in indicators:
        event_store.record_event(
            "indicator_events",
            {
                "run_id": run_id,
                "cycle_id": cycle_id,
                "symbol": symbol,
                "indicator_name": indicator_name,
                "value": float(value),
                "bar_ts": bar_ts,
            },
        )


def _row_to_bar(row: Sequence[object]) -> Bar:
    """Handle row to bar."""
    return Bar(
        ts=row[0],  # type: ignore[arg-type]
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        vwap=float(row[6]) if row[6] is not None else None,
        trade_count=float(row[7]) if row[7] is not None else None,
    )
