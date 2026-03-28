"""Tests for startup order recovery and local cleanup flows."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.broker import AlpacaPaperBroker
from trader.order_recovery import inspect_recovery_state, run_local_clean_start, run_startup_recovery
from tests.support.duckdb_store import DuckDBEventStore
from tests.test_alpaca_broker import FakeOrder, FakeTradingClient


def _broker(store, client):
    return AlpacaPaperBroker(api_key="key", secret_key="secret", event_store=store, client=client)


def test_startup_recovery_closes_missing_local_open(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    client = FakeTradingClient()
    broker = _broker(store, client)
    base_ts = datetime(2026, 1, 20, tzinfo=timezone.utc)
    store.record_event(
        "order_events",
        {
            "order_event_id": "evt_open",
            "client_order_id": "cid_local_missing",
            "run_id": "run_1",
            "session_id": "run_1",
            "cycle_id": "cycle_1",
            "symbol": "BTC/USD",
            "side": "buy",
            "qty": 1.0,
            "order_type": "market",
            "status": "submitted",
            "broker_order_id": None,
            "rejection_reason": None,
            "created_at": base_ts,
        },
    )

    report = run_startup_recovery(
        event_store=store,
        broker=broker,
        configured_symbols=("BTC/USD",),
        configured_asset_class="crypto",
        mode="resume",
        run_id="run_recovery",
    )

    assert report.local_closed_missing == 1
    latest = store.connection().execute(
        """
        SELECT status, rejection_reason
        FROM order_events
        WHERE client_order_id = 'cid_local_missing'
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    assert latest == ("canceled", "reconciled_missing")


def test_startup_recovery_adopts_broker_open_order_in_scope(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    client = FakeTradingClient()
    client.listed.append(
        FakeOrder(
            id="alpaca_open_1",
            status="accepted",
            client_order_id="cid_broker_open",
            symbol="BTC/USD",
            asset_class="crypto",
            qty=0.01,
            side="buy",
            order_type="market",
            submitted_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        )
    )
    broker = _broker(store, client)

    report = run_startup_recovery(
        event_store=store,
        broker=broker,
        configured_symbols=("BTC/USD",),
        configured_asset_class="crypto",
        mode="resume",
        run_id="run_recovery",
    )

    assert report.adopted_broker_open == 1
    latest = store.connection().execute(
        """
        SELECT status, rejection_reason, broker_order_id
        FROM order_events
        WHERE client_order_id = 'cid_broker_open'
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    assert latest == ("accepted", "adopted_from_broker", "alpaca_open_1")


def test_startup_recovery_fail_closed_on_broker_open_in_scope(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    client = FakeTradingClient()
    client.listed.append(
        FakeOrder(
            id="alpaca_open_2",
            status="accepted",
            client_order_id="cid_fail",
            symbol="BTC/USD",
            asset_class="crypto",
            qty=0.01,
            side="buy",
            order_type="market",
            submitted_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        )
    )
    broker = _broker(store, client)

    with pytest.raises(ValueError, match="Broker open orders exist in configured universe"):
        run_startup_recovery(
            event_store=store,
            broker=broker,
            configured_symbols=("BTC/USD",),
            configured_asset_class="crypto",
            mode="fail_closed",
            run_id="run_recovery",
        )


def test_clean_start_closes_local_open_orders_without_touching_broker(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    client = FakeTradingClient()
    base_ts = datetime(2026, 1, 20, tzinfo=timezone.utc)
    store.record_event(
        "order_events",
        {
            "order_event_id": "evt_local_clean",
            "client_order_id": "cid_clean",
            "run_id": "run_1",
            "session_id": "run_1",
            "cycle_id": "cycle_1",
            "symbol": "BTC/USD",
            "side": "buy",
            "qty": 0.01,
            "order_type": "market",
            "status": "accepted",
            "broker_order_id": "alpaca_open_3",
            "rejection_reason": None,
            "created_at": base_ts,
        },
    )

    report = run_local_clean_start(
        event_store=store,
        configured_symbols=("BTC/USD",),
        configured_asset_class="crypto",
        run_id=None,
    )

    assert report.local_clean_start_closed == 1
    assert client.canceled == []
    latest = store.connection().execute(
        """
        SELECT status, rejection_reason, broker_order_id
        FROM order_events
        WHERE client_order_id = 'cid_clean'
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    assert latest == ("canceled", "local_clean_start", "alpaca_open_3")


def test_report_identifies_out_of_scope_broker_orders(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    client = FakeTradingClient()
    client.listed.append(
        FakeOrder(
            id="alpaca_open_4",
            status="accepted",
            client_order_id="cid_other",
            symbol="AAPL",
            asset_class="us_equity",
            qty=1.0,
            side="buy",
            order_type="market",
            submitted_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        )
    )
    broker = _broker(store, client)

    report = inspect_recovery_state(
        event_store=store,
        broker=broker,
        configured_symbols=("BTC/USD",),
        configured_asset_class="crypto",
    )

    assert report.broker_open_in_scope == 0
    assert report.broker_open_out_of_scope == 1
