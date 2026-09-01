"""MCP contracts for first-slice session and canonical-evidence tools."""

from __future__ import annotations

import anyio

from trader_mcp.constants import (
    RESEARCH_CREATE_AGENT_SESSION_TOOL,
    RESEARCH_GET_AGENT_SESSION_TOOL,
    RESEARCH_READ_ARTIFACT_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.foundation import InMemoryResearchArtifactStore
from trader_research.governance import AgentBudget, ResearchSession


def test_agentic_tools_fail_closed_without_canonical_store() -> None:
    server = create_server(load_local_environment("env.template"))

    async def _run() -> None:
        result = await server.call_tool(
            RESEARCH_GET_AGENT_SESSION_TOOL,
            {"session_ref": "session-missing"},
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["agent_owner"] == "Research Coordinator"
        assert result.structuredContent["side_effect"] == "read_only"
        assert result.structuredContent["errors"][0]["code"] == (
            "agent_session_resolution_failed"
        )

    anyio.run(_run)


def test_agentic_tools_persist_and_resolve_exact_session() -> None:
    store = InMemoryResearchArtifactStore()
    server = create_server(
        load_local_environment("env.template"),
        research_artifact_store_provider=lambda: store,
    )
    session = _session()

    async def _run() -> None:
        created = await server.call_tool(
            RESEARCH_CREATE_AGENT_SESSION_TOOL,
            {"session": session.to_dict()},
        )
        resolved = await server.call_tool(
            RESEARCH_GET_AGENT_SESSION_TOOL,
            {"session_ref": session.session_id},
        )
        read = await server.call_tool(
            RESEARCH_READ_ARTIFACT_TOOL,
            {
                "artifact_ref": session.session_id,
                "expected_artifact_type": "research_session",
            },
        )

        assert created.isError is False
        assert created.structuredContent is not None
        assert created.structuredContent["side_effect"] == "local_mutating"
        assert resolved.isError is False
        assert resolved.structuredContent is not None
        assert resolved.structuredContent["data"]["research_session"][
            "session_digest"
        ] == session.session_digest
        assert read.isError is False

    anyio.run(_run)


def _session() -> ResearchSession:
    return ResearchSession(
        session_id="session-mcp-demo",
        objective="Prepare bounded research inputs.",
        success_definition="Return exact evidence.",
        operator_id="operator-demo",
        approval_policy={"broker_mutation": False},
        scope_envelope={"symbols": ["AAA"]},
        implementation_specification={"implementation_kind": "strategy"},
        implementation_ref=None,
        python_quality_guide="docs/python_code_quality.md",
        model_profile_id="model-v1",
        agent_program_ids=("coordinator-v1",),
        tool_catalog_id="catalog-v1",
        budget=AgentBudget(4, 8, 4_000, 120, 1, 1, 1),
    )
