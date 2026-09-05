"""Exercise the core backtest runner and its execution planning boundary.

Subject: Historical replay scheduling, runner outcomes, universe alignment, and runtime configuration.
Level: In-process runner integration and deterministic planning unit contracts.
Collaborators: Real runner/planning code, temporary DuckDB stores, injected no-op policies, and a fake cycle call.
Guarantees: Bounded bars drive the expected cycles through backtest-only dependencies and explicit result states.
Non-goals: Strategy profitability, Postgres persistence, provider data, export formatting, or fill accounting.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader.backtest import BacktestAssumptions, BacktestRunner, BacktestSpec
from trader.backtest.runtime_planning import (
    _build_backtest_runtime_config,
    _build_symbol_runtime_configs,
    _count_scheduled_symbol_runs,
    _normalize_backtest_symbols,
    _resolve_backtest_asset_class,
    _resolve_effective_replay_limit,
)
from trader.config import Config
from tests.support.duckdb_store import DuckDBEventStore
from trader_standard.risk import NoOpRiskManager
from trader_standard.strategies.noop import NoOpStrategy


class CycleRecorder:
    def __init__(self) -> None:
        self.decision_times: list[datetime] = []

    def __call__(self, *args, **kwargs) -> None:
        self.decision_times.append(kwargs["decision_ts"])


class UniverseNoOpStrategy(NoOpStrategy):
    @property
    def decision_scope(self) -> str:
        return "universe_snapshot"


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
    """Replay each stored timestamp once and retain explicit default assumptions."""
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
    monkeypatch.setattr("trader.backtest.core.run_cycle", recorder)

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


def test_backtest_runner_returns_empty_result_when_window_has_no_bars(
    tmp_path: Path,
) -> None:
    """Return identified empty evidence when the requested window contains no bars."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    base = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    spec = BacktestSpec(start=base, end=base + timedelta(minutes=2), timeframe="1Min")

    runner = BacktestRunner(
        _config(tmp_path),
        spec,
        symbols=["AAPL"],
        asset_class="stocks",
        event_store=store,
        strategy=NoOpStrategy(),
        risk_manager=NoOpRiskManager(),
        run_id="run_empty",
        started_at=base,
    )

    result = runner.run()

    assert result.run_id == "run_empty"
    assert result.total_runs == 0
    assert result.success_runs == 0
    assert result.failed_runs == 0
    assert result.symbols == ("AAPL",)
    assert result.warnings == ("No bars found for backtest window.",)
    assert result.strategy_performance.start_equity is None
    assert result.benchmark_performance.start_equity is None


def test_universe_backtest_runs_once_only_at_complete_aligned_timestamps(
    monkeypatch, tmp_path: Path
) -> None:
    """Run a universe strategy only when every configured symbol is timestamp-aligned."""
    store = DuckDBEventStore(str(tmp_path / "universe.duckdb"))
    base = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    complete = base + timedelta(minutes=1)
    for symbol, timestamps in {
        "AAPL": (base, complete),
        "MSFT": (complete,),
    }.items():
        for ts in timestamps:
            store.record_event(
                "stock_bar_events",
                {
                    "symbol": symbol,
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

    calls: list[dict[str, object]] = []

    def record_cycle(*args, **kwargs) -> None:
        del args
        calls.append(kwargs)
        events = kwargs["market_data_source"].fetch()
        assert {event.symbol for event in events} == {"AAPL", "MSFT"}
        assert {event.ts for event in events} == {complete}

    monkeypatch.setattr("trader.backtest.core.run_cycle", record_cycle)
    runner = BacktestRunner(
        _config(tmp_path),
        BacktestSpec(start=base, end=complete, timeframe="1Min"),
        symbols=["AAPL", "MSFT"],
        asset_class="stocks",
        event_store=store,
        strategy=UniverseNoOpStrategy(),
        risk_manager=NoOpRiskManager(),
    )

    result = runner.run()

    assert [call["decision_ts"] for call in calls] == [complete]
    assert calls[0]["config"].market_data_symbols == ("AAPL", "MSFT")
    assert result.total_runs == 1
    assert result.warnings == (
        "Skipped 1 incomplete universe timestamps; exact symbol alignment is required.",
    )


def test_build_backtest_runtime_config_forces_backtest_dependencies(
    tmp_path: Path,
) -> None:
    """Copy source configuration while forcing isolated backtest data and broker dependencies."""
    source = _config(tmp_path)

    config = _build_backtest_runtime_config(
        source,
        symbols=("MSFT", "AAPL"),
        asset_class="crypto",
        timeframe="5Min",
    )

    assert config.mode == "backtest"
    assert config.market_data_source == "noop"
    assert config.market_data_symbols == ("MSFT", "AAPL")
    assert config.market_data_asset_class == "crypto"
    assert config.strategy_timeframe == "5Min"
    assert config.broker_type == "internal"
    assert source.mode == "once"
    assert source.broker_type == "noop"


def test_build_symbol_runtime_configs_scopes_each_config_to_one_symbol(
    tmp_path: Path,
) -> None:
    """Derive per-symbol configurations without narrowing the shared source configuration."""
    source = _build_backtest_runtime_config(
        _config(tmp_path),
        symbols=("AAPL", "MSFT"),
        asset_class="stocks",
        timeframe="1Min",
    )

    configs = _build_symbol_runtime_configs(source, ("AAPL", "MSFT"))

    assert configs["AAPL"].market_data_symbols == ("AAPL",)
    assert configs["MSFT"].market_data_symbols == ("MSFT",)
    assert configs["AAPL"].mode == "backtest"
    assert source.market_data_symbols == ("AAPL", "MSFT")


def test_backtest_runtime_planning_normalizes_symbols_and_asset_class() -> None:
    """Normalize explicit or configured symbols and asset classes before replay planning."""
    assert _normalize_backtest_symbols(
        (" aapl ", "", "msft"), config_symbols=("TSLA",)
    ) == ("AAPL", "MSFT")
    assert _normalize_backtest_symbols(
        None, config_symbols=(" btc/usd ", "ETH/USD")
    ) == ("BTC/USD", "ETH/USD")
    assert (
        _resolve_backtest_asset_class("Crypto", config_asset_class="stocks") == "crypto"
    )
    assert _resolve_backtest_asset_class(None, config_asset_class="Stocks") == "stocks"


def test_count_scheduled_symbol_runs_and_resolve_effective_limit() -> None:
    """Count scheduled symbol executions and cap them only when requested."""
    first = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    second = first + timedelta(minutes=1)
    schedule = {
        first: ("AAPL", "MSFT"),
        second: ("AAPL",),
    }

    total = _count_scheduled_symbol_runs(schedule, (first, second))

    assert total == 3
    assert _resolve_effective_replay_limit(total_bars=total, max_runs=None) == 3
    assert _resolve_effective_replay_limit(total_bars=total, max_runs=10) == 3
    assert _resolve_effective_replay_limit(total_bars=total, max_runs=2) == 2


def test_backtest_runner_requires_injected_risk_manager(tmp_path: Path) -> None:
    """Reject runner construction when the caller omits an explicit risk policy."""
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
