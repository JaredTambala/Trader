"""Tests for the SMA strategy implementation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from trader.config import Config
from trader.cycle import run_cycle
from tests.support.duckdb_store import DuckDBEventStore
from trader.market_data import StaticMarketDataSource, StockBarEvent
from trader.signal_generators import SimpleBarsSignalGenerator
from trader.signals import SmaCrossoverSignal
from trader.indicators import SmaIndicator
from trader.portfolio import Portfolio
from trader.strategies import SimpleStrategy


def _config(tmp_path: Path) -> Config:
    return Config(
        mode="once",
        strategy_type="sma",
        strategy_id="sma_v1",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=str(tmp_path / "events.duckdb"),
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("AAPL",),
        market_data_max_age_seconds=60,
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


def test_sma_strategy_emits_signal_when_sufficient_bars(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime.now(timezone.utc)
    bars = [
        (now - timedelta(minutes=3), 8.0),
        (now - timedelta(minutes=2), 8.0),
        (now - timedelta(minutes=1), 8.0),
        (now, 12.0),
    ]
    for ts, close in bars:
        store.record_event(
            "stock_bar_events",
            {
                "symbol": "AAPL",
                "timeframe": "1Min",
                "ts": ts,
                "ingested_at": now,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
                "trade_count": None,
                "vwap": None,
                "source": "test",
            },
        )

    generator = SimpleBarsSignalGenerator(
        event_store=store,
        symbols=["AAPL"],
        asset_class="stocks",
        timeframe="1Min",
        signals=[
            SmaCrossoverSignal(
                short=SmaIndicator(period=2),
                long=SmaIndicator(period=3),
            )
        ],
    )
    strategy = SimpleStrategy(signal_generator=generator, primary_signal="sma_crossover")
    orders = list(
        strategy.generate_orders(
            run_id="run_test",
            cycle_id="cycle_test",
            decision_ts=now,
            event_store=store,
            portfolio=Portfolio.empty(),
        )
    )
    assert len(orders) == 1
    assert orders[0]["symbol"] == "AAPL"
    assert orders[0]["side"] == "buy"
    assert orders[0]["qty"] == 1.0


def test_cycle_persists_sma_signals(tmp_path: Path) -> None:
    config = _config(tmp_path)
    store = DuckDBEventStore(config.db_path)
    now = datetime.now(timezone.utc)

    # Pre-seed three bars; the ingested bar will become the 4th.
    for minutes_ago, close in [(3, 8.0), (2, 8.0), (1, 8.0)]:
        store.record_event(
            "stock_bar_events",
            {
                "symbol": "AAPL",
                "timeframe": "1Min",
                "ts": now - timedelta(minutes=minutes_ago),
                "ingested_at": now,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
                "trade_count": None,
                "vwap": None,
                "source": "test",
            },
        )

    events = [
        StockBarEvent(
            symbol="AAPL",
            timeframe="1Min",
            ts=now,
            ingested_at=now,
            open=12.0,
            high=12.0,
            low=12.0,
            close=12.0,
            volume=1.0,
            trade_count=None,
            vwap=None,
            source="test",
        )
    ]
    run_cycle(
        event_store=store,
        config=config,
        decision_ts=now,
        market_data_source=StaticMarketDataSource(events),
    )

    conn = duckdb.connect(config.db_path)
    rows = conn.execute(
        "SELECT symbol, signal_value, target_qty FROM signal_events WHERE run_id IS NOT NULL"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "AAPL"
    assert float(rows[0][2]) in {0.0, 1.0}


def test_simple_strategy_emits_sell_order_on_negative_signal(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime.now(timezone.utc)
    bars = [
        (now - timedelta(minutes=3), 12.0),
        (now - timedelta(minutes=2), 12.0),
        (now - timedelta(minutes=1), 12.0),
        (now, 8.0),
    ]
    for ts, close in bars:
        store.record_event(
            "stock_bar_events",
            {
                "symbol": "AAPL",
                "timeframe": "1Min",
                "ts": ts,
                "ingested_at": now,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
                "trade_count": None,
                "vwap": None,
                "source": "test",
            },
        )

    generator = SimpleBarsSignalGenerator(
        event_store=store,
        symbols=["AAPL"],
        asset_class="stocks",
        timeframe="1Min",
        signals=[
            SmaCrossoverSignal(
                short=SmaIndicator(period=2),
                long=SmaIndicator(period=3),
            )
        ],
    )
    strategy = SimpleStrategy(signal_generator=generator, primary_signal="sma_crossover")
    orders = list(
        strategy.generate_orders(
            run_id="run_test",
            cycle_id="cycle_test",
            decision_ts=now,
            event_store=store,
            portfolio=Portfolio.empty(),
        )
    )
    assert len(orders) == 1
    assert orders[0]["side"] == "sell"
