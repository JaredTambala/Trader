"""Pure tests for runtime order-recovery value helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from trader.runtime.order_recovery import (
    build_latest_order_events_query,
    latest_order_events_from_rows,
    parse_timestamp,
    partition_broker_orders,
    partition_local_orders,
    plan_broker_open_adoption,
    plan_local_clean_start_close,
    plan_local_open_order_recovery,
)


def test_partition_broker_orders_normalizes_asset_class_and_crypto_symbols() -> None:
    in_scope, out_of_scope = partition_broker_orders(
        [
            {"client_order_id": "btc", "symbol": "BTCUSD", "asset_class": "crypto"},
            {"client_order_id": "eth", "symbol": "ETHUSD", "asset_class": "crypto"},
            {"client_order_id": "stock", "symbol": "AAPL", "asset_class": "us_equity"},
        ],
        configured_symbols=("BTC/USD",),
        configured_asset_class="crypto",
    )

    assert [order["client_order_id"] for order in in_scope] == ["btc"]
    assert in_scope[0]["symbol"] == "BTC/USD"
    assert in_scope[0]["asset_class"] == "crypto"
    assert [order["client_order_id"] for order in out_of_scope] == ["eth", "stock"]
    assert out_of_scope[1]["asset_class"] == "stocks"


def test_partition_local_orders_uses_configured_asset_class_for_symbol_normalization() -> None:
    in_scope, out_of_scope = partition_local_orders(
        [
            {"client_order_id": "btc", "symbol": "BTCUSD"},
            {"client_order_id": "eth", "symbol": "ETHUSD"},
        ],
        configured_symbols=("BTC/USD",),
        configured_asset_class="crypto",
    )

    assert [order["client_order_id"] for order in in_scope] == ["btc"]
    assert in_scope[0]["symbol"] == "BTC/USD"
    assert [order["client_order_id"] for order in out_of_scope] == ["eth"]


def test_latest_order_events_from_rows_keeps_newest_row_per_client_order() -> None:
    latest = latest_order_events_from_rows(
        [
            ("cid_1", "run", "session", "cycle", "AAPL", "buy", 1, "market", "filled", "broker", None, "new"),
            ("cid_2", "run", "session", "cycle", "MSFT", "sell", 2, "market", "submitted", "broker", None, "only"),
            ("cid_1", "run", "session", "cycle", "AAPL", "buy", 1, "market", "submitted", "broker", None, "old"),
            (None, "run", "session", "cycle", "TSLA", "buy", 1, "market", "submitted", "broker", None, "missing"),
        ]
    )

    assert [event["client_order_id"] for event in latest] == ["cid_1", "cid_2"]
    assert latest[0]["status"] == "filled"
    assert latest[1]["created_at"] == "only"


def test_build_latest_order_events_query_names_expected_projection() -> None:
    query = build_latest_order_events_query()

    assert "SELECT client_order_id, run_id, session_id, cycle_id" in query.sql
    assert "rejection_reason, created_at" in query.sql
    assert "FROM order_events" in query.sql
    assert "ORDER BY created_at DESC, order_event_id DESC" in query.sql
    assert query.params == ()


def test_parse_timestamp_accepts_z_suffix_and_naive_values() -> None:
    assert parse_timestamp("2026-01-01T12:00:00Z") == datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert parse_timestamp(datetime(2026, 1, 1, 12)) == datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert parse_timestamp("") is None
    assert parse_timestamp("not-a-date") is None


def test_plan_local_open_order_recovery_closes_missing_broker_order() -> None:
    fallback_ts = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    local_event = {
        "client_order_id": "cid_missing",
        "status": "submitted",
        "broker_order_id": "broker_missing",
    }

    plan = plan_local_open_order_recovery(local_event, None, fallback_ts=fallback_ts)

    assert plan is not None
    assert plan.action == "close_missing_local_open"
    assert plan.order is local_event
    assert plan.status == "canceled"
    assert plan.rejection_reason == "reconciled_missing"
    assert plan.event_ts == fallback_ts
    assert plan.should_record_fill is False


def test_plan_local_open_order_recovery_updates_changed_broker_order() -> None:
    fallback_ts = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    fill_ts = datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc)
    local_event = {
        "client_order_id": "cid_filled",
        "status": "submitted",
        "broker_order_id": "broker_1",
        "symbol": "AAPL",
    }
    broker_order = {
        "client_order_id": "cid_filled",
        "status": "filled",
        "broker_order_id": "broker_1",
        "fill_qty": "1",
        "fill_price": "101.0",
        "fill_ts": fill_ts.isoformat(),
    }

    plan = plan_local_open_order_recovery(local_event, broker_order, fallback_ts=fallback_ts)

    assert plan is not None
    assert plan.action == "update_local_from_broker"
    assert plan.order == {**local_event, **broker_order}
    assert plan.status == "filled"
    assert plan.rejection_reason is None
    assert plan.event_ts == fill_ts
    assert plan.should_record_fill is True


def test_plan_local_open_order_recovery_ignores_matching_broker_order() -> None:
    fallback_ts = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    local_event = {
        "client_order_id": "cid_open",
        "status": "accepted",
        "broker_order_id": "broker_1",
    }
    broker_order = {
        "client_order_id": "cid_open",
        "status": "accepted",
        "broker_order_id": "broker_1",
    }

    assert plan_local_open_order_recovery(local_event, broker_order, fallback_ts=fallback_ts) is None


def test_plan_broker_open_adoption_prepares_missing_local_order() -> None:
    fallback_ts = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    created_at = datetime(2026, 1, 1, 11, 59, tzinfo=timezone.utc)
    broker_order = {
        "client_order_id": "cid_broker",
        "status": "accepted",
        "broker_order_id": "broker_1",
        "created_at": created_at.isoformat(),
    }

    plan = plan_broker_open_adoption(
        broker_order,
        known_local_client_order_ids={"cid_other"},
        run_id="run_recovery",
        fallback_ts=fallback_ts,
    )

    assert plan is not None
    assert plan.action == "adopt_broker_open"
    assert plan.order == {
        **broker_order,
        "run_id": "run_recovery",
        "session_id": "run_recovery",
        "cycle_id": None,
    }
    assert plan.status == "accepted"
    assert plan.rejection_reason == "adopted_from_broker"
    assert plan.event_ts == created_at
    assert plan.should_record_fill is False


def test_plan_broker_open_adoption_skips_known_or_unidentified_orders() -> None:
    fallback_ts = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    assert (
        plan_broker_open_adoption(
            {"client_order_id": "cid_known", "status": "accepted"},
            known_local_client_order_ids={"cid_known"},
            run_id="run_recovery",
            fallback_ts=fallback_ts,
        )
        is None
    )
    assert (
        plan_broker_open_adoption(
            {"status": "accepted"},
            known_local_client_order_ids=set(),
            run_id="run_recovery",
            fallback_ts=fallback_ts,
        )
        is None
    )


def test_plan_local_clean_start_close_prepares_local_cancellation() -> None:
    event_ts = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    local_event = {
        "client_order_id": "cid_clean",
        "run_id": "run_old",
        "session_id": "session_old",
        "cycle_id": "cycle_old",
        "status": "accepted",
    }

    plan = plan_local_clean_start_close(local_event, run_id="run_clean", event_ts=event_ts)

    assert plan.action == "local_clean_start_close"
    assert plan.order == {
        **local_event,
        "run_id": "run_clean",
        "session_id": "run_clean",
        "cycle_id": None,
    }
    assert plan.status == "canceled"
    assert plan.rejection_reason == "local_clean_start"
    assert plan.event_ts == event_ts
    assert plan.should_record_fill is False
