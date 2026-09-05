"""Snapshot value objects, records, and query plans for portfolio state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Mapping, Protocol, Sequence

if TYPE_CHECKING:
    from ..event_store import EventStore

__all__ = [
    "PortfolioQueryPlan",
    "PortfolioSnapshot",
    "PortfolioSnapshotState",
    "PositionSnapshotEvent",
    "build_cash_neutral_snapshot",
    "build_portfolio_snapshot",
    "build_position_snapshot_events",
    "latest_cash_query_plan",
    "latest_positions_query_plan",
]


class PositionSnapshotInput(Protocol):
    """Minimal position shape needed for snapshot event payloads."""

    symbol: str
    qty: float
    avg_price: float | None


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Portfolio state persisted as one row per position at a timestamp.

    An empty portfolio is represented by a single row with `symbol=None` so cash
    can still be reconstructed from the event store.
    """

    asof_ts: datetime
    positions: Sequence[PositionSnapshotInput]
    cash_balance: float
    run_id: str | None = None
    cycle_id: str | None = None
    session_id: str | None = None

    def persist(self, event_store: EventStore) -> None:
        """Append this snapshot to the event store.

        Prefer `persist_portfolio_snapshot(snapshot, event_store)` in new code
        so the side effect remains explicit at the shell boundary.
        """
        from .persistence import persist_portfolio_snapshot

        persist_portfolio_snapshot(self, event_store)


@dataclass(frozen=True)
class PortfolioSnapshotState:
    """Pure input state for constructing an ordered portfolio snapshot."""

    positions: Mapping[str, PositionSnapshotInput]
    cash_balance: float


@dataclass(frozen=True)
class PositionSnapshotEvent:
    """Event-store record for one portfolio position snapshot row."""

    event_type: str
    payload: Mapping[str, object]


@dataclass(frozen=True)
class PortfolioQueryPlan:
    """Parameterized query plan for portfolio snapshot reads."""

    query: str
    parameters: tuple[object, ...] = ()


def build_portfolio_snapshot(
    *,
    state: PortfolioSnapshotState,
    asof_ts: datetime,
    run_id: str | None = None,
    cycle_id: str | None = None,
    session_id: str | None = None,
) -> PortfolioSnapshot:
    """Return a deterministic snapshot from explicit portfolio state."""
    positions = tuple(state.positions[symbol] for symbol in sorted(state.positions))
    return PortfolioSnapshot(
        asof_ts=asof_ts,
        positions=positions,
        cash_balance=state.cash_balance,
        run_id=run_id,
        cycle_id=cycle_id,
        session_id=session_id or run_id,
    )


def build_cash_neutral_snapshot(
    *,
    positions: Sequence[PositionSnapshotInput],
    asof_ts: datetime,
) -> PortfolioSnapshot:
    """Return a cash-neutral snapshot for explicit position inputs."""
    return PortfolioSnapshot(
        asof_ts=asof_ts,
        positions=tuple(positions),
        cash_balance=0.0,
    )


def build_position_snapshot_events(
    *,
    asof_ts: datetime,
    positions: Sequence[PositionSnapshotInput],
    cash_balance: float,
    run_id: str | None,
    cycle_id: str | None,
    session_id: str | None,
) -> tuple[PositionSnapshotEvent, ...]:
    """Return event-store records for one portfolio snapshot.

    Empty portfolios emit a sentinel row with `symbol=None` so cash-only state
    remains reconstructable from the append-only event stream.
    """
    resolved_session_id = session_id or run_id
    if not positions:
        return (
            PositionSnapshotEvent(
                "position_snapshots",
                _position_snapshot_payload(
                    asof_ts=asof_ts,
                    symbol=None,
                    qty=0.0,
                    avg_price=None,
                    cash_balance=cash_balance,
                    run_id=run_id,
                    cycle_id=cycle_id,
                    session_id=resolved_session_id,
                ),
            ),
        )
    return tuple(
        PositionSnapshotEvent(
            "position_snapshots",
            _position_snapshot_payload(
                asof_ts=asof_ts,
                symbol=position.symbol,
                qty=position.qty,
                avg_price=position.avg_price,
                cash_balance=cash_balance,
                run_id=run_id,
                cycle_id=cycle_id,
                session_id=resolved_session_id,
            ),
        )
        for position in positions
    )


def latest_positions_query_plan(
    connection: object,
    *,
    asof_ts: datetime | None = None,
) -> PortfolioQueryPlan:
    """Return the query plan for latest non-empty position snapshots."""
    if asof_ts is None:
        return PortfolioQueryPlan(
            """
                    SELECT symbol, qty, avg_price
                    FROM (
                        SELECT
                            symbol,
                            qty,
                            avg_price,
                            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY asof_ts DESC) AS rn
                        FROM position_snapshots
                        WHERE symbol IS NOT NULL AND symbol <> ''
                    ) AS ranked
                    WHERE rn = 1
                    """
        )
    placeholder = _param_placeholder(connection)
    return PortfolioQueryPlan(
        f"""
                    SELECT symbol, qty, avg_price
                    FROM (
                        SELECT
                            symbol,
                            qty,
                            avg_price,
                            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY asof_ts DESC) AS rn
                        FROM position_snapshots
                        WHERE asof_ts <= {placeholder} AND symbol IS NOT NULL AND symbol <> ''
                    ) AS ranked
                    WHERE rn = 1
                    """,
        (asof_ts,),
    )


def latest_cash_query_plan(
    connection: object,
    *,
    asof_ts: datetime | None = None,
) -> PortfolioQueryPlan:
    """Return the query plan for latest portfolio cash balance."""
    if asof_ts is None:
        return PortfolioQueryPlan(
            """
                    SELECT cash_balance
                    FROM position_snapshots
                    ORDER BY asof_ts DESC
                    LIMIT 1
                    """
        )
    placeholder = _param_placeholder(connection)
    return PortfolioQueryPlan(
        f"""
                    SELECT cash_balance
                    FROM position_snapshots
                    WHERE asof_ts <= {placeholder}
                    ORDER BY asof_ts DESC
                    LIMIT 1
                    """,
        (asof_ts,),
    )


def _position_snapshot_payload(
    *,
    asof_ts: datetime,
    symbol: str | None,
    qty: float,
    avg_price: float | None,
    cash_balance: float,
    run_id: str | None,
    cycle_id: str | None,
    session_id: str | None,
) -> dict[str, object]:
    return {
        "asof_ts": asof_ts,
        "symbol": symbol,
        "qty": qty,
        "avg_price": avg_price,
        "cash_balance": cash_balance,
        "run_id": run_id,
        "cycle_id": cycle_id,
        "session_id": session_id,
    }


def _param_placeholder(connection: object) -> str:
    module = connection.__class__.__module__
    if module.startswith("duckdb"):
        return "?"
    return "%s"
