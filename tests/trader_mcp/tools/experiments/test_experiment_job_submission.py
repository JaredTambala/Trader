"""MCP registration contract for approved experiment job admission.

Subject: Typed MCP command registration and fail-closed job-store authority.
Level: MCP tool integration contract.
Collaborators: FastMCP, in-memory artifact store, and the canonical handoff
service; no worker, producer, or Postgres.
Guarantees: The command is discoverable through the public catalogue, accepts
typed canonical references, and refuses admission when a durable job store is
not composed.
Non-goals: Approval construction, BacktestRunner execution, SQL locking, or
terminal job recovery.
"""

from __future__ import annotations

import anyio

from trader_mcp.catalogue.definitions import (
    REGISTERED_TOOL_NAMES,
    RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB_TOOL,
)
from trader_mcp.runtime.server import create_server
from trader_mcp.catalogue.policy import load_local_environment
from trader_research.foundation import InMemoryResearchArtifactStore
from trader_research.governance import artifact_report_ref


def test_approved_experiment_submission_is_registered_and_fail_closed_without_job_store() -> (
    None
):
    """An unconfigured runtime exposes the command but cannot admit work."""
    server = create_server(
        load_local_environment("env.template"),
        research_artifact_store_provider=InMemoryResearchArtifactStore,
    )

    async def _run() -> None:
        tools = await server.list_tools()
        assert RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB_TOOL in REGISTERED_TOOL_NAMES
        assert RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB_TOOL in {
            tool.name for tool in tools
        }
        result = await server.call_tool(
            RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB_TOOL,
            {
                "proposal_ref": artifact_report_ref(
                    "experiment_protocol_proposal", "proposal-1"
                ).to_dict(),
                "approved_protocol_ref": artifact_report_ref(
                    "experiment_protocol", "protocol-1"
                ).to_dict(),
                "requested_by": "workflow-1",
                "actor": "workflow_executor",
                "code_identity": "git:approved",
                "environment_identity": "env:test",
            },
        )
        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["ok"] is False
        assert result.structuredContent["errors"][0]["code"] == (
            "research_job_store_required"
        )

    anyio.run(_run)
