"""Tests for the backtest runner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader.backtest import BacktestAssumptions, BacktestRunner, BacktestSpec
from trader.config import Config
from tests.support.duckdb_store import DuckDBEventStore
from trader_standard.risk import NoOpRiskManager
from trader_standard.strategies.noop import NoOpStrategy


class CycleRecorder:
    def __init__(self) -> None:
        self.decision_times: list[datetime] = []

    def __call__(self, *args, **kwargs) -> None:
        self.decision_times.append(kwargs["decision_ts"])


def _config(tmp_path: Path) -> Config:
    return Config(
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


def test_backtest_runner_replays_timestamps(monkeypatch, tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    base = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    timestamps = [base, base + timedelta(minutes=1), base + timedelta(minutes=2)]
    for ts in timestamps:
        store.record_event(
            "stock_bar_events",
            {
                "symbol": "AAPL",
                "timeframe": "1Min",
                "ts": ts,
                "ingested_at": ts,
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

    recorder = CycleRecorder()
    monkeypatch.setattr("trader.backtest.run_cycle", recorder)

    spec = BacktestSpec(start=base, end=base + timedelta(minutes=2), timeframe="1Min")
    runner = BacktestRunner(
        _config(tmp_path),
        spec,
        symbols=["AAPL"],
        asset_class="stocks",
        event_store=store,
        strategy=NoOpStrategy(),
        risk_manager=NoOpRiskManager(),
    )
    result = runner.run()

    assert recorder.decision_times == timestamps
    assert result.assumptions == BacktestAssumptions()
    assert result.warnings == ()
    assert result.total_fees == 0.0
    assert result.total_slippage == 0.0


def test_backtest_runner_requires_injected_risk_manager(tmp_path: Path) -> None:
    spec = BacktestSpec(
        start=datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc),
        end=datetime(2026, 1, 21, 12, 1, tzinfo=timezone.utc),
        timeframe="1Min",
    )
    with pytest.raises(TypeError):
        BacktestRunner(
            _config(tmp_path),
            spec,
            symbols=["AAPL"],
            asset_class="stocks",
            event_store=DuckDBEventStore(str(tmp_path / "events.duckdb")),
            strategy=NoOpStrategy(),
        )
