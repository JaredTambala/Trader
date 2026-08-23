from __future__ import annotations

from typing import Any

import pytest

from trader_research.foundation.artifacts import (
    ContextualResearchArtifactStore,
    InMemoryResearchArtifactStore,
    ResearchArtifactStoreError,
    build_artifact_record,
)
from trader_research.governance.artifacts import EXPERIMENTS_DOMAIN_OWNER
from trader_research.infrastructure.postgres.projections import (
    combine_projection_writers,
    default_projection_registry,
)


def _record(artifact_type: str = "demo_artifact"):
    return build_artifact_record(
        artifact_type=artifact_type,
        artifact_id="demo_1",
        domain_owner=EXPERIMENTS_DOMAIN_OWNER,
        producer_tool="test_projection_fixture",
        payload={"status": "passed"},
    )


def test_artifact_record_exposes_authority_and_producer_provenance() -> None:
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


def test_projection_registry_dispatches_only_registered_artifact_type() -> None:
    calls: list[tuple[Any, str, Any]] = []

    def writer(connection: Any, record: Any, json_value: Any) -> None:
        calls.append((connection, record.artifact_id, json_value))

    registry = combine_projection_writers({"demo_artifact": writer})
    connection = object()

    def json_value(value: Any) -> Any:
        return value

    registry.write(connection, _record(), json_value=json_value)
    registry.write(
        connection,
        _record("canonical_only_artifact"),
        json_value=json_value,
    )

    assert calls == [(connection, "demo_1", json_value)]


def test_projection_registry_rejects_duplicate_context_ownership() -> None:
    def writer(connection: Any, record: Any, json_value: Any) -> None:
        del connection, record, json_value

    with pytest.raises(ValueError, match="duplicate projection writers: demo_artifact"):
        combine_projection_writers(
            {"demo_artifact": writer},
            {"demo_artifact": writer},
        )


def test_default_projection_registry_is_partitioned_by_context() -> None:
    projected = set(default_projection_registry().writers)

    assert "methodology_candidate" in projected
    assert "implementation_version" in projected
    assert "backtest_run" in projected
    assert "parameter_optimization_evaluation_report" in projected
    assert "parameter_optimization_robustness_report" in projected
    assert "research_objective" in projected
    assert "experiment_protocol" in projected
    assert "experiment_protocol_proposal" in projected
    assert "workflow_plan" in projected
    assert "workflow_outcome" in projected
