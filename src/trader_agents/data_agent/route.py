"""Register the production Data specialist with composition routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from trader_research.foundation import ResearchArtifactStore
from trader_research.governance import DATASET_MANIFEST, DATA_QUALITY_REPORT

from trader_agents.specialists import (
    RegisteredSpecialistRoute,
    SpecialistResult,
    SpecialistRouteDescriptor,
    SpecialistTask,
    run_specialist_task,
)
from trader_agents.tool_client import McpToolClient

from .domain import DATA_SPECIALIST_AUTHORITY
from .graph import build_data_specialist_graph


DATA_SPECIALIST_ROUTE_VERSION = "1"
"""Immutable assembly version for the production Data specialist route."""


@dataclass(frozen=True)
class _DataSpecialistRunner:
    graph: Any

    async def run(self, task: SpecialistTask) -> SpecialistResult:
        state = await run_specialist_task(graph=self.graph, task=task)
        return SpecialistResult.from_dict(state.get("result", {}))


def build_data_specialist_route(
    *,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
    checkpointer: BaseCheckpointSaver[Any],
) -> RegisteredSpecialistRoute:
    """Build the Data route with all runtime dependencies injected in code.

    Args:
        tool_client: MCP client used only by registered Data action handlers.
        artifact_store: Canonical store used to verify Data handoffs.
        checkpointer: Operational saver used by the specialist graph.

    Returns:
        A route registration exposing only Data authority, version, and outputs.
    """
    graph = build_data_specialist_graph(
        tool_client=tool_client,
        artifact_store=artifact_store,
        checkpointer=checkpointer,
    )
    return RegisteredSpecialistRoute(
        descriptor=SpecialistRouteDescriptor(
            authority_key=DATA_SPECIALIST_AUTHORITY,
            version=DATA_SPECIALIST_ROUTE_VERSION,
            supported_output_types=(DATASET_MANIFEST, DATA_QUALITY_REPORT),
        ),
        runner=_DataSpecialistRunner(graph),
    )
