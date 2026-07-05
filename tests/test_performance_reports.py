from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.test_research_backtests import _run_successful_backtest, _sample_store_and_reports, _update_metrics, _update_run_ref
from trader_research.domain import EVALUATION_REPORT
from trader_research.evaluation import EVALUATION_GENERATE_PERFORMANCE_REPORT, generate_performance_report


def test_generate_performance_report_writes_passed_report(tmp_path: Path) -> None:
    run_payload, quality_report = _run_with_trade_evidence(tmp_path)
    run_ref = run_payload["data"]["backtest_run_ref"]

    payload = generate_performance_report(
        artifact_root=tmp_path,
        backtest_run_ref=run_ref,
        data_quality_report=quality_report,
    ).to_dict()

    assert payload["ok"] is True
    assert payload["command"] == EVALUATION_GENERATE_PERFORMANCE_REPORT
    assert payload["agent_owner"] == "Evaluation Agent"
    report = payload["data"]["evaluation_report"]
    assert report["artifact_type"] == EVALUATION_REPORT
    assert report["report_kind"] == "performance_report"
    assert report["status"] == "passed"
    assert report["run_id"] == run_ref["run_id"]
    assert report["candidate_id"] == run_ref["candidate_id"]
    assert report["validation_id"] == run_ref["validation_id"]
    assert report["dataset_id"] == run_ref["dataset_id"]
    assert report["data_scope"] == run_ref["data_scope"]
    assert report["core_metrics"]["total_return"] == 0.01
    assert report["core_metrics"]["sharpe"] == 1.25
    assert report["core_metrics"]["max_drawdown"] == 0.02
    assert report["trade_stats"]["trade_count"] == 1
    assert report["trade_stats"]["hit_rate"] == 1.0
    assert report["costs"]["realized_fees"] == 0.1
    assert report["costs"]["realized_slippage"] == 0.2
    assert report["benchmark"]["benchmark_total_return"] == 0.005
    assert report["benchmark"]["information_ratio"] == 0.5
    assert report["data_quality"]["complete"] is True
    assert report["blockers"] == []
    report_path = Path(payload["artifacts"]["evaluation_report"]["path"])
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_generate_performance_report_resolves_refs_and_is_deterministic(tmp_path: Path) -> None:
    run_payload, quality_report = _run_with_trade_evidence(tmp_path)
    run_ref = run_payload["data"]["backtest_run_ref"]

    by_id = generate_performance_report(
        artifact_root=tmp_path,
        run_id=run_ref["run_id"],
        data_quality_report=quality_report,
    ).to_dict()
    by_dir = generate_performance_report(
        artifact_root=tmp_path,
        artifact_dir=run_ref["artifact_dir"],
        data_quality_report_ref={"data_quality_report": quality_report},
    ).to_dict()
    quality_path = tmp_path / "quality.json"
    quality_path.write_text(json.dumps(quality_report, indent=2, sort_keys=True), encoding="utf-8")
    by_ref = generate_performance_report(
        artifact_root=tmp_path,
        backtest_run_ref=run_ref,
        data_quality_report_path=quality_path,
    ).to_dict()

    assert by_id["ok"] is True
    assert by_dir["ok"] is True
    assert by_ref["ok"] is True
    assert by_id["data"]["evaluation_report"]["report_id"] == by_dir["data"]["evaluation_report"]["report_id"]
    assert by_id["data"]["evaluation_report"]["report_id"] == by_ref["data"]["evaluation_report"]["report_id"]


@pytest.mark.parametrize(
    ("quality_mutator", "expected_code"),
    [
        (lambda _quality: None, "missing_data_quality_report"),
        (lambda quality: {**quality, "complete": False}, "incomplete_data_quality"),
        (lambda quality: {**quality, "symbols": ["OTHER"]}, "data_quality_symbol_mismatch"),
    ],
)
def test_generate_performance_report_blocks_for_data_quality_issues(
    tmp_path: Path,
    quality_mutator: Any,
    expected_code: str,
) -> None:
    run_payload, quality_report = _run_with_trade_evidence(tmp_path)
    run_ref = run_payload["data"]["backtest_run_ref"]
    mutated_quality = quality_mutator(quality_report)

    payload = generate_performance_report(
        artifact_root=tmp_path,
        backtest_run_ref=run_ref,
        data_quality_report=mutated_quality,
    ).to_dict()

    assert payload["ok"] is True
    report = payload["data"]["evaluation_report"]
    assert report["status"] == "blocked"
    assert expected_code in {blocker["code"] for blocker in report["blockers"]}


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda run_ref: _update_metrics(run_ref, failed_runs=1), "failed_backtest_runs"),
        (
            lambda run_ref: _update_run_ref(
                run_ref,
                blockers=[{"code": "runtime_blocker", "message": "Synthetic blocker."}],
            ),
            "backtest_blocker",
        ),
        (lambda _run_ref: None, "zero_trades"),
    ],
)
def test_generate_performance_report_blocks_for_backtest_evidence_issues(
    tmp_path: Path,
    mutator: Any,
    expected_code: str,
) -> None:
    run_payload = _run_successful_backtest(tmp_path)
    _store, _manifest, quality_report = _sample_store_and_reports(tmp_path / "quality")
    run_ref = run_payload["data"]["backtest_run_ref"]
    mutator(run_ref)

    payload = generate_performance_report(
        artifact_root=tmp_path,
        artifact_dir=run_ref["artifact_dir"],
        data_quality_report=quality_report,
    ).to_dict()

    assert payload["ok"] is True
    report = payload["data"]["evaluation_report"]
    assert report["status"] == "blocked"
    assert expected_code in {blocker["code"] for blocker in report["blockers"]}


@pytest.mark.parametrize(
    ("mutator", "expected_message"),
    [
        (lambda _run_ref: None, "exactly one of run_id, artifact_dir, or backtest_run_ref is required"),
        (lambda run_ref: Path(run_ref["artifact_paths"]["metrics"]).unlink(), "metrics.json not found"),
        (lambda run_ref: Path(run_ref["artifact_paths"]["result"]).unlink(), "result.json not found"),
        (lambda run_ref: _update_run_ref(run_ref, artifact_type="wrong_type"), "artifact_type must be backtest_run_ref"),
        (lambda run_ref: Path(run_ref["artifact_paths"]["result"]).write_text("{bad", encoding="utf-8"), "Expecting property name"),
    ],
)
def test_generate_performance_report_fails_closed_for_invalid_bundle(
    tmp_path: Path,
    mutator: Any,
    expected_message: str,
) -> None:
    run_payload, quality_report = _run_with_trade_evidence(tmp_path)
    run_ref = run_payload["data"]["backtest_run_ref"]
    mutator(run_ref)

    kwargs: dict[str, Any] = (
        {}
        if expected_message.startswith("exactly one")
        else {"artifact_dir": run_ref["artifact_dir"]}
    )
    payload = generate_performance_report(
        artifact_root=tmp_path,
        data_quality_report=quality_report,
        **kwargs,
    ).to_dict()

    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "performance_report_failed"
    assert expected_message in payload["errors"][0]["message"]


def _run_with_trade_evidence(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run_payload = _run_successful_backtest(root)
    _store, _manifest, quality_report = _sample_store_and_reports(root / "quality")
    run_ref = run_payload["data"]["backtest_run_ref"]
    _update_metrics(
        run_ref,
        total_return=0.01,
        sharpe=1.25,
        max_drawdown=0.02,
        turnover=0.3,
        trade_count=1,
        fees=0.1,
        slippage=0.2,
        alpha=0.004,
        beta=0.7,
        failed_runs=0,
    )
    _update_result(
        run_ref,
        strategy_performance={
            "total_return": 0.01,
            "sharpe": 1.25,
            "max_drawdown": 0.02,
            "turnover": 0.3,
            "trade_count": 1,
            "hit_rate": 1.0,
        },
        benchmark_performance={
            "total_return": 0.005,
            "sharpe": 0.8,
            "max_drawdown": 0.01,
        },
        total_fees=0.1,
        total_slippage=0.2,
        tracking_error=0.1,
        information_ratio=0.5,
        alpha=0.004,
        beta=0.7,
        trades=[{"symbol": "DEMO", "side": "buy"}],
    )
    return run_payload, quality_report


def _update_result(run_ref: dict[str, Any], **updates: Any) -> None:
    result_path = Path(run_ref["artifact_paths"]["result"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    for key, value in updates.items():
        if key in {"strategy_performance", "benchmark_performance"}:
            result[key].update(value)
        else:
            result[key] = value
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
