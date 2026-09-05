"""Deterministic MCP workflow for parameter optimization and independent review.

Subject: Composition of optimization, sealed holdout, Evaluation, and Adversarial evidence.
Level: Cross-package local workflow.
Collaborators: Real MCP, research, core, maintained implementations, and DuckDB; no external service.
Guarantees: Selection and holdout evidence flow into separately owned Evaluation and attack artifacts.
Non-goals: Postgres recovery, provider optimization engines, model-backed decisions, or live trading.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import anyio

from tests.support.duckdb_store import DuckDBEventStore
from trader.config import Config
from trader.market_data.sample import load_sample_market_data_csv
from trader_mcp.catalogue.definitions import (
    ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
    ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
    EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
    RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
    RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL,
    RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
    RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
    RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
)
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.data import (
    DataInventoryRequest,
    DataQualityRequest,
    data_summarize_quality,
    get_data_inventory,
)


STRATEGY_SOURCE = """
from trader.strategies import Strategy

class EmptyStrategy(Strategy):
    def __init__(self, period=2):
        self.period = period

    @property
    def strategy_id(self):
        return "mcp-optimization-empty"

    def generate_orders(self, **kwargs):
        return ()

def build_strategy(period=2, **kwargs):
    return EmptyStrategy(period=period)
"""

OBJECTIVE_SOURCE = """
def objective(observation):
    return {"value": observation["metrics"]["total_return"]}
"""

RISK_SOURCE = """
from trader.risk import RiskContext, RiskManager

class BoundedPassThroughRiskManager(RiskManager):
    def __init__(self, max_orders=10):
        self.max_orders = max_orders

    def validate(self, orders, context):
        return list(orders)[:self.max_orders]

def build_risk_manager(max_orders=10):
    return BoundedPassThroughRiskManager(max_orders=max_orders)
"""

SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


def test_mcp_optimization_holdout_and_adversarial_evidence_graph(
    tmp_path: Path,
) -> None:
    """Carry selection through sealed holdout, Evaluation, and Adversarial evidence."""
    event_store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(event_store, SAMPLE_CSV)
    selection_manifest, selection_quality = _scope(
        event_store,
        datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc),
    )
    holdout_manifest, holdout_quality = _scope(
        event_store,
        datetime(2026, 1, 20, 12, 6, tzinfo=timezone.utc),
        datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
    )
    artifact_store = InMemoryResearchArtifactStore()
    environment = replace(
        load_local_environment("env.template"),
        allow_backtests=True,
        allow_optimization=True,
    )
    server = create_server(
        environment,
        event_store_provider=lambda: event_store,
        backtest_config_provider=lambda: _config(tmp_path),
        research_artifact_store_provider=lambda: artifact_store,
    )

    async def _run() -> None:
        strategy = _data(
            await server.call_tool(
                RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
                {
                    "name": "empty-strategy",
                    "version": "1",
                    "source_code": STRATEGY_SOURCE,
                    "factory_name": "build_strategy",
                    "class_name": "EmptyStrategy",
                    "parameter_schema": {
                        "type": "object",
                        "properties": {
                            "period": {
                                "type": "integer",
                                "minimum": 2,
                                "maximum": 3,
                                "default": 2,
                            }
                        },
                    },
                    "authoring_origin": "handwritten_test_fixture",
                },
            ),
            "implementation_version",
        )
        strategy_validation = _data(
            await server.call_tool(
                RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
                {"implementation_version_id": strategy["implementation_version_id"]},
            ),
            "implementation_validation_report",
        )
        strategy_specification = _data(
            await server.call_tool(
                RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
                {
                    "implementation_validation_ref": strategy_validation[
                        "validation_id"
                    ],
                    "parameters": {"period": 2},
                    "tunable_fields": ["/strategy/parameters/period"],
                },
            ),
            "strategy_specification",
        )
        strategy_specification_validation = _data(
            await server.call_tool(
                RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
                {
                    "strategy_specification_id": strategy_specification[
                        "strategy_specification_id"
                    ]
                },
            ),
            "strategy_specification_validation_report",
        )
        risk = _data(
            await server.call_tool(
                RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
                {
                    "name": "bounded-pass-through-risk",
                    "version": "1",
                    "source_code": RISK_SOURCE,
                    "factory_name": "build_risk_manager",
                    "class_name": "BoundedPassThroughRiskManager",
                    "parameter_schema": {
                        "type": "object",
                        "properties": {
                            "max_orders": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                            }
                        },
                        "required": ["max_orders"],
                    },
                    "authoring_origin": "handwritten_test_fixture",
                },
            ),
            "implementation_version",
        )
        risk_validation = _data(
            await server.call_tool(
                RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
                {
                    "implementation_version_id": risk["implementation_version_id"],
                    "fixture_parameters": {"max_orders": 10},
                },
            ),
            "implementation_validation_report",
        )
        risk_stack = _data(
            await server.call_tool(
                RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL,
                {
                    "risk_managers": [
                        {
                            "implementation_validation_ref": risk_validation[
                                "validation_id"
                            ],
                            "parameters": {"max_orders": 10},
                        }
                    ]
                },
            ),
            "risk_stack_specification",
        )
        risk_stack_validation = _data(
            await server.call_tool(
                RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL,
                {
                    "risk_stack_specification_id": risk_stack[
                        "risk_stack_specification_id"
                    ]
                },
            ),
            "risk_stack_specification_validation_report",
        )
        selection_backtest_validation = await _create_validated_backtest(
            server,
            strategy_validation_id=strategy_specification_validation["validation_id"],
            risk_validation_id=risk_stack_validation["validation_id"],
            manifest=selection_manifest,
            quality=selection_quality,
        )

        objective = _data(
            await server.call_tool(
                RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
                {
                    "name": "completed-runs",
                    "version": "1",
                    "source_code": OBJECTIVE_SOURCE,
                    "factory_name": "objective",
                },
            ),
            "implementation_version",
        )
        objective_validation = _data(
            await server.call_tool(
                RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
                {"implementation_version_id": objective["implementation_version_id"]},
            ),
            "implementation_validation_report",
        )
        plan = _data(
            await server.call_tool(
                RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
                {
                    "base_backtest_specification_validation_ref": selection_backtest_validation[
                        "validation_id"
                    ],
                    "holdout_dataset_manifest": holdout_manifest,
                    "holdout_data_quality_report": holdout_quality,
                    "objective_validation_ref": objective_validation["validation_id"],
                    "search_space": [
                        {
                            "path": "/strategy/parameters/period",
                            "type": "integer",
                            "low": 2,
                            "high": 3,
                        }
                    ],
                    "max_trials": 2,
                },
            ),
            "parameter_optimization_plan",
        )
        optimization_result = await server.call_tool(
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {
                "optimization_plan_ref": plan["optimization_plan_id"],
                "optimizer_profile": "builtin_grid",
            },
        )
        assert optimization_result.structuredContent["ok"] is True, [
            {
                "status": record.payload.get("status"),
                "blockers": record.payload.get("blockers"),
                "objective": record.payload.get("objective_value"),
                "observation": record.payload.get("observation"),
            }
            for record in artifact_store.list_artifacts(
                artifact_type="parameter_optimization_trial"
            )
        ]
        optimization = _data(optimization_result, "parameter_optimization_run")
        assert optimization["status"] == "completed"
        assert optimization["trial_count"] == 2

        holdout_validation = await _create_validated_backtest(
            server,
            strategy_validation_id=optimization["selected_child_refs"][
                "strategy_specification_validation_id"
            ],
            risk_validation_id=optimization["selected_child_refs"][
                "risk_stack_specification_validation_id"
            ],
            manifest=holdout_manifest,
            quality=holdout_quality,
            selection_origin_ref=optimization["optimization_run_id"],
        )
        holdout_run = _data(
            await server.call_tool(
                RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
                {
                    "backtest_specification_validation_ref": holdout_validation[
                        "validation_id"
                    ]
                },
            ),
            "backtest_run",
        )
        assert holdout_run["backtest_kind"] == "portfolio"
        assert (
            holdout_run["risk_lineage"][0]["implementation_version_id"]
            == risk["implementation_version_id"]
        )
        evaluation = _data(
            await server.call_tool(
                EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
                {
                    "optimization_run_ref": optimization["optimization_run_id"],
                    "holdout_backtest_run_ref": holdout_run["run_id"],
                },
            ),
            "parameter_optimization_evaluation_report",
        )
        assert evaluation["status"] == "passed"

        audit_plan = _data(
            await server.call_tool(
                ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
                {
                    "optimization_run_ref": optimization["optimization_run_id"],
                    "attacks": [
                        {"attack_type": "seed_sensitivity"},
                        {"attack_type": "concentration"},
                        {"attack_type": "multiple_testing"},
                    ],
                },
            ),
            "parameter_optimization_audit_plan",
        )
        variants = _data(
            await server.call_tool(
                RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
                {"audit_plan_ref": audit_plan["audit_plan_id"]},
            ),
            "variant_optimization_runs",
        )
        audit = _data(
            await server.call_tool(
                ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
                {
                    "audit_plan_ref": audit_plan["audit_plan_id"],
                    "variant_optimization_run_refs": [
                        item["optimization_run_id"] for item in variants
                    ],
                },
            ),
            "parameter_optimization_robustness_report",
        )
        assert audit["status"] == "passed"
        assert (
            artifact_store.load_artifact(
                "parameter_optimization_run", optimization["optimization_run_id"]
            )["selected_trial_id"]
            == optimization["selected_trial_id"]
        )

    anyio.run(_run)


async def _create_validated_backtest(
    server: Any,
    *,
    strategy_validation_id: str,
    risk_validation_id: str | None,
    manifest: Mapping[str, Any],
    quality: Mapping[str, Any],
    selection_origin_ref: str | None = None,
) -> Mapping[str, Any]:
    specification = _data(
        await server.call_tool(
            RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
            {
                "strategy_specification_validation_ref": strategy_validation_id,
                "risk_stack_specification_validation_ref": risk_validation_id,
                "dataset_manifest": dict(manifest),
                "data_quality_report": dict(quality),
                "max_runs": 3,
                "selection_origin_ref": selection_origin_ref,
            },
        ),
        "backtest_specification",
    )
    return _data(
        await server.call_tool(
            RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
            {"backtest_specification_id": specification["backtest_specification_id"]},
        ),
        "backtest_specification_validation_report",
    )


def _scope(
    store: DuckDBEventStore,
    start: datetime,
    end: datetime,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    request = {
        "symbols": ("DEMO",),
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": start,
        "end": end,
    }
    inventory = get_data_inventory(store, DataInventoryRequest(**request))
    quality = data_summarize_quality(store, DataQualityRequest(**request))
    assert inventory.ok and quality.ok
    return _jsonable(inventory.data["dataset_manifest"]), _jsonable(
        quality.data["data_quality_report"]
    )


def _data(result: Any, key: str) -> Any:
    payload = result.structuredContent
    assert payload["ok"] is True, payload.get("errors")
    return payload["data"][key]


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _config(tmp_path: Path) -> Config:
    return Config(
        mode="once",
        strategy_type="research",
        strategy_id="research",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path=str(tmp_path / "events.duckdb"),
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("DEMO",),
        market_data_max_age_seconds=60,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
        alpaca_base_url="https://paper-api.alpaca.markets",
        pg_dsn="",
        pg_host="",
        pg_port=5432,
        pg_db="",
        pg_user="",
        pg_password="",
        buffered_event_store=False,
        buffer_flush_interval_ms=250,
        buffer_max_batch_size=500,
        buffer_max_queue_size=10000,
        buffer_block_on_full=True,
        log_signal_events=True,
        log_indicator_events=True,
        log_order_events=True,
        log_fill_events=True,
        log_position_snapshots=True,
        broker_type="noop",
    )
