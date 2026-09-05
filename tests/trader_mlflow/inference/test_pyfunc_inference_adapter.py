"""Contract tests for provider-neutral MLflow pyfunc prediction.

Subject: The optional package's normalization of already-loaded pyfunc model outputs.
Level: Unit contract.
Collaborators: Real core prediction values with fake model and dataframe collaborators.
Guarantees: Tabular outputs become correctly identified core prediction observations.
Non-goals: Research deployment governance, MLflow loading, remote tracking, or model quality.
"""

from __future__ import annotations

from datetime import datetime, timezone

from trader.predictions import (
    FeatureBatch,
    FeatureColumn,
    FeatureRow,
    ModelIdentity,
    PredictionRequest,
)
from trader_mlflow import MLflowPyfuncPredictor


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
    """Normalize tabular pyfunc output without importing optional provider packages."""
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
