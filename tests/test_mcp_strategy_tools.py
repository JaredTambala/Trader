from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio

from trader_mcp.constants import (
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
    RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_GET_BACKTEST_RESULTS_TOOL,
    RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL,
    RESEARCH_RUN_BACKTEST_TOOL,
    RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.method_implementations.manifest import SIGNAL_RUNTIME_CONTRACT
from trader_research.methods.packages import MethodPackageManifest


def test_mcp_strategy_candidate_tools_list_create_and_validate(tmp_path: Path) -> None:
    environment = replace(load_local_environment("env.template"), artifact_root=tmp_path / "artifacts")
    server = create_server(environment)

    async def _run() -> None:
        tools = await server.list_tools()
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        catalog = await server.call_tool(RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL, {})
        created = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
            {
                "template_family": "bollinger_band",
                "method_package_refs": [
                    {"role": "bollinger_band_signal", "package_manifest": _signal_package("method_package_bollinger")}
                ],
                "parameters": {"period": 20, "stddev_multiplier": 2.0},
                "sizing": {"target_qty_when_long": 1.0, "max_position_qty": 5.0},
            },
        )
        candidate = created.structuredContent["data"]["strategy_candidate_manifest"]
        validated = await server.call_tool(
            RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
            {"strategy_candidate_manifest": candidate},
        )

        tool_names = {tool.name for tool in tools}
        assert tool_names == set(REGISTERED_TOOL_NAMES)
        assert RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL in tool_names
        assert RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL in tool_names
        assert RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL in tool_names
        assert RESEARCH_RUN_BACKTEST_TOOL in tool_names
        assert RESEARCH_GET_BACKTEST_RESULTS_TOOL in tool_names

        config_tools = {tool["name"]: tool for tool in config.structuredContent["data"]["tools"]}
        assert config_tools[RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL]["agent_owner"] == "Quant Research Supervisor Agent"
        assert config_tools[RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL]["side_effect"] == "read_only"
        assert config_tools[RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL]["agent_owner"] == "Quant Research Supervisor Agent"
        assert config_tools[RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL]["agent_owner"] == (
            "Quant Research Supervisor Agent"
        )
        assert config_tools[RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL]["side_effect"] == "local_mutating"
        assert config.structuredContent["data"]["safety"]["strategy_candidate_tools_registered"] is True
        assert config.structuredContent["data"]["safety"]["backtest_tools_registered"] is True
        assert config.structuredContent["data"]["safety"]["backtest_execution_allowed"] is False

        assert catalog.isError is False
        assert catalog.structuredContent["data"]["template_count"] == 3
        assert created.isError is False
        assert candidate["template_family"] == "bollinger_band"
        assert candidate["strategy_source"]["runtime_contract"] == "trader.strategies.Strategy"
        assert Path(candidate["strategy_source"]["path"]).exists()
        assert validated.isError is False
        report = validated.structuredContent["data"]["strategy_candidate_validation_report"]
        assert report["status"] == "passed"
        assert report["candidate_id"] == candidate["candidate_id"]
        assert "strategy_candidate_validation_report" in validated.structuredContent["artifacts"]

    anyio.run(_run)


def _signal_package(package_id: str) -> dict[str, Any]:
    return MethodPackageManifest(
        package_id=package_id,
        method_id=f"method_{package_id}",
        runtime_contract=SIGNAL_RUNTIME_CONTRACT,
        implementation_id=f"implementation_{package_id}",
        entrypoint=f"trader_standard.signals:{package_id}",
        class_name="DemoSignal",
        source_path=f"src/trader_standard/signals/{package_id}.py",
        source_hash=f"hash_{package_id}",
        source_provenance={"kind": "validated_fixture"},
        constructor_kwargs={},
        method_contract={"method_id": f"method_{package_id}"},
        method_card_ids=("method_card_bollinger_band",),
        validation_report_ref={
            "artifact_type": "signal_implementation_validation_report",
            "validation_id": f"validation_{package_id}",
            "status": "passed",
            "path": f"artifacts/research/validations/{package_id}.json",
        },
        validation_summary={"status": "passed", "fixture_count": 1},
        safety_profile={"imports": "static_allowlist"},
        dependency_allowlist=("trader", "trader_standard"),
    ).to_dict()
