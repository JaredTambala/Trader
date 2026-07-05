"""Tests for cycle event persistence and order lifecycle."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from trader.cycle import (
    assess_market_data_event_freshness,
    assess_market_data_readiness,
    build_enriched_cycle_order,
    build_broker_fill_event_payload,
    build_metrics_snapshot_event,
    build_metrics_snapshot_payload,
    build_order_lifecycle_event_payload,
    normalize_cycle_order_intent,
    resolve_order_lifecycle_event_timestamp,
    resolve_terminal_event_timestamp,
    run_cycle,
)
from trader.identifiers import deterministic_client_order_id
from trader.config import Config
from trader.market_data import StaticMarketDataSource, StockBarEvent
from trader.portfolio import Portfolio, Position
from trader.signals import Bar
from trader.strategies import Strategy
from tests.support.duckdb_store import DuckDBEventStore
from trader_standard.indicators import SmaIndicator
from trader_standard.risk import NoOpRiskManager
from trader_standard.signal_generators import InMemoryBarsSignalGenerator
from trader_standard.signals import SmaCrossoverSignal
from trader_standard.strategies import SimpleStrategy


class SingleOrderStrategy(Strategy):
    """Strategy that always emits a single buy order."""

    @property
    def strategy_id(self) -> str:
        return "single_order"

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store,
        portfolio,
    ):
        return [
            {
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "order_type": "market",
            }
        ]


def _stock_event(*, ts: datetime, close: float = 100.0) -> StockBarEvent:
    return StockBarEvent(
        symbol="AAPL",
        timeframe="1Min",
        ts=ts,
        ingested_at=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        trade_count=None,
        vwap=None,
        source="test",
    )


def test_assess_market_data_readiness_blocks_missing_market_data() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    readiness = assess_market_data_readiness([], now=now, max_age_seconds=60)

    assert readiness.should_skip is True
    assert readiness.latest_ts is None
    assert readiness.age_seconds is None
    assert readiness.is_stale is False
    assert readiness.reason == "missing_market_data"


def test_assess_market_data_readiness_reports_fresh_latest_event() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    older = _stock_event(ts=now - timedelta(seconds=30), close=99.0)
    latest = _stock_event(ts=now - timedelta(seconds=10), close=101.0)

    readiness = assess_market_data_readiness([older, latest], now=now, max_age_seconds=60)

    assert readiness.should_skip is False
    assert readiness.latest_ts == latest.ts
    assert readiness.age_seconds == 10.0
    assert readiness.is_stale is False
    assert readiness.reason is None


def test_assess_market_data_readiness_reports_stale_latest_event_and_normalizes_now() -> None:
    now = datetime(2026, 1, 20, 12, 0)
    latest = _stock_event(ts=datetime(2026, 1, 20, 11, 58, tzinfo=timezone.utc))

    readiness = assess_market_data_readiness([latest], now=now, max_age_seconds=60)

    assert readiness.should_skip is True
    assert readiness.latest_ts == latest.ts
    assert readiness.age_seconds == 120.0
    assert readiness.is_stale is True
    assert readiness.reason == "stale_market_data"


def test_assess_market_data_readiness_rejects_negative_staleness_window() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="max_age_seconds must be non-negative"):
        assess_market_data_readiness([_stock_event(ts=now)], now=now, max_age_seconds=-1)


def test_assess_market_data_event_freshness_reports_fresh_event() -> None:
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    event = _stock_event(ts=now - timedelta(seconds=5))

    freshness = assess_market_data_event_freshness(event, now=now, max_age_seconds=60)

    assert freshness.ts == event.ts
    assert freshness.age_seconds == 5.0
    assert freshness.max_age_seconds == 60
    assert freshness.is_stale is False


def test_assess_market_data_event_freshness_reports_stale_event_and_normalizes_now() -> None:
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
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="max_age_seconds must be non-negative"):
        assess_market_data_event_freshness(_stock_event(ts=now), now=now, max_age_seconds=-1)


def test_build_metrics_snapshot_payload_excludes_unpriced_positions() -> None:
    positions = {
        "AAPL": Position(symbol="AAPL", qty=2.0, avg_price=90.0),
        "MSFT": Position(symbol="MSFT", qty=-1.0, avg_price=200.0),
        "NVDA": Position(symbol="NVDA", qty=5.0, avg_price=50.0),
    }

    payload = build_metrics_snapshot_payload(
        positions=positions,
        cash_balance=1000.0,
        price_lookup={"AAPL": 100.0, "MSFT": 250.0},
        asset_class="stocks",
        symbols=("AAPL", "MSFT", "NVDA"),
    )

    assert payload.equity == 950.0
    assert payload.cash == 1000.0
    assert payload.net_exposure == -50.0
    assert payload.gross_exposure == 450.0
    assert payload.to_payload() == {
        "equity": 950.0,
        "cash": 1000.0,
        "net_exposure": -50.0,
        "gross_exposure": 450.0,
        "asset_class": "stocks",
        "symbols": ["AAPL", "MSFT", "NVDA"],
    }


def test_build_metrics_snapshot_event_serializes_payload_deterministically() -> None:
    asof_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    event = build_metrics_snapshot_event(
        positions={"AAPL": Position(symbol="AAPL", qty=1.0, avg_price=90.0)},
        cash_balance=500.0,
        price_lookup={"AAPL": 125.0},
        asof_ts=asof_ts,
        run_id="run_1",
        cycle_id="cycle_1",
        asset_class="stocks",
        symbols=("AAPL",),
    )

    record = event.to_record()
    assert record["ts"] == asof_ts
    assert record["run_id"] == "run_1"
    assert record["session_id"] == "run_1"
    assert record["cycle_id"] == "cycle_1"
    assert json.loads(str(record["payload"])) == {
        "equity": 625.0,
        "cash": 500.0,
        "net_exposure": 125.0,
        "gross_exposure": 125.0,
        "asset_class": "stocks",
        "symbols": ["AAPL"],
    }


def test_normalize_cycle_order_intent_preserves_source_without_mutation() -> None:
    order = {"symbol": " aapl ", "side": " BUY ", "qty": "2.5"}
    original = dict(order)

    intent = normalize_cycle_order_intent(order)

    assert order == original
    assert intent.source is order
    assert intent.symbol == "AAPL"
    assert intent.side == "buy"
    assert intent.qty == 2.5


def test_build_enriched_cycle_order_attaches_deterministic_metadata() -> None:
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    order = {"symbol": " aapl ", "side": " BUY ", "qty": "2.5"}
    original = dict(order)

    enriched = build_enriched_cycle_order(
        order,
        run_id="run_1",
        cycle_id="cycle_1",
        created_at=created_at,
        price_lookup={"AAPL": 101.25},
        asset_class="stocks",
        time_in_force="day",
    )

    assert order == original
    assert enriched.to_record() == {
        **order,
        "symbol": "AAPL",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "client_order_id": deterministic_client_order_id("cycle_1", "AAPL", "buy", 2.5),
        "price": 101.25,
        "created_at": created_at,
        "asset_class": "stocks",
        "time_in_force": "day",
    }


def test_build_enriched_cycle_order_preserves_explicit_order_fields() -> None:
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    explicit_created_at = created_at.replace(hour=13)
    order = {
        "symbol": "MSFT",
        "side": "sell",
        "qty": 1.0,
        "client_order_id": "cid_explicit",
        "created_at": explicit_created_at,
        "time_in_force": "gtc",
    }

    enriched = build_enriched_cycle_order(
        order,
        run_id="run_1",
        cycle_id="cycle_1",
        created_at=created_at,
        price_lookup={},
        asset_class="stocks",
        time_in_force="day",
    )

    record = enriched.to_record()
    assert record["client_order_id"] == "cid_explicit"
    assert record["created_at"] == explicit_created_at
    assert record["time_in_force"] == "gtc"
    assert record["price"] is None


def test_resolve_order_lifecycle_event_timestamp_is_pure_and_stably_ordered() -> None:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    fallback_ts = base_ts + timedelta(minutes=5)
    order = {"created_at": base_ts}

    assert (
        resolve_order_lifecycle_event_timestamp(order, status="created", fallback_ts=fallback_ts)
        == base_ts
    )
    assert (
        resolve_order_lifecycle_event_timestamp(order, status="validated", fallback_ts=fallback_ts)
        == base_ts + timedelta(microseconds=1)
    )
    assert (
        resolve_order_lifecycle_event_timestamp(order, status="submitted", fallback_ts=fallback_ts)
        == base_ts + timedelta(microseconds=2)
    )
    explicit_ts = base_ts + timedelta(seconds=10)
    assert (
        resolve_order_lifecycle_event_timestamp(
            order,
            status="created",
            fallback_ts=fallback_ts,
            event_ts=explicit_ts,
        )
        == explicit_ts
    )
    assert (
        resolve_order_lifecycle_event_timestamp({}, status="created", fallback_ts=fallback_ts)
        == fallback_ts
    )


def test_build_order_lifecycle_event_payload_does_not_mutate_input() -> None:
    created_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    order = {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "rejection_reason": "risk_limit",
    }
    original = dict(order)

    payload = build_order_lifecycle_event_payload(
        order,
        status="rejected",
        broker_order_id=None,
        created_at=created_at,
        order_event_id="order_evt_fixed",
    )

    assert order == original
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
        "status": "rejected",
        "broker_order_id": None,
        "rejection_reason": "risk_limit",
        "created_at": created_at,
    }


def test_build_broker_fill_event_payload_returns_fill_record_or_none() -> None:
    fill_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    order = {
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "qty": 2.0,
        "price": 100.0,
    }
    response = {
        "client_order_id": "cid_1",
        "fill_qty": "1.5",
        "fill_price": "100.25",
        "raw_fill_price": 100.0,
        "slippage_amount": 0.375,
        "fee_amount": 0.1,
    }

    payload = build_broker_fill_event_payload(order, response, fill_ts=fill_ts)

    assert payload is not None
    assert payload.to_record() == {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "session_id": "run_1",
        "cycle_id": "cycle_1",
        "fill_ts": fill_ts,
        "fill_qty": 1.5,
        "raw_fill_price": 100.0,
        "fill_price": 100.25,
        "slippage_amount": 0.375,
        "fee_amount": 0.1,
    }
    assert (
        build_broker_fill_event_payload(
            order,
            {"client_order_id": "cid_1", "fill_price": None},
            fill_ts=fill_ts,
        )
        is None
    )


def test_resolve_terminal_event_timestamp_preserves_later_broker_time() -> None:
    latest_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    proposed_ts = latest_ts + timedelta(seconds=1)
    fallback_ts = latest_ts + timedelta(minutes=1)

    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=proposed_ts,
            latest_order_ts=latest_ts,
            fallback_ts=fallback_ts,
        )
        == proposed_ts
    )


def test_resolve_terminal_event_timestamp_nudges_stale_or_equal_time() -> None:
    latest_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=latest_ts,
            latest_order_ts=latest_ts,
            fallback_ts=latest_ts + timedelta(minutes=1),
        )
        == latest_ts + timedelta(microseconds=1)
    )
    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=latest_ts - timedelta(seconds=1),
            latest_order_ts=latest_ts,
            fallback_ts=latest_ts + timedelta(minutes=1),
        )
        == latest_ts + timedelta(microseconds=1)
    )


def test_resolve_terminal_event_timestamp_uses_fallback_and_normalizes_naive_datetimes() -> None:
    latest_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    fallback_ts = latest_ts + timedelta(seconds=10)
    naive_proposed_ts = datetime(2026, 1, 20, 12, 0, 20)

    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=None,
            latest_order_ts=latest_ts,
            fallback_ts=fallback_ts,
        )
        == fallback_ts
    )
    assert (
        resolve_terminal_event_timestamp(
            proposed_ts=naive_proposed_ts,
            latest_order_ts=None,
            fallback_ts=fallback_ts,
        )
        == naive_proposed_ts.replace(tzinfo=timezone.utc)
    )


def _base_config(db_path: str) -> Config:
    return Config(
        mode="once",
        strategy_type="noop",
        strategy_id="test",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=db_path,
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("AAPL",),
        market_data_max_age_seconds=300,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
        alpaca_base_url="https://paper-api.alpaca.markets",
        pg_dsn="",
        pg_host="",
        pg_port=5432,
        pg_db="",
        pg_user="",
        pg_password="",
        buffered_event_store=False,
        buffer_flush_interval_ms=250,
        buffer_max_batch_size=500,
        buffer_max_queue_size=10000,
        buffer_block_on_full=True,
        log_signal_events=True,
        log_indicator_events=True,
        log_order_events=True,
        log_fill_events=True,
        log_position_snapshots=True,
        broker_type="noop",
    )


def test_indicator_events_persisted(tmp_path) -> None:
    """Ensure indicator events are written when enabled."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars = [
        Bar(ts=base_ts - timedelta(minutes=3), open=100, high=101, low=99, close=100, volume=1, vwap=None, trade_count=None),
        Bar(ts=base_ts - timedelta(minutes=2), open=101, high=102, low=100, close=101, volume=1, vwap=None, trade_count=None),
        Bar(ts=base_ts - timedelta(minutes=1), open=102, high=103, low=101, close=102, volume=1, vwap=None, trade_count=None),
        Bar(ts=base_ts, open=103, high=104, low=102, close=103, volume=1, vwap=None, trade_count=None),
    ]
    signal = SmaCrossoverSignal(SmaIndicator(period=2), SmaIndicator(period=3))
    generator = InMemoryBarsSignalGenerator(
        bars_by_symbol={"AAPL": bars},
        signals=[signal],
        symbols=["AAPL"],
        timeframe="1Min",
        event_store=store,
    )
    strategy = SimpleStrategy(signal_generator=generator, primary_signal=signal.name)

    event = StockBarEvent(
        symbol="AAPL",
        timeframe="1Min",
        ts=base_ts,
        ingested_at=base_ts,
        open=103,
        high=104,
        low=102,
        close=103,
        volume=10,
        trade_count=None,
        vwap=None,
        source="test",
    )

    config = replace(_base_config(str(tmp_path / "events.duckdb")), mode="backtest")
    run_cycle(
        event_store=store,
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        market_data_source=StaticMarketDataSource([event]),
        config=config,
        decision_ts=base_ts,
        ingest_market_data=False,
        portfolio=Portfolio.from_event_store(store, asof_ts=base_ts),
    )

    count = store.connection().execute("SELECT COUNT(*) FROM indicator_events").fetchone()[0]
    assert count > 0


def test_order_lifecycle_and_fill_events(tmp_path) -> None:
    """Verify order lifecycle and fill events are persisted for internal broker."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    event = StockBarEvent(
        symbol="AAPL",
        timeframe="1Min",
        ts=now,
        ingested_at=now,
        open=100,
        high=101,
        low=99,
        close=100.5,
        volume=10,
        trade_count=None,
        vwap=None,
        source="test",
    )

    config = replace(
        _base_config(str(tmp_path / "events.duckdb")),
        broker_type="internal",
        mode="backtest",
    )

    strategy = SingleOrderStrategy()
    run_cycle(
        event_store=store,
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        market_data_source=StaticMarketDataSource([event]),
        config=config,
        decision_ts=now,
        ingest_market_data=False,
        portfolio=Portfolio.from_event_store(store, asof_ts=now),
    )

    statuses = {
        row[0] for row in store.connection().execute("SELECT status FROM order_events").fetchall()
    }
    assert {"created", "validated", "submitted", "filled"}.issubset(statuses)

    fill_count = store.connection().execute("SELECT COUNT(*) FROM fill_events").fetchone()[0]
    assert fill_count == 1
