"""Contracts for typed Postgres projections of ML deployment evidence.

Subject: Deployment and validation schema registration plus pgAdmin-visible typed records.
Level: Schema unit contract plus guarded Postgres adapter integration.
Collaborators: ML deployment services, deterministic adapter fixture, and Postgres artifact store.
Guarantees: Registered projection writers persist exact deployment and validation fields.
Non-goals: Provider model loading, strategy bindings, training, inference latency, or agent decisions.
"""

from __future__ import annotations

import pytest

from tests.trader_research.ml.deployment_fixtures import (
    FixtureAdapter,
    _create,
    _seed_upstream,
)
from trader_research.governance.artifacts import (
    ML_DEPLOYMENT_MANIFEST,
    ML_DEPLOYMENT_VALIDATION_REPORT,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from trader_research.ml import InferenceAdapterRegistry, validate_deployment


@pytest.mark.postgres
def test_ml_deployments_have_pgadmin_visible_typed_projections(
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
    """Passed ML deployment evidence populates typed Postgres deployment and validation rows."""
    store = postgres_research_artifact_store
    _seed_upstream(store)
    created = _create(store)
    deployment_id = created.data["ml_deployment_manifest"]["deployment_id"]
    validated = validate_deployment(
        deployment_id=str(deployment_id),
        artifact_store=store,
        adapter_registry=InferenceAdapterRegistry((FixtureAdapter(),)),
    )
    validation_id = validated.data["ml_deployment_validation_report"]["validation_id"]

    deployment = (
        store.connection()
        .execute(
            """
        SELECT model_version_id, feature_set_id, adapter_profile, inference_scope,
               decision_scope, eligibility, status
        FROM research_ml_deployments WHERE deployment_id = %s
        """,
            [deployment_id],
        )
        .fetchone()
    )
    validation = (
        store.connection()
        .execute(
            """
        SELECT deployment_id, status, valid, adapter_status
        FROM research_ml_deployment_validations WHERE validation_id = %s
        """,
            [validation_id],
        )
        .fetchone()
    )

    assert deployment == {
        "model_version_id": "ml_model_version_1",
        "feature_set_id": "ml_feature_set_1",
        "adapter_profile": "fixture_local",
        "inference_scope": "per_symbol",
        "decision_scope": "per_symbol",
        "eligibility": ["backtest", "paper"],
        "status": "created",
    }
    assert validation == {
        "deployment_id": deployment_id,
        "status": "passed",
        "valid": True,
        "adapter_status": "passed",
    }


def test_ml_projection_schema_and_registry_are_registered() -> None:
    """ML projection tables and artifact writers are present in the default schema registry."""
    from trader_research.infrastructure.postgres import (
        RESEARCH_ARTIFACT_SCHEMA_STATEMENTS,
    )
    from trader_research.infrastructure.postgres.projections import (
        default_projection_registry,
    )

    schema = "\n".join(RESEARCH_ARTIFACT_SCHEMA_STATEMENTS)
    assert "CREATE TABLE IF NOT EXISTS research_ml_deployments" in schema
    assert "CREATE TABLE IF NOT EXISTS research_ml_deployment_validations" in schema
    assert ML_DEPLOYMENT_MANIFEST in default_projection_registry().writers
    assert ML_DEPLOYMENT_VALIDATION_REPORT in default_projection_registry().writers
