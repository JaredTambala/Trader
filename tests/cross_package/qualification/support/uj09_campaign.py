"""Real producer and isolated database composition for Console review qualification."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import os
import sys
from typing import Any, Iterator
from uuid import uuid4

import psycopg
from psycopg import sql

from trader.event_store import PostgresEventStore
from trader.event_store.console_read_contract import install_console_read_contract
from trader_agents import PersistentStdioMcpToolClient
from trader_console_api import ApprovedExperimentBacktestExecutor, BacktestRunnerResearchProducer, ResearchJobWorker
from trader_research.governance import QUANT_RESEARCH_SUPERVISOR_OWNER, ResearchIssue, ResearchJob, ResearchJobStatus, WorkflowOutcome, WorkflowOutcomeStatus
from trader_research.foundation import json_payload_hash
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore, PostgresResearchJobStore
from tests.cross_package.qualification.support.realistic_optimization_fixture import build_backtest_config
from tests.cross_package.qualification.support.uj08_campaign import CampaignStore, REPO_ROOT, call, prepare_protocol, verify_chain
from tests.cross_package.qualification.support.uj08_inputs import _pinned_ref
from tests.cross_package.qualification.support.uj08_session import campaign_runtime


@contextmanager
def isolated_database(settings: dict[str, Any]) -> Iterator[tuple[CampaignStore, dict[str, Any]]]:
    """Own a separate database because Console projections resolve public tables."""
    database = f"trader_uj09_{uuid4().hex}_test"
    with psycopg.connect(**settings, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database)))
    campaign_settings = {**settings, "dbname": database}
    dsn = psycopg.conninfo.make_conninfo(**campaign_settings)
    try:
        events = PostgresEventStore(dsn=dsn)
        artifacts = PostgresResearchArtifactStore(dsn=dsn)
        try:
            with psycopg.connect(dsn) as connection:
                install_console_read_contract(connection)
            yield CampaignStore(dsn, "public", events, artifacts,
                                PostgresResearchJobStore(artifacts.connection())), campaign_settings
        finally:
            artifacts.close()
            events.close()
    finally:
        with psycopg.connect(**settings, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


def mcp_client(dsn: str) -> PersistentStdioMcpToolClient:
    """Start a production MCP process against this campaign's private database."""
    return PersistentStdioMcpToolClient(
        command=sys.executable,
        args=["-m", "tests.cross_package.qualification.support.uj09_process", "mcp"],
        cwd=REPO_ROOT, env={**os.environ, "UJ09_DSN": dsn,
                           "PYTHONPATH": f"{REPO_ROOT / 'src'}{os.pathsep}{REPO_ROOT}"}, read_timeout_seconds=60,
    )


async def _review_blocker(dsn: str, role: str, run_ref: Any) -> ResearchIssue:
    """Discover the missing real producer without inventing an independent report."""
    expected = {"evaluation": "evaluation_review_experiment", "robustness": "adversarial_review_experiment"}[role]
    async with mcp_client(dsn) as client:
        names = sorted(item.name for item in await client.list_tools())
        await call(client, "research_read_artifact", {
            "artifact_ref": run_ref.uri, "expected_artifact_type": "backtest_run", "include_payload": False,
        })
        assert expected not in names
    return ResearchIssue(
        code="independent_review_producer_unavailable",
        message=f"No registered {role} producer supports this approved single-backtest scope.",
        details={"role": role, "branch_id": f"workflow-uj08-real:{role}",
                 "run_ref": run_ref.to_dict(), "required_producer": expected,
                 "catalogue_sha256": json_payload_hash({"tools": names})},
    )


async def execute(campaign: CampaignStore, settings: dict[str, Any], *, code_identity: str) -> dict[str, Any]:
    """Produce one actual governed run and retain its honest blocked review outcome."""
    async with mcp_client(campaign.dsn) as client:
        proposal, protocol, objective, plan = await prepare_protocol(campaign, client)
        # Retain the real declared session; this campaign makes no Coordinator/model claim.
        _, session = campaign_runtime(campaign.dsn, None)
        await call(client, "research_create_agent_session", {"session": session.to_dict()})
        admitted = await call(client, "research_submit_approved_experiment_job", {
            "proposal_ref": _pinned_ref(campaign.artifacts.load_artifact_record(
                "experiment_protocol_proposal", proposal.proposal_id)).to_dict(),
            "approved_protocol_ref": _pinned_ref(campaign.artifacts.load_artifact_record(
                "experiment_protocol", protocol.protocol_id)).to_dict(),
            "requested_by": proposal.requested_by, "actor": QUANT_RESEARCH_SUPERVISOR_OWNER,
            "code_identity": code_identity, "environment_identity": f"uj09-postgres:{settings['dbname']}",
        })
        job = ResearchJob.from_dict(admitted["data"]["research_job"])
        worker = ResearchJobWorker(
            campaign.jobs,
            ApprovedExperimentBacktestExecutor(campaign.artifacts,
                BacktestRunnerResearchProducer(campaign.artifacts, build_backtest_config(settings), campaign.events)),
            worker_id="uj09-real-worker",
        )
        assert await worker.run_once()
        completed = campaign.jobs.load(job.job_id)
        assert completed.status is ResearchJobStatus.SUCCEEDED
        run_ref = completed.produced_artifact_refs[0]
        blockers = await asyncio.gather(*(_review_blocker(campaign.dsn, role, run_ref)
                                          for role in ("evaluation", "robustness")))
        outcome = WorkflowOutcome(
            outcome_id="uj09-real-terminal", workflow_id=proposal.requested_by, plan_id=plan.plan_id,
            objective_ref=_pinned_ref(campaign.artifacts.load_artifact_record("research_objective", objective.objective_id)),
            protocol_ref=_pinned_ref(campaign.artifacts.load_artifact_record("experiment_protocol", protocol.protocol_id)),
            status=WorkflowOutcomeStatus.BLOCKED, produced_artifact_refs=(run_ref,), review_verdict_refs=(),
            requested_by=plan.requested_by, actor=plan.actor, blockers=tuple(blockers),
            next_permitted_actions=("review blocked evidence",),
        )
        await call(client, "research_record_workflow_outcome", {
            "outcome": outcome.to_dict(), "requested_by": plan.requested_by, "actor": plan.actor,
        })
        assert not campaign.artifacts.list_artifacts(artifact_type="evaluation_report")
        assert not campaign.artifacts.list_artifacts(artifact_type="robustness_report")
        return verify_chain(campaign.dsn, job.job_id, outcome.outcome_id)
