"""Persist governance records produced by deterministic workflow execution.

Registration validates that an objective, approved protocol, and ready plan
share exact identity before saving them. Outcome recording accepts only terminal
summaries whose canonical refs and workflow attribution remain internally
consistent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from trader_research.foundation import (
    ApplicationResult,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    json_payload_hash,
    success_result,
)

from ..artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    EXPERIMENT_PROTOCOL,
    RESEARCH_OBJECTIVE,
    WORKFLOW_OUTCOME,
    WORKFLOW_PLAN,
)
from ..handoffs import ArtifactReportRef
from .enums import (
    ExperimentProtocolStatus,
    ResearchObjectiveStatus,
    WorkflowPlanStatus,
)
from .protocols import ExperimentProtocol, ResearchObjective
from .workflows import WorkflowOutcome, WorkflowPlan


RESEARCH_REGISTER_EXPERIMENT_WORKFLOW = "research_register_experiment_workflow"
RESEARCH_RECORD_WORKFLOW_OUTCOME = "research_record_workflow_outcome"


def register_experiment_workflow(
    *,
    objective: Mapping[str, Any],
    protocol: Mapping[str, Any],
    workflow_plan: Mapping[str, Any],
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Persist a consistent objective, approved protocol, and ready workflow.

    All three mappings are parsed into immutable contracts. Objective and protocol
    IDs must agree, the protocol must be approved, the plan must be ready and
    bound to both inputs, and content digests are recomputed before any record is
    saved. Records are written in dependency order under Orchestration ownership.

    Returns:
        A result containing all three canonical payloads and references, or a
        structured contract, identity, or persistence failure.
    """
    command = RESEARCH_REGISTER_EXPERIMENT_WORKFLOW
    if artifact_store is None:
        return _error(
            command,
            "research_artifact_store_required",
            "A ResearchArtifactStore is required.",
        )
    try:
        parsed_objective = ResearchObjective.from_dict(objective)
        parsed_protocol = ExperimentProtocol.from_dict(protocol)
        parsed_plan = WorkflowPlan.from_dict(workflow_plan)
        if parsed_objective.status is not ResearchObjectiveStatus.APPROVED:
            raise ValueError("research objective must be approved")
        if parsed_protocol.status is not ExperimentProtocolStatus.APPROVED:
            raise ValueError("experiment protocol must be approved")
        if parsed_plan.status is not WorkflowPlanStatus.READY:
            raise ValueError("workflow plan must be ready")
        if parsed_protocol.objective_id != parsed_objective.objective_id:
            raise ValueError("protocol objective_id does not match objective")
        if parsed_plan.objective_ref.artifact_id != parsed_objective.objective_id:
            raise ValueError("workflow plan objective ref does not match objective")
        if parsed_plan.protocol_ref is None:
            raise ValueError("workflow plan protocol ref is required")
        if parsed_plan.protocol_ref.artifact_id != parsed_protocol.protocol_id:
            raise ValueError("workflow plan protocol ref does not match protocol")
        records = (
            _save_contract(
                artifact_store,
                command=command,
                artifact_type=RESEARCH_OBJECTIVE,
                artifact_id=parsed_objective.objective_id,
                payload=parsed_objective.to_dict(),
                status=parsed_objective.status.value,
            ),
            _save_contract(
                artifact_store,
                command=command,
                artifact_type=EXPERIMENT_PROTOCOL,
                artifact_id=parsed_protocol.protocol_id,
                payload=parsed_protocol.to_dict(),
                status=parsed_protocol.status.value,
            ),
            _save_contract(
                artifact_store,
                command=command,
                artifact_type=WORKFLOW_PLAN,
                artifact_id=parsed_plan.plan_id,
                payload=parsed_plan.to_dict(),
                status=parsed_plan.status.value,
            ),
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return _error(
            command,
            "experiment_workflow_registration_failed",
            str(exc),
        )
    return success_result(
        command=command,
        data={
            "research_objective": parsed_objective.to_dict(),
            "experiment_protocol": parsed_protocol.to_dict(),
            "workflow_plan": parsed_plan.to_dict(),
        },
        artifacts={
            "research_objective": records[0].reference().to_dict(),
            "experiment_protocol": records[1].reference().to_dict(),
            "workflow_plan": records[2].reference().to_dict(),
        },
    )


def record_workflow_outcome(
    *,
    outcome: Mapping[str, Any],
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Persist a terminal orchestration summary over canonical evidence.

    The outcome is parsed and required to be terminal. Its workflow plan is
    reloaded and checked for workflow ID and plan digest agreement before the
    outcome is saved; referenced step artifacts remain owned by their specialist
    domains and are not copied into the summary.

    Returns:
        A result containing the canonical outcome and reference, or a structured
        non-terminal, lineage, or persistence failure.
    """
    command = RESEARCH_RECORD_WORKFLOW_OUTCOME
    if artifact_store is None:
        return _error(
            command,
            "research_artifact_store_required",
            "A ResearchArtifactStore is required.",
        )
    try:
        parsed = WorkflowOutcome.from_dict(outcome)
        plan = artifact_store.load_artifact(WORKFLOW_PLAN, parsed.plan_id)
        if str(plan.get("plan_id") or "") != parsed.plan_id:
            raise ValueError("workflow outcome plan does not resolve")
        if str(plan.get("status") or "") != WorkflowPlanStatus.READY.value:
            raise ValueError("workflow outcome plan is not ready")
        objective_ref = _mapping(plan.get("objective_ref"))
        protocol_ref = _mapping(plan.get("protocol_ref"))
        if objective_ref.get("artifact_id") != parsed.objective_ref.artifact_id:
            raise ValueError(
                "workflow outcome objective does not match registered plan"
            )
        if protocol_ref.get("artifact_id") != parsed.protocol_ref.artifact_id:
            raise ValueError(
                "workflow outcome protocol does not match registered plan"
            )
        if parsed.requested_by != plan.get("requested_by"):
            raise ValueError(
                "workflow outcome requested_by does not match registered plan"
            )
        if parsed.actor != plan.get("actor"):
            raise ValueError(
                "workflow outcome actor does not match registered plan"
            )
        _resolve_ref(parsed.objective_ref, artifact_store)
        _resolve_ref(parsed.protocol_ref, artifact_store)
        produced_uris = {
            reference.uri for reference in parsed.produced_artifact_refs
        }
        unknown_reviews = sorted(
            reference.uri
            for reference in parsed.review_verdict_refs
            if reference.uri not in produced_uris
        )
        if unknown_reviews:
            raise ValueError(
                "workflow outcome review refs are not produced refs: "
                + ", ".join(unknown_reviews)
            )
        for reference in parsed.produced_artifact_refs:
            _resolve_ref(reference, artifact_store)
        record = _save_contract(
            artifact_store,
            command=command,
            artifact_type=WORKFLOW_OUTCOME,
            artifact_id=parsed.outcome_id,
            payload=parsed.to_dict(),
            status=parsed.status.value,
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return _error(
            command,
            "workflow_outcome_recording_failed",
            str(exc),
        )
    return success_result(
        command=command,
        data={"workflow_outcome": parsed.to_dict()},
        artifacts={"workflow_outcome": record.reference().to_dict()},
    )


def _save_contract(
    artifact_store: ResearchArtifactStore,
    *,
    command: str,
    artifact_type: str,
    artifact_id: str,
    payload: Mapping[str, Any],
    status: str,
) -> ResearchArtifactRecord:
    return artifact_store.save_artifact(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
        producer_tool=command,
        payload=payload,
        status=status,
    )


def _resolve_ref(
    reference: ArtifactReportRef,
    artifact_store: ResearchArtifactStore,
) -> ResearchArtifactRecord:
    record = artifact_store.load_artifact_record(
        reference.artifact_type,
        reference.artifact_id,
    )
    if record.domain_owner != reference.domain_owner:
        raise ValueError(
            f"workflow outcome artifact authority drift: {reference.uri}"
        )
    if record.payload.get("artifact_type") != reference.artifact_type:
        raise ValueError(
            f"workflow outcome artifact type drift: {reference.uri}"
        )
    expected_hash = str(reference.metadata.get("payload_sha256") or "")
    if expected_hash and json_payload_hash(record.payload) != expected_hash:
        raise ValueError(
            f"workflow outcome artifact payload drift: {reference.uri}"
        )
    return record


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _error(command: str, code: str, message: str) -> ApplicationResult:
    return error_result(command=command, code=code, message=message)
