"""MCP adapters for model-backed research session governance."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.adapters import result_to_mcp_result
from trader_mcp.constants import (
    AGENTIC_TOOL_DESCRIPTIONS,
    RESEARCH_CREATE_AGENT_SESSION_TOOL,
    RESEARCH_GET_AGENT_DECISION_TOOL,
    RESEARCH_GET_AGENT_SESSION_TOOL,
    RESEARCH_READ_ARTIFACT_TOOL,
    RESEARCH_RECORD_AGENT_DECISION_TOOL,
)
from trader_research.foundation import ResearchArtifactStore
from trader_research.governance import (
    create_agent_session,
    get_agent_decision,
    get_agent_session,
    read_canonical_artifact,
    record_agent_decision,
)


ResearchArtifactStoreProvider = Callable[[], ResearchArtifactStore]


def register_agentic_tools(
    server: FastMCP,
    *,
    artifact_store_provider: ResearchArtifactStoreProvider | None,
) -> None:
    """Register first-slice session, receipt, and canonical-read operations.

    Args:
        server: FastMCP server receiving the tool registrations.
        artifact_store_provider: Lazy canonical store provider, or ``None`` to
            expose structured fail-closed results.
    """

    def _store() -> ResearchArtifactStore | None:
        return (
            artifact_store_provider()
            if artifact_store_provider is not None
            else None
        )

    def _result(result: Any) -> CallToolResult:
        return CallToolResult(**result_to_mcp_result(result))

    @server.tool(
        name=RESEARCH_CREATE_AGENT_SESSION_TOOL,
        description=AGENTIC_TOOL_DESCRIPTIONS[RESEARCH_CREATE_AGENT_SESSION_TOOL],
    )
    def research_create_agent_session(session: dict[str, Any]) -> CallToolResult:
        """Persist one strict operator-approved research session."""
        return _result(create_agent_session(session, artifact_store=_store()))

    @server.tool(
        name=RESEARCH_GET_AGENT_SESSION_TOOL,
        description=AGENTIC_TOOL_DESCRIPTIONS[RESEARCH_GET_AGENT_SESSION_TOOL],
    )
    def research_get_agent_session(session_ref: str) -> CallToolResult:
        """Resolve one exact immutable research session."""
        return _result(get_agent_session(session_ref, artifact_store=_store()))

    @server.tool(
        name=RESEARCH_RECORD_AGENT_DECISION_TOOL,
        description=AGENTIC_TOOL_DESCRIPTIONS[RESEARCH_RECORD_AGENT_DECISION_TOOL],
    )
    def research_record_agent_decision(
        receipt: dict[str, Any],
    ) -> CallToolResult:
        """Persist one append-only public coordinator decision receipt."""
        return _result(record_agent_decision(receipt, artifact_store=_store()))

    @server.tool(
        name=RESEARCH_GET_AGENT_DECISION_TOOL,
        description=AGENTIC_TOOL_DESCRIPTIONS[RESEARCH_GET_AGENT_DECISION_TOOL],
    )
    def research_get_agent_decision(receipt_ref: str) -> CallToolResult:
        """Resolve one exact public decision receipt."""
        return _result(get_agent_decision(receipt_ref, artifact_store=_store()))

    @server.tool(
        name=RESEARCH_READ_ARTIFACT_TOOL,
        description=AGENTIC_TOOL_DESCRIPTIONS[RESEARCH_READ_ARTIFACT_TOOL],
    )
    def research_read_artifact(
        artifact_ref: str,
        expected_artifact_type: str,
        max_payload_bytes: int = 64_000,
        include_payload: bool = True,
    ) -> CallToolResult:
        """Read one exact size-bounded canonical artifact."""
        return _result(
            read_canonical_artifact(
                artifact_ref,
                expected_artifact_type,
                artifact_store=_store(),
                max_payload_bytes=max_payload_bytes,
                include_payload=include_payload,
            )
        )
