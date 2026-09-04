"""Reusable canonical fixtures for ML deployment contract tests.

The builders seed immutable model and feature evidence and expose a deterministic
provider-neutral adapter without importing a concrete MLflow implementation.
"""

from __future__ import annotations

from typing import Mapping

from trader.predictions import InferenceAdapterProfile, Predictor
from trader_research.foundation.artifacts import ResearchArtifactStore
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    ML_FEATURE_SET_SPEC,
    ML_FEATURE_SET_VALIDATION_REPORT,
    ML_MODEL_VERSION_REF,
)
from trader_research.ml import (
    InferenceAdapterRegistry,
    create_deployment_manifest,
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

    def validate_deployment(
        self, manifest: Mapping[str, object]
    ) -> Mapping[str, object]:
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
        environment=environment
        or {"python": "3.12", "environment_digest": "sha256:env"},
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
