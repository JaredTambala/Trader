from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest

from tests.test_backtest_exports import _sample_result
from trader.backtest import BacktestAssumptions, BacktestSpec
from trader.config import Config
from trader_research.research import (
    attach_research_metadata,
    build_parameter_grid,
    build_run_provenance,
    comparison_payload,
    config_snapshot_hash,
    experiment_id_from_name,
    experiment_run_id,
    export_research_bundle,
    result_summary,
)
from trader.strategy_metadata import StrategyInfo


def test_experiment_ids_are_deterministic() -> None:
    assert experiment_id_from_name("Demo Trend Following!") == "exp_demo_trend_following"
    assert experiment_run_id("exp_demo", "run_1") == experiment_run_id("exp_demo", "run_1")


def test_parameter_grid_expands_in_sorted_key_order() -> None:
    config_data = {
        "strategy": {"trend_following": {}},
        "research": {
            "sweep": {
                "max_runs": 4,
                "parameters": {
                    "strategy.trend_following.ema_slow_period": [4, 6],
                    "strategy.trend_following.ema_fast_period": [2, 3],
                },
            }
        },
    }

    grid = build_parameter_grid(config_data)

    assert [params for params, _ in grid] == [
        {
            "strategy.trend_following.ema_fast_period": 2,
            "strategy.trend_following.ema_slow_period": 4,
        },
        {
            "strategy.trend_following.ema_fast_period": 2,
            "strategy.trend_following.ema_slow_period": 6,
        },
        {
            "strategy.trend_following.ema_fast_period": 3,
            "strategy.trend_following.ema_slow_period": 4,
        },
        {
            "strategy.trend_following.ema_fast_period": 3,
            "strategy.trend_following.ema_slow_period": 6,
        },
    ]
    assert grid[0][1]["strategy"]["trend_following"]["ema_fast_period"] == 2


def test_parameter_grid_respects_max_run_guardrail() -> None:
    config_data = {
        "research": {
            "sweep": {
                "max_runs": 1,
                "parameters": {"a.b": [1, 2]},
            }
        },
    }

    with pytest.raises(ValueError, match="max_runs=1"):
        build_parameter_grid(config_data)


def test_provenance_degrades_when_git_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(subprocess, "run", _raise)
    spec = BacktestSpec(
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 1, 2, tzinfo=timezone.utc),
        timeframe="1Min",
    )
    config = _config()

    provenance = build_run_provenance(
        config_data={"strategy": {"id": "demo"}},
        config=config,
        spec=spec,
        strategy_info=StrategyInfo(strategy_id="demo", name="Demo"),
        risk_config={},
        assumptions=BacktestAssumptions(),
        parameters={},
        data_quality=None,
    )

    assert provenance["git"] == {"sha": None, "dirty": None}
    assert provenance["warnings"] == ["No data quality report attached to this research run."]
    assert config_snapshot_hash({"b": 2, "a": 1}) == config_snapshot_hash({"a": 1, "b": 2})


def test_result_summary_and_export_bundle(tmp_path: Path) -> None:
    result = attach_research_metadata(
        _sample_result(),
        experiment_id="exp_demo",
        experiment_run_id="exp_run_1",
        provenance={"config_hash": "abc"},
    )

    bundle = export_research_bundle(result, output_dir=tmp_path / "bundle", provenance={"config_hash": "abc"})

    assert result_summary(result)["total_return"] == 0.00959
    assert (bundle / "result.json").exists()
    assert (bundle / "provenance.json").exists()
    assert (bundle / "metrics.json").exists()
    assert (bundle / "equity_curve.csv").exists()
    assert (bundle / "benchmark_curve.csv").exists()
    assert (bundle / "positions.csv").exists()
    assert (bundle / "trades.csv").exists()


def test_comparison_payload_warns_on_mismatched_assumptions() -> None:
    rows = [
        {
            "experiment_run_id": "one",
            "run_id": "run_1",
            "status": "success",
            "strategy_id": "demo",
            "assumptions": {"slippage": 0},
            "symbols": ["DEMO"],
            "timeframe": "1Min",
            "asset_class": "stocks",
            "start_ts": "2026-01-01",
            "end_ts": "2026-01-02",
            "result_summary": {"total_return": 0.1, "sharpe": 1.0},
        },
        {
            "experiment_run_id": "two",
            "run_id": "run_2",
            "status": "success",
            "strategy_id": "demo",
            "assumptions": {"slippage": 10},
            "symbols": ["DEMO"],
            "timeframe": "1Min",
            "asset_class": "stocks",
            "start_ts": "2026-01-01",
            "end_ts": "2026-01-02",
            "result_summary": {"total_return": 0.2, "sharpe": 2.0},
        },
    ]

    payload = comparison_payload(rows)

    assert payload["rows"][0]["total_return"] == 0.1
    assert payload["warnings"] == ["Compared runs differ in assumptions."]


def _config() -> Config:
    return Config(
        mode="backtest",
        strategy_type="demo",
        strategy_id="demo",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=4,
        db_path="",
        event_store="noop",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("DEMO",),
        market_data_max_age_seconds=60,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="",
        alpaca_base_url="",
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
        broker_type="internal",
    )
