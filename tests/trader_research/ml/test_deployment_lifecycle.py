"""Contracts for immutable ML deployment creation and validation.

Subject: Deployment identity, adapter parity, immutable upstream pins, environment safety, and lookup.
Level: Offline ML application contract.
Collaborators: In-memory canonical artifacts and a deterministic provider-neutral adapter double.
Guarantees: Deployments are stable, loadable, and reject unavailable, mutable, or drifted dependencies.
Non-goals: Strategy prediction bindings, concrete MLflow loading, Postgres projections, or training.
"""

from __future__ import annotations

from tests.trader_research.ml.deployment_fixtures import (
    FixtureAdapter,
    _create,
    _seed_upstream,
)
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    ML_MODEL_VERSION_REF,
)
from trader_research.ml import (
    ArtifactPredictionDeploymentReader,
    InferenceAdapterRegistry,
    create_deployment_manifest,
    validate_deployment,
)


def test_deployment_manifest_and_validation_are_deterministic_and_loadable() -> None:
    """Repeated creation yields one deployment whose passed validation resolves exact model evidence."""
    store = InMemoryResearchArtifactStore()
    _seed_upstream(store)
    first = _create(store)
    second = _create(store)

    assert first.ok and second.ok
    manifest = first.data["ml_deployment_manifest"]
    assert (
        manifest["deployment_id"]
        == second.data["ml_deployment_manifest"]["deployment_id"]
    )
    assert manifest["decision_scope"] == "per_symbol"
    assert "threshold" not in manifest
    assert manifest["policy"]["live_trading_allowed"] is False

    registry = InferenceAdapterRegistry((FixtureAdapter(),))
    validation = validate_deployment(
        deployment_id=str(manifest["deployment_id"]),
        artifact_store=store,
        adapter_registry=registry,
    )

    assert validation.ok
    report = validation.data["ml_deployment_validation_report"]
    assert report["status"] == "passed"
    resolved = ArtifactPredictionDeploymentReader(store).resolve_passed(
        str(report["validation_id"])
    )
    assert resolved["model_version_id"] == "ml_model_version_1"
    assert resolved["feature_set_id"] == "ml_feature_set_1"


def test_deployment_validation_blocks_unavailable_adapter_and_upstream_drift() -> None:
    """Validation blocks unavailable adapters and changes to pinned upstream model content."""
    store = InMemoryResearchArtifactStore()
    _seed_upstream(store)
    created = _create(store)
    deployment_id = created.data["ml_deployment_manifest"]["deployment_id"]

    unavailable = validate_deployment(
        deployment_id=str(deployment_id),
        artifact_store=store,
        adapter_registry=InferenceAdapterRegistry((FixtureAdapter(available=False),)),
    )
    assert not unavailable.ok
    assert unavailable.data["ml_deployment_validation_report"]["status"] == "blocked"

    model = dict(store.load_artifact(ML_MODEL_VERSION_REF, "ml_model_version_1"))
    model["model_digest"] = "sha256:changed"
    store.save_artifact(
        artifact_type=ML_MODEL_VERSION_REF,
        artifact_id="ml_model_version_1",
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[ML_MODEL_VERSION_REF],
        producer_tool="test_ml_deployment_fixture",
        payload=model,
        status="registered",
    )
    drifted = validate_deployment(
        deployment_id=str(deployment_id),
        artifact_store=store,
        adapter_registry=InferenceAdapterRegistry((FixtureAdapter(available=False),)),
    )
    assert not drifted.ok
    assert (
        "snapshot drifted"
        in drifted.data["ml_deployment_validation_report"]["blockers"][0]
    )


def test_deployment_creation_rejects_provider_locations_and_mutable_aliases() -> None:
    """Deployment creation rejects secret provider locations and mutable registry aliases."""
    store = InMemoryResearchArtifactStore()
    _seed_upstream(store)

    location = _create(store, environment={"tracking_uri": "postgresql://secret"})
    assert not location.ok
    assert location.errors[0]["code"] == "ml_deployment_creation_failed"

    model = dict(store.load_artifact(ML_MODEL_VERSION_REF, "ml_model_version_1"))
    model.update({"resolved_alias": "champion", "immutable": False})
    store.save_artifact(
        artifact_type=ML_MODEL_VERSION_REF,
        artifact_id="ml_model_version_1",
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[ML_MODEL_VERSION_REF],
        producer_tool="test_ml_deployment_fixture",
        payload=model,
        status="registered",
    )
    alias = _create(store)
    assert not alias.ok
    assert "resolved and immutable" in alias.errors[0]["message"]

    model.update(
        {
            "model_uri": "models:/fx_return_model@champion",
            "immutable": True,
        }
    )
    store.save_artifact(
        artifact_type=ML_MODEL_VERSION_REF,
        artifact_id="ml_model_version_1",
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[ML_MODEL_VERSION_REF],
        producer_tool="test_ml_deployment_fixture",
        payload=model,
        status="registered",
    )
    mutable_uri = _create(store)
    assert not mutable_uri.ok
    assert (
        "pin the declared immutable registry version"
        in mutable_uri.errors[0]["message"]
    )


def test_deployment_services_fail_closed_without_required_stores_or_registry() -> None:
    """Deployment services require canonical artifact storage and an explicit adapter registry."""
    missing_store = create_deployment_manifest(
        model_version_ref="model",
        feature_set_validation_ref="features",
        adapter_profile="fixture",
        output_contract=(),
        inference_scope="per_symbol",
    )
    assert not missing_store.ok
    assert missing_store.errors[0]["code"] == "research_artifact_store_required"

    store = InMemoryResearchArtifactStore()
    _seed_upstream(store)
    missing_registry = create_deployment_manifest(
        model_version_ref="model",
        feature_set_validation_ref="features",
        adapter_profile="fixture",
        output_contract=(),
        inference_scope="per_symbol",
        artifact_store=store,
    )
    assert not missing_registry.ok
    assert missing_registry.errors[0]["code"] == "inference_adapter_registry_required"


def test_inline_deployment_validation_requires_matching_persisted_content() -> None:
    """Inline validation rejects deployment content that differs from the canonical record."""
    store = InMemoryResearchArtifactStore()
    _seed_upstream(store)
    created = _create(store)
    manifest = dict(created.data["ml_deployment_manifest"])
    manifest["environment"] = {"environment_digest": "sha256:tampered"}

    result = validate_deployment(
        deployment_manifest=manifest,
        artifact_store=store,
        adapter_registry=InferenceAdapterRegistry((FixtureAdapter(),)),
    )
    assert not result.ok
    assert "does not match persisted canonical content" in result.errors[0]["message"]
