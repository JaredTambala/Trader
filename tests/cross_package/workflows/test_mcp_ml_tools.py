"""Cross-package workflow from MCP model deployment through backtesting.

Subject: Composition of ML deployment, strategy admission, prediction mapping, and backtest execution.
Level: Local workflow.
Collaborators: Real MCP/research/core services with DuckDB and a deterministic inference adapter.
Guarantees: Immutable model identity reaches prediction, decision, order, and backtest evidence.
Non-goals: Isolated MCP ML-tool policy, real MLflow, Postgres recovery, or live trading.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anyio

from tests.support.duckdb_store import DuckDBEventStore
from tests.cross_package.workflows.test_model_backtest_integration import (
    MODEL_STRATEGY_SOURCE,
    _config,
    _record_bar,
)
from tests.trader_mcp.tools.ml.test_deployment_tools import (
    _FixtureAdapter,
    _deployment_request,
    _payload,
    _seed_upstream,
)
from trader_mcp.catalogue.definitions import (
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
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.ml import InferenceAdapterRegistry


def test_mcp_model_deployment_to_backtest_evidence_graph(tmp_path: Path) -> None:
    """Carry a validated model deployment through strategy binding and backtesting."""
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
        backtest_config_provider=lambda: _config(
            tmp_path / "mcp-model-backtest.duckdb"
        ),
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
        assert (
            event_store.connection()
            .execute("SELECT COUNT(*) FROM prediction_events WHERE status = 'success'")
            .fetchone()[0]
            == 2
        )
        assert (
            event_store.connection()
            .execute(
                "SELECT COUNT(*) FROM order_events WHERE decision_evidence LIKE '%ml_model_version_1%'"
            )
            .fetchone()[0]
            >= 2
        )

    anyio.run(_run)
