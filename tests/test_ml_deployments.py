"""Tests for immutable ML deployment manifests and validation evidence."""

from __future__ import annotations

from typing import Mapping

import pytest

from trader.predictions import Predictor
from trader_research.foundation.artifacts import (
    InMemoryResearchArtifactStore,
    ResearchArtifactStore,
)
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    ML_DEPLOYMENT_MANIFEST,
    ML_DEPLOYMENT_VALIDATION_REPORT,
    ML_FEATURE_SET_SPEC,
    ML_FEATURE_SET_VALIDATION_REPORT,
    ML_MODEL_VERSION_REF,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from trader_research.ml import (
    ArtifactPredictionDeploymentReader,
    InferenceAdapterProfile,
    InferenceAdapterRegistry,
    create_deployment_manifest,
    validate_deployment,
)


class FixtureAdapter:
    """Deterministic adapter that proves the supplied parity fixture."""

    def __init__(self, *, available: bool = True) -> None:
        self._profile = InferenceAdapterProfile(
            profile_name="fixture_local",
            provider="fixture",
            adapter_version="1",
            configuration_digest="sha256:fixture-config",
            capabilities=("local_model", "python_function", "scalar_outputs"),
            available=available,
            reason=None if available else "fixture provider is unavailable",
        )

    def profile(self) -> InferenceAdapterProfile:
        return self._profile

    def validate_deployment(self, manifest: Mapping[str, object]) -> Mapping[str, object]:
        fixture = dict(manifest["parity_fixture"])  # type: ignore[arg-type]
        return {
            "status": "passed",
            "expected_outputs_digest": fixture["expected_outputs_digest"],
            "actual_outputs_digest": fixture["expected_outputs_digest"],
            "latency_ms": 1.5,
        }

    def build_predictor(self, manifest: Mapping[str, object]) -> Predictor:
        del manifest
        raise NotImplementedError


def _seed_upstream(store: ResearchArtifactStore) -> None:
    model = {
        "artifact_type": ML_MODEL_VERSION_REF,
        "model_version_id": "ml_model_version_1",
        "registered_model_name": "fx_return_model",
        "model_version": "7",
        "model_digest": "sha256:model",
        "signature_digest": "sha256:signature",
        "source_run_id": "mlflow_run_1",
        "model_uri": "models:/fx_return_model/7",
        "status": "registered",
        "immutable": True,
    }
    feature_set = {
        "artifact_type": ML_FEATURE_SET_SPEC,
        "feature_set_id": "ml_feature_set_1",
        "feature_set_digest": "sha256:features",
        "status": "created",
        "schema": [{"name": "return_1", "dtype": "float64", "nullable": False}],
    }
    validation = {
        "artifact_type": ML_FEATURE_SET_VALIDATION_REPORT,
        "validation_id": "ml_feature_set_validation_1",
        "feature_set_id": "ml_feature_set_1",
        "feature_set_digest": "sha256:features",
        "status": "passed",
        "valid": True,
        "blockers": [],
    }
    for artifact_type, artifact_id, payload, status in (
        (ML_MODEL_VERSION_REF, "ml_model_version_1", model, "registered"),
        (ML_FEATURE_SET_SPEC, "ml_feature_set_1", feature_set, "created"),
        (
            ML_FEATURE_SET_VALIDATION_REPORT,
            "ml_feature_set_validation_1",
            validation,
            "passed",
        ),
    ):
        store.save_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
            producer_tool="test_ml_deployment_fixture",
            payload=payload,
            status=status,
        )


def _create(
    store: ResearchArtifactStore,
    *,
    adapter: FixtureAdapter | None = None,
    environment: Mapping[str, object] | None = None,
):
    registry = InferenceAdapterRegistry((adapter or FixtureAdapter(),))
    return create_deployment_manifest(
        model_version_ref="ml_model_version_1",
        feature_set_validation_ref="ml_feature_set_validation_1",
        adapter_profile="fixture_local",
        output_contract=(
            {
                "name": "expected_return",
                "semantics": "expected_return",
                "horizon": "1h",
                "units": "return",
            },
        ),
        inference_scope="per_symbol",
        inference_policy={"timeout_ms": 500, "failure_action": "fail_closed"},
        environment=environment or {"python": "3.12", "environment_digest": "sha256:env"},
        parity_fixture={
            "decision_ts": "2026-07-22T12:00:00+00:00",
            "rows": [
                {
                    "symbol": "EURUSD",
                    "as_of_ts": "2026-07-22T12:00:00+00:00",
                    "availability_ts": "2026-07-22T12:00:00+00:00",
                    "values": {"return_1": 0.01},
                }
            ],
            "expected_outputs": [
                {
                    "symbol": "EURUSD",
                    "output_name": "expected_return",
                    "semantics": "expected_return",
                    "horizon": "1h",
                    "value": 0.02,
                }
            ],
        },
        eligibility=("backtest", "paper"),
        artifact_store=store,
        adapter_registry=registry,
    )


def test_deployment_manifest_and_validation_are_deterministic_and_loadable() -> None:
    store = InMemoryResearchArtifactStore()
    _seed_upstream(store)
    first = _create(store)
    second = _create(store)

    assert first.ok and second.ok
    manifest = first.data["ml_deployment_manifest"]
    assert manifest["deployment_id"] == second.data["ml_deployment_manifest"]["deployment_id"]
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
    resolved = ArtifactPredictionDeploymentReader(store).resolve_passed(str(report["validation_id"]))
    assert resolved["model_version_id"] == "ml_model_version_1"
    assert resolved["feature_set_id"] == "ml_feature_set_1"


def test_deployment_validation_blocks_unavailable_adapter_and_upstream_drift() -> None:
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
    assert "snapshot drifted" in drifted.data["ml_deployment_validation_report"]["blockers"][0]


def test_deployment_creation_rejects_provider_locations_and_mutable_aliases() -> None:
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
    assert "pin the declared immutable registry version" in mutable_uri.errors[0]["message"]


def test_deployment_services_fail_closed_without_required_stores_or_registry() -> None:
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


@pytest.mark.postgres
def test_ml_deployments_have_pgadmin_visible_typed_projections(
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
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

    deployment = store.connection().execute(
        """
        SELECT model_version_id, feature_set_id, adapter_profile, inference_scope,
               decision_scope, eligibility, status
        FROM research_ml_deployments WHERE deployment_id = %s
        """,
        [deployment_id],
    ).fetchone()
    validation = store.connection().execute(
        """
        SELECT deployment_id, status, valid, adapter_status
        FROM research_ml_deployment_validations WHERE validation_id = %s
        """,
        [validation_id],
    ).fetchone()

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
    from trader_research.infrastructure.postgres import RESEARCH_ARTIFACT_SCHEMA_STATEMENTS
    from trader_research.infrastructure.postgres.projections import default_projection_registry

    schema = "\n".join(RESEARCH_ARTIFACT_SCHEMA_STATEMENTS)
    assert "CREATE TABLE IF NOT EXISTS research_ml_deployments" in schema
    assert "CREATE TABLE IF NOT EXISTS research_ml_deployment_validations" in schema
    assert ML_DEPLOYMENT_MANIFEST in default_projection_registry().writers
    assert ML_DEPLOYMENT_VALIDATION_REPORT in default_projection_registry().writers
