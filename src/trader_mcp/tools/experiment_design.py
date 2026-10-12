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
    RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB_TOOL,
    RESEARCH_TOOL_DESCRIPTIONS,
)
from trader_research.foundation import (
    ContextualResearchArtifactStore,
    ResearchArtifactStore,
)
from trader_research.governance import (
    ArtifactReportRef,
    ResearchJobStore,
    create_experiment_protocol_proposal,
    record_workflow_outcome,
    register_experiment_workflow,
)
from trader_research.experiments import submit_approved_experiment_job


ResearchArtifactStoreProvider = Callable[[], ResearchArtifactStore]
ResearchJobStoreProvider = Callable[[], ResearchJobStore]


def register_orchestration_tools(
    server: FastMCP,
    *,
    artifact_store_provider: ResearchArtifactStoreProvider,
    job_store_provider: ResearchJobStoreProvider | None = None,
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

    def _job_store() -> ResearchJobStore | None:
        """Resolve the durable job store or fail closed when unconfigured."""
        return job_store_provider() if job_store_provider is not None else None

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

    @server.tool(
        name=RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB_TOOL,
        description=RESEARCH_TOOL_DESCRIPTIONS[
            RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB_TOOL
        ],
    )
    def research_submit_approved_experiment_job(
        proposal_ref: dict[str, Any],
        approved_protocol_ref: dict[str, Any],
        requested_by: str,
        actor: str,
        code_identity: str,
        environment_identity: str,
    ) -> CallToolResult:
        """Admit one exact approved protocol to the durable job boundary."""
        try:
            result = submit_approved_experiment_job(
                proposal_ref=ArtifactReportRef.from_dict(proposal_ref),
                approved_protocol_ref=ArtifactReportRef.from_dict(
                    approved_protocol_ref
                ),
                requested_by=requested_by,
                actor=actor,
                code_identity=code_identity,
                environment_identity=environment_identity,
                artifact_store=_store(requested_by, actor),
                job_store=_job_store(),
            )
        except (TypeError, ValueError) as exc:
            from trader_research.foundation import error_result

            result = error_result(
                command=RESEARCH_SUBMIT_APPROVED_EXPERIMENT_JOB_TOOL,
                code="validation_error",
                message=str(exc),
            )
        return CallToolResult(**result_to_mcp_result(result))
