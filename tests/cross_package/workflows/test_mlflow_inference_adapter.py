"""Cross-package adapter verification of research deployment parity through MLflow.

Subject: Composition of research deployment validation with the optional MLflow adapter.
Level: Adapter integration.
Collaborators: Real local MLflow and pandas runtimes with an in-memory research artifact store.
Guarantees: A pinned pyfunc model satisfies the research-owned parity fixture through the adapter seam.
Non-goals: Exhaustive predictor normalization, remote tracking servers, training, or strategy execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import warnings

import pytest

from trader_mlflow import MLflowLocalPyfuncAdapter
from trader_research.foundation import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    ML_FEATURE_SET_SPEC,
    ML_FEATURE_SET_VALIDATION_REPORT,
    ML_MODEL_VERSION_REF,
)
from trader_research.ml import (
    InferenceAdapterRegistry,
    create_deployment_manifest,
    validate_deployment,
)


NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


@pytest.mark.skipif(
    importlib.util.find_spec("mlflow") is None,
    reason="optional mlflow extra is not installed",
)
def test_local_mlflow_pyfunc_deployment_passes_real_parity_fixture(
    tmp_path: Path,
) -> None:
    """Prove research deployment validation accepts matching real MLflow outputs."""
    import mlflow
    import pandas as pd

    # MLflow 3.14 emits this warning while deriving its own Responses schema.
    # It is unrelated to the pyfunc model exercised by this integration test.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*Any type hint is inferred as AnyType.*",
            category=UserWarning,
        )
        from mlflow.pyfunc import PythonModel

    class _ReturnModel(PythonModel):
        def predict(self, context, model_input, params=None):  # type: ignore[no-untyped-def]
            del context, params
            return pd.DataFrame({"alpha": model_input["return_1"] * 2.0})

    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    mlflow.set_tracking_uri(tracking_uri)
    experiment_name = "prediction-adapter-qualification"
    mlflow.create_experiment(
        experiment_name,
        artifact_location=(tmp_path / "artifacts").as_uri(),
    )
    mlflow.set_experiment(experiment_name)
    with mlflow.start_run() as run:
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=_ReturnModel(),
            input_example=pd.DataFrame({"return_1": [0.01]}),
        )
        model_uri = f"runs:/{run.info.run_id}/model"

    store = InMemoryResearchArtifactStore()
    artifacts = (
        (
            ML_MODEL_VERSION_REF,
            "model_version_1",
            "registered",
            {
                "artifact_type": ML_MODEL_VERSION_REF,
                "model_version_id": "model_version_1",
                "registered_model_name": "returns",
                "model_version": "1",
                "model_digest": "sha256:model",
                "signature_digest": "sha256:signature",
                "source_run_id": run.info.run_id,
                "model_uri": model_uri,
                "status": "registered",
                "immutable": True,
            },
        ),
        (
            ML_FEATURE_SET_SPEC,
            "feature_set_1",
            "created",
            {
                "artifact_type": ML_FEATURE_SET_SPEC,
                "feature_set_id": "feature_set_1",
                "feature_set_digest": "sha256:features",
                "status": "created",
                "schema": [
                    {"name": "return_1", "dtype": "float64", "nullable": False}
                ],
            },
        ),
        (
            ML_FEATURE_SET_VALIDATION_REPORT,
            "feature_validation_1",
            "passed",
            {
                "artifact_type": ML_FEATURE_SET_VALIDATION_REPORT,
                "validation_id": "feature_validation_1",
                "feature_set_id": "feature_set_1",
                "feature_set_digest": "sha256:features",
                "status": "passed",
                "valid": True,
                "blockers": [],
            },
        ),
    )
    for artifact_type, artifact_id, status, payload in artifacts:
        store.save_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
            producer_tool="test_mlflow_inference_fixture",
            payload=payload,
            status=status,
        )

    adapter = MLflowLocalPyfuncAdapter(
        profile_name="mlflow_local_pyfunc", tracking_uri=tracking_uri
    )
    registry = InferenceAdapterRegistry((adapter,))
    created = create_deployment_manifest(
        model_version_ref="model_version_1",
        feature_set_validation_ref="feature_validation_1",
        adapter_profile="mlflow_local_pyfunc",
        output_contract=(
            {
                "name": "alpha",
                "semantics": "expected_return",
                "horizon": "1bar",
                "shape": "scalar",
                "units": "return",
            },
        ),
        inference_scope="per_symbol",
        environment={"environment_digest": "sha256:test"},
        parity_fixture={
            "decision_ts": NOW.isoformat(),
            "rows": [
                {
                    "symbol": "EURUSD",
                    "as_of_ts": NOW.isoformat(),
                    "availability_ts": NOW.isoformat(),
                    "values": {"return_1": 0.01},
                }
            ],
            "expected_outputs": [
                {
                    "symbol": "EURUSD",
                    "output_name": "alpha",
                    "value": 0.02,
                }
            ],
        },
        artifact_store=store,
        adapter_registry=registry,
    )
    assert created.ok

    validated = validate_deployment(
        deployment_id=str(created.data["ml_deployment_manifest"]["deployment_id"]),
        artifact_store=store,
        adapter_registry=registry,
    )

    assert validated.ok
    report = validated.data["ml_deployment_validation_report"]
    assert report["status"] == "passed"
    assert report["adapter_evidence"]["expected_outputs_digest"] == report[
        "adapter_evidence"
    ]["actual_outputs_digest"]
