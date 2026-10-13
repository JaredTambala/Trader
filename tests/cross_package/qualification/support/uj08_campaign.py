"""Public-boundary composition and canonical recovery for the UJ-08 campaign.

Fixtures expose only pinned public references. The verifier reloads and checks
producer-owned identities rather than copying an expected lineage onto records.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterator
from uuid import uuid4

import psycopg
from psycopg import sql

from trader.event_store import PostgresEventStore
from trader_agents import PersistentStdioMcpToolClient
from trader_research.experiments import ExperimentJobRequest
from trader_research.experiments.specifications import (
    load_passed_backtest_specification,
)
from trader_research.experiments.specifications.common import (
    normalized_dataset_manifest,
)
from trader_research.foundation import json_payload_hash, parse_research_artifact_uri
from trader_research.governance import (
    ArtifactCardinality,
    ArtifactSlot,
    ArtifactReportRef,
    ApprovalStatus,
    CapabilityDefinition,
    CapabilitySideEffect,
    CostAssumption,
    ExperimentProtocol,
    ExperimentProtocolProposal,
    ResearchJob,
    QUANT_RESEARCH_SUPERVISOR_OWNER,
    WorkflowOutcome,
    WorkflowPlan,
    WorkflowPlanStatus,
    WorkflowStep,
    apply_experiment_protocol_approvals,
)
from trader_research.infrastructure.postgres import (
    PostgresResearchArtifactStore,
    PostgresResearchJobStore,
)
from trader_research.review import (
    EvidenceJoinRef,
    EvidenceJoinStatus,
    qualify_evidence_join,
)
from tests.cross_package.qualification.support.realistic_optimization_fixture import (
    build_realistic_optimization_fixture,
    data_evidence,
    seed_fixture,
)
from tests.cross_package.qualification.support.uj08_inputs import (
    realistic_design,
    _pinned_ref,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


def checkout_commit() -> str:
    """Pin the actual checkout, including the CI checkout revision."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def mcp_client(dsn: str) -> PersistentStdioMcpToolClient:
    """Use real stdio transport with production registrations and scoped stores."""
    return PersistentStdioMcpToolClient(
        command=sys.executable,
        args=["-m", "tests.cross_package.qualification.support.mcp_uj08_server"],
        cwd=REPO_ROOT,
        env={**os.environ, "UJ08_DSN": dsn},
        read_timeout_seconds=60,
    )


async def call(
    client: Any, name: str, arguments: dict[str, Any], *, ok: bool = True
) -> dict[str, Any]:
    """Require the public envelope's operation, ownership, and success state."""
    response = await client.call_tool(name, arguments)
    envelope = response["structuredContent"]
    assert envelope["command"] == name, envelope
    assert envelope["ok"] is ok, envelope
    assert response["isError"] is (not ok), response
    return envelope


@dataclass
class CampaignStore:
    """Test-owned schema and independent event/artifact/job connections."""

    dsn: str
    schema: str
    events: PostgresEventStore
    artifacts: PostgresResearchArtifactStore
    jobs: PostgresResearchJobStore


@contextmanager
def isolated_store(settings: dict[str, Any]) -> Iterator[CampaignStore]:
    """Create and drop only this test's unique schema in a disposable database."""
    schema = f"trader_uj08_{uuid4().hex}"
    with psycopg.connect(**settings, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    dsn = psycopg.conninfo.make_conninfo(**settings, options=f"-c search_path={schema}")
    events = PostgresEventStore(dsn=dsn)
    artifacts = PostgresResearchArtifactStore(dsn=dsn)
    try:
        yield CampaignStore(
            dsn,
            schema,
            events,
            artifacts,
            PostgresResearchJobStore(artifacts.connection()),
        )
    finally:
        artifacts.close()
        events.close()
        with psycopg.connect(**settings, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


async def prepare_protocol(
    campaign: CampaignStore, client: Any, *, unsupported_cost: bool = False
) -> tuple[Any, Any, Any, Any]:
    """Create a real MCP proposal and register its operator-approved workflow."""
    fixture = build_realistic_optimization_fixture()
    seed_fixture(campaign.events, fixture)
    manifest, quality = data_evidence(campaign.events, fixture.selection)
    objective, design = realistic_design(
        campaign.artifacts, campaign.events, manifest, quality
    )
    if unsupported_cost:
        design = replace(design, costs=(CostAssumption("commission", 0.25, "EUR"),))
    created = await call(
        client,
        "research_create_experiment_protocol_proposal",
        {
            "objective": objective.to_dict(),
            "design_request": design.to_dict(),
            "task_id": "uj08-real-proposal",
            "requested_by": "workflow-uj08-real",
            "actor": "Experiment Design Agent",
        },
    )
    proposal = ExperimentProtocolProposal.from_dict(
        created["data"]["experiment_protocol_proposal"]
    )
    approval = replace(
        proposal.protocol.approvals[0],
        status=ApprovalStatus.APPROVED,
        decided_by=design.requested_approver,
        rationale="Reviewed bounded retained fixture.",
    )
    protocol = apply_experiment_protocol_approvals(proposal, (approval,))
    slot = ArtifactSlot(
        "run", "backtest_run", "Experiments", ArtifactCardinality.EXACTLY_ONE, True
    )
    capability = CapabilityDefinition(
        "approved_backtest",
        "1",
        "Execute an approved immutable backtest",
        "Experiments",
        "research_run_backtest_specification",
        CapabilitySideEffect.LOCAL_MUTATING,
        (),
        (slot,),
    )
    plan = WorkflowPlan(
        plan_id=f"uj08-plan-{proposal.proposal_id}",
        objective_ref=ArtifactReportRef(
            objective.objective_id,
            "research_objective",
            "Orchestration",
            f"research://postgres/research_objective/{objective.objective_id}",
        ),
        protocol_ref=ArtifactReportRef(
            protocol.protocol_id,
            "experiment_protocol",
            "Experiments",
            f"research://postgres/experiment_protocol/{protocol.protocol_id}",
        ),
        template_id="approved_experiment_backtest",
        template_version="1",
        capabilities=(capability,),
        artifact_slots=(slot,),
        prerequisites=(),
        approvals=protocol.approvals,
        steps=(
            WorkflowStep(
                "backtest",
                capability.capability_id,
                output_bindings={"run": "run"},
                approval_ids=tuple(item.approval_id for item in protocol.approvals),
            ),
        ),
        requested_by=proposal.requested_by,
        actor="workflow_executor",
        status=WorkflowPlanStatus.READY,
    )
    # The public registration boundary must deny a pending proposal before any job exists.
    denied = await call(
        client,
        "research_register_experiment_workflow",
        {
            "objective": objective.to_dict(),
            "protocol": proposal.protocol.to_dict(),
            "workflow_plan": plan.to_dict(),
            "requested_by": proposal.requested_by,
            "actor": "workflow_executor",
        },
        ok=False,
    )
    assert "approved" in denied["errors"][0]["message"]
    assert (
        campaign.artifacts.connection()
        .execute("SELECT count(*) AS n FROM research_jobs")
        .fetchone()["n"]
        == 0
    )
    await call(
        client,
        "research_register_experiment_workflow",
        {
            "objective": objective.to_dict(),
            "protocol": protocol.to_dict(),
            "workflow_plan": plan.to_dict(),
            "requested_by": proposal.requested_by,
            "actor": "workflow_executor",
        },
    )
    return proposal, protocol, objective, plan


async def admit(
    campaign: CampaignStore, client: Any, proposal: Any, protocol: Any
) -> tuple[ResearchJob, dict[str, Any]]:
    """Record a Supervisor-owned handoff through the actual MCP process."""
    arguments = {
        "proposal_ref": _pinned_ref(
            campaign.artifacts.load_artifact_record(
                "experiment_protocol_proposal", proposal.proposal_id
            )
        ).to_dict(),
        "approved_protocol_ref": _pinned_ref(
            campaign.artifacts.load_artifact_record(
                "experiment_protocol", protocol.protocol_id
            )
        ).to_dict(),
        "requested_by": proposal.requested_by,
        "actor": QUANT_RESEARCH_SUPERVISOR_OWNER,
        "code_identity": f"git:{checkout_commit()}",
        "environment_identity": f"uj08-postgres:{campaign.schema}",
    }
    envelope = await call(client, "research_submit_approved_experiment_job", arguments)
    job = ResearchJob.from_dict(envelope["data"]["research_job"])
    assert job.actor == QUANT_RESEARCH_SUPERVISOR_OWNER
    return job, arguments


def _load_pinned(store: Any, reference: ArtifactReportRef) -> Any:
    """Resolve exact authority, URI identity, and payload digest after restart."""
    kind, identity = parse_research_artifact_uri(reference.uri)
    assert (kind, identity) == (reference.artifact_type, reference.artifact_id)
    record = store.load_artifact_record(kind, identity)
    assert record.domain_owner == reference.domain_owner
    assert record.uri == reference.uri
    assert json_payload_hash(record.payload) == reference.metadata["payload_sha256"]
    return record


def verify_chain(dsn: str, job_id: str, outcome_id: str) -> dict[str, Any]:
    """Reconstruct the complete chain from canonical records, never a saved report."""
    store = PostgresResearchArtifactStore(dsn=dsn, ensure_schema=False)
    try:
        job = PostgresResearchJobStore(store.connection()).load(job_id)
        kind, request_id = parse_research_artifact_uri(job.request_ref)
        request_record = store.load_artifact_record(kind, request_id)
        request = ExperimentJobRequest.from_dict(request_record.payload)
        assert json_payload_hash(request.to_dict()) == job.request_digest
        assert request.actor == job.actor == QUANT_RESEARCH_SUPERVISOR_OWNER
        assert request.requested_by == job.requested_by
        assert request.code_identity == job.code_identity
        assert request.environment_identity == job.environment_identity
        assert request_record.producer_tool == "research_submit_approved_experiment_job"
        assert (
            request_record.actor == job.actor
            and request_record.requested_by == job.requested_by
        )
        proposal_record = _load_pinned(store, request.proposal_ref)
        protocol_record = _load_pinned(store, request.approved_protocol_ref)
        proposal = ExperimentProtocolProposal.from_dict(proposal_record.payload)
        protocol = ExperimentProtocol.from_dict(protocol_record.payload)
        assert apply_experiment_protocol_approvals(
            proposal, protocol.approvals
        ).to_dict() == dict(protocol_record.payload)
        for reference in request.input_refs:
            _load_pinned(store, reference)
        assert job.status.value == "succeeded" and len(job.produced_artifact_refs) == 1
        run = _load_pinned(store, job.produced_artifact_refs[0])
        specification, _ = load_passed_backtest_specification(
            store, run.payload["backtest_specification_validation_id"]
        )
        assert (
            specification["backtest_specification_id"]
            == run.payload["backtest_specification_id"]
        )
        assert (
            specification["runtime_limits"]["experiment_job_request_ref"]
            == job.request_ref
        )
        assert (
            specification["runtime_limits"]["experiment_job_request_sha256"]
            == job.request_digest
        )
        dataset = protocol_record.payload["datasets"][0]
        manifest = _load_pinned(
            store, ArtifactReportRef.from_dict(dataset["dataset_manifest_ref"])
        )
        strategy = _load_pinned(
            store,
            ArtifactReportRef.from_dict(
                protocol_record.payload["strategy"]["implementation_ref"]
            ),
        )
        assert run.producer_tool == "research_run_backtest_specification"
        assert run.actor == job.actor and run.requested_by == job.requested_by
        session_record = store.load_artifact_record(
            "research_session", job.requested_by
        )
        assert session_record.payload["operator_id"] == protocol.approvals[0].decided_by
        session_scope = session_record.payload["scope_envelope"]["data_scope"]["items"][
            0
        ]
        assert sorted(session_scope["symbols"]) == sorted(manifest.payload["symbols"])
        assert session_scope["asset_class"] == manifest.payload["asset_class"]
        assert session_scope["timeframe"] == manifest.payload["timeframe"]
        window = manifest.payload["requested_window"]
        for edge in ("start", "end"):
            assert datetime.fromisoformat(
                session_scope[edge].replace("Z", "+00:00")
            ) == datetime.fromisoformat(window[edge].replace("Z", "+00:00"))
        assert run.payload["dataset_id"] == manifest.payload["dataset_id"]
        assert specification["dataset"]["payload"] == normalized_dataset_manifest(
            manifest.payload
        )
        assert run.payload["strategy_implementation_version_id"] == strategy.artifact_id
        assert run.payload["replay_data_identity_validation"]["status"] == "passed"
        terminal = store.load_artifact_record("workflow_outcome", outcome_id)
        outcome = WorkflowOutcome.from_dict(terminal.payload)
        plan = WorkflowPlan.from_dict(
            store.load_artifact("workflow_plan", outcome.plan_id)
        )
        objective = _load_pinned(store, outcome.objective_ref)
        assert json_payload_hash(objective.payload) == proposal.objective_digest
        assert (
            outcome.objective_ref.artifact_id
            == proposal.objective_id
            == plan.objective_ref.artifact_id
        )
        assert outcome.protocol_ref.to_dict() == request.approved_protocol_ref.to_dict()
        assert plan.protocol_ref.artifact_id == protocol_record.artifact_id
        assert outcome.requested_by == plan.requested_by == proposal.requested_by
        assert outcome.workflow_id == job.requested_by
        assert outcome.actor == plan.actor
        assert terminal.producer_tool == "research_record_workflow_outcome"
        assert (
            terminal.actor == plan.actor and terminal.requested_by == job.requested_by
        )
        assert outcome.status.value == "blocked"
        assert {item.details["role"] for item in outcome.blockers} == {
            "evaluation",
            "robustness",
        }
        assert len({item.details["branch_id"] for item in outcome.blockers}) == 2
        for reference in outcome.produced_artifact_refs:
            _load_pinned(store, reference)
        assert tuple(item.uri for item in outcome.produced_artifact_refs) == (run.uri,)
        base = {
            "experiment_id": protocol_record.artifact_id,
            "proposal_id": proposal.proposal_id,
        }
        # Contextual links are derived only after all referenced producer identities are checked.
        records = (
            ("proposal", proposal_record, base),
            ("approval", protocol_record, base),
            ("scope", manifest, {**base, "scope_id": manifest.payload["dataset_id"]}),
            (
                "strategy",
                strategy,
                {**base, "strategy_version_id": strategy.artifact_id},
            ),
            (
                "run",
                run,
                {
                    **base,
                    "scope_id": run.payload["dataset_id"],
                    "strategy_version_id": run.payload[
                        "strategy_implementation_version_id"
                    ],
                    "run_id": run.artifact_id,
                },
            ),
            (
                "decision",
                terminal,
                {
                    **base,
                    "scope_id": run.payload["dataset_id"],
                    "strategy_version_id": strategy.artifact_id,
                    "run_id": run.artifact_id,
                },
            ),
        )
        joined = qualify_evidence_join(
            **base,
            scope_id=run.payload["dataset_id"],
            strategy_version_id=strategy.artifact_id,
            run_id=run.artifact_id,
            evidence_revision=3,
            records=tuple(
                EvidenceJoinRef(
                    role, _pinned_ref(record), 1, EvidenceJoinStatus.AVAILABLE, lineage
                )
                for role, record, lineage in records
            ),
        )
        assert joined.verdict.value == "blocked"
        return {
            "job": job.to_dict(),
            "terminal": outcome.to_dict(),
            "join": joined.to_dict(),
            "request_sha256": job.request_digest,
            "run_sha256": json_payload_hash(run.payload),
            "terminal_sha256": json_payload_hash(terminal.payload),
        }
    finally:
        store.close()


async def review_preflight(dsn: str, role: str, run_ref: ArtifactReportRef) -> Any:
    """Independently discover whether this scope has a registered review producer.

    Only optimisation review producers currently exist. A plain approved
    backtest must therefore retain a typed unavailable-producer blocker, not a
    fabricated report or an unrelated optimisation review invocation.
    """
    from trader_research.governance import ResearchIssue

    expected = {
        "evaluation": "evaluation_review_experiment",
        "robustness": "adversarial_review_experiment",
    }[role]
    async with mcp_client(dsn) as client:
        names = sorted(item.name for item in await client.list_tools())
        observed = await call(
            client,
            "research_read_artifact",
            {
                "artifact_ref": run_ref.uri,
                "expected_artifact_type": "backtest_run",
                "include_payload": False,
            },
        )
        assert observed["ok"] and expected not in names
    return ResearchIssue(
        code="independent_review_producer_unavailable",
        message=f"No registered {role} producer supports this approved single-backtest scope.",
        details={
            "role": role,
            "branch_id": f"workflow-uj08-real:{role}",
            "run_ref": run_ref.to_dict(),
            "required_producer": expected,
            "catalogue_sha256": json_payload_hash({"tools": names}),
        },
    )


def main() -> None:
    """Reverify canonical evidence in a separate Python process."""
    from tests.cross_package.qualification.support.mcp_uj08_server import campaign_dsn

    print(
        json.dumps(
            verify_chain(
                campaign_dsn(), os.environ["UJ08_JOB_ID"], os.environ["UJ08_OUTCOME_ID"]
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
