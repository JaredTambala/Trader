"""Cycle market-data admission and event-store projection contracts.

Subject: Market-data freshness, ingestion planning, event-table queries, and row normalization.
Level: Deterministic unit contracts.
Collaborators: Real cycle market-data helpers and package-owned value factories; no database or provider.
Guarantees: Missing, stale, bounded, and asset-specific data produce explicit repeatable pipeline decisions.
Non-goals: Stream queue coordination, strategy execution, metrics, or event persistence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.trader.cycle.factories import stock_event as _stock_event
from trader.cycle import (
    assess_market_data_event_freshness,
    assess_market_data_readiness,
)
from trader.cycle.lifecycle import (
    _resolve_market_data_freshness_ts,
    _should_use_stream_ingestion,
)
from trader.cycle.market_data import (
    _build_recent_market_data_query,
    _empty_market_data_pipeline_result,
    _market_data_event_table_name,
    _row_to_market_event,
)
from trader.market_data import CryptoBarEvent, StockBarEvent


def test_assess_market_data_readiness_blocks_missing_market_data() -> None:
    """Skip cycle execution with an explicit reason when no market event exists."""
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    readiness = assess_market_data_readiness([], now=now, max_age_seconds=60)

    assert readiness.should_skip is True
    assert readiness.latest_ts is None
    assert readiness.age_seconds is None
    assert readiness.is_stale is False
    assert readiness.reason == "missing_market_data"


def test_assess_market_data_readiness_reports_fresh_latest_event() -> None:
    """Admit the newest event when its age remains within policy."""
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    older = _stock_event(ts=now - timedelta(seconds=30), close=99.0)
    latest = _stock_event(ts=now - timedelta(seconds=10), close=101.0)

    readiness = assess_market_data_readiness(
        [older, latest], now=now, max_age_seconds=60
    )

    assert readiness.should_skip is False
    assert readiness.latest_ts == latest.ts
    assert readiness.age_seconds == 10.0
    assert readiness.is_stale is False
    assert readiness.reason is None


def test_assess_market_data_readiness_reports_stale_latest_event_and_normalizes_now() -> (
    None
):
    """Normalize a naive clock and explain rejection of stale latest data."""
    now = datetime(2026, 1, 20, 12, 0)
    latest = _stock_event(ts=datetime(2026, 1, 20, 11, 58, tzinfo=timezone.utc))

    readiness = assess_market_data_readiness([latest], now=now, max_age_seconds=60)

    assert readiness.should_skip is True
    assert readiness.latest_ts == latest.ts
    assert readiness.age_seconds == 120.0
    assert readiness.is_stale is True
    assert readiness.reason == "stale_market_data"


def test_assess_market_data_readiness_rejects_negative_staleness_window() -> None:
    """Reject an invalid negative market-data age policy before comparison."""
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="max_age_seconds must be non-negative"):
        assess_market_data_readiness(
            [_stock_event(ts=now)], now=now, max_age_seconds=-1
        )


def test_assess_market_data_event_freshness_reports_fresh_event() -> None:
    """Expose timestamp, age, and policy for an individually fresh event."""
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    event = _stock_event(ts=now - timedelta(seconds=5))

    freshness = assess_market_data_event_freshness(event, now=now, max_age_seconds=60)

    assert freshness.ts == event.ts
    assert freshness.age_seconds == 5.0
    assert freshness.max_age_seconds == 60
    assert freshness.is_stale is False


def test_assess_market_data_event_freshness_reports_stale_event_and_normalizes_now() -> (
    None
):
    """Normalize a naive clock before classifying an individual event as stale."""
    event_ts = datetime(2026, 1, 20, 11, 58, tzinfo=timezone.utc)
    now = datetime(2026, 1, 20, 12, 0)

    freshness = assess_market_data_event_freshness(
        _stock_event(ts=event_ts),
        now=now,
        max_age_seconds=60,
    )

    assert freshness.ts == event_ts
    assert freshness.age_seconds == 120.0
    assert freshness.is_stale is True


def test_assess_market_data_event_freshness_rejects_negative_staleness_window() -> None:
    """Reject a negative age threshold for single-event freshness assessment."""
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="max_age_seconds must be non-negative"):
        assess_market_data_event_freshness(
            _stock_event(ts=now), now=now, max_age_seconds=-1
        )


def test_market_data_pipeline_planning_helpers_are_deterministic() -> None:
    """Select stream ingestion and freshness clocks solely from explicit mode inputs."""
    decision_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    current_ts = decision_ts + timedelta(minutes=1)

    assert (
        _should_use_stream_ingestion(ingest_market_data=True, stream_mode=True) is True
    )
    assert (
        _should_use_stream_ingestion(ingest_market_data=False, stream_mode=True)
        is False
    )
    assert (
        _should_use_stream_ingestion(ingest_market_data=True, stream_mode=False)
        is False
    )
    assert (
        _resolve_market_data_freshness_ts(
            mode="backtest",
            decision_ts=decision_ts,
            current_ts=current_ts,
        )
        == decision_ts
    )
    assert (
        _resolve_market_data_freshness_ts(
            mode="once",
            decision_ts=decision_ts,
            current_ts=current_ts,
        )
        == current_ts
    )


def test_empty_market_data_pipeline_result_is_stable() -> None:
    """Represent a no-data pipeline outcome with stable empty typed fields."""
    result = _empty_market_data_pipeline_result()

    assert result.processed_orders == ()
    assert result.market_data_events == ()
    assert result.price_lookup == {}


def test_market_data_event_table_name_selects_asset_class_table() -> None:
    """Map stock and crypto asset aliases onto canonical event tables."""
    assert _market_data_event_table_name("stocks") == "stock_bar_events"
    assert _market_data_event_table_name("stock") == "stock_bar_events"
    assert _market_data_event_table_name("crypto") == "crypto_bar_events"
    assert _market_data_event_table_name("cryptocurrency") == "crypto_bar_events"


def test_build_recent_market_data_query_shapes_sql_and_params() -> None:
    """Build normalized parameterized queries with an optional as-of bound."""
    as_of_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    latest = _build_recent_market_data_query(
        table="stock_bar_events",
        symbol="aapl",
        timeframe="1Min",
        as_of_ts=None,
    )
    bounded = _build_recent_market_data_query(
        table="crypto_bar_events",
        symbol="btc/usd",
        timeframe="5Min",
        as_of_ts=as_of_ts,
    )

    assert "FROM stock_bar_events" in latest.sql
    assert "ts <= %s" not in latest.sql
    assert latest.params == ("AAPL", "1Min")
    assert "FROM crypto_bar_events" in bounded.sql
    assert "ts <= %s" in bounded.sql
    assert bounded.params == ("BTC/USD", "5Min", as_of_ts)


def test_row_to_market_event_selects_stock_or_crypto_event() -> None:
    """Project one database row into the requested asset-specific event type."""
    ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    row = (ts, ts, 100.0, 101.0, 99.0, 100.5, 10.0, None, None, "event_store")

    stock = _row_to_market_event("stocks", "AAPL", "1Min", row)
    crypto = _row_to_market_event("crypto", "BTC/USD", "1Min", row)

    assert isinstance(stock, StockBarEvent)
    assert stock.symbol == "AAPL"
    assert stock.close == 100.5
    assert isinstance(crypto, CryptoBarEvent)
    assert crypto.symbol == "BTC/USD"
    assert crypto.close == 100.5
