"""Pure builders for runtime operator status payloads.

The runtime status shell owns SQL queries and halt-state writes. This module
turns already-fetched rows and values into JSON-safe payloads so data-shaping
logic can be tested without an event-store dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Iterable, Mapping, Sequence, cast

__all__ = [
    "OPEN_ORDER_STATUSES",
    "TRUE_VALUES",
    "build_halt_state",
    "build_market_data_status",
    "build_open_orders_status",
    "build_portfolio_status",
    "jsonable",
    "map_cycle_status_row",
    "map_run_status_row",
    "map_trading_session_status_row",
    "normalize_symbols",
    "parse_dt",
    "sequence",
    "to_float",
    "utc",
]

OPEN_ORDER_STATUSES = {"submitted", "accepted", "partially_filled", "error"}
TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def utc(value: datetime | None) -> datetime:
    """Return `value` as an aware UTC datetime, using current UTC time if absent."""
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_dt(value: object) -> datetime | None:
    """Parse event-store timestamp values into aware UTC datetimes."""
    if isinstance(value, datetime):
        return utc(value)
    if value is None:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def jsonable(value: object) -> object:
    """Return the JSON-safe representation used by runtime status payloads."""
    if isinstance(value, datetime):
        return utc(value).isoformat()
    return value


def to_float(value: object) -> float | None:
    """Convert numeric event-store values to float, returning `None` when absent."""
    if value is None:
        return None
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return None


def sequence(value: object) -> list[object] | None:
    """Normalize scalar, JSON string, or sequence values into a list."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return list(parsed) if isinstance(parsed, list) else [value]
    if isinstance(value, Sequence):
        return list(value)
    return [value]


def normalize_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    """Return configured symbols as non-empty uppercase values."""
    return tuple(symbol.strip().upper() for symbol in symbols if symbol.strip())


def map_run_status_row(row: Sequence[object]) -> dict[str, Any]:
    """Map a latest `runs` row into the runtime status payload shape."""
    return {
        "run_id": row[0],
        "run_type": row[1],
        "started_at": jsonable(row[2]),
        "finished_at": jsonable(row[3]),
        "status": row[4],
        "error_message": row[5],
        "mode": row[6],
        "symbols": sequence(row[7]),
        "timeframe": row[8],
        "start_ts": jsonable(row[9]),
        "end_ts": jsonable(row[10]),
    }


def map_trading_session_status_row(row: Sequence[object]) -> dict[str, Any]:
    """Map a latest `trading_sessions` row into the runtime status payload shape."""
    return {
        "session_id": row[0],
        "strategy_id": row[1],
        "started_at": jsonable(row[2]),
        "finished_at": jsonable(row[3]),
        "status": row[4],
        "error_message": row[5],
        "mode": row[6],
        "symbols": sequence(row[7]),
        "timeframe": row[8],
    }


def map_cycle_status_row(row: Sequence[object]) -> dict[str, Any]:
    """Map a latest `run_events` row into the runtime status payload shape."""
    return {
        "cycle_id": row[0],
        "run_id": row[1],
        "session_id": row[2],
        "strategy_id": row[3],
        "mode": row[4],
        "decision_ts": jsonable(row[5]),
        "started_at": jsonable(row[6]),
        "finished_at": jsonable(row[7]),
        "status": row[8],
        "error_message": row[9],
    }


def build_market_data_status(
    *,
    symbols: Sequence[str],
    timeframe: str,
    latest_by_symbol: Mapping[str, datetime | None],
    now: datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    """Build the market-data freshness subsection for runtime status."""
    if not symbols:
        return {"items": [], "missing_count": 0, "stale_count": 0, "max_age_seconds": max_age_seconds}
    items: list[dict[str, Any]] = []
    stale_count = 0
    missing_count = 0
    for symbol in symbols:
        ts = latest_by_symbol.get(symbol)
        age_seconds = (now - ts).total_seconds() if ts is not None else None
        missing = ts is None
        stale = age_seconds is not None and age_seconds > max_age_seconds
        if missing:
            missing_count += 1
        if stale:
            stale_count += 1
        items.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "latest_ts": jsonable(ts),
                "age_seconds": age_seconds,
                "missing": missing,
                "stale": stale,
            }
        )
    return {
        "items": items,
        "missing_count": missing_count,
        "stale_count": stale_count,
        "max_age_seconds": max_age_seconds,
    }


def build_portfolio_status(
    *,
    position_rows: Sequence[Sequence[object]],
    cash_rows: Sequence[Sequence[object]],
) -> dict[str, Any]:
    """Build the cash and position subsection for runtime status."""
    positions = [
        {
            "symbol": row[0],
            "qty": to_float(row[1]) or 0.0,
            "avg_price": to_float(row[2]),
            "asof_ts": jsonable(row[4]),
        }
        for row in position_rows
    ]
    return {
        "cash": (to_float(cash_rows[0][0]) or 0.0) if cash_rows and cash_rows[0][0] is not None else 0.0,
        "asof_ts": jsonable(cash_rows[0][1]) if cash_rows else None,
        "positions": positions,
        "position_count": len(positions),
    }


def build_open_orders_status(
    *,
    rows: Iterable[Sequence[object]],
    now: datetime,
    stale_after_seconds: int,
) -> dict[str, Any]:
    """Build current local open-order status from newest-first order rows."""
    seen: set[str] = set()
    orders: list[dict[str, Any]] = []
    stale_count = 0
    max_age_seconds: float | None = None
    for row in rows:
        client_order_id = str(row[0]) if row[0] is not None else ""
        if not client_order_id or client_order_id in seen:
            continue
        seen.add(client_order_id)
        status = str(row[8]).lower()
        if status not in OPEN_ORDER_STATUSES:
            continue
        created_at = parse_dt(row[11])
        age_seconds = (now - created_at).total_seconds() if created_at is not None else None
        stale = age_seconds is not None and age_seconds > stale_after_seconds
        if stale:
            stale_count += 1
        if age_seconds is not None:
            max_age_seconds = age_seconds if max_age_seconds is None else max(max_age_seconds, age_seconds)
        orders.append(
            {
                "client_order_id": client_order_id,
                "run_id": row[1],
                "session_id": row[2],
                "cycle_id": row[3],
                "symbol": row[4],
                "side": row[5],
                "qty": to_float(row[6]),
                "order_type": row[7],
                "status": row[8],
                "broker_order_id": row[9],
                "rejection_reason": row[10],
                "created_at": jsonable(created_at),
                "age_seconds": age_seconds,
                "stale": stale,
            }
        )
    return {
        "items": orders,
        "count": len(orders),
        "stale_count": stale_count,
        "max_age_seconds": max_age_seconds,
        "stale_after_seconds": stale_after_seconds,
    }


def build_halt_state(values: Mapping[str, str]) -> dict[str, Any]:
    """Build the normalized halt-state payload from config key/value rows."""
    raw_halt = str(values.get("halt", "")).strip().lower()
    return {
        "halted": raw_halt in TRUE_VALUES,
        "reason": values.get("halt_reason") or "",
        "updated_at": values.get("halt_updated_at"),
    }
