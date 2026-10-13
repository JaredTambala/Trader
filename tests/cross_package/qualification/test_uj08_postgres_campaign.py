"""Public MCP-to-worker qualification of the governed experiment evidence chain.

Subject: UJ-08 approved handoff, isolated execution, session pause recovery,
independent review blockers, terminal lineage, and durable failure handling.
Level: Cross-package qualification with fresh operating-system processes.
Collaborators: Real stdio MCP, Postgres events/artifacts/jobs/checkpoints,
canonical specification services and BacktestRunner. Scripted Coordinator model
responses and injected producer faults exercise deterministic control contracts.
Guarantees: Exact approval and source/Data pins govern execution, concurrent
review branches preserve unavailable-producer blockers, recovery reconstructs
canonical evidence, and uncertain execution never silently replays.
Non-goals: Third-party-model quality, independent scientific review maturity,
positive statistical evidence, paper admission, or pausing an active backtest.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from typing import Any

import psycopg
from psycopg.rows import dict_row
import pytest

from trader_console_api import (
    ApprovedExperimentBacktestExecutor,
    BacktestRunnerResearchProducer,
    ResearchJobExecutionOutcome,
    ResearchJobWorker,
)
from trader_console_api.worker import AmbiguousExecutionError
from trader_research.foundation import ResearchArtifactStoreError
from trader_research.experiments import run_backtest_specification
from trader_research.governance import (
    ResearchIssue,
    ResearchJobStatus,
    ResearchJobLifecycleService,
    WorkflowOutcome,
    WorkflowOutcomeStatus,
)
from trader_research.infrastructure.postgres import PostgresResearchJobStore
from tests.cross_package.qualification.support.realistic_optimization_fixture import (
    build_backtest_config,
)
from tests.cross_package.qualification.support.uj08_inputs import _pinned_ref
from tests.cross_package.qualification.support.uj08_campaign import (
    admit,
    call,
    checkout_commit,
    isolated_store,
    mcp_client,
    prepare_protocol,
    review_preflight,
    verify_chain,
)
from tests.cross_package.qualification.support.uj08_session import pause_session


@pytest.fixture
def uj08_postgres_settings() -> dict[str, Any]:
    """Require the explicit disposable profile; required CI must never skip it."""
    values = {
        key: os.environ.get(f"UJ08_PG_{name}", "")
        for key, name in (
            ("host", "HOST"),
            ("port", "PORT"),
            ("dbname", "DB"),
            ("user", "USER"),
            ("password", "PASSWORD"),
        )
    }
    if not all(values.values()):
        if os.environ.get("UJ08_REQUIRED") == "1":
            pytest.fail("UJ08_REQUIRED=1 requires every UJ08_PG_* setting")
        pytest.skip("UJ08_PG_* disposable database profile is not configured")
    if not values["dbname"].endswith(("_test", "_testing")):
        raise pytest.UsageError("UJ08_PG_DB must name a disposable test database")
    settings = {**values, "port": int(values["port"])}
    with psycopg.connect(**settings) as connection:
        identity = connection.execute(
            "SELECT current_database(), current_user, current_setting('TimeZone')"
        ).fetchone()
    assert identity[:2] == (settings["dbname"], settings["user"])
    assert identity[2].upper() in {"UTC", "ETC/UTC"}
    return settings


def _fresh_process(module: str, dsn: str, **identities: str) -> dict[str, Any]:
    """Run canonical recovery over a new interpreter and store connections."""
    child = subprocess.run(
        [sys.executable, "-m", module],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "UJ08_DSN": dsn, **identities},
    )
    assert child.returncode == 0, child.stderr
    return json.loads(child.stdout)


@pytest.mark.postgres
def test_uj08_public_campaign_recovers_exact_chain_and_retains_review_blockers(
    uj08_postgres_settings: dict[str, Any],
    tmp_path: Path,
) -> None:
    """MCP admission, real execution, pause/resume and full reopen preserve blockers."""
    with isolated_store(uj08_postgres_settings) as campaign:

        async def run_campaign() -> dict[str, Any]:
            async with mcp_client(campaign.dsn) as client:
                proposal, protocol, objective, plan = await prepare_protocol(
                    campaign, client
                )
                paused = await pause_session(campaign.dsn, client)
                resumed = await asyncio.to_thread(
                    _fresh_process,
                    "tests.cross_package.qualification.support.uj08_session",
                    campaign.dsn,
                )
                assert resumed["branch_id"] == paused["branch_id"]
                assert resumed["model_calls"] == 2
                job, arguments = await admit(campaign, client, proposal, protocol)
                worker = ResearchJobWorker(
                    campaign.jobs,
                    ApprovedExperimentBacktestExecutor(
                        campaign.artifacts,
                        BacktestRunnerResearchProducer(
                            campaign.artifacts,
                            build_backtest_config(uj08_postgres_settings),
                            campaign.events,
                        ),
                    ),
                    worker_id="uj08-real-runner",
                )
                assert await worker.run_once() is True
                completed = campaign.jobs.load(job.job_id)
                assert completed.status is ResearchJobStatus.SUCCEEDED
                run_ref = completed.produced_artifact_refs[0]
                run_record = campaign.artifacts.load_artifact_record(
                    "backtest_run", run_ref.artifact_id
                )

                def forbid_repeat(processed, total, last_ts):
                    raise AssertionError(
                        "A retained explicit run ID must not execute another replay"
                    )

                replayed_run = run_backtest_specification(
                    event_store=campaign.events,
                    config=build_backtest_config(uj08_postgres_settings),
                    artifact_store=campaign.artifacts,
                    backtest_specification_validation_ref=run_record.payload[
                        "backtest_specification_validation_id"
                    ],
                    run_id=run_ref.artifact_id,
                    progress_callback=forbid_repeat,
                )
                assert replayed_run.ok is True, replayed_run.errors
                # Independent clients and process-owned connections prevent shared branch state.
                blockers = await asyncio.gather(
                    review_preflight(campaign.dsn, "evaluation", run_ref),
                    review_preflight(campaign.dsn, "robustness", run_ref),
                )
                outcome = WorkflowOutcome(
                    outcome_id="uj08-real-terminal",
                    workflow_id=proposal.requested_by,
                    plan_id=plan.plan_id,
                    objective_ref=_pinned_ref(
                        campaign.artifacts.load_artifact_record(
                            "research_objective", objective.objective_id
                        )
                    ),
                    protocol_ref=_pinned_ref(
                        campaign.artifacts.load_artifact_record(
                            "experiment_protocol", protocol.protocol_id
                        )
                    ),
                    status=WorkflowOutcomeStatus.BLOCKED,
                    produced_artifact_refs=(run_ref,),
                    review_verdict_refs=(),
                    requested_by=plan.requested_by,
                    actor=plan.actor,
                    blockers=tuple(blockers),
                    next_permitted_actions=("review blocked evidence",),
                )
                await call(
                    client,
                    "research_record_workflow_outcome",
                    {
                        "outcome": outcome.to_dict(),
                        "requested_by": proposal.requested_by,
                        "actor": plan.actor,
                    },
                )
                invalid_outcome = outcome.to_dict()
                invalid_outcome["objective_ref"] = arguments["proposal_ref"]
                await call(
                    client,
                    "research_record_workflow_outcome",
                    {
                        "outcome": invalid_outcome,
                        "requested_by": proposal.requested_by,
                        "actor": plan.actor,
                    },
                    ok=False,
                )
                expected = verify_chain(campaign.dsn, job.job_id, outcome.outcome_id)
                reopened = await asyncio.to_thread(
                    _fresh_process,
                    "tests.cross_package.qualification.support.uj08_campaign",
                    campaign.dsn,
                    UJ08_JOB_ID=job.job_id,
                    UJ08_OUTCOME_ID=outcome.outcome_id,
                )
                assert reopened == expected
                replay = await call(
                    client, "research_submit_approved_experiment_job", arguments
                )
                assert replay["data"]["research_job"] == completed.to_dict()
                changed = {**arguments, "code_identity": "git:changed-checkout"}
                await call(
                    client, "research_submit_approved_experiment_job", changed, ok=False
                )
                assert await worker.run_once() is False
                assert (
                    len(campaign.artifacts.list_artifacts(artifact_type="backtest_run"))
                    == 1
                )
                return {
                    "canonical_evidence": reopened,
                    "session_pause": paused,
                    "session_resume": resumed,
                }

        evidence = asyncio.run(run_campaign())
        report = {
            "fixture_id": "uj08-public-postgres-campaign-v3",
            "contract": "MCP/ResearchJob/CanonicalBacktestSpecification/WorkflowOutcome/EvidenceJoinResult",
            "contract_version": "3",
            "checkout_commit": checkout_commit(),
            "evidence_revision": 3,
            "command": "uv run pytest tests/cross_package/qualification/test_uj08_postgres_campaign.py -m postgres -q",
            "assertions": {
                "public_approved_supervisor_handoff": "passed",
                "real_runner_and_specification_lineage": "passed",
                "concurrent_independent_review_blockers": "passed",
                "session_pause_fresh_process_resume": "passed",
                "complete_canonical_chain_fresh_process": "passed",
                "terminal_submission_no_replay": "passed",
            },
            **evidence,
            "model_gate": {
                "status": "not_claimed",
                "reason": "Scripted model responses qualify control flow only.",
            },
            "scientific_gate": {
                "status": "blocked",
                "reason": "Single-backtest independent review producers are unavailable.",
            },
        }
        path = Path(
            os.environ.get(
                "UJ08_EVIDENCE_PATH", str(tmp_path / "uj08-postgres-verifier.json")
            )
        )
        path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")


@pytest.mark.postgres
def test_uj08_concurrent_workers_have_one_schema_scoped_claim_winner(
    uj08_postgres_settings: dict[str, Any],
) -> None:
    """Two actual connections race on one admitted job and retain one exact lease."""
    with isolated_store(uj08_postgres_settings) as campaign:

        async def prepare():
            async with mcp_client(campaign.dsn) as client:
                proposal, protocol, _, _ = await prepare_protocol(campaign, client)
                return (await admit(campaign, client, proposal, protocol))[0]

        job = asyncio.run(prepare())
        barrier = Barrier(2)

        def claim(identity: str):
            with psycopg.connect(
                campaign.dsn, row_factory=dict_row, autocommit=True
            ) as connection:
                barrier.wait(timeout=10)
                return PostgresResearchJobStore(connection).claim_next(
                    worker_id=identity, lease_seconds=60, max_attempts=3
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ("worker-a", "worker-b")))
        winners = [item for item in results if item is not None]
        assert len(winners) == 1
        assert winners[0].job_id == job.job_id and winners[0].attempt == 1
        assert campaign.jobs.load(job.job_id).lease_id == winners[0].lease_id
        evidence_path = os.environ.get("UJ08_EVIDENCE_PATH")
        if evidence_path:
            Path(f"{evidence_path}.concurrent_claim.json").write_text(
                json.dumps(
                    {
                        "fixture_id": "uj08-concurrent-claim-v3",
                        "contract_version": "3",
                        "checkout_commit": checkout_commit(),
                        "evidence_revision": 3,
                        "canonical_job": campaign.jobs.load(job.job_id).to_dict(),
                        "concurrent_workers": 2,
                        "claim_winners": len(winners),
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )


class MissingRunReceiptStore:
    """Inject a persistence loss after real BacktestRunner execution."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def save_artifact(self, **values: Any) -> Any:
        """Reject the exact run receipt while retaining actual earlier artifacts."""
        if values["artifact_type"] == "backtest_run":
            raise ResearchArtifactStoreError("Injected run receipt persistence failure")
        return self.delegate.save_artifact(**values)


@dataclass
class FaultExecutor:
    """Inject producer boundaries while using actual durable job transitions."""

    campaign: Any
    fault: str

    async def execute(self, job, *, run_id, progress):
        del run_id
        if self.fault == "partial":
            return ResearchJobExecutionOutcome(
                status="partial",
                blockers=(
                    ResearchIssue(
                        code="fixture_partial_evidence",
                        message="Injected producer retained incomplete evidence.",
                    ),
                ),
            )
        if self.fault == "failure":
            raise ValueError("Injected pre-execution producer failure")
        if self.fault == "cancel":
            result = ResearchJobLifecycleService(self.campaign.jobs).cancel(
                job.job_id,
                actor=job.actor,
                reason="Cancel active research before another producer action.",
            )
            assert result.ok
            await progress(None)
        if self.fault == "worker_loss":
            # Test-owned fault injection changes only this exact leased row.
            self.campaign.artifacts.connection().execute(
                "UPDATE research_jobs SET lease_expires_at = %s WHERE job_id = %s",
                [datetime.now(UTC) - timedelta(seconds=1), job.job_id],
            )
            await progress(None)
        raise AssertionError("The lease sink must stop cancelled or lost work")


@pytest.mark.postgres
@pytest.mark.parametrize(
    "fault,expected",
    [
        ("partial", ResearchJobStatus.PARTIAL),
        ("failure", ResearchJobStatus.FAILED),
        ("cancel", ResearchJobStatus.CANCELLED),
        ("queued_cancel", ResearchJobStatus.CANCELLED),
        ("worker_loss", ResearchJobStatus.RECONCILIATION_REQUIRED),
        ("unsupported_cost", ResearchJobStatus.FAILED),
        ("receipt_failure", ResearchJobStatus.RECONCILIATION_REQUIRED),
    ],
)
def test_uj08_durable_fault_paths_reopen_without_automatic_execution(
    uj08_postgres_settings: dict[str, Any],
    fault: str,
    expected: ResearchJobStatus,
) -> None:
    """Injected failures preserve exact durable blockers and never silently requeue."""
    with isolated_store(uj08_postgres_settings) as campaign:

        async def execute():
            async with mcp_client(campaign.dsn) as client:
                proposal, protocol, _, _ = await prepare_protocol(
                    campaign, client, unsupported_cost=fault == "unsupported_cost"
                )
                job, arguments = await admit(campaign, client, proposal, protocol)
                denied = ResearchJobLifecycleService(campaign.jobs).cancel(
                    job.job_id, actor="foreign-agent", reason="Unauthorized"
                )
                assert denied.ok is False
                executor = FaultExecutor(campaign, fault)
                if fault in {"unsupported_cost", "receipt_failure"}:
                    producer_store = (
                        MissingRunReceiptStore(campaign.artifacts)
                        if fault == "receipt_failure"
                        else campaign.artifacts
                    )
                    executor = ApprovedExperimentBacktestExecutor(
                        campaign.artifacts,
                        BacktestRunnerResearchProducer(
                            producer_store,
                            build_backtest_config(uj08_postgres_settings),
                            campaign.events,
                        ),
                    )
                worker = ResearchJobWorker(
                    campaign.jobs, executor, worker_id="fault-worker"
                )
                if fault == "queued_cancel":
                    accepted = ResearchJobLifecycleService(campaign.jobs).cancel(
                        job.job_id, actor=job.actor, reason="Cancel before execution."
                    )
                    assert accepted.ok
                if fault in {"cancel", "worker_loss"}:
                    with pytest.raises(
                        AmbiguousExecutionError, match="terminal receipt"
                    ):
                        await worker.run_once()
                elif fault == "queued_cancel":
                    assert await worker.run_once() is False
                else:
                    assert await worker.run_once()
                if fault == "worker_loss":
                    recovered = campaign.jobs.reconcile_expired_leases()
                    assert len(recovered) == 1 and recovered[0].retryable is False
                saved = campaign.jobs.load(job.job_id)
                assert saved.status is expected and saved.blockers
                if fault in {"unsupported_cost", "receipt_failure"}:
                    assert not campaign.artifacts.list_artifacts(
                        artifact_type="backtest_run"
                    )
                if fault == "unsupported_cost":
                    assert "unsupported approved cost" in saved.blockers[0].message
                if fault == "receipt_failure":
                    assert saved.blockers[0].code == "ambiguous_producer_outcome"
                    assert saved.retryable is False
                assert await worker.run_once() is False
                replay = await call(
                    client, "research_submit_approved_experiment_job", arguments
                )
                assert replay["data"]["research_job"] == saved.to_dict()
                return saved.to_dict()

        retained = asyncio.run(execute())
        script = """import json, os
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore, PostgresResearchJobStore
store = PostgresResearchArtifactStore(dsn=os.environ['UJ08_DSN'], ensure_schema=False)
print(json.dumps(PostgresResearchJobStore(store.connection()).load(os.environ['UJ08_JOB_ID']).to_dict(), sort_keys=True))
store.close()
"""
        child = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "UJ08_DSN": campaign.dsn,
                "UJ08_JOB_ID": retained["job_id"],
            },
        )
        assert json.loads(child.stdout) == retained
        evidence_path = os.environ.get("UJ08_EVIDENCE_PATH")
        if evidence_path:
            Path(f"{evidence_path}.{fault}.json").write_text(
                json.dumps(
                    {
                        "fixture_id": f"uj08-durable-fault-{fault}-v3",
                        "contract_version": "3",
                        "checkout_commit": checkout_commit(),
                        "evidence_revision": 3,
                        "fault": fault,
                        "canonical_job": retained,
                        "fresh_process_reopen": "passed",
                        "automatic_execution_replay": "suppressed",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
