"""Tests for AlpacaPaperBroker idempotency and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from trader.broker import AlpacaPaperBroker
from tests.support.duckdb_store import DuckDBEventStore


@dataclass
class FakeOrder:
    id: str
    status: str
    client_order_id: str
    filled_qty: float | None = None
    filled_avg_price: float | None = None
    filled_at: datetime | None = None
    updated_at: datetime | None = None


class FakeTradingClient:
    def __init__(self) -> None:
        self.submitted: list[FakeOrder] = []
        self.listed: list[FakeOrder] = []

    def submit_order(self, order_data: object) -> FakeOrder:
        client_order_id = getattr(order_data, "client_order_id", None)
        if client_order_id is None and isinstance(order_data, dict):
            client_order_id = order_data.get("client_order_id")
        order = FakeOrder(
            id=f"alpaca_{len(self.submitted) + 1}",
            status="accepted",
            client_order_id=str(client_order_id),
        )
        self.submitted.append(order)
        return order

    def get_orders(self, **_kwargs: object) -> list[FakeOrder]:
        return list(self.listed)

    def get_order_by_id(self, order_id: str) -> FakeOrder:
        for order in self.submitted + self.listed:
            if order.id == order_id:
                return order
        raise KeyError(order_id)

    def get_all_positions(self) -> list[object]:
        return []

    def get_account(self) -> object:
        return type("Account", (), {"cash": "0", "buying_power": "0", "equity": "0"})()


def test_alpaca_broker_idempotent_submission(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    client = FakeTradingClient()
    broker = AlpacaPaperBroker(
        api_key="key",
        secret_key="secret",
        event_store=store,
        client=client,
    )
    store.record_event(
        "order_events",
        {
            "order_event_id": "order_evt_existing",
            "client_order_id": "cid_1",
            "run_id": "run_1",
            "cycle_id": "cycle_1",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 1.0,
            "order_type": "market",
            "status": "submitted",
            "broker_order_id": "alpaca_existing",
            "rejection_reason": None,
            "created_at": datetime.now(timezone.utc),
        },
    )

    responses = broker.submit_orders(
        [
            {
                "client_order_id": "cid_1",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "cycle_id": "cycle_1",
            }
        ]
    )

    # If we cannot reconcile the broker-side order, submit a new order rather than skipping.
    assert client.submitted != []
    assert responses and responses[0]["status"] in {"submitted", "accepted"}


def test_alpaca_broker_reconcile_updates_events(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    client = FakeTradingClient()
    broker = AlpacaPaperBroker(
        api_key="key",
        secret_key="secret",
        event_store=store,
        client=client,
    )
    base_ts = datetime(2026, 1, 20, tzinfo=timezone.utc)
    store.record_event(
        "order_events",
        {
            "order_event_id": "order_evt_error",
            "client_order_id": "cid_2",
            "run_id": "run_2",
            "cycle_id": "cycle_2",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 2.0,
            "order_type": "market",
            "status": "error",
            "broker_order_id": None,
            "rejection_reason": "timeout",
            "created_at": base_ts,
        },
    )

    client.listed.append(
        FakeOrder(
            id="alpaca_2",
            status="filled",
            client_order_id="cid_2",
            filled_qty=2.0,
            filled_avg_price=101.0,
            filled_at=base_ts + timedelta(seconds=30),
        )
    )

    updates = broker.reconcile_orders(since_ts=base_ts - timedelta(minutes=1))
    assert updates
    statuses = {
        row[0] for row in store.connection().execute(
            "SELECT status FROM order_events WHERE client_order_id = 'cid_2'"
        ).fetchall()
    }
    assert "filled" in statuses
    fill_count = store.connection().execute(
        "SELECT COUNT(*) FROM fill_events WHERE client_order_id = 'cid_2'"
    ).fetchone()[0]
    assert fill_count == 1


def test_alpaca_status_mapping() -> None:
    broker = AlpacaPaperBroker(
        api_key="key",
        secret_key="secret",
        client=FakeTradingClient(),
    )
    assert broker._map_status("accepted") == "accepted"
    assert broker._map_status("partially_filled") == "partially_filled"
    assert broker._map_status("filled") == "filled"
    assert broker._map_status("rejected") == "rejected"
    assert broker._map_status("pending_cancel") == "canceled"
