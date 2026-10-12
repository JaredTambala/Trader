"""Approval-to-job handoff contracts for deterministic experiment execution.

Subject: The research-owned approved experiment request and ResearchJob admission.
Level: In-process service contract over in-memory canonical and job stores.
Collaborators: Existing proposal/approval contracts and the durable job service.
Guarantees: Only an exact approved protocol can produce one idempotent job request.
Non-goals: MCP transport, worker execution, backtest results, model acceptance, or
Postgres durability.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from trader_research.foundation import (
    EXPERIMENTS_DOMAIN_OWNER,
    InMemoryResearchArtifactStore,
    ResearchArtifactRecord,
    json_payload_hash,
)
from trader_research.experiments import submit_approved_experiment_job
from trader_research.governance import (
    EXPERIMENT_JOB_REQUEST,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    ExperimentProtocolProposal,
    ApprovalStatus,
    ResearchJob,
    ResearchJobStatus,
    apply_experiment_protocol_approvals,
    create_experiment_protocol_proposal,
)
from trader_research.governance.handoffs import ArtifactReportRef
from trader_research.infrastructure.postgres.job_store import (
    ResearchJobConflict,
    ResearchJobNotFound,
    ResearchJobTransitionError,
)

from tests.trader_research.governance.test_experiment_protocol_design import (
    _prepared_design,
)


@dataclass
class _MemoryJobStore:
    """Minimal durable-job port with immutable admission semantics."""

    jobs: dict[str, ResearchJob]

    def __init__(self) -> None:
        self.jobs = {}

    def admit(self, job: ResearchJob) -> ResearchJob:
        existing = next(
            (
                item
                for item in self.jobs.values()
                if item.idempotency_key == job.idempotency_key
            ),
            None,
        )
        if existing is not None:
            for field in (
                "operation_kind",
                "request_ref",
                "request_digest",
                "idempotency_key",
                "requested_by",
                "actor",
                "code_identity",
                "environment_identity",
            ):
                if getattr(existing, field) != getattr(job, field):
                    raise ResearchJobConflict("research job identity conflicts")
            return existing
        self.jobs[job.job_id] = job
        return job

    def load(self, job_id: str) -> ResearchJob:
        try:
            return self.jobs[job_id]
        except KeyError as exc:
            raise ResearchJobNotFound(job_id) from exc

    def save(
        self,
        job: ResearchJob,
        *,
        expected_status: ResearchJobStatus | None = None,
    ) -> ResearchJob:
        current = self.load(job.job_id)
        if expected_status is not None and current.status is not expected_status:
            raise ResearchJobTransitionError("status changed")
        self.jobs[job.job_id] = job
        return job


def _approved_inputs() -> tuple[
    InMemoryResearchArtifactStore,
    ArtifactReportRef,
    ArtifactReportRef,
]:
    """Build one canonical approved proposal and protocol fixture."""
    store, objective, design = _prepared_design()
    proposal_result = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="handoff-task",
        requested_by="workflow-1",
        actor="Experiment Design Agent",
        artifact_store=store,
    )
    assert proposal_result.ok is True
    proposal = proposal_result.data["experiment_protocol_proposal"]
    parsed = ExperimentProtocolProposal.from_dict(proposal)
    requested = parsed.protocol.approvals[0]
    decision = replace(
        requested,
        status=ApprovalStatus.APPROVED,
        decided_by=requested.requested_from,
        rationale="Approved for the bounded fixture.",
    )
    approved = apply_experiment_protocol_approvals(parsed, (decision,))
    store.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL,
        artifact_id=approved.protocol_id,
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="research_register_experiment_workflow",
        payload=approved.to_dict(),
        requested_by=approved.requested_by,
        actor="workflow_executor",
        status=approved.status.value,
    )
    proposal_record = store.load_artifact_record(
        EXPERIMENT_PROTOCOL_PROPOSAL,
        parsed.proposal_id,
    )
    protocol_record = store.load_artifact_record(
        EXPERIMENT_PROTOCOL,
        approved.protocol_id,
    )
    return store, _pinned_ref(proposal_record), _pinned_ref(protocol_record)


def test_approved_handoff_persists_one_job_and_replays_exactly() -> None:
    """An exact approved handoff creates one immutable request and one job."""
    artifact_store, proposal_ref, approved_protocol_ref = _approved_inputs()
    jobs = _MemoryJobStore()
    kwargs = {
        "proposal_ref": proposal_ref,
        "approved_protocol_ref": approved_protocol_ref,
        "requested_by": "workflow-1",
        "actor": "workflow_executor",
        "code_identity": "git:approved-candidate",
        "environment_identity": "env:qualification",
        "artifact_store": artifact_store,
        "job_store": jobs,
    }

    first = submit_approved_experiment_job(**kwargs)
    replay = submit_approved_experiment_job(**kwargs)

    assert first.ok is True
    assert replay.ok is True
    assert first.data == replay.data
    assert len(jobs.jobs) == 1
    assert len(artifact_store.list_artifacts(artifact_type=EXPERIMENT_JOB_REQUEST)) == 1


def test_handoff_rejects_unauthorized_actor_before_job_admission() -> None:
    """A caller outside the execution authority cannot submit the approved protocol."""
    artifact_store, proposal_ref, approved_protocol_ref = _approved_inputs()
    result = submit_approved_experiment_job(
        proposal_ref=proposal_ref,
        approved_protocol_ref=approved_protocol_ref,
        requested_by="workflow-1",
        actor="Experiment Design Agent",
        code_identity="git:approved-candidate",
        environment_identity="env:qualification",
        artifact_store=artifact_store,
        job_store=_MemoryJobStore(),
    )

    assert result.ok is False
    assert "not authorized" in result.errors[0]["message"]


def test_handoff_rejects_missing_approval() -> None:
    """A proposed protocol cannot cross the execution boundary."""
    artifact_store, proposal_ref, approved_protocol_ref = _approved_inputs()
    proposed_record = artifact_store.load_artifact_record(
        EXPERIMENT_PROTOCOL,
        approved_protocol_ref.artifact_id,
    )
    proposed = dict(proposed_record.payload)
    proposed["status"] = "proposed"
    artifact_store.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL,
        artifact_id=approved_protocol_ref.artifact_id,
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="test-proposed-protocol",
        payload=proposed,
        status="proposed",
    )
    proposed_ref = _pinned_ref(
        artifact_store.load_artifact_record(
            EXPERIMENT_PROTOCOL,
            approved_protocol_ref.artifact_id,
        )
    )
    result = submit_approved_experiment_job(
        proposal_ref=proposal_ref,
        approved_protocol_ref=proposed_ref,
        requested_by="workflow-1",
        actor="workflow_executor",
        code_identity="git:approved-candidate",
        environment_identity="env:qualification",
        artifact_store=artifact_store,
        job_store=_MemoryJobStore(),
    )

    assert result.ok is False
    assert "approved status" in result.errors[0]["message"]


def test_handoff_rejects_rewritten_proposal_identity() -> None:
    """Changing canonical evidence under an existing key fails closed."""
    artifact_store, proposal_ref, approved_protocol_ref = _approved_inputs()
    proposal_id = proposal_ref.artifact_id
    original = dict(
        artifact_store.load_artifact(EXPERIMENT_PROTOCOL_PROPOSAL, proposal_id)
    )
    original["task_id"] = "rewritten-task"
    artifact_store.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL_PROPOSAL,
        artifact_id=proposal_id,
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="test-rewrite",
        payload=original,
        requested_by="workflow-1",
        actor="test",
        status="proposed",
    )

    result = submit_approved_experiment_job(
        proposal_ref=proposal_ref,
        approved_protocol_ref=approved_protocol_ref,
        requested_by="workflow-1",
        actor="workflow_executor",
        code_identity="git:approved-candidate",
        environment_identity="env:qualification",
        artifact_store=artifact_store,
        job_store=_MemoryJobStore(),
    )

    assert result.ok is False
    assert "canonical payload drifted" in result.errors[0]["message"]


def test_handoff_rejects_approval_payload_drift() -> None:
    """A supplied approval payload must match the requested decision exactly."""
    artifact_store, proposal_ref, approved_protocol_ref = _approved_inputs()
    drifted = dict(
        artifact_store.load_artifact(
            EXPERIMENT_PROTOCOL,
            approved_protocol_ref.artifact_id,
        )
    )
    approvals = [dict(item) for item in drifted["approvals"]]
    approvals[0]["rationale"] = "Different decision record."
    drifted["approvals"] = approvals
    artifact_store.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL,
        artifact_id=approved_protocol_ref.artifact_id,
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="test-drifted-protocol",
        payload=drifted,
        status="approved",
    )
    result = submit_approved_experiment_job(
        proposal_ref=proposal_ref,
        approved_protocol_ref=approved_protocol_ref,
        requested_by="workflow-1",
        actor="workflow_executor",
        code_identity="git:approved-candidate",
        environment_identity="env:qualification",
        artifact_store=artifact_store,
        job_store=_MemoryJobStore(),
    )

    assert result.ok is False
    assert "canonical payload drifted" in result.errors[0]["message"]


def test_handoff_rejects_execution_pin_conflict_after_admission() -> None:
    """A changed code pin cannot create a second attempt for one proposal."""
    artifact_store, proposal_ref, approved_protocol_ref = _approved_inputs()
    common = {
        "proposal_ref": proposal_ref,
        "approved_protocol_ref": approved_protocol_ref,
        "requested_by": "workflow-1",
        "actor": "workflow_executor",
        "environment_identity": "env:qualification",
        "artifact_store": artifact_store,
        "job_store": _MemoryJobStore(),
    }
    first = submit_approved_experiment_job(
        **common,
        code_identity="git:approved-candidate",
    )
    second = submit_approved_experiment_job(
        **common,
        code_identity="git:changed-candidate",
    )

    assert first.ok is True
    assert second.ok is False
    assert "identity conflicts" in second.errors[0]["message"]


def test_handoff_replays_terminal_job_without_creating_a_retry() -> None:
    """A terminal repeat returns the retained projection and no new job."""
    artifact_store, proposal_ref, approved_protocol_ref = _approved_inputs()
    jobs = _MemoryJobStore()
    kwargs = {
        "proposal_ref": proposal_ref,
        "approved_protocol_ref": approved_protocol_ref,
        "requested_by": "workflow-1",
        "actor": "workflow_executor",
        "code_identity": "git:approved-candidate",
        "environment_identity": "env:qualification",
        "artifact_store": artifact_store,
        "job_store": jobs,
    }
    first = submit_approved_experiment_job(**kwargs)
    job_id = first.data["research_job"]["job_id"]
    jobs.jobs[job_id] = replace(
        jobs.jobs[job_id],
        status=ResearchJobStatus.SUCCEEDED,
    )

    replay = submit_approved_experiment_job(**kwargs)

    assert replay.ok is True
    assert replay.data["research_job"]["status"] == "succeeded"
    assert len(jobs.jobs) == 1


def _pinned_ref(record: ResearchArtifactRecord) -> ArtifactReportRef:
    """Build a digest-pinned test reference from a canonical record."""
    return ArtifactReportRef(
        artifact_id=record.artifact_id,
        artifact_type=record.artifact_type,
        domain_owner=record.domain_owner,
        uri=record.uri,
        metadata={"payload_sha256": json_payload_hash(record.payload)},
    )
