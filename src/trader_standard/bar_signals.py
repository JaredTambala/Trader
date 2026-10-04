"""Shared helpers for standard bar-backed signal computation."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Sequence

from trader.event_store import EventStore
from trader.indicators import IndicatorObservation
from trader.identifiers import deterministic_signal_event_id
from trader.market_data import RecentBarReader, RecentBarRequest
from trader.signals import Bar, Signal


logger = logging.getLogger(__name__)


def table_for_asset_class(asset_class: str) -> str:
    """Return the event-store bar table used for an asset class.

    Crypto-like asset classes map to `crypto_bar_events`; everything else uses
    stock bars so callers can build SQL without duplicating routing logic.
    """
    return "crypto_bar_events" if asset_class.lower() in {"crypto", "cryptocurrency"} else "stock_bar_events"


def max_window_for_signals(signals: Sequence[Signal]) -> int:
    """Return the largest bar lookback required by a non-empty signal set."""
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
    recent_bar_reader: RecentBarReader | None = None,
) -> list[Bar]:
    """Fetch recent OHLCV bars for a symbol/timeframe in latest-first order.

    `as_of_ts` bounds historical/backtest reads so signals do not see bars after
    the decision timestamp.
    """
    if recent_bar_reader is not None:
        if as_of_ts is None:
            raise ValueError("recent-bar reader calls require an as_of_ts")
        asset_class = "crypto" if table == "crypto_bar_events" else "stocks"
        request = RecentBarRequest(
            symbol=symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            as_of_ts=as_of_ts,
            limit=limit,
        )
        return list(recent_bar_reader.read(request))

    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return []

    if hasattr(connection, "cursor"):
        with connection.cursor() as cursor:
            placeholder = "?" if connection.__class__.__module__.startswith("_duckdb") else "%s"
            query = f"""
                    SELECT ts, open, high, low, close, volume, vwap, trade_count
                    FROM {table}
                    WHERE symbol = {placeholder} AND COALESCE(timeframe, '1Min') = {placeholder}
                    ORDER BY ts DESC
                    LIMIT {placeholder}
                """
            params = [symbol.upper(), timeframe, limit]
            if as_of_ts is not None:
                query = f"""
                        SELECT ts, open, high, low, close, volume, vwap, trade_count
                        FROM {table}
                        WHERE symbol = {placeholder}
                          AND COALESCE(timeframe, '1Min') = {placeholder}
                          AND ts <= {placeholder}
                        ORDER BY ts DESC
                        LIMIT {placeholder}
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
    """Compute signal values and persist indicator audit events when possible.

    Individual signal failures are logged and skipped so one bad signal does not
    prevent the strategy from using other available signals.
    """
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
    """Persist normalized indicator telemetry for one signal evaluation.

    Missing event-store or correlation identifiers make telemetry optional; the
    function returns without writing so signal computation can still proceed.
    """
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
    for indicator in indicators:
        indicator_name, value, bar_ts, payload_document = _normalize_indicator_audit_value(indicator)
        metadata = dict(payload_document.get("metadata", {})) if payload_document else {}
        metadata.setdefault("series_id", indicator_name)
        metadata.setdefault("series_label", indicator_name)
        metadata.setdefault("display", _display_metadata(signal, indicator_name, metadata))
        metadata["signal_name"] = signal.name
        metadata["signal_event_id"] = deterministic_signal_event_id(run_id, cycle_id, symbol, signal.name)
        payload = json.dumps(
            {
                "indicator_name": indicator_name,
                "ts": bar_ts,
                "value": payload_document.get("value") if payload_document else value,
                "metadata": metadata,
            },
            default=str,
            sort_keys=True,
        )
        event_store.record_event(
            "indicator_events",
            {
                "run_id": run_id,
                "session_id": run_id,
                "cycle_id": cycle_id,
                "symbol": symbol,
                "indicator_name": indicator_name,
                "value": value,
                "bar_ts": bar_ts,
                "payload": payload,
            },
        )


def _normalize_indicator_audit_value(
    value: IndicatorObservation | tuple[str, float, datetime],
) -> tuple[str, float | None, datetime, dict[str, object] | None]:
    if isinstance(value, IndicatorObservation):
        return value.indicator_name, value.scalar_value, value.ts, value.to_payload()
    indicator_name, scalar_value, bar_ts = value
    return indicator_name, float(scalar_value), bar_ts, {"metadata": {}}


def _display_metadata(
    signal: Signal,
    indicator_name: str,
    metadata: dict[str, object],
) -> dict[str, str]:
    """Return producer-declared plotting semantics for standard indicators.

    The Console consumes these fields as evidence. It never classifies a series
    from a display name or recomputes an indicator from the chart bars.
    """
    existing = metadata.get("display")
    if isinstance(existing, dict):
        return {str(key): str(value) for key, value in existing.items()}
    base_indicator = str(metadata.get("base_indicator", ""))
    if base_indicator in {"sma", "ema"} or indicator_name.startswith(("sma_", "ema_")):
        return {"pane": "price", "scale_group": "price", "unit": "price", "series_kind": "line"}
    if base_indicator in {"rsi", "momentum"} or indicator_name.startswith(("rsi", "momentum")):
        return {"pane": "secondary", "scale_group": "momentum", "unit": "index", "series_kind": "line"}
    if indicator_name.startswith(("bollinger_middle", "bollinger_upper", "bollinger_lower", "bollinger_bwma_middle", "bollinger_bwma_upper", "bollinger_bwma_lower")):
        return {"pane": "price", "scale_group": "price", "unit": "price", "series_kind": "line"}
    if "bandwidth" in indicator_name or "volatility" in indicator_name:
        return {"pane": "secondary", "scale_group": "volatility", "unit": "ratio", "series_kind": "line"}
    if indicator_name.startswith("macd"):
        return {"pane": "secondary", "scale_group": "macd", "unit": "value", "series_kind": "bar"}
    return {"pane": "unknown", "scale_group": "unknown", "unit": "unknown", "series_kind": "line"}


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
