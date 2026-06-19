"""Runtime status queries and operator safety helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Mapping, Sequence, cast

from .config import Config
from .event_store import EventStore

_OPEN_ORDER_STATUSES = {"submitted", "accepted", "partially_filled", "error"}
_TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def runtime_status(event_store: EventStore, config: Config, *, now: datetime | None = None) -> dict[str, Any]:
    """Build the complete operator status payload from event-store evidence.

    The result combines latest run/session/cycle rows, market-data freshness,
    portfolio state, open-order staleness, halt state, and a derived health
    classification into one JSON-serializable structure for CLI/API consumers.
    """
    now = _utc(now)
    latest_run = latest_run_status(event_store)
    latest_session = latest_trading_session_status(event_store)
    latest_cycle = latest_cycle_status(event_store)
    market_data = latest_market_data_status(event_store, config, now=now)
    portfolio = latest_portfolio_status(event_store)
    open_orders = latest_open_orders(event_store, now=now, stale_after_seconds=config.market_data_max_age_seconds)
    halt = get_halt_state(event_store)
    health = evaluate_health(
        latest_run=latest_run,
        latest_cycle=latest_cycle,
        market_data=market_data,
        open_orders=open_orders,
        halt=halt,
    )
    return {
        "generated_at": now.isoformat(),
        "health": health,
        "halt": halt,
        "latest_run": latest_run,
        "latest_trading_session": latest_session,
        "latest_cycle": latest_cycle,
        "market_data": market_data,
        "portfolio": portfolio,
        "open_orders": open_orders,
    }


def evaluate_health(
    *,
    latest_run: Mapping[str, Any] | None,
    latest_cycle: Mapping[str, Any] | None,
    market_data: Mapping[str, Any],
    open_orders: Mapping[str, Any],
    halt: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify runtime health from status subsections.

    Missing runs/cycles, active halt state, missing market data, and stale open
    orders degrade the result. Failed runs/cycles and stale market data are
    classified as unhealthy because they indicate trading decisions may be wrong
    or no longer operating.
    """
    reasons: list[str] = []
    exit_code = 0
    if latest_run is None:
        reasons.append("no_run")
        exit_code = max(exit_code, 1)
    elif str(latest_run.get("status", "")).lower() == "failed":
        reasons.append("latest_run_failed")
        exit_code = max(exit_code, 2)
    if latest_cycle is None:
        reasons.append("no_cycle")
        exit_code = max(exit_code, 1)
    elif str(latest_cycle.get("status", "")).lower() == "failed":
        reasons.append("latest_cycle_failed")
        exit_code = max(exit_code, 2)
    if bool(halt.get("halted")):
        reasons.append("halted")
        exit_code = max(exit_code, 1)
    if market_data.get("missing_count"):
        reasons.append("missing_market_data")
        exit_code = max(exit_code, 1)
    if market_data.get("stale_count"):
        reasons.append("stale_market_data")
        exit_code = max(exit_code, 2)
    if open_orders.get("stale_count"):
        reasons.append("stale_open_orders")
        exit_code = max(exit_code, 1)
    label = "healthy" if exit_code == 0 else "degraded" if exit_code == 1 else "unhealthy"
    return {"status": label, "exit_code": exit_code, "reasons": reasons}


def latest_run_status(event_store: EventStore) -> dict[str, Any] | None:
    """Return the newest aggregate run-session row, if one exists.

    The row is normalized into JSON-safe timestamp and symbol values for CLI and
    API consumers.
    """
    rows = _fetch_all(
        event_store,
        """
        SELECT run_id, run_type, started_at, finished_at, status, error_message, mode, symbols, timeframe, start_ts, end_ts
        FROM runs
        ORDER BY started_at DESC
        LIMIT 1
        """,
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "run_id": row[0],
        "run_type": row[1],
        "started_at": _jsonable(row[2]),
        "finished_at": _jsonable(row[3]),
        "status": row[4],
        "error_message": row[5],
        "mode": row[6],
        "symbols": _sequence(row[7]),
        "timeframe": row[8],
        "start_ts": _jsonable(row[9]),
        "end_ts": _jsonable(row[10]),
    }


def latest_trading_session_status(event_store: EventStore) -> dict[str, Any] | None:
    """Return the newest live trading-session row, if one exists.

    Trading sessions are separate from backtests so operator status can focus on
    the currently running or most recent live service run.
    """
    rows = _fetch_all(
        event_store,
        """
        SELECT session_id, strategy_id, started_at, finished_at, status, error_message, mode, symbols, timeframe
        FROM trading_sessions
        ORDER BY started_at DESC
        LIMIT 1
        """,
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "session_id": row[0],
        "strategy_id": row[1],
        "started_at": _jsonable(row[2]),
        "finished_at": _jsonable(row[3]),
        "status": row[4],
        "error_message": row[5],
        "mode": row[6],
        "symbols": _sequence(row[7]),
        "timeframe": row[8],
    }


def latest_cycle_status(event_store: EventStore) -> dict[str, Any] | None:
    """Return the newest decision-cycle lifecycle row, if one exists.

    This is the most recent per-decision lifecycle event and may differ from the
    latest aggregate run status when a service contains many cycles.
    """
    rows = _fetch_all(
        event_store,
        """
        SELECT cycle_id, run_id, session_id, strategy_id, mode, decision_ts, started_at, finished_at, status, error_message
        FROM run_events
        ORDER BY started_at DESC
        LIMIT 1
        """,
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "cycle_id": row[0],
        "run_id": row[1],
        "session_id": row[2],
        "strategy_id": row[3],
        "mode": row[4],
        "decision_ts": _jsonable(row[5]),
        "started_at": _jsonable(row[6]),
        "finished_at": _jsonable(row[7]),
        "status": row[8],
        "error_message": row[9],
    }


def latest_market_data_status(event_store: EventStore, config: Config, *, now: datetime | None = None) -> dict[str, Any]:
    """Summarize latest bar recency for the configured trading universe.

    The function chooses the stock or crypto event table from config, checks one
    latest timestamp per configured symbol/timeframe, and reports both missing
    symbols and symbols older than `market_data_max_age_seconds`.
    """
    now = _utc(now)
    table = "crypto_bar_events" if config.market_data_asset_class.lower() in {"crypto", "cryptocurrency"} else "stock_bar_events"
    symbols = tuple(symbol.strip().upper() for symbol in config.market_data_symbols if symbol.strip())
    if not symbols:
        return {"items": [], "missing_count": 0, "stale_count": 0, "max_age_seconds": config.market_data_max_age_seconds}
    placeholder = _placeholder(event_store)
    placeholders = ", ".join([placeholder] * len(symbols))
    rows = _fetch_all(
        event_store,
        f"""
        SELECT symbol, MAX(ts)
        FROM {table}
        WHERE symbol IN ({placeholders}) AND COALESCE(timeframe, '1Min') = {placeholder}
        GROUP BY symbol
        """,
        [*symbols, config.strategy_timeframe],
    )
    latest_by_symbol = {str(row[0]).upper(): _parse_dt(row[1]) for row in rows}
    items: list[dict[str, Any]] = []
    stale_count = 0
    missing_count = 0
    for symbol in symbols:
        ts = latest_by_symbol.get(symbol)
        age_seconds = (now - ts).total_seconds() if ts is not None else None
        missing = ts is None
        stale = age_seconds is not None and age_seconds > config.market_data_max_age_seconds
        if missing:
            missing_count += 1
        if stale:
            stale_count += 1
        items.append(
            {
                "symbol": symbol,
                "timeframe": config.strategy_timeframe,
                "latest_ts": _jsonable(ts),
                "age_seconds": age_seconds,
                "missing": missing,
                "stale": stale,
            }
        )
    return {
        "items": items,
        "missing_count": missing_count,
        "stale_count": stale_count,
        "max_age_seconds": config.market_data_max_age_seconds,
    }


def latest_portfolio_status(event_store: EventStore) -> dict[str, Any]:
    """Return latest cash and one latest position snapshot per symbol.

    Position rows are de-duplicated by symbol using the latest snapshot
    timestamp, while cash comes from the newest snapshot row overall.
    """
    rows = _fetch_all(
        event_store,
        """
        SELECT symbol, qty, avg_price, cash_balance, asof_ts
        FROM (
            SELECT
                symbol,
                qty,
                avg_price,
                cash_balance,
                asof_ts,
                ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY asof_ts DESC) AS rn
            FROM position_snapshots
            WHERE symbol IS NOT NULL
        ) ranked
        WHERE rn = 1
        ORDER BY symbol
        """,
    )
    cash_rows = _fetch_all(
        event_store,
        """
        SELECT cash_balance, asof_ts
        FROM position_snapshots
        ORDER BY asof_ts DESC
        LIMIT 1
        """,
    )
    positions = [
        {
            "symbol": row[0],
            "qty": _to_float(row[1]) or 0.0,
            "avg_price": _to_float(row[2]),
            "asof_ts": _jsonable(row[4]),
        }
        for row in rows
    ]
    return {
        "cash": (_to_float(cash_rows[0][0]) or 0.0) if cash_rows and cash_rows[0][0] is not None else 0.0,
        "asof_ts": _jsonable(cash_rows[0][1]) if cash_rows else None,
        "positions": positions,
        "position_count": len(positions),
    }


def latest_open_orders(
    event_store: EventStore,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = 60,
) -> dict[str, Any]:
    """Return current local open orders with age and stale-order counts.

    The query reads all order lifecycle rows newest first, keeps only the latest
    row per `client_order_id`, and then filters to statuses that still represent
    local open risk.
    """
    now = _utc(now)
    rows = _fetch_all(
        event_store,
        """
        SELECT client_order_id, run_id, session_id, cycle_id, symbol, side, qty, order_type, status, broker_order_id, rejection_reason, created_at
        FROM order_events
        ORDER BY created_at DESC, order_event_id DESC
        """,
    )
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
        if status not in _OPEN_ORDER_STATUSES:
            continue
        created_at = _parse_dt(row[11])
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
                "qty": _to_float(row[6]),
                "order_type": row[7],
                "status": row[8],
                "broker_order_id": row[9],
                "rejection_reason": row[10],
                "created_at": _jsonable(created_at),
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


def get_halt_state(event_store: EventStore) -> dict[str, Any]:
    """Read the operator-controlled global halt flag from `config_kv`.

    The returned mapping includes normalized boolean state, reason text, and the
    last update timestamp string when present.
    """
    values = _read_config_values(event_store, ("halt", "halt_reason", "halt_updated_at"))
    raw_halt = str(values.get("halt", "")).strip().lower()
    return {
        "halted": raw_halt in _TRUE_VALUES,
        "reason": values.get("halt_reason") or "",
        "updated_at": values.get("halt_updated_at"),
    }


def set_halt_state(event_store: EventStore, *, halted: bool, reason: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Write global halt state to config_kv and return the new state."""
    timestamp = _utc(now).isoformat()
    _write_config_value(event_store, "halt", "true" if halted else "false")
    _write_config_value(event_store, "halt_reason", reason or "")
    _write_config_value(event_store, "halt_updated_at", timestamp)
    return get_halt_state(event_store)


def _read_config_values(event_store: EventStore, keys: Sequence[str]) -> dict[str, str]:
    placeholder = _placeholder(event_store)
    rows = _fetch_all(
        event_store,
        f"SELECT key, value FROM config_kv WHERE key IN ({', '.join([placeholder] * len(keys))})",
        list(keys),
    )
    return {str(row[0]): str(row[1]) for row in rows}


def _write_config_value(event_store: EventStore, key: str, value: str) -> None:
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        raise ValueError("Event store does not expose a SQL connection")
    placeholder = _placeholder(event_store)
    if placeholder == "?":
        query = "INSERT INTO config_kv (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value"
    else:
        query = "INSERT INTO config_kv (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = excluded.value"
    _execute(connection, query, [key, value])


def _fetch_all(event_store: EventStore, query: str, params: Sequence[object] | None = None) -> list[Sequence[object]]:
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return []
    return list(_execute(connection, query, params or []).fetchall())


def _execute(connection: object, query: str, params: Sequence[object]) -> Any:
    if hasattr(connection, "cursor"):
        cursor = connection.cursor()
        cursor.execute(query, list(params))
        return cursor
    return cast(Any, connection).execute(query, list(params))


def _placeholder(event_store: EventStore) -> str:
    connection = getattr(event_store, "connection", lambda: None)()
    module_name = connection.__class__.__module__ if connection is not None else ""
    return "?" if "duckdb" in module_name else "%s"


def _utc(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if value is None:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return _utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def _jsonable(value: object) -> object:
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    return value


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return None


def _sequence(value: object) -> list[object] | None:
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
