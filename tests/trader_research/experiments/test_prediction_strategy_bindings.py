"""Contracts for prediction-bound canonical strategy specifications.

Subject: Typed deployment bindings, mapper semantics, exact dependency pins, and revalidation.
Level: In-process Experiments application contract.
Collaborators: A deployment-reader double, maintained prediction mappers, and canonical artifact storage.
Guarantees: Strategy specifications reject unavailable, incompatible, drifted, or malformed prediction dependencies.
Non-goals: Creating ML deployments, loading provider models, executing strategies, Postgres, or agents.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from trader_research.experiments import (
    create_strategy_specification,
    load_passed_strategy_specification,
    register_strategy_implementation,
    validate_strategy_implementation,
    validate_strategy_specification,
)
from trader_research.foundation import InMemoryResearchArtifactStore
from trader_standard.predictions import MaintainedPredictionMapperCatalog


MODEL_STRATEGY_SOURCE = """
from trader.strategies import Strategy


class FixtureModelStrategy(Strategy):
    def __init__(self, *, prediction_bindings):
        self.prediction_bindings = tuple(prediction_bindings)

    @property
    def strategy_id(self):
        return "fixture_model_strategy:1"

    def generate_orders(self, **kwargs):
        return []


def build_strategy(*, prediction_bindings, **kwargs):
    return FixtureModelStrategy(prediction_bindings=prediction_bindings)
"""


class FixtureDeploymentReader:
    """Return one immutable deployment and optionally simulate dependency drift."""

    def __init__(
        self, *, semantics: str = "expected_return", model_version_id: str = "model_1"
    ) -> None:
        self.semantics = semantics
        self.model_version_id = model_version_id

    def resolve_passed(self, validation_ref: str) -> Mapping[str, Any]:
        assert validation_ref in {
            "deployment_validation_1",
            "research://postgres/ml_deployment_validation_report/deployment_validation_1",
        }
        output = {
            "name": "alpha",
            "semantics": self.semantics,
            "horizon": "1h",
            "dtype": "float64",
            "shape": "scalar",
            "units": "return",
            "nullable": False,
        }
        manifest = {
            "artifact_type": "ml_deployment_manifest",
            "deployment_id": "deployment_1",
            "model_version_id": self.model_version_id,
            "output_contract": [output],
        }
        return {
            "deployment_id": "deployment_1",
            "deployment_validation_id": "deployment_validation_1",
            "model_version_id": self.model_version_id,
            "feature_set_id": "features_1",
            "adapter_profile": {"profile_name": "fixture"},
            "output_contract": [output],
            "inference_scope": "per_symbol",
            "decision_scope": "per_symbol",
            "inference_policy": {"failure_action": "fail_closed"},
            "eligibility": ["backtest", "paper"],
            "manifest": manifest,
        }


def _validated_implementation(store: InMemoryResearchArtifactStore) -> str:
    registered = register_strategy_implementation(
        name="fixture_model_strategy",
        version="1",
        source_code=MODEL_STRATEGY_SOURCE,
        factory_name="build_strategy",
        parameter_schema={"type": "object", "properties": {}, "required": []},
        runtime_requirements={
            "prediction_requirements": [
                {
                    "name": "alpha_model",
                    "accepted_semantics": ["expected_return"],
                    "accepted_horizons": ["1h"],
                    "accepted_output_shapes": ["scalar"],
                    "inference_scopes": ["per_symbol"],
                    "consumer_kind": "directional",
                }
            ]
        },
        artifact_store=store,
    )
    assert registered.ok
    implementation_id = registered.data["implementation_version"][
        "implementation_version_id"
    ]
    validated = validate_strategy_implementation(
        implementation_version_id=implementation_id,
        artifact_store=store,
    )
    assert validated.ok
    assert validated.data["implementation_validation_report"]["fixture"] == {
        "status": "passed",
        "orders_emitted": 0,
        "prediction_requirement_count": 1,
    }
    return str(validated.data["implementation_validation_report"]["validation_id"])


def _binding() -> list[dict[str, object]]:
    return [
        {
            "name": "alpha_model",
            "deployment_validation_ref": "deployment_validation_1",
            "output_names": ["alpha"],
            "mapper_id": "identity_numeric:v1",
            "mapper_parameters": {"target_name": "alpha"},
        }
    ]


def test_model_backed_strategy_specification_pins_typed_binding_and_revalidates() -> (
    None
):
    """A model-backed strategy specification pins typed deployment and mapper identities."""
    store = InMemoryResearchArtifactStore()
    implementation_validation_id = _validated_implementation(store)
    reader = FixtureDeploymentReader()
    catalog = MaintainedPredictionMapperCatalog()

    created = create_strategy_specification(
        implementation_validation_ref=implementation_validation_id,
        prediction_bindings=_binding(),
        prediction_deployment_reader=reader,
        prediction_mapper_catalog=catalog,
        artifact_store=store,
    )
    assert created.ok
    strategy = created.data["strategy_specification"]
    assert strategy["decision_scope"] == "per_symbol"
    assert strategy["prediction_bindings"][0]["model_version_id"] == "model_1"
    assert (
        strategy["prediction_bindings"][0]["mapper"]["mapper_id"]
        == "identity_numeric:v1"
    )

    validated = validate_strategy_specification(
        strategy_specification_id=strategy["strategy_specification_id"],
        prediction_deployment_reader=reader,
        prediction_mapper_catalog=catalog,
        artifact_store=store,
    )
    assert validated.ok
    validation_id = validated.data["strategy_specification_validation_report"][
        "validation_id"
    ]
    loaded, _ = load_passed_strategy_specification(
        store,
        validation_id,
        prediction_deployment_reader=reader,
        prediction_mapper_catalog=catalog,
    )
    assert loaded == strategy


def test_prediction_binding_rejects_missing_or_semantically_incompatible_deployment() -> (
    None
):
    """Specification creation rejects absent deployment readers and incompatible output semantics."""
    store = InMemoryResearchArtifactStore()
    implementation_validation_id = _validated_implementation(store)
    catalog = MaintainedPredictionMapperCatalog()

    missing_reader = create_strategy_specification(
        implementation_validation_ref=implementation_validation_id,
        prediction_bindings=_binding(),
        prediction_mapper_catalog=catalog,
        artifact_store=store,
    )
    assert not missing_reader.ok
    assert "deployment reader is required" in missing_reader.errors[0]["message"]

    incompatible = create_strategy_specification(
        implementation_validation_ref=implementation_validation_id,
        prediction_bindings=_binding(),
        prediction_deployment_reader=FixtureDeploymentReader(
            semantics="class_probability"
        ),
        prediction_mapper_catalog=catalog,
        artifact_store=store,
    )
    assert not incompatible.ok
    assert "semantics are incompatible" in incompatible.errors[0]["message"]


def test_prediction_binding_validation_blocks_deployment_or_mapper_drift() -> None:
    """Revalidation rejects changed deployment versions and tampered mapper parameters."""
    store = InMemoryResearchArtifactStore()
    implementation_validation_id = _validated_implementation(store)
    reader = FixtureDeploymentReader()
    catalog = MaintainedPredictionMapperCatalog()
    created = create_strategy_specification(
        implementation_validation_ref=implementation_validation_id,
        prediction_bindings=_binding(),
        prediction_deployment_reader=reader,
        prediction_mapper_catalog=catalog,
        artifact_store=store,
    )
    strategy = created.data["strategy_specification"]

    drifted = validate_strategy_specification(
        strategy_specification_id=strategy["strategy_specification_id"],
        prediction_deployment_reader=FixtureDeploymentReader(
            model_version_id="model_2"
        ),
        prediction_mapper_catalog=catalog,
        artifact_store=store,
    )
    assert not drifted.ok
    assert "dependency evidence drifted" in drifted.errors[0]["message"]

    tampered = deepcopy(dict(strategy))
    tampered["prediction_bindings"][0]["mapper"]["parameters"]["target_name"] = (
        "changed"
    )
    inline = validate_strategy_specification(
        strategy_specification=tampered,
        prediction_deployment_reader=reader,
        prediction_mapper_catalog=catalog,
        artifact_store=store,
    )
    assert not inline.ok
    assert "dependency evidence drifted" in inline.errors[0]["message"]


def test_implementation_rejects_unknown_prediction_requirement_fields() -> None:
    """Implementation registration explicitly rejects undeclared prediction-requirement configuration fields."""
    result = register_strategy_implementation(
        name="invalid",
        version="1",
        source_code=MODEL_STRATEGY_SOURCE,
        factory_name="build_strategy",
        runtime_requirements={
            "prediction_requirements": [
                {
                    "name": "alpha",
                    "accepted_semantics": ["anything"],
                    "accepted_horizons": ["1h"],
                    "accepted_output_shapes": ["scalar"],
                    "inference_scopes": ["per_symbol"],
                    "consumer_kind": "directional",
                    "hardcoded_target": "not allowed",
                }
            ]
        },
        artifact_store=InMemoryResearchArtifactStore(),
    )
    assert not result.ok
    assert "unknown prediction requirement fields" in result.errors[0]["message"]
