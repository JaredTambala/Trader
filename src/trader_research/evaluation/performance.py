"""Evaluation Agent performance reports over persisted backtest bundles."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

from trader_research.contracts import (
    ArtifactReference,
    SCHEMA_VERSION,
    SideEffect,
    ToolEnvelope,
    error_envelope,
    success_envelope,
    write_json_artifact,
)
from trader_research.domain import (
    BACKTEST_RUN_REF,
    DATA_QUALITY_REPORT,
    EVALUATION_REPORT,
    PORTFOLIO_BACKTEST_RUN_REF,
    ResearchIssue,
    stable_research_id,
)
from trader_research.artifact_store import (
    ResearchArtifactNotFound,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    ResearchArtifactRecord,
    parse_research_artifact_uri,
)


EVALUATION_GENERATE_PERFORMANCE_REPORT = "evaluation_generate_performance_report"
PERFORMANCE_REPORT_KIND = "performance_report"


def generate_performance_report(
    *,
    artifact_root: str | Path,
    run_id: str | None = None,
    artifact_dir: str | Path | None = None,
    backtest_run_ref: Mapping[str, Any] | None = None,
    portfolio_backtest_run_ref: Mapping[str, Any] | None = None,
    data_quality_report: Mapping[str, Any] | None = None,
    data_quality_report_path: str | Path | None = None,
    data_quality_report_ref: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Write an Evaluation-owned performance report for one backtest bundle.

    Args:
        artifact_root: Fallback root directory for filesystem research artifacts.
        run_id: Optional persisted backtest run ID.
        artifact_dir: Optional baseline or portfolio run artifact directory.
        backtest_run_ref: Optional inline `backtest_run_ref` payload.
        portfolio_backtest_run_ref: Optional inline `portfolio_backtest_run_ref` payload.
        data_quality_report: Optional inline Data Agent quality report.
        data_quality_report_path: Optional path to a quality report.
        data_quality_report_ref: Optional artifact reference containing a path
            or inline quality-report payload.

    Returns:
        Local-mutating envelope containing `evaluation_report`. Resolved backtest
        bundles produce a report even when report-level blockers are present.
    """
    try:
        bundle = _resolve_bundle(
            artifact_root=artifact_root,
            run_id=run_id,
            artifact_dir=artifact_dir,
            backtest_run_ref=backtest_run_ref,
            portfolio_backtest_run_ref=portfolio_backtest_run_ref,
            artifact_store=artifact_store,
        )
        quality_report, quality_source = _resolve_quality_report(
            data_quality_report=data_quality_report,
            data_quality_report_path=data_quality_report_path,
            data_quality_report_ref=data_quality_report_ref,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError, ResearchArtifactStoreError) as exc:
        return error_envelope(
            command=EVALUATION_GENERATE_PERFORMANCE_REPORT,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="performance_report_failed",
            message=str(exc),
        )

    blockers = _bundle_blockers(bundle)
    warnings = _bundle_warnings(bundle)
    caveats = _bundle_caveats(bundle)
    blockers.extend(_portfolio_risk_evidence_blockers(bundle))
    quality_summary, quality_blockers, quality_warnings = _quality_evaluation(
        quality_report=quality_report,
        quality_source=quality_source,
        data_scope=_mapping(bundle.run_ref.get("data_scope")),
    )
    blockers.extend(quality_blockers)
    warnings.extend(quality_warnings)
    caveats.extend(_quality_caveats(quality_summary))

    core_metrics = _core_metrics(bundle.metrics, bundle.result)
    trade_stats = _trade_stats(bundle.metrics, bundle.result, bundle.trades_path)
    benchmark = _benchmark_metrics(bundle.metrics, bundle.result)
    costs = _cost_summary(bundle.metrics, bundle.result)
    caveats.extend(_metric_caveats(core_metrics, trade_stats, costs, benchmark))
    blockers.extend(_metric_blockers(bundle.metrics, trade_stats))
    candidate_id = _first(bundle.run_ref.get("candidate_id"), bundle.provenance.get("candidate_id"))
    validation_id = _first(bundle.run_ref.get("validation_id"), bundle.provenance.get("validation_id"))

    report_id = stable_research_id(
        "evaluation_performance_report",
        {
            "run_id": bundle.run_id,
            "backtest_kind": bundle.backtest_kind,
            "metrics": bundle.metrics,
            "result_summary": {
                "total_runs": bundle.result.get("total_runs"),
                "success_runs": bundle.result.get("success_runs"),
                "failed_runs": bundle.result.get("failed_runs"),
                "strategy_performance": bundle.result.get("strategy_performance"),
                "benchmark_performance": bundle.result.get("benchmark_performance"),
                "tracking_error": bundle.result.get("tracking_error"),
                "information_ratio": bundle.result.get("information_ratio"),
                "alpha": bundle.result.get("alpha"),
                "beta": bundle.result.get("beta"),
                "total_fees": bundle.result.get("total_fees"),
                "total_slippage": bundle.result.get("total_slippage"),
            },
            "data_scope": bundle.run_ref.get("data_scope"),
            "data_quality": _quality_identity(quality_summary),
            "portfolio_risk": {
                "symbol_metrics": bundle.symbol_metrics,
                "exposure_summary": bundle.exposure_summary,
                "risk_decisions": _risk_decision_identity(bundle.risk_decisions),
                "risk_limit_breaches": bundle.risk_limit_breaches,
                "risk_measure_summary": bundle.risk_measure_summary,
            },
        },
    )
    report = {
        "artifact_type": EVALUATION_REPORT,
        "report_kind": PERFORMANCE_REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id,
        "status": "blocked" if blockers else "passed",
        "backtest_kind": bundle.backtest_kind,
        "run_id": bundle.run_id,
        "candidate_id": candidate_id,
        "validation_id": validation_id,
        "strategy_risk_stack_id": bundle.run_ref.get("strategy_risk_stack_id"),
        "strategy_risk_stack_validation_id": bundle.run_ref.get("strategy_risk_stack_validation_id"),
        "dataset_id": bundle.run_ref.get("dataset_id"),
        "data_scope": _jsonable(bundle.run_ref.get("data_scope")),
        "core_metrics": core_metrics,
        "trade_stats": trade_stats,
        "costs": costs,
        "benchmark": benchmark,
        "symbol_metrics": _jsonable(bundle.symbol_metrics),
        "exposure_summary": _jsonable(bundle.exposure_summary),
        "risk_decisions": _jsonable(bundle.risk_decisions),
        "risk_limit_breaches": _jsonable(bundle.risk_limit_breaches),
        "risk_measure_summary": _jsonable(bundle.risk_measure_summary),
        "data_quality": quality_summary,
        "artifact_paths": bundle.artifact_paths,
        "caveats": _dedupe_text(caveats),
        "warnings": [issue.to_dict() for issue in _dedupe_issues(warnings)],
        "blockers": [issue.to_dict() for issue in _dedupe_issues(blockers)],
    }
    if artifact_store is None:
        report_path = write_json_artifact(
            report,
            Path(artifact_root) / "evaluation" / "performance_reports" / f"{report_id}.json",
        )
        report_artifact = ArtifactReference(
            artifact_type=EVALUATION_REPORT,
            path=report_path,
            metadata={"id": report_id, "run_id": bundle.run_id, "status": report["status"]},
        )
    else:
        try:
            record = artifact_store.save_artifact(
                artifact_type=EVALUATION_REPORT,
                artifact_id=report_id,
                payload=report,
                status=str(report["status"]),
                metadata={"run_id": bundle.run_id, "backtest_kind": bundle.backtest_kind},
            )
        except ResearchArtifactStoreError as exc:
            return error_envelope(
                command=EVALUATION_GENERATE_PERFORMANCE_REPORT,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="performance_report_failed",
                message=str(exc),
            )
        report_artifact = record.reference()
    return success_envelope(
        command=EVALUATION_GENERATE_PERFORMANCE_REPORT,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"evaluation_report": report},
        artifacts={"evaluation_report": report_artifact.to_dict()},
        warnings=tuple(issue["message"] for issue in report["warnings"]),
    )


@dataclass(frozen=True)
class _BacktestBundle:
    """Loaded task-28 artifact bundle used by performance reports."""

    bundle_dir: Path
    backtest_kind: str
    run_ref: Mapping[str, Any]
    metrics: Mapping[str, Any]
    result: Mapping[str, Any]
    provenance: Mapping[str, Any]
    artifact_paths: Mapping[str, Any]
    trades_path: Path | None
    run_id: str
    symbol_metrics: Mapping[str, Any] | None = None
    exposure_summary: Mapping[str, Any] | None = None
    risk_decisions: Mapping[str, Any] | None = None
    risk_limit_breaches: Mapping[str, Any] | None = None
    risk_measure_summary: Mapping[str, Any] | None = None


def _resolve_bundle(
    *,
    artifact_root: str | Path,
    run_id: str | None,
    artifact_dir: str | Path | None,
    backtest_run_ref: Mapping[str, Any] | None,
    portfolio_backtest_run_ref: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore | None,
) -> _BacktestBundle:
    _validate_single_bundle_source(
        run_id=run_id,
        artifact_dir=artifact_dir,
        backtest_run_ref=backtest_run_ref,
        portfolio_backtest_run_ref=portfolio_backtest_run_ref,
    )
    if artifact_store is not None:
        db_bundle = _resolve_db_bundle(
            run_id=run_id,
            backtest_run_ref=backtest_run_ref,
            portfolio_backtest_run_ref=portfolio_backtest_run_ref,
            artifact_store=artifact_store,
        )
        if db_bundle is not None:
            return db_bundle
    bundle_dir = _resolve_bundle_dir(
        artifact_root=artifact_root,
        run_id=run_id,
        artifact_dir=artifact_dir,
        backtest_run_ref=backtest_run_ref,
        portfolio_backtest_run_ref=portfolio_backtest_run_ref,
    )
    return _load_bundle(bundle_dir)


def _validate_single_bundle_source(
    *,
    run_id: str | None,
    artifact_dir: str | Path | None,
    backtest_run_ref: Mapping[str, Any] | None,
    portfolio_backtest_run_ref: Mapping[str, Any] | None,
) -> None:
    sources = [
        bool(run_id and run_id.strip()),
        artifact_dir is not None and str(artifact_dir).strip() != "",
        backtest_run_ref is not None,
        portfolio_backtest_run_ref is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError(
            "exactly one of run_id, artifact_dir, backtest_run_ref, or portfolio_backtest_run_ref is required"
        )


def _resolve_db_bundle(
    *,
    run_id: str | None,
    backtest_run_ref: Mapping[str, Any] | None,
    portfolio_backtest_run_ref: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore,
) -> _BacktestBundle | None:
    if run_id and run_id.strip():
        run = run_id.strip()
        baseline = _load_optional_artifact_record(artifact_store, BACKTEST_RUN_REF, run)
        portfolio = _load_optional_artifact_record(artifact_store, PORTFOLIO_BACKTEST_RUN_REF, run)
        matches = [record for record in (baseline, portfolio) if record is not None]
        if len(matches) > 1:
            raise ValueError(f"ambiguous run_id resolves to baseline and portfolio bundles: {run}")
        return _load_db_bundle(matches[0]) if matches else None
    if backtest_run_ref is not None:
        record = _record_from_run_ref(artifact_store, BACKTEST_RUN_REF, backtest_run_ref)
        return _load_db_bundle(record) if record is not None else None
    if portfolio_backtest_run_ref is not None:
        record = _record_from_run_ref(artifact_store, PORTFOLIO_BACKTEST_RUN_REF, portfolio_backtest_run_ref)
        return _load_db_bundle(record) if record is not None else None
    return None


def _load_optional_artifact_record(
    artifact_store: ResearchArtifactStore,
    artifact_type: str,
    artifact_id: str,
) -> ResearchArtifactRecord | None:
    try:
        return artifact_store.load_artifact_record(artifact_type, artifact_id)
    except ResearchArtifactNotFound:
        return None


def _record_from_run_ref(
    artifact_store: ResearchArtifactStore,
    expected_type: str,
    run_ref: Mapping[str, Any],
) -> ResearchArtifactRecord | None:
    if not isinstance(run_ref, MappingABC):
        raise ValueError("run ref must be a mapping")
    uri = str(run_ref.get("uri") or "").strip()
    if uri:
        artifact_type, artifact_id = parse_research_artifact_uri(uri)
        if artifact_type != expected_type:
            raise ValueError(f"run ref URI artifact_type must be {expected_type}")
        return artifact_store.load_artifact_record(artifact_type, artifact_id)
    run_id = str(run_ref.get("run_id") or _mapping(run_ref.get("metadata")).get("id") or "").strip()
    if not run_id:
        if isinstance(run_ref.get("bundle"), MappingABC):
            return None
        raise ValueError("run ref requires uri or run_id")
    try:
        return artifact_store.load_artifact_record(expected_type, run_id)
    except ResearchArtifactNotFound:
        return None


def _load_db_bundle(record: ResearchArtifactRecord | None) -> _BacktestBundle | None:
    if record is None:
        return None
    payload = dict(record.payload)
    bundle = payload.get("bundle")
    if not isinstance(bundle, MappingABC):
        return None
    backtest_kind = str(bundle.get("backtest_kind") or "").strip().lower()
    if not backtest_kind:
        backtest_kind = "portfolio" if record.artifact_type == PORTFOLIO_BACKTEST_RUN_REF else "baseline"
    if backtest_kind == "portfolio":
        run_ref = _mapping(bundle.get("portfolio_backtest_run_ref")) or payload
        expected_artifact_type = PORTFOLIO_BACKTEST_RUN_REF
        ref_key = "portfolio_backtest_run_ref"
    else:
        run_ref = _mapping(bundle.get("backtest_run_ref")) or payload
        expected_artifact_type = BACKTEST_RUN_REF
        ref_key = "backtest_run_ref"
    if record.artifact_type != expected_artifact_type:
        raise ValueError(f"stored bundle artifact_type must be {expected_artifact_type}")
    if run_ref.get("artifact_type") != expected_artifact_type:
        raise ValueError(f"run ref artifact_type must be {expected_artifact_type}")
    metrics = _mapping(bundle.get("metrics"))
    result = _mapping(bundle.get("result"))
    run_id = str(run_ref.get("run_id") or metrics.get("run_id") or result.get("run_id") or record.artifact_id).strip()
    if not run_id:
        raise ValueError("backtest run ref run_id is required")
    artifact_paths = dict(_mapping(run_ref.get("artifact_paths")))
    artifact_uris = dict(_mapping(run_ref.get("artifact_uris")))
    artifact_uris.setdefault(ref_key, record.uri)
    artifact_paths["artifact_uris"] = artifact_uris
    return _BacktestBundle(
        bundle_dir=Path("research_artifact_store") / backtest_kind / run_id,
        backtest_kind=backtest_kind,
        run_ref=run_ref,
        metrics=metrics,
        result=result,
        provenance=_mapping(bundle.get("provenance")),
        artifact_paths=artifact_paths,
        trades_path=None,
        run_id=run_id,
        symbol_metrics=_mapping_or_none(bundle.get("symbol_metrics")),
        exposure_summary=_mapping_or_none(bundle.get("exposure_summary")),
        risk_decisions=_mapping_or_none(bundle.get("risk_decisions")),
        risk_limit_breaches=_mapping_or_none(bundle.get("risk_limit_breaches")),
        risk_measure_summary=_mapping_or_none(bundle.get("risk_measure_summary")),
    )


def _resolve_bundle_dir(
    *,
    artifact_root: str | Path,
    run_id: str | None,
    artifact_dir: str | Path | None,
    backtest_run_ref: Mapping[str, Any] | None,
    portfolio_backtest_run_ref: Mapping[str, Any] | None,
) -> Path:
    _validate_single_bundle_source(
        run_id=run_id,
        artifact_dir=artifact_dir,
        backtest_run_ref=backtest_run_ref,
        portfolio_backtest_run_ref=portfolio_backtest_run_ref,
    )
    if run_id:
        run = run_id.strip()
        baseline_dir = Path(artifact_root) / "backtests" / "runs" / run
        portfolio_dir = Path(artifact_root) / "portfolio_backtests" / "runs" / run
        existing = [path for path in (baseline_dir, portfolio_dir) if path.exists()]
        if len(existing) > 1:
            raise ValueError(f"ambiguous run_id resolves to baseline and portfolio bundles: {run}")
        return existing[0] if existing else baseline_dir
    if artifact_dir is not None:
        return Path(str(artifact_dir))
    if not isinstance(backtest_run_ref, MappingABC):
        if portfolio_backtest_run_ref is None:
            raise ValueError("backtest_run_ref must be a mapping")
    ref_payload = backtest_run_ref if backtest_run_ref is not None else portfolio_backtest_run_ref
    if not isinstance(ref_payload, MappingABC):
        raise ValueError("portfolio_backtest_run_ref must be a mapping")
    ref_dir = ref_payload.get("artifact_dir")
    if ref_dir is None or str(ref_dir).strip() == "":
        raise ValueError("run ref artifact_dir is required")
    return Path(str(ref_dir))


def _load_bundle(bundle_dir: Path) -> _BacktestBundle:
    baseline_ref_path = bundle_dir / "backtest_run_ref.json"
    portfolio_ref_path = bundle_dir / "portfolio_backtest_run_ref.json"
    metrics_path = bundle_dir / "metrics.json"
    result_path = bundle_dir / "result.json"
    provenance_path = bundle_dir / "provenance.json"
    if baseline_ref_path.exists() and portfolio_ref_path.exists():
        raise ValueError(f"bundle contains both baseline and portfolio run refs: {bundle_dir}")
    if portfolio_ref_path.exists():
        run_ref_path = portfolio_ref_path
        backtest_kind = "portfolio"
        expected_artifact_type = PORTFOLIO_BACKTEST_RUN_REF
    else:
        run_ref_path = baseline_ref_path
        backtest_kind = "baseline"
        expected_artifact_type = BACKTEST_RUN_REF
    if not run_ref_path.exists():
        raise FileNotFoundError(f"backtest run ref not found: {run_ref_path}")
    if not metrics_path.exists():
        raise FileNotFoundError(f"metrics.json not found: {metrics_path}")
    if not result_path.exists():
        raise FileNotFoundError(f"result.json not found: {result_path}")
    run_ref = _read_json(run_ref_path)
    if run_ref.get("artifact_type") != expected_artifact_type:
        raise ValueError(f"run ref artifact_type must be {expected_artifact_type}")
    metrics = _read_json(metrics_path)
    result = _read_json(result_path)
    provenance = _read_json(provenance_path) if provenance_path.exists() else {}
    run_id = str(run_ref.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("backtest_run_ref.run_id is required")
    artifact_paths = _bundle_paths(bundle_dir, backtest_kind=backtest_kind)
    ref_key = "portfolio_backtest_run_ref" if backtest_kind == "portfolio" else "backtest_run_ref"
    artifact_paths[ref_key] = str(run_ref_path)
    trades_path = bundle_dir / "trades.csv"
    return _BacktestBundle(
        bundle_dir=bundle_dir,
        backtest_kind=backtest_kind,
        run_ref=run_ref,
        metrics=metrics,
        result=result,
        provenance=provenance,
        artifact_paths=artifact_paths,
        trades_path=trades_path if trades_path.exists() else None,
        run_id=str(run_ref.get("run_id") or metrics.get("run_id") or result.get("run_id") or "").strip(),
        symbol_metrics=_load_optional_json(bundle_dir / "symbol_metrics.json"),
        exposure_summary=_load_optional_json(bundle_dir / "exposure_summary.json"),
        risk_decisions=_load_optional_json(bundle_dir / "risk_decisions.json"),
        risk_limit_breaches=_load_optional_json(bundle_dir / "risk_limit_breaches.json"),
        risk_measure_summary=_load_optional_json(bundle_dir / "risk_measure_summary.json"),
    )


def _resolve_quality_report(
    *,
    data_quality_report: Mapping[str, Any] | None,
    data_quality_report_path: str | Path | None,
    data_quality_report_ref: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any]]:
    sources = [
        data_quality_report is not None,
        data_quality_report_path is not None and str(data_quality_report_path).strip() != "",
        data_quality_report_ref is not None,
    ]
    if sum(1 for selected in sources if selected) > 1:
        raise ValueError("provide at most one data_quality_report input")
    if data_quality_report is not None:
        return data_quality_report, {"kind": "inline"}
    if data_quality_report_path is not None and str(data_quality_report_path).strip() != "":
        path = Path(str(data_quality_report_path))
        if not path.exists():
            raise FileNotFoundError(f"data_quality_report not found: {path}")
        return _read_json(path), {"kind": "path", "path": str(path)}
    if data_quality_report_ref is None:
        return None, {"kind": "missing"}
    if not isinstance(data_quality_report_ref, MappingABC):
        raise ValueError("data_quality_report_ref must be a mapping")
    if data_quality_report_ref.get("data_quality_report") is not None:
        payload = data_quality_report_ref["data_quality_report"]
        if not isinstance(payload, MappingABC):
            raise ValueError("data_quality_report_ref.data_quality_report must be a mapping")
        return payload, {"kind": "ref_payload"}
    if data_quality_report_ref.get("payload") is not None:
        payload = data_quality_report_ref["payload"]
        if not isinstance(payload, MappingABC):
            raise ValueError("data_quality_report_ref.payload must be a mapping")
        return payload, {"kind": "ref_payload"}
    path_value = data_quality_report_ref.get("path")
    if path_value is None or str(path_value).strip() == "":
        raise ValueError("data_quality_report_ref requires path, payload, or data_quality_report")
    path = Path(str(path_value))
    if not path.exists():
        raise FileNotFoundError(f"data_quality_report not found: {path}")
    return _read_json(path), {"kind": "ref_path", "path": str(path)}


def _bundle_blockers(bundle: _BacktestBundle) -> list[ResearchIssue]:
    blockers: list[ResearchIssue] = []
    status = str(bundle.run_ref.get("status") or "").strip().lower()
    if status and status != "passed":
        blockers.append(_issue("backtest_status_not_passed", f"Backtest status is {status}."))
    for item in _issue_sequence(bundle.run_ref.get("blockers")):
        blockers.append(_issue("backtest_blocker", str(item.get("message") or item), item))
    failed_runs = _optional_float(bundle.metrics.get("failed_runs"))
    if failed_runs is not None and failed_runs > 0:
        blockers.append(_issue("failed_backtest_runs", f"Backtest has {int(failed_runs)} failed runs."))
    return blockers


def _portfolio_risk_evidence_blockers(bundle: _BacktestBundle) -> list[ResearchIssue]:
    if bundle.backtest_kind != "portfolio":
        return []
    blockers: list[ResearchIssue] = []
    if not str(bundle.run_ref.get("strategy_risk_stack_id") or "").strip():
        blockers.append(_issue("missing_strategy_risk_stack_id", "Portfolio backtest ref is missing strategy_risk_stack_id."))
    if not str(bundle.run_ref.get("strategy_risk_stack_validation_id") or "").strip():
        blockers.append(
            _issue(
                "missing_strategy_risk_stack_validation_id",
                "Portfolio backtest ref is missing strategy_risk_stack_validation_id.",
            )
        )
    required = {
        "symbol_metrics": bundle.symbol_metrics,
        "exposure_summary": bundle.exposure_summary,
        "risk_decisions": bundle.risk_decisions,
        "risk_limit_breaches": bundle.risk_limit_breaches,
        "risk_measure_summary": bundle.risk_measure_summary,
    }
    for name, payload in required.items():
        if payload is None:
            blockers.append(_issue("missing_portfolio_risk_evidence", f"Portfolio backtest bundle is missing {name}."))
    risk_measure_summary = _mapping(bundle.risk_measure_summary)
    for telemetry in _sequence(risk_measure_summary.get("missing_required_telemetry")):
        blockers.append(
            _issue(
                "missing_required_risk_telemetry",
                f"Portfolio backtest is missing required risk telemetry: {telemetry}.",
            )
        )
    return blockers


def _bundle_warnings(bundle: _BacktestBundle) -> list[ResearchIssue]:
    warnings: list[ResearchIssue] = []
    for item in _issue_sequence(bundle.run_ref.get("warnings")):
        warnings.append(_issue("backtest_warning", str(item.get("message") or item), item))
    for item in _sequence(bundle.result.get("warnings")):
        warnings.append(_issue("runtime_warning", str(item), {"source": "result.json"}))
    return warnings


def _bundle_caveats(bundle: _BacktestBundle) -> list[str]:
    caveats: list[str] = []
    if not bundle.provenance:
        caveats.append("Backtest provenance was missing or empty.")
    return caveats


def _quality_evaluation(
    *,
    quality_report: Mapping[str, Any] | None,
    quality_source: Mapping[str, Any],
    data_scope: Mapping[str, Any],
) -> tuple[dict[str, Any], list[ResearchIssue], list[ResearchIssue]]:
    if quality_report is None:
        summary = {"provided": False, "source": dict(quality_source)}
        return summary, [_issue("missing_data_quality_report", "Data-quality report is required for evaluation.")], []

    summary = {
        "provided": True,
        "source": dict(quality_source),
        "artifact_type": quality_report.get("artifact_type", DATA_QUALITY_REPORT),
        "report_id": quality_report.get("report_id"),
        "complete": quality_report.get("complete"),
        "total_bars": quality_report.get("total_bars", quality_report.get("total_rows")),
        "missing_bar_count": quality_report.get("missing_bar_count"),
        "missing_gap_count": quality_report.get("missing_gap_count"),
        "warnings": list(str(item) for item in _sequence(quality_report.get("warnings"))),
    }
    blockers: list[ResearchIssue] = []
    warnings = [_issue("data_quality_warning", message, {"report_id": summary.get("report_id")}) for message in summary["warnings"]]
    if str(summary["artifact_type"]) not in {DATA_QUALITY_REPORT, ""}:
        blockers.append(_issue("invalid_data_quality_artifact_type", "Data-quality artifact type must be data_quality_report."))
    if quality_report.get("complete") is not True:
        blockers.append(_issue("incomplete_data_quality", "Data-quality report is incomplete."))
    blockers.extend(_quality_scope_blockers(quality_report, data_scope))
    return summary, blockers, warnings


def _quality_scope_blockers(quality_report: Mapping[str, Any], data_scope: Mapping[str, Any]) -> list[ResearchIssue]:
    blockers: list[ResearchIssue] = []
    if not data_scope:
        return blockers
    report_symbols = [str(item).strip().upper() for item in _sequence(quality_report.get("symbols")) if str(item).strip()]
    scope_symbols = [str(item).strip().upper() for item in _sequence(data_scope.get("symbols")) if str(item).strip()]
    if report_symbols and scope_symbols and report_symbols != scope_symbols:
        blockers.append(_issue("data_quality_symbol_mismatch", "Data-quality symbols do not match backtest data scope."))
    for field in ("asset_class", "timeframe", "source_filter"):
        report_value = quality_report.get(field)
        scope_value = data_scope.get(field)
        if _normalize_optional_text(report_value) != _normalize_optional_text(scope_value):
            blockers.append(_issue(f"data_quality_{field}_mismatch", f"Data-quality {field} does not match backtest data scope."))
    quality_window = _window_payload(quality_report)
    scope_window = _window_payload(data_scope)
    if quality_window and scope_window:
        quality_range = (_normalize_optional_text(quality_window.get("start")), _normalize_optional_text(quality_window.get("end")))
        scope_range = (_normalize_optional_text(scope_window.get("start")), _normalize_optional_text(scope_window.get("end")))
        if quality_range != scope_range:
            blockers.append(_issue("data_quality_window_mismatch", "Data-quality time window does not match backtest data scope."))
    total_bars = quality_report.get("total_bars", quality_report.get("total_rows"))
    scope_rows = data_scope.get("total_rows")
    if total_bars is not None and scope_rows is not None and int(total_bars) != int(scope_rows):
        blockers.append(_issue("data_quality_row_count_mismatch", "Data-quality row count does not match backtest data scope."))
    return blockers


def _quality_caveats(summary: Mapping[str, Any]) -> list[str]:
    if not summary.get("provided"):
        return ["Data-quality evidence was not supplied."]
    return [str(message) for message in _sequence(summary.get("warnings"))]


def _quality_identity(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Return transport-independent quality evidence for stable report IDs."""
    return {key: value for key, value in summary.items() if key != "source"}


def _risk_decision_identity(summary: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = _mapping(summary)
    return {
        "manager_count": payload.get("manager_count"),
        "decision_count": payload.get("decision_count"),
        "rejected_order_count": payload.get("rejected_order_count"),
        "managers": payload.get("managers"),
    }


def _core_metrics(metrics: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    strategy_performance = _mapping(result.get("strategy_performance"))
    return {
        "total_return": _first(metrics.get("total_return"), strategy_performance.get("total_return")),
        "sharpe": _first(metrics.get("sharpe"), strategy_performance.get("sharpe")),
        "max_drawdown": _first(metrics.get("max_drawdown"), strategy_performance.get("max_drawdown")),
        "turnover": _first(metrics.get("turnover"), strategy_performance.get("turnover")),
        "trade_count": _first(metrics.get("trade_count"), strategy_performance.get("trade_count")),
        "hit_rate": _first(strategy_performance.get("hit_rate"), strategy_performance.get("win_rate")),
        "failed_runs": metrics.get("failed_runs", result.get("failed_runs")),
        "warnings_count": metrics.get("warnings_count"),
        "alpha": metrics.get("alpha", result.get("alpha")),
        "beta": metrics.get("beta", result.get("beta")),
        "tracking_error": result.get("tracking_error"),
        "information_ratio": result.get("information_ratio"),
    }


def _trade_stats(metrics: Mapping[str, Any], result: Mapping[str, Any], trades_path: Path | None) -> dict[str, Any]:
    strategy_performance = _mapping(result.get("strategy_performance"))
    trade_count = _first(metrics.get("trade_count"), strategy_performance.get("trade_count"), len(_sequence(result.get("trades"))))
    trade_rows = _read_trade_rows(trades_path)
    if trade_rows is not None:
        trade_count = len(trade_rows)
    return {
        "trade_count": trade_count,
        "hit_rate": _first(strategy_performance.get("hit_rate"), strategy_performance.get("win_rate")),
        "profit_factor": strategy_performance.get("profit_factor"),
        "expectancy": strategy_performance.get("expectancy"),
        "avg_win": strategy_performance.get("avg_win"),
        "avg_loss": strategy_performance.get("avg_loss"),
        "realized_pnl": result.get("realized_pnl"),
        "trades_path": str(trades_path) if trades_path else None,
    }


def _cost_summary(metrics: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    assumptions = _mapping(result.get("assumptions"))
    return {
        "assumptions": {
            "fees": _mapping(assumptions.get("fees")),
            "slippage": _mapping(assumptions.get("slippage")),
        },
        "realized_fees": _first(metrics.get("fees"), result.get("total_fees")),
        "realized_slippage": _first(metrics.get("slippage"), result.get("total_slippage")),
    }


def _benchmark_metrics(metrics: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    benchmark = _mapping(result.get("benchmark_performance"))
    return {
        "benchmark_total_return": benchmark.get("total_return"),
        "benchmark_sharpe": benchmark.get("sharpe"),
        "benchmark_max_drawdown": benchmark.get("max_drawdown"),
        "alpha": _first(metrics.get("alpha"), result.get("alpha")),
        "beta": _first(metrics.get("beta"), result.get("beta")),
        "tracking_error": result.get("tracking_error"),
        "information_ratio": result.get("information_ratio"),
    }


def _metric_blockers(metrics: Mapping[str, Any], trade_stats: Mapping[str, Any]) -> list[ResearchIssue]:
    blockers: list[ResearchIssue] = []
    trade_count = _optional_float(trade_stats.get("trade_count"))
    if trade_count is not None and trade_count <= 0:
        blockers.append(_issue("zero_trades", "Backtest executed zero trades."))
    if metrics.get("run_id") is None:
        blockers.append(_issue("missing_metrics_run_id", "metrics.json does not contain run_id."))
    return blockers


def _metric_caveats(
    core_metrics: Mapping[str, Any],
    trade_stats: Mapping[str, Any],
    costs: Mapping[str, Any],
    benchmark: Mapping[str, Any],
) -> list[str]:
    caveats: list[str] = []
    if trade_stats.get("hit_rate") is None:
        caveats.append("Win-rate/hit-rate is unavailable.")
    if _optional_float(trade_stats.get("trade_count")) == 0:
        caveats.append("Backtest executed zero trades; performance is not strategy-action evidence.")
    if benchmark.get("benchmark_total_return") is None:
        caveats.append("Benchmark total return is unavailable.")
    if benchmark.get("tracking_error") is None:
        caveats.append("Tracking error is unavailable.")
    if _optional_float(costs.get("realized_fees")) == 0 and _optional_float(costs.get("realized_slippage")) == 0:
        caveats.append("Backtest used or realized zero fees and zero slippage.")
    if core_metrics.get("sharpe") is None:
        caveats.append("Sharpe ratio is unavailable.")
    return caveats


def _bundle_paths(bundle_dir: Path, *, backtest_kind: str = "baseline") -> dict[str, Any]:
    paths = {
        "artifact_dir": str(bundle_dir),
        "result": str(bundle_dir / "result.json"),
        "metrics": str(bundle_dir / "metrics.json"),
        "provenance": str(bundle_dir / "provenance.json"),
        "equity_curve": str(bundle_dir / "equity_curve.csv"),
        "benchmark_curve": str(bundle_dir / "benchmark_curve.csv"),
        "positions": str(bundle_dir / "positions.csv"),
    }
    trades_path = bundle_dir / "trades.csv"
    if trades_path.exists():
        paths["trades"] = str(trades_path)
    if backtest_kind == "portfolio":
        paths.update(
            {
                "portfolio_backtest_run_ref": str(bundle_dir / "portfolio_backtest_run_ref.json"),
                "symbol_metrics": str(bundle_dir / "symbol_metrics.json"),
                "exposure_summary": str(bundle_dir / "exposure_summary.json"),
                "risk_decisions": str(bundle_dir / "risk_decisions.json"),
                "risk_limit_breaches": str(bundle_dir / "risk_limit_breaches.json"),
                "risk_measure_summary": str(bundle_dir / "risk_measure_summary.json"),
            }
        )
    else:
        paths["backtest_run_ref"] = str(bundle_dir / "backtest_run_ref.json")
    return paths


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


def _read_trade_rows(path: Path | None) -> list[dict[str, Any]] | None:
    if path is None or not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _issue(code: str, message: str, details: Mapping[str, Any] | None = None) -> ResearchIssue:
    return ResearchIssue(code=code, message=message, details=details or {})


def _dedupe_issues(issues: list[ResearchIssue]) -> list[ResearchIssue]:
    seen: set[tuple[str, str]] = set()
    output: list[ResearchIssue] = []
    for issue in issues:
        key = (issue.code, issue.message)
        if key in seen:
            continue
        seen.add(key)
        output.append(issue)
    return output


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _issue_sequence(value: Any) -> list[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    for item in _sequence(value):
        output.append(item if isinstance(item, MappingABC) else {"message": str(item)})
    return output


def _sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, MappingABC) else {}


def _mapping_or_none(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, MappingABC) else None


def _window_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    window = payload.get("time_range", payload.get("requested_window"))
    return window if isinstance(window, MappingABC) else {}


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _jsonable(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
