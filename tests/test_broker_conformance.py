"""Broker contract and capability conformance tests."""

from __future__ import annotations

from datetime import datetime, timezone

from trader.broker import (
    AccountBroker,
    AlpacaPaperBroker,
    InternalPaperBroker,
    OrderCancelBroker,
    OrderLookupBroker,
    OrderReconcileBroker,
)
from tests.test_alpaca_broker import FakeOrder, FakeTradingClient


def test_internal_broker_response_shape_includes_canonical_fields() -> None:
    broker = InternalPaperBroker(slippage_bps=10.0, fee_bps=5.0, fee_minimum=1.0, sleep_on_fill_delay=False)

    responses = broker.submit_orders(
        [
            {
                "client_order_id": "cid_1",
                "run_id": "run_1",
                "cycle_id": "cycle_1",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 2.0,
                "price": 100.0,
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ]
    )

    response = responses[0]
    assert {
        "client_order_id",
        "status",
        "broker_order_id",
        "symbol",
        "qty",
        "order_type",
        "fill_qty",
        "raw_fill_price",
        "fill_price",
        "fill_ts",
        "slippage_amount",
        "fee_amount",
    }.issubset(response)
    assert response["status"] == "filled"
    assert response["fill_price"] == 100.1
    assert response["fee_amount"] == 1.0


def test_alpaca_broker_exposes_optional_capabilities() -> None:
    broker = AlpacaPaperBroker(
        api_key="key",
        secret_key="secret",
        client=FakeTradingClient(),
    )

    assert isinstance(broker, AccountBroker)
    assert isinstance(broker, OrderLookupBroker)
    assert isinstance(broker, OrderCancelBroker)
    assert isinstance(broker, OrderReconcileBroker)


def test_alpaca_fake_client_conformance_for_accepted_lookup_cancel_and_partial_fill() -> None:
    client = FakeTradingClient()
    broker = AlpacaPaperBroker(
        api_key="key",
        secret_key="secret",
        client=client,
    )

    accepted = broker.submit_orders(
        [
            {
                "client_order_id": "cid_accepted",
                "cycle_id": "cycle_1",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "asset_class": "stocks",
            }
        ]
    )[0]
    assert accepted["status"] == "accepted"
    assert accepted["client_order_id"] == "cid_accepted"

    client.listed.append(
        FakeOrder(
            id="alpaca_partial",
            status="partially_filled",
            client_order_id="cid_partial",
            filled_qty=0.5,
            filled_avg_price=101.0,
        )
    )
    listed = broker.list_orders()
    assert listed[0]["status"] == "partially_filled"
    assert listed[0]["fill_qty"] == 0.5
    assert broker.get_order_by_id("alpaca_partial")["client_order_id"] == "cid_partial"

    broker.cancel_order("alpaca_partial")
    assert client.canceled == ["alpaca_partial"]


def test_alpaca_submit_error_is_normalized() -> None:
    class FailingClient(FakeTradingClient):
        def submit_order(self, order_data: object) -> FakeOrder:
            raise RuntimeError("broker unavailable")

    broker = AlpacaPaperBroker(
        api_key="key",
        secret_key="secret",
        client=FailingClient(),
        max_retries=1,
    )

    response = broker.submit_orders(
        [
            {
                "client_order_id": "cid_error",
                "cycle_id": "cycle_1",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "asset_class": "stocks",
            }
        ]
    )[0]

    assert response["status"] == "error"
    assert response["client_order_id"] == "cid_error"
    assert "broker unavailable" in str(response["rejection_reason"])
