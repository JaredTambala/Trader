from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import anyio

from trader_mcp.constants import (
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
    RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL,
    RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.artifact_store import InMemoryResearchArtifactStore


def test_mcp_risk_manager_tools_list_and_create(tmp_path: Path) -> None:
    environment = replace(load_local_environment("env.template"), artifact_root=tmp_path / "artifacts")
    artifact_store = InMemoryResearchArtifactStore()
    server = create_server(environment, research_artifact_store_provider=lambda: artifact_store)

    async def _run() -> None:
        tools = await server.list_tools()
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        catalog = await server.call_tool(RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL, {})
        created = await server.call_tool(
            RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
            {
                "template_family": "gross_exposure_cap",
                "parameters": {"max_gross_exposure": 100_000.0},
            },
        )
        validated = await server.call_tool(
            RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL,
            {
                "risk_manager_candidate_manifest": created.structuredContent["data"]["risk_manager_candidate_manifest"],
            },
        )

        tool_names = {tool.name for tool in tools}
        assert tool_names == set(REGISTERED_TOOL_NAMES)
        assert RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL in tool_names
        assert RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL in tool_names
        assert RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL in tool_names

        config_tools = {tool["name"]: tool for tool in config.structuredContent["data"]["tools"]}
        assert config_tools[RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL]["agent_owner"] == (
            "Quant Research Supervisor Agent"
        )
        assert config_tools[RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL]["side_effect"] == "read_only"
        assert config_tools[RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL]["agent_owner"] == (
            "Quant Research Supervisor Agent"
        )
        assert config_tools[RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL]["side_effect"] == "local_mutating"
        assert config.structuredContent["data"]["safety"]["risk_manager_candidate_tools_registered"] is True
        assert config.structuredContent["data"]["safety"]["risk_manager_validation_tools_registered"] is True

        assert catalog.isError is False
        assert catalog.structuredContent["data"]["template_count"] == 5
        assert created.isError is False
        manifest = created.structuredContent["data"]["risk_manager_candidate_manifest"]
        assert manifest["template_family"] == "gross_exposure_cap"
        assert manifest["risk_manager_source"]["runtime_contract"] == "trader.risk.RiskManager"
        assert manifest["risk_manager_source"]["path"] is None
        assert manifest["risk_manager_source"]["uri"].startswith("research://postgres/risk_manager_implementation/")
        assert "risk_manager_candidate" in created.structuredContent["artifacts"]
        assert "risk_manager_source" in created.structuredContent["artifacts"]
        assert validated.isError is False
        report = validated.structuredContent["data"]["risk_manager_candidate_validation_report"]
        assert report["status"] == "passed"
        assert "risk_manager_candidate_validation_report" in validated.structuredContent["artifacts"]

    anyio.run(_run)
