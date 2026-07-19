from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

import anyio

from trader_agents.data_agent import build_data_agent_quality_graph
from trader_agents.quant_research import data_agent_handoffs_from_state, build_quant_research_supervisor_graph
from trader_agents.state import build_data_agent_initial_state, build_quant_research_supervisor_initial_state
from trader_agents.tool_client import StdioMcpToolClient
from trader_mcp.constants import DATA_DISCOVER_SYMBOLS_TOOL, DATA_GET_INVENTORY_TOOL, DATA_SUMMARIZE_QUALITY_TOOL
from trader_research.governance.artifacts import (
    DATASET_MANIFEST,
    DATA_QUALITY_REPORT,
)


def test_supervisor_consumes_data_agent_graph_handoff_without_fetching_raw_data() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{repo_root / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env["TRADER_MCP_TRADER_CONFIG_PATH"] = ""
    client = StdioMcpToolClient(
        command=sys.executable,
        args=["-m", "tests.support.mcp_sample_inventory_server"],
        cwd=repo_root,
        env=env,
        read_timeout_seconds=10,
    )
    data_graph = build_data_agent_quality_graph(client)
    supervisor_graph = build_quant_research_supervisor_graph()

    async def _run() -> None:
        data_output = await data_graph.ainvoke(_data_state())
        handoffs = data_agent_handoffs_from_state(data_output)
        supervisor_state = build_quant_research_supervisor_initial_state(
            objective="Evaluate sample trend-following idea.",
            symbols=("DEMO",),
            asset_class="stocks",
            timeframe="1Min",
            start="2026-01-20T12:00:00Z",
            end="2026-01-20T12:11:00Z",
            incoming_handoffs=handoffs,
        )
        output = await supervisor_graph.ainvoke(supervisor_state)

        blocker_codes = {blocker["code"] for blocker in output["blockers"]}
        serialized = json.dumps(output, sort_keys=True)
        assert data_output["called_tools"] == [
            DATA_DISCOVER_SYMBOLS_TOOL,
            DATA_GET_INVENTORY_TOOL,
            DATA_SUMMARIZE_QUALITY_TOOL,
        ]
        assert len(handoffs) == 2
        assert output["status"] == "blocked"
        assert output["data_manifest"]["dataset_id"] == data_output["dataset_manifest"]["dataset_id"]
        assert output["data_quality_report"]["report_id"] == data_output["quality_report"]["report_id"]
        assert output["artifact_slots"][DATASET_MANIFEST]["handoff"]["agent_owner"] == "Data Agent"
        assert output["artifact_slots"][DATA_QUALITY_REPORT]["handoff"]["agent_owner"] == "Data Agent"
        assert "missing_indicator_metadata" in blocker_codes
        assert "missing_hypothesis_card" in blocker_codes
        assert "missing_evaluation_report" in blocker_codes
        assert "missing_robustness_report" in blocker_codes
        assert output["called_tools"] == []
        assert "raw_bars" not in serialized
        assert "trades" not in serialized

    anyio.run(_run)


def _data_state() -> dict[str, Any]:
    return build_data_agent_initial_state(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start="2026-01-20T12:00:00Z",
        end="2026-01-20T12:11:00Z",
    )
