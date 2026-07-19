"""Evaluation-owned untouched-holdout reports for parameter optimization."""

from __future__ import annotations

from trader_research.governance.artifacts import EVALUATION_AGENT_OWNER

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import SCHEMA_VERSION

from typing import Any, Mapping

from trader_research.foundation.artifacts import ResearchArtifactStore, ResearchArtifactStoreError
from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import (
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
)
from trader_research.experiments.reads import StoreBackedExperimentEvidenceReader


EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT = "evaluation_generate_parameter_optimization_report"


def generate_parameter_optimization_report(
    *,
    optimization_run_ref: str,
    holdout_backtest_run_ref: str,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Evaluate only the sealed holdout run for an optimization-derived selection."""
    command = EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT
    if artifact_store is None:
        return _error("research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        evidence_reader = StoreBackedExperimentEvidenceReader(artifact_store)
        optimization, _ = evidence_reader.load_parameter_optimization_run(
            optimization_run_ref
        )
        holdout = evidence_reader.load_backtest_run(holdout_backtest_run_ref)
        blockers = _holdout_blockers(optimization, holdout)
        status = "passed" if not blockers else "blocked"
        identity = {
            "optimization_run_id": optimization["optimization_run_id"],
            "holdout_backtest_run_id": holdout["run_id"],
            "selected_trial_id": optimization.get("selected_trial_id"),
            "blockers": blockers,
        }
        report_id = stable_research_id("parameter_optimization_evaluation", identity)
        report = {
            "artifact_type": PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
            "schema_version": SCHEMA_VERSION,
            "report_id": report_id,
            **identity,
            "status": status,
            "valid": not blockers,
            "search_disclosure": {
                "engine_profile": optimization.get("engine_profile"),
                "trial_count": optimization.get("trial_count"),
                "passed_trial_count": optimization.get("passed_trial_count"),
                "selected_parameters": optimization.get("selected_parameters"),
                "selected_objective_value": optimization.get("selected_objective_value"),
            },
            "holdout_performance": dict(holdout.get("summary") or {}),
            "holdout_exposure": dict((holdout.get("bundle") or {}).get("exposure_summary") or {}),
            "holdout_risk": {
                "decisions": dict((holdout.get("bundle") or {}).get("risk_decisions") or {}),
                "breaches": dict((holdout.get("bundle") or {}).get("risk_limit_breaches") or {}),
                "measures": dict((holdout.get("bundle") or {}).get("risk_measure_summary") or {}),
            },
            "warnings": list(holdout.get("warnings") or []),
        }
        record = artifact_store.save_artifact(
            agent_owner=EVALUATION_AGENT_OWNER,
            artifact_type=PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
            artifact_id=report_id,
            payload=report,
            status=status,
            metadata={"optimization_run_id": optimization["optimization_run_id"], "holdout_run_id": holdout["run_id"]},
        )
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error("parameter_optimization_evaluation_failed", str(exc))
    result = success_result(
        command=command,
        data={"parameter_optimization_evaluation_report": report},
        artifacts={"parameter_optimization_evaluation_report": record.reference().to_dict()},
    )
    if status == "passed":
        return result
    return ApplicationResult(
        ok=False,
        operation=command,
        data=result.data,
        artifacts=result.artifacts,
        errors=({"code": "parameter_optimization_evaluation_blocked", "message": blockers[0]},),
    )


def _holdout_blockers(optimization: Mapping[str, Any], holdout: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if optimization.get("status") != "completed" or not optimization.get("selected_trial_id"):
        blockers.append("optimization run must be completed with a selected trial")
    if holdout.get("status") != "passed" or holdout.get("blockers"):
        blockers.append("holdout backtest must be passed and blocker-free")
    if holdout.get("selection_origin_ref") != optimization.get("optimization_run_id"):
        blockers.append("holdout backtest selection_origin_ref does not match optimization run")
    if holdout.get("dataset_hash") != (optimization.get("holdout_dataset") or {}).get("sha256"):
        blockers.append("holdout backtest dataset does not match the sealed plan holdout")
    selected_strategy_id = (optimization.get("selected_child_refs") or {}).get("strategy_specification_id")
    if holdout.get("strategy_specification_id") != selected_strategy_id:
        blockers.append("holdout backtest does not use the selected strategy specification")
    missing = ((holdout.get("bundle") or {}).get("risk_measure_summary") or {}).get("missing_required_telemetry") or []
    if missing:
        blockers.append(f"holdout risk evidence is missing required telemetry: {sorted(missing)}")
    return blockers


def _error(code: str, message: str) -> ApplicationResult:
    return error_result(
        command=EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT,
        code=code,
        message=message,
    )
