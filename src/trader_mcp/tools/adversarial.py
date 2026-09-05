"""MCP registrations for independent Adversarial optimization review."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.protocol.adapters import result_to_mcp_result
from trader_mcp.catalogue.definitions import (
    ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
    ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
    ADVERSARIAL_TOOL_DESCRIPTIONS,
)
from trader_research.review import (
    create_parameter_optimization_audit_plan,
    generate_parameter_optimization_audit,
)
from trader_research.foundation import (
    ContextualResearchArtifactStore,
    ResearchArtifactStore,
)


ResearchArtifactStoreProvider = Callable[[], ResearchArtifactStore]


def register_adversarial_tools(
    server: FastMCP,
    *,
    artifact_store_provider: ResearchArtifactStoreProvider | None = None,
) -> None:
    """Register Adversarial planning and judgment as separate calls."""

    def _store(
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> ResearchArtifactStore | None:
        if (requested_by is None) != (actor is None):
            raise ValueError("requested_by and actor must be supplied together")
        if artifact_store_provider is None:
            return None
        store = artifact_store_provider()
        if requested_by is None and actor is None:
            return store
        assert requested_by is not None and actor is not None
        return ContextualResearchArtifactStore(
            store,
            requested_by=requested_by,
            actor=actor,
        )

    @server.tool(
        name=ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
        description=ADVERSARIAL_TOOL_DESCRIPTIONS[
            ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL
        ],
    )
    def adversarial_create_parameter_optimization_audit_plan(
        optimization_run_ref: str,
        attacks: list[dict[str, Any]] | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        envelope = create_parameter_optimization_audit_plan(
            optimization_run_ref=optimization_run_ref,
            attacks=attacks,
            artifact_store=_store(requested_by, actor),
        )
        return CallToolResult(**result_to_mcp_result(envelope))

    @server.tool(
        name=ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
        description=ADVERSARIAL_TOOL_DESCRIPTIONS[
            ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL
        ],
    )
    def adversarial_generate_parameter_optimization_audit(
        audit_plan_ref: str,
        variant_optimization_run_refs: list[str] | None = None,
        stress_backtest_run_refs: list[str] | None = None,
        requested_by: str | None = None,
        actor: str | None = None,
    ) -> CallToolResult:
        envelope = generate_parameter_optimization_audit(
            audit_plan_ref=audit_plan_ref,
            variant_optimization_run_refs=variant_optimization_run_refs,
            stress_backtest_run_refs=stress_backtest_run_refs,
            artifact_store=_store(requested_by, actor),
        )
        return CallToolResult(**result_to_mcp_result(envelope))
