"""Runtime status queries and operator safety helpers.

The functions in this module convert event-store evidence into JSON-safe
operator payloads for CLI, API, and health-check consumers. They also own the
manual halt-state helpers used to stop live trading without changing strategy
code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence, cast

from ..config import Config
from ..event_store import EventStore
from .health import RuntimeHealthAssessment, assess_runtime_health, evaluate_health
from .status_payloads import (
    build_halt_state,
    build_market_data_status,
    build_open_orders_status,
    build_portfolio_status,
    map_cycle_status_row,
    map_run_status_row,
    map_trading_session_status_row,
    normalize_symbols,
    parse_dt,
    utc,
)

__all__ = [
    "RuntimeHealthAssessment",
    "assess_runtime_health",
    "evaluate_health",
    "get_halt_state",
    "latest_cycle_status",
    "latest_market_data_status",
    "latest_open_orders",
    "latest_portfolio_status",
    "latest_run_status",
    "latest_trading_session_status",
    "runtime_status",
    "set_halt_state",
]


def runtime_status(event_store: EventStore, config: Config, *, now: datetime | None = None) -> dict[str, Any]:
    """Build the complete operator status payload from event-store evidence.

    The result combines latest run/session/cycle rows, market-data freshness,
    portfolio state, open-order staleness, halt state, and a derived health
    classification into one JSON-serializable structure for CLI/API consumers.
    """
    now = utc(now)
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
    return map_run_status_row(rows[0])


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
    return map_trading_session_status_row(rows[0])


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
    return map_cycle_status_row(rows[0])


def latest_market_data_status(event_store: EventStore, config: Config, *, now: datetime | None = None) -> dict[str, Any]:
    """Summarize latest bar recency for the configured trading universe.

    The function chooses the stock or crypto event table from config, checks one
    latest timestamp per configured symbol/timeframe, and reports both missing
    symbols and symbols older than `market_data_max_age_seconds`.
    """
    now = utc(now)
    table = "crypto_bar_events" if config.market_data_asset_class.lower() in {"crypto", "cryptocurrency"} else "stock_bar_events"
    symbols = normalize_symbols(config.market_data_symbols)
    if not symbols:
        return build_market_data_status(
            symbols=symbols,
            timeframe=config.strategy_timeframe,
            latest_by_symbol={},
            now=now,
            max_age_seconds=config.market_data_max_age_seconds,
        )
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
    latest_by_symbol = {str(row[0]).upper(): parse_dt(row[1]) for row in rows}
    return build_market_data_status(
        symbols=symbols,
        timeframe=config.strategy_timeframe,
        latest_by_symbol=latest_by_symbol,
        now=now,
        max_age_seconds=config.market_data_max_age_seconds,
    )


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
    return build_portfolio_status(position_rows=rows, cash_rows=cash_rows)


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
    now = utc(now)
    rows = _fetch_all(
        event_store,
        """
        SELECT client_order_id, run_id, session_id, cycle_id, symbol, side, qty, order_type, status, broker_order_id, rejection_reason, created_at
        FROM order_events
        ORDER BY created_at DESC, order_event_id DESC
        """,
    )
    return build_open_orders_status(rows=rows, now=now, stale_after_seconds=stale_after_seconds)


def get_halt_state(event_store: EventStore) -> dict[str, Any]:
    """Read the operator-controlled global halt flag from `config_kv`.

    The returned mapping includes normalized boolean state, reason text, and the
    last update timestamp string when present.
    """
    return build_halt_state(_read_config_values(event_store, ("halt", "halt_reason", "halt_updated_at")))


def set_halt_state(event_store: EventStore, *, halted: bool, reason: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Write global halt state to config_kv and return the new state."""
    timestamp = utc(now).isoformat()
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
