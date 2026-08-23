"""Assemble the maintained specialist routes available to composition."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from trader_research.foundation import ResearchArtifactStore

from trader_agents.data_agent import build_data_specialist_route
from trader_agents.experiment_design_agent import build_experiment_design_route
from trader_agents.specialists import SpecialistRouteCatalog
from trader_agents.tool_client import McpToolClient


def build_research_composition_catalog(
    *,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
    checkpointer: BaseCheckpointSaver[Any],
) -> SpecialistRouteCatalog:
    """Build the production route catalog for resumable research composition.

    The catalog contains the production Data and Experiment Design specialists.
    Later authorities are added independently after their own graph contracts and
    deterministic tools are complete; composition never substitutes a fallback.

    Args:
        tool_client: MCP client injected into registered specialist handlers.
        artifact_store: Canonical store shared by specialists and composition.
        checkpointer: Operational saver shared by isolated child graph threads.

    Returns:
        Code-owned catalog containing the production Data and Design routes.
    """
    return SpecialistRouteCatalog(
        (
            build_data_specialist_route(
                tool_client=tool_client,
                artifact_store=artifact_store,
                checkpointer=checkpointer,
            ),
            build_experiment_design_route(
                tool_client=tool_client,
                artifact_store=artifact_store,
                checkpointer=checkpointer,
            ),
        )
    )
