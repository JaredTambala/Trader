"""Run or resume the bounded research-composition control loop."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver

from trader_research.foundation import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    json_payload_hash,
)
from trader_research.governance import (
    ArtifactReportRef,
    ExperimentProtocol,
    ExperimentProtocolStatus,
)

from trader_agents.research_coordinator import (
    WorkflowTemplateCatalog,
    default_workflow_template_catalog,
)
from trader_agents.specialists import (
    AcceptedSpecialistResult,
    SpecialistRouteCatalog,
    specialist_task_digest,
)
from trader_agents.tool_client import McpToolClient

from .catalog import build_research_composition_catalog
from .domain import (
    MAX_COMPOSITION_TRANSITIONS,
    ResearchCompositionRequest,
    ResearchCompositionState,
    build_research_composition_initial_state,
    protocol_design_digest,
    protocol_digest,
    research_composition_digest,
    research_composition_thread_config,
)
from .graph import build_research_composition_graph
from .validation import (
    revalidate_accepted_specialist_results,
    revalidate_composition_outcome,
    resolve_accepted_protocol_proposal,
    validate_protocol_matches_proposal,
)


_TERMINAL_STATUSES = frozenset({"completed", "blocked", "failed"})
_PAUSED_STATUSES = frozenset(
    {"awaiting_prerequisite", "awaiting_approval", "interrupted"}
)


class ResearchCompositionConflictError(RuntimeError):
    """Raised when an existing composition thread is reused with changed input."""


async def run_research_composition(
    *,
    request: ResearchCompositionRequest,
    protocol: ExperimentProtocol | None,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
    checkpointer: BaseCheckpointSaver[Any],
    specialist_catalog: SpecialistRouteCatalog | None = None,
    workflow_catalog: WorkflowTemplateCatalog | None = None,
    max_workflow_tool_calls: int | None = None,
    max_transitions: int = MAX_COMPOSITION_TRANSITIONS,
) -> ResearchCompositionState:
    """Run or resume one composition until it pauses or reaches terminal state.

    The caller resupplies the exact immutable request on every invocation. A
    protocol may be absent initially, may advance from the same proposed design
    to approved, and is immutable after approval. Exact terminal replay returns
    saved state before constructing a specialist or workflow call.

    Args:
        request: Exact approved objective and ordered explicit specialist tasks.
        protocol: Optional proposed or approved operator-owned experiment design.
        tool_client: MCP boundary shared by registered routes and workflow execution.
        artifact_store: Canonical store shared with the MCP server.
        checkpointer: Operational saver for composition and isolated child threads.
        specialist_catalog: Optional injected Data and Design route catalog.
        workflow_catalog: Optional injected fixed workflow-template catalog.
        max_workflow_tool_calls: Optional deliberate pause after this many workflow
            step calls during the current invocation.
        max_transitions: Maximum checkpointed parent transitions.

    Returns:
        Latest bounded composition checkpoint state.

    Raises:
        ResearchCompositionConflictError: If request or protocol content drifts on
            an existing thread.
        ValueError: If execution budgets are invalid.
    """
    if max_transitions <= 0:
        raise ValueError("max_transitions must be positive")
    if max_workflow_tool_calls is not None and max_workflow_tool_calls < 0:
        raise ValueError("max_workflow_tool_calls cannot be negative")
    selected_specialists = specialist_catalog or build_research_composition_catalog(
        tool_client=tool_client,
        artifact_store=artifact_store,
        checkpointer=checkpointer,
    )
    selected_workflows = workflow_catalog or default_workflow_template_catalog()
    config = research_composition_thread_config(request.composition_id)
    graph = build_research_composition_graph(
        request=request,
        protocol=protocol,
        specialist_catalog=selected_specialists,
        workflow_catalog=selected_workflows,
        tool_client=tool_client,
        artifact_store=artifact_store,
        checkpointer=checkpointer,
        max_workflow_tool_calls=max_workflow_tool_calls,
        max_transitions=max_transitions,
    )
    snapshot = await graph.aget_state(config)
    if snapshot.values:
        state = cast(ResearchCompositionState, dict(snapshot.values))
        _validate_resume_request(state, request)
        _validate_resume_protocol(state, request, protocol)
        _validate_resume_evidence(
            state=state,
            request=request,
            protocol=protocol,
            specialist_catalog=selected_specialists,
            artifact_store=artifact_store,
        )
        status = str(state.get("status") or "")
        if status in _TERMINAL_STATUSES:
            return state
        if status in _PAUSED_STATUSES and not _input_can_resume(state, protocol):
            return state
        graph_input: ResearchCompositionState = {}
    else:
        state = build_research_composition_initial_state(request)
        graph_input = state

    while True:
        state = cast(
            ResearchCompositionState,
            dict(await graph.ainvoke(graph_input, config)),
        )
        status = str(state.get("status") or "")
        if status != "running":
            return state
        graph_input = {}


def _validate_resume_request(
    state: ResearchCompositionState,
    request: ResearchCompositionRequest,
) -> None:
    expected_tasks = {
        task.task_id: specialist_task_digest(task) for task in request.specialist_tasks
    }
    if (
        state.get("composition_id") != request.composition_id
        or state.get("request_digest") != research_composition_digest(request)
        or state.get("objective_id") != request.objective.objective_id
        or state.get("objective_digest")
        != json_payload_hash(request.objective.to_dict())
        or state.get("task_digests") != expected_tasks
    ):
        raise ResearchCompositionConflictError(
            "composition checkpoint does not match the supplied request"
        )


def _validate_resume_protocol(
    state: ResearchCompositionState,
    request: ResearchCompositionRequest,
    protocol: ExperimentProtocol | None,
) -> None:
    if protocol is None:
        return
    if protocol.objective_id != request.objective.objective_id:
        raise ResearchCompositionConflictError(
            "composition protocol objective does not match the request"
        )
    saved_id = str(state.get("protocol_id") or "")
    if saved_id and saved_id != protocol.protocol_id:
        raise ResearchCompositionConflictError("composition protocol identity drift")
    saved_design = str(state.get("protocol_design_digest") or "")
    if saved_design and saved_design != protocol_design_digest(protocol):
        raise ResearchCompositionConflictError("composition protocol design drift")
    saved_approved = str(state.get("accepted_protocol_digest") or "")
    if saved_approved:
        if protocol.status is not ExperimentProtocolStatus.APPROVED:
            raise ResearchCompositionConflictError(
                "an accepted protocol cannot return to a non-approved status"
            )
        if saved_approved != protocol_digest(protocol):
            raise ResearchCompositionConflictError(
                "composition approved protocol content drift"
            )


def _input_can_resume(
    state: ResearchCompositionState,
    protocol: ExperimentProtocol | None,
) -> bool:
    status = str(state.get("status") or "")
    if status == "interrupted":
        return protocol is not None
    if protocol is None:
        return False
    if status == "awaiting_approval":
        return protocol.status is ExperimentProtocolStatus.APPROVED
    if status == "awaiting_prerequisite":
        prerequisites = state.get("prerequisites", [])
        return any(
            isinstance(item, dict) and item.get("target") == "experiment_protocol"
            for item in prerequisites
        )
    return True


def _validate_resume_evidence(
    *,
    state: ResearchCompositionState,
    request: ResearchCompositionRequest,
    protocol: ExperimentProtocol | None,
    specialist_catalog: SpecialistRouteCatalog,
    artifact_store: ResearchArtifactStore,
) -> None:
    """Revalidate accepted routes and canonical refs before checkpoint reuse."""
    try:
        raw_results = state.get("accepted_specialist_results") or ()
        if not isinstance(raw_results, Sequence) or isinstance(
            raw_results,
            (str, bytes),
        ):
            raise ValueError("accepted specialist results must be a sequence")
        if any(not isinstance(item, Mapping) for item in raw_results):
            raise ValueError("accepted specialist results must contain mappings")
        accepted_results = tuple(
            AcceptedSpecialistResult.from_dict(item)
            for item in raw_results
            if isinstance(item, Mapping)
        )
        task_by_id = {task.task_id: task for task in request.specialist_tasks}
        for receipt in accepted_results:
            try:
                task = task_by_id[receipt.task_id]
            except KeyError as exc:
                raise ValueError(
                    "accepted specialist result references an unknown task"
                ) from exc
            specialist_catalog.require(
                authority_key=receipt.authority_key,
                version=receipt.route_version,
                task=task,
            )
        revalidate_accepted_specialist_results(
            accepted_results=accepted_results,
            artifact_store=artifact_store,
        )
        proposal_resolution = resolve_accepted_protocol_proposal(
            accepted_results=accepted_results,
            artifact_store=artifact_store,
        )
        if proposal_resolution is not None:
            proposal, proposal_ref = proposal_resolution
            saved_ref = state.get("protocol_proposal_ref") or {}
            if saved_ref and saved_ref != proposal_ref.to_dict():
                raise ValueError("composition protocol proposal ref drift")
            saved_digest = str(state.get("protocol_proposal_digest") or "")
            observed_digest = str(
                proposal_ref.metadata.get("payload_sha256") or ""
            )
            if saved_digest and saved_digest != observed_digest:
                raise ValueError("composition protocol proposal payload drift")
            if protocol is not None:
                validate_protocol_matches_proposal(
                    protocol=protocol,
                    proposal=proposal,
                )
        raw_outcome_ref = state.get("outcome_ref") or {}
        if raw_outcome_ref:
            if not isinstance(raw_outcome_ref, Mapping):
                raise ValueError("composition outcome_ref must be a mapping")
            revalidate_composition_outcome(
                outcome_ref=ArtifactReportRef.from_dict(raw_outcome_ref),
                outcome_digest=str(state.get("outcome_digest") or ""),
                artifact_store=artifact_store,
            )
    except (ResearchArtifactStoreError, TypeError, ValueError) as exc:
        raise ResearchCompositionConflictError(
            f"composition checkpoint evidence drift: {exc}"
        ) from exc
