"""Contract tests for MCP environment policy and catalogue registration.

Subject: Environment defaults and the public registered-tool policy surface.
Level: Contract.
Collaborators: Real environment normalization and an in-process FastMCP server catalogue.
Guarantees: Portable defaults, complete registration, ownership, side effects, and gates stay explicit.
Non-goals: Capability execution, stdio lifecycle, concrete provider composition, or agent allowlists.
"""

from __future__ import annotations

import anyio

from trader_mcp.catalogue.definitions import (
    CAPABILITY_REGISTRATION_FLAGS,
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    DATA_ENSURE_LOADED_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
    RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL,
    RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
    RESEARCH_GET_BACKTEST_RESULTS_TOOL,
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL,
    RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL,
    RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
)
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server


def test_local_env_loads_portable_configuration() -> None:
    """Normalize the portable template into default MCP policy configuration."""
    local_env = load_local_environment("env.template")

    assert local_env.environment == "local"
    assert local_env.transport == "stdio"
    assert str(local_env.artifact_root) == "artifacts/research"
    assert local_env.trader_config_path is None
    assert local_env.policy_flags() == {
        "allow_broker_mutation": False,
        "allow_raw_sql": False,
        "allow_symbol_provider_discovery": False,
        "allow_data_loading": False,
        "allow_backtests": False,
        "allow_optimization": False,
        "allow_external_research_writes": False,
        "allow_optuna_writes": False,
        "allow_experiment_tracking_writes": False,
        "allow_ml_runtime": False,
        "allow_coding_workspace": False,
    }


def test_create_server_registers_support_and_data_tools() -> None:
    """Register the complete declared catalogue on a composed server instance."""
    local_env = load_local_environment("env.template")
    server = create_server(local_env)

    async def _run() -> None:
        tools = await server.list_tools()

        assert {tool.name for tool in tools} == set(REGISTERED_TOOL_NAMES)

    anyio.run(_run)


def test_config_tool_excludes_broker_raw_sql_and_gates_backtest_execution() -> None:
    """Expose registered tools and conservative capability gates through server configuration."""
    local_env = load_local_environment("env.template")
    server = create_server(local_env)

    async def _run() -> None:
        result = await server.call_tool(MCP_CONFIG_TOOL, {})

        assert result.structuredContent is not None
        data = result.structuredContent["data"]
        tool_names = {tool["name"] for tool in data["tools"]}
        assert tool_names == set(REGISTERED_TOOL_NAMES)
        inventory_tool = next(
            tool for tool in data["tools"] if tool["name"] == DATA_GET_INVENTORY_TOOL
        )
        quality_tool = next(
            tool
            for tool in data["tools"]
            if tool["name"] == DATA_SUMMARIZE_QUALITY_TOOL
        )
        ensure_tool = next(
            tool for tool in data["tools"] if tool["name"] == DATA_ENSURE_LOADED_TOOL
        )
        snapshot_tool = next(
            tool
            for tool in data["tools"]
            if tool["name"] == DATA_CREATE_RESEARCH_SNAPSHOT_TOOL
        )
        template_tool = next(
            tool
            for tool in data["tools"]
            if tool["name"] == RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL
        )
        implementation_tool = next(
            tool
            for tool in data["tools"]
            if tool["name"] == RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL
        )
        run_backtest_tool = next(
            tool
            for tool in data["tools"]
            if tool["name"] == RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL
        )
        get_backtest_tool = next(
            tool
            for tool in data["tools"]
            if tool["name"] == RESEARCH_GET_BACKTEST_RESULTS_TOOL
        )
        compare_tool = next(
            tool
            for tool in data["tools"]
            if tool["name"] == RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL
        )
        risk_template_tool = next(
            tool
            for tool in data["tools"]
            if tool["name"] == RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL
        )
        optimization_tool = next(
            tool
            for tool in data["tools"]
            if tool["name"] == RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL
        )
        performance_tool = next(
            tool
            for tool in data["tools"]
            if tool["name"]
            == EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL
        )
        assert inventory_tool["agent_owner"] == "Data Agent"
        assert inventory_tool["side_effect"] == "read_only"
        assert quality_tool["side_effect"] == "read_only"
        assert ensure_tool["side_effect"] == "local_mutating"
        assert snapshot_tool["agent_owner"] == "Data Agent"
        assert snapshot_tool["side_effect"] == "local_mutating"
        assert template_tool["agent_owner"] == "Strategy Engineering Agent"
        assert template_tool["side_effect"] == "read_only"
        assert implementation_tool["side_effect"] == "local_mutating"
        assert run_backtest_tool["agent_owner"] == "Quant Research Supervisor Agent"
        assert run_backtest_tool["side_effect"] == "local_mutating"
        assert get_backtest_tool["side_effect"] == "read_only"
        assert compare_tool["agent_owner"] == "Quant Research Supervisor Agent"
        assert compare_tool["side_effect"] == "local_mutating"
        assert risk_template_tool["agent_owner"] == "Strategy Engineering Agent"
        assert risk_template_tool["side_effect"] == "read_only"
        assert optimization_tool["agent_owner"] == "Quant Research Supervisor Agent"
        assert optimization_tool["side_effect"] == "local_mutating"
        assert performance_tool["agent_owner"] == "Evaluation Agent"
        assert performance_tool["side_effect"] == "local_mutating"
        assert {
            "research_create_strategy_candidate",
            "research_validate_strategy_candidate",
            "research_create_risk_manager_candidate",
            "research_run_backtest",
            "evaluation_generate_performance_report",
        }.isdisjoint(tool_names)
        assert data["policy"] == local_env.policy_flags()
        assert data["safety"] == {
            **CAPABILITY_REGISTRATION_FLAGS,
            "symbol_provider_discovery_allowed": local_env.allow_symbol_provider_discovery,
            "data_loading_mutation_allowed": local_env.allow_data_loading,
            "backtest_execution_allowed": local_env.allow_backtests,
            "optimization_execution_allowed": local_env.allow_optimization,
            "external_research_writes_allowed": local_env.allow_external_research_writes,
            "optuna_writes_allowed": local_env.allow_optuna_writes,
            "experiment_tracking_writes_allowed": local_env.allow_experiment_tracking_writes,
            "ml_runtime_allowed": local_env.allow_ml_runtime,
            "coding_workspace_allowed": local_env.allow_coding_workspace,
        }

    anyio.run(_run)
