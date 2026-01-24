"""Tests for the trader service runner."""

from __future__ import annotations

from trader.config import Config
from trader.data import NoOpEventStore
from trader.trader_service import TraderService


class CycleRecorder:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args, **kwargs) -> None:
        self.calls += 1


def _config() -> Config:
    return Config(
        mode="loop",
        strategy_type="noop",
        strategy_id="noop",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=":memory:",
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=(),
        market_data_max_age_seconds=60,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
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


def test_trader_service_loop_runs_expected_iterations(monkeypatch) -> None:
    recorder = CycleRecorder()
    monkeypatch.setattr("trader.trader_service.run_cycle", recorder)

    service = TraderService(
        _config(),
        event_store=NoOpEventStore(),
        cadence_seconds=0.0,
        max_iterations=3,
    )
    service.run()

    assert recorder.calls == 3
