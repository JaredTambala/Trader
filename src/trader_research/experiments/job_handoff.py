"""Turn an approved experiment proposal into one durable research job.

The handoff is the deterministic boundary between Experiment Design approval
and execution.  It persists a small, source-free request record containing
the exact proposal/protocol references and then admits one ``ResearchJob``.
Worker execution, evaluation, and paper admission remain separate boundaries.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from trader_research.foundation import (
    ApplicationResult,
    ResearchArtifactNotFound,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    json_payload_hash,
    load_artifact_ref,
    stable_research_id,
    success_result,
)
from trader_research.governance import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    EXPERIMENT_JOB_REQUEST,
    ExperimentProtocol,
    ExperimentProtocolProposal,
    ExperimentProtocolStatus,
    QUANT_RESEARCH_SUPERVISOR_OWNER,
    ResearchJob,
    ResearchJobLifecycleService,
    ResearchJobStore,
    ResearchOperationKind,
    apply_experiment_protocol_approvals,
)
from trader_research.governance.handoffs import ArtifactReportRef


RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB = "research_submit_approved_experiment_job"
_ALLOWED_EXECUTION_ACTORS = frozenset(
    {"workflow_executor", QUANT_RESEARCH_SUPERVISOR_OWNER}
)


@dataclass(frozen=True)
class ExperimentJobRequest:
    """Immutable, bounded request joining proposal approval to one job."""

    request_id: str
    proposal_ref: ArtifactReportRef
    approved_protocol_ref: ArtifactReportRef
    input_refs: tuple[ArtifactReportRef, ...]
    requested_by: str
    actor: str
    code_identity: str
    environment_identity: str
    operation_kind: ResearchOperationKind = ResearchOperationKind.BACKTEST
    status: str = "approved"

    artifact_type = EXPERIMENT_JOB_REQUEST

    def __post_init__(self) -> None:
        """Validate identity, approval state, and bounded canonical references."""
        for value, label in (
            (self.request_id, "request_id"),
            (self.requested_by, "requested_by"),
            (self.actor, "actor"),
            (self.code_identity, "code_identity"),
            (self.environment_identity, "environment_identity"),
        ):
            if not value.strip():
                raise ValueError(f"{label} is required")
        if self.status != "approved":
            raise ValueError("experiment job requests must be approved")
        if self.proposal_ref.artifact_type != EXPERIMENT_PROTOCOL_PROPOSAL:
            raise ValueError("proposal_ref must point to an experiment protocol proposal")
        if self.approved_protocol_ref.artifact_type != EXPERIMENT_PROTOCOL:
            raise ValueError("approved_protocol_ref must point to an experiment protocol")
        if not self.input_refs:
            raise ValueError("approved experiment input refs are required")
        refs = (*self.input_refs, self.proposal_ref, self.approved_protocol_ref)
        if any(not str(item.metadata.get("payload_sha256") or "") for item in refs):
            raise ValueError("approved experiment refs must pin payload hashes")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the source-free request record."""
        return {
            "artifact_type": self.artifact_type,
            "request_id": self.request_id,
            "proposal_ref": self.proposal_ref.to_dict(),
            "approved_protocol_ref": self.approved_protocol_ref.to_dict(),
            "input_refs": [item.to_dict() for item in self.input_refs],
            "requested_by": self.requested_by,
            "actor": self.actor,
            "code_identity": self.code_identity,
            "environment_identity": self.environment_identity,
            "operation_kind": self.operation_kind.value,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentJobRequest":
        """Parse and validate one persisted request."""
        if payload.get("artifact_type") != EXPERIMENT_JOB_REQUEST:
            raise ValueError("experiment job request artifact_type is invalid")
        return cls(
            request_id=str(payload.get("request_id") or ""),
            proposal_ref=ArtifactReportRef.from_dict(payload["proposal_ref"]),
            approved_protocol_ref=ArtifactReportRef.from_dict(
                payload["approved_protocol_ref"]
            ),
            input_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in payload.get("input_refs", ())
            ),
            requested_by=str(payload.get("requested_by") or ""),
            actor=str(payload.get("actor") or ""),
            code_identity=str(payload.get("code_identity") or ""),
            environment_identity=str(payload.get("environment_identity") or ""),
            operation_kind=ResearchOperationKind(str(payload.get("operation_kind"))),
            status=str(payload.get("status") or ""),
        )


def submit_approved_experiment_job(
    *,
    proposal_ref: str,
    approved_protocol: Mapping[str, Any],
    requested_by: str,
    actor: str,
    code_identity: str,
    environment_identity: str,
    artifact_store: ResearchArtifactStore | None,
    job_store: ResearchJobStore | None,
) -> ApplicationResult:
    """Persist an exact approval handoff and admit one durable backtest job."""
    command = RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB
    if artifact_store is None or job_store is None:
        return error_result(
            command=command,
            code="research_job_store_required",
            message="Artifact and ResearchJob stores are required.",
        )
    try:
        if actor not in _ALLOWED_EXECUTION_ACTORS:
            raise ValueError("actor is not authorized to submit approved experiments")
        proposal_payload = load_artifact_ref(
            artifact_store, EXPERIMENT_PROTOCOL_PROPOSAL, proposal_ref
        )
        proposal = ExperimentProtocolProposal.from_dict(proposal_payload)
        _validate_proposal_identity(proposal)
        protocol = ExperimentProtocol.from_dict(approved_protocol)
        if protocol.status is not ExperimentProtocolStatus.APPROVED:
            raise ValueError("approved_protocol must have approved status")
        expected = apply_experiment_protocol_approvals(proposal, protocol.approvals)
        if expected.to_dict() != protocol.to_dict():
            raise ValueError("approved protocol does not match the proposal")
        proposal_record = artifact_store.load_artifact_record(
            EXPERIMENT_PROTOCOL_PROPOSAL, proposal.proposal_id
        )
        protocol_record = artifact_store.load_artifact_record(
            EXPERIMENT_PROTOCOL, protocol.protocol_id
        )
        if protocol_record.payload != protocol.to_dict():
            raise ValueError("approved protocol canonical payload drifted")
        proposal_ref_value = _report_ref(proposal_record)
        protocol_ref_value = _report_ref(protocol_record)
        request_payload_seed = {
            "proposal_ref": proposal_ref_value.to_dict(),
            "approved_protocol_ref": protocol_ref_value.to_dict(),
            "input_refs": [item.to_dict() for item in proposal.input_refs],
            "requested_by": requested_by,
            "actor": actor,
            "code_identity": code_identity,
            "environment_identity": environment_identity,
            "operation_kind": ResearchOperationKind.BACKTEST.value,
        }
        request_id = stable_research_id("experiment_job_request", request_payload_seed)
        request = ExperimentJobRequest(
            request_id=request_id,
            proposal_ref=proposal_ref_value,
            approved_protocol_ref=protocol_ref_value,
            input_refs=proposal.input_refs,
            requested_by=requested_by,
            actor=actor,
            code_identity=code_identity,
            environment_identity=environment_identity,
        )
        payload = request.to_dict()
        try:
            existing = artifact_store.load_artifact_record(
                EXPERIMENT_JOB_REQUEST, request.request_id
            )
        except ResearchArtifactNotFound:
            existing = None
        if existing is not None and dict(existing.payload) != payload:
            raise ValueError("experiment job request identity conflicts")
        request_record = existing or artifact_store.save_artifact(
            artifact_type=EXPERIMENT_JOB_REQUEST,
            artifact_id=request.request_id,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[EXPERIMENT_JOB_REQUEST],
            producer_tool=command,
            payload=payload,
            requested_by=requested_by,
            actor=actor,
            status=request.status,
            source_hash=json_payload_hash(payload),
        )
        job = ResearchJob(
            job_id=stable_research_id(
                "research_job", {"request_id": request.request_id}
            ),
            operation_kind=request.operation_kind,
            request_ref=request_record.uri,
            request_digest=json_payload_hash(payload),
            idempotency_key=request.request_id,
            requested_by=requested_by,
            actor=actor,
            code_identity=code_identity,
            environment_identity=environment_identity,
        )
        result = ResearchJobLifecycleService(job_store).submit(job)
        if not result.ok:
            return result
    except (KeyError, ValueError, ResearchArtifactStoreError) as exc:
        return error_result(command=command, code="approved_experiment_job_failed", message=str(exc))
    return success_result(
        command=command,
        data={"experiment_job_request": payload, "research_job": result.data["research_job"]},
        artifacts={
            "experiment_job_request": request_record.reference().to_dict(),
        },
    )


__all__ = [
    "ExperimentJobRequest",
    "RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB",
    "submit_approved_experiment_job",
]


def _report_ref(record: Any) -> ArtifactReportRef:
    """Convert a canonical record to the research handoff reference shape."""
    return ArtifactReportRef(
        artifact_id=record.artifact_id,
        artifact_type=record.artifact_type,
        domain_owner=record.domain_owner,
        uri=record.uri,
        metadata={
            **dict(record.reference().metadata),
            "payload_sha256": json_payload_hash(record.payload),
        },
    )


def _validate_proposal_identity(proposal: ExperimentProtocolProposal) -> None:
    """Reject a rewritten proposal record that retains an old artifact key."""
    expected_id = stable_research_id(
        "experiment_protocol_proposal",
        {
            "task_id": proposal.task_id,
            "objective_digest": proposal.objective_digest,
            "design_digest": proposal.design_digest,
            "input_refs": [item.to_dict() for item in proposal.input_refs],
        },
    )
    if proposal.proposal_id != expected_id:
        raise ValueError("experiment protocol proposal identity drifted")
