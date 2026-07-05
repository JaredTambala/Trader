"""Data-scoped baseline backtest services for research supervisors."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib import util as importlib_util
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader.backtest import BacktestRunner, BacktestSpec, build_backtest_assumptions
from trader.config import Config
from trader.event_store import EventStore
from trader.portfolio import Position
from trader.strategies import Strategy
from trader_standard.risk import NoOpRiskManager

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
    COMPARISON_REPORT,
    DATASET_MANIFEST,
    QUANT_RESEARCH_SUPERVISOR_OWNER,
    BacktestRunRef,
    ResearchIssue,
    StrategyCandidateManifest,
    stable_research_id,
)
from trader_research.method_implementations.io import file_sha256
from trader_research.research import attach_research_metadata, config_snapshot_hash, export_research_bundle, result_summary
from trader_research.strategy_candidates import (
    get_strategy_template,
    strategy_candidate_path,
    strategy_candidate_validation_report_path,
)


RESEARCH_RUN_BACKTEST = "research_run_backtest"
RESEARCH_GET_BACKTEST_RESULTS = "research_get_backtest_results"
RESEARCH_COMPARE_BACKTEST_RESULTS = "research_compare_backtest_results"
_RAW_SCOPE_FIELDS = ("symbols", "asset_class", "timeframe", "start", "end", "source_filter")
_MAX_COMPARISON_RUNS = 50
_DESCENDING_RANKING_METRICS = frozenset({"sharpe", "total_return", "alpha", "beta", "trade_count", "total_runs"})
_ASCENDING_RANKING_METRICS = frozenset(
    {"max_drawdown", "turnover", "fees", "slippage", "warnings_count", "failed_runs"}
)
_SUPPORTED_RANKING_METRICS = _DESCENDING_RANKING_METRICS | _ASCENDING_RANKING_METRICS


@dataclass(frozen=True)
class BacktestDataScope:
    """Normalized Data Agent scope used to bind a strategy candidate to bars.

    Attributes:
        dataset_id: Stable dataset ID produced by `data_get_inventory`.
        symbols: Canonical symbols included in the dataset.
        asset_class: Market-data asset class.
        timeframe: Bar timeframe.
        start: Inclusive UTC start timestamp.
        end: Inclusive UTC end timestamp.
        source_filter: Optional source filter recorded on the dataset manifest.
        total_rows: Total rows reported by the Data Agent.
        complete: Whether the manifest reports complete coverage.
        symbols_detail: Optional per-symbol inventory rows.
        provider_context: Optional provider-resolution metadata.
    """

    dataset_id: str
    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    start: datetime
    end: datetime
    source_filter: str | None
    total_rows: int
    complete: bool
    symbols_detail: tuple[Mapping[str, Any], ...] = ()
    provider_context: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the normalized backtest scope."""
        return {
            "dataset_id": self.dataset_id,
            "artifact_type": DATASET_MANIFEST,
            "symbols": list(self.symbols),
            "asset_class": self.asset_class,
            "timeframe": self.timeframe,
            "time_range": {
                "start": self.start.isoformat(),
                "end": self.end.isoformat(),
            },
            "source_filter": self.source_filter,
            "total_rows": self.total_rows,
            "complete": self.complete,
            "symbols_detail": [_jsonable(item) for item in self.symbols_detail],
            "provider_context": _jsonable(self.provider_context),
        }


@dataclass(frozen=True)
class _ResolvedCandidate:
    """Parsed strategy candidate with optional local source path."""

    manifest: StrategyCandidateManifest
    path: Path | None


@dataclass(frozen=True)
class _ResolvedValidationReport:
    """Parsed validation report with optional local artifact path."""

    report: Mapping[str, Any]
    path: Path | None


def run_baseline_backtest(
    *,
    artifact_root: str | Path,
    event_store: EventStore,
    config: Config,
    candidate_id: str | None = None,
    candidate_path: str | Path | None = None,
    strategy_candidate_manifest: Mapping[str, Any] | None = None,
    validation_id: str | None = None,
    validation_report_path: str | Path | None = None,
    strategy_candidate_validation_report: Mapping[str, Any] | None = None,
    dataset_manifest: Mapping[str, Any] | None = None,
    dataset_manifest_path: str | Path | None = None,
    dataset_manifest_ref: Mapping[str, Any] | None = None,
    data_quality_report: Mapping[str, Any] | None = None,
    data_quality_report_path: str | Path | None = None,
    assumptions: Mapping[str, Any] | None = None,
    initial_cash: float = 100_000.0,
    initial_positions: Sequence[Mapping[str, Any]] | None = None,
    max_runs: int | None = None,
    log_cycle_details: bool = False,
    symbols: Sequence[str] | None = None,
    asset_class: str | None = None,
    timeframe: str | None = None,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    source_filter: str | None = None,
) -> ToolEnvelope:
    """Run one baseline backtest over a Data Agent dataset manifest.

    Args:
        artifact_root: Root directory for research artifacts.
        event_store: Platform event store with historical bars.
        config: Runtime config used by `BacktestRunner`.
        candidate_id: Optional persisted strategy candidate ID.
        candidate_path: Optional path to a candidate manifest.
        strategy_candidate_manifest: Optional inline candidate manifest.
        validation_id: Optional persisted validation report ID.
        validation_report_path: Optional path to a validation report.
        strategy_candidate_validation_report: Optional inline validation report.
        dataset_manifest: Optional inline Data Agent dataset manifest.
        dataset_manifest_path: Optional path to a dataset manifest.
        dataset_manifest_ref: Optional artifact reference containing a path or
            payload to a dataset manifest.
        data_quality_report: Optional inline Data Agent quality report.
        data_quality_report_path: Optional path to a quality report.
        assumptions: Optional execution/data assumptions for the platform runner.
        initial_cash: Cash balance seeded into the baseline run.
        initial_positions: Optional initial positions.
        max_runs: Optional cap for replayed symbol cycles.
        log_cycle_details: Whether to keep per-cycle logs verbose.
        symbols: Forbidden loose scope field; must be supplied by the manifest.
        asset_class: Forbidden loose scope field; must be supplied by the manifest.
        timeframe: Forbidden loose scope field; must be supplied by the manifest.
        start: Forbidden loose scope field; must be supplied by the manifest.
        end: Forbidden loose scope field; must be supplied by the manifest.
        source_filter: Forbidden loose scope field; must be supplied by the manifest.

    Returns:
        Local-mutating envelope containing the persisted `backtest_run_ref` and
        artifact bundle paths, or a fail-closed envelope with actionable errors.
    """
    loose_scope = {
        "symbols": symbols,
        "asset_class": asset_class,
        "timeframe": timeframe,
        "start": start,
        "end": end,
        "source_filter": source_filter,
    }
    supplied_loose_scope = [name for name, value in loose_scope.items() if value is not None]
    if supplied_loose_scope:
        return _run_error(
            code="raw_backtest_scope_rejected",
            message="Backtest scope must come from a Data Agent dataset_manifest, not loose fields.",
            data={"rejected_fields": supplied_loose_scope},
        )

    try:
        candidate = _resolve_candidate(
            artifact_root=artifact_root,
            candidate_id=candidate_id,
            candidate_path=candidate_path,
            strategy_candidate_manifest=strategy_candidate_manifest,
        )
        validation_report = _resolve_validation_report(
            artifact_root=artifact_root,
            validation_id=validation_id,
            validation_report_path=validation_report_path,
            strategy_candidate_validation_report=strategy_candidate_validation_report,
        )
        data_scope = _resolve_data_scope(
            dataset_manifest=dataset_manifest,
            dataset_manifest_path=dataset_manifest_path,
            dataset_manifest_ref=dataset_manifest_ref,
        )
        quality_report = _resolve_quality_report(
            data_quality_report=data_quality_report,
            data_quality_report_path=data_quality_report_path,
        )
        _validate_backtest_inputs(
            candidate=candidate.manifest,
            validation_report=validation_report.report,
            data_scope=data_scope,
            data_quality_report=quality_report,
        )
        normalized_assumptions = _normalize_assumptions_payload(assumptions)
        normalized_initial_cash = _normalize_initial_cash(initial_cash)
        normalized_initial_positions = _normalize_initial_positions(initial_positions)
        normalized_max_runs = _normalize_max_runs(max_runs)
        strategy = _instantiate_strategy(candidate.manifest, data_scope)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return _run_error(code="backtest_input_validation_failed", message=str(exc))

    assumptions_model = build_backtest_assumptions(normalized_assumptions)
    source_hash = candidate.manifest.strategy_source.source_hash if candidate.manifest.strategy_source else ""
    run_id = stable_research_id(
        "backtest_run",
        {
            "candidate_id": candidate.manifest.candidate_id,
            "validation_id": validation_report.report.get("validation_id"),
            "data_scope": data_scope.to_dict(),
            "assumptions": normalized_assumptions,
            "initial_cash": normalized_initial_cash,
            "initial_positions": [position.__dict__ for position in normalized_initial_positions],
            "max_runs": normalized_max_runs,
            "strategy_source_hash": source_hash,
        },
    )
    spec = BacktestSpec(
        start=data_scope.start,
        end=data_scope.end,
        timeframe=data_scope.timeframe,
        max_runs=normalized_max_runs,
    )
    experiment_id = stable_research_id(
        "backtest_experiment",
        {"candidate_id": candidate.manifest.candidate_id, "dataset_id": data_scope.dataset_id},
    )
    experiment_run_id = stable_research_id(
        "backtest_experiment_run",
        {"experiment_id": experiment_id, "run_id": run_id},
    )

    try:
        runner = BacktestRunner(
            config,
            spec,
            strategy=strategy,
            risk_manager=NoOpRiskManager(),
            symbols=data_scope.symbols,
            asset_class=data_scope.asset_class,
            event_store=event_store,
            initial_positions=normalized_initial_positions,
            initial_cash=normalized_initial_cash,
            config_snapshot=_config_snapshot(config),
            assumptions=assumptions_model,
            run_id=run_id,
            started_at=data_scope.start,
        )
        result = runner.run(log_cycle_details=log_cycle_details)
    except Exception as exc:
        return _run_error(code="backtest_run_failed", message=f"baseline backtest failed: {exc}")

    warnings = list(result.warnings)
    blockers: list[ResearchIssue] = []
    status = "passed"
    if result.total_runs <= 0:
        status = "failed"
        blockers.append(
            ResearchIssue(
                code="backtest_no_replay_cycles",
                message="Backtest completed with zero replay cycles for the supplied dataset manifest.",
            )
        )

    summary = result_summary(result)
    artifact_dir = Path(artifact_root) / "backtests" / "runs" / run_id
    provenance = _build_baseline_provenance(
        config=config,
        candidate=candidate,
        validation_report=validation_report,
        data_scope=data_scope,
        data_quality_report=quality_report,
        assumptions=normalized_assumptions,
        initial_cash=normalized_initial_cash,
        initial_positions=normalized_initial_positions,
        max_runs=normalized_max_runs,
        status=status,
        artifact_dir=artifact_dir,
    )
    result = attach_research_metadata(result, experiment_id=experiment_id, experiment_run_id=experiment_run_id, provenance=provenance)
    export_research_bundle(result, output_dir=artifact_dir, provenance=provenance)
    artifact_paths = _bundle_paths(artifact_dir)
    run_ref = BacktestRunRef(
        experiment_id=experiment_id,
        experiment_run_id=experiment_run_id,
        run_id=run_id,
        artifact_dir=str(artifact_dir),
        candidate_id=candidate.manifest.candidate_id,
        validation_id=str(validation_report.report.get("validation_id") or ""),
        dataset_id=data_scope.dataset_id,
        data_scope=data_scope.to_dict(),
        status=status,
        summary=summary,
        artifact_paths=artifact_paths,
        warnings=tuple(ResearchIssue(code="backtest_warning", message=warning) for warning in warnings),
        blockers=tuple(blockers),
    )
    run_ref_path = write_json_artifact(run_ref.to_dict(), artifact_dir / "backtest_run_ref.json")
    artifact_paths["backtest_run_ref"] = str(run_ref_path)
    write_json_artifact({**run_ref.to_dict(), "artifact_paths": artifact_paths}, run_ref_path)

    artifacts = {
        "backtest_run_ref": ArtifactReference(
            artifact_type=BACKTEST_RUN_REF,
            path=run_ref_path,
            metadata={"run_id": run_id, "dataset_id": data_scope.dataset_id, "candidate_id": candidate.manifest.candidate_id},
        ).to_dict()
    }
    data = {
        "backtest_run_ref": {**run_ref.to_dict(), "artifact_paths": artifact_paths},
        "summary": summary,
        "data_scope": data_scope.to_dict(),
        "artifact_paths": artifact_paths,
    }
    if blockers:
        return ToolEnvelope(
            ok=False,
            command=RESEARCH_RUN_BACKTEST,
            agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
            side_effect=SideEffect.LOCAL_MUTATING,
            data=data,
            artifacts=artifacts,
            warnings=tuple(warnings),
            errors=({"code": blockers[0].code, "message": blockers[0].message},),
        )
    return success_envelope(
        command=RESEARCH_RUN_BACKTEST,
        side_effect=SideEffect.LOCAL_MUTATING,
        data=data,
        artifacts=artifacts,
        warnings=tuple(warnings),
    )


def get_backtest_results(
    *,
    artifact_root: str | Path,
    run_id: str | None = None,
    artifact_dir: str | Path | None = None,
    backtest_run_ref: Mapping[str, Any] | None = None,
) -> ToolEnvelope:
    """Read a persisted task-28 baseline backtest bundle.

    Args:
        artifact_root: Root directory for research artifacts.
        run_id: Optional persisted run ID.
        artifact_dir: Optional path to a run artifact directory.
        backtest_run_ref: Optional inline run reference payload.

    Returns:
        Read-only envelope with run ref, summary metrics, provenance, data scope,
        and artifact paths.
    """
    try:
        bundle_dir = _resolve_result_bundle_dir(
            artifact_root=artifact_root,
            run_id=run_id,
            artifact_dir=artifact_dir,
            backtest_run_ref=backtest_run_ref,
        )
        run_ref = _load_run_ref(bundle_dir)
        metrics = _load_optional_json(bundle_dir / "metrics.json")
        provenance = _load_optional_json(bundle_dir / "provenance.json")
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return error_envelope(
            command=RESEARCH_GET_BACKTEST_RESULTS,
            side_effect=SideEffect.READ_ONLY,
            code="backtest_result_lookup_failed",
            message=str(exc),
        )

    warnings = [str(item.get("message") or item) for item in _mapping_sequence(run_ref.get("warnings"))]
    blockers = [str(item.get("message") or item) for item in _mapping_sequence(run_ref.get("blockers"))]
    artifact_paths = _bundle_paths(bundle_dir)
    artifact_paths["backtest_run_ref"] = str(bundle_dir / "backtest_run_ref.json")
    return success_envelope(
        command=RESEARCH_GET_BACKTEST_RESULTS,
        side_effect=SideEffect.READ_ONLY,
        data={
            "backtest_run_ref": {**run_ref, "artifact_paths": artifact_paths},
            "summary": metrics or run_ref.get("summary") or {},
            "data_scope": run_ref.get("data_scope") or {},
            "candidate_id": run_ref.get("candidate_id"),
            "validation_id": run_ref.get("validation_id"),
            "dataset_id": run_ref.get("dataset_id"),
            "provenance": provenance,
            "artifact_paths": artifact_paths,
            "warnings": warnings,
            "blockers": blockers,
        },
        artifacts={
            "backtest_run_ref": ArtifactReference(
                artifact_type=BACKTEST_RUN_REF,
                path=bundle_dir / "backtest_run_ref.json",
                metadata={"run_id": run_ref.get("run_id"), "dataset_id": run_ref.get("dataset_id")},
            ).to_dict()
        },
        warnings=tuple(warnings),
    )


def compare_backtest_results(
    *,
    artifact_root: str | Path,
    backtest_runs: Sequence[Mapping[str, Any]],
    ranking_metric: str = "sharpe",
    sort_order: str | None = None,
) -> ToolEnvelope:
    """Compare persisted task-28 baseline backtest bundles.

    Args:
        artifact_root: Root directory for research artifacts.
        backtest_runs: Explicit run refs. Each item must contain exactly one of
            `run_id`, `artifact_dir`, or inline `backtest_run_ref`.
        ranking_metric: Summary metric used for ranking rows.
        sort_order: Optional `ascending` or `descending` override.

    Returns:
        Local-mutating envelope with a persisted `comparison_report.json`.
    """
    try:
        metric = _normalize_ranking_metric(ranking_metric)
        order = _normalize_sort_order(sort_order, metric)
        rows = _load_comparison_rows(artifact_root=artifact_root, backtest_runs=backtest_runs)
        _validate_unique_run_ids(rows)
        ranked_rows = _rank_comparison_rows(rows, ranking_metric=metric, sort_order=order)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return error_envelope(
            command=RESEARCH_COMPARE_BACKTEST_RESULTS,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="backtest_comparison_failed",
            message=str(exc),
        )

    comparable_dimensions, comparison_warnings = _comparison_dimensions(rows)
    comparison_id = stable_research_id(
        "backtest_comparison",
        {
            "run_ids": [row["run_id"] for row in rows],
            "ranking_metric": metric,
            "sort_order": order,
            "rows": [
                {
                    "run_id": row["run_id"],
                    "summary": row["summary"],
                    "candidate_id": row["candidate_id"],
                    "validation_id": row["validation_id"],
                    "dataset_id": row["dataset_id"],
                    "data_scope": row["data_scope"],
                    "status": row["status"],
                }
                for row in rows
            ],
        },
    )
    report = {
        "artifact_type": COMPARISON_REPORT,
        "schema_version": SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "status": "passed",
        "ranking_metric": metric,
        "sort_order": order,
        "run_count": len(rows),
        "ranked_rows": ranked_rows,
        "best_run_id": ranked_rows[0]["run_id"],
        "comparable_dimensions": comparable_dimensions,
        "warnings": comparison_warnings,
        "blockers": [],
    }
    report_path = write_json_artifact(
        report,
        Path(artifact_root) / "backtests" / "comparisons" / f"{comparison_id}.json",
    )
    return success_envelope(
        command=RESEARCH_COMPARE_BACKTEST_RESULTS,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"comparison_report": report},
        artifacts={
            "comparison_report": ArtifactReference(
                artifact_type=COMPARISON_REPORT,
                path=report_path,
                metadata={
                    "id": comparison_id,
                    "ranking_metric": metric,
                    "run_count": len(rows),
                    "best_run_id": report["best_run_id"],
                },
            ).to_dict()
        },
        warnings=tuple(comparison_warnings),
    )


def _normalize_ranking_metric(value: str) -> str:
    metric = str(value or "").strip().lower()
    if metric not in _SUPPORTED_RANKING_METRICS:
        supported = ", ".join(sorted(_SUPPORTED_RANKING_METRICS))
        raise ValueError(f"unsupported ranking_metric: {value}; supported metrics: {supported}")
    return metric


def _normalize_sort_order(value: str | None, ranking_metric: str) -> str:
    if value is None or str(value).strip() == "":
        return "descending" if ranking_metric in _DESCENDING_RANKING_METRICS else "ascending"
    normalized = str(value).strip().lower()
    aliases = {"asc": "ascending", "ascending": "ascending", "desc": "descending", "descending": "descending"}
    if normalized not in aliases:
        raise ValueError("sort_order must be ascending or descending")
    return aliases[normalized]


def _load_comparison_rows(
    *,
    artifact_root: str | Path,
    backtest_runs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(backtest_runs, SequenceABC) or isinstance(backtest_runs, (str, bytes)):
        raise ValueError("backtest_runs must be a sequence of refs")
    if len(backtest_runs) < 2:
        raise ValueError("backtest comparison requires at least two backtest run refs")
    if len(backtest_runs) > _MAX_COMPARISON_RUNS:
        raise ValueError(f"backtest comparison accepts at most {_MAX_COMPARISON_RUNS} run refs")
    rows: list[dict[str, Any]] = []
    for index, ref in enumerate(backtest_runs):
        if not isinstance(ref, MappingABC):
            raise ValueError(f"backtest_runs[{index}] must be a mapping")
        bundle_dir = _bundle_dir_from_comparison_ref(artifact_root=artifact_root, ref=ref, index=index)
        rows.append(_comparison_row_from_bundle(bundle_dir))
    return rows


def _bundle_dir_from_comparison_ref(
    *,
    artifact_root: str | Path,
    ref: Mapping[str, Any],
    index: int,
) -> Path:
    sources = [
        bool(str(ref.get("run_id") or "").strip()),
        bool(str(ref.get("artifact_dir") or "").strip()),
        ref.get("backtest_run_ref") is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError(
            f"backtest_runs[{index}] must contain exactly one of run_id, artifact_dir, or backtest_run_ref"
        )
    backtest_run_ref = ref.get("backtest_run_ref")
    if backtest_run_ref is not None and not isinstance(backtest_run_ref, MappingABC):
        raise ValueError(f"backtest_runs[{index}].backtest_run_ref must be a mapping")
    return _resolve_result_bundle_dir(
        artifact_root=artifact_root,
        run_id=str(ref["run_id"]) if ref.get("run_id") is not None else None,
        artifact_dir=ref.get("artifact_dir"),
        backtest_run_ref=backtest_run_ref,
    )


def _comparison_row_from_bundle(bundle_dir: Path) -> dict[str, Any]:
    run_ref = _load_run_ref(bundle_dir)
    metrics_path = bundle_dir / "metrics.json"
    if not metrics_path.exists():
        raise FileNotFoundError(f"metrics.json not found: {metrics_path}")
    summary = _read_json(metrics_path)
    provenance = _load_optional_json(bundle_dir / "provenance.json") or {}
    run_id = str(run_ref.get("run_id") or "").strip()
    if not run_id:
        raise ValueError(f"backtest_run_ref.run_id is required: {bundle_dir / 'backtest_run_ref.json'}")
    data_scope = _mapping(run_ref.get("data_scope"))
    artifact_paths = _bundle_paths(bundle_dir)
    artifact_paths["backtest_run_ref"] = str(bundle_dir / "backtest_run_ref.json")
    warnings = _mapping_sequence(run_ref.get("warnings"))
    blockers = _mapping_sequence(run_ref.get("blockers"))
    return {
        "run_id": run_id,
        "candidate_id": run_ref.get("candidate_id"),
        "validation_id": run_ref.get("validation_id"),
        "dataset_id": run_ref.get("dataset_id"),
        "status": run_ref.get("status"),
        "summary": summary,
        "data_scope": data_scope,
        "artifact_paths": artifact_paths,
        "warnings_count": len(warnings),
        "blockers_count": len(blockers),
        "provenance": provenance,
    }


def _validate_unique_run_ids(rows: Sequence[Mapping[str, Any]]) -> None:
    seen: set[str] = set()
    for row in rows:
        run_id = str(row.get("run_id") or "")
        if run_id in seen:
            raise ValueError(f"duplicate backtest run_id: {run_id}")
        seen.add(run_id)


def _rank_comparison_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    ranking_metric: str,
    sort_order: str,
) -> list[dict[str, Any]]:
    normalized_rows = [_public_comparison_row(row, ranking_metric=ranking_metric) for row in rows]
    rankable_rows = [row for row in normalized_rows if row["ranking_metric_value"] is not None]
    if len(rankable_rows) < 2:
        raise ValueError(f"at least two runs must have numeric ranking_metric={ranking_metric}")
    reverse = sort_order == "descending"
    sorted_rankable = sorted(
        rankable_rows,
        key=lambda row: (float(row["ranking_metric_value"]), row["run_id"]),
        reverse=reverse,
    )
    for rank, row in enumerate(sorted_rankable, start=1):
        row["rank"] = rank
    unranked_rows = [row for row in normalized_rows if row["ranking_metric_value"] is None]
    return sorted_rankable + unranked_rows


def _public_comparison_row(row: Mapping[str, Any], *, ranking_metric: str) -> dict[str, Any]:
    summary = _mapping(row.get("summary"))
    metric_value = _optional_float(summary.get(ranking_metric))
    payload = {
        "run_id": row.get("run_id"),
        "candidate_id": row.get("candidate_id"),
        "validation_id": row.get("validation_id"),
        "dataset_id": row.get("dataset_id"),
        "status": row.get("status"),
        "summary": summary,
        "data_scope": _mapping(row.get("data_scope")),
        "artifact_paths": _mapping(row.get("artifact_paths")),
        "warnings_count": int(row.get("warnings_count") or 0),
        "blockers_count": int(row.get("blockers_count") or 0),
        "ranking_metric": ranking_metric,
        "ranking_metric_value": metric_value,
    }
    if metric_value is None:
        payload["rankable"] = False
    else:
        payload["rankable"] = True
    return payload


def _comparison_dimensions(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    dimensions = {
        "dataset_id": ("dataset ID", lambda row: row.get("dataset_id")),
        "symbols": ("symbols", lambda row: _mapping(row.get("data_scope")).get("symbols")),
        "asset_class": ("asset class", lambda row: _mapping(row.get("data_scope")).get("asset_class")),
        "timeframe": ("timeframe", lambda row: _mapping(row.get("data_scope")).get("timeframe")),
        "time_range": ("time range", lambda row: _mapping(row.get("data_scope")).get("time_range")),
        "source_filter": ("source filter", lambda row: _mapping(row.get("data_scope")).get("source_filter")),
        "assumptions": ("assumptions", lambda row: _mapping(row.get("provenance")).get("assumptions")),
        "candidate_id": ("candidate ID", lambda row: row.get("candidate_id")),
        "validation_id": ("validation ID", lambda row: row.get("validation_id")),
    }
    comparable: dict[str, Any] = {}
    warnings: list[str] = []
    for key, (label, extractor) in dimensions.items():
        values = [extractor(row) for row in rows]
        unique_values = _unique_values(values)
        is_comparable = len(unique_values) <= 1
        comparable[key] = {"comparable": is_comparable, "values": unique_values}
        if not is_comparable:
            warnings.append(f"Compared runs differ in {label}.")
    return comparable, warnings


def _unique_values(values: Sequence[Any]) -> list[Any]:
    seen: set[str] = set()
    unique: list[Any] = []
    for value in values:
        normalized = _stable_json(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(_jsonable(value))
    return unique


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _resolve_candidate(
    *,
    artifact_root: str | Path,
    candidate_id: str | None,
    candidate_path: str | Path | None,
    strategy_candidate_manifest: Mapping[str, Any] | None,
) -> _ResolvedCandidate:
    sources = [
        bool(candidate_id and candidate_id.strip()),
        candidate_path is not None and str(candidate_path).strip() != "",
        strategy_candidate_manifest is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError("exactly one strategy candidate input is required")
    if strategy_candidate_manifest is not None:
        return _ResolvedCandidate(StrategyCandidateManifest.from_dict(strategy_candidate_manifest), None)
    path = strategy_candidate_path(artifact_root, candidate_id.strip()) if candidate_id else Path(str(candidate_path))
    if not path.exists():
        raise FileNotFoundError(f"strategy candidate manifest not found: {path}")
    return _ResolvedCandidate(StrategyCandidateManifest.from_dict(_read_json(path)), path)


def _resolve_validation_report(
    *,
    artifact_root: str | Path,
    validation_id: str | None,
    validation_report_path: str | Path | None,
    strategy_candidate_validation_report: Mapping[str, Any] | None,
) -> _ResolvedValidationReport:
    sources = [
        bool(validation_id and validation_id.strip()),
        validation_report_path is not None and str(validation_report_path).strip() != "",
        strategy_candidate_validation_report is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError("exactly one strategy validation report input is required")
    if strategy_candidate_validation_report is not None:
        return _ResolvedValidationReport(dict(strategy_candidate_validation_report), None)
    path = (
        strategy_candidate_validation_report_path(artifact_root, validation_id.strip())
        if validation_id
        else Path(str(validation_report_path))
    )
    if not path.exists():
        raise FileNotFoundError(f"strategy candidate validation report not found: {path}")
    return _ResolvedValidationReport(_read_json(path), path)


def _resolve_data_scope(
    *,
    dataset_manifest: Mapping[str, Any] | None,
    dataset_manifest_path: str | Path | None,
    dataset_manifest_ref: Mapping[str, Any] | None,
) -> BacktestDataScope:
    sources = [
        dataset_manifest is not None,
        dataset_manifest_path is not None and str(dataset_manifest_path).strip() != "",
        dataset_manifest_ref is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError("exactly one dataset_manifest input is required")
    payload: Mapping[str, Any]
    if dataset_manifest is not None:
        payload = dataset_manifest
    elif dataset_manifest_path is not None:
        path = Path(str(dataset_manifest_path))
        if not path.exists():
            raise FileNotFoundError(f"dataset manifest not found: {path}")
        payload = _read_json(path)
    else:
        payload = _manifest_from_ref(dataset_manifest_ref or {})
    return _scope_from_manifest(payload)


def _manifest_from_ref(ref: Mapping[str, Any]) -> Mapping[str, Any]:
    if ref.get("payload") is not None:
        payload = ref["payload"]
        if not isinstance(payload, MappingABC):
            raise ValueError("dataset_manifest_ref.payload must be a mapping")
        return payload
    if ref.get("dataset_manifest") is not None:
        payload = ref["dataset_manifest"]
        if not isinstance(payload, MappingABC):
            raise ValueError("dataset_manifest_ref.dataset_manifest must be a mapping")
        return payload
    path_value = ref.get("path")
    if path_value is None:
        raise ValueError("dataset_manifest_ref requires path, payload, or dataset_manifest")
    path = Path(str(path_value))
    if not path.exists():
        raise FileNotFoundError(f"dataset manifest not found: {path}")
    return _read_json(path)


def _scope_from_manifest(payload: Mapping[str, Any]) -> BacktestDataScope:
    dataset_id = str(payload.get("dataset_id") or "").strip()
    if not dataset_id:
        raise ValueError("dataset_manifest.dataset_id is required")
    symbols = tuple(str(symbol).strip().upper() for symbol in _sequence(payload.get("symbols")) if str(symbol).strip())
    if not symbols:
        raise ValueError("dataset_manifest.symbols must contain at least one symbol")
    asset_class = str(payload.get("asset_class") or "").strip().lower()
    if not asset_class:
        raise ValueError("dataset_manifest.asset_class is required")
    timeframe = str(payload.get("timeframe") or "").strip()
    if not timeframe:
        raise ValueError("dataset_manifest.timeframe is required")
    window = _window_payload(payload)
    start = _parse_datetime(window.get("start"), "dataset_manifest.time_range.start")
    end = _parse_datetime(window.get("end"), "dataset_manifest.time_range.end")
    if start > end:
        raise ValueError("dataset_manifest time_range.start must be <= time_range.end")
    total_rows = _int_value(payload.get("total_rows"), "dataset_manifest.total_rows")
    if total_rows <= 0:
        raise ValueError("dataset_manifest.total_rows must be positive")
    complete = payload.get("complete")
    if complete is not True:
        raise ValueError("dataset_manifest.complete must be true")
    source_value = payload.get("source_filter")
    source_filter = str(source_value).strip() if source_value is not None and str(source_value).strip() else None
    if source_filter is not None:
        raise ValueError("dataset_manifest.source_filter is not supported by baseline backtests yet")
    return BacktestDataScope(
        dataset_id=dataset_id,
        symbols=symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        start=start,
        end=end,
        source_filter=source_filter,
        total_rows=total_rows,
        complete=True,
        symbols_detail=tuple(dict(item) for item in _mapping_sequence(payload.get("symbols_detail"))),
        provider_context=_mapping(payload.get("provider_context")),
    )


def _resolve_quality_report(
    *,
    data_quality_report: Mapping[str, Any] | None,
    data_quality_report_path: str | Path | None,
) -> Mapping[str, Any] | None:
    sources = [
        data_quality_report is not None,
        data_quality_report_path is not None and str(data_quality_report_path).strip() != "",
    ]
    if sum(1 for selected in sources if selected) > 1:
        raise ValueError("at most one data_quality_report input is allowed")
    if data_quality_report is not None:
        return data_quality_report
    if data_quality_report_path is None:
        return None
    path = Path(str(data_quality_report_path))
    if not path.exists():
        raise FileNotFoundError(f"data quality report not found: {path}")
    return _read_json(path)


def _validate_backtest_inputs(
    *,
    candidate: StrategyCandidateManifest,
    validation_report: Mapping[str, Any],
    data_scope: BacktestDataScope,
    data_quality_report: Mapping[str, Any] | None,
) -> None:
    template = get_strategy_template(candidate.template_family)
    if candidate.blockers:
        raise ValueError("strategy candidate manifest has blockers")
    if candidate.strategy_source is None:
        raise ValueError("strategy candidate strategy_source is required")
    source_path = Path(candidate.strategy_source.path)
    if not source_path.exists():
        raise FileNotFoundError(f"strategy source file not found: {source_path}")
    if file_sha256(source_path) != candidate.strategy_source.source_hash:
        raise ValueError("strategy source_hash does not match current source file")
    if str(candidate.strategy_source.metadata.get("runtime_builder_path") or "") != template.runtime_builder_path:
        raise ValueError("strategy_source runtime_builder_path does not match template")
    if validation_report.get("status") != "passed":
        raise ValueError("strategy candidate validation report status must be passed")
    if validation_report.get("blockers"):
        raise ValueError("strategy candidate validation report must not contain blockers")
    if str(validation_report.get("candidate_id") or "") != candidate.candidate_id:
        raise ValueError("strategy candidate validation report candidate_id does not match candidate")
    if str(validation_report.get("runtime_builder_path") or "") != template.runtime_builder_path:
        raise ValueError("strategy candidate validation report runtime_builder_path does not match template")
    _validate_execution_assumptions(candidate.execution_assumptions)
    if data_quality_report is not None:
        _validate_quality_matches_scope(data_quality_report, data_scope)


def _validate_execution_assumptions(assumptions: Mapping[str, Any]) -> None:
    if assumptions.get("live_trading_allowed") is True:
        raise ValueError("strategy candidate execution_assumptions.live_trading_allowed must remain false")
    if assumptions.get("broker_mutation_allowed") is True:
        raise ValueError("strategy candidate execution_assumptions.broker_mutation_allowed must remain false")
    order_type = assumptions.get("order_type")
    if order_type is not None and str(order_type).strip().lower() != "market":
        raise ValueError("strategy candidate execution_assumptions.order_type must be market")


def _validate_quality_matches_scope(report: Mapping[str, Any], scope: BacktestDataScope) -> None:
    if report.get("complete") is not True:
        raise ValueError("data_quality_report.complete must be true")
    report_symbols = tuple(str(symbol).strip().upper() for symbol in _sequence(report.get("symbols")) if str(symbol).strip())
    if report_symbols and report_symbols != scope.symbols:
        raise ValueError("data_quality_report.symbols does not match dataset_manifest.symbols")
    if str(report.get("asset_class") or "").strip().lower() != scope.asset_class:
        raise ValueError("data_quality_report.asset_class does not match dataset_manifest.asset_class")
    if str(report.get("timeframe") or "").strip() != scope.timeframe:
        raise ValueError("data_quality_report.timeframe does not match dataset_manifest.timeframe")
    quality_window = _window_payload(report)
    quality_start = _parse_datetime(quality_window.get("start"), "data_quality_report.time_range.start")
    quality_end = _parse_datetime(quality_window.get("end"), "data_quality_report.time_range.end")
    if quality_start != scope.start or quality_end != scope.end:
        raise ValueError("data_quality_report time window does not match dataset_manifest time_range")
    quality_source = report.get("source_filter")
    normalized_source = str(quality_source).strip() if quality_source is not None and str(quality_source).strip() else None
    if normalized_source != scope.source_filter:
        raise ValueError("data_quality_report.source_filter does not match dataset_manifest.source_filter")
    total_bars = report.get("total_bars", report.get("total_rows"))
    if total_bars is not None and _int_value(total_bars, "data_quality_report.total_bars") != scope.total_rows:
        raise ValueError("data_quality_report total rows does not match dataset_manifest.total_rows")


def _instantiate_strategy(candidate: StrategyCandidateManifest, data_scope: BacktestDataScope) -> Strategy:
    source_ref = candidate.strategy_source
    if source_ref is None:
        raise ValueError("strategy candidate strategy_source is required")
    source_path = Path(source_ref.path)
    module_name = f"_trader_backtest_strategy_{_module_suffix(candidate.candidate_id)}"
    spec = importlib_util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load strategy source module: {source_path}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, source_ref.class_name):
        raise ValueError(f"strategy source class not found: {source_ref.class_name}")
    factory = getattr(module, source_ref.factory_name, None)
    if factory is None:
        raise ValueError(f"strategy source factory not found: {source_ref.factory_name}")
    strategy = factory(
        symbols=list(data_scope.symbols),
        asset_class=data_scope.asset_class,
        timeframe=data_scope.timeframe,
        target_qty_when_long=candidate.sizing.target_qty_when_long,
    )
    if not isinstance(strategy, Strategy):
        raise ValueError("strategy source factory did not return a trader.strategies.Strategy")
    return strategy


def _normalize_assumptions_payload(assumptions: Mapping[str, Any] | None) -> dict[str, Any]:
    if assumptions is None:
        return {}
    if not isinstance(assumptions, MappingABC):
        raise ValueError("assumptions must be a mapping")
    payload = dict(assumptions)
    if "fill_model" in payload and not str(payload["fill_model"]).strip():
        raise ValueError("assumptions.fill_model must be non-empty when supplied")
    for key in ("latency_ms",):
        if key in payload and _float_value(payload[key], f"assumptions.{key}") < 0.0:
            raise ValueError(f"assumptions.{key} must be non-negative")
    for section_name, value_names in {
        "fees": ("fixed_per_order", "bps", "minimum_fee"),
        "slippage": ("bps",),
    }.items():
        section = payload.get(section_name)
        if section is None:
            continue
        if not isinstance(section, MappingABC):
            raise ValueError(f"assumptions.{section_name} must be a mapping")
        for value_name in value_names:
            if value_name in section and _float_value(section[value_name], f"assumptions.{section_name}.{value_name}") < 0.0:
                raise ValueError(f"assumptions.{section_name}.{value_name} must be non-negative")
    data_section = payload.get("data")
    if data_section is not None and not isinstance(data_section, MappingABC):
        raise ValueError("assumptions.data must be a mapping")
    return payload


def _normalize_initial_cash(value: float) -> float:
    cash = _float_value(value, "initial_cash")
    if cash < 0.0:
        raise ValueError("initial_cash must be non-negative")
    return cash


def _normalize_initial_positions(values: Sequence[Mapping[str, Any]] | None) -> list[Position]:
    if values is None:
        return []
    if not isinstance(values, SequenceABC) or isinstance(values, (str, bytes)):
        raise ValueError("initial_positions must be a sequence of mappings")
    positions: list[Position] = []
    for index, item in enumerate(values):
        if not isinstance(item, MappingABC):
            raise ValueError(f"initial_positions[{index}] must be a mapping")
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            raise ValueError(f"initial_positions[{index}].symbol is required")
        qty = _float_value(item.get("qty"), f"initial_positions[{index}].qty")
        avg_price_value = item.get("avg_price")
        avg_price = _float_value(avg_price_value, f"initial_positions[{index}].avg_price") if avg_price_value is not None else None
        if avg_price is not None and avg_price < 0.0:
            raise ValueError(f"initial_positions[{index}].avg_price must be non-negative")
        positions.append(Position(symbol=symbol, qty=qty, avg_price=avg_price))
    return positions


def _normalize_max_runs(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("max_runs must be a positive integer")
    if value <= 0:
        raise ValueError("max_runs must be a positive integer")
    return value


def _build_baseline_provenance(
    *,
    config: Config,
    candidate: _ResolvedCandidate,
    validation_report: _ResolvedValidationReport,
    data_scope: BacktestDataScope,
    data_quality_report: Mapping[str, Any] | None,
    assumptions: Mapping[str, Any],
    initial_cash: float,
    initial_positions: Sequence[Position],
    max_runs: int | None,
    status: str,
    artifact_dir: Path,
) -> dict[str, Any]:
    source_ref = candidate.manifest.strategy_source
    return {
        "artifact_type": "backtest_provenance",
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "candidate_id": candidate.manifest.candidate_id,
        "candidate_ref": {
            "path": str(candidate.path) if candidate.path is not None else None,
            "template_family": candidate.manifest.template_family,
            "strategy_source": source_ref.to_dict() if source_ref is not None else None,
        },
        "validation_id": validation_report.report.get("validation_id"),
        "validation_ref": {
            "path": str(validation_report.path) if validation_report.path is not None else None,
            "status": validation_report.report.get("status"),
        },
        "dataset_id": data_scope.dataset_id,
        "data_scope": data_scope.to_dict(),
        "data_quality_report": _jsonable(data_quality_report),
        "assumptions": _jsonable(assumptions),
        "initial_cash": initial_cash,
        "initial_positions": [position.__dict__ for position in initial_positions],
        "max_runs": max_runs,
        "risk": {"risk_manager": "trader_standard.risk.NoOpRiskManager", "policy": "baseline_noop_risk"},
        "config_hash": config_snapshot_hash(_config_snapshot(config)),
        "artifact_dir": str(artifact_dir),
    }


def _bundle_paths(bundle_dir: Path) -> dict[str, Any]:
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
    return paths


def _resolve_result_bundle_dir(
    *,
    artifact_root: str | Path,
    run_id: str | None,
    artifact_dir: str | Path | None,
    backtest_run_ref: Mapping[str, Any] | None,
) -> Path:
    sources = [
        bool(run_id and run_id.strip()),
        artifact_dir is not None and str(artifact_dir).strip() != "",
        backtest_run_ref is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError("exactly one of run_id, artifact_dir, or backtest_run_ref is required")
    if run_id:
        return Path(artifact_root) / "backtests" / "runs" / run_id.strip()
    if artifact_dir is not None:
        return Path(str(artifact_dir))
    ref_dir = backtest_run_ref.get("artifact_dir") if backtest_run_ref is not None else None
    if ref_dir is None:
        raise ValueError("backtest_run_ref.artifact_dir is required")
    return Path(str(ref_dir))


def _load_run_ref(bundle_dir: Path) -> dict[str, Any]:
    path = bundle_dir / "backtest_run_ref.json"
    if not path.exists():
        raise FileNotFoundError(f"backtest_run_ref.json not found: {path}")
    payload = _read_json(path)
    if payload.get("artifact_type") != BACKTEST_RUN_REF:
        raise ValueError("backtest_run_ref artifact_type must be backtest_run_ref")
    return payload


def _run_error(*, code: str, message: str, data: Mapping[str, Any] | None = None) -> ToolEnvelope:
    return error_envelope(
        command=RESEARCH_RUN_BACKTEST,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
        data=data,
    )


def _window_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    window = payload.get("time_range", payload.get("requested_window"))
    if not isinstance(window, MappingABC):
        raise ValueError("manifest time_range/requested_window is required")
    return window


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


def _config_snapshot(config: Config) -> dict[str, Any]:
    snapshot = asdict(config)
    for secret_key in ("alpaca_api_key", "alpaca_secret_key", "pg_password", "pg_dsn"):
        if snapshot.get(secret_key):
            snapshot[secret_key] = "<redacted>"
    return snapshot


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, MappingABC) else {}


def _mapping_sequence(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, SequenceABC) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, MappingABC)]


def _parse_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    else:
        raise ValueError(f"{field_name} is required")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_value(value: object, field_name: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field_name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    return parsed


def _float_value(value: object, field_name: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field_name} must be numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _module_suffix(candidate_id: str) -> str:
    suffix = "".join(character for character in candidate_id if character.isalnum())[-16:]
    return suffix or "generated"


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, MappingABC):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"))
