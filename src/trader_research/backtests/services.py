"""Data-scoped baseline backtest services for research supervisors."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib import util as importlib_util
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from trader.backtest import BacktestResult, BacktestRunner, BacktestSpec, build_backtest_assumptions
from trader.backtest.export_payloads import _build_equity_curve_csv_rows, _build_trade_csv_rows, serialize_backtest_result
from trader.config import Config
from trader.event_store import EventStore
from trader.portfolio import Position
from trader.risk import RiskContext, RiskManager
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
from trader_research.artifact_store import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    load_artifact_ref,
    load_module_from_source,
    source_hash as source_text_hash,
)
from trader_research.domain import (
    BACKTEST_RUN_REF,
    COMPARISON_REPORT,
    DATASET_MANIFEST,
    PORTFOLIO_BACKTEST_RUN_REF,
    QUANT_RESEARCH_SUPERVISOR_OWNER,
    RISK_MANAGER_CANDIDATE,
    STRATEGY_CANDIDATE,
    STRATEGY_CANDIDATE_VALIDATION_REPORT,
    STRATEGY_RISK_STACK_VALIDATION_REPORT,
    BacktestRunRef,
    PortfolioBacktestRunRef,
    ResearchIssue,
    RiskManagerCandidateSourceRef,
    RiskManagerCandidateManifest,
    StrategyCandidateManifest,
    StrategyCandidateSourceRef,
    StrategyRiskStackManifest,
    stable_research_id,
)
from trader_research.method_implementations.io import file_sha256
from trader_research.portfolio_stacks import (
    strategy_risk_stack_manifest_path,
    strategy_risk_stack_validation_report_path,
)
from trader_research.research import attach_research_metadata, config_snapshot_hash, export_research_bundle, result_summary
from trader_research.risk_managers import risk_manager_candidate_path
from trader_research.strategy_candidates import (
    get_strategy_template,
    strategy_candidate_path,
    strategy_candidate_validation_report_path,
)


RESEARCH_RUN_BACKTEST = "research_run_backtest"
RESEARCH_RUN_PORTFOLIO_BACKTEST = "research_run_portfolio_backtest"
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


@dataclass(frozen=True)
class _ResolvedStack:
    """Parsed strategy/risk stack manifest with optional local artifact path."""

    manifest: StrategyRiskStackManifest
    path: Path | None


@dataclass(frozen=True)
class _ResolvedRiskManager:
    """Resolved risk-manager candidate manifest, source path, and runtime instance."""

    manifest: RiskManagerCandidateManifest
    path: Path | None
    instance: RiskManager


class _RecordingRiskPipeline(RiskManager):
    """Research-only ordered risk manager that records decision telemetry."""

    def __init__(self, managers: Sequence[_ResolvedRiskManager]) -> None:
        self._managers = tuple(managers)
        self._decisions: list[dict[str, Any]] = []

    @property
    def decisions(self) -> tuple[dict[str, Any], ...]:
        """Return JSON-safe risk decisions recorded during the backtest."""
        return tuple(self._decisions)

    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        """Return orders approved by the ordered manager chain."""
        approved, _rejected = self.evaluate(orders, context)
        return approved

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        """Run managers in order and record per-manager approval/rejection counts."""
        approved_orders: Sequence[Mapping[str, object]] = list(orders)
        rejected_all: list[Mapping[str, object]] = []
        for index, resolved in enumerate(self._managers):
            before_count = len(approved_orders)
            approved, rejected = resolved.instance.evaluate(approved_orders, context)
            approved_tuple = tuple(approved)
            rejected_tuple = tuple(rejected)
            rejected_all.extend(rejected_tuple)
            self._decisions.append(
                {
                    "manager_index": index,
                    "manager_class": resolved.instance.__class__.__name__,
                    "risk_manager_candidate_id": resolved.manifest.candidate_id,
                    "template_family": resolved.manifest.template_family,
                    "run_id": context.run_id,
                    "cycle_id": context.cycle_id,
                    "decision_ts": context.decision_ts.isoformat(),
                    "input_count": before_count,
                    "approved_count": len(approved_tuple),
                    "rejected_count": len(rejected_tuple),
                    "approved_order_ids": _order_ids(approved_tuple),
                    "rejected_orders": [_order_evidence(order) for order in rejected_tuple],
                }
            )
            approved_orders = approved_tuple
            if not approved_orders:
                break
        return tuple(approved_orders), tuple(rejected_all)


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
    artifact_store: ResearchArtifactStore | None = None,
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
            artifact_store=artifact_store,
        )
        validation_report = _resolve_validation_report(
            artifact_root=artifact_root,
            validation_id=validation_id,
            validation_report_path=validation_report_path,
            strategy_candidate_validation_report=strategy_candidate_validation_report,
            artifact_store=artifact_store,
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
            artifact_store=artifact_store,
        )
        normalized_assumptions = _normalize_assumptions_payload(assumptions)
        normalized_initial_cash = _normalize_initial_cash(initial_cash)
        normalized_initial_positions = _normalize_initial_positions(initial_positions)
        normalized_max_runs = _normalize_max_runs(max_runs)
        strategy = _instantiate_strategy(candidate.manifest, data_scope, artifact_store)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, ResearchArtifactStoreError) as exc:
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


def run_portfolio_backtest(
    *,
    artifact_root: str | Path,
    event_store: EventStore,
    config: Config,
    strategy_risk_stack_validation_id: str | None = None,
    strategy_risk_stack_validation_report_path: str | Path | None = None,
    strategy_risk_stack_validation_report: Mapping[str, Any] | None = None,
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
    artifact_store: ResearchArtifactStore | None = None,
    symbols: Sequence[str] | None = None,
    asset_class: str | None = None,
    timeframe: str | None = None,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    source_filter: str | None = None,
) -> ToolEnvelope:
    """Run a risk-scoped portfolio backtest from a validated strategy/risk stack."""
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
        return _portfolio_run_error(
            code="raw_backtest_scope_rejected",
            message="Backtest scope must come from a Data Agent dataset_manifest, not loose fields.",
            data={"rejected_fields": supplied_loose_scope},
        )

    try:
        stack_validation_report = _resolve_stack_validation_report(
            artifact_root=artifact_root,
            validation_id=strategy_risk_stack_validation_id,
            validation_report_path=strategy_risk_stack_validation_report_path,
            strategy_risk_stack_validation_report=strategy_risk_stack_validation_report,
            artifact_store=artifact_store,
        )
        _validate_stack_validation_report(stack_validation_report.report)
        stack = _resolve_stack_from_validation_report(
            artifact_root=artifact_root,
            validation_report=stack_validation_report.report,
            artifact_store=artifact_store,
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
        strategy_candidate = _load_strategy_candidate_from_stack(artifact_root, stack.manifest, artifact_store)
        strategy_validation_report = _load_strategy_validation_report_from_stack(
            artifact_root,
            stack.manifest,
            artifact_store,
        )
        _validate_backtest_inputs(
            candidate=strategy_candidate.manifest,
            validation_report=strategy_validation_report.report,
            data_scope=data_scope,
            data_quality_report=quality_report,
            artifact_store=artifact_store,
        )
        risk_managers = _load_risk_managers_from_stack(artifact_root, stack.manifest, artifact_store)
        _validate_portfolio_stack_inputs(
            stack=stack,
            strategy_candidate=strategy_candidate.manifest,
            risk_managers=risk_managers,
        )
        normalized_assumptions = _normalize_assumptions_payload(assumptions)
        normalized_initial_cash = _normalize_initial_cash(initial_cash)
        normalized_initial_positions = _normalize_initial_positions(initial_positions)
        normalized_max_runs = _normalize_max_runs(max_runs)
        strategy = _instantiate_strategy(strategy_candidate.manifest, data_scope, artifact_store)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, ResearchArtifactStoreError) as exc:
        return _portfolio_run_error(code="portfolio_backtest_input_validation_failed", message=str(exc))

    assumptions_model = build_backtest_assumptions(normalized_assumptions)
    risk_source_hashes = [
        manager.manifest.risk_manager_source.source_hash
        for manager in risk_managers
        if manager.manifest.risk_manager_source is not None
    ]
    strategy_source_hash = (
        strategy_candidate.manifest.strategy_source.source_hash
        if strategy_candidate.manifest.strategy_source is not None
        else ""
    )
    stack_validation_id = str(stack_validation_report.report.get("validation_id") or "")
    run_id = stable_research_id(
        "portfolio_backtest_run",
        {
            "strategy_risk_stack_id": stack.manifest.stack_id,
            "strategy_risk_stack_validation_id": stack_validation_id,
            "data_scope": data_scope.to_dict(),
            "assumptions": normalized_assumptions,
            "initial_cash": normalized_initial_cash,
            "initial_positions": [position.__dict__ for position in normalized_initial_positions],
            "max_runs": normalized_max_runs,
            "strategy_source_hash": strategy_source_hash,
            "risk_source_hashes": risk_source_hashes,
        },
    )
    spec = BacktestSpec(
        start=data_scope.start,
        end=data_scope.end,
        timeframe=data_scope.timeframe,
        max_runs=normalized_max_runs,
    )
    experiment_id = stable_research_id(
        "portfolio_backtest_experiment",
        {"strategy_risk_stack_id": stack.manifest.stack_id, "dataset_id": data_scope.dataset_id},
    )
    experiment_run_id = stable_research_id(
        "portfolio_backtest_experiment_run",
        {"experiment_id": experiment_id, "run_id": run_id},
    )
    recording_pipeline = _RecordingRiskPipeline(risk_managers)

    try:
        runner = BacktestRunner(
            config,
            spec,
            strategy=strategy,
            risk_manager=recording_pipeline,
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
        return _portfolio_run_error(code="portfolio_backtest_run_failed", message=f"portfolio backtest failed: {exc}")

    warnings = list(result.warnings)
    blockers: list[ResearchIssue] = []
    status = "passed"
    if result.total_runs <= 0:
        status = "failed"
        blockers.append(
            ResearchIssue(
                code="portfolio_backtest_no_replay_cycles",
                message="Portfolio backtest completed with zero replay cycles for the supplied dataset manifest.",
            )
        )

    summary = result_summary(result)
    symbol_metrics = _portfolio_symbol_metrics(result)
    exposure_summary = _portfolio_exposure_summary(result, symbol_metrics)
    risk_decisions = _risk_decision_summary(recording_pipeline.decisions, risk_managers)
    risk_measure_summary = _risk_measure_summary(result, risk_managers, exposure_summary, symbol_metrics)
    risk_limit_breaches = _risk_limit_breach_summary(
        risk_decisions=risk_decisions,
        risk_managers=risk_managers,
        exposure_summary=exposure_summary,
        symbol_metrics=symbol_metrics,
        risk_measure_summary=risk_measure_summary,
    )
    missing_telemetry = risk_measure_summary.get("missing_required_telemetry") or []
    if missing_telemetry:
        warnings.append(f"Portfolio backtest missing required risk telemetry: {', '.join(missing_telemetry)}.")

    artifact_dir = Path(artifact_root) / "portfolio_backtests" / "runs" / run_id
    provenance = _build_portfolio_provenance(
        config=config,
        stack=stack,
        stack_validation_report=stack_validation_report,
        strategy_candidate=strategy_candidate,
        strategy_validation_report=strategy_validation_report,
        risk_managers=risk_managers,
        data_scope=data_scope,
        data_quality_report=quality_report,
        assumptions=normalized_assumptions,
        initial_cash=normalized_initial_cash,
        initial_positions=normalized_initial_positions,
        max_runs=normalized_max_runs,
        status=status,
        artifact_dir=artifact_dir,
        risk_measure_summary=risk_measure_summary,
    )
    result = attach_research_metadata(
        result,
        experiment_id=experiment_id,
        experiment_run_id=experiment_run_id,
        provenance=provenance,
    )
    artifact_paths: Mapping[str, Any]
    if artifact_store is None:
        export_research_bundle(result, output_dir=artifact_dir, provenance=provenance)
        artifact_paths = _portfolio_bundle_paths(artifact_dir)
        write_json_artifact(symbol_metrics, artifact_dir / "symbol_metrics.json")
        write_json_artifact(exposure_summary, artifact_dir / "exposure_summary.json")
        write_json_artifact(risk_decisions, artifact_dir / "risk_decisions.json")
        write_json_artifact(risk_limit_breaches, artifact_dir / "risk_limit_breaches.json")
        write_json_artifact(risk_measure_summary, artifact_dir / "risk_measure_summary.json")
        artifact_paths = _portfolio_bundle_paths(artifact_dir)
    else:
        artifact_paths = {}
    run_ref = PortfolioBacktestRunRef(
        run_id=run_id,
        artifact_dir=str(artifact_dir) if artifact_store is None else None,
        strategy_risk_stack_id=stack.manifest.stack_id,
        strategy_risk_stack_validation_id=stack_validation_id,
        dataset_id=data_scope.dataset_id,
        data_scope=data_scope.to_dict(),
        status=status,
        summary=summary,
        symbol_metrics=symbol_metrics,
        exposure_summary=exposure_summary,
        risk_measure_summary=risk_measure_summary,
        artifact_paths=artifact_paths,
        warnings=tuple(ResearchIssue(code="portfolio_backtest_warning", message=warning) for warning in warnings),
        blockers=tuple(blockers),
    )
    run_ref_payload = {**run_ref.to_dict(), "artifact_paths": dict(artifact_paths)}
    if artifact_store is not None:
        bundle_payload = _db_portfolio_bundle_payload(
            run_ref=run_ref_payload,
            result=result,
            provenance=provenance,
            summary=summary,
            symbol_metrics=symbol_metrics,
            exposure_summary=exposure_summary,
            risk_decisions=risk_decisions,
            risk_limit_breaches=risk_limit_breaches,
            risk_measure_summary=risk_measure_summary,
        )
        stored_payload = {**run_ref_payload, "bundle": bundle_payload}
        record = artifact_store.save_artifact(
            artifact_type=PORTFOLIO_BACKTEST_RUN_REF,
            artifact_id=run_id,
            payload=stored_payload,
            status=status,
            metadata={
                "dataset_id": data_scope.dataset_id,
                "strategy_risk_stack_id": stack.manifest.stack_id,
                "strategy_risk_stack_validation_id": stack_validation_id,
            },
        )
        run_ref_payload = {**run_ref_payload, "uri": record.uri, "artifact_uris": {"portfolio_backtest_run_ref": record.uri}}
        run_ref_artifact = ArtifactReference(
            artifact_type=PORTFOLIO_BACKTEST_RUN_REF,
            uri=record.uri,
            metadata={
                "run_id": run_id,
                "dataset_id": data_scope.dataset_id,
                "strategy_risk_stack_id": stack.manifest.stack_id,
            },
        ).to_dict()
    else:
        run_ref_path = write_json_artifact(run_ref_payload, artifact_dir / "portfolio_backtest_run_ref.json")
        artifact_paths = {**artifact_paths, "portfolio_backtest_run_ref": str(run_ref_path)}
        run_ref_payload = {**run_ref_payload, "artifact_paths": artifact_paths}
        write_json_artifact(run_ref_payload, run_ref_path)
        run_ref_artifact = ArtifactReference(
            artifact_type=PORTFOLIO_BACKTEST_RUN_REF,
            path=run_ref_path,
            metadata={
                "run_id": run_id,
                "dataset_id": data_scope.dataset_id,
                "strategy_risk_stack_id": stack.manifest.stack_id,
            },
        ).to_dict()

    artifacts = {
        "portfolio_backtest_run_ref": run_ref_artifact
    }
    data = {
        "portfolio_backtest_run_ref": run_ref_payload,
        "summary": summary,
        "data_scope": data_scope.to_dict(),
        "symbol_metrics": symbol_metrics,
        "exposure_summary": exposure_summary,
        "risk_decisions": risk_decisions,
        "risk_limit_breaches": risk_limit_breaches,
        "risk_measure_summary": risk_measure_summary,
        "artifact_paths": dict(artifact_paths),
    }
    if blockers:
        return ToolEnvelope(
            ok=False,
            command=RESEARCH_RUN_PORTFOLIO_BACKTEST,
            agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
            side_effect=SideEffect.LOCAL_MUTATING,
            data=data,
            artifacts=artifacts,
            warnings=tuple(warnings),
            errors=({"code": blockers[0].code, "message": blockers[0].message},),
        )
    return success_envelope(
        command=RESEARCH_RUN_PORTFOLIO_BACKTEST,
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
    artifact_store: ResearchArtifactStore | None,
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
    if artifact_store is not None and candidate_id:
        return _ResolvedCandidate(
            StrategyCandidateManifest.from_dict(load_artifact_ref(artifact_store, STRATEGY_CANDIDATE, candidate_id)),
            None,
        )
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
    artifact_store: ResearchArtifactStore | None,
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
    if artifact_store is not None and validation_id:
        return _ResolvedValidationReport(
            load_artifact_ref(artifact_store, STRATEGY_CANDIDATE_VALIDATION_REPORT, validation_id),
            None,
        )
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
        raise ValueError("dataset_manifest.source_filter is not supported by research backtests yet")
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
    artifact_store: ResearchArtifactStore | None,
) -> None:
    template = get_strategy_template(candidate.template_family)
    if candidate.blockers:
        raise ValueError("strategy candidate manifest has blockers")
    if candidate.strategy_source is None:
        raise ValueError("strategy candidate strategy_source is required")
    _validate_source_hash(candidate.strategy_source, label="strategy", artifact_store=artifact_store)
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


def _instantiate_strategy(
    candidate: StrategyCandidateManifest,
    data_scope: BacktestDataScope,
    artifact_store: ResearchArtifactStore | None,
) -> Strategy:
    source_ref = candidate.strategy_source
    if source_ref is None:
        raise ValueError("strategy candidate strategy_source is required")
    module_name = f"_trader_backtest_strategy_{_module_suffix(candidate.candidate_id)}"
    _validate_source_hash(source_ref, label="strategy_source", artifact_store=artifact_store)
    module = _load_source_module(source_ref, module_name, artifact_store)
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


def _validate_source_hash(
    source_ref: StrategyCandidateSourceRef | RiskManagerCandidateSourceRef,
    *,
    label: str,
    artifact_store: ResearchArtifactStore | None,
) -> None:
    if source_ref.uri:
        if artifact_store is None:
            raise ValueError(f"{label} uri requires a configured research artifact store")
        payload = load_artifact_ref(artifact_store, source_ref.artifact_type, source_ref.uri)
        source_code = str(payload.get("source_code") or "")
        if not source_code:
            raise ValueError(f"{label} DB artifact source_code is required")
        if source_text_hash(source_code) != source_ref.source_hash:
            raise ValueError(f"{label} source_hash does not match DB source artifact")
        return
    if not source_ref.path:
        raise ValueError(f"{label} path or uri is required")
    source_path = Path(source_ref.path)
    if not source_path.exists():
        raise FileNotFoundError(f"{label} source file not found: {source_path}")
    if file_sha256(source_path) != source_ref.source_hash:
        raise ValueError(f"{label} source_hash does not match current source file")


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


def _resolve_stack_validation_report(
    *,
    artifact_root: str | Path,
    validation_id: str | None,
    validation_report_path: str | Path | None,
    strategy_risk_stack_validation_report: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore | None,
) -> _ResolvedValidationReport:
    sources = [
        bool(validation_id and validation_id.strip()),
        validation_report_path is not None and str(validation_report_path).strip() != "",
        strategy_risk_stack_validation_report is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError("exactly one strategy/risk stack validation report input is required")
    if strategy_risk_stack_validation_report is not None:
        return _ResolvedValidationReport(dict(strategy_risk_stack_validation_report), None)
    if artifact_store is not None and validation_id:
        return _ResolvedValidationReport(
            load_artifact_ref(artifact_store, STRATEGY_RISK_STACK_VALIDATION_REPORT, validation_id.strip()),
            None,
        )
    path = (
        strategy_risk_stack_validation_report_path(artifact_root, validation_id.strip())
        if validation_id
        else Path(str(validation_report_path))
    )
    if not path.exists():
        raise FileNotFoundError(f"strategy/risk stack validation report not found: {path}")
    return _ResolvedValidationReport(_read_json(path), path)


def _validate_stack_validation_report(report: Mapping[str, Any]) -> None:
    if report.get("artifact_type") != STRATEGY_RISK_STACK_VALIDATION_REPORT:
        raise ValueError("strategy/risk stack validation report artifact_type must be strategy_risk_stack_validation_report")
    if str(report.get("status") or "") != "passed":
        raise ValueError("strategy/risk stack validation report status must be passed")
    if _sequence(report.get("blockers")):
        raise ValueError("strategy/risk stack validation report must not contain blockers")
    if not str(report.get("validation_id") or "").strip():
        raise ValueError("strategy/risk stack validation report validation_id is required")
    if not str(report.get("stack_id") or "").strip():
        raise ValueError("strategy/risk stack validation report stack_id is required")


def _resolve_stack_from_validation_report(
    *,
    artifact_root: str | Path,
    validation_report: Mapping[str, Any],
    artifact_store: ResearchArtifactStore | None,
) -> _ResolvedStack:
    stack_id = str(validation_report.get("stack_id") or "").strip()
    if artifact_store is not None:
        manifest = StrategyRiskStackManifest.from_dict(
            load_artifact_ref(artifact_store, "strategy_risk_stack", stack_id)
        )
        if manifest.stack_id != stack_id:
            raise ValueError("strategy/risk stack validation report stack_id does not match stack manifest")
        _validate_stack_manifest_for_portfolio(manifest)
        return _ResolvedStack(manifest=manifest, path=None)
    path = strategy_risk_stack_manifest_path(artifact_root, stack_id)
    if not path.exists():
        raise FileNotFoundError(f"strategy/risk stack manifest not found: {path}")
    manifest = StrategyRiskStackManifest.from_dict(_read_json(path))
    if manifest.stack_id != stack_id:
        raise ValueError("strategy/risk stack validation report stack_id does not match stack manifest")
    _validate_stack_manifest_for_portfolio(manifest)
    return _ResolvedStack(manifest=manifest, path=path)


def _validate_stack_manifest_for_portfolio(manifest: StrategyRiskStackManifest) -> None:
    if manifest.blockers:
        raise ValueError("strategy/risk stack manifest has blockers")
    if manifest.status and manifest.status not in {"candidate", "validated"}:
        raise ValueError("strategy/risk stack manifest status is not usable for portfolio backtests")
    if manifest.strategy_candidate_ref.status != "validated":
        raise ValueError("strategy/risk stack strategy_candidate_ref status must be validated")
    if manifest.strategy_validation_report_ref is None:
        raise ValueError("strategy/risk stack strategy_validation_report_ref is required")
    if manifest.strategy_validation_report_ref.status != "passed":
        raise ValueError("strategy/risk stack strategy_validation_report_ref status must be passed")
    if not manifest.risk_manager_refs:
        raise ValueError("strategy/risk stack requires at least one risk manager")
    _validate_no_live_execution_assumptions(manifest.execution_assumptions, label="strategy/risk stack")


def _load_strategy_candidate_from_stack(
    artifact_root: str | Path,
    manifest: StrategyRiskStackManifest,
    artifact_store: ResearchArtifactStore | None,
) -> _ResolvedCandidate:
    ref = manifest.strategy_candidate_ref
    if artifact_store is not None:
        candidate = StrategyCandidateManifest.from_dict(
            load_artifact_ref(artifact_store, STRATEGY_CANDIDATE, ref.uri or ref.artifact_id)
        )
        if candidate.candidate_id != ref.artifact_id:
            raise ValueError("strategy/risk stack strategy candidate ref does not match loaded candidate")
        return _ResolvedCandidate(candidate, None)
    path = Path(ref.path) if ref.path else strategy_candidate_path(artifact_root, ref.artifact_id)
    if not path.exists():
        raise FileNotFoundError(f"strategy candidate manifest not found: {path}")
    candidate = StrategyCandidateManifest.from_dict(_read_json(path))
    if candidate.candidate_id != ref.artifact_id:
        raise ValueError("strategy/risk stack strategy candidate ref does not match loaded candidate")
    return _ResolvedCandidate(candidate, path)


def _load_strategy_validation_report_from_stack(
    artifact_root: str | Path,
    manifest: StrategyRiskStackManifest,
    artifact_store: ResearchArtifactStore | None,
) -> _ResolvedValidationReport:
    ref = manifest.strategy_validation_report_ref
    if ref is None:
        raise ValueError("strategy/risk stack strategy_validation_report_ref is required")
    if artifact_store is not None:
        report = load_artifact_ref(artifact_store, STRATEGY_CANDIDATE_VALIDATION_REPORT, ref.uri or ref.artifact_id)
        if str(report.get("validation_id") or "") != ref.artifact_id:
            raise ValueError("strategy validation report ref does not match loaded validation report")
        return _ResolvedValidationReport(report, None)
    path = Path(ref.path) if ref.path else strategy_candidate_validation_report_path(artifact_root, ref.artifact_id)
    if not path.exists():
        raise FileNotFoundError(f"strategy validation report not found: {path}")
    report = _read_json(path)
    if str(report.get("validation_id") or "") != ref.artifact_id:
        raise ValueError("strategy validation report ref does not match loaded validation report")
    return _ResolvedValidationReport(report, path)


def _load_risk_managers_from_stack(
    artifact_root: str | Path,
    manifest: StrategyRiskStackManifest,
    artifact_store: ResearchArtifactStore | None,
) -> tuple[_ResolvedRiskManager, ...]:
    resolved: list[_ResolvedRiskManager] = []
    for index, ref in enumerate(manifest.risk_manager_refs):
        if ref.status != "validated":
            raise ValueError(f"{ref.role} status must be validated")
        expected_role = f"risk_manager_{index}"
        if ref.role != expected_role:
            raise ValueError(f"risk manager ref at index {index} must have role={expected_role}")
        validation_ref = _mapping(ref.metadata.get("validation_report_ref"))
        if validation_ref.get("status") != "passed":
            raise ValueError(f"{ref.role} validation_report_ref.status must be passed")
        if artifact_store is not None:
            candidate = RiskManagerCandidateManifest.from_dict(
                load_artifact_ref(artifact_store, RISK_MANAGER_CANDIDATE, ref.uri or ref.artifact_id)
            )
            path = None
        else:
            path = Path(ref.path) if ref.path else risk_manager_candidate_path(artifact_root, ref.artifact_id)
            if not path.exists():
                raise FileNotFoundError(f"risk-manager candidate manifest not found: {path}")
            candidate = RiskManagerCandidateManifest.from_dict(_read_json(path))
        if candidate.candidate_id != ref.artifact_id:
            raise ValueError(f"{ref.role} ref does not match loaded risk-manager candidate")
        _validate_risk_manager_candidate_for_portfolio(candidate, index=index, artifact_store=artifact_store)
        manager = _instantiate_risk_manager_candidate(candidate, index=index, artifact_store=artifact_store)
        resolved.append(_ResolvedRiskManager(manifest=candidate, path=path, instance=manager))
    return tuple(resolved)


def _validate_portfolio_stack_inputs(
    *,
    stack: _ResolvedStack,
    strategy_candidate: StrategyCandidateManifest,
    risk_managers: Sequence[_ResolvedRiskManager],
) -> None:
    if stack.manifest.strategy_candidate_ref.artifact_id != strategy_candidate.candidate_id:
        raise ValueError("strategy/risk stack candidate ref does not match strategy candidate")
    if not risk_managers:
        raise ValueError("portfolio backtest requires at least one risk manager")
    risk_ids = [manager.manifest.candidate_id for manager in risk_managers]
    stack_ids = [ref.artifact_id for ref in stack.manifest.risk_manager_refs]
    if risk_ids != stack_ids:
        raise ValueError("strategy/risk stack risk manager order does not match loaded candidates")


def _validate_risk_manager_candidate_for_portfolio(
    candidate: RiskManagerCandidateManifest,
    *,
    index: int,
    artifact_store: ResearchArtifactStore | None,
) -> None:
    if candidate.blockers:
        raise ValueError(f"risk_manager_{index} candidate manifest has blockers")
    if candidate.risk_manager_source is None:
        raise ValueError(f"risk_manager_{index} risk_manager_source is required")
    source_ref = candidate.risk_manager_source
    _validate_source_hash(source_ref, label=f"risk_manager_{index}", artifact_store=artifact_store)
    if source_ref.runtime_contract != "trader.risk.RiskManager":
        raise ValueError(f"risk_manager_{index} source runtime_contract must be trader.risk.RiskManager")
    _validate_no_live_execution_assumptions(candidate.execution_assumptions, label=f"risk_manager_{index}")


def _validate_no_live_execution_assumptions(assumptions: Mapping[str, Any], *, label: str) -> None:
    if assumptions.get("backtest_only") is False:
        raise ValueError(f"{label} execution_assumptions.backtest_only must remain true")
    for flag in ("broker_mutation_allowed", "live_trading_allowed", "raw_sql_allowed"):
        if _truthy(assumptions.get(flag)):
            raise ValueError(f"{label} execution_assumptions.{flag} must remain false")


def _instantiate_risk_manager_candidate(
    candidate: RiskManagerCandidateManifest,
    *,
    index: int,
    artifact_store: ResearchArtifactStore | None,
) -> RiskManager:
    source_ref = candidate.risk_manager_source
    if source_ref is None:
        raise ValueError(f"risk_manager_{index} risk_manager_source is required")
    module = _load_source_module(
        source_ref,
        f"_trader_portfolio_risk_{index}_{_module_suffix(candidate.candidate_id)}",
        artifact_store,
    )
    if not hasattr(module, source_ref.class_name):
        raise ValueError(f"risk_manager_{index} source class not found: {source_ref.class_name}")
    factory = getattr(module, source_ref.factory_name, None)
    if factory is None:
        raise ValueError(f"risk_manager_{index} source factory not found: {source_ref.factory_name}")
    manager = factory()
    if not isinstance(manager, RiskManager):
        raise ValueError(f"risk_manager_{index} source factory did not return a trader.risk.RiskManager")
    return manager


def _load_source_module(
    source_ref: StrategyCandidateSourceRef | RiskManagerCandidateSourceRef,
    module_name: str,
    artifact_store: ResearchArtifactStore | None,
) -> object:
    if source_ref.uri:
        if artifact_store is None:
            raise ValueError("source uri requires a configured research artifact store")
        payload = load_artifact_ref(artifact_store, source_ref.artifact_type, source_ref.uri)
        source_code = str(payload.get("source_code") or "")
        if not source_code:
            raise ValueError("source DB artifact source_code is required")
        return load_module_from_source(module_name, source_code, filename=source_ref.uri)
    if not source_ref.path:
        raise ValueError("source path or uri is required")
    source_path = Path(source_ref.path)
    spec = importlib_util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load source module: {source_path}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _portfolio_symbol_metrics(result: BacktestResult) -> dict[str, Any]:
    metrics: dict[str, dict[str, Any]] = {
        symbol: {
            "trade_count": 0,
            "buy_qty": 0.0,
            "sell_qty": 0.0,
            "buy_notional": 0.0,
            "sell_notional": 0.0,
            "gross_notional": 0.0,
            "fees": 0.0,
            "slippage": 0.0,
            "realized_pnl": 0.0,
            "realized_return": None,
            "final_qty": 0.0,
            "final_avg_price": None,
            "final_last_price": None,
            "final_market_value": None,
            "final_abs_notional": 0.0,
            "final_weight": None,
            "final_abs_weight": None,
            "unrealized_pnl": None,
        }
        for symbol in sorted(result.symbols)
    }
    for trade in result.trades:
        row = metrics.setdefault(
            trade.symbol,
            {
                "trade_count": 0,
                "buy_qty": 0.0,
                "sell_qty": 0.0,
                "buy_notional": 0.0,
                "sell_notional": 0.0,
                "gross_notional": 0.0,
                "fees": 0.0,
                "slippage": 0.0,
                "realized_pnl": 0.0,
                "realized_return": None,
                "final_qty": 0.0,
                "final_avg_price": None,
                "final_last_price": None,
                "final_market_value": None,
                "final_abs_notional": 0.0,
                "final_weight": None,
                "final_abs_weight": None,
                "unrealized_pnl": None,
            },
        )
        notional = abs(float(trade.notional or 0.0))
        qty = abs(float(trade.fill_qty or 0.0))
        row["trade_count"] += 1
        row["gross_notional"] += notional
        row["fees"] += float(trade.fee_amount or 0.0)
        row["slippage"] += float(trade.slippage_amount or 0.0)
        row["realized_pnl"] += float(trade.realized_pnl or 0.0)
        if str(trade.side).lower() == "buy":
            row["buy_qty"] += qty
            row["buy_notional"] += notional
        elif str(trade.side).lower() == "sell":
            row["sell_qty"] += qty
            row["sell_notional"] += notional
    final_portfolio_value = _optional_float(result.strategy_performance.end_equity)
    for position in result.positions:
        row = metrics.setdefault(position.symbol, {})
        market_value = _optional_float(position.market_value)
        row.update(
            {
                "final_qty": position.qty,
                "final_avg_price": position.avg_price,
                "final_last_price": position.last_price,
                "final_market_value": market_value,
                "final_abs_notional": abs(market_value) if market_value is not None else 0.0,
                "unrealized_pnl": position.unrealized_pnl,
            }
        )
        if market_value is not None and final_portfolio_value not in {None, 0.0}:
            row["final_weight"] = market_value / float(final_portfolio_value)
            row["final_abs_weight"] = abs(market_value) / abs(float(final_portfolio_value))
    for row in metrics.values():
        buy_notional = _optional_float(row.get("buy_notional"))
        realized_pnl = _optional_float(row.get("realized_pnl"))
        if buy_notional is not None and buy_notional > 0 and realized_pnl is not None:
            row["realized_return"] = realized_pnl / buy_notional
    return {symbol: _jsonable(metrics[symbol]) for symbol in sorted(metrics)}


def _portfolio_exposure_summary(
    result: BacktestResult,
    symbol_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    performance = result.strategy_performance
    final_weights = [
        weight
        for weight in (_optional_float(_mapping(row).get("final_abs_weight")) for row in symbol_metrics.values())
        if weight is not None
    ]
    symbols_with_exposure = sum(
        1
        for row in symbol_metrics.values()
        if abs(float(_mapping(row).get("final_qty") or 0.0)) > 0.0
    )
    return {
        "position_count": result.position_count,
        "long_positions": result.long_positions,
        "short_positions": result.short_positions,
        "symbols_with_exposure": symbols_with_exposure,
        "net_qty": result.net_qty,
        "gross_qty": result.gross_qty,
        "final_net_notional": result.net_notional,
        "final_gross_notional": result.gross_notional,
        "avg_net_exposure": performance.avg_net_exposure,
        "avg_gross_exposure": performance.avg_gross_exposure,
        "avg_invested_pct": performance.avg_invested_pct,
        "max_drawdown": performance.max_drawdown,
        "final_portfolio_value": performance.end_equity,
        "max_final_symbol_weight": max(final_weights) if final_weights else None,
        "symbol_weights": {
            symbol: _mapping(row).get("final_weight")
            for symbol, row in symbol_metrics.items()
            if _mapping(row).get("final_weight") is not None
        },
    }


def _risk_decision_summary(
    decisions: Sequence[Mapping[str, Any]],
    risk_managers: Sequence[_ResolvedRiskManager],
) -> dict[str, Any]:
    rejected_count = sum(int(decision.get("rejected_count") or 0) for decision in decisions)
    return {
        "manager_count": len(risk_managers),
        "decision_count": len(decisions),
        "approved_decision_count": sum(1 for decision in decisions if int(decision.get("approved_count") or 0) > 0),
        "rejected_order_count": rejected_count,
        "managers": [
            {
                "manager_index": index,
                "risk_manager_candidate_id": resolved.manifest.candidate_id,
                "template_family": resolved.manifest.template_family,
                "source_path": str(resolved.path) if resolved.path is not None else None,
                "source_uri": (
                    resolved.manifest.risk_manager_source.uri
                    if resolved.manifest.risk_manager_source is not None
                    else None
                ),
            }
            for index, resolved in enumerate(risk_managers)
        ],
        "decisions": [_jsonable(decision) for decision in decisions],
    }


def _risk_measure_summary(
    result: BacktestResult,
    risk_managers: Sequence[_ResolvedRiskManager],
    exposure_summary: Mapping[str, Any],
    symbol_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    available_telemetry = _available_risk_telemetry(result, exposure_summary, symbol_metrics)
    manager_requirements: list[dict[str, Any]] = []
    missing_required: set[str] = set()
    for resolved in risk_managers:
        required = _required_telemetry(resolved.manifest)
        missing = [name for name in required if name not in available_telemetry]
        missing_required.update(missing)
        manager_requirements.append(
            {
                "risk_manager_candidate_id": resolved.manifest.candidate_id,
                "template_family": resolved.manifest.template_family,
                "required_telemetry": required,
                "available_telemetry": sorted(name for name in required if name in available_telemetry),
                "missing_telemetry": sorted(missing),
                "method_package_refs": [ref.to_dict() for ref in resolved.manifest.method_package_refs],
            }
        )
    return {
        "available_telemetry": sorted(available_telemetry),
        "missing_required_telemetry": sorted(missing_required),
        "manager_requirements": manager_requirements,
        "var": None,
        "cvar": None,
        "note": "VaR/CVaR estimates are pass-through only in this slice and remain null unless supplied evidence exists.",
    }


def _available_risk_telemetry(
    result: BacktestResult,
    exposure_summary: Mapping[str, Any],
    symbol_metrics: Mapping[str, Any],
) -> set[str]:
    available: set[str] = set()
    if exposure_summary.get("final_gross_notional") is not None or exposure_summary.get("avg_gross_exposure") is not None:
        available.add("gross_exposure")
    if symbol_metrics:
        available.add("per_symbol_exposure")
    if exposure_summary.get("final_portfolio_value") is not None:
        available.add("portfolio_value")
    if result.equity_curve:
        available.add("equity_curve")
    if result.strategy_performance.max_drawdown is not None:
        available.add("drawdown")
    if len(result.equity_curve) >= 2:
        available.add("portfolio_returns")
    return available


def _required_telemetry(candidate: RiskManagerCandidateManifest) -> list[str]:
    return sorted(str(item) for item in _sequence(candidate.execution_assumptions.get("telemetry_required")) if str(item))


def _risk_limit_breach_summary(
    *,
    risk_decisions: Mapping[str, Any],
    risk_managers: Sequence[_ResolvedRiskManager],
    exposure_summary: Mapping[str, Any],
    symbol_metrics: Mapping[str, Any],
    risk_measure_summary: Mapping[str, Any],
) -> dict[str, Any]:
    breaches: list[dict[str, Any]] = []
    for decision in _mapping_sequence(risk_decisions.get("decisions")):
        for order in _mapping_sequence(decision.get("rejected_orders")):
            breaches.append(
                {
                    "source": "risk_manager_rejection",
                    "risk_manager_candidate_id": decision.get("risk_manager_candidate_id"),
                    "template_family": decision.get("template_family"),
                    "run_id": decision.get("run_id"),
                    "cycle_id": decision.get("cycle_id"),
                    "decision_ts": decision.get("decision_ts"),
                    "symbol": order.get("symbol"),
                    "side": order.get("side"),
                    "qty": order.get("qty"),
                    "rejection_reason": order.get("rejection_reason"),
                }
            )
    for resolved in risk_managers:
        breaches.extend(
            _threshold_breaches(
                resolved.manifest,
                exposure_summary=exposure_summary,
                symbol_metrics=symbol_metrics,
                risk_measure_summary=risk_measure_summary,
            )
        )
    return {"breach_count": len(breaches), "breaches": _jsonable(breaches)}


def _threshold_breaches(
    candidate: RiskManagerCandidateManifest,
    *,
    exposure_summary: Mapping[str, Any],
    symbol_metrics: Mapping[str, Any],
    risk_measure_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    family = candidate.template_family
    params = candidate.parameters
    breaches: list[dict[str, Any]] = []
    if family == "gross_exposure_cap":
        cap = _optional_float(params.get("max_gross_exposure"))
        value = _optional_float(exposure_summary.get("final_gross_notional"))
        if cap is not None and value is not None and value > cap:
            breaches.append(_threshold_breach(candidate, "max_gross_exposure", value, cap))
    elif family == "per_symbol_exposure_cap":
        cap = _optional_float(params.get("max_symbol_exposure"))
        if cap is not None:
            for symbol, row in symbol_metrics.items():
                value = _optional_float(_mapping(row).get("final_abs_notional"))
                if value is not None and value > cap:
                    breaches.append(_threshold_breach(candidate, "max_symbol_exposure", value, cap, symbol=symbol))
    elif family == "concentration_cap":
        cap = _optional_float(params.get("max_symbol_weight"))
        value = _optional_float(exposure_summary.get("max_final_symbol_weight"))
        if cap is not None and value is not None and value > cap:
            breaches.append(_threshold_breach(candidate, "max_symbol_weight", value, cap))
    elif family == "drawdown_guard":
        cap = _optional_float(params.get("max_drawdown_fraction"))
        value = _optional_float(exposure_summary.get("max_drawdown"))
        if cap is not None and value is not None and value > cap:
            breaches.append(_threshold_breach(candidate, "max_drawdown_fraction", value, cap))
    elif family == "var_cvar_limit":
        for metric, cap_key in (("var", "max_var_fraction"), ("cvar", "max_cvar_fraction")):
            cap = _optional_float(params.get(cap_key))
            value = _optional_float(risk_measure_summary.get(metric))
            if cap is not None and value is not None and value > cap:
                breaches.append(_threshold_breach(candidate, cap_key, value, cap))
    return breaches


def _threshold_breach(
    candidate: RiskManagerCandidateManifest,
    limit_name: str,
    observed_value: float,
    limit_value: float,
    *,
    symbol: str | None = None,
) -> dict[str, Any]:
    payload = {
        "source": "derived_threshold_check",
        "risk_manager_candidate_id": candidate.candidate_id,
        "template_family": candidate.template_family,
        "limit_name": limit_name,
        "observed_value": observed_value,
        "limit_value": limit_value,
    }
    if symbol is not None:
        payload["symbol"] = symbol
    return payload


def _build_portfolio_provenance(
    *,
    config: Config,
    stack: _ResolvedStack,
    stack_validation_report: _ResolvedValidationReport,
    strategy_candidate: _ResolvedCandidate,
    strategy_validation_report: _ResolvedValidationReport,
    risk_managers: Sequence[_ResolvedRiskManager],
    data_scope: BacktestDataScope,
    data_quality_report: Mapping[str, Any] | None,
    assumptions: Mapping[str, Any],
    initial_cash: float,
    initial_positions: Sequence[Position],
    max_runs: int | None,
    status: str,
    artifact_dir: Path,
    risk_measure_summary: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_type": "portfolio_backtest_provenance",
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "strategy_risk_stack_id": stack.manifest.stack_id,
        "strategy_risk_stack_ref": {
            "path": str(stack.path) if stack.path is not None else None,
            "manifest": stack.manifest.to_dict(),
        },
        "strategy_risk_stack_validation_id": stack_validation_report.report.get("validation_id"),
        "strategy_risk_stack_validation_ref": {
            "path": str(stack_validation_report.path) if stack_validation_report.path is not None else None,
            "status": stack_validation_report.report.get("status"),
        },
        "candidate_id": strategy_candidate.manifest.candidate_id,
        "candidate_ref": {
            "path": str(strategy_candidate.path) if strategy_candidate.path is not None else None,
            "template_family": strategy_candidate.manifest.template_family,
            "strategy_source": (
                strategy_candidate.manifest.strategy_source.to_dict()
                if strategy_candidate.manifest.strategy_source is not None
                else None
            ),
        },
        "validation_id": strategy_validation_report.report.get("validation_id"),
        "validation_ref": {
            "path": str(strategy_validation_report.path) if strategy_validation_report.path is not None else None,
            "status": strategy_validation_report.report.get("status"),
        },
        "risk_manager_refs": [
            {
                "candidate_id": resolved.manifest.candidate_id,
                "template_family": resolved.manifest.template_family,
                "path": str(resolved.path),
                "risk_manager_source": (
                    resolved.manifest.risk_manager_source.to_dict()
                    if resolved.manifest.risk_manager_source is not None
                    else None
                ),
                "parameters": _jsonable(resolved.manifest.parameters),
                "execution_assumptions": _jsonable(resolved.manifest.execution_assumptions),
            }
            for resolved in risk_managers
        ],
        "dataset_id": data_scope.dataset_id,
        "data_scope": data_scope.to_dict(),
        "data_quality_report": _jsonable(data_quality_report),
        "assumptions": _jsonable(assumptions),
        "initial_cash": initial_cash,
        "initial_positions": [position.__dict__ for position in initial_positions],
        "max_runs": max_runs,
        "risk_measure_summary": _jsonable(risk_measure_summary),
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


def _portfolio_bundle_paths(bundle_dir: Path) -> dict[str, Any]:
    paths = _bundle_paths(bundle_dir)
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
    return paths


def _db_portfolio_bundle_payload(
    *,
    run_ref: Mapping[str, Any],
    result: BacktestResult,
    provenance: Mapping[str, Any],
    summary: Mapping[str, Any],
    symbol_metrics: Mapping[str, Any],
    exposure_summary: Mapping[str, Any],
    risk_decisions: Mapping[str, Any],
    risk_limit_breaches: Mapping[str, Any],
    risk_measure_summary: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "backtest_kind": "portfolio",
        "portfolio_backtest_run_ref": _jsonable(run_ref),
        "result": serialize_backtest_result(result),
        "metrics": _jsonable(summary),
        "provenance": _jsonable(provenance),
        "equity_curve": _jsonable(_build_equity_curve_csv_rows(result)),
        "trades": _jsonable(_build_trade_csv_rows(result.trades)),
        "positions": _jsonable([asdict(position) for position in result.positions]),
        "symbol_metrics": _jsonable(symbol_metrics),
        "exposure_summary": _jsonable(exposure_summary),
        "risk_decisions": _jsonable(risk_decisions),
        "risk_limit_breaches": _jsonable(risk_limit_breaches),
        "risk_measure_summary": _jsonable(risk_measure_summary),
    }


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


def _order_ids(orders: Sequence[Mapping[str, object]]) -> list[str]:
    return [str(order.get("client_order_id")) for order in orders if order.get("client_order_id") is not None]


def _order_evidence(order: Mapping[str, object]) -> dict[str, Any]:
    keys = (
        "client_order_id",
        "symbol",
        "side",
        "qty",
        "order_type",
        "rejection_reason",
        "created_at",
        "cycle_id",
    )
    return {key: _jsonable(order.get(key)) for key in keys if order.get(key) is not None}


def _run_error(*, code: str, message: str, data: Mapping[str, Any] | None = None) -> ToolEnvelope:
    return error_envelope(
        command=RESEARCH_RUN_BACKTEST,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
        data=data,
    )


def _portfolio_run_error(*, code: str, message: str, data: Mapping[str, Any] | None = None) -> ToolEnvelope:
    return error_envelope(
        command=RESEARCH_RUN_PORTFOLIO_BACKTEST,
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


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


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
