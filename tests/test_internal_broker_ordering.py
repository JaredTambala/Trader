"""Regression tests for internal broker order lifecycle ordering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.broker import InternalPaperBroker
from trader.cycle import _record_broker_responses, _record_order_events


class _ListEventStore:
    def __init__(self) -> None:
        self.events: dict[str, list[dict[str, object]]] = {}

    def record_event(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.setdefault(event_type, []).append(dict(payload))


def test_internal_broker_fill_becomes_terminal_order_state() -> None:
    store = _ListEventStore()
    broker = InternalPaperBroker()
    base_ts = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    order = {
        "client_order_id": "order_test_internal_fill",
        "run_id": "run_test",
        "session_id": "run_test",
        "cycle_id": "cycle_test",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "price": 100.0,
        "order_type": "market",
        "created_at": base_ts,
    }

    _record_order_events(store, [order], status="created", event_ts=base_ts)
    _record_order_events(store, [order], status="validated", event_ts=base_ts + timedelta(seconds=1))
    _record_order_events(store, [order], status="submitted", event_ts=base_ts + timedelta(seconds=2))

    response = broker.submit_orders([order])[0]
    _record_broker_responses(store, [order], [response])

    lifecycle = sorted(
        store.events["order_events"],
        key=lambda event: (event["created_at"], str(event["order_event_id"])),
    )
    assert [event["status"] for event in lifecycle] == ["created", "validated", "submitted", "filled"]
    assert lifecycle[-1]["status"] == "filled"
    assert response["fill_ts"] > order["created_at"]
