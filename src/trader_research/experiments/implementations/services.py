"""Application services for implementation registration and admission.

Registration persists content-addressed source and declared runtime metadata.
Validation loads an exact version, applies safety and interface checks, runs the
bounded fixture for its kind, and persists a separate validation report.
"""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import SCHEMA_VERSION

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from trader.event_store import NoOpEventStore
from trader.portfolio import Portfolio
from trader_research.foundation.artifacts import ResearchArtifactStore, ResearchArtifactStoreError, load_artifact_ref
from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
)

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
) -> ApplicationResult:
    """Normalize and persist one content-addressed implementation version.

    Registration records supplied source and declarative metadata under
    Experiments ownership but does not mark the implementation executable. The
    caller must run the kind-specific validation service and use its passed
    report before any specification can reference the implementation.

    Returns:
        A result containing the canonical implementation and reference, or a
        structured registration/persistence failure.
    """
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
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[IMPLEMENTATION_VERSION],
            producer_tool=command,
            artifact_type=IMPLEMENTATION_VERSION,
            artifact_id=implementation.implementation_version_id,
            payload=implementation.to_dict(),
            status=implementation.status,
            source_hash=implementation.source_hash,
            metadata={"implementation_kind": implementation.implementation_kind, "name": implementation.name},
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return _error(command, "implementation_registration_failed", str(exc))
    return success_result(
        command=command,
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
) -> ApplicationResult:
    """Validate source safety, interface conformance, and fixture behavior.

    Exactly one inline, ID, or URI implementation is resolved and checked against
    ``expected_kind``. Default and supplied fixture parameters are validated,
    static blockers are collected, and the kind-specific bounded runtime fixture
    runs only when static checks pass. A canonical validation report is persisted
    for both passed and blocked outcomes.

    Returns:
        A result containing the validation report and reference. ``ok`` is false
        for blocked evidence as well as resolution or persistence failures.
    """
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
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[IMPLEMENTATION_VALIDATION_REPORT],
            producer_tool=command,
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
    result = success_result(
        command=command,
        data={"implementation_validation_report": report},
        artifacts={"implementation_validation_report": record.reference().to_dict()},
    )
    if not blockers:
        return result
    return ApplicationResult(
        ok=False,
        operation=result.operation,
        data=result.data,
        artifacts=result.artifacts,
        errors=({"code": "implementation_validation_failed", "message": blockers[0]},),
    )


def register_strategy_implementation(**kwargs: Any) -> ApplicationResult:
    """Register supplied source as a content-addressed strategy implementation.

    Keyword inputs are delegated to the shared registration boundary with stable
    strategy operation and kind metadata; registration does not validate runtime use.
    """
    return register_implementation(
        command=RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION,
        implementation_kind="strategy",
        **kwargs,
    )


def validate_strategy_implementation(**kwargs: Any) -> ApplicationResult:
    """Run strategy-specific admission over one registered implementation.

    The shared validator requires strategy kind and records static, interface, and
    deterministic fixture evidence in a canonical validation report.
    """
    return validate_implementation(
        command=RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION,
        expected_kind="strategy",
        **kwargs,
    )


def register_risk_manager_implementation(**kwargs: Any) -> ApplicationResult:
    """Register supplied source as a content-addressed risk-manager implementation.

    Keyword inputs are delegated with stable risk-manager operation and kind
    metadata; the resulting registered version is not yet executable evidence.
    """
    return register_implementation(
        command=RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION,
        implementation_kind="risk_manager",
        **kwargs,
    )


def validate_risk_manager_implementation(**kwargs: Any) -> ApplicationResult:
    """Run risk-manager admission over one registered implementation.

    The shared validator requires risk-manager kind and persists source-safety,
    interface, parameter, and bounded risk-fixture evidence.
    """
    return validate_implementation(
        command=RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION,
        expected_kind="risk_manager",
        **kwargs,
    )


def register_optimization_objective(**kwargs: Any) -> ApplicationResult:
    """Register source for a closed-input optimization objective.

    Keyword inputs are delegated with the objective kind and stable operation
    metadata. Registration stores source but does not prove the closed-input policy.
    """
    return register_implementation(
        command=RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE,
        implementation_kind="optimization_objective",
        **kwargs,
    )


def validate_optimization_objective(**kwargs: Any) -> ApplicationResult:
    """Run closed-input admission over a registered optimization objective.

    The shared validator applies the narrower objective safety policy and bounded
    numeric-output fixture before persisting passed or blocked evidence.
    """
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
    """Load a passed validation and its exact implementation dependency.

    The validation status, kind, content-derived ID, implementation identity, and
    source hash are recomputed before returning either payload. This function is
    the fail-closed read boundary used by specification services.

    Returns:
        The validated implementation value and canonical validation payload.

    Raises:
        ValueError: If the report is blocked, has drifted, targets another kind,
            or no longer matches the implementation source.
        ResearchArtifactStoreError: If a referenced artifact cannot be loaded.
    """
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
            prediction_requirements = list(
                implementation.runtime_requirements.get("prediction_requirements") or []
            )
            fixture_bindings = tuple(
                _FixturePredictionBinding(
                    binding_name=str(item["name"]),
                    decision_scope=(
                        "per_symbol"
                        if item.get("inference_scopes") == ["per_symbol"]
                        else "universe_snapshot"
                    ),
                )
                for item in prediction_requirements
            )
            strategy = instantiate_strategy(
                implementation,
                symbols=["SYNTH"],
                asset_class="stocks",
                timeframe="1Min",
                parameters=parameters,
                prediction_bindings=fixture_bindings if prediction_requirements else None,
            )
            if prediction_requirements:
                second = instantiate_strategy(
                    implementation,
                    symbols=["SYNTH"],
                    asset_class="stocks",
                    timeframe="1Min",
                    parameters=parameters,
                    prediction_bindings=fixture_bindings,
                )
                if strategy.strategy_id != second.strategy_id:
                    blockers.append("model-backed strategy fixture identity is not deterministic")
                fixture = {
                    "status": "passed" if not blockers else "blocked",
                    "orders_emitted": 0,
                    "prediction_requirement_count": len(prediction_requirements),
                }
                return fixture, blockers
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


@dataclass(frozen=True)
class _FixturePredictionBinding:
    """Constructor-only placeholder for model-backed implementation validation."""

    binding_name: str
    decision_scope: str
    required_lookback: int = 1
    deployment_id: str = "fixture_deployment"
    deployment_validation_id: str = "fixture_deployment_validation"
    mapper: object = None

    def __post_init__(self) -> None:
        if self.mapper is None:
            object.__setattr__(self, "mapper", _FixturePredictionMapper())


@dataclass(frozen=True)
class _FixturePredictionMapper:
    mapper_id: str = "fixture_mapper:v1"


def _error(command: str, code: str, message: str) -> ApplicationResult:
    return error_result(command=command, code=code, message=message)
