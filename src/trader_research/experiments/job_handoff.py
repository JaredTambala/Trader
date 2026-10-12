"""Join canonical experiment approval to one durable backtest admission.

The request artifact pins approved evidence and execution identities. Its
content-derived key makes concurrent preparation safe; the job's proposal-based
idempotency key prevents different execution pins from admitting a second job.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import re
from typing import Any

from trader_research.foundation import (
    ApplicationResult,
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    json_payload_hash,
    stable_research_id,
    success_result,
)
from trader_research.governance import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    EXPERIMENT_JOB_REQUEST,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    ExperimentProtocol,
    ExperimentProtocolProposal,
    ExperimentProtocolStatus,
    QUANT_RESEARCH_SUPERVISOR_OWNER,
    ResearchJob,
    ResearchJobLifecycleService,
    ResearchJobStore,
    ResearchOperationKind,
    apply_experiment_protocol_approvals,
    revalidate_experiment_protocol_inputs,
)
from trader_research.governance.handoffs import ArtifactReportRef


RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB = "research_submit_approved_experiment_job"
_ALLOWED_EXECUTION_ACTORS = frozenset(
    {"workflow_executor", QUANT_RESEARCH_SUPERVISOR_OWNER}
)
_PAYLOAD_DIGEST = re.compile(r"[0-9a-f]{64}")
_REQUEST_FIELDS = frozenset(
    {
        "artifact_type",
        "request_id",
        "proposal_ref",
        "approved_protocol_ref",
        "input_refs",
        "requested_by",
        "actor",
        "code_identity",
        "environment_identity",
        "operation_kind",
        "status",
    }
)


@dataclass(frozen=True)
class ExperimentJobRequest:
    """Source-free, content-addressed preparation for a backtest job.

    Attributes:
        request_id: Digest-derived identity of the complete prepared request.
        proposal_ref: Exact specialist proposal and payload hash.
        approved_protocol_ref: Exact approved protocol and payload hash.
        input_refs: Digest-pinned canonical implementation and Data evidence.
        requested_by: Workflow requester retained from the proposal.
        actor: Trusted composition's execution actor.
        code_identity: Checkout or executable build selected for the job.
        environment_identity: Execution environment selected for the job.
        operation_kind: Backtest; other producer types require their own handoff.
        status: Protocol approval state, not a claim that job admission succeeded.
    """

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
        """Reject malformed, unpinned, or identity-conflicting persisted values."""
        for label in (
            "request_id",
            "requested_by",
            "actor",
            "code_identity",
            "environment_identity",
        ):
            value = getattr(self, label)
            if _required_text(value, label) != value:
                raise ValueError(f"{label} must be normalized")
        if self.actor not in _ALLOWED_EXECUTION_ACTORS:
            raise ValueError("actor is not authorized to submit approved experiments")
        if self.status != "approved":
            raise ValueError("experiment job requests must be approved")
        if self.operation_kind is not ResearchOperationKind.BACKTEST:
            raise ValueError("experiment job requests support backtest only")
        _validate_ref(self.proposal_ref, EXPERIMENT_PROTOCOL_PROPOSAL)
        _validate_ref(self.approved_protocol_ref, EXPERIMENT_PROTOCOL)
        if not self.input_refs:
            raise ValueError("approved experiment input refs are required")
        if len({item.uri for item in self.input_refs}) != len(self.input_refs):
            raise ValueError("approved experiment input refs must be unique")
        for reference in self.input_refs:
            _validate_ref(reference, reference.artifact_type)
        if self.request_id != _request_id(self.to_dict()):
            raise ValueError("experiment job request identity conflicts")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the bounded request without expanding its evidence payloads."""
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
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentJobRequest:
        """Parse a closed persisted request and recompute its immutable identity.

        Args:
            payload: Complete JSON-compatible request record.

        Returns:
            Validated typed request.

        Raises:
            ValueError: If a field is unknown, missing, malformed, or unpinned.
        """
        if set(payload) != _REQUEST_FIELDS:
            raise ValueError("experiment job request fields are missing or unknown")
        if payload["artifact_type"] != EXPERIMENT_JOB_REQUEST:
            raise ValueError("experiment job request artifact_type is invalid")
        input_refs = payload["input_refs"]
        if not isinstance(input_refs, (list, tuple)):
            raise ValueError("input_refs must be a sequence of references")
        return cls(
            request_id=_required_text(payload["request_id"], "request_id"),
            proposal_ref=ArtifactReportRef.from_dict(
                _mapping(payload["proposal_ref"], "proposal_ref")
            ),
            approved_protocol_ref=ArtifactReportRef.from_dict(
                _mapping(payload["approved_protocol_ref"], "approved_protocol_ref")
            ),
            input_refs=tuple(
                ArtifactReportRef.from_dict(_mapping(item, "input_ref"))
                for item in input_refs
            ),
            requested_by=_required_text(payload["requested_by"], "requested_by"),
            actor=_required_text(payload["actor"], "actor"),
            code_identity=_required_text(payload["code_identity"], "code_identity"),
            environment_identity=_required_text(
                payload["environment_identity"], "environment_identity"
            ),
            operation_kind=ResearchOperationKind(payload["operation_kind"]),
            status=_required_text(payload["status"], "status"),
        )


def submit_approved_experiment_job(
    *,
    proposal_ref: ArtifactReportRef,
    approved_protocol_ref: ArtifactReportRef,
    requested_by: str,
    actor: str,
    code_identity: str,
    environment_identity: str,
    artifact_store: ResearchArtifactStore | None,
    job_store: ResearchJobStore | None,
) -> ApplicationResult:
    """Validate canonical approval and admit one proposal's durable backtest.

    Args:
        proposal_ref: Canonical proposal reference with an expected payload hash.
        approved_protocol_ref: Canonical approved protocol reference and hash.
        requested_by: Must match the requester retained by the proposal.
        actor: Trusted executor or Supervisor identity supplied by composition.
        code_identity: Immutable checkout/build pin supplied by composition.
        environment_identity: Immutable runtime environment pin.
        artifact_store: Canonical artifact read/write port.
        job_store: Durable job port enforcing atomic idempotent admission.

    Returns:
        Bounded request and current job projection on success. Exact replay
        returns the existing job, including its terminal state, without retrying
        execution. Conflicting pins fail closed. If admission fails after request
        preparation, the failure retains the request ref for reconciliation.
    """
    command = RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB
    if artifact_store is None or job_store is None:
        return error_result(
            command=command,
            code="research_job_store_required",
            message="Artifact and ResearchJob stores are required.",
        )
    try:
        requester = _required_text(requested_by, "requested_by")
        execution_actor = _required_text(actor, "actor")
        code_pin = _required_text(code_identity, "code_identity")
        environment_pin = _required_text(environment_identity, "environment_identity")
        if execution_actor not in _ALLOWED_EXECUTION_ACTORS:
            raise ValueError("actor is not authorized to submit approved experiments")
        proposal_record = _load_pinned_record(
            proposal_ref, EXPERIMENT_PROTOCOL_PROPOSAL, artifact_store
        )
        protocol_record = _load_pinned_record(
            approved_protocol_ref, EXPERIMENT_PROTOCOL, artifact_store
        )
        proposal = ExperimentProtocolProposal.from_dict(proposal_record.payload)
        protocol = ExperimentProtocol.from_dict(protocol_record.payload)
        if (
            proposal.proposal_id != proposal_record.artifact_id
            or protocol.protocol_id != protocol_record.artifact_id
        ):
            raise ValueError("canonical proposal or protocol payload identity drifted")
        if requester != proposal.requested_by:
            raise ValueError("experiment requester does not match the proposal")
        if protocol.status is not ExperimentProtocolStatus.APPROVED:
            raise ValueError("approved protocol must have approved status")
        expected = apply_experiment_protocol_approvals(proposal, protocol.approvals)
        if expected.to_dict() != dict(protocol_record.payload):
            raise ValueError("approved protocol does not match the proposal")
        if protocol.optimization is not None:
            raise ValueError("optimization protocols require an optimization handoff")
        revalidate_experiment_protocol_inputs(proposal, artifact_store=artifact_store)
        request = _build_request(
            proposal,
            proposal_record,
            protocol_record,
            requester,
            execution_actor,
            code_pin,
            environment_pin,
        )
        request_record = _save_request(artifact_store, request)
        proposal_key = {"proposal_id": proposal.proposal_id}
        job = ResearchJob(
            job_id=stable_research_id("research_job", proposal_key),
            operation_kind=request.operation_kind,
            request_ref=request_record.uri,
            request_digest=json_payload_hash(request.to_dict()),
            idempotency_key=stable_research_id(
                "approved_experiment_submission", proposal_key
            ),
            requested_by=request.requested_by,
            actor=request.actor,
            code_identity=request.code_identity,
            environment_identity=request.environment_identity,
        )
        result = ResearchJobLifecycleService(job_store).submit(job)
    except (ValueError, TypeError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=command, code="approved_experiment_job_failed", message=str(exc)
        )
    artifacts = {"experiment_job_request": request_record.reference().to_dict()}
    if not result.ok:
        return replace(
            result,
            operation=command,
            data={"experiment_job_request": request.to_dict()},
            artifacts=artifacts,
        )
    return success_result(
        command=command,
        data={
            "experiment_job_request": request.to_dict(),
            "research_job": result.data["research_job"],
        },
        artifacts=artifacts,
    )


def _build_request(
    proposal: ExperimentProtocolProposal,
    proposal_record: ResearchArtifactRecord,
    protocol_record: ResearchArtifactRecord,
    requester: str,
    actor: str,
    code_pin: str,
    environment_pin: str,
) -> ExperimentJobRequest:
    proposal_reference = _report_ref(proposal_record)
    protocol_reference = _report_ref(protocol_record)
    seed = {
        "proposal_ref": proposal_reference.to_dict(),
        "approved_protocol_ref": protocol_reference.to_dict(),
        "input_refs": [item.to_dict() for item in proposal.input_refs],
        "requested_by": requester,
        "actor": actor,
        "code_identity": code_pin,
        "environment_identity": environment_pin,
        "operation_kind": ResearchOperationKind.BACKTEST.value,
    }
    return ExperimentJobRequest(
        request_id=_request_id(seed),
        proposal_ref=proposal_reference,
        approved_protocol_ref=protocol_reference,
        input_refs=proposal.input_refs,
        requested_by=requester,
        actor=actor,
        code_identity=code_pin,
        environment_identity=environment_pin,
    )


def _save_request(
    store: ResearchArtifactStore, request: ExperimentJobRequest
) -> ResearchArtifactRecord:
    payload = request.to_dict()
    digest = json_payload_hash(payload)
    try:
        existing = store.load_artifact_record(
            EXPERIMENT_JOB_REQUEST, request.request_id
        )
    except ResearchArtifactNotFound:
        existing = None
    if existing is not None:
        if (
            dict(existing.payload) != payload
            or existing.domain_owner
            != DOMAIN_OWNER_BY_ARTIFACT_TYPE[EXPERIMENT_JOB_REQUEST]
            or existing.producer_tool != RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB
            or existing.status != request.status
            or existing.source_hash != digest
        ):
            raise ValueError("experiment job request identity conflicts")
        return existing
    return store.save_artifact(
        artifact_type=EXPERIMENT_JOB_REQUEST,
        artifact_id=request.request_id,
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[EXPERIMENT_JOB_REQUEST],
        producer_tool=RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB,
        payload=payload,
        requested_by=request.requested_by,
        actor=request.actor,
        status=request.status,
        source_hash=digest,
    )


def _load_pinned_record(
    reference: ArtifactReportRef, expected_type: str, store: ResearchArtifactStore
) -> ResearchArtifactRecord:
    _validate_ref(reference, expected_type)
    record = store.load_artifact_record(reference.artifact_type, reference.artifact_id)
    if record.uri != reference.uri or record.domain_owner != reference.domain_owner:
        raise ValueError("canonical reference identity or authority drifted")
    if json_payload_hash(record.payload) != reference.metadata["payload_sha256"]:
        raise ValueError(f"canonical payload drifted: {reference.uri}")
    return record


def _validate_ref(reference: ArtifactReportRef, expected_type: str) -> None:
    if (
        not isinstance(reference, ArtifactReportRef)
        or reference.artifact_type != expected_type
    ):
        raise ValueError(f"reference must point to {expected_type}")
    digest = reference.metadata.get("payload_sha256")
    if not isinstance(digest, str) or _PAYLOAD_DIGEST.fullmatch(digest) is None:
        raise ValueError("approved experiment refs must pin payload hashes")


def _report_ref(record: ResearchArtifactRecord) -> ArtifactReportRef:
    return ArtifactReportRef(
        artifact_id=record.artifact_id,
        artifact_type=record.artifact_type,
        domain_owner=record.domain_owner,
        uri=record.uri,
        metadata={"payload_sha256": json_payload_hash(record.payload)},
    )


def _request_id(payload: Mapping[str, Any]) -> str:
    seed = {
        key: value
        for key, value in payload.items()
        if key not in {"artifact_type", "request_id", "status"}
    }
    return stable_research_id(EXPERIMENT_JOB_REQUEST, seed)


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


__all__ = [
    "ExperimentJobRequest",
    "RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB",
    "submit_approved_experiment_job",
]
