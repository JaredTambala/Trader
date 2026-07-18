"""Registration and validation services for canonical executable implementations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from trader.event_store import NoOpEventStore
from trader.portfolio import Portfolio
from trader_research.artifact_store import ResearchArtifactStore, ResearchArtifactStoreError, load_artifact_ref
from trader_research.contracts import SCHEMA_VERSION, SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import IMPLEMENTATION_VALIDATION_REPORT, IMPLEMENTATION_VERSION, stable_research_id

from .domain import ImplementationVersion, build_implementation_version, parameter_defaults, validate_parameters
from .runtime import (
    evaluate_objective,
    instantiate_risk_manager,
    instantiate_strategy,
    smoke_risk_manager,
    source_safety_blockers,
)


RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION = "research_register_strategy_implementation"
RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION = "research_validate_strategy_implementation"
RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION = "research_register_risk_manager_implementation"
RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION = "research_validate_risk_manager_implementation"
RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE = "research_register_optimization_objective"
RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE = "research_validate_optimization_objective"


def register_implementation(
    *,
    command: str,
    implementation_kind: str,
    name: str,
    version: str,
    source_code: str,
    factory_name: str,
    class_name: str | None = None,
    parameter_schema: Mapping[str, Any] | None = None,
    dependencies: Sequence[str] | None = None,
    authoring_origin: str = "supplied",
    capabilities: Sequence[str] | None = None,
    runtime_requirements: Mapping[str, Any] | None = None,
    resource_bounds: Mapping[str, Any] | None = None,
    provenance_refs: Sequence[Mapping[str, Any]] | None = None,
    metadata: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Persist one content-addressed implementation version."""
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        implementation = build_implementation_version(
            implementation_kind=implementation_kind,
            name=name,
            version=version,
            source_code=source_code,
            class_name=class_name,
            factory_name=factory_name,
            parameter_schema=parameter_schema,
            dependencies=dependencies,
            authoring_origin=authoring_origin,
            capabilities=capabilities,
            runtime_requirements=runtime_requirements,
            resource_bounds=resource_bounds,
            provenance_refs=provenance_refs,
            metadata=metadata,
        )
        record = artifact_store.save_artifact(
            artifact_type=IMPLEMENTATION_VERSION,
            artifact_id=implementation.implementation_version_id,
            payload=implementation.to_dict(),
            status=implementation.status,
            source_hash=implementation.source_hash,
            metadata={"implementation_kind": implementation.implementation_kind, "name": implementation.name},
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return _error(command, "implementation_registration_failed", str(exc))
    return success_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"implementation_version": implementation.to_dict()},
        artifacts={"implementation_version": record.reference().to_dict()},
    )


def validate_implementation(
    *,
    command: str,
    expected_kind: str,
    implementation_version_id: str | None = None,
    implementation_version_uri: str | None = None,
    implementation_version: Mapping[str, Any] | None = None,
    fixture_parameters: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Validate source safety, interface conformance, and deterministic fixture behavior."""
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        resolved = _resolve_implementation(
            implementation_version_id=implementation_version_id,
            implementation_version_uri=implementation_version_uri,
            implementation_version=implementation_version,
            artifact_store=artifact_store,
        )
        if resolved.implementation_kind != expected_kind:
            raise ValueError(f"implementation_kind must be {expected_kind}")
        parameters = {**parameter_defaults(resolved.parameter_schema), **dict(fixture_parameters or {})}
        blockers = list(validate_parameters(resolved.parameter_schema, parameters))
        blockers.extend(source_safety_blockers(resolved))
        fixture: dict[str, Any] = {"status": "not_run"}
        if not blockers:
            fixture, runtime_blockers = _runtime_fixture(resolved, parameters)
            blockers.extend(runtime_blockers)
    except (ValueError, ResearchArtifactStoreError) as exc:
        return _error(command, "implementation_resolution_failed", str(exc))

    status = "passed" if not blockers else "blocked"
    validation_id = stable_research_id(
        "implementation_validation",
        {
            "implementation_version_id": resolved.implementation_version_id,
            "source_hash": resolved.source_hash,
            "fixture_parameters": parameters,
            "fixture": fixture,
            "blockers": blockers,
        },
    )
    report = {
        "artifact_type": IMPLEMENTATION_VALIDATION_REPORT,
        "schema_version": SCHEMA_VERSION,
        "validation_id": validation_id,
        "implementation_version_id": resolved.implementation_version_id,
        "implementation_kind": resolved.implementation_kind,
        "source_hash": resolved.source_hash,
        "status": status,
        "valid": not blockers,
        "fixture_parameters": parameters,
        "fixture": fixture,
        "warnings": [],
        "blockers": blockers,
    }
    try:
        record = artifact_store.save_artifact(
            artifact_type=IMPLEMENTATION_VALIDATION_REPORT,
            artifact_id=validation_id,
            payload=report,
            status=status,
            source_hash=resolved.source_hash,
            metadata={
                "implementation_version_id": resolved.implementation_version_id,
                "implementation_kind": resolved.implementation_kind,
            },
        )
    except ResearchArtifactStoreError as exc:
        return _error(command, "implementation_validation_persistence_failed", str(exc))
    envelope = success_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"implementation_validation_report": report},
        artifacts={"implementation_validation_report": record.reference().to_dict()},
    )
    if not blockers:
        return envelope
    return ToolEnvelope(
        ok=False,
        command=envelope.command,
        agent_owner=envelope.agent_owner,
        side_effect=envelope.side_effect,
        data=envelope.data,
        artifacts=envelope.artifacts,
        errors=({"code": "implementation_validation_failed", "message": blockers[0]},),
    )


def register_strategy_implementation(**kwargs: Any) -> ToolEnvelope:
    """Register a strategy implementation version."""
    return register_implementation(
        command=RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION,
        implementation_kind="strategy",
        **kwargs,
    )


def validate_strategy_implementation(**kwargs: Any) -> ToolEnvelope:
    """Validate a strategy implementation version."""
    return validate_implementation(
        command=RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION,
        expected_kind="strategy",
        **kwargs,
    )


def register_risk_manager_implementation(**kwargs: Any) -> ToolEnvelope:
    """Register a risk-manager implementation version."""
    return register_implementation(
        command=RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION,
        implementation_kind="risk_manager",
        **kwargs,
    )


def validate_risk_manager_implementation(**kwargs: Any) -> ToolEnvelope:
    """Validate a risk-manager implementation version."""
    return validate_implementation(
        command=RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION,
        expected_kind="risk_manager",
        **kwargs,
    )


def register_optimization_objective(**kwargs: Any) -> ToolEnvelope:
    """Register a closed-input optimization objective implementation."""
    return register_implementation(
        command=RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE,
        implementation_kind="optimization_objective",
        **kwargs,
    )


def validate_optimization_objective(**kwargs: Any) -> ToolEnvelope:
    """Validate an optimization objective implementation."""
    return validate_implementation(
        command=RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE,
        expected_kind="optimization_objective",
        **kwargs,
    )


def load_passed_implementation(
    artifact_store: ResearchArtifactStore,
    validation_ref: str,
    *,
    expected_kind: str,
) -> tuple[ImplementationVersion, Mapping[str, Any]]:
    """Resolve one passed validation and its exact source-hash-matching implementation."""
    report = load_artifact_ref(artifact_store, IMPLEMENTATION_VALIDATION_REPORT, validation_ref)
    if report.get("status") != "passed" or report.get("valid") is not True or report.get("blockers"):
        raise ValueError("implementation validation report must be passed, valid, and blocker-free")
    if str(report.get("implementation_kind") or "") != expected_kind:
        raise ValueError(f"implementation validation kind must be {expected_kind}")
    expected_validation_id = stable_research_id(
        "implementation_validation",
        {
            "implementation_version_id": report.get("implementation_version_id"),
            "source_hash": report.get("source_hash"),
            "fixture_parameters": report.get("fixture_parameters") or {},
            "fixture": report.get("fixture") or {},
            "blockers": report.get("blockers") or [],
        },
    )
    if expected_validation_id != report.get("validation_id"):
        raise ValueError("implementation validation ID does not match its canonical evidence")
    implementation_id = str(report.get("implementation_version_id") or "")
    implementation = ImplementationVersion.from_dict(
        load_artifact_ref(artifact_store, IMPLEMENTATION_VERSION, implementation_id)
    )
    if implementation.implementation_kind != expected_kind:
        raise ValueError(f"implementation kind must be {expected_kind}")
    if implementation.source_hash != str(report.get("source_hash") or ""):
        raise ValueError("implementation source hash does not match validation report")
    return implementation, report


def _resolve_implementation(
    *,
    implementation_version_id: str | None,
    implementation_version_uri: str | None,
    implementation_version: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore,
) -> ImplementationVersion:
    selected = [bool(implementation_version_id), bool(implementation_version_uri), implementation_version is not None]
    if sum(selected) != 1:
        raise ValueError("exactly one implementation version input is required")
    if implementation_version is not None:
        return ImplementationVersion.from_dict(implementation_version)
    ref = str(implementation_version_uri or implementation_version_id or "")
    return ImplementationVersion.from_dict(load_artifact_ref(artifact_store, IMPLEMENTATION_VERSION, ref))


def _runtime_fixture(
    implementation: ImplementationVersion,
    parameters: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    fixture: dict[str, Any]
    try:
        if implementation.implementation_kind == "strategy":
            strategy = instantiate_strategy(
                implementation,
                symbols=["SYNTH"],
                asset_class="stocks",
                timeframe="1Min",
                parameters=parameters,
            )
            orders_a = tuple(
                strategy.generate_orders(
                    run_id="implementation-validation",
                    cycle_id="fixture",
                    decision_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    event_store=NoOpEventStore(),
                    portfolio=Portfolio.empty(cash_balance=100_000.0),
                )
            )
            strategy_b = instantiate_strategy(
                implementation,
                symbols=["SYNTH"],
                asset_class="stocks",
                timeframe="1Min",
                parameters=parameters,
            )
            orders_b = tuple(
                strategy_b.generate_orders(
                    run_id="implementation-validation",
                    cycle_id="fixture",
                    decision_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    event_store=NoOpEventStore(),
                    portfolio=Portfolio.empty(cash_balance=100_000.0),
                )
            )
            if orders_a != orders_b:
                blockers.append("strategy fixture output is not deterministic")
            fixture = {"status": "passed" if not blockers else "blocked", "orders_emitted": len(orders_a)}
        elif implementation.implementation_kind == "risk_manager":
            first_decisions = smoke_risk_manager(instantiate_risk_manager(implementation, parameters=parameters))
            second_decisions = smoke_risk_manager(instantiate_risk_manager(implementation, parameters=parameters))
            if first_decisions != second_decisions:
                blockers.append("risk-manager fixture output is not deterministic")
            fixture = {
                "status": "passed" if not blockers else "blocked",
                "decision_count": len(first_decisions),
            }
        else:
            observation = {
                "schema_version": SCHEMA_VERSION,
                "status": "passed",
                "metrics": {"sharpe": 1.0, "total_return": 0.1, "max_drawdown": 0.05},
                "counts": {"trade_count": 10},
                "costs": {"fees": 1.0, "slippage": 0.5},
                "exposure": {},
                "risk": {},
                "quality": {"complete": True, "blockers": []},
                "constraints": {},
                "lineage": {"fixture": True},
            }
            first_value, _ = evaluate_objective(implementation, observation)
            second_value, _ = evaluate_objective(implementation, observation)
            if first_value != second_value:
                blockers.append("optimization objective fixture output is not deterministic")
            fixture = {"status": "passed" if not blockers else "blocked", "objective_value": first_value}
    except Exception as exc:
        return {"status": "blocked"}, [f"runtime fixture failed: {exc}"]
    return fixture, blockers


def _error(command: str, code: str, message: str) -> ToolEnvelope:
    return error_envelope(command=command, side_effect=SideEffect.LOCAL_MUTATING, code=code, message=message)
