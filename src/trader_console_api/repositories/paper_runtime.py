"""Read adapter for the published paper-runtime evidence projections."""

from __future__ import annotations

from typing import Any

from .database import ConsoleDatabase
from .resources import _row_dicts


class PaperRuntimeRepository:
    """Load paper-runtime evidence in one read-only database transaction."""

    def __init__(self, database: ConsoleDatabase) -> None:
        """Bind the repository to the Console database policy."""
        self._database = database

    async def snapshot(self, *, stale_after_seconds: int) -> dict[str, Any]:
        """Return bounded session, order, fill, portfolio and risk evidence."""
        async with self._database.transaction() as connection:
            session_cursor = await connection.execute(
                """
                SELECT session_id, strategy_id, started_at, finished_at, status,
                       error_message, mode, symbols, timeframe
                FROM console_read.sessions
                ORDER BY started_at DESC NULLS LAST, session_id
                LIMIT 1
                """
            )
            sessions = _row_dicts(session_cursor, await session_cursor.fetchall())
            session = sessions[0] if sessions else None

            freshness_cursor = await connection.execute(
                """
                SELECT 'stock'::text AS asset_class, symbol, timeframe,
                       max(ts) AS latest_ts
                FROM console_read.stock_bars
                GROUP BY symbol, timeframe
                UNION ALL
                SELECT 'crypto'::text AS asset_class, symbol, timeframe,
                       max(ts) AS latest_ts
                FROM console_read.crypto_bars
                GROUP BY symbol, timeframe
                ORDER BY asset_class, symbol, timeframe
                """
            )
            freshness = _row_dicts(freshness_cursor, await freshness_cursor.fetchall())

            positions_cursor = await connection.execute(
                """
                SELECT DISTINCT ON (symbol) symbol, qty, avg_price, asof_ts, cash_balance
                FROM console_read.positions
                ORDER BY symbol, asof_ts DESC NULLS LAST
                """
            )
            positions = _row_dicts(positions_cursor, await positions_cursor.fetchall())

            orders_cursor = await connection.execute(
                """
                SELECT DISTINCT ON (client_order_id)
                       client_order_id, broker_order_id, symbol, side, qty,
                       order_type, status, created_at, rejection_reason
                FROM console_read.orders
                ORDER BY client_order_id, created_at DESC NULLS LAST, order_event_id DESC
                """
            )
            orders = _row_dicts(orders_cursor, await orders_cursor.fetchall())

            fills_cursor = await connection.execute(
                """
                SELECT client_order_id, fill_ts, fill_qty, fill_price,
                       fee_amount, slippage_amount
                FROM console_read.fills
                ORDER BY fill_ts DESC NULLS LAST
                LIMIT 500
                """
            )
            fills = _row_dicts(fills_cursor, await fills_cursor.fetchall())

            risk: list[dict[str, Any]] = []
            if session and session.get("session_id"):
                risk_cursor = await connection.execute(
                    """
                    SELECT outcome, count(*)::integer AS count
                    FROM console_read.risk_decisions
                    WHERE session_id = %s
                    GROUP BY outcome
                    """,
                    [session["session_id"]],
                )
                risk = _row_dicts(risk_cursor, await risk_cursor.fetchall())

        return {
            "session": session,
            "freshness": freshness,
            "positions": positions,
            "orders": orders,
            "fills": fills,
            "risk": risk,
            "stale_after_seconds": stale_after_seconds,
        }
