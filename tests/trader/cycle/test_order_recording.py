"""Cycle order enrichment and lifecycle-recording contracts.

Subject: Order normalization, deterministic metadata, lifecycle timestamps, broker responses, and fill evidence.
Level: Pure order-recording unit contracts.
Collaborators: Real cycle order builders and identifier helpers with fixed mapping inputs.
Guarantees: Caller inputs remain unchanged while ordered canonical events and missing-fill evidence stay explicit.
Non-goals: Broker calls, risk authorization, persistence, portfolio mutation, or whole-cycle execution.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.cycle import (
    build_broker_fill_event_payload,
    build_broker_response_recording_plan,
    build_enriched_cycle_order,
    build_order_lifecycle_event_payload,
    normalize_cycle_order_intent,
    resolve_order_lifecycle_event_timestamp,
    resolve_terminal_event_timestamp,
)
from trader.cycle.orders import _attach_order_metadata
from trader.identifiers import deterministic_client_order_id


def test_normalize_cycle_order_intent_preserves_source_without_mutation() -> None:
    """Normalize identity fields while retaining untouched caller-owned order evidence."""
    order = {"symbol": " aapl ", "side": " BUY ", "qty": "2.5"}
    original = dict(order)

    intent = normalize_cycle_order_intent(order)

    assert order == original
    assert intent.source is order
    assert intent.symbol == "AAPL"
    assert intent.side == "buy"
    assert intent.qty == 2.5


def test_build_enriched_cycle_order_attaches_deterministic_metadata() -> None:
    """Attach deterministic identity, lineage, price, and venue fields to intent."""
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    order = {"symbol": " aapl ", "side": " BUY ", "qty": "2.5"}
    original = dict(order)

    enriched = build_enriched_cycle_order(
        order,
        run_id="run_1",
        cycle_id="cycle_1",
        created_at=created_at,
        price_lookup={"AAPL": 101.25},
        asset_class="stocks",
        time_in_force="day",
    )

    assert order == original
    assert enriched.to_record() == {
        **order,
        "symbol": "AAPL",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "client_order_id": deterministic_client_order_id("cycle_1", "AAPL", "buy", 2.5),
        "price": 101.25,
        "created_at": created_at,
        "asset_class": "stocks",
        "time_in_force": "day",
    }


def test_build_enriched_cycle_order_preserves_explicit_order_fields() -> None:
    """Preserve explicit client identity, creation time, and time-in-force values."""
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    explicit_created_at = created_at.replace(hour=13)
    order = {
        "symbol": "MSFT",
        "side": "sell",
        "qty": 1.0,
        "client_order_id": "cid_explicit",
        "created_at": explicit_created_at,
        "time_in_force": "gtc",
    }

    enriched = build_enriched_cycle_order(
        order,
        run_id="run_1",
        cycle_id="cycle_1",
        created_at=created_at,
        price_lookup={},
        asset_class="stocks",
        time_in_force="day",
    )

    record = enriched.to_record()
    assert record["client_order_id"] == "cid_explicit"
    assert record["created_at"] == explicit_created_at
    assert record["time_in_force"] == "gtc"
    assert record["price"] is None


def test_attach_order_metadata_enriches_batch_without_mutating_inputs() -> None:
    """Enrich a batch consistently without changing any source order mapping."""
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    orders = [
        {"symbol": " aapl ", "side": "BUY", "qty": "2"},
        {"symbol": "MSFT", "side": "sell", "qty": 1.5, "time_in_force": "gtc"},
    ]
    originals = [dict(order) for order in orders]

    enriched = _attach_order_metadata(
        orders,
        run_id="run_1",
        cycle_id="cycle_1",
        created_at=created_at,
        price_lookup={"AAPL": 101.0, "MSFT": 250.0},
        asset_class="stocks",
        time_in_force="day",
    )

    assert orders == originals
    assert [order["symbol"] for order in enriched] == ["AAPL", "MSFT"]
    assert [order["price"] for order in enriched] == [101.0, 250.0]
    assert [order["time_in_force"] for order in enriched] == ["day", "gtc"]
    assert enriched[0]["client_order_id"] == deterministic_client_order_id(
        "cycle_1",
        "AAPL",
        "buy",
        2.0,
    )


def test_resolve_order_lifecycle_event_timestamp_is_pure_and_stably_ordered() -> None:
    """Order created, validated, and submitted timestamps deterministically around explicit inputs."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    fallback_ts = base_ts + timedelta(minutes=5)
    order = {"created_at": base_ts}

    assert (
        resolve_order_lifecycle_event_timestamp(
            order, status="created", fallback_ts=fallback_ts
        )
        == base_ts
    )
    assert resolve_order_lifecycle_event_timestamp(
        order, status="validated", fallback_ts=fallback_ts
    ) == base_ts + timedelta(microseconds=1)
    assert resolve_order_lifecycle_event_timestamp(
        order, status="submitted", fallback_ts=fallback_ts
    ) == base_ts + timedelta(microseconds=2)
    explicit_ts = base_ts + timedelta(seconds=10)
    assert (
        resolve_order_lifecycle_event_timestamp(
            order,
            status="created",
            fallback_ts=fallback_ts,
            event_ts=explicit_ts,
        )
        == explicit_ts
    )
    assert (
        resolve_order_lifecycle_event_timestamp(
            {}, status="created", fallback_ts=fallback_ts
        )
        == fallback_ts
    )


def test_build_order_lifecycle_event_payload_does_not_mutate_input() -> None:
    """Build canonical rejected-order evidence without mutating the enriched order."""
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    order = {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "rejection_reason": "risk_limit",
    }
    original = dict(order)

    payload = build_order_lifecycle_event_payload(
        order,
        status="rejected",
        broker_order_id=None,
        created_at=created_at,
        order_event_id="order_evt_fixed",
    )

    assert order == original
    assert payload.to_record() == {
        "order_event_id": "order_evt_fixed",
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "order_type": "market",
        "status": "rejected",
        "broker_order_id": None,
        "rejection_reason": "risk_limit",
        "decision_evidence": None,
        "created_at": created_at,
    }


def test_build_broker_fill_event_payload_returns_fill_record_or_none() -> None:
    """Emit canonical fill evidence only when the broker supplies a fill price."""
    fill_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    order = {
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "qty": 2.0,
        "price": 100.0,
    }
    response = {
        "client_order_id": "cid_1",
        "fill_qty": "1.5",
        "fill_price": "100.25",
        "raw_fill_price": 100.0,
        "slippage_amount": 0.375,
        "fee_amount": 0.1,
    }

    payload = build_broker_fill_event_payload(order, response, fill_ts=fill_ts)

    assert payload is not None
    assert payload.to_record() == {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "fill_ts": fill_ts,
        "fill_qty": 1.5,
        "raw_fill_price": 100.0,
        "fill_price": 100.25,
        "slippage_amount": 0.375,
        "fee_amount": 0.1,
    }
    assert (
        build_broker_fill_event_payload(
            order,
            {"client_order_id": "cid_1", "fill_price": None},
            fill_ts=fill_ts,
        )
        is None
    )


def test_build_broker_response_recording_plan_prepares_order_and_fill_records() -> None:
    """Plan matching terminal order and fill records from complete broker evidence."""
    terminal_ts = datetime(2026, 1, 20, 12, 0, 3, tzinfo=timezone.utc)
    order = {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 2.0,
        "order_type": "market",
        "price": 100.0,
    }
    response = {
        "client_order_id": "cid_1",
        "status": "filled",
        "broker_order_id": "broker_1",
        "fill_qty": 2.0,
        "fill_price": 101.0,
        "raw_fill_price": 100.0,
        "slippage_amount": 2.0,
        "fee_amount": 0.25,
    }

    plan = build_broker_response_recording_plan(
        order,
        response,
        terminal_ts=terminal_ts,
        order_event_id="order_evt_fixed",
    )

    assert plan.order_event.to_record() == {
        "order_event_id": "order_evt_fixed",
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 2.0,
        "order_type": "market",
        "status": "filled",
        "broker_order_id": "broker_1",
        "rejection_reason": None,
        "decision_evidence": None,
        "created_at": terminal_ts,
    }
    assert plan.fill_event is not None
    assert plan.fill_event.to_record() == {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "fill_ts": terminal_ts,
        "fill_qty": 2.0,
        "raw_fill_price": 100.0,
        "fill_price": 101.0,
        "slippage_amount": 2.0,
        "fee_amount": 0.25,
    }
    assert plan.missing_fill_evidence is False


def test_build_broker_response_recording_plan_flags_missing_fill_evidence() -> None:
    """Retain a filled status while explicitly flagging absent fill details."""
    terminal_ts = datetime(2026, 1, 20, 12, 0, 3, tzinfo=timezone.utc)

    plan = build_broker_response_recording_plan(
        {
            "client_order_id": "cid_1",
            "run_id": "run_1",
            "cycle_id": "cycle_1",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 2.0,
        },
        {
            "client_order_id": "cid_1",
            "status": "filled",
            "fill_qty": None,
            "fill_price": None,
        },
        terminal_ts=terminal_ts,
        order_event_id="order_evt_missing_fill",
    )

    assert plan.order_event.status == "filled"
    assert plan.fill_event is None
    assert plan.missing_fill_evidence is True


def test_resolve_terminal_event_timestamp_preserves_later_broker_time() -> None:
    """Keep a broker timestamp that already follows the latest local event."""
    latest_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    proposed_ts = latest_ts + timedelta(seconds=1)
    fallback_ts = latest_ts + timedelta(minutes=1)

    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=proposed_ts,
            latest_order_ts=latest_ts,
            fallback_ts=fallback_ts,
        )
        == proposed_ts
    )


def test_resolve_terminal_event_timestamp_nudges_stale_or_equal_time() -> None:
    """Nudge stale broker times forward to preserve strict lifecycle ordering."""
    latest_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    assert resolve_terminal_event_timestamp(
        proposed_ts=latest_ts,
        latest_order_ts=latest_ts,
        fallback_ts=latest_ts + timedelta(minutes=1),
    ) == latest_ts + timedelta(microseconds=1)
    assert resolve_terminal_event_timestamp(
        proposed_ts=latest_ts - timedelta(seconds=1),
        latest_order_ts=latest_ts,
        fallback_ts=latest_ts + timedelta(minutes=1),
    ) == latest_ts + timedelta(microseconds=1)


def test_resolve_terminal_event_timestamp_uses_fallback_and_normalizes_naive_datetimes() -> (
    None
):
    """Use the fallback for absent time and normalize naive proposed timestamps."""
    latest_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    fallback_ts = latest_ts + timedelta(seconds=10)
    naive_proposed_ts = datetime(2026, 1, 20, 12, 0, 20)

    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=None,
            latest_order_ts=latest_ts,
            fallback_ts=fallback_ts,
        )
        == fallback_ts
    )
    assert resolve_terminal_event_timestamp(
        proposed_ts=naive_proposed_ts,
        latest_order_ts=None,
        fallback_ts=fallback_ts,
    ) == naive_proposed_ts.replace(tzinfo=timezone.utc)
