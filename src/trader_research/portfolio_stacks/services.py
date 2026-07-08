"""Strategy/risk stack composition and validation services."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader.event_store import EventStore
from trader.portfolio import Portfolio, Position
from trader.risk import RiskContext, RiskManager, RiskPipeline
from trader.signals import Bar
from trader.strategies import Strategy

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
    QUANT_RESEARCH_SUPERVISOR_OWNER,
    RISK_MANAGER_CANDIDATE,
    RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
    STRATEGY_CANDIDATE,
    STRATEGY_CANDIDATE_VALIDATION_REPORT,
    STRATEGY_RISK_STACK,
    STRATEGY_RISK_STACK_VALIDATION_REPORT,
    RiskManagerCandidateManifest,
    RiskManagerCandidateSourceRef,
    StrategyCandidateArtifactLink,
    StrategyCandidateManifest,
    StrategyCandidateSourceRef,
    StrategyRiskStackManifest,
    stable_research_id,
)
from trader_research.method_implementations.io import file_sha256
from trader_research.risk_managers import (
    risk_manager_candidate_path,
    risk_manager_candidate_validation_report_path,
)
from trader_research.strategy_candidates import (
    strategy_candidate_path,
    strategy_candidate_validation_report_path,
)


RESEARCH_CREATE_STRATEGY_RISK_STACK = "research_create_strategy_risk_stack"
RESEARCH_VALIDATE_STRATEGY_RISK_STACK = "research_validate_strategy_risk_stack"
STACK_VALIDATION_FIXTURE_ID = "strategy_risk_stack_smoke_v1"
FIXTURE_SYMBOLS = ("SYNTH_A", "SYNTH_B", "SYNTH_C")
FIXTURE_ASSET_CLASS = "stocks"
FIXTURE_TIMEFRAME = "1Min"
SYNTHETIC_BAR_COUNT = 160


@dataclass(frozen=True)
class _ResolvedReport:
    """Resolved validation report payload plus optional artifact path."""

    report: Mapping[str, Any]
    path: Path | None


@dataclass(frozen=True)
class _ResolvedStack:
    """Resolved stack manifest plus optional artifact path."""

    manifest: StrategyRiskStackManifest
    path: Path | None


def create_strategy_risk_stack(
    *,
    artifact_root: str | Path,
    strategy_validation_id: str | None = None,
    strategy_validation_report_path: str | Path | None = None,
    strategy_candidate_validation_report: Mapping[str, Any] | None = None,
    risk_manager_validation_refs: Sequence[Mapping[str, Any]] = (),
    execution_assumptions: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Compose one validated strategy candidate with ordered risk managers.

    Args:
        artifact_root: Root directory for local research artifacts.
        strategy_validation_id: Optional persisted strategy validation ID.
        strategy_validation_report_path: Optional path to a strategy validation report.
        strategy_candidate_validation_report: Optional inline strategy validation report.
        risk_manager_validation_refs: Ordered risk-manager validation refs. Each
            item must provide exactly one of `validation_id`, `path`, or
            `risk_manager_candidate_validation_report`.
        execution_assumptions: Optional stack-level execution-boundary assumptions.

    Returns:
        Local-mutating envelope containing `strategy_risk_stack_manifest`.
    """
    try:
        strategy_report = _resolve_strategy_validation_report(
            artifact_root=artifact_root,
            validation_id=strategy_validation_id,
            path=strategy_validation_report_path,
            report=strategy_candidate_validation_report,
            artifact_store=artifact_store,
        )
        risk_reports = _resolve_risk_manager_validation_reports(
            artifact_root=artifact_root,
            refs=risk_manager_validation_refs,
            artifact_store=artifact_store,
        )
        strategy_candidate = _load_strategy_candidate_for_report(artifact_root, strategy_report.report, artifact_store)
        risk_candidates = tuple(
            _load_risk_manager_candidate_for_report(artifact_root, resolved.report, artifact_store)
            for resolved in risk_reports
        )
        _validate_stack_builder_inputs(strategy_report, risk_reports, strategy_candidate, risk_candidates)
        normalized_execution_assumptions = _normalize_execution_assumptions(execution_assumptions)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return error_envelope(
            command=RESEARCH_CREATE_STRATEGY_RISK_STACK,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="strategy_risk_stack_creation_failed",
            message=str(exc),
        )

    stack_id = _stack_id(
        strategy_report=strategy_report,
        risk_reports=risk_reports,
        execution_assumptions=normalized_execution_assumptions,
    )
    manifest = StrategyRiskStackManifest(
        stack_id=stack_id,
        strategy_candidate_ref=_strategy_candidate_link(
            strategy_candidate,
            strategy_report=strategy_report,
            artifact_root=artifact_root,
            artifact_store=artifact_store,
        ),
        strategy_validation_report_ref=_strategy_validation_link(strategy_report),
        risk_manager_refs=tuple(
            _risk_manager_candidate_link(
                candidate,
                validation_report=risk_reports[index],
                artifact_root=artifact_root,
                index=index,
                artifact_store=artifact_store,
            )
            for index, candidate in enumerate(risk_candidates)
        ),
        execution_assumptions=normalized_execution_assumptions,
        status="candidate",
    )
    manifest_payload = manifest.to_dict()
    if artifact_store is not None:
        record = artifact_store.save_artifact(
            artifact_type=STRATEGY_RISK_STACK,
            artifact_id=stack_id,
            payload=manifest_payload,
            status=manifest.status,
            metadata={"risk_manager_count": len(risk_candidates)},
        )
        stack_ref = ArtifactReference(
            artifact_type=STRATEGY_RISK_STACK,
            uri=record.uri,
            metadata={
                "id": stack_id,
                "strategy_candidate_id": strategy_candidate.candidate_id,
                "risk_manager_count": len(risk_candidates),
            },
        ).to_dict()
    else:
        manifest_path = write_json_artifact(manifest_payload, strategy_risk_stack_manifest_path(artifact_root, stack_id))
        stack_ref = ArtifactReference(
            artifact_type=STRATEGY_RISK_STACK,
            path=manifest_path,
            metadata={
                "id": stack_id,
                "strategy_candidate_id": strategy_candidate.candidate_id,
                "risk_manager_count": len(risk_candidates),
            },
        ).to_dict()
    return success_envelope(
        command=RESEARCH_CREATE_STRATEGY_RISK_STACK,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"strategy_risk_stack_manifest": manifest_payload},
        artifacts={"strategy_risk_stack": stack_ref},
    )


def validate_strategy_risk_stack(
    *,
    artifact_root: str | Path,
    stack_id: str | None = None,
    path: str | Path | None = None,
    strategy_risk_stack_manifest: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Validate one strategy/risk stack before portfolio backtests can consume it.

    Args:
        artifact_root: Root directory for local research artifacts.
        stack_id: Optional persisted stack ID.
        path: Optional path to a `strategy_risk_stack_manifest.json`.
        strategy_risk_stack_manifest: Optional inline stack manifest.

    Returns:
        Local-mutating envelope with a persisted validation report.
    """
    try:
        stack = _resolve_stack(
            artifact_root=artifact_root,
            stack_id=stack_id,
            path=path,
            strategy_risk_stack_manifest=strategy_risk_stack_manifest,
            artifact_store=artifact_store,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return error_envelope(
            command=RESEARCH_VALIDATE_STRATEGY_RISK_STACK,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="strategy_risk_stack_resolution_failed",
            message=str(exc),
        )

    report, report_path = _build_stack_validation_report(
        artifact_root=artifact_root,
        stack=stack,
        artifact_store=artifact_store,
    )
    artifacts = {
        "strategy_risk_stack_validation_report": _stack_validation_ref(report, report_path, artifact_store)
    }
    if report["status"] == "passed":
        return success_envelope(
            command=RESEARCH_VALIDATE_STRATEGY_RISK_STACK,
            side_effect=SideEffect.LOCAL_MUTATING,
            data={"strategy_risk_stack_validation_report": report},
            artifacts=artifacts,
            warnings=tuple(str(item) for item in report["warnings"]),
        )
    return ToolEnvelope(
        ok=False,
        command=RESEARCH_VALIDATE_STRATEGY_RISK_STACK,
        agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"strategy_risk_stack_validation_report": report},
        artifacts=artifacts,
        warnings=tuple(str(item) for item in report["warnings"]),
        errors=(
            {
                "code": "strategy_risk_stack_validation_failed",
                "message": "Strategy/risk stack validation failed",
            },
        ),
    )


def strategy_risk_stack_manifest_path(artifact_root: str | Path, stack_id: str) -> Path:
    """Return the deterministic path for one strategy/risk stack manifest."""
    return Path(artifact_root) / "portfolio_stacks" / "manifests" / f"{stack_id}.json"


def strategy_risk_stack_validation_report_path(artifact_root: str | Path, validation_id: str) -> Path:
    """Return the deterministic path for one strategy/risk stack validation report."""
    return Path(artifact_root) / "portfolio_stacks" / "validation_reports" / f"{validation_id}.json"


def _resolve_strategy_validation_report(
    *,
    artifact_root: str | Path,
    validation_id: str | None,
    path: str | Path | None,
    report: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore | None,
) -> _ResolvedReport:
    sources = [
        validation_id is not None and str(validation_id).strip() != "",
        path is not None and str(path).strip() != "",
        report is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError(
            "exactly one of strategy_validation_id, strategy_validation_report_path, "
            "or strategy_candidate_validation_report is required"
        )
    if report is not None:
        return _ResolvedReport(dict(report), None)
    if validation_id is not None and str(validation_id).strip():
        if artifact_store is not None:
            return _ResolvedReport(
                load_artifact_ref(artifact_store, STRATEGY_CANDIDATE_VALIDATION_REPORT, str(validation_id).strip()),
                None,
            )
        report_path = strategy_candidate_validation_report_path(artifact_root, str(validation_id).strip())
        return _ResolvedReport(_read_json(report_path), report_path)
    report_path = Path(str(path))
    return _ResolvedReport(_read_json(report_path), report_path)


def _resolve_risk_manager_validation_reports(
    *,
    artifact_root: str | Path,
    refs: Sequence[Mapping[str, Any]],
    artifact_store: ResearchArtifactStore | None,
) -> tuple[_ResolvedReport, ...]:
    if isinstance(refs, MappingABC) or isinstance(refs, (str, bytes)):
        raise ValueError("risk_manager_validation_refs must be a sequence of validation refs")
    if not refs:
        raise ValueError("at least one risk_manager_validation_ref is required")
    resolved: list[_ResolvedReport] = []
    for index, ref in enumerate(refs):
        if not isinstance(ref, MappingABC):
            raise ValueError(f"risk_manager_validation_refs[{index}] must be a mapping")
        source_keys = [
            key
            for key in ("validation_id", "path", "risk_manager_candidate_validation_report")
            if ref.get(key) is not None
        ]
        if len(source_keys) != 1:
            raise ValueError(
                f"risk_manager_validation_refs[{index}] must provide exactly one of validation_id, path, "
                "or risk_manager_candidate_validation_report"
            )
        if ref.get("risk_manager_candidate_validation_report") is not None:
            payload = ref["risk_manager_candidate_validation_report"]
            if not isinstance(payload, MappingABC):
                raise ValueError(
                    f"risk_manager_validation_refs[{index}].risk_manager_candidate_validation_report must be a mapping"
                )
            resolved.append(_ResolvedReport(dict(payload), None))
            continue
        if ref.get("validation_id") is not None:
            validation_id = str(ref.get("validation_id") or "").strip()
            if not validation_id:
                raise ValueError(f"risk_manager_validation_refs[{index}].validation_id is required")
            if artifact_store is not None:
                resolved.append(
                    _ResolvedReport(
                        load_artifact_ref(artifact_store, RISK_MANAGER_CANDIDATE_VALIDATION_REPORT, validation_id),
                        None,
                    )
                )
                continue
            report_path = risk_manager_candidate_validation_report_path(artifact_root, validation_id)
            resolved.append(_ResolvedReport(_read_json(report_path), report_path))
            continue
        report_path = Path(str(ref.get("path") or ""))
        if not str(report_path):
            raise ValueError(f"risk_manager_validation_refs[{index}].path is required")
        resolved.append(_ResolvedReport(_read_json(report_path), report_path))
    return tuple(resolved)


def _resolve_stack(
    *,
    artifact_root: str | Path,
    stack_id: str | None,
    path: str | Path | None,
    strategy_risk_stack_manifest: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore | None,
) -> _ResolvedStack:
    sources = [
        stack_id is not None and str(stack_id).strip() != "",
        path is not None and str(path).strip() != "",
        strategy_risk_stack_manifest is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError("exactly one of stack_id, path, or strategy_risk_stack_manifest is required")
    if strategy_risk_stack_manifest is not None:
        return _ResolvedStack(StrategyRiskStackManifest.from_dict(strategy_risk_stack_manifest), None)
    if stack_id is not None and str(stack_id).strip():
        if artifact_store is not None:
            return _ResolvedStack(
                StrategyRiskStackManifest.from_dict(
                    load_artifact_ref(artifact_store, STRATEGY_RISK_STACK, str(stack_id).strip())
                ),
                None,
            )
        stack_path = strategy_risk_stack_manifest_path(artifact_root, str(stack_id).strip())
        return _ResolvedStack(StrategyRiskStackManifest.from_dict(_read_json(stack_path)), stack_path)
    stack_path = Path(str(path))
    return _ResolvedStack(StrategyRiskStackManifest.from_dict(_read_json(stack_path)), stack_path)


def _load_strategy_candidate_for_report(
    artifact_root: str | Path,
    report: Mapping[str, Any],
    artifact_store: ResearchArtifactStore | None,
) -> StrategyCandidateManifest:
    candidate_id = str(report.get("candidate_id") or "").strip()
    if not candidate_id:
        raise ValueError("strategy validation report candidate_id is required")
    if artifact_store is not None:
        return StrategyCandidateManifest.from_dict(
            load_artifact_ref(artifact_store, STRATEGY_CANDIDATE, candidate_id)
        )
    return StrategyCandidateManifest.from_dict(_read_json(strategy_candidate_path(artifact_root, candidate_id)))


def _load_risk_manager_candidate_for_report(
    artifact_root: str | Path,
    report: Mapping[str, Any],
    artifact_store: ResearchArtifactStore | None,
) -> RiskManagerCandidateManifest:
    candidate_id = str(report.get("candidate_id") or "").strip()
    if not candidate_id:
        raise ValueError("risk-manager validation report candidate_id is required")
    if artifact_store is not None:
        return RiskManagerCandidateManifest.from_dict(
            load_artifact_ref(artifact_store, RISK_MANAGER_CANDIDATE, candidate_id)
        )
    manifest_ref = _mapping(report.get("candidate_manifest_ref"))
    ref_path = str(manifest_ref.get("path") or "").strip()
    path = Path(ref_path) if ref_path else risk_manager_candidate_path(artifact_root, candidate_id)
    return RiskManagerCandidateManifest.from_dict(_read_json(path))


def _validate_stack_builder_inputs(
    strategy_report: _ResolvedReport,
    risk_reports: Sequence[_ResolvedReport],
    strategy_candidate: StrategyCandidateManifest,
    risk_candidates: Sequence[RiskManagerCandidateManifest],
) -> None:
    _require_passed_report(
        strategy_report.report,
        artifact_type=STRATEGY_CANDIDATE_VALIDATION_REPORT,
        label="strategy validation report",
    )
    if str(strategy_report.report.get("candidate_id") or "") != strategy_candidate.candidate_id:
        raise ValueError("strategy validation report candidate_id does not match strategy candidate")
    seen_risk_candidates: set[str] = set()
    for index, resolved in enumerate(risk_reports):
        _require_passed_report(
            resolved.report,
            artifact_type=RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
            label=f"risk-manager validation report {index}",
        )
        candidate = risk_candidates[index]
        if str(resolved.report.get("candidate_id") or "") != candidate.candidate_id:
            raise ValueError(f"risk-manager validation report {index} candidate_id does not match candidate")
        if candidate.candidate_id in seen_risk_candidates:
            raise ValueError(f"duplicate risk-manager candidate_id: {candidate.candidate_id}")
        seen_risk_candidates.add(candidate.candidate_id)


def _require_passed_report(report: Mapping[str, Any], *, artifact_type: str, label: str) -> None:
    if str(report.get("artifact_type") or "") != artifact_type:
        raise ValueError(f"{label} artifact_type must be {artifact_type}")
    if str(report.get("status") or "") != "passed":
        raise ValueError(f"{label} status must be passed")
    blockers = _sequence(report.get("blockers"))
    if blockers:
        raise ValueError(f"{label} blockers must be empty")


def _normalize_execution_assumptions(execution_assumptions: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(execution_assumptions or {})
    normalized = {
        "backtest_only": True,
        "broker_mutation_allowed": False,
        "live_trading_allowed": False,
        "raw_sql_allowed": False,
        "runtime_instantiation": "deferred_to_strategy_risk_stack_validation",
    }
    normalized.update(raw)
    if normalized.get("backtest_only") is not True:
        raise ValueError("execution_assumptions.backtest_only must remain true")
    for flag in ("broker_mutation_allowed", "live_trading_allowed", "raw_sql_allowed"):
        if _truthy(normalized.get(flag)):
            raise ValueError(f"execution_assumptions.{flag} must remain false")
    return _jsonable(normalized)


def _stack_id(
    *,
    strategy_report: _ResolvedReport,
    risk_reports: Sequence[_ResolvedReport],
    execution_assumptions: Mapping[str, Any],
) -> str:
    return stable_research_id(
        "strategy_risk_stack",
        {
            "strategy_validation_id": strategy_report.report.get("validation_id"),
            "risk_manager_validation_ids": [item.report.get("validation_id") for item in risk_reports],
            "execution_assumptions": execution_assumptions,
        },
    )


def _strategy_candidate_link(
    manifest: StrategyCandidateManifest,
    *,
    strategy_report: _ResolvedReport,
    artifact_root: str | Path,
    artifact_store: ResearchArtifactStore | None,
) -> StrategyCandidateArtifactLink:
    source_ref = manifest.strategy_source
    return StrategyCandidateArtifactLink(
        artifact_id=manifest.candidate_id,
        artifact_type=STRATEGY_CANDIDATE,
        role="strategy",
        path=None if artifact_store is not None else str(strategy_candidate_path(artifact_root, manifest.candidate_id)),
        uri=f"research://postgres/{STRATEGY_CANDIDATE}/{manifest.candidate_id}" if artifact_store is not None else None,
        agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
        status="validated",
        metadata={
            "portfolio_mode": manifest.strategy_source.metadata.get("portfolio_mode") if manifest.strategy_source else "",
            "runtime_builder_path": source_ref.metadata.get("runtime_builder_path") if source_ref is not None else "",
            "source_hash": source_ref.source_hash if source_ref is not None else "",
            "template_family": manifest.template_family,
            "validation_id": strategy_report.report.get("validation_id"),
        },
    )


def _strategy_validation_link(strategy_report: _ResolvedReport) -> StrategyCandidateArtifactLink:
    validation_id = str(strategy_report.report.get("validation_id") or "")
    return StrategyCandidateArtifactLink(
        artifact_id=validation_id,
        artifact_type=STRATEGY_CANDIDATE_VALIDATION_REPORT,
        role="strategy_validation",
        path=str(strategy_report.path) if strategy_report.path is not None else None,
        uri=(
            f"research://postgres/{STRATEGY_CANDIDATE_VALIDATION_REPORT}/{validation_id}"
            if strategy_report.path is None
            else None
        ),
        agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
        status=str(strategy_report.report.get("status") or ""),
        metadata={
            "candidate_id": strategy_report.report.get("candidate_id"),
            "runtime_builder_path": strategy_report.report.get("runtime_builder_path"),
        },
    )


def _risk_manager_candidate_link(
    manifest: RiskManagerCandidateManifest,
    *,
    validation_report: _ResolvedReport,
    artifact_root: str | Path,
    index: int,
    artifact_store: ResearchArtifactStore | None,
) -> StrategyCandidateArtifactLink:
    source_ref = manifest.risk_manager_source
    return StrategyCandidateArtifactLink(
        artifact_id=manifest.candidate_id,
        artifact_type=RISK_MANAGER_CANDIDATE,
        role=f"risk_manager_{index}",
        path=None if artifact_store is not None else str(risk_manager_candidate_path(artifact_root, manifest.candidate_id)),
        uri=f"research://postgres/{RISK_MANAGER_CANDIDATE}/{manifest.candidate_id}" if artifact_store is not None else None,
        agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
        status="validated",
        metadata={
            "priority": index,
            "source_hash": source_ref.source_hash if source_ref is not None else "",
            "telemetry_required": list(_sequence(manifest.execution_assumptions.get("telemetry_required"))),
            "template_family": manifest.template_family,
            "validation_report_ref": _risk_manager_validation_link(validation_report).to_dict(),
        },
    )


def _risk_manager_validation_link(validation_report: _ResolvedReport) -> StrategyCandidateArtifactLink:
    validation_id = str(validation_report.report.get("validation_id") or "")
    return StrategyCandidateArtifactLink(
        artifact_id=validation_id,
        artifact_type=RISK_MANAGER_CANDIDATE_VALIDATION_REPORT,
        role="risk_manager_validation",
        path=str(validation_report.path) if validation_report.path is not None else None,
        uri=(
            f"research://postgres/{RISK_MANAGER_CANDIDATE_VALIDATION_REPORT}/{validation_id}"
            if validation_report.path is None
            else None
        ),
        agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
        status=str(validation_report.report.get("status") or ""),
        metadata={
            "candidate_id": validation_report.report.get("candidate_id"),
            "template_family": validation_report.report.get("template_family"),
        },
    )


def _build_stack_validation_report(
    *,
    artifact_root: str | Path,
    stack: _ResolvedStack,
    artifact_store: ResearchArtifactStore | None,
) -> tuple[dict[str, Any], Path | None]:
    manifest = stack.manifest
    warnings = [issue.message for issue in manifest.warnings]
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []
    fixture_summary: dict[str, Any] = {
        "fixture_id": STACK_VALIDATION_FIXTURE_ID,
        "status": "not_run",
        "strategy_orders_emitted": 0,
        "risk_approved_orders": 0,
        "risk_rejected_orders": 0,
    }
    strategy_report: _ResolvedReport | None = None
    risk_reports: tuple[_ResolvedReport, ...] = ()
    strategy_candidate: StrategyCandidateManifest | None = None
    risk_candidates: tuple[RiskManagerCandidateManifest, ...] = ()

    _record_check(checks, blockers, "manifest_integrity", _check_stack_manifest_integrity(manifest))
    _record_check(checks, blockers, "execution_assumptions", _check_stack_execution_assumptions(manifest))
    _record_check(checks, blockers, "risk_manager_ordering", _check_risk_manager_ordering(manifest))
    if not blockers:
        try:
            strategy_report = _resolved_strategy_report_from_stack(artifact_root, manifest, artifact_store)
            risk_reports = tuple(
                _resolved_risk_report_from_stack(artifact_root, ref, artifact_store)
                for ref in manifest.risk_manager_refs
            )
            strategy_candidate = _load_strategy_candidate_for_report(artifact_root, strategy_report.report, artifact_store)
            risk_candidates = tuple(
                _load_risk_manager_candidate_for_report(artifact_root, resolved.report, artifact_store)
                for resolved in risk_reports
            )
            _validate_stack_builder_inputs(strategy_report, risk_reports, strategy_candidate, risk_candidates)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            _add_blocking_check(checks, blockers, "validation_refs", str(exc))

    if strategy_candidate is not None and risk_candidates:
        _record_check(checks, blockers, "runtime_contracts", _check_runtime_contracts(strategy_candidate, risk_candidates))
        _record_check(
            checks,
            blockers,
            "source_hashes",
            _check_source_hashes(strategy_candidate, risk_candidates, artifact_store),
        )
    if not blockers and strategy_candidate is not None and risk_candidates:
        strategy, strategy_blockers = _instantiate_strategy(strategy_candidate, artifact_store)
        _record_check(checks, blockers, "strategy_source_instantiation", strategy_blockers)
        risk_managers, risk_blockers = _instantiate_risk_managers(risk_candidates, artifact_store)
        _record_check(checks, blockers, "risk_manager_source_instantiation", risk_blockers)
        if strategy is not None and risk_managers and not strategy_blockers and not risk_blockers:
            fixture_summary, fixture_blockers = _run_stack_fixture_smoke(strategy, risk_managers, risk_candidates)
            _record_check(checks, blockers, "fixture_smoke", fixture_blockers)
            _record_check(checks, blockers, "risk_telemetry_hooks", _check_telemetry_hooks(risk_candidates))

    status = "passed" if not blockers else "failed"
    validation_id = stable_research_id(
        "strategy_risk_stack_validation",
        {
            "stack_manifest": manifest.to_dict(),
            "checks": [{"name": check["name"], "status": check["status"]} for check in checks],
            "fixture_summary": fixture_summary,
            "status": status,
        },
    )
    strategy_validation_ref = manifest.strategy_validation_report_ref
    risk_validation_refs = tuple(
        StrategyCandidateArtifactLink.from_dict(_mapping(ref.metadata.get("validation_report_ref")))
        for ref in manifest.risk_manager_refs
        if ref.metadata.get("validation_report_ref") is not None
    )
    report = {
        "artifact_type": STRATEGY_RISK_STACK_VALIDATION_REPORT,
        "schema_version": SCHEMA_VERSION,
        "validation_id": validation_id,
        "stack_id": manifest.stack_id,
        "status": status,
        "checks": checks,
        "fixture_summary": fixture_summary,
        "strategy_validation_report_ref": (
            strategy_validation_ref.to_dict() if strategy_validation_ref is not None else None
        ),
        "risk_manager_validation_refs": [item.to_dict() for item in risk_validation_refs],
        "warnings": warnings,
        "blockers": blockers,
    }
    if artifact_store is not None:
        artifact_store.save_artifact(
            artifact_type=STRATEGY_RISK_STACK_VALIDATION_REPORT,
            artifact_id=validation_id,
            payload=report,
            status=status,
            metadata={"stack_id": manifest.stack_id},
        )
        return report, None
    report_path = strategy_risk_stack_validation_report_path(artifact_root, validation_id)
    write_json_artifact(report, report_path)
    return report, report_path


def _stack_validation_ref(
    report: Mapping[str, Any],
    report_path: Path | None,
    artifact_store: ResearchArtifactStore | None,
) -> dict[str, Any]:
    validation_id = str(report["validation_id"])
    metadata = {"id": validation_id, "stack_id": report["stack_id"]}
    if artifact_store is not None:
        return ArtifactReference(
            artifact_type=STRATEGY_RISK_STACK_VALIDATION_REPORT,
            uri=f"research://postgres/{STRATEGY_RISK_STACK_VALIDATION_REPORT}/{validation_id}",
            metadata=metadata,
        ).to_dict()
    return ArtifactReference(
        artifact_type=STRATEGY_RISK_STACK_VALIDATION_REPORT,
        path=report_path,
        metadata=metadata,
    ).to_dict()


def _check_stack_manifest_integrity(manifest: StrategyRiskStackManifest) -> list[str]:
    blockers: list[str] = []
    if manifest.blockers:
        blockers.extend(f"stack manifest blocker: {blocker.message}" for blocker in manifest.blockers)
    if manifest.artifact_type != STRATEGY_RISK_STACK:
        blockers.append(f"stack artifact_type must be {STRATEGY_RISK_STACK}")
    if manifest.strategy_candidate_ref.artifact_type != STRATEGY_CANDIDATE:
        blockers.append(f"strategy_candidate_ref artifact_type must be {STRATEGY_CANDIDATE}")
    if manifest.strategy_candidate_ref.status != "validated":
        blockers.append("strategy_candidate_ref status must be validated")
    if manifest.strategy_validation_report_ref is None:
        blockers.append("strategy_validation_report_ref is required")
    elif manifest.strategy_validation_report_ref.status != "passed":
        blockers.append("strategy_validation_report_ref status must be passed")
    if not manifest.risk_manager_refs:
        blockers.append("at least one risk_manager_ref is required")
    for ref in manifest.risk_manager_refs:
        if ref.artifact_type != RISK_MANAGER_CANDIDATE:
            blockers.append(f"{ref.role} artifact_type must be {RISK_MANAGER_CANDIDATE}")
        if ref.status != "validated":
            blockers.append(f"{ref.role} status must be validated")
    return blockers


def _check_stack_execution_assumptions(manifest: StrategyRiskStackManifest) -> list[str]:
    assumptions = manifest.execution_assumptions
    blockers: list[str] = []
    if assumptions.get("backtest_only") is not True:
        blockers.append("stack execution_assumptions.backtest_only must remain true")
    for flag in ("broker_mutation_allowed", "live_trading_allowed", "raw_sql_allowed"):
        if _truthy(assumptions.get(flag)):
            blockers.append(f"stack execution_assumptions.{flag} must remain false")
    return blockers


def _check_risk_manager_ordering(manifest: StrategyRiskStackManifest) -> list[str]:
    blockers: list[str] = []
    seen_roles: set[str] = set()
    for index, ref in enumerate(manifest.risk_manager_refs):
        expected_role = f"risk_manager_{index}"
        if ref.role != expected_role:
            blockers.append(f"risk manager ref at index {index} must have role={expected_role}")
        if ref.role in seen_roles:
            blockers.append(f"duplicate risk manager role: {ref.role}")
        seen_roles.add(ref.role)
        priority = _optional_int(ref.metadata.get("priority"))
        if priority is not None and priority != index:
            blockers.append(f"{ref.role} metadata.priority must equal {index}")
        validation_ref = _mapping(ref.metadata.get("validation_report_ref"))
        if not validation_ref:
            blockers.append(f"{ref.role} metadata.validation_report_ref is required")
        elif validation_ref.get("status") != "passed":
            blockers.append(f"{ref.role} validation_report_ref.status must be passed")
    return blockers


def _resolved_strategy_report_from_stack(
    artifact_root: str | Path,
    manifest: StrategyRiskStackManifest,
    artifact_store: ResearchArtifactStore | None,
) -> _ResolvedReport:
    ref = manifest.strategy_validation_report_ref
    if ref is None:
        raise ValueError("strategy_validation_report_ref is required")
    if ref.path:
        path = Path(ref.path)
        return _ResolvedReport(_read_json(path), path)
    if artifact_store is not None:
        artifact_id = str(ref.artifact_id or "").strip()
        if not artifact_id:
            raise ValueError("strategy validation report id is required")
        return _ResolvedReport(load_artifact_ref(artifact_store, STRATEGY_CANDIDATE_VALIDATION_REPORT, artifact_id), None)
    return _ResolvedReport(
        _read_json(strategy_candidate_validation_report_path(artifact_root, ref.artifact_id)),
        strategy_candidate_validation_report_path(artifact_root, ref.artifact_id),
    )


def _resolved_risk_report_from_stack(
    artifact_root: str | Path,
    ref: StrategyCandidateArtifactLink,
    artifact_store: ResearchArtifactStore | None,
) -> _ResolvedReport:
    validation_ref = _mapping(ref.metadata.get("validation_report_ref"))
    if not validation_ref:
        raise ValueError(f"{ref.role} metadata.validation_report_ref is required")
    path_value = str(validation_ref.get("path") or "").strip()
    if path_value:
        path = Path(path_value)
        return _ResolvedReport(_read_json(path), path)
    validation_id = str(validation_ref.get("artifact_id") or validation_ref.get("validation_id") or "").strip()
    if not validation_id:
        raise ValueError(f"{ref.role} validation report id is required")
    if artifact_store is not None:
        return _ResolvedReport(load_artifact_ref(artifact_store, RISK_MANAGER_CANDIDATE_VALIDATION_REPORT, validation_id), None)
    path = risk_manager_candidate_validation_report_path(artifact_root, validation_id)
    return _ResolvedReport(_read_json(path), path)


def _check_runtime_contracts(
    strategy_candidate: StrategyCandidateManifest,
    risk_candidates: Sequence[RiskManagerCandidateManifest],
) -> list[str]:
    blockers: list[str] = []
    source_ref = strategy_candidate.strategy_source
    if source_ref is None or source_ref.runtime_contract != "trader.strategies.Strategy":
        blockers.append("strategy source runtime_contract must be trader.strategies.Strategy")
    for index, candidate in enumerate(risk_candidates):
        risk_source = candidate.risk_manager_source
        if risk_source is None or risk_source.runtime_contract != "trader.risk.RiskManager":
            blockers.append(f"risk_manager_{index} source runtime_contract must be trader.risk.RiskManager")
    return blockers


def _check_source_hashes(
    strategy_candidate: StrategyCandidateManifest,
    risk_candidates: Sequence[RiskManagerCandidateManifest],
    artifact_store: ResearchArtifactStore | None,
) -> list[str]:
    blockers: list[str] = []
    strategy_source = strategy_candidate.strategy_source
    if strategy_source is None:
        blockers.append("strategy_source is required")
    else:
        blockers.extend(_source_hash_blockers(strategy_source, label="strategy_source", artifact_store=artifact_store))
    for index, candidate in enumerate(risk_candidates):
        risk_source = candidate.risk_manager_source
        if risk_source is None:
            blockers.append(f"risk_manager_{index} risk_manager_source is required")
        else:
            blockers.extend(
                _source_hash_blockers(
                    risk_source,
                    label=f"risk_manager_{index}.risk_manager_source",
                    artifact_store=artifact_store,
                )
            )
    return blockers


def _source_hash_blockers(
    source_ref: StrategyCandidateSourceRef | RiskManagerCandidateSourceRef,
    *,
    label: str,
    artifact_store: ResearchArtifactStore | None,
) -> list[str]:
    if source_ref.uri:
        if artifact_store is None:
            return [f"{label} uri requires a configured research artifact store"]
        try:
            payload = load_artifact_ref(artifact_store, source_ref.artifact_type, source_ref.uri)
        except ResearchArtifactStoreError as exc:
            return [f"{label} DB artifact could not be loaded: {exc}"]
        source_code = str(payload.get("source_code") or "")
        if not source_code:
            return [f"{label} DB artifact source_code is required"]
        if source_text_hash(source_code) != source_ref.source_hash:
            return [f"{label} source_hash does not match DB source artifact"]
        return []
    if not source_ref.path:
        return [f"{label} path or uri is required"]
    path = Path(source_ref.path)
    if not path.exists():
        return [f"{label} file not found: {path}"]
    if file_sha256(path) != source_ref.source_hash:
        return [f"{label} source_hash does not match current source file"]
    return []


def _instantiate_strategy(
    manifest: StrategyCandidateManifest,
    artifact_store: ResearchArtifactStore | None,
) -> tuple[Strategy | None, list[str]]:
    source_ref = manifest.strategy_source
    if source_ref is None:
        return None, ["strategy_source is required"]
    blockers: list[str] = []
    try:
        module = _load_source_module(
            source_ref,
            f"_trader_stack_strategy_{_module_suffix(manifest.candidate_id)}",
            artifact_store,
        )
        if not hasattr(module, source_ref.class_name):
            raise ValueError(f"strategy source class not found: {source_ref.class_name}")
        factory = getattr(module, source_ref.factory_name)
        strategy = factory(symbols=list(FIXTURE_SYMBOLS), asset_class=FIXTURE_ASSET_CLASS, timeframe=FIXTURE_TIMEFRAME)
    except Exception as exc:
        blockers.append(f"strategy source instantiation failed: {exc}")
        return None, blockers
    if not isinstance(strategy, Strategy):
        blockers.append("strategy source factory did not return a trader.strategies.Strategy")
        return None, blockers
    return strategy, blockers


def _instantiate_risk_managers(
    candidates: Sequence[RiskManagerCandidateManifest],
    artifact_store: ResearchArtifactStore | None,
) -> tuple[tuple[RiskManager, ...], list[str]]:
    managers: list[RiskManager] = []
    blockers: list[str] = []
    for index, candidate in enumerate(candidates):
        source_ref = candidate.risk_manager_source
        if source_ref is None:
            blockers.append(f"risk_manager_{index} risk_manager_source is required")
            continue
        try:
            module = _load_source_module(
                source_ref,
                f"_trader_stack_risk_manager_{index}_{_module_suffix(candidate.candidate_id)}",
                artifact_store,
            )
            if not hasattr(module, source_ref.class_name):
                raise ValueError(f"risk-manager source class not found: {source_ref.class_name}")
            factory = getattr(module, source_ref.factory_name)
            manager = factory()
        except Exception as exc:
            blockers.append(f"risk_manager_{index} source instantiation failed: {exc}")
            continue
        if not isinstance(manager, RiskManager):
            blockers.append(f"risk_manager_{index} source factory did not return a trader.risk.RiskManager")
            continue
        managers.append(manager)
    return tuple(managers), blockers


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
    from importlib import util as importlib_util

    spec = importlib_util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load source module: {source_path}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_stack_fixture_smoke(
    strategy: Strategy,
    risk_managers: Sequence[RiskManager],
    risk_candidates: Sequence[RiskManagerCandidateManifest],
) -> tuple[dict[str, Any], list[str]]:
    store = _FixtureEventStore(
        {symbol: _synthetic_bars(symbol_index=index) for index, symbol in enumerate(FIXTURE_SYMBOLS)},
        FIXTURE_TIMEFRAME,
    )
    decision_ts = datetime(2026, 1, 1, 14, 39, tzinfo=timezone.utc)
    portfolio = Portfolio.empty(cash_balance=100_000.0)
    try:
        strategy_orders = list(
            strategy.generate_orders(
                run_id="strategy_risk_stack_validation",
                cycle_id=STACK_VALIDATION_FIXTURE_ID,
                decision_ts=decision_ts,
                event_store=store,
                portfolio=portfolio,
            )
        )
    except Exception as exc:
        return _stack_fixture_summary(
            status="failed",
            strategy_orders=(),
            risk_approved=(),
            risk_rejected=(),
            risk_candidates=risk_candidates,
            risk_probe_used=False,
        ), [f"strategy stack fixture failed: {exc}"]

    risk_probe_used = False
    risk_orders = strategy_orders
    if not risk_orders:
        risk_orders = list(_fixture_probe_orders())
        risk_probe_used = True
    context = _fixture_risk_context()
    try:
        approved, rejected = RiskPipeline(risk_managers).evaluate(risk_orders, context)
    except Exception as exc:
        return _stack_fixture_summary(
            status="failed",
            strategy_orders=strategy_orders,
            risk_approved=(),
            risk_rejected=(),
            risk_candidates=risk_candidates,
            risk_probe_used=risk_probe_used,
        ), [f"risk pipeline stack fixture failed: {exc}"]

    blockers: list[str] = []
    for index, order in enumerate([*strategy_orders, *approved, *rejected]):
        blockers.extend(_order_blockers(index, order))
    for index, order in enumerate(rejected):
        if str(order.get("rejection_reason") or "").strip() == "":
            blockers.append(f"risk rejected order {index} missing rejection_reason")
    status = "passed" if not blockers else "failed"
    return _stack_fixture_summary(
        status=status,
        strategy_orders=strategy_orders,
        risk_approved=approved,
        risk_rejected=rejected,
        risk_candidates=risk_candidates,
        risk_probe_used=risk_probe_used,
    ), blockers


def _stack_fixture_summary(
    *,
    status: str,
    strategy_orders: Sequence[Mapping[str, object]],
    risk_approved: Sequence[Mapping[str, object]],
    risk_rejected: Sequence[Mapping[str, object]],
    risk_candidates: Sequence[RiskManagerCandidateManifest],
    risk_probe_used: bool,
) -> dict[str, Any]:
    exposure_summary = _exposure_summary([*risk_approved, *risk_rejected])
    return {
        "fixture_id": STACK_VALIDATION_FIXTURE_ID,
        "fixture_context": {
            "asset_class": FIXTURE_ASSET_CLASS,
            "symbols": list(FIXTURE_SYMBOLS),
            "timeframe": FIXTURE_TIMEFRAME,
        },
        "status": status,
        "symbol_count": len(FIXTURE_SYMBOLS),
        "bar_count_per_symbol": SYNTHETIC_BAR_COUNT,
        "strategy_orders_emitted": len(strategy_orders),
        "risk_probe_orders_used": risk_probe_used,
        "risk_approved_orders": len(risk_approved),
        "risk_rejected_orders": len(risk_rejected),
        "risk_manager_count": len(risk_candidates),
        "risk_manager_order": [candidate.candidate_id for candidate in risk_candidates],
        "risk_telemetry_requirements": _risk_telemetry_requirements(risk_candidates),
        "exposure_summary": exposure_summary,
    }


def _check_telemetry_hooks(risk_candidates: Sequence[RiskManagerCandidateManifest]) -> list[str]:
    blockers: list[str] = []
    for index, candidate in enumerate(risk_candidates):
        required = tuple(_sequence(candidate.execution_assumptions.get("telemetry_required")))
        if not required:
            blockers.append(f"risk_manager_{index} execution_assumptions.telemetry_required is required")
        if not candidate.policy_intent:
            blockers.append(f"risk_manager_{index} policy_intent is required")
    return blockers


def _risk_telemetry_requirements(
    risk_candidates: Sequence[RiskManagerCandidateManifest],
) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": candidate.candidate_id,
            "template_family": candidate.template_family,
            "telemetry_required": list(_sequence(candidate.execution_assumptions.get("telemetry_required"))),
            "policy_intent": dict(candidate.policy_intent),
        }
        for candidate in risk_candidates
    ]


def _fixture_probe_orders() -> tuple[Mapping[str, object], ...]:
    return (
        {"symbol": "SYNTH_A", "side": "buy", "qty": 1.0, "order_type": "market", "price": 100.0},
        {"symbol": "SYNTH_B", "side": "buy", "qty": 1.0, "order_type": "market", "price": 110.0},
    )


def _fixture_risk_context() -> RiskContext:
    decision_ts = datetime(2026, 1, 1, 14, 39, tzinfo=timezone.utc)
    return RiskContext(
        positions={
            "SYNTH_A": Position(symbol="SYNTH_A", qty=0.0, avg_price=None),
            "SYNTH_B": Position(symbol="SYNTH_B", qty=1.0, avg_price=108.0),
            "SYNTH_C": Position(symbol="SYNTH_C", qty=0.0, avg_price=None),
        },
        open_orders=(),
        price_lookup={"SYNTH_A": 100.0, "SYNTH_B": 110.0, "SYNTH_C": 90.0},
        run_id="strategy_risk_stack_validation",
        cycle_id=STACK_VALIDATION_FIXTURE_ID,
        decision_ts=decision_ts,
    )


def _order_blockers(index: int, order: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    symbol = str(order.get("symbol") or "").strip().upper()
    side = str(order.get("side") or "").strip().lower()
    order_type = str(order.get("order_type") or "").strip().lower()
    qty = _numeric_value(order.get("qty"))
    if symbol not in FIXTURE_SYMBOLS:
        blockers.append(f"fixture order {index} has unknown symbol: {symbol}")
    if side not in {"buy", "sell"}:
        blockers.append(f"fixture order {index} side must be buy or sell")
    if order_type != "market":
        blockers.append(f"fixture order {index} order_type must be market")
    if qty is None or qty < 0.0:
        blockers.append(f"fixture order {index} qty must be non-negative numeric")
    return blockers


def _exposure_summary(orders: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    gross = 0.0
    net = 0.0
    symbol_notional: dict[str, float] = {}
    for order in orders:
        symbol = str(order.get("symbol") or "").strip().upper()
        qty = _numeric_value(order.get("qty")) or 0.0
        price = _numeric_value(order.get("price")) or _fixture_price(symbol)
        side = str(order.get("side") or "").strip().lower()
        signed = qty * price * (-1.0 if side == "sell" else 1.0)
        gross += abs(signed)
        net += signed
        symbol_notional[symbol] = symbol_notional.get(symbol, 0.0) + signed
    return {
        "gross_order_notional": gross,
        "net_order_notional": net,
        "per_symbol_order_notional": symbol_notional,
        "symbol_count": len([symbol for symbol, value in symbol_notional.items() if value != 0.0]),
    }


def _fixture_price(symbol: str) -> float:
    return {"SYNTH_A": 100.0, "SYNTH_B": 110.0, "SYNTH_C": 90.0}.get(symbol, 1.0)


class _FixtureEventStore(EventStore):
    """Small in-memory event store with enough read support for strategy smoke checks."""

    def __init__(self, bars_by_symbol: Mapping[str, Sequence[Bar]], timeframe: str) -> None:
        self._bars_by_symbol = {symbol.upper(): tuple(bars) for symbol, bars in bars_by_symbol.items()}
        self._timeframe = timeframe
        self.events: list[Mapping[str, object]] = []

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Record fixture telemetry emitted by maintained strategies."""
        self.events.append({"event_type": event_type, "payload": dict(payload)})

    def connection(self) -> "_FixtureConnection":
        """Return a DB-API-like connection facade used by bar query helpers."""
        return _FixtureConnection(self)

    def rows(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        as_of_ts: datetime | None,
    ) -> list[tuple[datetime, float, float, float, float, float, float | None, float | None]]:
        """Return latest-first OHLCV tuples for the requested fixture symbol."""
        if timeframe != self._timeframe:
            return []
        bars = self._bars_by_symbol.get(symbol.upper(), ())
        bounded = [bar for bar in bars if as_of_ts is None or bar.ts <= as_of_ts]
        return [
            (bar.ts, bar.open, bar.high, bar.low, bar.close, bar.volume, bar.vwap, bar.trade_count)
            for bar in bounded[:limit]
        ]


class _FixtureConnection:
    """Connection facade that creates fixture cursors."""

    def __init__(self, store: _FixtureEventStore) -> None:
        self._store = store

    def cursor(self) -> "_FixtureCursor":
        """Return a context-manager cursor facade."""
        return _FixtureCursor(self._store)


class _FixtureCursor:
    """Cursor facade for the query shape used by standard strategy bar helpers."""

    def __init__(self, store: _FixtureEventStore) -> None:
        self._store = store
        self._rows: list[tuple[datetime, float, float, float, float, float, float | None, float | None]] = []

    def __enter__(self) -> "_FixtureCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: Sequence[object]) -> None:
        """Store deterministic rows for the latest executed fixture query."""
        del query
        if len(params) == 4:
            symbol, timeframe, as_of_ts, limit = params
            parsed_as_of = as_of_ts if isinstance(as_of_ts, datetime) else None
        else:
            symbol, timeframe, limit = params
            parsed_as_of = None
        self._rows = self._store.rows(
            symbol=str(symbol),
            timeframe=str(timeframe),
            limit=int(limit),
            as_of_ts=parsed_as_of,
        )

    def fetchall(self) -> list[tuple[datetime, float, float, float, float, float, float | None, float | None]]:
        """Return rows from the latest fixture query."""
        return list(self._rows)


def _synthetic_bars(*, symbol_index: int = 0) -> tuple[Bar, ...]:
    base_ts = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    ascending: list[Bar] = []
    drift = 0.03 + symbol_index * 0.02
    base_price = 95.0 + symbol_index * 5.0
    for index in range(SYNTHETIC_BAR_COUNT):
        close = base_price + index * drift + ((index % 7) - 3) * 0.02
        ts = base_ts + timedelta(minutes=index)
        ascending.append(
            Bar(
                ts=ts,
                open=close,
                high=close + 0.1,
                low=close - 0.1,
                close=close,
                volume=1000.0 + index,
                vwap=None,
                trade_count=None,
            )
        )
    return tuple(reversed(ascending))


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"JSON artifact not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, MappingABC):
        raise ValueError(f"JSON artifact must contain an object: {source}")
    return dict(payload)


def _record_check(
    checks: list[dict[str, Any]],
    blockers: list[str],
    name: str,
    check_blockers: Sequence[str],
) -> None:
    checks.append(
        {
            "name": name,
            "status": "passed" if not check_blockers else "failed",
            "messages": list(check_blockers),
        }
    )
    blockers.extend(check_blockers)


def _add_blocking_check(
    checks: list[dict[str, Any]],
    blockers: list[str],
    name: str,
    message: str,
) -> None:
    _record_check(checks, blockers, name, (message,))


def _module_suffix(value: str) -> str:
    suffix = "".join(character for character in value if character.isalnum())[-16:]
    return suffix or "generated"


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number


def _numeric_value(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, MappingABC) else {}


def _sequence(value: object) -> Sequence[Any]:
    return value if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes)) else ()


def _jsonable(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
