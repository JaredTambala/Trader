"""Tests for the trading cycle execution path."""

import os
import subprocess
import sys
from datetime import datetime, timezone
from textwrap import dedent

from trader.cycle import run_cycle
from trader.config import Config
from trader.data import NoOpEventStore
from trader.identifiers import deterministic_cycle_id
from trader.market_data import StaticMarketDataSource
from trader.portfolio import Portfolio
from tests.support.duckdb_store import DuckDBEventStore
from trader.strategies import Strategy


def test_run_cycle_returns_success(tmp_path, monkeypatch):
    """Verify run_cycle executes successfully and writes DuckDB state.

    Args:
        tmp_path: Pytest temporary path fixture.
        monkeypatch: Pytest fixture for environment overrides.

    Raises:
        AssertionError: If the cycle fails or DB is not created.
    """
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    result = run_cycle(
        event_store=store,
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
    result = run_cycle(
        event_store=NoOpEventStore(),
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
    assert result.cycle_id == deterministic_cycle_id("demo", decision_ts)


def test_module_entrypoint_runs(tmp_path):
    """Smoke test the module entry point.

    Args:
        tmp_path: Pytest temporary path fixture.

    Raises:
        AssertionError: If module execution returns a non-zero code.
    """
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        dedent(
            """\
            runtime:
              mode: once
            strategy:
              type: noop
              id: noop
            market_data:
              source: noop
              asset_class: stocks
              symbols: []
            database:
              event_store: noop
            """
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(["src", env.get("PYTHONPATH", "")]).strip(os.pathsep)
    completed = subprocess.run(
        [sys.executable, "-m", "trader.cycle", str(config_path)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0


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
