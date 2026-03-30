"""Shared helpers for standard bar-backed signal computation."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Mapping, Sequence

from trader.data import EventStore
from trader.signals import Bar, Signal


logger = logging.getLogger(__name__)


def table_for_asset_class(asset_class: str) -> str:
    """Return the bar table name for an asset class."""
    return "crypto_bar_events" if asset_class.lower() in {"crypto", "cryptocurrency"} else "stock_bar_events"


def max_window_for_signals(signals: Sequence[Signal]) -> int:
    """Return the largest lookback window required by the signal set."""
    if not signals:
        raise ValueError("At least one Signal must be provided")
    return max(signal.window for signal in signals)


def fetch_recent_bars(
    event_store: EventStore,
    *,
    table: str,
    symbol: str,
    timeframe: str,
    limit: int,
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


def compute_signal_map(
    *,
    signals: Sequence[Signal],
    bars: Sequence[Bar],
    event_store: EventStore | None = None,
    run_id: str | None = None,
    cycle_id: str | None = None,
    symbol: str | None = None,
) -> dict[str, float]:
    """Compute signal values from a latest-first bar window."""
    output: dict[str, float] = {}
    for signal in signals:
        try:
            subset = bars[: signal.window]
            output[signal.name] = float(signal.compute(subset))
            record_indicator_events(
                event_store,
                run_id=run_id,
                cycle_id=cycle_id,
                symbol=symbol,
                signal=signal,
                bars=subset,
            )
        except Exception as exc:
            logger.warning(
                "Signal compute failed signal=%s symbol=%s: %s",
                signal.name,
                symbol or "<unknown>",
                exc,
            )
    return output


def record_indicator_events(
    event_store: EventStore | None,
    *,
    run_id: str | None,
    cycle_id: str | None,
    symbol: str | None,
    signal: Signal,
    bars: Sequence[Bar],
) -> None:
    """Persist indicator telemetry events for a signal evaluation."""
    if event_store is None or not run_id or not cycle_id or not symbol:
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
                "session_id": run_id,
                "cycle_id": cycle_id,
                "symbol": symbol,
                "indicator_name": indicator_name,
                "value": float(value),
                "bar_ts": bar_ts,
            },
        )


def _row_to_bar(row: Sequence[object]) -> Bar:
    """Convert a DB row into a bar object."""
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
