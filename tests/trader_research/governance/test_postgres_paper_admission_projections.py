"""Contracts for the typed Postgres paper-admission projection.

Subject: Schema registration and projection fields for human paper admission.
Level: Offline schema contract plus guarded adapter integration.
Collaborators: Real Postgres artifact store and governance admission service.
Guarantees: Canonical admission writes expose stable query fields atomically.
Non-goals: Broker operation, Console commands, or agent-model behavior.
"""

from __future__ import annotations

import pytest
from trader_research.governance import create_paper_candidate_admission
from trader_research.infrastructure.postgres import (
    RESEARCH_ARTIFACT_SCHEMA_STATEMENTS,
    PostgresResearchArtifactStore,
)
from trader_research.infrastructure.postgres.projections import default_projection_registry

from tests.trader_research.governance.test_paper_admission import (
    _admission_payload,
    _seed_evidence,
)


def test_paper_admission_schema_and_projection_are_registered() -> None:
    """The schema and default registry expose the human admission record."""
    schema = "\n".join(RESEARCH_ARTIFACT_SCHEMA_STATEMENTS)
    assert "CREATE TABLE IF NOT EXISTS research_paper_candidate_admissions" in schema
    from trader_research.governance.artifacts import PAPER_CANDIDATE_ADMISSION

    assert PAPER_CANDIDATE_ADMISSION in default_projection_registry().writers


@pytest.mark.postgres
def test_paper_admission_projection_retains_typed_fields(
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
    """A persisted admission is queryable through typed Postgres columns."""
    store = postgres_research_artifact_store
    _seed_evidence(store)
    payload = _admission_payload()
    result = create_paper_candidate_admission(
        payload,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    )
    assert result.ok is True
    row = (
        store.connection()
        .execute(
            """
            SELECT candidate_ref, strategy_version, risk_version, data_version,
                   decision, approver, expires_at, status
            FROM research_paper_candidate_admissions
            WHERE admission_id = %s
            """,
            [payload["admission_id"]],
        )
        .fetchone()
    )
    assert row["candidate_ref"] == "strategy-candidate-1"
    assert row["strategy_version"] == "strategy-v1"
    assert row["risk_version"] == "risk-v1"
    assert row["data_version"] == "dataset-v1"
    assert row["decision"] == "approved"
    assert row["approver"] == "human:jared"
    assert row["status"] == "approved"
