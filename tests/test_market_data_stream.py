"""Tests for websocket market data stream helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from trader.market_data.stream import StreamContext, _build_bar_event
from trader.market_data import CryptoBarEvent, StockBarEvent


class FakeBar:
    def __init__(
        self,
        symbol: str,
        ts: datetime,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> None:
        self.symbol = symbol
        self.timestamp = ts
        self.open = open_price
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


def test_build_bar_event_for_stocks() -> None:
    """Ensure stock bars map to StockBarEvent."""
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)
    bar = FakeBar("AAPL", now, 100.0, 101.0, 99.5, 100.5, 10.0)
    context = StreamContext(
        event_store=None,
        asset_class="stocks",
        source="alpaca",
        timeframe="1Min",
    )
    event = _build_bar_event(context, bar)
    assert isinstance(event, StockBarEvent)
    assert event.symbol == "AAPL"
    assert event.close == 100.5
    assert event.timeframe == "1Min"


def test_build_bar_event_for_crypto() -> None:
    """Ensure crypto bars map to CryptoBarEvent."""
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)
    bar = FakeBar("BTC/USD", now, 1.0, 2.0, 0.5, 1.5, 0.1)
    context = StreamContext(
        event_store=None,
        asset_class="crypto",
        source="alpaca",
        timeframe="1Min",
    )
    event = _build_bar_event(context, bar)
    assert isinstance(event, CryptoBarEvent)
    assert event.symbol == "BTC/USD"
    assert event.close == 1.5
