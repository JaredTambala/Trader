from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import anyio

from trader_mcp.constants import (
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
    RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
    RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL,
    RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL,
    RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.artifact_store import InMemoryResearchArtifactStore
from trader_research.method_implementations.manifest import SIGNAL_RUNTIME_CONTRACT
from trader_research.methods.packages import MethodPackageManifest


def test_mcp_strategy_risk_stack_tools_create_and_validate(tmp_path: Path) -> None:
    environment = replace(load_local_environment("env.template"), artifact_root=tmp_path / "artifacts")
    artifact_store = InMemoryResearchArtifactStore()
    server = create_server(environment, research_artifact_store_provider=lambda: artifact_store)

    async def _run() -> None:
        tools = await server.list_tools()
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        strategy_created = await server.call_tool(
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
        strategy_validated = await server.call_tool(
            RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
            {
                "strategy_candidate_manifest": strategy_created.structuredContent["data"]["strategy_candidate_manifest"],
            },
        )
        risk_created = await server.call_tool(
            RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
            {
                "template_family": "gross_exposure_cap",
                "parameters": {"max_gross_exposure": 100_000.0},
            },
        )
        risk_validated = await server.call_tool(
            RESEARCH_VALIDATE_RISK_MANAGER_CANDIDATE_TOOL,
            {
                "risk_manager_candidate_manifest": risk_created.structuredContent["data"][
                    "risk_manager_candidate_manifest"
                ],
            },
        )
        stack_created = await server.call_tool(
            RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL,
            {
                "strategy_candidate_validation_report": strategy_validated.structuredContent["data"][
                    "strategy_candidate_validation_report"
                ],
                "risk_manager_validation_refs": [
                    {
                        "risk_manager_candidate_validation_report": risk_validated.structuredContent["data"][
                            "risk_manager_candidate_validation_report"
                        ]
                    }
                ],
            },
        )
        stack_validated = await server.call_tool(
            RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL,
            {
                "strategy_risk_stack_manifest": stack_created.structuredContent["data"][
                    "strategy_risk_stack_manifest"
                ],
            },
        )

        tool_names = {tool.name for tool in tools}
        assert tool_names == set(REGISTERED_TOOL_NAMES)
        assert RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL in tool_names
        assert RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL in tool_names
        config_tools = {tool["name"]: tool for tool in config.structuredContent["data"]["tools"]}
        assert config_tools[RESEARCH_CREATE_STRATEGY_RISK_STACK_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[RESEARCH_VALIDATE_STRATEGY_RISK_STACK_TOOL]["side_effect"] == "local_mutating"
        assert config.structuredContent["data"]["safety"]["strategy_risk_stack_tools_registered"] is True

        assert stack_created.isError is False
        stack_manifest = stack_created.structuredContent["data"]["strategy_risk_stack_manifest"]
        assert stack_manifest["risk_manager_refs"][0]["role"] == "risk_manager_0"
        assert stack_validated.isError is False
        stack_report = stack_validated.structuredContent["data"]["strategy_risk_stack_validation_report"]
        assert stack_report["status"] == "passed"
        assert stack_report["fixture_summary"]["risk_manager_count"] == 1

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
