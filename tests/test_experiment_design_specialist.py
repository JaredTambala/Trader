"""Test the resumable Experiment Design specialist over real MCP registration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import anyio
from langgraph.checkpoint.memory import InMemorySaver

from tests.test_experiment_design import _prepared_design
from trader_agents import (
    SpecialistResult,
    SpecialistResultStatus,
    build_experiment_design_graph,
    build_experiment_design_task,
    run_specialist_task,
)
from trader_mcp.constants import (
    RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.governance import EXPERIMENT_PROTOCOL_PROPOSAL


@dataclass
class _InProcessMcpClient:
    """Adapt an in-process FastMCP server and record public tool calls."""

    server: Any
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Call one registered tool and return its MCP-style public result."""
        args = dict(arguments)
        self.calls.append((tool_name, args))
        result = await self.server.call_tool(tool_name, args)
        return {
            "content": [],
            "structuredContent": dict(result.structuredContent or {}),
            "isError": bool(result.isError),
        }


def test_design_specialist_requests_proposal_persistence_permission() -> None:
    async def _run() -> None:
        store, objective, design = _prepared_design()
        server = create_server(
            load_local_environment("env.template"),
            research_artifact_store_provider=lambda: store,
        )
        client = _InProcessMcpClient(server)
        task = build_experiment_design_task(
            request=design,
            objective=objective,
            requested_by="composition_design_permission",
            actor="research_coordinator",
            permit_local_mutation=False,
        )
        graph = build_experiment_design_graph(
            tool_client=client,
            artifact_store=store,
            checkpointer=InMemorySaver(),
        )

        state = await run_specialist_task(graph=graph, task=task)
        result = SpecialistResult.from_dict(state["result"])
        assert result.status is SpecialistResultStatus.AWAITING_PREREQUISITE
        assert result.prerequisites[0].target == "local_mutating"
        assert client.calls == []

    anyio.run(_run)


def test_design_specialist_persists_once_and_resumes_without_replay() -> None:
    async def _run() -> None:
        store, objective, design = _prepared_design()
        server = create_server(
            load_local_environment("env.template"),
            research_artifact_store_provider=lambda: store,
        )
        client = _InProcessMcpClient(server)
        task = build_experiment_design_task(
            request=design,
            objective=objective,
            requested_by="composition_design_replay",
            actor="research_coordinator",
            permit_local_mutation=True,
        )
        graph = build_experiment_design_graph(
            tool_client=client,
            artifact_store=store,
            checkpointer=InMemorySaver(),
        )

        first = SpecialistResult.from_dict(
            (await run_specialist_task(graph=graph, task=task))["result"]
        )
        second = SpecialistResult.from_dict(
            (await run_specialist_task(graph=graph, task=task))["result"]
        )

        assert first.status is SpecialistResultStatus.COMPLETED
        assert second.to_dict() == first.to_dict()
        assert [name for name, _ in client.calls] == [
            RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL
        ]
        assert first.handoffs[0].artifact_type == EXPERIMENT_PROTOCOL_PROPOSAL
        assert first.handoffs[0].payload == {}
        assert set(first.handoffs[0].source_request) == {
            "task_id",
            "objective_id",
        }

    anyio.run(_run)
