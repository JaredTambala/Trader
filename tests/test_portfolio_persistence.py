"""Tests for explicit portfolio snapshot persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from trader.portfolio import PortfolioSnapshot, Position, persist_portfolio_snapshot
from trader.portfolio.core import load_latest_cash as core_load_latest_cash
from trader.portfolio.core import load_latest_portfolio_state as core_load_latest_portfolio_state
from trader.portfolio.core import load_latest_positions as core_load_latest_positions
from trader.portfolio.persistence import load_latest_cash, load_latest_portfolio_state, load_latest_positions


@dataclass
class RecordingEventStore:
    """Minimal event-store test double for snapshot persistence."""

    events: list[tuple[str, Mapping[str, object]]]

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Record the event without touching external storage."""
        self.events.append((event_type, payload))


def test_persist_portfolio_snapshot_records_position_events() -> None:
    """The explicit shell helper writes one event per position."""
    store = RecordingEventStore(events=[])
    asof_ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    snapshot = PortfolioSnapshot(
        asof_ts=asof_ts,
        positions=(Position("AAPL", 2.0, 100.0),),
        cash_balance=750.0,
        run_id="run-1",
        cycle_id="cycle-1",
    )

    persist_portfolio_snapshot(snapshot, store)

    assert store.events == [
        (
            "position_snapshots",
            {
                "asof_ts": asof_ts,
                "symbol": "AAPL",
                "qty": 2.0,
                "avg_price": 100.0,
                "cash_balance": 750.0,
                "run_id": "run-1",
                "cycle_id": "cycle-1",
                "session_id": "run-1",
            },
        )
    ]


def test_portfolio_snapshot_persist_delegates_for_existing_callers() -> None:
    """The legacy method remains as a thin compatibility shell."""
    store = RecordingEventStore(events=[])
    snapshot = PortfolioSnapshot(
        asof_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
        positions=(),
        cash_balance=1000.0,
    )

    snapshot.persist(store)

    assert store.events[0][0] == "position_snapshots"
    assert store.events[0][1]["symbol"] is None


def test_portfolio_core_re_exports_persistence_loaders() -> None:
    """Direct core imports continue to resolve after moving I/O helpers."""
    assert core_load_latest_cash is load_latest_cash
    assert core_load_latest_portfolio_state is load_latest_portfolio_state
    assert core_load_latest_positions is load_latest_positions
