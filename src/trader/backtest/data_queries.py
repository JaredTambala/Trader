"""Pure query, row, and replay-schedule helpers for backtest market data."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from ..signals import Bar
from .replay import _normalize_timestamp

__all__ = [
    "_bar_event_table_name",
    "_build_symbol_schedule",
    "_param_placeholder",
    "_row_to_bar",
]


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
