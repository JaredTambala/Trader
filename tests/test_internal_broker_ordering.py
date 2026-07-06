"""Regression tests for internal broker order lifecycle ordering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trader.broker import InternalPaperBroker
from trader.broker.internal_execution import (
    InternalFeeModel,
    build_internal_fill_response,
    build_internal_rejection_response,
    normalize_internal_order,
)
from trader.cycle import _record_broker_responses, _record_order_events
from trader.identifiers import deterministic_client_order_id


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


def test_normalize_internal_order_returns_typed_request_without_mutating_input() -> None:
    order = {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": " aapl ",
        "side": " BUY ",
        "qty": "2.5",
        "price": "100.0",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    original = dict(order)

    request = normalize_internal_order(order)

    assert order == original
    assert request is not None
    assert request.symbol == "AAPL"
    assert request.side == "buy"
    assert request.qty == 2.5
    assert request.order_type == "market"
    assert normalize_internal_order({**order, "side": "hold"}) is None


def test_build_internal_fill_response_calculates_partial_sell_fill_deterministically() -> None:
    created_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    request = normalize_internal_order(
        {
            "run_id": "run_1",
            "cycle_id": "cycle_1",
            "symbol": "AAPL",
            "side": "sell",
            "qty": 2.0,
            "price": 100.0,
            "created_at": created_at,
        }
    )
    assert request is not None

    response = build_internal_fill_response(
        request,
        order_event_id="order_evt_fixed",
        timestamp=created_at,
        delay_ms=5.0,
        fill_fraction=0.5,
        slippage_bps=10.0,
        fee_model=InternalFeeModel(fixed_per_order=0.25, bps=5.0, minimum=0.5),
    )

    record = response.to_record()
    slippage_amount = record.pop("slippage_amount")
    assert record == {
        "order_event_id": "order_evt_fixed",
        "client_order_id": deterministic_client_order_id("cycle_1", "AAPL", "sell", 2.0),
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "status": "partially_filled",
        "broker_order_id": None,
        "order_type": "market",
        "qty": 2.0,
        "fill_ts": created_at + timedelta(milliseconds=5, microseconds=3),
        "fill_qty": 1.0,
        "fill_price": 99.9,
        "raw_fill_price": 100.0,
        "fee_amount": 0.5,
    }
    assert slippage_amount == pytest.approx(0.1)


def test_build_internal_rejection_response_uses_canonical_mapping_shape() -> None:
    fill_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    request = normalize_internal_order(
        {
            "client_order_id": "cid_reject",
            "run_id": "run_1",
            "cycle_id": "cycle_1",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 1.0,
        }
    )
    assert request is not None

    response = build_internal_rejection_response(
        request,
        order_event_id="order_evt_reject",
        fill_ts=fill_ts,
    )

    assert response.to_record() == {
        "order_event_id": "order_evt_reject",
        "client_order_id": "cid_reject",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "status": "rejected",
        "broker_order_id": None,
        "order_type": "market",
        "qty": 1.0,
        "fill_ts": fill_ts,
        "fill_qty": None,
        "fill_price": None,
        "rejection_reason": "internal_reject_probability",
    }
