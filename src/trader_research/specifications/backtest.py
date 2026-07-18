"""Canonical DB-backed backtest specification services."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from trader_research.artifact_store import ResearchArtifactStore, ResearchArtifactStoreError, json_payload_hash
from trader_research.contracts import SCHEMA_VERSION, SideEffect, ToolEnvelope, success_envelope
from trader_research.domain import BACKTEST_SPECIFICATION, BACKTEST_SPECIFICATION_VALIDATION_REPORT, stable_research_id

from .common import (
    artifact_snapshot,
    normalize_assumptions,
    normalize_positions,
    normalized_dataset_manifest,
    number,
    resolve_exactly_one,
    specification_error,
    validate_quality_report,
)
from .risk import load_passed_risk_stack_specification
from .strategy import load_passed_strategy_specification


RESEARCH_CREATE_BACKTEST_SPECIFICATION = "research_create_backtest_specification"
RESEARCH_VALIDATE_BACKTEST_SPECIFICATION = "research_validate_backtest_specification"


def create_backtest_specification(
    *,
    strategy_specification_validation_ref: str,
    dataset_manifest: Mapping[str, Any],
    data_quality_report: Mapping[str, Any],
    risk_stack_specification_validation_ref: str | None = None,
    assumptions: Mapping[str, Any] | None = None,
    initial_cash: float = 100_000.0,
    initial_positions: Sequence[Mapping[str, Any]] | None = None,
    benchmark: Mapping[str, Any] | None = None,
    deterministic_seed: int = 0,
    max_runs: int | None = None,
    log_cycle_details: bool = False,
    runtime_limits: Mapping[str, Any] | None = None,
    parent_specification_ref: str | None = None,
    selection_origin_ref: str | None = None,
    variant_reason: str | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Bind validated behavior, Data Agent scope, costs, and execution policy."""
    command = RESEARCH_CREATE_BACKTEST_SPECIFICATION
    if artifact_store is None:
        return specification_error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        strategy_specification, strategy_validation = load_passed_strategy_specification(
            artifact_store, strategy_specification_validation_ref
        )
        risk_specification = None
        risk_validation = None
        if risk_stack_specification_validation_ref:
            risk_specification, risk_validation = load_passed_risk_stack_specification(
                artifact_store, risk_stack_specification_validation_ref
            )
        manifest = normalized_dataset_manifest(dataset_manifest)
        quality = validate_quality_report(data_quality_report, manifest)
        normalized_assumptions = normalize_assumptions(assumptions)
        normalized_cash = number(initial_cash, "initial_cash")
        if normalized_cash < 0:
            raise ValueError("initial_cash must be non-negative")
        positions = normalize_positions(initial_positions)
        if isinstance(deterministic_seed, bool) or not isinstance(deterministic_seed, int):
            raise ValueError("deterministic_seed must be an integer")
        if max_runs is not None and (isinstance(max_runs, bool) or not isinstance(max_runs, int) or max_runs <= 0):
            raise ValueError("max_runs must be a positive integer")
        identity = {
            "strategy_specification_id": strategy_specification["strategy_specification_id"],
            "strategy_specification_validation_id": strategy_validation["validation_id"],
            "risk_stack_specification_id": (
                risk_specification["risk_stack_specification_id"] if risk_specification else None
            ),
            "risk_stack_specification_validation_id": risk_validation["validation_id"] if risk_validation else None,
            "dataset": artifact_snapshot(manifest),
            "data_quality": artifact_snapshot(quality),
            "assumptions": normalized_assumptions,
            "initial_cash": normalized_cash,
            "initial_positions": positions,
            "benchmark": dict(benchmark or {}),
            "deterministic_seed": deterministic_seed,
            "max_runs": max_runs,
            "log_cycle_details": bool(log_cycle_details),
            "runtime_limits": dict(runtime_limits or {}),
            "parent_specification_ref": parent_specification_ref,
            "selection_origin_ref": selection_origin_ref,
            "variant_reason": variant_reason,
        }
        specification_id = stable_research_id("backtest_specification", identity)
        payload = {
            "artifact_type": BACKTEST_SPECIFICATION,
            "schema_version": SCHEMA_VERSION,
            "backtest_specification_id": specification_id,
            **identity,
            "status": "created",
        }
        record = artifact_store.save_artifact(
            artifact_type=BACKTEST_SPECIFICATION,
            artifact_id=specification_id,
            payload=payload,
            status="created",
            metadata={
                "dataset_id": manifest["dataset_id"],
                "strategy_specification_id": strategy_specification["strategy_specification_id"],
            },
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return specification_error(command, "backtest_specification_creation_failed", str(exc))
    return success_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"backtest_specification": payload},
        artifacts={"backtest_specification": record.reference().to_dict()},
    )


def validate_backtest_specification(
    *,
    backtest_specification_id: str | None = None,
    backtest_specification_uri: str | None = None,
    backtest_specification: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Validate immutable snapshots and all upstream passed specifications."""
    command = RESEARCH_VALIDATE_BACKTEST_SPECIFICATION
    if artifact_store is None:
        return specification_error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        payload = resolve_exactly_one(
            artifact_store,
            BACKTEST_SPECIFICATION,
            artifact_id=backtest_specification_id,
            artifact_uri=backtest_specification_uri,
            inline=backtest_specification,
            label="backtest specification",
        )
        if payload.get("artifact_type") != BACKTEST_SPECIFICATION:
            raise ValueError(f"artifact_type must be {BACKTEST_SPECIFICATION}")
        blockers: list[str] = []
        load_passed_strategy_specification(
            artifact_store, str(payload.get("strategy_specification_validation_id") or "")
        )
        risk_validation = payload.get("risk_stack_specification_validation_id")
        if risk_validation:
            load_passed_risk_stack_specification(artifact_store, str(risk_validation))
        for key in ("dataset", "data_quality"):
            snapshot = dict(payload.get(key) or {})
            embedded = dict(snapshot.get("payload") or {})
            if json_payload_hash(embedded) != snapshot.get("sha256"):
                blockers.append(f"backtest specification {key} snapshot hash drifted")
        manifest = normalized_dataset_manifest(dict(payload["dataset"]["payload"]))
        validate_quality_report(dict(payload["data_quality"]["payload"]), manifest)
        normalize_assumptions(dict(payload.get("assumptions") or {}))
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return specification_error(command, "backtest_specification_resolution_failed", str(exc))
    identity = {
        "backtest_specification_id": payload["backtest_specification_id"],
        "dataset_hash": payload["dataset"]["sha256"],
        "quality_hash": payload["data_quality"]["sha256"],
        "blockers": blockers,
    }
    report = {
        "artifact_type": BACKTEST_SPECIFICATION_VALIDATION_REPORT,
        "schema_version": SCHEMA_VERSION,
        "validation_id": stable_research_id("backtest_specification_validation", identity),
        **identity,
        "status": "passed" if not blockers else "blocked",
        "valid": not blockers,
        "warnings": [],
    }
    try:
        record = artifact_store.save_artifact(
            artifact_type=BACKTEST_SPECIFICATION_VALIDATION_REPORT,
            artifact_id=report["validation_id"],
            payload=report,
            status=report["status"],
            metadata={"backtest_specification_id": payload["backtest_specification_id"]},
        )
    except ResearchArtifactStoreError as exc:
        return specification_error(command, "backtest_specification_validation_persistence_failed", str(exc))
    if blockers:
        return ToolEnvelope(
            ok=False,
            command=command,
            agent_owner="Quant Research Supervisor Agent",
            side_effect=SideEffect.LOCAL_MUTATING,
            data={"backtest_specification_validation_report": report},
            artifacts={"backtest_specification_validation_report": record.reference().to_dict()},
            errors=({"code": "backtest_specification_validation_failed", "message": blockers[0]},),
        )
    return success_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"backtest_specification_validation_report": report},
        artifacts={"backtest_specification_validation_report": record.reference().to_dict()},
    )


def load_passed_backtest_specification(
    store: ResearchArtifactStore,
    validation_ref: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Load a passed canonical backtest specification and validation report."""
    validation_id = str(validation_ref).rstrip("/").rsplit("/", 1)[-1]
    report = store.load_artifact(BACKTEST_SPECIFICATION_VALIDATION_REPORT, validation_id)
    if report.get("status") != "passed" or report.get("valid") is not True or report.get("blockers"):
        raise ValueError("backtest specification validation must be passed, valid, and blocker-free")
    specification = store.load_artifact(
        BACKTEST_SPECIFICATION, str(report.get("backtest_specification_id") or "")
    )
    specification_id = str(specification.get("backtest_specification_id") or "")
    identity = {
        key: specification.get(key)
        for key in (
            "strategy_specification_id",
            "strategy_specification_validation_id",
            "risk_stack_specification_id",
            "risk_stack_specification_validation_id",
            "dataset",
            "data_quality",
            "assumptions",
            "initial_cash",
            "initial_positions",
            "benchmark",
            "deterministic_seed",
            "max_runs",
            "log_cycle_details",
            "runtime_limits",
            "parent_specification_ref",
            "selection_origin_ref",
            "variant_reason",
        )
    }
    if stable_research_id("backtest_specification", identity) != specification_id:
        raise ValueError("backtest specification ID does not match its canonical content")
    if specification["dataset"]["sha256"] != report.get("dataset_hash"):
        raise ValueError("backtest specification dataset hash does not match validation")
    if specification["data_quality"]["sha256"] != report.get("quality_hash"):
        raise ValueError("backtest specification quality hash does not match validation")
    for key in ("dataset", "data_quality"):
        snapshot = dict(specification.get(key) or {})
        if json_payload_hash(dict(snapshot.get("payload") or {})) != snapshot.get("sha256"):
            raise ValueError(f"backtest specification {key} snapshot drifted after validation")
    if stable_research_id(
        "backtest_specification_validation",
        {
            "backtest_specification_id": specification_id,
            "dataset_hash": report.get("dataset_hash"),
            "quality_hash": report.get("quality_hash"),
            "blockers": report.get("blockers") or [],
        },
    ) != report.get("validation_id"):
        raise ValueError("backtest specification validation ID does not match its evidence")
    strategy, _ = load_passed_strategy_specification(
        store, str(specification.get("strategy_specification_validation_id") or "")
    )
    if strategy.get("strategy_specification_id") != specification.get("strategy_specification_id"):
        raise ValueError("backtest strategy specification drifted after validation")
    risk_validation = specification.get("risk_stack_specification_validation_id")
    if risk_validation:
        risk, _ = load_passed_risk_stack_specification(store, str(risk_validation))
        if risk.get("risk_stack_specification_id") != specification.get("risk_stack_specification_id"):
            raise ValueError("backtest risk-stack specification drifted after validation")
    return specification, report
