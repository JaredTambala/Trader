"""Protect the backtest runner from configured live-adapter dependencies.

Subject: Broker and market-data isolation applied during backtest runner construction.
Level: In-process safety contract.
Collaborators: Real runner configuration with injected no-op strategy and risk implementations.
Guarantees: A live-shaped source configuration is forced onto internal, no-op backtest dependencies.
Non-goals: Order execution, broker connectivity, replay results, or runtime startup recovery.
"""

from __future__ import annotations

from datetime import datetime, timezone

from trader.backtest import BacktestRunner, BacktestSpec
from trader.config import Config
from trader_standard.risk import NoOpRiskManager
from trader_standard.strategies.noop import NoOpStrategy


def _config() -> Config:
    return Config(
        mode="once",
        strategy_type="noop",
        strategy_id="noop",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path="",
        event_store="postgres",
        market_data_source="alpaca",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("AAPL",),
        market_data_max_age_seconds=60,
        alpaca_api_key="key",
        alpaca_secret_key="secret",
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
        broker_type="alpaca",
    )


def test_backtest_runner_forces_internal_broker() -> None:
    """Replace configured Alpaca dependencies with the isolated internal backtest broker."""
    runner = BacktestRunner(
        _config(),
        BacktestSpec(
            start=datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 21, 12, 1, tzinfo=timezone.utc),
            timeframe="1Min",
        ),
        symbols=["AAPL"],
        asset_class="stocks",
        event_store=object(),
        strategy=NoOpStrategy(),
        risk_manager=NoOpRiskManager(),
    )

    assert runner._config.mode == "backtest"
    assert runner._config.market_data_source == "noop"
    assert runner._config.broker_type == "internal"
