"""Tests for the trading cycle execution path."""

import logging
from datetime import datetime, timezone

from trader.cycle import run_cycle
from trader.config import Config
from trader.data import NoOpEventStore
from trader.identifiers import deterministic_cycle_id
from trader.market_data import StaticMarketDataSource, StockBarEvent
from trader.portfolio import Portfolio
from tests.support.duckdb_store import DuckDBEventStore
from trader.strategies import Strategy
from trader_standard.risk import NoOpRiskManager, OpenBuyOrderLimitRiskManager
from trader_standard.strategies.noop import NoOpStrategy


def test_run_cycle_returns_success(tmp_path, monkeypatch):
    """Verify run_cycle executes successfully and writes DuckDB state.

    Args:
        tmp_path: Pytest temporary path fixture.
        monkeypatch: Pytest fixture for environment overrides.

    Raises:
        AssertionError: If the cycle fails or DB is not created.
    """
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    strategy = NoOpStrategy()
    result = run_cycle(
        event_store=store,
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        config=Config(
            mode="once",
            strategy_type="noop",
            strategy_id="noop",
            strategy_timeframe="1Min",
            sma_short_window=2,
            sma_long_window=3,
            db_path=str(tmp_path / "events.duckdb"),
            event_store="postgres",
            market_data_source="noop",
            market_data_asset_class="stocks",
            market_data_stock_feed="iex",
            market_data_symbols=(),
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
        ),
    )
    assert result.status == "success"
    assert result.run_id
    assert result.cycle_id
    assert (tmp_path / "events.duckdb").exists()


def test_run_cycle_uses_deterministic_cycle_id(tmp_path, monkeypatch):
    """Ensure deterministic cycle IDs are used with a fixed decision timestamp.

    Args:
        tmp_path: Pytest temporary path fixture.
        monkeypatch: Pytest fixture for environment overrides.

    Raises:
        AssertionError: If the run ID does not match expectations.
    """
    decision_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    strategy = NoOpStrategy()
    result = run_cycle(
        event_store=NoOpEventStore(),
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        config=Config(
            mode="once",
            strategy_type="noop",
            strategy_id="demo",
            strategy_timeframe="1Min",
            sma_short_window=2,
            sma_long_window=3,
            db_path=str(tmp_path / "events.duckdb"),
            event_store="postgres",
            market_data_source="noop",
            market_data_asset_class="stocks",
            market_data_stock_feed="iex",
            market_data_symbols=(),
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
        ),
        decision_ts=decision_ts,
    )
    assert result.cycle_id == deterministic_cycle_id(strategy.strategy_id, decision_ts)


class ProbeStrategy(Strategy):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def strategy_id(self) -> str:
        return "probe"

    def generate_orders(self, *, run_id, cycle_id, decision_ts, event_store, portfolio):
        self.calls += 1
        return []


def test_run_cycle_uses_event_store_market_data(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime.now(timezone.utc)
    store.record_event(
        "stock_bar_events",
        {
            "symbol": "AAPL",
            "timeframe": "1Min",
            "ts": now,
            "ingested_at": now,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "trade_count": None,
            "vwap": None,
            "source": "test",
        },
    )

    strategy = ProbeStrategy()
    run_cycle(
        event_store=store,
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        market_data_source=StaticMarketDataSource([]),
        config=Config(
            mode="once",
            strategy_type="noop",
            strategy_id="probe",
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
        ),
        decision_ts=now,
        portfolio=Portfolio.from_event_store(store, asof_ts=now),
    )
    assert strategy.calls == 1


class BuyStrategy(Strategy):
    @property
    def strategy_id(self) -> str:
        return "buy-probe"

    def generate_orders(self, *, run_id, cycle_id, decision_ts, event_store, portfolio):
        return [{"symbol": "AAPL", "side": "buy", "qty": 1.0, "order_type": "market"}]


def test_run_cycle_logs_risk_rejections(tmp_path, caplog) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime.now(timezone.utc)
    store.record_event(
        "order_events",
        {
            "order_event_id": "order_evt_existing",
            "client_order_id": "cid_existing",
            "run_id": "run_existing",
            "cycle_id": "cycle_existing",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 1.0,
            "order_type": "market",
            "status": "submitted",
            "broker_order_id": None,
            "rejection_reason": None,
            "created_at": now,
        },
    )
    caplog.set_level(logging.INFO)

    run_cycle(
        event_store=store,
        strategy=BuyStrategy(),
        risk_manager=OpenBuyOrderLimitRiskManager(max_open_buy_orders_per_symbol=1),
        market_data_source=StaticMarketDataSource(
            [
                StockBarEvent(
                    symbol="AAPL",
                    timeframe="1Min",
                    ts=now,
                    ingested_at=now,
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.5,
                    volume=10.0,
                    trade_count=None,
                    vwap=None,
                    source="test",
                )
            ]
        ),
        config=Config(
            mode="once",
            strategy_type="buy-probe",
            strategy_id="buy-probe",
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
        ),
        decision_ts=now,
        portfolio=Portfolio.from_event_store(store, asof_ts=now),
    )

    assert "reason=open_buy_order_exists manager=OpenBuyOrderLimitRiskManager" in caplog.text
