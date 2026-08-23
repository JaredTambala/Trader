"""Contract and optional integration tests for local MLflow pyfunc inference."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import warnings

import pytest

from trader.predictions import (
    FeatureBatch,
    FeatureColumn,
    FeatureRow,
    ModelIdentity,
    PredictionRequest,
)
from trader_mlflow import MLflowLocalPyfuncAdapter, MLflowPyfuncPredictor
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


class _Frame:
    def __init__(self, rows: list[list[object]], columns: list[str]) -> None:
        self.rows = rows
        self.columns = columns


class _Model:
    def predict(self, frame: _Frame) -> list[list[float]]:
        return [[float(row[0]) * 2.0] for row in frame.rows]


def _identity() -> ModelIdentity:
    return ModelIdentity(
        registered_model_name="returns",
        model_version="1",
        model_version_id="model_version_1",
        model_digest="sha256:model",
        signature_digest="sha256:signature",
        source_run_id="training_run_1",
        adapter_profile="mlflow_local_pyfunc",
        adapter_version="1",
    )


def _batch() -> FeatureBatch:
    return FeatureBatch.build(
        feature_set_id="feature_set_1",
        feature_set_digest="sha256:features",
        decision_ts=NOW,
        schema=(FeatureColumn("return_1", "float64"),),
        rows=(
            FeatureRow(
                symbol="EURUSD",
                as_of_ts=NOW,
                availability_ts=NOW,
                values={"return_1": 0.01},
            ),
        ),
    )


def test_pyfunc_predictor_normalizes_tabular_outputs_without_importing_mlflow() -> None:
    predictor = MLflowPyfuncPredictor(
        model=_Model(),
        dataframe_factory=_Frame,
        identity=_identity(),
        output_contract=(
            {
                "name": "alpha",
                "semantics": "expected_return",
                "horizon": "1bar",
                "units": "return",
            },
        ),
    )

    result = predictor.predict(
        PredictionRequest(
            run_id="run_1",
            cycle_id="cycle_1",
            feature_batch=_batch(),
            requested_outputs=("alpha",),
            timeout_ms=1_000,
        )
    )

    assert result.status == "success"
    assert result.feature_batch_hash == _batch().input_hash
    assert result.observations[0].to_dict() == {
        "symbol": "EURUSD",
        "output_name": "alpha",
        "semantics": "expected_return",
        "value": 0.02,
        "horizon": "1bar",
        "units": "return",
        "uncertainty": None,
        "metadata": {},
    }


@pytest.mark.skipif(
    importlib.util.find_spec("mlflow") is None,
    reason="optional mlflow extra is not installed",
)
def test_local_mlflow_pyfunc_deployment_passes_real_parity_fixture(
    tmp_path: Path,
) -> None:
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
