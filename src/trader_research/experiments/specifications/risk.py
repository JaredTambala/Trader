"""Immutable ordered risk-stack specification services."""

from __future__ import annotations

from trader_research.governance.artifacts import QUANT_RESEARCH_SUPERVISOR_OWNER

from trader_research.foundation import ApplicationResult, success_result
from trader_research.foundation.artifacts import SCHEMA_VERSION

from typing import Any, Mapping, Sequence

from trader_research.foundation.artifacts import ResearchArtifactStore, ResearchArtifactStoreError
from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import (
    RISK_STACK_SPECIFICATION,
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
)
from trader_research.experiments.implementations import load_passed_implementation, validate_parameters

from .common import mapping, resolve_exactly_one, specification_error


RESEARCH_CREATE_RISK_STACK_SPECIFICATION = "research_create_risk_stack_specification"
RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION = "research_validate_risk_stack_specification"


def create_risk_stack_specification(
    *,
    risk_managers: Sequence[Mapping[str, Any]],
    execution_assumptions: Mapping[str, Any] | None = None,
    provenance_refs: Sequence[Mapping[str, Any]] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Create an ordered risk-stack over passed implementation validations."""
    command = RESEARCH_CREATE_RISK_STACK_SPECIFICATION
    if artifact_store is None:
        return specification_error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        if not risk_managers:
            raise ValueError("risk_managers must contain at least one ordered item")
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(risk_managers):
            row = mapping(item, f"risk_managers[{index}]")
            validation_ref = str(row.get("implementation_validation_ref") or "").strip()
            implementation, validation = load_passed_implementation(
                artifact_store, validation_ref, expected_kind="risk_manager"
            )
            parameters = dict(row.get("parameters") or {})
            blockers = validate_parameters(implementation.parameter_schema, parameters)
            if blockers:
                raise ValueError(f"risk_managers[{index}]: {blockers[0]}")
            normalized.append(
                {
                    "order": index,
                    "implementation_version_id": implementation.implementation_version_id,
                    "implementation_validation_id": validation["validation_id"],
                    "source_hash": implementation.source_hash,
                    "parameters": parameters,
                    "tunable_fields": _risk_tunable_fields(index, row.get("tunable_fields") or [], parameters),
                }
            )
        assumptions = dict(execution_assumptions or {})
        for name in ("broker_mutation_allowed", "live_trading_allowed", "raw_sql_allowed"):
            if assumptions.get(name) is True:
                raise ValueError(f"execution_assumptions.{name} must be false")
        identity = {
            "risk_managers": normalized,
            "execution_assumptions": assumptions,
            "provenance_refs": [dict(item) for item in (provenance_refs or ())],
        }
        specification_id = stable_research_id("risk_stack_specification", identity)
        payload = {
            "artifact_type": RISK_STACK_SPECIFICATION,
            "schema_version": SCHEMA_VERSION,
            "risk_stack_specification_id": specification_id,
            **identity,
            "status": "created",
        }
        record = artifact_store.save_artifact(
            agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
            artifact_type=RISK_STACK_SPECIFICATION,
            artifact_id=specification_id,
            payload=payload,
            status="created",
            metadata={"manager_count": len(normalized)},
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return specification_error(command, "risk_stack_specification_creation_failed", str(exc))
    return success_result(
        command=command,
        data={"risk_stack_specification": payload},
        artifacts={"risk_stack_specification": record.reference().to_dict()},
    )


def validate_risk_stack_specification(
    *,
    risk_stack_specification_id: str | None = None,
    risk_stack_specification_uri: str | None = None,
    risk_stack_specification: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Revalidate every ordered risk implementation and source hash."""
    command = RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION
    if artifact_store is None:
        return specification_error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        payload = resolve_exactly_one(
            artifact_store,
            RISK_STACK_SPECIFICATION,
            artifact_id=risk_stack_specification_id,
            artifact_uri=risk_stack_specification_uri,
            inline=risk_stack_specification,
            label="risk-stack specification",
        )
        if payload.get("artifact_type") != RISK_STACK_SPECIFICATION:
            raise ValueError(f"artifact_type must be {RISK_STACK_SPECIFICATION}")
        blockers: list[str] = []
        managers = payload.get("risk_managers") or []
        if not isinstance(managers, list) or not managers:
            blockers.append("risk-stack specification requires ordered risk managers")
        for index, item in enumerate(managers):
            row = mapping(item, f"risk_managers[{index}]")
            implementation, _ = load_passed_implementation(
                artifact_store, str(row.get("implementation_validation_id") or ""), expected_kind="risk_manager"
            )
            if row.get("order") != index:
                blockers.append(f"risk_managers[{index}].order must preserve array order")
            if implementation.implementation_version_id != row.get("implementation_version_id"):
                blockers.append(f"risk_managers[{index}] implementation version drifted")
            if implementation.source_hash != row.get("source_hash"):
                blockers.append(f"risk_managers[{index}] source hash drifted")
            blockers.extend(validate_parameters(implementation.parameter_schema, dict(row.get("parameters") or {})))
    except (ValueError, ResearchArtifactStoreError) as exc:
        return specification_error(command, "risk_stack_specification_resolution_failed", str(exc))
    identity = {
        "risk_stack_specification_id": payload["risk_stack_specification_id"],
        "manager_source_hashes": [item.get("source_hash") for item in payload.get("risk_managers", [])],
        "blockers": blockers,
    }
    report = {
        "artifact_type": RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
        "schema_version": SCHEMA_VERSION,
        "validation_id": stable_research_id("risk_stack_specification_validation", identity),
        **identity,
        "status": "passed" if not blockers else "blocked",
        "valid": not blockers,
        "warnings": [],
    }
    try:
        record = artifact_store.save_artifact(
            agent_owner=QUANT_RESEARCH_SUPERVISOR_OWNER,
            artifact_type=RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
            artifact_id=report["validation_id"],
            payload=report,
            status=report["status"],
            metadata={"risk_stack_specification_id": payload["risk_stack_specification_id"]},
        )
    except ResearchArtifactStoreError as exc:
        return specification_error(command, "risk_stack_specification_validation_persistence_failed", str(exc))
    if blockers:
        return ApplicationResult(
            ok=False,
            operation=command,
            data={"risk_stack_specification_validation_report": report},
            artifacts={"risk_stack_specification_validation_report": record.reference().to_dict()},
            errors=({"code": "risk_stack_specification_validation_failed", "message": blockers[0]},),
        )
    return success_result(
        command=command,
        data={"risk_stack_specification_validation_report": report},
        artifacts={"risk_stack_specification_validation_report": record.reference().to_dict()},
    )


def load_passed_risk_stack_specification(
    store: ResearchArtifactStore,
    validation_ref: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Load one passed risk-stack specification validation and its specification."""
    validation_id = str(validation_ref).rstrip("/").rsplit("/", 1)[-1]
    report = store.load_artifact(RISK_STACK_SPECIFICATION_VALIDATION_REPORT, validation_id)
    if report.get("status") != "passed" or report.get("valid") is not True or report.get("blockers"):
        raise ValueError("risk-stack specification validation must be passed, valid, and blocker-free")
    specification = store.load_artifact(
        RISK_STACK_SPECIFICATION, str(report.get("risk_stack_specification_id") or "")
    )
    specification_id = str(specification.get("risk_stack_specification_id") or "")
    identity = {
        "risk_managers": list(specification.get("risk_managers") or []),
        "execution_assumptions": dict(specification.get("execution_assumptions") or {}),
        "provenance_refs": list(specification.get("provenance_refs") or []),
    }
    if stable_research_id("risk_stack_specification", identity) != specification_id:
        raise ValueError("risk-stack specification ID does not match its canonical content")
    manager_hashes = [item.get("source_hash") for item in specification.get("risk_managers", [])]
    if manager_hashes != list(report.get("manager_source_hashes") or []):
        raise ValueError("risk-stack source hashes do not match validation evidence")
    if stable_research_id(
        "risk_stack_specification_validation",
        {
            "risk_stack_specification_id": specification_id,
            "manager_source_hashes": manager_hashes,
            "blockers": report.get("blockers") or [],
        },
    ) != report.get("validation_id"):
        raise ValueError("risk-stack validation ID does not match its evidence")
    for index, row in enumerate(specification.get("risk_managers", [])):
        implementation, validation = load_passed_implementation(
            store, str(row.get("implementation_validation_id") or ""), expected_kind="risk_manager"
        )
        if row.get("order") != index:
            raise ValueError("risk-stack manager order drifted after validation")
        if implementation.implementation_version_id != row.get("implementation_version_id"):
            raise ValueError("risk-manager implementation version drifted after validation")
        if implementation.source_hash != row.get("source_hash"):
            raise ValueError("risk-manager source hash drifted after validation")
        if validation.get("validation_id") != row.get("implementation_validation_id"):
            raise ValueError("risk-manager validation lineage drifted")
    return specification, report


def _risk_tunable_fields(index: int, fields: Any, parameters: Mapping[str, Any]) -> list[str]:
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes)):
        raise ValueError(f"risk_managers[{index}].tunable_fields must be an array")
    allowed = {f"/risk/{index}/parameters/{name}" for name in parameters}
    normalized = sorted(set(str(item).strip() for item in fields if str(item).strip()))
    unknown = sorted(set(normalized).difference(allowed))
    if unknown:
        raise ValueError(f"risk_managers[{index}].tunable_fields contain unknown or forbidden paths: {unknown}")
    return normalized
