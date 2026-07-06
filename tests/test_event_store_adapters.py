"""Tests for event-store adapter policy behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from trader.event_store import EventStore, FilteredEventStore
from trader.event_store.filtering import build_event_filter_policy


class RecordingEventStore(EventStore):
    """Concrete event-store fake for adapter delegation tests."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Mapping[str, object]]] = []

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Record delegated events."""
        self.events.append((event_type, dict(payload)))


def test_event_filter_policy_is_immutable_and_checks_allowed_events() -> None:
    """Ensure filtering decisions are pure and independent of caller mutation."""
    allowed = {"signal_events"}
    policy = build_event_filter_policy(allowed)

    allowed.add("order_events")

    assert policy.allows("signal_events") is True
    assert policy.allows("order_events") is False


def test_filtered_event_store_filters_only_generic_record_events() -> None:
    """Ensure ordinary event writes are delegated only when allowed."""
    inner = RecordingEventStore()
    store = FilteredEventStore(inner, allowed_event_types={"signal_events"})

    store.record_event("indicator_events", {"value": 1.0})
    store.record_event("signal_events", {"signal_value": 1.0})

    assert inner.events == [("signal_events", {"signal_value": 1.0})]


def test_filtered_event_store_lifecycle_methods_bypass_optional_filters() -> None:
    """Ensure required lifecycle records are delegated through the wrapper."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    inner = RecordingEventStore()
    store = FilteredEventStore(inner, allowed_event_types=set())

    store.record_cycle_start(
        run_id="run_1",
        cycle_id="cycle_1",
        strategy_id="demo",
        mode="once",
        decision_ts=timestamp,
        started_at=timestamp,
    )

    assert inner.events == [
        (
            "run_events",
            {
                "run_id": "run_1",
                "cycle_id": "cycle_1",
                "session_id": "run_1",
                "strategy_id": "demo",
                "mode": "once",
                "decision_ts": timestamp,
                "started_at": timestamp,
                "finished_at": None,
                "status": "started",
                "error_message": None,
            },
        )
    ]
