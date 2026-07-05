"""Tests for AlpacaPaperBroker idempotency and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from trader.broker import AlpacaPaperBroker
from trader.broker.core import (
    build_alpaca_reconciliation_fill_event,
    build_alpaca_reconciliation_order_event,
    ensure_alpaca_client_order_id,
    normalize_alpaca_order_request_fields,
)
from trader.broker.alpaca_domain import normalize_alpaca_order_response
from trader.identifiers import deterministic_client_order_id
from tests.support.duckdb_store import DuckDBEventStore


@dataclass
class FakeOrder:
    id: str
    status: str
    client_order_id: str
    symbol: str = "AAPL"
    asset_class: str = "us_equity"
    qty: float = 1.0
    order_type: str = "market"
    side: str = "buy"
    submitted_at: datetime | None = None
    filled_qty: float | None = None
    filled_avg_price: float | None = None
    filled_at: datetime | None = None
    updated_at: datetime | None = None


class FakeTradingClient:
    def __init__(self) -> None:
        self.submitted: list[FakeOrder] = []
        self.listed: list[FakeOrder] = []
        self.list_calls = 0
        self.canceled: list[str] = []

    def submit_order(self, order_data: object) -> FakeOrder:
        client_order_id = getattr(order_data, "client_order_id", None)
        if client_order_id is None and isinstance(order_data, dict):
            client_order_id = order_data.get("client_order_id")
        symbol = getattr(order_data, "symbol", None)
        if symbol is None and isinstance(order_data, dict):
            symbol = order_data.get("symbol")
        qty = getattr(order_data, "qty", None)
        if qty is None and isinstance(order_data, dict):
            qty = order_data.get("qty")
        side = getattr(order_data, "side", None)
        if hasattr(side, "value"):
            side = side.value
        if side is None and isinstance(order_data, dict):
            side = order_data.get("side")
        order_type = getattr(order_data, "order_type", None) or getattr(order_data, "type", None)
        if hasattr(order_type, "value"):
            order_type = order_type.value
        if order_type is None and isinstance(order_data, dict):
            order_type = order_data.get("type")
        order = FakeOrder(
            id=f"alpaca_{len(self.submitted) + 1}",
            status="accepted",
            client_order_id=str(client_order_id),
            symbol=str(symbol or "AAPL"),
            qty=float(qty or 0.0),
            side=str(side or "buy"),
            order_type=str(order_type or "market"),
            submitted_at=datetime.now(timezone.utc),
        )
        self.submitted.append(order)
        return order

    def get_orders(self, **_kwargs: object) -> list[FakeOrder]:
        self.list_calls += 1
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

    def cancel_order_by_id(self, order_id: str) -> None:
        self.canceled.append(order_id)


def test_build_alpaca_reconciliation_order_event_is_deterministic_without_mutation() -> None:
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    local_event = {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "order_type": "market",
        "broker_order_id": "alpaca_1",
    }
    original = dict(local_event)

    payload = build_alpaca_reconciliation_order_event(
        local_event,
        status="canceled",
        order_event_id="order_evt_fixed",
        created_at=created_at,
        broker_order_id="alpaca_1",
        rejection_reason="reconciled_missing",
    )

    assert local_event == original
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
        "status": "canceled",
        "broker_order_id": "alpaca_1",
        "rejection_reason": "reconciled_missing",
        "created_at": created_at,
    }


def test_build_alpaca_reconciliation_fill_event_requires_fill_evidence() -> None:
    fill_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    local_event = {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
    }
    broker_order = {"fill_qty": "2.5", "fill_price": "101.25"}
    original_event = dict(local_event)
    original_broker_order = dict(broker_order)

    payload = build_alpaca_reconciliation_fill_event(local_event, broker_order, fill_ts=fill_ts)

    assert local_event == original_event
    assert broker_order == original_broker_order
    assert payload is not None
    assert payload.to_record() == {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "fill_ts": fill_ts,
        "fill_qty": 2.5,
        "raw_fill_price": 101.25,
        "fill_price": 101.25,
        "slippage_amount": None,
        "fee_amount": None,
    }
    assert build_alpaca_reconciliation_fill_event(local_event, {"fill_qty": 1.0}, fill_ts=fill_ts) is None
    assert build_alpaca_reconciliation_fill_event(local_event, {"fill_price": 100.0}, fill_ts=fill_ts) is None


def test_normalize_alpaca_order_request_fields_converts_crypto_order_for_trading_api() -> None:
    order = {
        "symbol": "btc/usd",
        "side": " BUY ",
        "qty": "0.25",
        "time_in_force": "day",
        "asset_class": "crypto",
        "order_type": "limit",
        "client_order_id": "cid_crypto",
        "price": "65000.5",
    }
    original = dict(order)

    fields = normalize_alpaca_order_request_fields(order)

    assert order == original
    assert fields.symbol == "BTCUSD"
    assert fields.side == "buy"
    assert fields.qty == 0.25
    assert fields.time_in_force == "gtc"
    assert fields.order_type == "limit"
    assert fields.client_order_id == "cid_crypto"
    assert fields.limit_price == "65000.5"
    assert fields.to_fallback_mapping() == {
        "symbol": "BTCUSD",
        "qty": 0.25,
        "side": "buy",
        "time_in_force": "gtc",
        "type": "limit",
        "client_order_id": "cid_crypto",
        "limit_price": "65000.5",
    }


def test_normalize_alpaca_order_request_fields_preserves_stock_day_order() -> None:
    fields = normalize_alpaca_order_request_fields(
        {
            "symbol": " aapl ",
            "side": "sell",
            "qty": 2,
            "time_in_force": "day",
            "asset_class": "stocks",
            "client_order_id": "cid_stock",
        }
    )

    assert fields.symbol == "AAPL"
    assert fields.qty == 2.0
    assert fields.side == "sell"
    assert fields.time_in_force == "day"
    assert fields.order_type == "market"
    assert fields.limit_price is None


def test_ensure_alpaca_client_order_id_preserves_explicit_id_without_mutation() -> None:
    order = {
        "client_order_id": "cid_explicit",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
    }
    original = dict(order)

    enriched = ensure_alpaca_client_order_id(order)

    assert enriched is order
    assert order == original


def test_ensure_alpaca_client_order_id_derives_stable_id_without_mutation() -> None:
    order = {
        "cycle_id": "cycle_1",
        "symbol": " aapl ",
        "side": " BUY ",
        "qty": "1.0",
    }
    original = dict(order)

    enriched = ensure_alpaca_client_order_id(order)

    assert order == original
    assert enriched is not order
    assert enriched["client_order_id"] == deterministic_client_order_id("cycle_1", "AAPL", "buy", 1.0)
    assert enriched["symbol"] == " aapl "


def test_normalize_alpaca_order_response_maps_provider_payload_without_mutation() -> None:
    response = {
        "id": "alpaca_1",
        "status": "filled",
        "symbol": "BTCUSD",
        "asset_class": "crypto",
        "side": "BUY",
        "type": "market",
        "qty": "0.25",
        "filled_qty": "0.25",
        "filled_avg_price": "65000.50",
        "filled_at": "2026-01-20T12:00:00Z",
        "client_order_id": "cid_crypto",
    }
    original = dict(response)

    normalized = normalize_alpaca_order_response(response, {})

    assert response == original
    assert normalized["client_order_id"] == "cid_crypto"
    assert normalized["status"] == "filled"
    assert normalized["broker_order_id"] == "alpaca_1"
    assert normalized["symbol"] == "BTC/USD"
    assert normalized["asset_class"] == "crypto"
    assert normalized["side"] == "buy"
    assert normalized["qty"] == 0.25
    assert normalized["fill_price"] == 65000.50
    assert normalized["fill_ts"] == datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)


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


def test_alpaca_broker_reconcile_missing_closes_open_order(tmp_path) -> None:
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
            "order_event_id": "order_evt_open",
            "client_order_id": "cid_3",
            "run_id": "run_3",
            "cycle_id": "cycle_3",
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

    updates = broker.reconcile_orders(since_ts=base_ts - timedelta(minutes=1))

    assert updates
    latest = store.connection().execute(
        """
        SELECT status, rejection_reason
        FROM order_events
        WHERE client_order_id = 'cid_3'
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    assert latest == ("canceled", "reconciled_missing")


def test_alpaca_submit_does_not_list_orders_without_broker_order_id(tmp_path) -> None:
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
            "order_event_id": "order_evt_existing_local_only",
            "client_order_id": "cid_4",
            "run_id": "run_4",
            "cycle_id": "cycle_4",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 1.0,
            "order_type": "market",
            "status": "submitted",
            "broker_order_id": None,
            "rejection_reason": None,
            "created_at": datetime.now(timezone.utc),
        },
    )

    responses = broker.submit_orders(
        [
            {
                "client_order_id": "cid_4",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "cycle_id": "cycle_4",
            }
        ]
    )

    assert client.list_calls == 0
    assert client.submitted != []
    assert responses and responses[0]["status"] in {"submitted", "accepted"}


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
