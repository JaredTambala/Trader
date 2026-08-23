"""Validate specialist and protocol evidence at the composition boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from trader_research.foundation import (
    ResearchArtifactStore,
    json_payload_hash,
    parse_research_artifact_uri,
)
from trader_research.governance import (
    EXPERIMENT_PROTOCOL_PROPOSAL,
    WORKFLOW_OUTCOME,
    ArtifactReportRef,
    ExperimentProtocol,
    ExperimentProtocolProposal,
    SpecialistHandoff,
    experiment_protocol_design_digest,
    get_decision_authority,
)

from trader_agents.data_agent import DATA_SPECIALIST_AUTHORITY
from trader_agents.experiment_design_agent import EXPERIMENT_DESIGN_AUTHORITY
from trader_agents.specialists import (
    AcceptedSpecialistResult,
    RegisteredSpecialistRoute,
    SpecialistResult,
    SpecialistResultStatus,
    SpecialistTask,
    specialist_task_digest,
)


def accept_specialist_result(
    *,
    task: SpecialistTask,
    result: SpecialistResult,
    route: RegisteredSpecialistRoute,
    artifact_store: ResearchArtifactStore,
) -> AcceptedSpecialistResult:
    """Validate and summarize one completed specialist result.

    The result must match the exact task and selected route. Every handoff URI is
    resolved through the canonical store and checked for identity, ownership,
    producer, requester, actor, and payload digest before a bounded receipt is
    returned.

    Args:
        task: Original caller-built task selected by the Coordinator.
        result: Terminal result returned by the registered specialist graph.
        route: Exact code-owned route pinned by the decision.
        artifact_store: Canonical store used to resolve every handoff.

    Returns:
        Checkpoint-safe accepted-result receipt with canonical refs only.

    Raises:
        ValueError: If result identity, output binding, or canonical evidence
            differs from the original task or selected route.
    """
    summary = summarize_specialist_result(
        task=task,
        result=result,
        route=route,
        artifact_store=artifact_store,
    )
    if result.status is not SpecialistResultStatus.COMPLETED:
        raise ValueError("only completed specialist results can be accepted")
    raw_refs = cast(Sequence[Mapping[str, Any]], summary["artifact_refs"])
    raw_bindings = cast(
        Mapping[str, Sequence[str]],
        summary["output_bindings"],
    )
    return AcceptedSpecialistResult(
        task_id=task.task_id,
        authority_key=task.authority_key,
        task_digest=specialist_task_digest(task),
        route_version=route.descriptor.version,
        result_digest=json_payload_hash(result.to_dict()),
        artifact_refs=tuple(ArtifactReportRef.from_dict(item) for item in raw_refs),
        output_bindings={
            slot_id: tuple(uris) for slot_id, uris in raw_bindings.items()
        },
    )


def summarize_specialist_result(
    *,
    task: SpecialistTask,
    result: SpecialistResult,
    route: RegisteredSpecialistRoute,
    artifact_store: ResearchArtifactStore,
) -> dict[str, Any]:
    """Validate one terminal result and return bounded canonical-ref summary.

    Unlike ``accept_specialist_result``, this function also summarizes waiting,
    blocked, and failed results so their inspectable refs and typed issues survive
    composition without storing complete handoff inputs or artifact payloads.
    """
    if result.task_id != task.task_id:
        raise ValueError("specialist result task_id does not match selected task")
    if result.authority_key != task.authority_key:
        raise ValueError("specialist result authority does not match selected task")
    if result.requested_by != task.requested_by:
        raise ValueError("specialist result requester does not match selected task")
    if route.descriptor.authority_key != task.authority_key:
        raise ValueError("specialist result route authority does not match task")
    requested_slots = {slot.slot_id: slot for slot in task.requested_outputs}
    if set(result.output_bindings) != set(requested_slots):
        raise ValueError("specialist result bindings do not match requested task slots")
    handoff_by_id = {handoff.handoff_id: handoff for handoff in result.handoffs}
    artifact_refs = tuple(
        _verified_handoff_ref(
            handoff=handoff,
            task=task,
            route=route,
            artifact_store=artifact_store,
        )
        for handoff in result.handoffs
    )
    uri_by_handoff_id = {
        handoff_id: handoff.artifact_uri or ""
        for handoff_id, handoff in handoff_by_id.items()
    }
    output_bindings: dict[str, tuple[str, ...]] = {}
    for slot_id, handoff_ids in result.output_bindings.items():
        try:
            uris = tuple(uri_by_handoff_id[handoff_id] for handoff_id in handoff_ids)
        except KeyError as exc:
            raise ValueError(
                "specialist result binding references an unknown handoff"
            ) from exc
        slot = requested_slots[slot_id]
        if any(
            handoff_by_id[handoff_id].artifact_type != slot.artifact_type
            or handoff_by_id[handoff_id].domain_owner != slot.domain_owner
            for handoff_id in handoff_ids
        ):
            raise ValueError(
                f"specialist result binding does not satisfy task slot {slot_id}"
            )
        output_bindings[slot_id] = uris
    return {
        "task_id": task.task_id,
        "authority_key": task.authority_key,
        "task_digest": specialist_task_digest(task),
        "route_version": route.descriptor.version,
        "result_digest": json_payload_hash(result.to_dict()),
        "status": result.status.value,
        "artifact_refs": [item.to_dict() for item in artifact_refs],
        "output_bindings": {
            slot_id: list(uris) for slot_id, uris in output_bindings.items()
        },
        "prerequisites": [item.to_dict() for item in result.prerequisites],
        "warnings": [item.to_dict() for item in result.warnings],
        "blockers": [item.to_dict() for item in result.blockers],
        "errors": [item.to_dict() for item in result.errors],
    }


def validate_protocol_consumes_specialist_outputs(
    *,
    protocol: ExperimentProtocol,
    accepted_results: Sequence[AcceptedSpecialistResult],
) -> None:
    """Require an approved protocol to pin every required Data output.

    Future specialist routes can define their own downstream binding contracts.
    The current production composition has one concrete rule: every manifest and
    quality ref returned by an accepted Data task must be present in a protocol
    dataset before workflow compilation.

    Args:
        protocol: Approved protocol about to reach workflow compilation.
        accepted_results: Validated completed specialist receipts.

    Raises:
        ValueError: If any accepted Data output is not consumed by the protocol.
    """
    protocol_data_uris = {
        reference.uri
        for dataset in protocol.datasets
        for reference in (
            dataset.dataset_manifest_ref,
            dataset.data_quality_report_ref,
        )
    }
    required_data_uris = {
        reference.uri
        for receipt in accepted_results
        if receipt.authority_key == DATA_SPECIALIST_AUTHORITY
        for reference in receipt.artifact_refs
    }
    missing = sorted(required_data_uris.difference(protocol_data_uris))
    if missing:
        raise ValueError(
            "approved protocol does not consume required Data specialist refs: "
            + ", ".join(missing)
        )


def revalidate_accepted_specialist_results(
    *,
    accepted_results: Sequence[AcceptedSpecialistResult],
    artifact_store: ResearchArtifactStore,
) -> None:
    """Revalidate canonical refs retained by accepted-result receipts.

    Args:
        accepted_results: Checkpointed receipts being reused on resume.
        artifact_store: Current canonical store view.

    Raises:
        ValueError: If a ref no longer matches its authority or stored metadata.
    """
    for receipt in accepted_results:
        authority = get_decision_authority(receipt.authority_key)
        for reference in receipt.artifact_refs:
            if reference.domain_owner not in authority.artifact_domains:
                raise ValueError(
                    "accepted specialist ref exceeds its decision authority: "
                    f"{reference.uri}"
                )
            _revalidate_canonical_ref(
                reference=reference,
                artifact_store=artifact_store,
            )


def resolve_accepted_protocol_proposal(
    *,
    accepted_results: Sequence[AcceptedSpecialistResult],
    artifact_store: ResearchArtifactStore,
) -> tuple[ExperimentProtocolProposal, ArtifactReportRef] | None:
    """Resolve the sole accepted Experiment Design proposal, when present.

    Args:
        accepted_results: Validated specialist receipts in composition order.
        artifact_store: Current canonical artifact-store view.

    Returns:
        Parsed proposal and its digest-pinned canonical ref, or ``None`` when no
        Experiment Design task has completed.

    Raises:
        ValueError: If multiple proposals, wrong output types, task lineage, or
            canonical content drift are observed.
    """
    design_results = tuple(
        item
        for item in accepted_results
        if item.authority_key == EXPERIMENT_DESIGN_AUTHORITY
    )
    if not design_results:
        return None
    if len(design_results) != 1:
        raise ValueError("composition accepts at most one protocol proposal")
    receipt = design_results[0]
    if (
        len(receipt.artifact_refs) != 1
        or receipt.artifact_refs[0].artifact_type
        != EXPERIMENT_PROTOCOL_PROPOSAL
    ):
        raise ValueError("Experiment Design result must contain one proposal ref")
    reference = receipt.artifact_refs[0]
    _revalidate_canonical_ref(
        reference=reference,
        artifact_store=artifact_store,
    )
    record = artifact_store.load_artifact_record(
        reference.artifact_type,
        reference.artifact_id,
    )
    proposal = ExperimentProtocolProposal.from_dict(record.payload)
    if proposal.task_id != receipt.task_id:
        raise ValueError("protocol proposal task lineage drift")
    return proposal, reference


def validate_protocol_matches_proposal(
    *,
    protocol: ExperimentProtocol,
    proposal: ExperimentProtocolProposal,
) -> None:
    """Require an operator protocol to be the same design as its proposal."""
    if protocol.protocol_id != proposal.protocol.protocol_id:
        raise ValueError("approved protocol identity does not match proposal")
    if protocol.objective_id != proposal.objective_id:
        raise ValueError("approved protocol objective does not match proposal")
    if experiment_protocol_design_digest(protocol) != proposal.design_digest:
        raise ValueError("approved protocol design does not match proposal")


def revalidate_composition_outcome(
    *,
    outcome_ref: ArtifactReportRef,
    outcome_digest: str,
    artifact_store: ResearchArtifactStore,
) -> None:
    """Revalidate the terminal outcome referenced by composition state.

    Args:
        outcome_ref: Canonical terminal outcome reference from the checkpoint.
        outcome_digest: Exact outcome-payload digest pinned by composition.
        artifact_store: Current canonical store view.

    Raises:
        ValueError: If identity, metadata, or payload content has drifted.
    """
    if outcome_ref.artifact_type != WORKFLOW_OUTCOME:
        raise ValueError("composition terminal ref is not a workflow outcome")
    observed_digest = _revalidate_canonical_ref(
        reference=outcome_ref,
        artifact_store=artifact_store,
    )
    if not outcome_digest or observed_digest != outcome_digest:
        raise ValueError("canonical composition outcome payload drift")


def _verified_handoff_ref(
    *,
    handoff: SpecialistHandoff,
    task: SpecialistTask,
    route: RegisteredSpecialistRoute,
    artifact_store: ResearchArtifactStore,
) -> ArtifactReportRef:
    uri = handoff.artifact_uri or ""
    artifact_type, artifact_id = parse_research_artifact_uri(uri)
    if artifact_type != handoff.artifact_type:
        raise ValueError(f"specialist handoff artifact type does not match URI: {uri}")
    if artifact_type not in route.descriptor.supported_output_types:
        raise ValueError(f"specialist route does not support handoff type: {uri}")
    record = artifact_store.load_artifact_record(artifact_type, artifact_id)
    if record.uri != uri or record.artifact_type != artifact_type:
        raise ValueError(f"canonical specialist record identity mismatch: {uri}")
    if record.domain_owner != handoff.domain_owner:
        raise ValueError(f"canonical specialist record authority drift: {uri}")
    if record.producer_tool != handoff.producer_tool:
        raise ValueError(f"canonical specialist record producer drift: {uri}")
    if record.requested_by != task.requested_by:
        raise ValueError(f"canonical specialist record requester drift: {uri}")
    if record.actor != handoff.actor:
        raise ValueError(f"canonical specialist record actor drift: {uri}")
    expected_digest = str(handoff.provenance_refs.get("payload_sha256") or "")
    if not expected_digest:
        raise ValueError(f"specialist handoff lacks canonical payload digest: {uri}")
    observed_digest = json_payload_hash(record.payload)
    if observed_digest != expected_digest:
        raise ValueError(f"canonical specialist record payload drift: {uri}")
    return ArtifactReportRef(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        domain_owner=record.domain_owner,
        uri=uri,
        metadata={
            "payload_sha256": observed_digest,
            "producer_tool": record.producer_tool,
            "requested_by": record.requested_by,
            "actor": record.actor,
            "status": record.status,
        },
    )


def _revalidate_canonical_ref(
    *,
    reference: ArtifactReportRef,
    artifact_store: ResearchArtifactStore,
) -> str:
    artifact_type, artifact_id = parse_research_artifact_uri(reference.uri)
    if artifact_type != reference.artifact_type or artifact_id != reference.artifact_id:
        raise ValueError(f"canonical composition ref identity drift: {reference.uri}")
    record = artifact_store.load_artifact_record(artifact_type, artifact_id)
    if record.uri != reference.uri or record.domain_owner != reference.domain_owner:
        raise ValueError(f"canonical composition ref authority drift: {reference.uri}")
    expected_metadata = {
        "producer_tool": record.producer_tool,
        "requested_by": record.requested_by,
        "actor": record.actor,
        "status": record.status,
    }
    for key, observed in expected_metadata.items():
        if reference.metadata.get(key) != observed:
            raise ValueError(f"canonical composition ref {key} drift: {reference.uri}")
    observed_digest = json_payload_hash(record.payload)
    if reference.metadata.get("payload_sha256") != observed_digest:
        raise ValueError(f"canonical composition ref payload drift: {reference.uri}")
    return observed_digest
