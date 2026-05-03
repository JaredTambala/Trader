from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from trader.notifications import notify_market_data
from trader.trader_service import _parse_market_data_notify


pytestmark = pytest.mark.postgres


def test_notify_market_data_sends_expected_payload_and_parse_round_trips(
    postgres_event_store,
    postgres_listener_connection,
) -> None:
    postgres_listener_connection.execute("LISTEN market_data")
    payload = {
        "symbol": "AAPL",
        "timeframe": "1Min",
        "ts": datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc).isoformat(),
        "asset_class": "stocks",
        "source": "stream",
    }

    sent = notify_market_data(postgres_event_store, payload)
    notifications = list(postgres_listener_connection.notifies(timeout=1.0))

    assert sent is True
    assert len(notifications) == 1
    assert notifications[0].channel == "market_data"

    raw_payload = json.loads(notifications[0].payload)
    assert raw_payload == payload

    parsed = _parse_market_data_notify(notifications[0].payload)
    assert parsed is not None
    assert parsed["symbol"] == "AAPL"
    assert parsed["timeframe"] == "1Min"
    assert parsed["asset_class"] == "stocks"
    assert parsed["ts"] == datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)


def test_notify_market_data_uses_fallback_channel_for_invalid_names(
    postgres_event_store,
    postgres_listener_connection,
) -> None:
    postgres_listener_connection.execute("LISTEN market_data")

    sent = notify_market_data(
        postgres_event_store,
        {
            "symbol": "BTC/USD",
            "timeframe": "1Min",
            "ts": datetime(2026, 1, 21, 12, 1, tzinfo=timezone.utc).isoformat(),
            "asset_class": "crypto",
            "source": "backfill",
        },
        channel="market-data;drop table",
    )
    notifications = list(postgres_listener_connection.notifies(timeout=1.0))

    assert sent is True
    assert len(notifications) == 1
    assert notifications[0].channel == "market_data"
