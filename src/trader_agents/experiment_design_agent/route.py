"""Register the production Experiment Design graph with composition routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from trader_research.foundation import ResearchArtifactStore
from trader_research.governance import EXPERIMENT_PROTOCOL_PROPOSAL

from trader_agents.specialists import (
    RegisteredSpecialistRoute,
    SpecialistResult,
    SpecialistRouteDescriptor,
    SpecialistTask,
    run_specialist_task,
)
from trader_agents.tool_client import McpToolClient

from .domain import EXPERIMENT_DESIGN_AUTHORITY
from .graph import build_experiment_design_graph


EXPERIMENT_DESIGN_ROUTE_VERSION = "1"
"""Immutable assembly version for the production Experiment Design route."""


@dataclass(frozen=True)
class _ExperimentDesignRunner:
    """Adapt the shared graph state to the specialist routing protocol."""

    graph: Any

    async def run(self, task: SpecialistTask) -> SpecialistResult:
        """Execute or resume the exact task and return its bounded result."""
        state = await run_specialist_task(graph=self.graph, task=task)
        return SpecialistResult.from_dict(state.get("result", {}))


def build_experiment_design_route(
    *,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
    checkpointer: BaseCheckpointSaver[Any],
) -> RegisteredSpecialistRoute:
    """Build the Experiment Design route with runtime dependencies in code.

    Args:
        tool_client: MCP client used only by the registered proposal handler.
        artifact_store: Canonical store used to verify the proposal handoff.
        checkpointer: Operational saver used by the specialist graph.

    Returns:
        Route exposing only Design authority, version, and proposal output.
    """
    graph = build_experiment_design_graph(
        tool_client=tool_client,
        artifact_store=artifact_store,
        checkpointer=checkpointer,
    )
    return RegisteredSpecialistRoute(
        descriptor=SpecialistRouteDescriptor(
            authority_key=EXPERIMENT_DESIGN_AUTHORITY,
            version=EXPERIMENT_DESIGN_ROUTE_VERSION,
            supported_output_types=(EXPERIMENT_PROTOCOL_PROPOSAL,),
        ),
        runner=_ExperimentDesignRunner(graph),
    )
