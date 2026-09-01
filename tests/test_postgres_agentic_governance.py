"""Postgres projections for model-backed agent session evidence."""

from __future__ import annotations

import pytest

from trader_research.governance import (
    AgentBudget,
    AgentBudgetUsage,
    AgentDecisionStatus,
    ResearchIssue,
    ResearchSession,
    build_agent_decision_receipt,
    create_agent_session,
    record_agent_decision,
)
from trader_research.infrastructure.postgres import (
    RESEARCH_ARTIFACT_SCHEMA_STATEMENTS,
    PostgresResearchArtifactStore,
)


def test_research_schema_exposes_agentic_records_to_pgadmin() -> None:
    schema = "\n".join(RESEARCH_ARTIFACT_SCHEMA_STATEMENTS)

    assert "CREATE TABLE IF NOT EXISTS research_agent_sessions" in schema
    assert "CREATE TABLE IF NOT EXISTS research_agent_decision_receipts" in schema


@pytest.mark.postgres
def test_agentic_session_and_receipt_have_typed_postgres_projections(
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
    store = postgres_research_artifact_store
    session = ResearchSession(
        session_id="session-postgres-demo",
        objective="Prepare research inputs.",
        success_definition="Return canonical evidence.",
        operator_id="operator-demo",
        approval_policy={"broker_mutation": False},
        scope_envelope={"symbols": ["AAA"]},
        implementation_specification={"implementation_kind": "strategy"},
        implementation_ref=None,
        python_quality_guide="docs/python_code_quality.md",
        model_profile_id="model-v1",
        agent_program_ids=("coordinator-v1",),
        tool_catalog_id="catalog-v1",
        budget=AgentBudget(4, 8, 4_000, 120, 1, 1, 1),
    )
    receipt = build_agent_decision_receipt(
        session_id=session.session_id,
        branch_id="branch-main",
        sequence=1,
        actor="Research Coordinator",
        program_id="coordinator-v1",
        model_profile_id=session.model_profile_id,
        action="ask_operator",
        status=AgentDecisionStatus.AWAITING_OPERATOR,
        summary="One material behavior is missing.",
        blockers=(
            ResearchIssue(
                code="missing_material_rule",
                message="The exit rule requires operator clarification.",
            ),
        ),
        budget_used=AgentBudgetUsage(model_calls=1, tokens=80),
    )

    session_result = create_agent_session(session.to_dict(), artifact_store=store)
    receipt_result = record_agent_decision(receipt.to_dict(), artifact_store=store)
    session_row = store.connection().execute(
        "SELECT * FROM research_agent_sessions WHERE session_id = %s",
        [session.session_id],
    ).fetchone()
    receipt_row = store.connection().execute(
        "SELECT * FROM research_agent_decision_receipts WHERE receipt_id = %s",
        [receipt.receipt_id],
    ).fetchone()

    assert session_result.ok is True
    assert receipt_result.ok is True
    assert session_row["model_profile_id"] == session.model_profile_id
    assert receipt_row["branch_id"] == "branch-main"
    assert receipt_row["decision_digest"] == receipt.decision_digest
