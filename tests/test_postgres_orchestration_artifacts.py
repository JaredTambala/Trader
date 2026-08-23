"""Postgres projections for canonical orchestration governance records."""

from __future__ import annotations

import pytest

from trader_research.foundation import (
    EXPERIMENTS_DOMAIN_OWNER,
    ORCHESTRATION_DOMAIN_OWNER,
)
from trader_research.governance.artifacts import (
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    RESEARCH_OBJECTIVE,
    WORKFLOW_OUTCOME,
    WORKFLOW_PLAN,
)
from trader_research.infrastructure.postgres import (
    RESEARCH_ARTIFACT_SCHEMA_STATEMENTS,
    PostgresResearchArtifactStore,
)


def test_research_schema_exposes_orchestration_records_to_pgadmin() -> None:
    schema = "\n".join(RESEARCH_ARTIFACT_SCHEMA_STATEMENTS)
    for table in (
        "research_objectives",
        "research_experiment_protocol_proposals",
        "research_experiment_protocols",
        "research_workflow_plans",
        "research_workflow_outcomes",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema


@pytest.mark.postgres
def test_orchestration_artifacts_have_typed_postgres_projections(
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
    store = postgres_research_artifact_store
    store.save_artifact(
        artifact_type=RESEARCH_OBJECTIVE,
        artifact_id="objective_1",
        domain_owner=ORCHESTRATION_DOMAIN_OWNER,
        producer_tool="research_register_experiment_workflow",
        requested_by="workflow_1",
        actor="workflow_executor",
        status="approved",
        payload={
            "artifact_type": RESEARCH_OBJECTIVE,
            "objective_id": "objective_1",
            "statement": "Evaluate supplied code.",
            "success_criteria": ["Produce evidence."],
            "constraints": [],
            "supplied_artifact_refs": [],
            "requested_by": "operator_1",
            "actor": "operator",
            "status": "approved",
        },
    )
    store.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL_PROPOSAL,
        artifact_id="proposal_1",
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="research_create_experiment_protocol_proposal",
        requested_by="composition_1",
        actor="Experiment Design Agent",
        status="proposed",
        payload={
            "artifact_type": EXPERIMENT_PROTOCOL_PROPOSAL,
            "proposal_id": "proposal_1",
            "protocol": {"protocol_id": "protocol_1"},
            "objective_id": "objective_1",
            "task_id": "design_task_1",
            "design_digest": "design_digest_1",
            "requested_by": "composition_1",
            "proposed_by": "Experiment Design Agent",
            "status": "proposed",
        },
    )
    store.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL,
        artifact_id="protocol_1",
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="research_register_experiment_workflow",
        requested_by="workflow_1",
        actor="workflow_executor",
        status="approved",
        payload={
            "artifact_type": EXPERIMENT_PROTOCOL,
            "protocol_id": "protocol_1",
            "objective_id": "objective_1",
            "requested_by": "objective_1",
            "proposed_by": "experiment_design_agent",
            "status": "approved",
        },
    )
    store.save_artifact(
        artifact_type=WORKFLOW_PLAN,
        artifact_id="plan_1",
        domain_owner=ORCHESTRATION_DOMAIN_OWNER,
        producer_tool="research_register_experiment_workflow",
        requested_by="workflow_1",
        actor="workflow_executor",
        status="ready",
        payload={
            "artifact_type": WORKFLOW_PLAN,
            "plan_id": "plan_1",
            "objective_ref": {"artifact_id": "objective_1"},
            "protocol_ref": {"artifact_id": "protocol_1"},
            "template_id": "supplied_implementation_to_evidence",
            "template_version": "1",
            "requested_by": "objective_1",
            "actor": "research_coordinator",
            "status": "ready",
        },
    )
    store.save_artifact(
        artifact_type=WORKFLOW_OUTCOME,
        artifact_id="outcome_1",
        domain_owner=ORCHESTRATION_DOMAIN_OWNER,
        producer_tool="research_record_workflow_outcome",
        requested_by="workflow_1",
        actor="workflow_executor",
        status="completed",
        payload={
            "artifact_type": WORKFLOW_OUTCOME,
            "outcome_id": "outcome_1",
            "workflow_id": "workflow_1",
            "plan_id": "plan_1",
            "status": "completed",
            "review_verdict_refs": [{"uri": "research://postgres/review/r1"}],
            "requested_by": "objective_1",
            "actor": "research_coordinator",
        },
    )

    plan = store.connection().execute(
        """
        SELECT objective_id, protocol_id, template_id, status
        FROM research_workflow_plans
        WHERE plan_id = %s
        """,
        ["plan_1"],
    ).fetchone()
    proposal = store.connection().execute(
        """
        SELECT protocol_id, objective_id, task_id, design_digest, status
        FROM research_experiment_protocol_proposals
        WHERE proposal_id = %s
        """,
        ["proposal_1"],
    ).fetchone()
    outcome = store.connection().execute(
        """
        SELECT workflow_id, plan_id, status, review_ref_count
        FROM research_workflow_outcomes
        WHERE outcome_id = %s
        """,
        ["outcome_1"],
    ).fetchone()
    authority = store.connection().execute(
        """
        SELECT domain_owner, producer_tool, requested_by, actor
        FROM research_artifacts
        WHERE artifact_type = %s AND artifact_id = %s
        """,
        [WORKFLOW_OUTCOME, "outcome_1"],
    ).fetchone()

    assert plan == {
        "objective_id": "objective_1",
        "protocol_id": "protocol_1",
        "template_id": "supplied_implementation_to_evidence",
        "status": "ready",
    }
    assert proposal == {
        "protocol_id": "protocol_1",
        "objective_id": "objective_1",
        "task_id": "design_task_1",
        "design_digest": "design_digest_1",
        "status": "proposed",
    }
    assert outcome == {
        "workflow_id": "workflow_1",
        "plan_id": "plan_1",
        "status": "completed",
        "review_ref_count": 1,
    }
    assert authority == {
        "domain_owner": "Orchestration",
        "producer_tool": "research_record_workflow_outcome",
        "requested_by": "workflow_1",
        "actor": "workflow_executor",
    }
