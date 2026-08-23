"""Build the resumable production Experiment Design specialist graph."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from trader_research.foundation import ResearchArtifactStore

from trader_agents.specialists import build_specialist_graph
from trader_agents.tool_client import McpToolClient

from .catalog import build_experiment_design_catalog
from .policy import ExperimentDesignPolicy


def build_experiment_design_graph(
    *,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    max_policy_decisions: int = 3,
    max_action_attempts: int = 1,
) -> Any:
    """Compile Experiment Design over one MCP-backed proposal action.

    Args:
        tool_client: MCP boundary for proposal persistence.
        artifact_store: Canonical store used to revalidate the returned proposal.
        checkpointer: Optional operational saver used for task resumption.
        max_policy_decisions: Maximum deterministic policy transitions.
        max_action_attempts: Maximum accepted registered actions.

    Returns:
        Compiled shared specialist graph scoped to Experiment Design authority.
    """
    return build_specialist_graph(
        catalog=build_experiment_design_catalog(
            tool_client=tool_client,
            artifact_store=artifact_store,
        ),
        policy=ExperimentDesignPolicy(),
        checkpointer=checkpointer,
        max_policy_decisions=max_policy_decisions,
        max_action_attempts=max_action_attempts,
    )
