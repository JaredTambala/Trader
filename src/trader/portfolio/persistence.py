"""Side-effecting portfolio snapshot persistence helpers."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Protocol, Sequence

from ..event_store import EventStore
from .models import PortfolioState, Position
from .reconstruction import (
    cash_balance_from_snapshot_row,
    portfolio_state_from_loaded_values,
    positions_from_snapshot_rows,
)
from .snapshots import (
    PositionSnapshotInput,
    build_position_snapshot_events,
    latest_cash_query_plan,
    latest_positions_query_plan,
)


logger = logging.getLogger(__name__)


class PortfolioSnapshotInput(Protocol):
    """Minimal snapshot shape needed to persist portfolio state."""

    asof_ts: datetime
    positions: Sequence[PositionSnapshotInput]
    cash_balance: float
    run_id: str | None
    cycle_id: str | None
    session_id: str | None


def persist_portfolio_snapshot(snapshot: PortfolioSnapshotInput, event_store: EventStore) -> None:
    """Append a portfolio snapshot to the event store.

    Each position becomes one `position_snapshots` event with the same cash
    balance and correlation IDs. When no positions exist, a sentinel row is
    written so cash-only state is not lost.
    """
    for event in build_position_snapshot_events(
        asof_ts=snapshot.asof_ts,
        positions=snapshot.positions,
        cash_balance=snapshot.cash_balance,
        run_id=snapshot.run_id,
        cycle_id=snapshot.cycle_id,
        session_id=snapshot.session_id,
    ):
        event_store.record_event(event.event_type, event.payload)


def load_latest_positions(event_store: EventStore, *, asof_ts: datetime | None = None) -> list[Position]:
    """Load one latest non-empty position snapshot per symbol.

    Args:
        event_store: Store with a SQL connection.
        asof_ts: Optional upper timestamp bound; used by backtests to avoid
            reading future snapshots.

    Returns:
        Position objects reconstructed from the latest row for each symbol. An
        empty list is returned when the store has no readable connection.
    """
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Portfolio load skipped; event store has no connection")
        return []

    if hasattr(connection, "cursor"):
        with connection.cursor() as cursor:
            plan = latest_positions_query_plan(connection, asof_ts=asof_ts)
            _execute_query_plan(cursor, plan.query, plan.parameters)
            rows = cursor.fetchall()
            positions = positions_from_snapshot_rows(rows)
            logger.info("Loaded portfolio positions count=%s", len(positions))
            return positions

    return []


def load_latest_cash(event_store: EventStore, *, asof_ts: datetime | None = None) -> float | None:
    """Load the latest recorded cash balance from position snapshots.

    Args:
        event_store: Store with a SQL connection.
        asof_ts: Optional upper timestamp bound for historical reconstruction.

    Returns:
        Latest cash balance, or `None` when no snapshot is available.
    """
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Cash load skipped; event store has no connection")
        return None

    if hasattr(connection, "cursor"):
        with connection.cursor() as cursor:
            plan = latest_cash_query_plan(connection, asof_ts=asof_ts)
            _execute_query_plan(cursor, plan.query, plan.parameters)
            row = cursor.fetchone()
            return cash_balance_from_snapshot_row(row)
    return None


def load_latest_portfolio_state(
    event_store: EventStore,
    *,
    asof_ts: datetime | None = None,
) -> PortfolioState:
    """Load latest portfolio positions and cash into immutable state."""
    return portfolio_state_from_loaded_values(
        positions=load_latest_positions(event_store, asof_ts=asof_ts),
        cash_balance=load_latest_cash(event_store, asof_ts=asof_ts),
    )


def _execute_query_plan(cursor: object, query: str, parameters: Sequence[object]) -> None:
    """Execute a query plan with DB-API-compatible optional parameters."""
    if parameters:
        cursor.execute(query, list(parameters))
        return
    cursor.execute(query)


__all__ = [
    "PortfolioSnapshotInput",
    "load_latest_cash",
    "load_latest_portfolio_state",
    "load_latest_positions",
    "persist_portfolio_snapshot",
]
