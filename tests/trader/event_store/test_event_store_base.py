"""Contracts for lifecycle behavior supplied by the base event-store interface.

Subject: Default run, trading-session, cycle, and experiment lifecycle event emission.
Level: Deterministic interface unit contracts.
Collaborators: The real EventStore base class, a recording implementation, and fixed timestamps.
Guarantees: High-level lifecycle calls emit complete canonical records through the generic write boundary.
Non-goals: Backend-specific SQL, transaction behavior, filtering, buffering, or runtime orchestration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from trader.event_store import EventStore


class RecordingEventStore(EventStore):
    """Concrete EventStore that records emitted append-only events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Mapping[str, object]]] = []

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Record one event emitted by default lifecycle methods."""
        self.events.append((event_type, dict(payload)))


def test_default_run_session_methods_emit_trading_session_records() -> None:
    """Ensure default run-session methods fan out trading run records."""
    started_at = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 1, 21, 12, 5, tzinfo=timezone.utc)
    store = RecordingEventStore()

    store.record_run_session_start(
        "run_1",
        "trading",
        started_at,
        strategy_id="demo",
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )
    store.record_run_session_finish(
        "run_1",
        "trading",
        started_at,
        finished_at,
        "success",
        None,
        strategy_id="demo",
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )

    assert [event_type for event_type, _ in store.events] == [
        "runs",
        "trading_sessions",
        "runs",
        "trading_sessions",
    ]
    assert store.events[0][1]["run_id"] == "run_1"
    assert store.events[1][1]["session_id"] == "run_1"
    assert store.events[1][1]["strategy_id"] == "demo"
    assert store.events[2][1]["status"] == "success"
    assert store.events[3][1]["finished_at"] == finished_at


def test_default_run_session_methods_skip_session_records_for_backtests() -> None:
    """Ensure default run-session methods only emit run records for backtests."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    store = RecordingEventStore()

    store.record_run_session_start("run_1", "backtest", timestamp, strategy_id="demo")
    store.record_run_session_finish(
        "run_1", "backtest", timestamp, timestamp, "success", None
    )

    assert [event_type for event_type, _ in store.events] == ["runs", "runs"]


def test_default_cycle_and_legacy_run_methods_emit_run_events() -> None:
    """Ensure cycle and legacy run aliases use the run-events lifecycle shape."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    store = RecordingEventStore()

    store.record_cycle_start("run_1", "cycle_1", "demo", "once", timestamp, timestamp)
    store.record_run_finish(
        "legacy_run", "demo", "once", timestamp, timestamp, timestamp, "failed", "boom"
    )

    assert [event_type for event_type, _ in store.events] == [
        "run_events",
        "run_events",
    ]
    assert store.events[0][1]["cycle_id"] == "cycle_1"
    assert store.events[0][1]["session_id"] == "run_1"
    assert store.events[1][1]["cycle_id"] == "legacy_run"
    assert store.events[1][1]["status"] == "failed"


def test_default_experiment_methods_emit_append_only_records() -> None:
    """Ensure default experiment methods emit generic append-only records."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    store = RecordingEventStore()

    store.upsert_experiment(
        experiment_id="exp_1",
        name="Demo",
        tags=("baseline",),
        created_at=timestamp,
        updated_at=timestamp,
        metadata={"owner": "test"},
    )
    store.record_experiment_run_start(
        experiment_run_id="exp_run_1",
        experiment_id="exp_1",
        run_id="run_1",
        created_at=timestamp,
        parameters={"fast": 2},
    )
    store.record_experiment_run_finish(
        experiment_run_id="exp_run_1",
        experiment_id="exp_1",
        run_id="run_1",
        status="success",
        finished_at=timestamp,
        result_summary={"total_return": 0.1},
    )

    assert [event_type for event_type, _ in store.events] == [
        "experiments",
        "experiment_runs",
        "experiment_runs",
    ]
    assert store.events[0][1]["metadata"] == {"owner": "test"}
    assert store.events[1][1]["parameters"] == {"fast": 2}
    assert store.events[2][1]["result_summary"] == {"total_return": 0.1}
