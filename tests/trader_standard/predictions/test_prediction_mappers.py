"""Contracts for maintained prediction mappers and their semantic admission rules.

Subject: Categorical regime mapping and rejection of incompatible model-output semantics.
Level: Deterministic maintained-adapter unit contracts.
Collaborators: Real mapper catalogue with provider-neutral core prediction values and fixed output contracts.
Guarantees: Supported outputs retain their meaning while mismatched semantics fail before strategy consumption.
Non-goals: Model loading, feature construction, inference execution, strategy allocation, or model quality.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.predictions import ModelIdentity, PredictionBatch, PredictionObservation
from trader_standard.predictions import MaintainedPredictionMapperCatalog


def _batch(*, semantics: str, value: object) -> PredictionBatch:
    return PredictionBatch(
        model_identity=ModelIdentity(
            registered_model_name="fixture",
            model_version="1",
            model_version_id="model_1",
            model_digest="sha256:model",
            signature_digest="sha256:signature",
            source_run_id="run_1",
            adapter_profile="fixture",
            adapter_version="1",
        ),
        feature_batch_hash="sha256:features",
        decision_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        observations=(
            PredictionObservation(
                output_name="output",
                semantics=semantics,
                value=value,
                horizon="1bar",
                symbol="AAA",
            ),
        ),
        status="success",
        latency_ms=1.0,
    )


def _contract(semantics: str) -> tuple[dict[str, object], ...]:
    return (
        {
            "name": "output",
            "semantics": semantics,
            "horizon": "1bar",
            "shape": "scalar",
        },
    )


def test_regime_mapper_preserves_categorical_value() -> None:
    """Ensure regime mapping retains categorical content under the configured target name."""
    catalog = MaintainedPredictionMapperCatalog()
    snapshot = catalog.resolve_configuration(
        mapper_id="categorical_regime:v1",
        consumer_kind="regime",
        output_contract=_contract("regime"),
        parameters={"target_name": "market_regime"},
    )

    mapped = catalog.build_mapper(snapshot).map_predictions(
        _batch(semantics="regime", value="risk_on")
    )

    assert mapped[0].name == "market_regime"
    assert mapped[0].value == "risk_on"


@pytest.mark.parametrize(
    ("mapper_id", "consumer_kind", "semantics", "message"),
    [
        (
            "probability_threshold:v1",
            "directional",
            "expected_return",
            "requires probability semantics",
        ),
        (
            "target_weight:v1",
            "allocation",
            "expected_return",
            "requires target_weight semantics",
        ),
        (
            "categorical_regime:v1",
            "regime",
            "rank_score",
            "requires regime semantics",
        ),
    ],
)
def test_specialized_mappers_reject_incompatible_semantics(
    mapper_id: str,
    consumer_kind: str,
    semantics: str,
    message: str,
) -> None:
    """Ensure each specialized mapper rejects output meaning incompatible with its consumer."""
    with pytest.raises(ValueError, match=message):
        MaintainedPredictionMapperCatalog().resolve_configuration(
            mapper_id=mapper_id,
            consumer_kind=consumer_kind,
            output_contract=_contract(semantics),
            parameters={},
        )
