"""MCP registration and independent execution-gate tests for optimization."""

from __future__ import annotations

from trader_research.governance.artifacts import DOMAIN_OWNER_BY_ARTIFACT_TYPE

from dataclasses import replace

import anyio

from trader_mcp.constants import (
    ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
    ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
    EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
    RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
    RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL,
    RESEARCH_PROJECT_EXPERIMENT_TRACKING_TOOL,
    RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    PARAMETER_OPTIMIZATION_AUDIT_PLAN,
    PARAMETER_OPTIMIZATION_RUN,
)


def test_mcp_exposes_decoupled_tools_and_independent_write_gates() -> None:
    store = InMemoryResearchArtifactStore()
    environment = replace(
        load_local_environment("env.template"),
        allow_backtests=False,
        allow_optimization=False,
        allow_external_research_writes=False,
        allow_experiment_tracking_writes=False,
    )
    server = create_server(
        environment,
        research_artifact_store_provider=lambda: store,
    )

    async def _run() -> None:
        tools = await server.list_tools()
        names = {tool.name for tool in tools}
        assert names == set(REGISTERED_TOOL_NAMES)
        assert "research_create_strategy_candidate" not in names
        assert "research_run_backtest" not in names
        assert "research_run_portfolio_backtest" not in names
        assert RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL in names
        assert EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL in names
        assert ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL in names
        assert ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL in names

        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        metadata = {item["name"]: item for item in config.structuredContent["data"]["tools"]}
        assert metadata[RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL]["agent_owner"] == (
            "Quantitative Methods Agent"
        )
        assert metadata[RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL]["side_effect"] == "local_mutating"
        assert metadata[RESEARCH_PROJECT_EXPERIMENT_TRACKING_TOOL]["side_effect"] == (
            "external_research_mutating"
        )
        assert config.structuredContent["data"]["safety"]["optimization_execution_allowed"] is False
        assert config.structuredContent["data"]["experiment_tracking_runtime"]["authority"] == (
            "analytical_projection_only"
        )

        backtest = await server.call_tool(
            RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
            {"backtest_specification_validation_ref": "missing"},
        )
        assert backtest.structuredContent["errors"][0]["code"] == "backtests_not_allowed"

        optimization = await server.call_tool(
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {"optimization_plan_ref": "missing", "optimizer_profile": "builtin_random"},
        )
        assert optimization.structuredContent["errors"][0]["code"] == "backtests_not_allowed"

        projection = await server.call_tool(
            RESEARCH_PROJECT_EXPERIMENT_TRACKING_TOOL,
            {"canonical_run_ref": "missing", "tracking_profile": "mlflow_backtest_optimization"},
        )
        assert projection.structuredContent["errors"][0]["code"] == (
            "experiment_tracking_writes_not_allowed"
        )

        runtime = await server.call_tool(RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL, {})
        profiles = {item["profile_name"]: item for item in runtime.structuredContent["data"]["profiles"]}
        assert profiles["builtin_grid"]["available"] is True
        assert profiles["builtin_random"]["available"] is True
        assert "optuna_tpe" in profiles

    anyio.run(_run)


def test_optimization_requires_its_gate_after_backtests_are_enabled() -> None:
    environment = replace(
        load_local_environment("env.template"),
        allow_backtests=True,
        allow_optimization=False,
    )
    server = create_server(
        environment,
        research_artifact_store_provider=InMemoryResearchArtifactStore,
    )

    async def _run() -> None:
        result = await server.call_tool(
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
            {"optimization_plan_ref": "missing", "optimizer_profile": "builtin_random"},
        )
        assert result.structuredContent["errors"][0]["code"] == "optimization_not_allowed"

    anyio.run(_run)


def test_optuna_variant_execution_uses_the_same_external_write_gates() -> None:
    store = InMemoryResearchArtifactStore()
    store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_RUN],
        producer_tool="test_mcp_optimization_fixture",
        artifact_type=PARAMETER_OPTIMIZATION_RUN,
        artifact_id="baseline-run",
        payload={
            "artifact_type": PARAMETER_OPTIMIZATION_RUN,
            "optimization_run_id": "baseline-run",
            "engine_profile": {"profile_name": "optuna_tpe"},
        },
        status="completed",
    )
    store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_AUDIT_PLAN],
        producer_tool="test_mcp_optimization_fixture",
        artifact_type=PARAMETER_OPTIMIZATION_AUDIT_PLAN,
        artifact_id="audit-plan",
        payload={
            "artifact_type": PARAMETER_OPTIMIZATION_AUDIT_PLAN,
            "audit_plan_id": "audit-plan",
            "baseline_optimization_run_id": "baseline-run",
            "attacks": [
                {
                    "attack_type": "seed_sensitivity",
                    "evidence_kind": "optimization_variant",
                    "configuration": {},
                }
            ],
        },
        status="created",
    )
    environment = replace(
        load_local_environment("env.template"),
        allow_backtests=True,
        allow_optimization=True,
        allow_external_research_writes=False,
        allow_optuna_writes=False,
    )
    server = create_server(
        environment,
        event_store_provider=lambda: None,  # type: ignore[return-value]
        backtest_config_provider=lambda: None,  # type: ignore[return-value]
        research_artifact_store_provider=lambda: store,
    )

    async def _run() -> None:
        result = await server.call_tool(
            RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
            {"audit_plan_ref": "audit-plan"},
        )
        assert result.structuredContent["errors"][0]["code"] == "optuna_writes_not_allowed"

    anyio.run(_run)
