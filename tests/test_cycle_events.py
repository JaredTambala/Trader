"""Tests for cycle event persistence and order lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace

from trader.cycle import run_cycle
from trader.config import Config
from trader.market_data import StaticMarketDataSource, StockBarEvent
from trader.portfolio import Portfolio
from trader.strategies import SimpleStrategy, Strategy
from trader.signal_generators import InMemoryBarsSignalGenerator
from trader.signals import Bar, SmaCrossoverSignal
from trader.indicators import SmaIndicator
from tests.support.duckdb_store import DuckDBEventStore


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

    run_cycle(
        event_store=store,
        strategy=SingleOrderStrategy(),
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
