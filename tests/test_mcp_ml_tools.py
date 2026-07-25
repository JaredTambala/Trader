"""MCP registration and policy tests for ML deployment evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

import anyio

from trader.predictions import (
    ModelIdentity,
    PredictionBatch,
    PredictionObservation,
    PredictionRequest,
    Predictor,
)
from trader_mcp.constants import (
    MCP_CONFIG_TOOL,
    ML_CREATE_DEPLOYMENT_MANIFEST_TOOL,
    ML_VALIDATE_DEPLOYMENT_TOOL,
    RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
    RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    ML_AGENT_OWNER,
    ML_FEATURE_SET_SPEC,
    ML_FEATURE_SET_VALIDATION_REPORT,
    ML_MODEL_VERSION_REF,
)
from trader_research.ml import (
    InferenceAdapterProfile,
    InferenceAdapterRegistry,
)
from tests.support.duckdb_store import DuckDBEventStore
from tests.test_model_backtest_integration import (
    MODEL_STRATEGY_SOURCE,
    _config,
    _record_bar,
)


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

    def validate_deployment(self, manifest: Mapping[str, object]) -> Mapping[str, object]:
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
            agent_owner=ML_AGENT_OWNER,
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
        assert blocked.structuredContent["errors"][0]["code"] == "ml_runtime_not_allowed"

    anyio.run(_run)


def test_mcp_validates_ml_deployment_when_runtime_is_enabled() -> None:
    store = InMemoryResearchArtifactStore()
    _seed_upstream(store)
    registry = InferenceAdapterRegistry((_FixtureAdapter(),))
    environment = replace(
        load_local_environment("env.template"), allow_ml_runtime=True
    )
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
        report = validated.structuredContent["data"][
            "ml_deployment_validation_report"
        ]
        assert report["status"] == "passed"
        assert report["valid"] is True
        assert report["deployment_id"] == deployment_id

    anyio.run(_run)


def test_mcp_model_deployment_to_backtest_evidence_graph(tmp_path: Path) -> None:
    store = InMemoryResearchArtifactStore()
    _seed_upstream(store)
    registry = InferenceAdapterRegistry((_FixtureAdapter(),))
    event_store = DuckDBEventStore(str(tmp_path / "mcp-model-backtest.duckdb"))
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    _record_bar(event_store, "EURUSD", start - timedelta(minutes=1), 101.0)
    _record_bar(event_store, "EURUSD", start, 100.0)
    _record_bar(event_store, "EURUSD", start + timedelta(minutes=1), 102.0)
    environment = replace(
        load_local_environment("env.template"),
        allow_backtests=True,
        allow_ml_runtime=True,
    )
    server = create_server(
        environment,
        event_store_provider=lambda: event_store,
        backtest_config_provider=lambda: _config(tmp_path / "mcp-model-backtest.duckdb"),
        research_artifact_store_provider=lambda: store,
        inference_adapter_registry=registry,
    )

    async def _run() -> None:
        created = await server.call_tool(
            ML_CREATE_DEPLOYMENT_MANIFEST_TOOL, _deployment_request()
        )
        deployment_id = _payload(created, "ml_deployment_manifest")["deployment_id"]
        deployment_validation = _payload(
            await server.call_tool(
                ML_VALIDATE_DEPLOYMENT_TOOL, {"deployment_id": deployment_id}
            ),
            "ml_deployment_validation_report",
        )
        implementation = _payload(
            await server.call_tool(
                RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
                {
                    "name": "prediction-driven",
                    "version": "1",
                    "source_code": MODEL_STRATEGY_SOURCE,
                    "factory_name": "build_strategy",
                    "parameter_schema": {
                        "type": "object",
                        "properties": {
                            "prediction_binding_name": {
                                "type": "string",
                                "default": "alpha_model",
                            },
                            "input_name": {"type": "string", "default": "alpha"},
                            "consumer_kind": {
                                "type": "string",
                                "default": "directional",
                            },
                            "order_qty": {
                                "type": "number",
                                "minimum": 0.01,
                                "default": 1.0,
                            },
                            "decision_threshold": {
                                "type": "number",
                                "minimum": 0.0,
                                "default": 0.0,
                            },
                        },
                        "required": [
                            "prediction_binding_name",
                            "input_name",
                            "consumer_kind",
                            "order_qty",
                            "decision_threshold",
                        ],
                    },
                    "runtime_requirements": {
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
                },
            ),
            "implementation_version",
        )
        implementation_validation = _payload(
            await server.call_tool(
                RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
                {
                    "implementation_version_id": implementation[
                        "implementation_version_id"
                    ]
                },
            ),
            "implementation_validation_report",
        )
        parameters = {
            "prediction_binding_name": "alpha_model",
            "input_name": "alpha",
            "consumer_kind": "directional",
            "order_qty": 1.0,
            "decision_threshold": 0.0,
        }
        strategy = _payload(
            await server.call_tool(
                RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
                {
                    "implementation_validation_ref": implementation_validation[
                        "validation_id"
                    ],
                    "parameters": parameters,
                    "prediction_bindings": [
                        {
                            "name": "alpha_model",
                            "deployment_validation_ref": deployment_validation[
                                "validation_id"
                            ],
                            "output_names": ["expected_return"],
                            "mapper_id": "identity_numeric:v1",
                            "mapper_parameters": {"target_name": "alpha"},
                        }
                    ],
                },
            ),
            "strategy_specification",
        )
        strategy_validation = _payload(
            await server.call_tool(
                RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
                {"strategy_specification_id": strategy["strategy_specification_id"]},
            ),
            "strategy_specification_validation_report",
        )
        manifest = {
            "dataset_id": "dataset_mcp_model",
            "symbols": ["EURUSD"],
            "asset_class": "stocks",
            "timeframe": "1Min",
            "time_range": {
                "start": start.isoformat(),
                "end": (start + timedelta(minutes=1)).isoformat(),
            },
            "total_rows": 2,
            "complete": True,
            "source_filter": None,
        }
        backtest = _payload(
            await server.call_tool(
                RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
                {
                    "strategy_specification_validation_ref": strategy_validation[
                        "validation_id"
                    ],
                    "dataset_manifest": manifest,
                    "data_quality_report": {
                        "symbols": ["EURUSD"],
                        "asset_class": "stocks",
                        "timeframe": "1Min",
                        "time_range": manifest["time_range"],
                        "complete": True,
                    },
                },
            ),
            "backtest_specification",
        )
        backtest_validation = _payload(
            await server.call_tool(
                RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
                {"backtest_specification_id": backtest["backtest_specification_id"]},
            ),
            "backtest_specification_validation_report",
        )
        run = _payload(
            await server.call_tool(
                RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
                {
                    "backtest_specification_validation_ref": backtest_validation[
                        "validation_id"
                    ]
                },
            ),
            "backtest_run",
        )

        assert run["status"] == "passed"
        assert run["prediction_bindings"][0]["model_version_id"] == (
            "ml_model_version_1"
        )
        assert run["summary"]["trade_count"] >= 2
        assert event_store.connection().execute(
            "SELECT COUNT(*) FROM prediction_events WHERE status = 'success'"
        ).fetchone()[0] == 2
        assert event_store.connection().execute(
            "SELECT COUNT(*) FROM order_events WHERE decision_evidence LIKE '%ml_model_version_1%'"
        ).fetchone()[0] >= 2

    anyio.run(_run)


def _payload(result, name: str) -> dict[str, object]:
    assert result.isError is False, result.structuredContent
    assert result.structuredContent is not None
    return dict(result.structuredContent["data"][name])
