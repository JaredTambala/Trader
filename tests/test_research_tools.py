from __future__ import annotations

import json
from pathlib import Path

import pytest

from trader.tools.artifacts import load_strategy_artifacts
from trader.tools.discovery import DiscoveryRequest, run_discovery
from trader.tools.promotion import build_promotion_packet
from trader.tools.recommendations import RecommendationSettings, build_recommendations
from trader.tools.suites import build_suite_members


def test_suite_expansion_is_deterministic_and_guarded() -> None:
    config_data = {
        "strategy": {"id": "trend_following"},
        "market_data": {"symbols": ["DEMO"], "asset_class": "stocks"},
        "backtest": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        "research": {
            "suite": {
                "strategies": [
                    {
                        "id": "trend_following",
                        "parameters": {
                            "strategy.trend_following.ema_slow_period": [4, 6],
                            "strategy.trend_following.ema_fast_period": [2, 3],
                        },
                    }
                ]
            }
        },
    }

    members = build_suite_members(
        config_data,
        strategy_families=("trend_following",),
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        max_runs=4,
    )

    assert [dict(member.parameters) for member in members] == [
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
    assert members[0].suite_id == build_suite_members(
        config_data,
        strategy_families=("trend_following",),
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        max_runs=4,
    )[0].suite_id
    with pytest.raises(ValueError, match="max_runs=3"):
        build_suite_members(
            config_data,
            strategy_families=("trend_following",),
            symbols=("DEMO",),
            asset_class="stocks",
            timeframe="1Min",
            max_runs=3,
        )


def test_discovery_plan_rejects_oversized_symbol_universe() -> None:
    request = DiscoveryRequest(
        symbols=tuple(f"SYM{index}" for index in range(21)),
        asset_class="stocks",
        timeframe="1Min",
        strategy_families=("trend_following",),
        data_mode="plan",
    )

    with pytest.raises(ValueError, match="at most 20 symbols"):
        run_discovery({}, request)


def test_recommendations_apply_conservative_gates() -> None:
    comparison = {
        "rows": [
            {
                "run_id": "run_good",
                "experiment_run_id": "exp_run_good",
                "status": "success",
                "strategy_id": "trend_following",
                "strategy_name": "Trend Following",
                "strategy_version": "1",
                "total_return": 0.12,
                "sharpe": 1.5,
                "max_drawdown": 0.05,
                "turnover": 2.0,
                "fees": 1.0,
                "slippage": 1.0,
                "warnings_count": 0,
                "trade_count": 4,
                "artifact_dir": "artifacts/research/good",
            },
            {
                "run_id": "run_bad",
                "experiment_run_id": "exp_run_bad",
                "status": "success",
                "strategy_id": "mean_reversion",
                "total_return": 0.2,
                "sharpe": 2.0,
                "max_drawdown": 0.25,
                "turnover": 12.0,
                "warnings_count": 3,
                "trade_count": 2,
            },
        ]
    }
    data_quality = {
        "report_id": "dq_ok",
        "summaries": [{"symbol": "DEMO", "missing_gaps": 0}],
    }

    result = build_recommendations(
        comparison,
        experiment_name="demo",
        data_quality=data_quality,
        settings=RecommendationSettings(),
    )

    assert len(result.payload["accepted_candidates"]) == 1
    assert result.payload["accepted_candidates"][0]["run_id"] == "run_good"
    rejected = result.payload["rejected_candidates"][0]
    assert {"excessive_drawdown", "excessive_turnover", "too_many_warnings", "insufficient_trade_count"}.issubset(
        set(rejected["reasons"])
    )


def test_operator_context_blocks_promotion_readiness_not_ranking() -> None:
    comparison = {
        "rows": [
            {
                "run_id": "run_good",
                "experiment_run_id": "exp_run_good",
                "status": "success",
                "strategy_id": "trend_following",
                "total_return": 0.05,
                "sharpe": 1.0,
                "max_drawdown": 0.02,
                "turnover": 1.0,
                "warnings_count": 0,
                "trade_count": 5,
            }
        ]
    }

    result = build_recommendations(
        comparison,
        experiment_name="demo",
        data_quality={"report_id": "dq_ok", "summaries": [{"symbol": "DEMO", "missing_gaps": 0}]},
        operator_contexts=({"halt": {"halted": True}},),
    )

    candidate = result.payload["accepted_candidates"][0]
    assert candidate["promotion_ready"] is False
    assert candidate["operator_reasons"] == ["operator_halted"]


def test_artifact_loader_warns_for_optional_missing_files(tmp_path: Path) -> None:
    existing = tmp_path / "metrics.json"
    existing.write_text(json.dumps({"total_return": 0.1}), encoding="utf-8")

    loaded = load_strategy_artifacts((existing, tmp_path / "missing.json"))

    assert loaded.artifacts["metrics"]["total_return"] == 0.1
    assert loaded.warnings == (f"Artifact missing: {tmp_path / 'missing.json'}",)


def test_promotion_packet_is_dry_run_and_links_source(tmp_path: Path) -> None:
    recommendation_payload = {
        "experiment_name": "demo",
        "accepted_candidates": [
            {
                "recommendation_id": "rec_good",
                "promotion_ready": True,
                "run_id": "run_good",
                "experiment_run_id": "exp_run_good",
                "strategy_id": "trend_following",
                "strategy_name": "Trend Following",
                "strategy_version": "1",
                "artifact_dir": "artifacts/research/good",
            }
        ],
        "rejected_candidates": [],
    }

    packet = build_promotion_packet(
        base_config_data={"broker": {"type": "alpaca"}, "strategy": {"id": "trend_following"}},
        recommendation_payload=recommendation_payload,
        recommendation_id="rec_good",
        output_root=tmp_path / "promotions",
    )

    validation = json.loads(Path(packet["dry_run_validation"]).read_text(encoding="utf-8"))
    assert packet["promotion_ready"] is True
    assert validation["starts_trading"] is False
    assert Path(packet["promotion_packet"]).exists()
