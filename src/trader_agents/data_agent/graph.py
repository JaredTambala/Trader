"""Build the resumable production Data specialist graph."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from trader_research.foundation import ResearchArtifactStore

from trader_agents.specialists import build_specialist_graph
from trader_agents.tool_client import McpToolClient

from .catalog import build_data_specialist_catalog
from .policy import DataSpecialistPolicy


def build_data_specialist_graph(
    *,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    max_policy_decisions: int = 5,
    max_action_attempts: int = 3,
) -> Any:
    """Compile the Data specialist over MCP-backed registered actions.

    Args:
        tool_client: MCP boundary for discovery, loading, and snapshot actions.
        artifact_store: Canonical store used to revalidate snapshot references.
        checkpointer: Optional operational saver used for task resumption.
        max_policy_decisions: Maximum deterministic policy transitions.
        max_action_attempts: Maximum accepted registered actions.

    Returns:
        Compiled shared specialist graph scoped to Data authority.
    """
    return build_specialist_graph(
        catalog=build_data_specialist_catalog(
            tool_client=tool_client,
            artifact_store=artifact_store,
        ),
        policy=DataSpecialistPolicy(),
        checkpointer=checkpointer,
        max_policy_decisions=max_policy_decisions,
        max_action_attempts=max_action_attempts,
    )
