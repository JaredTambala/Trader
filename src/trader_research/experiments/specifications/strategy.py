"""Immutable strategy specification services."""

from __future__ import annotations

from trader_research.foundation import (
    ApplicationResult,
    PredictionDeploymentReader,
    PredictionMapperCatalog,
    success_result,
)
from trader_research.foundation.artifacts import SCHEMA_VERSION

from typing import Any, Mapping, Sequence

from trader_research.foundation.artifacts import ResearchArtifactStore, ResearchArtifactStoreError
from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    STRATEGY_SPECIFICATION,
    STRATEGY_SPECIFICATION_VALIDATION_REPORT,
)
from trader_research.experiments.implementations import load_passed_implementation, validate_parameters

from .common import resolve_exactly_one, specification_error
from .predictions import build_prediction_bindings, revalidate_prediction_bindings


RESEARCH_CREATE_STRATEGY_SPECIFICATION = "research_create_strategy_specification"
RESEARCH_VALIDATE_STRATEGY_SPECIFICATION = "research_validate_strategy_specification"


def create_strategy_specification(
    *,
    implementation_validation_ref: str,
    parameters: Mapping[str, Any] | None = None,
    sizing: Mapping[str, Any] | None = None,
    portfolio_mode: str = "single_or_multi_asset",
    required_runtime_context: Mapping[str, Any] | None = None,
    execution_assumptions: Mapping[str, Any] | None = None,
    tunable_fields: list[str] | None = None,
    provenance_refs: Sequence[Mapping[str, Any]] | None = None,
    prediction_bindings: Sequence[Mapping[str, Any]] | None = None,
    prediction_deployment_reader: PredictionDeploymentReader | None = None,
    prediction_mapper_catalog: PredictionMapperCatalog | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Create a data-scope-free strategy specification."""
    command = RESEARCH_CREATE_STRATEGY_SPECIFICATION
    if artifact_store is None:
        return specification_error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        implementation, validation = load_passed_implementation(
            artifact_store, implementation_validation_ref, expected_kind="strategy"
        )
        normalized_parameters = dict(parameters or {})
        blockers = validate_parameters(implementation.parameter_schema, normalized_parameters)
        if blockers:
            raise ValueError(blockers[0])
        normalized_sizing = dict(sizing or {})
        normalized_execution = dict(execution_assumptions or {})
        requirements = list(implementation.runtime_requirements.get("prediction_requirements") or [])
        normalized_bindings, decision_scope = build_prediction_bindings(
            requirements=requirements,
            requested_bindings=prediction_bindings,
            deployment_reader=prediction_deployment_reader,
            mapper_catalog=prediction_mapper_catalog,
        )
        _validate_no_scope(normalized_parameters, normalized_sizing, normalized_execution)
        _validate_no_live(normalized_execution)
        normalized_tunable = _validate_tunable_fields(tunable_fields or [], normalized_parameters, normalized_sizing)
        identity = {
            "implementation_version_id": implementation.implementation_version_id,
            "implementation_validation_id": validation["validation_id"],
            "source_hash": implementation.source_hash,
            "parameters": normalized_parameters,
            "sizing": normalized_sizing,
            "portfolio_mode": str(portfolio_mode),
            "required_runtime_context": dict(required_runtime_context or {}),
            "execution_assumptions": normalized_execution,
            "tunable_fields": normalized_tunable,
            "provenance_refs": [dict(item) for item in (provenance_refs or [])],
            "prediction_bindings": normalized_bindings,
            "decision_scope": decision_scope,
        }
        specification_id = stable_research_id("strategy_specification", identity)
        payload = {
            "artifact_type": STRATEGY_SPECIFICATION,
            "schema_version": SCHEMA_VERSION,
            "strategy_specification_id": specification_id,
            **identity,
            "status": "created",
        }
        record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[STRATEGY_SPECIFICATION],
            producer_tool=RESEARCH_CREATE_STRATEGY_SPECIFICATION,
            artifact_type=STRATEGY_SPECIFICATION,
            artifact_id=specification_id,
            payload=payload,
            status="created",
            source_hash=implementation.source_hash,
            metadata={"implementation_version_id": implementation.implementation_version_id},
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return specification_error(command, "strategy_specification_creation_failed", str(exc))
    return success_result(
        command=command,
        data={"strategy_specification": payload},
        artifacts={"strategy_specification": record.reference().to_dict()},
    )


def validate_strategy_specification(
    *,
    strategy_specification_id: str | None = None,
    strategy_specification_uri: str | None = None,
    strategy_specification: Mapping[str, Any] | None = None,
    prediction_deployment_reader: PredictionDeploymentReader | None = None,
    prediction_mapper_catalog: PredictionMapperCatalog | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Revalidate implementation lineage and configuration for a strategy specification."""
    command = RESEARCH_VALIDATE_STRATEGY_SPECIFICATION
    if artifact_store is None:
        return specification_error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        payload = resolve_exactly_one(
            artifact_store,
            STRATEGY_SPECIFICATION,
            artifact_id=strategy_specification_id,
            artifact_uri=strategy_specification_uri,
            inline=strategy_specification,
            label="strategy specification",
        )
        if payload.get("artifact_type") != STRATEGY_SPECIFICATION:
            raise ValueError(f"artifact_type must be {STRATEGY_SPECIFICATION}")
        implementation, validation = load_passed_implementation(
            artifact_store, str(payload.get("implementation_validation_id") or ""), expected_kind="strategy"
        )
        blockers = list(validate_parameters(implementation.parameter_schema, dict(payload.get("parameters") or {})))
        if implementation.implementation_version_id != payload.get("implementation_version_id"):
            blockers.append("strategy specification implementation version does not match validation")
        if implementation.source_hash != payload.get("source_hash"):
            blockers.append("strategy specification source hash drifted")
        if validation.get("validation_id") != payload.get("implementation_validation_id"):
            blockers.append("strategy specification validation lineage drifted")
        try:
            _, decision_scope = revalidate_prediction_bindings(
                requirements=list(
                    implementation.runtime_requirements.get("prediction_requirements") or []
                ),
                persisted_bindings=list(payload.get("prediction_bindings") or []),
                deployment_reader=prediction_deployment_reader,
                mapper_catalog=prediction_mapper_catalog,
            )
            if decision_scope != payload.get("decision_scope"):
                blockers.append("strategy specification decision scope drifted")
        except ValueError as exc:
            blockers.append(str(exc))
        _validate_no_scope(
            dict(payload.get("parameters") or {}),
            dict(payload.get("sizing") or {}),
            dict(payload.get("execution_assumptions") or {}),
        )
        _validate_no_live(dict(payload.get("execution_assumptions") or {}))
    except (ValueError, ResearchArtifactStoreError) as exc:
        return specification_error(command, "strategy_specification_resolution_failed", str(exc))
    report = _validation_report(payload, blockers)
    try:
        record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[STRATEGY_SPECIFICATION_VALIDATION_REPORT],
            producer_tool=RESEARCH_VALIDATE_STRATEGY_SPECIFICATION,
            artifact_type=STRATEGY_SPECIFICATION_VALIDATION_REPORT,
            artifact_id=report["validation_id"],
            payload=report,
            status=report["status"],
            source_hash=str(payload.get("source_hash") or ""),
            metadata={"strategy_specification_id": payload["strategy_specification_id"]},
        )
    except ResearchArtifactStoreError as exc:
        return specification_error(command, "strategy_specification_validation_persistence_failed", str(exc))
    if blockers:
        return ApplicationResult(
            ok=False,
            operation=command,
            data={"strategy_specification_validation_report": report},
            artifacts={"strategy_specification_validation_report": record.reference().to_dict()},
            errors=({"code": "strategy_specification_validation_failed", "message": blockers[0]},),
        )
    return success_result(
        command=command,
        data={"strategy_specification_validation_report": report},
        artifacts={"strategy_specification_validation_report": record.reference().to_dict()},
    )


def load_passed_strategy_specification(
    store: ResearchArtifactStore,
    validation_ref: str,
    *,
    prediction_deployment_reader: PredictionDeploymentReader | None = None,
    prediction_mapper_catalog: PredictionMapperCatalog | None = None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Load a passed strategy specification validation and exact specification."""
    report = store.load_artifact(STRATEGY_SPECIFICATION_VALIDATION_REPORT, _id_from_ref(validation_ref))
    if report.get("status") != "passed" or report.get("valid") is not True or report.get("blockers"):
        raise ValueError("strategy specification validation must be passed, valid, and blocker-free")
    specification_id = str(report.get("strategy_specification_id") or "")
    specification = store.load_artifact(STRATEGY_SPECIFICATION, specification_id)
    identity = {
        "implementation_version_id": specification.get("implementation_version_id"),
        "implementation_validation_id": specification.get("implementation_validation_id"),
        "source_hash": specification.get("source_hash"),
        "parameters": dict(specification.get("parameters") or {}),
        "sizing": dict(specification.get("sizing") or {}),
        "portfolio_mode": str(specification.get("portfolio_mode") or ""),
        "required_runtime_context": dict(specification.get("required_runtime_context") or {}),
        "execution_assumptions": dict(specification.get("execution_assumptions") or {}),
        "tunable_fields": list(specification.get("tunable_fields") or []),
        "provenance_refs": list(specification.get("provenance_refs") or []),
        "prediction_bindings": list(specification.get("prediction_bindings") or []),
        "decision_scope": str(specification.get("decision_scope") or ""),
    }
    if stable_research_id("strategy_specification", identity) != specification_id:
        raise ValueError("strategy specification ID does not match its canonical content")
    if specification.get("source_hash") != report.get("source_hash"):
        raise ValueError("strategy specification source hash does not match validation")
    if stable_research_id(
        "strategy_specification_validation",
        {
            "strategy_specification_id": specification_id,
            "source_hash": report.get("source_hash"),
            "blockers": report.get("blockers") or [],
        },
    ) != report.get("validation_id"):
        raise ValueError("strategy specification validation ID does not match its evidence")
    implementation, validation = load_passed_implementation(
        store, str(specification.get("implementation_validation_id") or ""), expected_kind="strategy"
    )
    if implementation.implementation_version_id != specification.get("implementation_version_id"):
        raise ValueError("strategy implementation version drifted after specification validation")
    if implementation.source_hash != specification.get("source_hash"):
        raise ValueError("strategy implementation source hash drifted after specification validation")
    if validation.get("validation_id") != specification.get("implementation_validation_id"):
        raise ValueError("strategy implementation validation lineage drifted")
    _, decision_scope = revalidate_prediction_bindings(
        requirements=list(implementation.runtime_requirements.get("prediction_requirements") or []),
        persisted_bindings=list(specification.get("prediction_bindings") or []),
        deployment_reader=prediction_deployment_reader,
        mapper_catalog=prediction_mapper_catalog,
    )
    if decision_scope != specification.get("decision_scope"):
        raise ValueError("strategy specification decision scope drifted")
    return specification, report


def _validation_report(payload: Mapping[str, Any], blockers: list[str]) -> dict[str, Any]:
    identity = {
        "strategy_specification_id": payload["strategy_specification_id"],
        "source_hash": payload["source_hash"],
        "blockers": blockers,
    }
    return {
        "artifact_type": STRATEGY_SPECIFICATION_VALIDATION_REPORT,
        "schema_version": SCHEMA_VERSION,
        "validation_id": stable_research_id("strategy_specification_validation", identity),
        **identity,
        "status": "passed" if not blockers else "blocked",
        "valid": not blockers,
        "warnings": [],
    }


def _validate_no_scope(*sections: Mapping[str, Any]) -> None:
    forbidden = {"symbols", "asset_class", "timeframe", "start", "end", "source_filter", "dataset_id"}
    found = sorted({name for section in sections for name in section if name in forbidden})
    if found:
        raise ValueError(f"strategy specification cannot contain data scope fields: {found}")


def _validate_no_live(assumptions: Mapping[str, Any]) -> None:
    for name in ("broker_mutation_allowed", "live_trading_allowed", "raw_sql_allowed"):
        if assumptions.get(name) is True:
            raise ValueError(f"execution_assumptions.{name} must be false")


def _validate_tunable_fields(
    fields: list[str],
    parameters: Mapping[str, Any],
    sizing: Mapping[str, Any],
) -> list[str]:
    allowed = {f"/strategy/parameters/{name}" for name in parameters} | {
        f"/strategy/sizing/{name}" for name in sizing
    }
    normalized = sorted(set(str(item).strip() for item in fields if str(item).strip()))
    unknown = sorted(set(normalized).difference(allowed))
    if unknown:
        raise ValueError(f"tunable_fields contain unknown or forbidden paths: {unknown}")
    return normalized


def _id_from_ref(ref: str) -> str:
    return str(ref).rstrip("/").rsplit("/", 1)[-1]
