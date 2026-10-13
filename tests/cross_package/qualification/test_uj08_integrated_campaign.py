"""Focused approved-job adapter and worker fault contracts.

Subject: Canonical approval rereads, request integrity, partial receipts,
worker cancellation, and uncertain lease handling.
Level: Offline cross-package contract.
Collaborators: Real approval/job values and worker, in-memory stores and injected
producer responses. No Postgres, MCP transport, or model invocation.
Guarantees: Request drift blocks execution and missing or uncertain producer
receipts remain explicit; queued cancellation suppresses execution.
Non-goals: Integrated journey qualification, durable recovery, independent
reviews, scientific validity, and model-backed behavior. The public Postgres
campaign owns integrated qualification.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import os
from typing import Any, cast

import psycopg
import pytest

from trader_console_api import (
    ApprovedExperimentBacktestExecutor,
    ResearchJobExecutionOutcome,
    ResearchJobProgressSink,
    ResearchJobWorker,
)
from trader_research.experiments import (
    submit_approved_experiment_job,
)
from trader_research.foundation import InMemoryResearchArtifactStore, json_payload_hash
from trader_research.governance import (
    BACKTEST_RUN,
    EXPERIMENT_DESIGN_AGENT_OWNER,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    create_experiment_protocol_proposal,
    ApprovalStatus,
    ArtifactReportRef,
    ExperimentProtocolProposal,
    ResearchJob,
    ResearchJobStatus,
    apply_experiment_protocol_approvals,
)
from trader_research.governance.orchestration import ResearchJobLifecycleService
from trader_research.foundation import EXPERIMENTS_DOMAIN_OWNER

from tests.trader_research.governance.test_experiment_protocol_design import (
    _prepared_design,
)


@pytest.fixture
def uj08_postgres_settings() -> dict[str, object]:
    """Return the explicitly provisioned UJ-08 disposable Postgres database.

    This campaign intentionally uses a separate profile from the historical
    guarded verification database: its schema is created and dropped by the
    test, while the database identity remains an explicit ``*_test`` target.
    """
    required = {
        "host": os.environ.get("UJ08_PG_HOST", "").strip(),
        "port": os.environ.get("UJ08_PG_PORT", "").strip(),
        "dbname": os.environ.get("UJ08_PG_DB", "").strip(),
        "user": os.environ.get("UJ08_PG_USER", "").strip(),
        "password": os.environ.get("UJ08_PG_PASSWORD", ""),
    }
    if not all(required.values()):
        pytest.skip("UJ08_PG_* disposable campaign settings are not configured")
    if not required["dbname"].endswith(("_test", "_testing")):
        raise pytest.UsageError("UJ08_PG_DB must be a disposable *_test database")
    settings = {**required, "port": int(str(required["port"]))}
    with psycopg.connect(**cast(Any, settings)) as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user, current_setting('TimeZone')"
        ).fetchone()
    if identity is None or identity[:2] != (settings["dbname"], settings["user"]):
        raise pytest.UsageError(
            "UJ08 Postgres database or role does not match its profile"
        )
    if str(identity[2]).upper() not in {"UTC", "ETC/UTC"}:
        raise pytest.UsageError(
            "UJ08 Postgres identity or timezone does not match its profile"
        )
    return settings


@dataclass
class _MemoryResearchJobStore:
    """Small lease-capable store preserving the worker's public contract."""

    job: ResearchJob
    lose_lease: bool = False

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int,
    ) -> ResearchJob | None:
        """Claim the single fixture job once."""
        del max_attempts
        if self.job.status is not ResearchJobStatus.QUEUED:
            return None
        self.job = replace(
            self.job,
            status=ResearchJobStatus.RUNNING,
            attempt=1,
            lease_id=f"{worker_id}:lease",
            lease_expires_at=datetime.now(UTC) + timedelta(seconds=lease_seconds),
        )
        return self.job

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_id: str,
        lease_seconds: int,
    ) -> bool:
        """Renew the fixture lease while the producer is active."""
        return (
            job_id == self.job.job_id
            and worker_id in (self.job.lease_id or "")
            and lease_id == self.job.lease_id
            and self.job.status is ResearchJobStatus.RUNNING
            and lease_seconds > 0
            and not self.lose_lease
        )

    def finish(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_id: str,
        status: ResearchJobStatus,
        produced_artifact_refs=(),
        warnings=(),
        blockers=(),
        retryable: bool = False,
    ) -> ResearchJob | None:
        """Retain one terminal worker receipt under the active lease."""
        if (
            job_id != self.job.job_id
            or worker_id not in (self.job.lease_id or "")
            or lease_id != self.job.lease_id
        ):
            return None
        self.job = replace(
            self.job,
            status=status,
            lease_id=None,
            lease_expires_at=None,
            produced_artifact_refs=tuple(produced_artifact_refs),
            warnings=tuple(warnings),
            blockers=tuple(blockers),
            retryable=retryable,
        )
        return self.job


class _DeterministicBacktestProducer:
    """Controlled producer fixture representing the canonical runner adapter."""

    def __init__(self, store: InMemoryResearchArtifactStore) -> None:
        self.store = store
        self.calls: list[tuple[str, str, str]] = []

    async def execute(
        self,
        request,
        protocol,
        *,
        run_id: str,
        progress: ResearchJobProgressSink,
    ) -> ResearchJobExecutionOutcome:
        """Persist one exact run receipt after a lease renewal."""
        self.calls.append((request.request_id, protocol.protocol_id, run_id))
        await progress(datetime(2026, 10, 12, 12, 0, tzinfo=UTC))
        payload = {
            "artifact_type": BACKTEST_RUN,
            "run_id": run_id,
            "experiment_id": protocol.protocol_id,
            "proposal_id": request.proposal_ref.artifact_id,
            "status": "passed",
            "deterministic": True,
        }
        record = self.store.save_artifact(
            artifact_type=BACKTEST_RUN,
            artifact_id=run_id,
            domain_owner=EXPERIMENTS_DOMAIN_OWNER,
            producer_tool="research_run_backtest_specification",
            payload=payload,
            status="passed",
            metadata={"revision": 1},
        )
        return ResearchJobExecutionOutcome(
            status="succeeded",
            produced_artifact_refs=(_pinned_ref(record),),
        )


class _NoReceiptProducer:
    """Producer fixture that completes without retaining its run receipt."""

    async def execute(
        self,
        request,
        protocol,
        *,
        run_id: str,
        progress: ResearchJobProgressSink,
    ) -> ResearchJobExecutionOutcome:
        """Return an invalid success so the adapter retains a partial blocker."""
        del request, protocol, run_id
        await progress(None)
        return ResearchJobExecutionOutcome(status="succeeded")


def test_uj08_adapter_rejects_request_digest_drift_before_producer() -> None:
    """A worker cannot execute when the durable request digest has changed."""
    artifacts, proposal_ref, protocol_ref = _approved_inputs()
    admission_store = _AdmissionStore()
    admission = submit_approved_experiment_job(
        proposal_ref=proposal_ref,
        approved_protocol_ref=protocol_ref,
        requested_by="workflow-uj08",
        actor="workflow_executor",
        code_identity="git:uj08-fixture",
        environment_identity="env:uj08-controlled",
        artifact_store=artifacts,
        job_store=admission_store,
    )
    assert admission.ok is True
    job = ResearchJob.from_dict(admission.data["research_job"])
    worker_store = _MemoryResearchJobStore(replace(job, request_digest="sha256:drift"))
    producer = _DeterministicBacktestProducer(artifacts)
    assert (
        asyncio.run(
            ResearchJobWorker(
                worker_store,
                ApprovedExperimentBacktestExecutor(artifacts, producer),
                worker_id="uj08-worker",
            ).run_once()
        )
        is True
    )
    assert worker_store.job.status is ResearchJobStatus.FAILED
    assert producer.calls == []
    assert worker_store.job.blockers[0].code == "worker_execution_failed"


def test_uj08_adapter_turns_missing_run_receipt_into_partial_outcome() -> None:
    """A producer cannot claim success without a canonical backtest artifact."""
    artifacts, proposal_ref, protocol_ref = _approved_inputs()
    admission_store = _AdmissionStore()
    admission = submit_approved_experiment_job(
        proposal_ref=proposal_ref,
        approved_protocol_ref=protocol_ref,
        requested_by="workflow-uj08",
        actor="workflow_executor",
        code_identity="git:uj08-fixture",
        environment_identity="env:uj08-controlled",
        artifact_store=artifacts,
        job_store=admission_store,
    )
    assert admission.ok is True
    worker_store = _MemoryResearchJobStore(
        ResearchJob.from_dict(admission.data["research_job"])
    )
    assert (
        asyncio.run(
            ResearchJobWorker(
                worker_store,
                ApprovedExperimentBacktestExecutor(artifacts, _NoReceiptProducer()),
                worker_id="uj08-worker",
            ).run_once()
        )
        is True
    )
    assert worker_store.job.status is ResearchJobStatus.PARTIAL
    assert worker_store.job.blockers[0].code == "backtest_run_receipt_missing"


def test_uj08_worker_retains_lost_lease_and_terminal_failure() -> None:
    """Worker loss becomes reconciliation-required and producer failure is terminal."""
    artifacts, proposal_ref, protocol_ref = _approved_inputs()
    admission = submit_approved_experiment_job(
        proposal_ref=proposal_ref,
        approved_protocol_ref=protocol_ref,
        requested_by="workflow-uj08",
        actor="workflow_executor",
        code_identity="git:uj08-fixture",
        environment_identity="env:uj08-controlled",
        artifact_store=artifacts,
        job_store=_AdmissionStore(),
    )
    assert admission.ok is True
    job = ResearchJob.from_dict(admission.data["research_job"])
    lost_store = _MemoryResearchJobStore(job, lose_lease=True)
    producer = _DeterministicBacktestProducer(artifacts)
    assert (
        asyncio.run(
            ResearchJobWorker(
                lost_store,
                ApprovedExperimentBacktestExecutor(artifacts, producer),
                worker_id="uj08-lost-worker",
            ).run_once()
        )
        is True
    )
    assert lost_store.job.status is ResearchJobStatus.RECONCILIATION_REQUIRED
    assert lost_store.job.blockers[0].code == "ambiguous_producer_outcome"
    assert producer.calls == [
        (
            job.request_ref.rsplit("/", 1)[-1],
            protocol_ref.artifact_id,
            _deterministic_run_id(job),
        )
    ]

    class _TerminalFailureProducer:
        """Producer fixture that fails before retaining any child evidence."""

        async def execute(
            self,
            request,
            protocol,
            *,
            run_id: str,
            progress: ResearchJobProgressSink,
        ) -> ResearchJobExecutionOutcome:
            """Raise one bounded terminal failure."""
            del request, protocol, run_id, progress
            raise RuntimeError("runner rejected the replay fixture")

    failure_store = _MemoryResearchJobStore(job)
    assert (
        asyncio.run(
            ResearchJobWorker(
                failure_store,
                ApprovedExperimentBacktestExecutor(
                    artifacts, _TerminalFailureProducer()
                ),
                worker_id="uj08-failed-worker",
            ).run_once()
        )
        is True
    )
    assert failure_store.job.status is ResearchJobStatus.FAILED
    assert failure_store.job.blockers[0].code == "worker_execution_failed"


def test_uj08_cancel_is_terminal_and_does_not_start_the_producer() -> None:
    """Cancellation is durable, idempotent, and prevents later worker claims."""
    artifacts, proposal_ref, protocol_ref = _approved_inputs()
    admission_store = _AdmissionStore()
    admission = submit_approved_experiment_job(
        proposal_ref=proposal_ref,
        approved_protocol_ref=protocol_ref,
        requested_by="workflow-uj08",
        actor="workflow_executor",
        code_identity="git:uj08-fixture",
        environment_identity="env:uj08-controlled",
        artifact_store=artifacts,
        job_store=admission_store,
    )
    assert admission.ok is True
    job = ResearchJob.from_dict(admission.data["research_job"])
    cancelled = ResearchJobLifecycleService(admission_store).cancel(
        job.job_id,
        actor=job.actor,
        reason="operator stopped the qualification before execution",
    )
    assert cancelled.ok is True
    assert cancelled.data["research_job"]["status"] == ResearchJobStatus.CANCELLED.value
    worker_store = _MemoryResearchJobStore(
        ResearchJob.from_dict(cancelled.data["research_job"])
    )
    producer = _DeterministicBacktestProducer(artifacts)
    assert (
        asyncio.run(
            ResearchJobWorker(
                worker_store,
                ApprovedExperimentBacktestExecutor(artifacts, producer),
                worker_id="uj08-cancelled-worker",
            ).run_once()
        )
        is False
    )
    assert producer.calls == []


class _AdmissionStore:
    """Admission-capable extension used before the worker claims the fixture."""

    def __init__(self) -> None:
        self.job: ResearchJob | None = None

    def admit(self, job: ResearchJob) -> ResearchJob:
        """Retain the one admitted job for the qualification."""
        if self.job is None:
            self.job = job
            return job
        if self.job.to_dict() != job.to_dict():
            raise ValueError("admission request drifted")
        return self.job

    def load(self, job_id: str) -> ResearchJob:
        """Return the admitted job projection."""
        if self.job is None or self.job.job_id != job_id:
            raise ValueError("unknown fixture job")
        return self.job

    def save(self, job: ResearchJob, *, expected_status=None) -> ResearchJob:
        """Apply a lifecycle update for the admission protocol."""
        del expected_status
        self.job = job
        return job


def _approved_inputs() -> tuple[
    InMemoryResearchArtifactStore, ArtifactReportRef, ArtifactReportRef
]:
    """Build one exact approved proposal and protocol from canonical fixtures."""

    artifacts, objective, design = _prepared_design()
    result = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="uj08-integrated",
        requested_by="workflow-uj08",
        actor=EXPERIMENT_DESIGN_AGENT_OWNER,
        artifact_store=artifacts,
    )
    assert result.ok is True
    proposal = ExperimentProtocolProposal.from_dict(
        result.data["experiment_protocol_proposal"]
    )
    requested = proposal.protocol.approvals[0]
    approved = apply_experiment_protocol_approvals(
        proposal,
        (
            replace(
                requested,
                status=ApprovalStatus.APPROVED,
                decided_by=requested.requested_from,
                rationale="Approved fixture.",
            ),
        ),
    )
    artifacts.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL,
        artifact_id=approved.protocol_id,
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="research_register_experiment_workflow",
        payload=approved.to_dict(),
        status="approved",
    )
    proposal_record = artifacts.load_artifact_record(
        EXPERIMENT_PROTOCOL_PROPOSAL, proposal.proposal_id
    )
    protocol_record = artifacts.load_artifact_record(
        EXPERIMENT_PROTOCOL, approved.protocol_id
    )
    artifacts.save_artifact(
        artifact_type="approval_request",
        artifact_id=proposal.proposal_id,
        domain_owner="Orchestration",
        producer_tool="research_register_experiment_workflow",
        payload={
            "artifact_type": "approval_request",
            "proposal_id": proposal.proposal_id,
            "status": "approved",
        },
        status="approved",
    )
    return artifacts, _pinned_ref(proposal_record), _pinned_ref(protocol_record)


def _pinned_ref(record) -> ArtifactReportRef:
    """Build an exact digest-pinned research reference."""
    return ArtifactReportRef(
        artifact_id=record.artifact_id,
        artifact_type=record.artifact_type,
        domain_owner=record.domain_owner,
        uri=record.uri,
        metadata={"payload_sha256": json_payload_hash(record.payload)},
    )


def _deterministic_run_id(job: ResearchJob) -> str:
    """Use the same deterministic run identity as the worker."""
    from trader_console_api.worker import deterministic_research_run_id

    return deterministic_research_run_id(job.job_id, job.request_digest)
