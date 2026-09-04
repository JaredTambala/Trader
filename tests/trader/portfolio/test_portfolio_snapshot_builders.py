"""Contracts for constructing deterministic portfolio snapshot values.

Subject: Position ordering, cash, timestamps, run/session lineage, shell delegation, and cash-neutral snapshots.
Level: Pure domain unit contracts.
Collaborators: Real snapshot builders and mutable portfolio shell with fixed in-memory values.
Guarantees: Explicit state produces reproducible immutable snapshots without losing caller-selected ordering.
Non-goals: Event persistence, row reconstruction, broker truth, lifecycle timing, or portfolio transitions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from trader.portfolio import Portfolio, Position
from trader.portfolio.snapshots import (
    PortfolioSnapshotState,
    build_cash_neutral_snapshot,
    build_portfolio_snapshot,
)


def test_build_portfolio_snapshot_sorts_positions_and_resolves_session() -> None:
    """Snapshot construction is deterministic for an explicit timestamp."""
    asof_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)

    snapshot = build_portfolio_snapshot(
        state=PortfolioSnapshotState(
            positions={
                "MSFT": Position("MSFT", 2.0, 50.0),
                "AAPL": Position("AAPL", 1.0, 100.0),
            },
            cash_balance=500.0,
        ),
        asof_ts=asof_ts,
        run_id="run-1",
        cycle_id="cycle-1",
    )

    assert snapshot.asof_ts == asof_ts
    assert tuple(position.symbol for position in snapshot.positions) == ("AAPL", "MSFT")
    assert snapshot.cash_balance == 500.0
    assert snapshot.session_id == "run-1"


def test_portfolio_snapshot_delegates_to_builder() -> None:
    """The mutable shell uses the same deterministic builder."""
    asof_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    portfolio = Portfolio(
        positions={
            "MSFT": Position("MSFT", 2.0, 50.0),
            "AAPL": Position("AAPL", 1.0, 100.0),
        },
        cash_balance=500.0,
    )

    snapshot = portfolio.snapshot(asof_ts=asof_ts, run_id="run-1", cycle_id="cycle-1")

    assert tuple(position.symbol for position in snapshot.positions) == ("AAPL", "MSFT")
    assert snapshot.asof_ts == asof_ts
    assert snapshot.session_id == "run-1"


def test_build_cash_neutral_snapshot_preserves_explicit_order() -> None:
    """Ensure cash-neutral snapshots retain the position ordering supplied by the caller."""
    positions = (
        Position("MSFT", 2.0, 50.0),
        Position("AAPL", 1.0, 100.0),
    )
    asof_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)

    snapshot = build_cash_neutral_snapshot(positions=positions, asof_ts=asof_ts)

    assert snapshot.positions == positions
    assert snapshot.cash_balance == 0.0
