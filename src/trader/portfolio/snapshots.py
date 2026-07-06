"""Pure snapshot records and query plans for portfolio state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol, Sequence

__all__ = [
    "PortfolioQueryPlan",
    "PositionSnapshotEvent",
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
class PositionSnapshotEvent:
    """Event-store record for one portfolio position snapshot row."""

    event_type: str
    payload: Mapping[str, object]


@dataclass(frozen=True)
class PortfolioQueryPlan:
    """Parameterized query plan for portfolio snapshot reads."""

    query: str
    parameters: tuple[object, ...] = ()


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
