"""Pure tests for runtime order-recovery value helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from trader.runtime.order_recovery import (
    latest_order_events_from_rows,
    parse_timestamp,
    partition_broker_orders,
    partition_local_orders,
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


def test_parse_timestamp_accepts_z_suffix_and_naive_values() -> None:
    assert parse_timestamp("2026-01-01T12:00:00Z") == datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert parse_timestamp(datetime(2026, 1, 1, 12)) == datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert parse_timestamp("") is None
    assert parse_timestamp("not-a-date") is None
