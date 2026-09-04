"""Unit contracts for canonical research artifact records and contextual stores.

Subject: Foundation artifact identity, authority provenance, and workflow-bound write attribution.
Level: In-process unit contract.
Collaborators: Real foundation records and the in-memory artifact store; no database or transport.
Guarantees: Artifact writes retain explicit authority and reject unsupported or conflicting provenance.
Non-goals: Business artifact ownership maps, Postgres projections, durable recovery, or agent decisions.
"""

from __future__ import annotations

import pytest

from trader_research.foundation.artifacts import (
    ContextualResearchArtifactStore,
    InMemoryResearchArtifactStore,
    ResearchArtifactStoreError,
    build_artifact_record,
)
from trader_research.governance.artifacts import EXPERIMENTS_DOMAIN_OWNER


def test_artifact_record_exposes_authority_and_producer_provenance() -> None:
    """A built record exposes each authority dimension without conflating its producer."""
    record = build_artifact_record(
        artifact_type="demo_artifact",
        artifact_id="demo_1",
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="research_demo",
        requested_by="workflow_run_1",
        actor="Research Coordinator",
        payload={"status": "passed"},
    )

    assert record.domain_owner == "Experiments"
    assert record.producer_tool == "research_demo"
    assert record.requested_by == "workflow_run_1"
    assert record.actor == "Research Coordinator"
    assert record.reference().metadata["domain_owner"] == "Experiments"


def test_artifact_record_rejects_unknown_domain_authority() -> None:
    """An unsupported domain owner cannot enter the canonical artifact boundary."""
    with pytest.raises(
        ResearchArtifactStoreError,
        match="unsupported research artifact domain_owner",
    ):
        build_artifact_record(
            artifact_type="demo_artifact",
            artifact_id="demo_1",
            domain_owner="Quant Research Supervisor Agent",
            producer_tool="research_demo",
            payload={"status": "passed"},
        )


def test_contextual_artifact_store_applies_and_enforces_workflow_provenance() -> None:
    """A contextual store supplies workflow provenance and rejects conflicting caller attribution."""
    underlying = InMemoryResearchArtifactStore()
    store = ContextualResearchArtifactStore(
        underlying,
        requested_by="workflow_1",
        actor="workflow_executor",
    )

    record = store.save_artifact(
        artifact_type="demo_artifact",
        artifact_id="demo_1",
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="research_demo",
        payload={"status": "passed"},
    )

    assert record.requested_by == "workflow_1"
    assert record.actor == "workflow_executor"
    with pytest.raises(
        ResearchArtifactStoreError,
        match="conflicts with the active workflow context",
    ):
        store.save_artifact(
            artifact_type="demo_artifact",
            artifact_id="demo_2",
            domain_owner=EXPERIMENTS_DOMAIN_OWNER,
            producer_tool="research_demo",
            requested_by="another_workflow",
            payload={"status": "passed"},
        )
