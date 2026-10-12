"""Retained UJ-08 qualification from approved protocol to terminal evidence.

Subject: Approved Experiment Design → public job-admission contract → worker
execution → concurrent independent review → exact terminal evidence join.
Level: Deterministic cross-package qualification with a guarded Postgres
campaign for the concrete ``BacktestRunnerResearchProducer``.
Collaborators: Research proposal/approval and job contracts, the Console
ResearchJobWorker, the canonical Trader runner, Postgres artifact/event stores,
and the exact evidence-join verifier. No model, broker, hidden reasoning, or
raw payload persistence.
Guarantees: Only an approved and freshly reread protocol can reach the producer;
one deterministic run receipt is retained; Evaluation and Robustness retain
their own ownership and may complete concurrently; a fresh process can reopen
the redacted terminal join.
Non-goals: Scientific validity, model-backed acceptance, paper authorization,
or a claim that missing independent evidence is positive evidence.
Cohesion rationale: The offline denial/partial cases and the guarded Postgres
campaign all protect the same approved-protocol-to-terminal-evidence contract;
keeping them together makes the retained report and its exact lineage fields
reviewable as one qualification boundary.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, cast
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg import sql
import pytest

from trader_console_api import (
    ApprovedExperimentBacktestExecutor,
    ResearchJobExecutionOutcome,
    ResearchJobProgressSink,
    ResearchJobWorker,
    BacktestRunnerResearchProducer,
)
from trader_research.experiments import (
    register_risk_manager_implementation,
    register_strategy_implementation,
    submit_approved_experiment_job,
    validate_risk_manager_implementation,
    validate_strategy_implementation,
)
from trader_research.foundation import InMemoryResearchArtifactStore, json_payload_hash
from trader_research.governance import (
    BACKTEST_RUN,
    CostAssumption,
    DataRequirement,
    DatasetRole,
    EXPERIMENT_DESIGN_AGENT_OWNER,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    ExperimentDesignRequest,
    InitialPortfolio,
    MaterialAssumption,
    ProtocolDataset,
    ProtocolRiskManager,
    ProtocolStrategy,
    ResearchObjective,
    ResearchObjectiveStatus,
    create_experiment_protocol_proposal,
    WORKFLOW_OUTCOME,
    ApprovalStatus,
    ArtifactReportRef,
    ExperimentProtocolProposal,
    ResearchJob,
    ResearchJobStatus,
    ResearchOperationKind,
    apply_experiment_protocol_approvals,
)
from trader_research.foundation import EXPERIMENTS_DOMAIN_OWNER
from trader_research.review import EvidenceJoinRef, EvidenceJoinStatus, qualify_evidence_join
from trader_research.infrastructure.postgres import PostgresResearchJobStore

from tests.trader_research.governance.test_experiment_protocol_design import _prepared_design
from tests.cross_package.qualification.support.realistic_optimization_fixture import (
    BASE_STRATEGY_PARAMETERS,
    RISK_PARAMETERS,
    RISK_PARAMETER_SCHEMA,
    RISK_SOURCE,
    STRATEGY_PARAMETER_SCHEMA,
    STRATEGY_SOURCE,
    build_backtest_config,
    build_realistic_optimization_fixture,
    data_evidence,
    seed_fixture,
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
        raise pytest.UsageError("UJ08 Postgres database or role does not match its profile")
    if str(identity[2]).upper() not in {"UTC", "ETC/UTC"}:
        raise pytest.UsageError("UJ08 Postgres identity or timezone does not match its profile")
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


def test_uj08_integrated_campaign_retains_terminal_join_and_fresh_process(
    tmp_path: Path,
) -> None:
    """Qualify approval, admission, worker execution, independent reviews, and join."""
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
    assert admission.ok is True, admission.errors
    job = ResearchJob.from_dict(admission.data["research_job"])
    producer = _DeterministicBacktestProducer(artifacts)
    job_store = _MemoryResearchJobStore(job)
    worker = ResearchJobWorker(
        job_store,
        ApprovedExperimentBacktestExecutor(artifacts, producer),
        worker_id="uj08-worker",
    )

    assert asyncio.run(worker.run_once()) is True
    assert job_store.job.status is ResearchJobStatus.SUCCEEDED
    assert len(producer.calls) == 1
    assert producer.calls[0][2] == _deterministic_run_id(job)

    protocol = artifacts.load_artifact_record(EXPERIMENT_PROTOCOL, protocol_ref.artifact_id)
    proposal = artifacts.load_artifact_record(EXPERIMENT_PROTOCOL_PROPOSAL, proposal_ref.artifact_id)
    lineage = {
        "experiment_id": protocol.artifact_id,
        "proposal_id": proposal.artifact_id,
        "scope_id": "manifest_design",
        "strategy_version_id": "strategy_v1",
        "run_id": producer.calls[0][2],
    }
    review_records = asyncio.run(_save_independent_reviews(artifacts, lineage))
    run_record = artifacts.load_artifact_record(BACKTEST_RUN, producer.calls[0][2])
    joined = qualify_evidence_join(
        experiment_id=protocol.artifact_id,
        proposal_id=proposal.artifact_id,
        scope_id="manifest_design",
        strategy_version_id="strategy_v1",
        run_id=producer.calls[0][2],
        evidence_revision=1,
        records=(
            _join_ref("proposal", proposal, lineage),
            _join_ref("approval", artifacts.load_artifact_record("approval_request", proposal.artifact_id), lineage),
            _join_ref("scope", artifacts.load_artifact_record("dataset_manifest", "manifest_design"), lineage),
            _join_ref("strategy", artifacts.load_artifact_record("implementation_version", "strategy_v1"), lineage),
            _join_ref("run", run_record, lineage),
            _join_ref("evaluation", review_records[0], lineage),
            _join_ref("robustness", review_records[1], lineage, status=EvidenceJoinStatus.NEGATIVE),
            _join_ref(
                "decision",
                artifacts.save_artifact(
                    artifact_type=WORKFLOW_OUTCOME,
                    artifact_id="uj08-terminal-decision-1",
                    domain_owner="Orchestration",
                    producer_tool="research_record_workflow_outcome",
                    payload={"artifact_type": WORKFLOW_OUTCOME, **lineage, "status": "completed"},
                    status="completed",
                    metadata={"revision": 1},
                ),
                lineage,
            ),
        ),
    )
    assert joined.verdict.value == "partial"
    assert joined.terminal_summary["robustness_status"] == "fail"

    report = {
        "fixture_id": "uj08-integrated-agent-directed-experiment-v1",
        "contract": "ApprovedExperimentBacktestExecutor/ResearchJobWorker/EvidenceJoinResult",
        "contract_version": "1",
        "evidence_revision": 1,
        "command": "uv run pytest tests/cross_package/qualification/test_uj08_integrated_campaign.py -q",
        "deterministic_evidence": joined.to_dict(),
        "model_gate": {"status": "not_claimed", "reason": "controlled third-party model gate is separate"},
    }
    report_path = tmp_path / "uj08-integrated-verifier.json"
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    reopened = subprocess.run(
        [sys.executable, "-c", "import json,sys; print(json.load(open(sys.argv[1]))['deterministic_evidence']['verdict'])", str(report_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert reopened.stdout.strip() == "partial"


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
    assert asyncio.run(
        ResearchJobWorker(
            worker_store,
            ApprovedExperimentBacktestExecutor(artifacts, producer),
            worker_id="uj08-worker",
        ).run_once()
    ) is True
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
    assert asyncio.run(
        ResearchJobWorker(
            worker_store,
            ApprovedExperimentBacktestExecutor(artifacts, _NoReceiptProducer()),
            worker_id="uj08-worker",
        ).run_once()
    ) is True
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
    assert asyncio.run(
        ResearchJobWorker(
            lost_store,
            ApprovedExperimentBacktestExecutor(artifacts, producer),
            worker_id="uj08-lost-worker",
        ).run_once()
    ) is True
    assert lost_store.job.status is ResearchJobStatus.RECONCILIATION_REQUIRED
    assert lost_store.job.blockers[0].code == "ambiguous_producer_outcome"
    assert producer.calls == [(job.request_ref.rsplit("/", 1)[-1], protocol_ref.artifact_id, _deterministic_run_id(job))]

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
    assert asyncio.run(
        ResearchJobWorker(
            failure_store,
            ApprovedExperimentBacktestExecutor(artifacts, _TerminalFailureProducer()),
            worker_id="uj08-failed-worker",
        ).run_once()
    ) is True
    assert failure_store.job.status is ResearchJobStatus.FAILED
    assert failure_store.job.blockers[0].code == "worker_execution_failed"


@pytest.mark.postgres
def test_uj08_postgres_campaign_uses_real_runner_and_fresh_process(
    uj08_postgres_settings: dict[str, object],
    tmp_path: Path,
) -> None:
    """Qualify the concrete runner, isolated schema, concurrent reviews, and reopen."""
    schema = f"trader_uj08_{uuid4().hex}"
    admin = psycopg.connect(**cast(Any, uj08_postgres_settings))
    admin.autocommit = True
    admin.execute(sql.SQL("CREATE SCHEMA {}" ).format(sql.Identifier(schema)))
    admin.close()
    dsn = psycopg.conninfo.make_conninfo(
        **cast(Any, uj08_postgres_settings),
        options=f"-c search_path={schema}",
    )
    event_store = None
    artifacts = None
    try:
        from trader.event_store import PostgresEventStore
        from trader_research.infrastructure.postgres import PostgresResearchArtifactStore

        event_store = PostgresEventStore(dsn=dsn)
        artifacts = PostgresResearchArtifactStore(dsn=dsn)
        fixture = build_realistic_optimization_fixture()
        seed_fixture(event_store, fixture)
        manifest, quality = data_evidence(event_store, fixture.selection)
        artifacts_for_job = artifacts
        proposal_ref, protocol_ref = _realistic_approved_inputs(
            artifacts_for_job,
            manifest,
            quality,
        )
        admission_store = PostgresResearchJobStore(artifacts.connection())
        admission = submit_approved_experiment_job(
            proposal_ref=proposal_ref,
            approved_protocol_ref=protocol_ref,
            requested_by="workflow-uj08-real",
            actor="workflow_executor",
            code_identity="git:uj08-real-runner",
            environment_identity=f"env:{schema}",
            artifact_store=artifacts,
            job_store=admission_store,
        )
        assert admission.ok is True, admission.errors
        job = ResearchJob.from_dict(admission.data["research_job"])
        worker = ResearchJobWorker(
            admission_store,
            ApprovedExperimentBacktestExecutor(
                artifacts,
                BacktestRunnerResearchProducer(
                    artifacts,
                    build_backtest_config(uj08_postgres_settings),
                    event_store,
                ),
            ),
            worker_id="uj08-real-runner",
        )
        assert asyncio.run(worker.run_once()) is True
        completed = admission_store.load(job.job_id)
        assert completed.status is ResearchJobStatus.SUCCEEDED
        assert len(completed.produced_artifact_refs) == 1
        run_ref = completed.produced_artifact_refs[0]
        run_record = artifacts.load_artifact_record(BACKTEST_RUN, run_ref.artifact_id)
        assert run_record.payload["run_id"] == _deterministic_run_id(job)
        assert run_record.payload["bundle"]["result"]["run_id"] == _deterministic_run_id(job)
        assert run_record.payload["bundle"]["result"]["total_runs"] > 0

        proposal = artifacts.load_artifact_record(
            EXPERIMENT_PROTOCOL_PROPOSAL,
            proposal_ref.artifact_id,
        )
        protocol = artifacts.load_artifact_record(EXPERIMENT_PROTOCOL, protocol_ref.artifact_id)
        manifest_record = artifacts.load_artifact_record("dataset_manifest", manifest["dataset_id"])
        strategy_record = artifacts.load_artifact_record(
            "implementation_version",
            protocol.payload["strategy"]["implementation_ref"]["artifact_id"],
        )
        lineage = {
            "experiment_id": protocol.artifact_id,
            "proposal_id": proposal.artifact_id,
            "scope_id": manifest["dataset_id"],
            "strategy_version_id": strategy_record.artifact_id,
            "run_id": run_record.artifact_id,
        }

        def save_review(role: str, artifact_type: str, status: str) -> Any:
            """Persist one independent review over a separate connection."""
            review_store = PostgresResearchArtifactStore(dsn=dsn, ensure_schema=False)
            try:
                return review_store.save_artifact(
                    artifact_type=artifact_type,
                    artifact_id=f"uj08-real-{role}-1",
                    domain_owner="Review",
                    producer_tool=f"{role}_review_experiment",
                    payload={"artifact_type": artifact_type, **lineage, "status": status},
                    status=status,
                    metadata={"revision": 1},
                )
            finally:
                review_store.close()

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            evaluation, robustness = tuple(
                pool.map(
                    save_review,
                    ("evaluation", "robustness"),
                    ("evaluation_report", "robustness_report"),
                    ("available", "negative"),
                )
            )
        terminal = artifacts.save_artifact(
            artifact_type=WORKFLOW_OUTCOME,
            artifact_id="uj08-real-terminal-1",
            domain_owner="Orchestration",
            producer_tool="research_record_workflow_outcome",
            payload={"artifact_type": WORKFLOW_OUTCOME, **lineage, "status": "completed"},
            status="completed",
            metadata={"revision": 1},
        )
        joined = qualify_evidence_join(
            experiment_id=protocol.artifact_id,
            proposal_id=proposal.artifact_id,
            scope_id=manifest["dataset_id"],
            strategy_version_id=strategy_record.artifact_id,
            run_id=run_record.artifact_id,
            evidence_revision=1,
            records=(
                _join_ref("proposal", proposal, lineage),
                _join_ref(
                    "approval",
                    artifacts.load_artifact_record("approval_request", proposal.artifact_id),
                    lineage,
                ),
                _join_ref("scope", manifest_record, lineage),
                _join_ref("strategy", strategy_record, lineage),
                _join_ref("run", run_record, lineage),
                _join_ref("evaluation", evaluation, lineage),
                _join_ref("robustness", robustness, lineage, status=EvidenceJoinStatus.NEGATIVE),
                _join_ref("decision", terminal, lineage),
            ),
        )
        assert joined.verdict.value == "partial"

        checkout = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        report = {
            "fixture_id": "uj08-integrated-agent-directed-experiment-postgres-v2",
            "contract": "BacktestRunnerResearchProducer/ResearchJobWorker/EvidenceJoinResult",
            "contract_version": "2",
            "checkout_commit": checkout,
            "evidence_revision": 2,
            "schema": schema,
            "deterministic_evidence": joined.to_dict(),
            "model_gate": {"status": "not_claimed", "reason": "controlled third-party model gate is separate"},
        }
        report_path = tmp_path / "uj08-postgres-verifier.json"
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        reopened = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json, os; "
                    "from trader_research.infrastructure.postgres import PostgresResearchArtifactStore; "
                    "store = PostgresResearchArtifactStore(dsn=os.environ['UJ08_DSN'], ensure_schema=False); "
                    "record = store.load_artifact_record('backtest_run', os.environ['UJ08_RUN_ID']); "
                    "print(record.payload['run_id']); store.close()"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "UJ08_DSN": dsn, "UJ08_RUN_ID": run_record.artifact_id},
        )
        assert reopened.stdout.strip() == run_record.artifact_id
    finally:
        if artifacts is not None:
            artifacts.close()
        if event_store is not None:
            event_store.close()
        cleanup = psycopg.connect(**cast(Any, uj08_postgres_settings))
        cleanup.autocommit = True
        cleanup.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        cleanup.close()


@pytest.mark.postgres
def test_uj08_postgres_claim_is_single_winner_across_concurrent_workers(
    postgres_research_artifact_store,
    postgres_settings: dict[str, object],
) -> None:
    """An isolated verification database gives one of two workers the job lease."""
    primary = PostgresResearchJobStore(postgres_research_artifact_store.connection())
    primary.admit(
        ResearchJob(
            job_id="uj08-concurrent-job",
            operation_kind=ResearchOperationKind.BACKTEST,
            request_ref="research://postgres/experiment_job_request/uj08-request",
            request_digest="sha256:uj08-request",
            idempotency_key="uj08-concurrent-request",
            requested_by="workflow-uj08",
            actor="workflow_executor",
            code_identity="git:uj08-fixture",
            environment_identity="env:uj08-controlled",
        )
    )

    def claim(worker_id: str) -> bool:
        """Claim through an independent connection and return lease ownership."""
        connection = psycopg.connect(**cast(Any, postgres_settings), row_factory=dict_row)
        connection.autocommit = True
        try:
            store = PostgresResearchJobStore(connection)
            return store.claim_next(worker_id=worker_id, lease_seconds=30, max_attempts=3) is not None
        finally:
            connection.close()

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(claim, ("uj08-worker-a", "uj08-worker-b")))
    assert sum(results) == 1


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


def _realistic_approved_inputs(
    artifacts,
    manifest: dict[str, Any],
    quality: dict[str, Any],
) -> tuple[ArtifactReportRef, ArtifactReportRef]:
    """Build a fully admitted protocol over the deterministic replay fixture."""
    strategy_result = register_strategy_implementation(
        name="uj08-real-trailing-return",
        version="1",
        source_code=STRATEGY_SOURCE,
        factory_name="build_strategy",
        class_name="TrailingReturnTransitionStrategy",
        parameter_schema=STRATEGY_PARAMETER_SCHEMA,
        authoring_origin="uj08_qualification",
        capabilities=["multi_asset", "event_store_bars"],
        artifact_store=artifacts,
    )
    assert strategy_result.ok is True, strategy_result.errors
    strategy = artifacts.load_artifact_record(
        "implementation_version",
        strategy_result.data["implementation_version"]["implementation_version_id"],
    )
    strategy_validation = validate_strategy_implementation(
        implementation_version_id=strategy.artifact_id,
        fixture_parameters=BASE_STRATEGY_PARAMETERS,
        artifact_store=artifacts,
    )
    assert strategy_validation.ok is True, strategy_validation.errors

    risk_result = register_risk_manager_implementation(
        name="uj08-real-entry-limit",
        version="1",
        source_code=RISK_SOURCE,
        factory_name="build_risk_manager",
        class_name="EntryQuantityLimitRiskManager",
        parameter_schema=RISK_PARAMETER_SCHEMA,
        authoring_origin="uj08_qualification",
        capabilities=["entry_quantity_limit"],
        artifact_store=artifacts,
    )
    assert risk_result.ok is True, risk_result.errors
    risk = artifacts.load_artifact_record(
        "implementation_version",
        risk_result.data["implementation_version"]["implementation_version_id"],
    )
    risk_validation = validate_risk_manager_implementation(
        implementation_version_id=risk.artifact_id,
        fixture_parameters=RISK_PARAMETERS,
        artifact_store=artifacts,
    )
    assert risk_validation.ok is True, risk_validation.errors

    manifest_record = artifacts.save_artifact(
        artifact_type="dataset_manifest",
        artifact_id=manifest["dataset_id"],
        domain_owner="Data",
        producer_tool="data_create_research_snapshot",
        payload=manifest,
        status="captured",
        metadata={"qualification": "uj08-real"},
    )
    quality_record = artifacts.save_artifact(
        artifact_type="data_quality_report",
        artifact_id=quality["report_id"],
        domain_owner="Data",
        producer_tool="data_create_research_snapshot",
        payload=quality,
        status="captured",
        metadata={"dataset_manifest_artifact_id": manifest_record.artifact_id},
    )
    requirement = DataRequirement(
        symbols=tuple(str(item) for item in manifest["symbols"]),
        asset_class=str(manifest["asset_class"]),
        timeframe=str(manifest["timeframe"]),
        start=str(manifest["time_range"]["start"]),
        end=str(manifest["time_range"]["end"]),
        source=str(manifest.get("source_filter")) if manifest.get("source_filter") else None,
    )
    strategy_ref = _pinned_ref(strategy)
    risk_ref = _pinned_ref(risk)
    design = ExperimentDesignRequest(
        strategy=ProtocolStrategy(
            implementation_ref=strategy_ref,
            parameters=BASE_STRATEGY_PARAMETERS,
            portfolio_mode="multi_asset",
        ),
        risk_managers=(
            ProtocolRiskManager(
                implementation_ref=risk_ref,
                parameters=RISK_PARAMETERS,
            ),
        ),
        datasets=(
            ProtocolDataset(
                requirement_id="baseline",
                role=DatasetRole.BASELINE,
                requirement=requirement,
                dataset_manifest_ref=_pinned_ref(manifest_record),
                data_quality_report_ref=_pinned_ref(quality_record),
            ),
        ),
        costs=(CostAssumption(name="commission", value=0.25, unit="USD"),),
        initial_portfolio=InitialPortfolio(cash=100_000.0, currency="USD"),
        robustness_requirements=(),
        evaluation_questions=("Does the admitted strategy replay deterministically?",),
        falsification_criteria=("Reject when the qualified replay cannot be completed.",),
        material_assumptions=(
            MaterialAssumption(
                assumption_id="commission",
                category="cost",
                statement="Use the declared fixed commission.",
                value={"fixed_per_order": 0.25, "unit": "USD"},
            ),
        ),
        requested_approver="operator:jared",
        deterministic_seed=5701,
        max_runs=48,
        log_cycle_details=False,
        runtime_limits={"fixture": "uj08-real", "bounded": True},
        optimizer_profile="builtin_random",
    )
    objective = ResearchObjective(
        objective_id="uj08-real-objective",
        statement="Qualify the approved strategy against the retained replay fixture.",
        success_criteria=("Retain deterministic runner evidence.",),
        requested_by="operator:jared",
        actor="operator:jared",
        supplied_artifact_refs=(strategy_ref, risk_ref),
        status=ResearchObjectiveStatus.APPROVED,
    )
    proposal_result = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="uj08-real-proposal",
        requested_by="workflow-uj08-real",
        actor=EXPERIMENT_DESIGN_AGENT_OWNER,
        artifact_store=artifacts,
    )
    assert proposal_result.ok is True, proposal_result.errors
    proposal = ExperimentProtocolProposal.from_dict(
        proposal_result.data["experiment_protocol_proposal"]
    )
    requested = proposal.protocol.approvals[0]
    approved = apply_experiment_protocol_approvals(
        proposal,
        (
            replace(
                requested,
                status=ApprovalStatus.APPROVED,
                decided_by=requested.requested_from,
                rationale="Approved retained qualification fixture.",
            ),
        ),
    )
    approved_record = artifacts.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL,
        artifact_id=approved.protocol_id,
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="research_register_experiment_workflow",
        payload=approved.to_dict(),
        status="approved",
    )
    artifacts.save_artifact(
        artifact_type="approval_request",
        artifact_id=proposal.proposal_id,
        domain_owner="Orchestration",
        producer_tool="research_register_experiment_workflow",
        payload={"artifact_type": "approval_request", "proposal_id": proposal.proposal_id, "status": "approved"},
        status="approved",
    )
    proposal_record = artifacts.load_artifact_record(
        EXPERIMENT_PROTOCOL_PROPOSAL,
        proposal.proposal_id,
    )
    return _pinned_ref(proposal_record), _pinned_ref(approved_record)


def _approved_inputs() -> tuple[InMemoryResearchArtifactStore, ArtifactReportRef, ArtifactReportRef]:
    """Build one exact approved proposal and protocol from canonical fixtures."""
    from trader_research.governance import (
        EXPERIMENT_DESIGN_AGENT_OWNER,
        create_experiment_protocol_proposal,
    )

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
        (replace(requested, status=ApprovalStatus.APPROVED, decided_by=requested.requested_from, rationale="Approved fixture."),),
    )
    artifacts.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL,
        artifact_id=approved.protocol_id,
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="research_register_experiment_workflow",
        payload=approved.to_dict(),
        status="approved",
    )
    proposal_record = artifacts.load_artifact_record(EXPERIMENT_PROTOCOL_PROPOSAL, proposal.proposal_id)
    protocol_record = artifacts.load_artifact_record(EXPERIMENT_PROTOCOL, approved.protocol_id)
    artifacts.save_artifact(
        artifact_type="approval_request",
        artifact_id=proposal.proposal_id,
        domain_owner="Orchestration",
        producer_tool="research_register_experiment_workflow",
        payload={"artifact_type": "approval_request", "proposal_id": proposal.proposal_id, "status": "approved"},
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


async def _save_independent_reviews(store, lineage):
    """Persist Evaluation and negative Robustness evidence concurrently."""
    async def save(role: str, artifact_type: str, status: str):
        payload = {"artifact_type": artifact_type, **lineage, "status": status}
        return store.save_artifact(
            artifact_type=artifact_type,
            artifact_id=f"uj08-{role}-1",
            domain_owner="Review",
            producer_tool=f"{role}_review_experiment",
            payload=payload,
            status=status,
            metadata={"revision": 1},
        )

    return await asyncio.gather(
        save("evaluation", "evaluation_report", "available"),
        save("robustness", "robustness_report", "negative"),
    )


def _join_ref(role: str, record, lineage, *, status=EvidenceJoinStatus.AVAILABLE):
    """Build a typed evidence-join reference from one canonical record."""
    return EvidenceJoinRef(
        role=role,
        reference=_pinned_ref(record),
        revision=1,
        status=status,
        lineage=lineage,
        statistical_status="inconclusive" if role == "evaluation" else None,
        robustness_status="fail" if role == "robustness" else None,
        comparison_status="eligible" if role == "decision" else None,
        limitations=("Controlled fixture only",) if role in {"evaluation", "robustness"} else (),
    )
