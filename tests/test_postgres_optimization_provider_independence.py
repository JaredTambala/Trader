"""Task 57P core provider-independence qualification over stdio MCP."""

from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from trader.event_store import PostgresEventStore
from trader_mcp.constants import (
    MCP_CONFIG_TOOL,
    RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL,
    RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.support.optimization_qualification import prepare_optimization_qualification


@pytest.mark.postgres
def test_builtin_optimizers_and_canonical_reads_need_no_optional_providers(
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
    postgres_settings: dict[str, object],
) -> None:
    prepared = prepare_optimization_qualification(
        event_store=postgres_event_store,
        artifact_store=postgres_research_artifact_store,
        postgres_settings=postgres_settings,
    )

    partial = anyio.run(
        _call_in_fresh_server,
        RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
        {
            "optimization_plan_ref": prepared.optimization_plan_id,
            "optimizer_profile": "builtin_grid",
            "max_new_trials": 2,
        },
    )
    assert partial["data"]["parameter_optimization_run"]["status"] == "partial"

    completed_grid = anyio.run(
        _call_in_fresh_server,
        RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
        {
            "optimization_plan_ref": prepared.optimization_plan_id,
            "optimizer_profile": "builtin_grid",
        },
    )
    grid_run = completed_grid["data"]["parameter_optimization_run"]
    assert grid_run["status"] == "completed"

    completed_random = anyio.run(
        _call_in_fresh_server,
        RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
        {
            "optimization_plan_ref": prepared.optimization_plan_id,
            "optimizer_profile": "builtin_random",
        },
    )
    random_run = completed_random["data"]["parameter_optimization_run"]
    assert random_run["status"] == "completed"
    assert random_run["optimization_run_id"] != grid_run["optimization_run_id"]

    for run in (grid_run, random_run):
        results = anyio.run(
            _call_in_fresh_server,
            RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
            {"optimization_run_ref": run["optimization_run_id"]},
        )
        assert results["data"]["parameter_optimization_run"] == run
        assert len(results["data"]["trials"]) == 4


async def _call_in_fresh_server(
    tool_name: str,
    arguments: Mapping[str, Any],
) -> Mapping[str, Any]:
    async with stdio_client(_server_parameters()) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=180),
        ) as session:
            await session.initialize()
            config = await _call(session, MCP_CONFIG_TOOL, {})
            safety = config["data"]["safety"]
            assert safety["backtest_execution_allowed"] is True
            assert safety["optimization_execution_allowed"] is True
            assert safety["external_research_writes_allowed"] is False
            assert safety["optuna_writes_allowed"] is False
            assert safety["experiment_tracking_writes_allowed"] is False
            runtime = await _call(session, RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL, {})
            profiles = {
                profile["profile_name"]: profile
                for profile in runtime["data"]["profiles"]
            }
            assert set(profiles) == {"builtin_grid", "builtin_random"}
            assert all(profile["available"] is True for profile in profiles.values())
            return await _call(session, tool_name, arguments)


async def _call(
    session: ClientSession,
    tool_name: str,
    arguments: Mapping[str, Any],
) -> Mapping[str, Any]:
    result = await session.call_tool(tool_name, dict(arguments))
    assert result.structuredContent is not None
    payload = result.structuredContent
    assert result.isError is False, payload.get("errors")
    assert payload["ok"] is True, payload.get("errors")
    assert payload["command"] == tool_name
    assert json.loads(result.content[0].text) == payload
    return payload


def _server_parameters() -> StdioServerParameters:
    repo_root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    source_path = str(repo_root / "src")
    environment["PYTHONPATH"] = (
        f"{repo_root}{os.pathsep}{source_path}{os.pathsep}"
        f"{environment.get('PYTHONPATH', '')}"
    )
    environment.update(
        {
            "TRADER_MCP_TRADER_CONFIG_PATH": "",
            "TRADER_MCP_ALLOW_BROKER_MUTATION": "false",
            "TRADER_MCP_ALLOW_RAW_SQL": "false",
            "TRADER_MCP_ALLOW_SYMBOL_PROVIDER_DISCOVERY": "false",
            "TRADER_MCP_ALLOW_DATA_LOADING": "false",
            "TRADER_MCP_ALLOW_BACKTESTS": "true",
            "TRADER_MCP_ALLOW_OPTIMIZATION": "true",
            "TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES": "false",
            "TRADER_MCP_ALLOW_OPTUNA_WRITES": "false",
            "TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES": "false",
        }
    )
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "tests.support.mcp_postgres_no_optional_server"],
        cwd=repo_root,
        env=environment,
    )
