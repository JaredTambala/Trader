"""Register protocol-proposal and workflow-evidence MCP operations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.protocol.adapters import result_to_mcp_result
from trader_mcp.catalogue.definitions import (
    EXPERIMENT_DESIGN_TOOL_DESCRIPTIONS,
    RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL,
    RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
    RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
    RESEARCH_TOOL_DESCRIPTIONS,
)
from trader_research.foundation import (
    ContextualResearchArtifactStore,
    ResearchArtifactStore,
)
from trader_research.governance import (
    create_experiment_protocol_proposal,
    record_workflow_outcome,
    register_experiment_workflow,
)


ResearchArtifactStoreProvider = Callable[[], ResearchArtifactStore]


def register_orchestration_tools(
    server: FastMCP,
    *,
    artifact_store_provider: ResearchArtifactStoreProvider,
) -> None:
    """Register proposal, workflow-contract, and outcome persistence tools."""

    def _store(
        requested_by: str,
        actor: str,
    ) -> ContextualResearchArtifactStore:
        return ContextualResearchArtifactStore(
            artifact_store_provider(),
            requested_by=requested_by,
            actor=actor,
        )

    @server.tool(
        name=RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL,
        description=EXPERIMENT_DESIGN_TOOL_DESCRIPTIONS[
            RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL
        ],
    )
    def research_create_experiment_protocol_proposal(
        objective: dict[str, Any],
        design_request: dict[str, Any],
        task_id: str,
        requested_by: str,
        actor: str,
    ) -> CallToolResult:
        """Persist one proposal after canonical input and identity validation."""
        result = create_experiment_protocol_proposal(
            objective=objective,
            design_request=design_request,
            task_id=task_id,
            requested_by=requested_by,
            actor=actor,
            artifact_store=_store(requested_by, actor),
        )
        return CallToolResult(**result_to_mcp_result(result))

    @server.tool(
        name=RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL
        ],
    )
    def research_register_experiment_workflow(
        objective: dict[str, Any],
        protocol: dict[str, Any],
        workflow_plan: dict[str, Any],
        requested_by: str,
        actor: str,
    ) -> CallToolResult:
        result = register_experiment_workflow(
            objective=objective,
            protocol=protocol,
            workflow_plan=workflow_plan,
            artifact_store=_store(requested_by, actor),
        )
        return CallToolResult(**result_to_mcp_result(result))

    @server.tool(
        name=RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL],
    )
    def research_record_workflow_outcome(
        outcome: dict[str, Any],
        requested_by: str,
        actor: str,
    ) -> CallToolResult:
        result = record_workflow_outcome(
            outcome=outcome,
            artifact_store=_store(requested_by, actor),
        )
        return CallToolResult(**result_to_mcp_result(result))
