"""Tests for market data backfill helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from alpaca.data.timeframe import TimeFrameUnit

from trader.market_data.backfill import (
    _build_bar_event,
    _parse_timeframe,
    _resolve_since,
    _subtract_months,
)
from trader.market_data import CryptoBarEvent, StockBarEvent
from tests.support.duckdb_store import DuckDBEventStore, merge_events


class FakeBar:
    def __init__(self, ts: datetime) -> None:
        self.t = ts
        self.o = 1.0
        self.h = 2.0
        self.l = 0.5
        self.c = 1.5
        self.v = 10.0
        self.n = 5.0
        self.vw = 1.6


def test_parse_timeframe_minutes() -> None:
    """Parse minute timeframe strings."""
    tf = _parse_timeframe("5Min")
    assert tf.amount == 5
    assert tf.unit == TimeFrameUnit.Minute


def test_parse_timeframe_hours() -> None:
    """Parse hour timeframe strings."""
    tf = _parse_timeframe("2Hour")
    assert tf.amount == 2
    assert tf.unit == TimeFrameUnit.Hour


def test_parse_timeframe_ticker_shorthands() -> None:
    """Parse shorthand timeframe strings."""
    tf_min = _parse_timeframe("15T")
    assert tf_min.amount == 15
    assert tf_min.unit == TimeFrameUnit.Minute
    tf_day = _parse_timeframe("1D")
    assert tf_day.amount == 1
    assert tf_day.unit == TimeFrameUnit.Day
    tf_week = _parse_timeframe("1W")
    assert tf_week.amount == 1
    assert tf_week.unit == TimeFrameUnit.Week
    tf_month = _parse_timeframe("3M")
    assert tf_month.amount == 3
    assert tf_month.unit == TimeFrameUnit.Month


def test_parse_timeframe_invalid() -> None:
    """Reject invalid timeframe strings."""
    with pytest.raises(ValueError):
        _parse_timeframe("nonsense")
    with pytest.raises(ValueError):
        _parse_timeframe("60Min")
    with pytest.raises(ValueError):
        _parse_timeframe("24Hour")
    with pytest.raises(ValueError):
        _parse_timeframe("2Day")
    with pytest.raises(ValueError):
        _parse_timeframe("2W")
    with pytest.raises(ValueError):
        _parse_timeframe("5M")


def test_build_bar_event_for_stocks() -> None:
    """Ensure backfill bars map to StockBarEvent."""
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)
    bar = FakeBar(now)
    event = _build_bar_event("stocks", "AAPL", bar, now, source="alpaca", timeframe="1Min")
    assert isinstance(event, StockBarEvent)
    assert event.symbol == "AAPL"


def test_build_bar_event_for_crypto() -> None:
    """Ensure backfill bars map to CryptoBarEvent."""
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)
    bar = FakeBar(now)
    event = _build_bar_event("crypto", "BTC/USD", bar, now, source="alpaca", timeframe="1Min")
    assert isinstance(event, CryptoBarEvent)
    assert event.symbol == "BTC/USD"


def test_subtract_months_clamps_day() -> None:
    """Ensure month subtraction clamps to the target month length."""
    ts = datetime(2024, 3, 31, 12, 0, tzinfo=timezone.utc)
    adjusted = _subtract_months(ts, 1)
    assert adjusted.year == 2024
    assert adjusted.month == 2
    assert adjusted.day == 29


def test_resolve_since_months() -> None:
    """Resolve a months-based window."""
    now = datetime(2024, 3, 31, 12, 0, tzinfo=timezone.utc)
    start, end = _resolve_since("1mo", now)
    assert end == now
    assert start.month == 2
    assert start.day == 29


def test_resolve_since_days() -> None:
    """Resolve a days-based window."""
    now = datetime(2024, 3, 1, 0, 0, tzinfo=timezone.utc)
    start, end = _resolve_since("10d", now)
    assert end == now
    assert start == now - timedelta(days=10)


def test_merge_events_dedupes(tmp_path) -> None:
    """Ensure merge ignores duplicate rows."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime(2026, 1, 20, tzinfo=timezone.utc)
    event = StockBarEvent(
        symbol="AAPL",
        timeframe="1Min",
        ts=now,
        ingested_at=now,
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=10.0,
        trade_count=None,
        vwap=None,
        source="test",
    )
    connection = store.connection()._connection
    merge_events(connection, "stock_bar_events", [event.to_payload()])
    merge_events(connection, "stock_bar_events", [event.to_payload()])
    count = connection.execute("SELECT COUNT(*) FROM stock_bar_events").fetchone()[0]
    assert count == 1
