"""Adapter tests for MCP ML deployment creation and validation tools.

Subject: ML deployment registration metadata, runtime policy, and parity validation adapters.
Level: Adapter integration.
Collaborators: Real MCP/research services with an in-memory store and deterministic inference adapter.
Guarantees: Deployment creation remains available while model loading is separately gated and evidenced.
Non-goals: Prediction-driven backtesting, real MLflow, training, registry mutation, or agent reasoning.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

import anyio

from trader.predictions import (
    InferenceAdapterProfile,
    ModelIdentity,
    PredictionBatch,
    PredictionObservation,
    PredictionRequest,
    Predictor,
)
from trader_mcp.catalogue.definitions import (
    MCP_CONFIG_TOOL,
    ML_CREATE_DEPLOYMENT_MANIFEST_TOOL,
    ML_VALIDATE_DEPLOYMENT_TOOL,
)
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    ML_FEATURE_SET_SPEC,
    ML_FEATURE_SET_VALIDATION_REPORT,
    ML_MODEL_VERSION_REF,
)
from trader_research.ml import InferenceAdapterRegistry


class _ReturnPredictor:
    """Return the point-in-time return input as one expected-return output."""

    identity = ModelIdentity(
        registered_model_name="fx_return_model",
        model_version="7",
        model_version_id="ml_model_version_1",
        model_digest="sha256:model",
        signature_digest="sha256:signature",
        source_run_id="mlflow_run_1",
        adapter_profile="fixture_local",
        adapter_version="1",
    )

    def predict(self, request: PredictionRequest) -> PredictionBatch:
        return PredictionBatch(
            model_identity=self.identity,
            feature_batch_hash=request.feature_batch.input_hash,
            decision_ts=request.feature_batch.decision_ts,
            observations=tuple(
                PredictionObservation(
                    output_name="expected_return",
                    semantics="expected_return",
                    value=float(row.values["return_1"]),
                    horizon="1h",
                    symbol=row.symbol,
                    units="return",
                )
                for row in request.feature_batch.rows
            ),
            status="success",
            latency_ms=1.0,
        )


class _FixtureAdapter:
    """Deterministic local adapter used to prove MCP orchestration."""

    def profile(self) -> InferenceAdapterProfile:
        return InferenceAdapterProfile(
            profile_name="fixture_local",
            provider="fixture",
            adapter_version="1",
            configuration_digest="sha256:fixture-config",
            capabilities=("local_model", "python_function", "scalar_outputs"),
            available=True,
        )

    def validate_deployment(
        self, manifest: Mapping[str, object]
    ) -> Mapping[str, object]:
        fixture = dict(manifest["parity_fixture"])  # type: ignore[arg-type]
        digest = fixture["expected_outputs_digest"]
        return {
            "status": "passed",
            "expected_outputs_digest": digest,
            "actual_outputs_digest": digest,
            "latency_ms": 1.0,
        }

    def build_predictor(self, manifest: Mapping[str, object]) -> Predictor:
        del manifest
        return _ReturnPredictor()


def _seed_upstream(store: InMemoryResearchArtifactStore) -> None:
    artifacts = (
        (
            ML_MODEL_VERSION_REF,
            "ml_model_version_1",
            "registered",
            {
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
            },
        ),
        (
            ML_FEATURE_SET_SPEC,
            "ml_feature_set_1",
            "created",
            {
                "artifact_type": ML_FEATURE_SET_SPEC,
                "feature_set_id": "ml_feature_set_1",
                "feature_set_digest": "sha256:features",
                "status": "created",
                "schema": [
                    {
                        "name": "return_1",
                        "dtype": "float64",
                        "nullable": False,
                        "transform": {
                            "kind": "simple_return",
                            "field": "close",
                            "periods": 1,
                            "lag": 0,
                        },
                    }
                ],
            },
        ),
        (
            ML_FEATURE_SET_VALIDATION_REPORT,
            "ml_feature_set_validation_1",
            "passed",
            {
                "artifact_type": ML_FEATURE_SET_VALIDATION_REPORT,
                "validation_id": "ml_feature_set_validation_1",
                "feature_set_id": "ml_feature_set_1",
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
            producer_tool="test_mcp_ml_fixture",
            payload=payload,
            status=status,
        )


def _deployment_request() -> dict[str, object]:
    return {
        "model_version_ref": "ml_model_version_1",
        "feature_set_validation_ref": "ml_feature_set_validation_1",
        "adapter_profile": "fixture_local",
        "output_contract": [
            {
                "name": "expected_return",
                "semantics": "expected_return",
                "horizon": "1h",
                "units": "return",
            }
        ],
        "inference_scope": "per_symbol",
        "inference_policy": {"timeout_ms": 500, "failure_action": "fail_closed"},
        "environment_config": {
            "python": "3.12",
            "environment_digest": "sha256:env",
        },
        "parity_fixture": {
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
        "eligibility": ["backtest", "paper"],
    }


def test_mcp_registers_ml_deployment_tools_and_enforces_runtime_gate() -> None:
    """Register ML deployment tools while blocking model loading behind runtime policy."""
    store = InMemoryResearchArtifactStore()
    _seed_upstream(store)
    registry = InferenceAdapterRegistry((_FixtureAdapter(),))
    environment = load_local_environment("env.template")
    server = create_server(
        environment,
        research_artifact_store_provider=lambda: store,
        inference_adapter_registry=registry,
    )

    async def _run() -> None:
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        tools = {
            item["name"]: item for item in config.structuredContent["data"]["tools"]
        }
        assert tools[ML_CREATE_DEPLOYMENT_MANIFEST_TOOL] == {
            "name": ML_CREATE_DEPLOYMENT_MANIFEST_TOOL,
            "agent_owner": "ML Agent",
            "side_effect": "local_mutating",
            "description": tools[ML_CREATE_DEPLOYMENT_MANIFEST_TOOL]["description"],
        }
        assert tools[ML_VALIDATE_DEPLOYMENT_TOOL]["agent_owner"] == "ML Agent"
        assert tools[ML_VALIDATE_DEPLOYMENT_TOOL]["side_effect"] == "local_mutating"
        assert config.structuredContent["data"]["safety"]["ml_runtime_allowed"] is False

        created = await server.call_tool(
            ML_CREATE_DEPLOYMENT_MANIFEST_TOOL, _deployment_request()
        )
        assert created.isError is False
        deployment_id = created.structuredContent["data"]["ml_deployment_manifest"][
            "deployment_id"
        ]

        blocked = await server.call_tool(
            ML_VALIDATE_DEPLOYMENT_TOOL, {"deployment_id": deployment_id}
        )
        assert blocked.isError is True
        assert (
            blocked.structuredContent["errors"][0]["code"] == "ml_runtime_not_allowed"
        )

    anyio.run(_run)


def test_mcp_validates_ml_deployment_when_runtime_is_enabled() -> None:
    """Validate deployment parity when explicit ML runtime permission is enabled."""
    store = InMemoryResearchArtifactStore()
    _seed_upstream(store)
    registry = InferenceAdapterRegistry((_FixtureAdapter(),))
    environment = replace(load_local_environment("env.template"), allow_ml_runtime=True)
    server = create_server(
        environment,
        research_artifact_store_provider=lambda: store,
        inference_adapter_registry=registry,
    )

    async def _run() -> None:
        created = await server.call_tool(
            ML_CREATE_DEPLOYMENT_MANIFEST_TOOL, _deployment_request()
        )
        deployment_id = created.structuredContent["data"]["ml_deployment_manifest"][
            "deployment_id"
        ]
        validated = await server.call_tool(
            ML_VALIDATE_DEPLOYMENT_TOOL, {"deployment_id": deployment_id}
        )

        assert validated.isError is False
        report = validated.structuredContent["data"]["ml_deployment_validation_report"]
        assert report["status"] == "passed"
        assert report["valid"] is True
        assert report["deployment_id"] == deployment_id

    anyio.run(_run)


def _payload(result, name: str) -> dict[str, object]:
    assert result.isError is False, result.structuredContent
    assert result.structuredContent is not None
    return dict(result.structuredContent["data"][name])
