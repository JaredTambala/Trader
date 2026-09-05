"""Persist protocol proposals and deterministic workflow governance records.

Proposal creation pins canonical design inputs without granting approval.
Workflow registration validates that an objective, approved protocol, and ready
plan share exact identity before saving them. Outcome recording accepts only
terminal summaries whose canonical refs and workflow attribution remain
internally consistent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from trader_research.foundation import (
    ApplicationResult,
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    json_payload_hash,
    success_result,
)

from ..artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
    EXPERIMENT_DESIGN_AGENT_OWNER,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
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
from .proposals import (
    ExperimentDesignRequest,
    ExperimentProtocolProposal,
    build_experiment_protocol_proposal,
    experiment_design_input_refs,
    replace_experiment_design_refs,
)
from .protocols import ExperimentProtocol, ProtocolDataset, ResearchObjective
from .workflows import WorkflowOutcome, WorkflowPlan


RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL = (
    "research_create_experiment_protocol_proposal"
)
RESEARCH_REGISTER_EXPERIMENT_WORKFLOW = "research_register_experiment_workflow"
RESEARCH_RECORD_WORKFLOW_OUTCOME = "research_record_workflow_outcome"


def create_experiment_protocol_proposal(
    *,
    objective: Mapping[str, Any],
    design_request: Mapping[str, Any],
    task_id: str,
    requested_by: str,
    actor: str,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Validate, pin, and persist one immutable experiment protocol proposal.

    The operation resolves every implementation, Data, and optional optimization
    input through the canonical store before deriving proposal identity. Exact
    replay returns the existing proposal; a conflicting record under the same
    identity fails without overwriting accepted evidence.

    Args:
        objective: Complete approved research-objective payload.
        design_request: Complete structured experiment-design request.
        task_id: Exact specialist task requesting the proposal.
        requested_by: Composition or workflow request identity.
        actor: Registered Experiment Design actor invoking the operation.
        artifact_store: Canonical store used for reads and proposal persistence.

    Returns:
        Application result containing the proposal payload and canonical ref, or
        a structured validation, identity, or persistence error.
    """
    command = RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL
    if artifact_store is None:
        return _error(
            command,
            "research_artifact_store_required",
            "A ResearchArtifactStore is required.",
        )
    try:
        parsed_objective = ResearchObjective.from_dict(objective)
        parsed_design = ExperimentDesignRequest.from_dict(design_request)
        normalized_task_id = _required_value(task_id, "task_id")
        normalized_requester = _required_value(requested_by, "requested_by")
        normalized_actor = _required_value(actor, "actor")
        if parsed_objective.status is not ResearchObjectiveStatus.APPROVED:
            raise ValueError("experiment design requires an approved objective")
        if normalized_actor != EXPERIMENT_DESIGN_AGENT_OWNER:
            raise ValueError(
                "experiment protocol proposals require the registered "
                "Experiment Design actor"
            )
        _validate_objective_implementation_scope(parsed_objective, parsed_design)
        pinned = _pin_experiment_design(parsed_design, artifact_store)
        proposal = build_experiment_protocol_proposal(
            objective=parsed_objective,
            design=pinned.design,
            task_id=normalized_task_id,
            requested_by=normalized_requester,
            proposed_by=normalized_actor,
            input_refs=pinned.input_refs,
        )
        record = _save_proposal_idempotently(
            artifact_store,
            proposal=proposal,
            command=command,
            requested_by=normalized_requester,
            actor=normalized_actor,
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return _error(
            command,
            "experiment_protocol_proposal_failed",
            str(exc),
        )
    return success_result(
        command=command,
        data={"experiment_protocol_proposal": proposal.to_dict()},
        artifacts={"experiment_protocol_proposal": record.reference().to_dict()},
    )


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


@dataclass(frozen=True)
class _PinnedExperimentDesign:
    """Internal normalized result of canonical design-input validation."""

    design: ExperimentDesignRequest
    input_refs: tuple[ArtifactReportRef, ...]


def _pin_experiment_design(
    design: ExperimentDesignRequest,
    artifact_store: ResearchArtifactStore,
) -> _PinnedExperimentDesign:
    records: dict[str, ResearchArtifactRecord] = {}
    pinned: dict[str, ArtifactReportRef] = {}
    for reference in experiment_design_input_refs(design):
        record = artifact_store.load_artifact_record(
            reference.artifact_type,
            reference.artifact_id,
        )
        _validate_record_identity(reference, record)
        records[reference.uri] = record
        pinned[reference.uri] = _pinned_ref(reference, record)
    _validate_implementation_record(
        records[design.strategy.implementation_ref.uri],
        expected_kind="strategy",
    )
    for risk in design.risk_managers:
        _validate_implementation_record(
            records[risk.implementation_ref.uri],
            expected_kind="risk_manager",
        )
    for dataset in design.datasets:
        _validate_dataset_records(
            dataset,
            manifest=records[dataset.dataset_manifest_ref.uri],
            quality=records[dataset.data_quality_report_ref.uri],
        )
    if design.optimization is not None:
        objective_uri = design.optimization.objective_validation_ref
        _validate_optimization_validation(records[objective_uri])
    pinned_design = replace_experiment_design_refs(design, pinned)
    ordered_refs = tuple(
        pinned[reference.uri] for reference in experiment_design_input_refs(design)
    )
    return _PinnedExperimentDesign(pinned_design, ordered_refs)


def _validate_objective_implementation_scope(
    objective: ResearchObjective,
    design: ExperimentDesignRequest,
) -> None:
    supplied = {item.uri for item in objective.supplied_artifact_refs}
    required = {
        design.strategy.implementation_ref.uri,
        *(item.implementation_ref.uri for item in design.risk_managers),
    }
    missing = sorted(required.difference(supplied))
    if missing:
        raise ValueError(
            "experiment design implementations are not supplied by the objective: "
            + ", ".join(missing)
        )


def _validate_record_identity(
    reference: ArtifactReportRef,
    record: ResearchArtifactRecord,
) -> None:
    if record.uri != reference.uri or record.artifact_type != reference.artifact_type:
        raise ValueError(f"canonical design input identity drift: {reference.uri}")
    if record.domain_owner != reference.domain_owner:
        raise ValueError(f"canonical design input authority drift: {reference.uri}")
    if record.payload.get("artifact_type") != reference.artifact_type:
        raise ValueError(f"canonical design input type drift: {reference.uri}")
    expected_digest = str(reference.metadata.get("payload_sha256") or "")
    if expected_digest and expected_digest != json_payload_hash(record.payload):
        raise ValueError(f"canonical design input payload drift: {reference.uri}")


def _validate_implementation_record(
    record: ResearchArtifactRecord,
    *,
    expected_kind: str,
) -> None:
    if record.artifact_type != IMPLEMENTATION_VERSION:
        raise ValueError("experiment design implementation ref has the wrong type")
    if record.payload.get("implementation_kind") != expected_kind:
        raise ValueError(
            f"experiment design requires a {expected_kind} implementation"
        )
    expected_producer = f"research_register_{expected_kind}_implementation"
    if record.producer_tool != expected_producer:
        raise ValueError(
            "experiment design implementation has the wrong producer"
        )
    if record.payload.get("status") != "registered" or record.status != "registered":
        raise ValueError("experiment design implementation must be registered")


def _validate_dataset_records(
    dataset: ProtocolDataset,
    *,
    manifest: ResearchArtifactRecord,
    quality: ResearchArtifactRecord,
) -> None:
    if manifest.artifact_type != DATASET_MANIFEST:
        raise ValueError("experiment design dataset manifest ref has the wrong type")
    if quality.artifact_type != DATA_QUALITY_REPORT:
        raise ValueError("experiment design quality ref has the wrong type")
    for record in (manifest, quality):
        if record.producer_tool != "data_create_research_snapshot":
            raise ValueError("experiment design Data evidence has the wrong producer")
        if record.status != "captured" or record.payload.get("status") != "captured":
            raise ValueError("experiment design Data evidence must be captured")
        if record.payload.get("complete") is not True:
            raise ValueError("experiment design Data evidence must be complete")
        _validate_data_scope(record.payload, dataset)
    manifest_dataset_id = str(manifest.payload.get("dataset_id") or "")
    if not manifest_dataset_id or manifest_dataset_id != str(
        quality.payload.get("dataset_id") or ""
    ):
        raise ValueError("experiment design Data refs identify different datasets")
    if quality.metadata.get("dataset_manifest_artifact_id") != manifest.artifact_id:
        raise ValueError(
            "experiment design quality ref does not cite the matching manifest"
        )


def _validate_data_scope(
    payload: Mapping[str, Any],
    dataset: ProtocolDataset,
) -> None:
    requirement = dataset.requirement
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or tuple(str(item) for item in symbols) != tuple(
        requirement.symbols
    ):
        raise ValueError("experiment design Data symbols do not match requirement")
    for key, expected in (
        ("asset_class", requirement.asset_class),
        ("timeframe", requirement.timeframe),
        ("source_filter", requirement.source),
    ):
        if payload.get(key) != expected:
            raise ValueError(f"experiment design Data {key} does not match requirement")
    window = payload.get("requested_window")
    if not isinstance(window, Mapping):
        raise ValueError("experiment design Data requested_window is invalid")
    if not _timestamps_equal(window.get("start"), requirement.start):
        raise ValueError("experiment design Data start does not match requirement")
    if not _timestamps_equal(window.get("end"), requirement.end):
        raise ValueError("experiment design Data end does not match requirement")


def _validate_optimization_validation(record: ResearchArtifactRecord) -> None:
    if record.artifact_type != IMPLEMENTATION_VALIDATION_REPORT:
        raise ValueError("optimization objective ref has the wrong artifact type")
    if record.producer_tool != "research_validate_optimization_objective":
        raise ValueError("optimization objective validation has the wrong producer")
    if (
        record.payload.get("implementation_kind") != "optimization_objective"
        or record.payload.get("status") != "passed"
        or record.payload.get("valid") is not True
        or record.payload.get("blockers")
    ):
        raise ValueError("optimization objective validation must be passed")


def _pinned_ref(
    reference: ArtifactReportRef,
    record: ResearchArtifactRecord,
) -> ArtifactReportRef:
    return ArtifactReportRef(
        artifact_id=reference.artifact_id,
        artifact_type=reference.artifact_type,
        domain_owner=reference.domain_owner,
        uri=reference.uri,
        metadata={
            **dict(reference.metadata),
            "payload_sha256": json_payload_hash(record.payload),
            "producer_tool": record.producer_tool,
            "requested_by": record.requested_by,
            "actor": record.actor,
            "status": record.status,
        },
    )


def _save_proposal_idempotently(
    artifact_store: ResearchArtifactStore,
    *,
    proposal: ExperimentProtocolProposal,
    command: str,
    requested_by: str,
    actor: str,
) -> ResearchArtifactRecord:
    try:
        existing = artifact_store.load_artifact_record(
            EXPERIMENT_PROTOCOL_PROPOSAL,
            proposal.proposal_id,
        )
    except ResearchArtifactNotFound:
        existing = None
    payload = proposal.to_dict()
    metadata = {
        "objective_id": proposal.objective_id,
        "protocol_id": proposal.protocol.protocol_id,
        "design_digest": proposal.design_digest,
    }
    if existing is not None:
        if (
            existing.payload != payload
            or existing.domain_owner
            != DOMAIN_OWNER_BY_ARTIFACT_TYPE[EXPERIMENT_PROTOCOL_PROPOSAL]
            or existing.producer_tool != command
            or existing.requested_by != requested_by
            or existing.actor != actor
            or existing.status != proposal.status
            or existing.metadata != metadata
        ):
            raise ValueError("existing experiment protocol proposal conflicts")
        return existing
    return artifact_store.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL_PROPOSAL,
        artifact_id=proposal.proposal_id,
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[EXPERIMENT_PROTOCOL_PROPOSAL],
        producer_tool=command,
        payload=payload,
        requested_by=requested_by,
        actor=actor,
        status=proposal.status,
        metadata=metadata,
    )


def _timestamps_equal(left: object, right: object) -> bool:
    try:
        left_value = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        right_value = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
    except ValueError:
        return False
    if left_value.tzinfo is None or right_value.tzinfo is None:
        return False
    return left_value.astimezone(timezone.utc) == right_value.astimezone(
        timezone.utc
    )


def _required_value(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


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
