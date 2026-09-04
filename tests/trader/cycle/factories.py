"""Package-owned value factories shared by core cycle contract tests."""

from __future__ import annotations

from datetime import datetime

from trader.config import Config
from trader.market_data import StockBarEvent


def build_cycle_config(db_path: str) -> Config:
    """Return the common isolated runtime configuration used by cycle tests."""
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


def stock_event(*, ts: datetime, close: float = 100.0) -> StockBarEvent:
    """Return a normalized stock bar event for one deterministic test symbol."""
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
