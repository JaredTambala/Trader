from __future__ import annotations

from pathlib import Path

from trader_research.math_tools import math_run_signal_diagnostics


def test_signal_diagnostics_evaluate_declared_signal_candidates(tmp_path: Path) -> None:
    result = math_run_signal_diagnostics(
        artifact_root=tmp_path / "artifacts",
        signal_observations=_signal_observations(),
        forward_return_labels=_forward_return_labels(),
        candidate_family_manifest=_candidate_family(),
        method_contracts=[_rank_ic_contract(1)],
        quantile_count=5,
    )

    assert result.ok is True, result.to_dict()
    report = result.data["signal_diagnostic_report"]
    by_candidate = {item["candidate_id"]: item for item in report["candidate_results"]}
    action_result = by_candidate["action_signal"]["horizon_results"][0]
    score_result = by_candidate["score_signal"]["horizon_results"][0]

    assert report["artifact_type"] == "signal_diagnostic_report"
    assert report["candidate_count"] == 2
    assert result.artifacts["signal_diagnostic_report"]["path"]
    assert action_result["hit_rate"] == 0.75
    assert action_result["quantile_buckets"] == []
    assert "discrete action signal" in action_result["warnings"][0]
    assert score_result["sample_size"] == 5
    assert len(score_result["quantile_buckets"]) == 5
    assert score_result["rank_ic"] == 1.0
    assert score_result["monotonicity_score"] == 1.0
    assert by_candidate["action_signal"]["turnover_proxy"] is not None
    assert report["warnings"] == [
        "candidate action_signal has no executable implementation reference; treating as observational",
        "candidate score_signal has no executable implementation reference; treating as observational",
    ]


def test_signal_diagnostics_fail_without_rank_ic_evidence(tmp_path: Path) -> None:
    result = math_run_signal_diagnostics(
        artifact_root=tmp_path / "artifacts",
        signal_observations=_signal_observations()[:5],
        forward_return_labels=_forward_return_labels()[:5],
        candidate_family_manifest={
            "candidate_family_id": "family_demo",
            "candidates": [{"candidate_id": "action_signal", "signal_name": "Action Signal"}],
            "tested_grid": {"period": [20]},
        },
        method_contracts=[],
    )

    assert result.ok is False
    report = result.data["signal_diagnostic_report"]
    assert "rank_ic method contract is required for horizon 1" in report["blockers"]


def test_signal_diagnostics_fail_on_duplicate_observation_keys(tmp_path: Path) -> None:
    observations = _signal_observations()[:5]
    result = math_run_signal_diagnostics(
        artifact_root=tmp_path / "artifacts",
        signal_observations=[*observations, observations[0]],
        forward_return_labels=_forward_return_labels()[:5],
        candidate_family_manifest={
            "candidate_family_id": "family_demo",
            "candidates": [{"candidate_id": "action_signal", "signal_name": "Action Signal"}],
            "tested_grid": {"period": [20]},
        },
        method_contracts=[_rank_ic_contract(1)],
    )

    assert result.ok is False
    report = result.data["signal_diagnostic_report"]
    assert "duplicate signal observation key: action_signal/AAA/2026-01-01T09:30:00+00:00" in report["blockers"]


def _candidate_family() -> dict[str, object]:
    return {
        "candidate_family_id": "family_demo",
        "candidates": [
            {"candidate_id": "action_signal", "signal_name": "Action Signal", "parameters": {"period": 20}},
            {"candidate_id": "score_signal", "signal_name": "Score Signal", "parameters": {"period": 20}},
        ],
        "tested_grid": {"period": [20], "kind": ["action", "score"]},
    }


def _rank_ic_contract(horizon: int) -> dict[str, object]:
    return {
        "method_id": "rank_ic",
        "parameters": {"horizon": horizon},
        "no_lookahead": True,
        "knowledge_evidence_refs": [{"method_card_id": "method_card_rank_ic_seed_v1"}],
    }


def _signal_observations() -> list[dict[str, object]]:
    times = [f"2026-01-01T09:3{idx}:00+00:00" for idx in range(5)]
    return [
        *[
            {
                "candidate_id": "action_signal",
                "signal_name": "Action Signal",
                "symbol": "AAA",
                "ts": ts,
                "value": value,
                "session": "regular",
                "regime": "trend",
            }
            for ts, value in zip(times, [1.0, -1.0, 0.0, 1.0, -1.0], strict=False)
        ],
        *[
            {
                "candidate_id": "score_signal",
                "signal_name": "Score Signal",
                "symbol": "BBB",
                "ts": ts,
                "value": value,
                "session": "regular",
                "regime": "trend",
            }
            for ts, value in zip(times, [0.1, 0.2, 0.3, 0.4, 0.5], strict=False)
        ],
    ]


def _forward_return_labels() -> list[dict[str, object]]:
    times = [f"2026-01-01T09:3{idx}:00+00:00" for idx in range(5)]
    return [
        *[
            {"symbol": "AAA", "ts": ts, "horizon": 1, "forward_return": value}
            for ts, value in zip(times, [0.01, -0.02, 0.03, 0.04, 0.05], strict=False)
        ],
        *[
            {"symbol": "BBB", "ts": ts, "horizon": 1, "forward_return": value}
            for ts, value in zip(times, [0.01, 0.02, 0.03, 0.04, 0.05], strict=False)
        ],
    ]
