"""Advance one bounded transition of resumable research composition.

The graph delegates decisions to the Research Coordinator, specialist behavior
to registered routes, and workflow behavior to the fixed executor. It owns only
ordering, cross-boundary validation, bounded checkpoint summaries, and recovery.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from trader_research.foundation import (
    ResearchArtifactStore,
    json_payload_hash,
    stable_research_id,
)
from trader_research.governance import (
    ArtifactReportRef,
    ExperimentProtocol,
    ExperimentProtocolProposal,
    ExperimentProtocolStatus,
    ResearchIssue,
    WorkflowOutcomeStatus,
)

from trader_agents.orchestration import (
    WorkflowExecutionInterrupted,
    execute_compiled_research_workflow,
)
from trader_agents.research_coordinator import (
    CoordinatorAction,
    ResearchCoordination,
    WorkflowTemplateCatalog,
    compile_coordination_decision,
    coordinate_research,
)
from trader_agents.specialists import (
    AcceptedSpecialistResult,
    SpecialistResultStatus,
    SpecialistRouteCatalog,
)
from trader_agents.tool_client import McpToolClient

from .domain import (
    MAX_COMPOSITION_TRANSITIONS,
    ResearchCompositionRequest,
    ResearchCompositionState,
    ResearchCompositionStatus,
    protocol_design_digest,
    protocol_digest,
    research_composition_digest,
)
from .validation import (
    accept_specialist_result,
    resolve_accepted_protocol_proposal,
    summarize_specialist_result,
    validate_protocol_matches_proposal,
    validate_protocol_consumes_specialist_outputs,
)


def build_research_composition_graph(
    *,
    request: ResearchCompositionRequest,
    protocol: ExperimentProtocol | None,
    specialist_catalog: SpecialistRouteCatalog,
    workflow_catalog: WorkflowTemplateCatalog,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
    checkpointer: BaseCheckpointSaver[Any],
    max_workflow_tool_calls: int | None = None,
    max_transitions: int = MAX_COMPOSITION_TRANSITIONS,
) -> Any:
    """Compile a one-transition graph over injected composition dependencies.

    Repeated invocations on the same composition thread each checkpoint one
    externally meaningful transition. A child specialist or workflow may finish
    before the parent transition is saved; replay-safe child APIs make the next
    invocation recover without repeating accepted work.

    Args:
        request: Exact immutable composition request retained outside state.
        protocol: Optional operator-supplied protocol for this invocation.
        specialist_catalog: Code-owned specialist graph routes.
        workflow_catalog: Code-owned deterministic workflow templates.
        tool_client: MCP client used only by child handlers and executor.
        artifact_store: Canonical store shared across all boundaries.
        checkpointer: Operational saver shared through isolated thread IDs.
        max_workflow_tool_calls: Optional deliberate child-workflow pause limit.
        max_transitions: Maximum checkpointed composition transitions.

    Returns:
        Compiled LangGraph that advances exactly one composition transition.

    Raises:
        ValueError: If the transition budget or workflow call limit is invalid.
    """
    if max_transitions <= 0:
        raise ValueError("max_transitions must be positive")
    if max_workflow_tool_calls is not None and max_workflow_tool_calls < 0:
        raise ValueError("max_workflow_tool_calls cannot be negative")

    async def advance(
        state: ResearchCompositionState,
    ) -> ResearchCompositionState:
        return await _advance_composition(
            state,
            request=request,
            protocol=protocol,
            specialist_catalog=specialist_catalog,
            workflow_catalog=workflow_catalog,
            tool_client=tool_client,
            artifact_store=artifact_store,
            checkpointer=checkpointer,
            max_workflow_tool_calls=max_workflow_tool_calls,
            max_transitions=max_transitions,
        )

    graph = StateGraph(ResearchCompositionState)
    graph.add_node("advance_research_composition", advance)
    graph.add_edge(START, "advance_research_composition")
    graph.add_edge("advance_research_composition", END)
    return graph.compile(checkpointer=checkpointer)


async def _advance_composition(
    state: ResearchCompositionState,
    *,
    request: ResearchCompositionRequest,
    protocol: ExperimentProtocol | None,
    specialist_catalog: SpecialistRouteCatalog,
    workflow_catalog: WorkflowTemplateCatalog,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
    checkpointer: BaseCheckpointSaver[Any],
    max_workflow_tool_calls: int | None,
    max_transitions: int,
) -> ResearchCompositionState:
    try:
        _validate_checkpoint_identity(state, request)
        accepted_results = _accepted_results(state)
        proposal_resolution = resolve_accepted_protocol_proposal(
            accepted_results=accepted_results,
            artifact_store=artifact_store,
        )
        proposed_protocol = (
            proposal_resolution[0].protocol
            if proposal_resolution is not None
            else None
        )
        if protocol is not None and proposal_resolution is not None:
            validate_protocol_matches_proposal(
                protocol=protocol,
                proposal=proposal_resolution[0],
            )
        effective_protocol = protocol or proposed_protocol
        protocol_fields = _validated_protocol_fields(
            state,
            request,
            effective_protocol,
            proposal_resolution=proposal_resolution,
        )
    except (TypeError, ValueError) as exc:
        return _failed_state(state, "invalid_composition_state", str(exc))
    transition_count = int(state.get("transition_count", 0))
    if transition_count >= max_transitions:
        return _failed_state(
            state,
            "composition_transition_limit_exceeded",
            f"Research composition supports at most {max_transitions} transitions.",
        )
    try:
        coordination = coordinate_research(
            objective=request.objective,
            protocol=effective_protocol,
            artifact_store=artifact_store,
            catalog=workflow_catalog,
            specialist_tasks=request.specialist_tasks,
            accepted_specialist_results=accepted_results,
            specialist_catalog=specialist_catalog,
        )
        decision = coordination.decision
        base: ResearchCompositionState = {
            **protocol_fields,
            "decision": decision.to_dict(),
            "transition_count": transition_count + 1,
            "prerequisites": [],
            "blockers": [],
            "errors": [],
        }
        if decision.action is CoordinatorAction.EXECUTE_REGISTERED_SPECIALIST_TASK:
            return await _run_specialist_transition(
                state,
                base=base,
                coordination=coordination,
                specialist_catalog=specialist_catalog,
                artifact_store=artifact_store,
                accepted_results=accepted_results,
            )
        if decision.action is CoordinatorAction.REQUEST_PREREQUISITE:
            return {
                **base,
                "status": "awaiting_prerequisite",
                "public_status": "awaiting_prerequisite",
                "prerequisites": [item.to_dict() for item in decision.prerequisites],
            }
        if decision.action is CoordinatorAction.REQUEST_APPROVAL:
            return {
                **base,
                "status": "awaiting_approval",
                "public_status": "awaiting_approval",
                "prerequisites": [item.to_dict() for item in decision.prerequisites],
            }
        if decision.action is CoordinatorAction.BLOCK:
            return {
                **base,
                "status": "blocked",
                "public_status": "blocked",
                "blockers": [item.to_dict() for item in decision.blockers],
            }
        if decision.action is CoordinatorAction.EXECUTE_REGISTERED_WORKFLOW:
            if effective_protocol is None:
                raise ValueError("workflow execution requires an approved protocol")
            return await _run_workflow_transition(
                state,
                base=base,
                request=request,
                protocol=effective_protocol,
                coordination=coordination,
                accepted_results=accepted_results,
                workflow_catalog=workflow_catalog,
                tool_client=tool_client,
                artifact_store=artifact_store,
                checkpointer=checkpointer,
                max_workflow_tool_calls=max_workflow_tool_calls,
            )
        raise ValueError(
            f"unexpected pre-outcome coordinator action: {decision.action.value}"
        )
    except WorkflowExecutionInterrupted:
        raise
    except Exception as exc:
        return _failed_state(state, "composition_transition_failed", str(exc))


async def _run_specialist_transition(
    state: ResearchCompositionState,
    *,
    base: ResearchCompositionState,
    coordination: ResearchCoordination,
    specialist_catalog: SpecialistRouteCatalog,
    artifact_store: ResearchArtifactStore,
    accepted_results: tuple[AcceptedSpecialistResult, ...],
) -> ResearchCompositionState:
    task = coordination.specialist_task
    if task is None:
        raise ValueError("specialist decision did not carry the selected task")
    decision = coordination.decision
    if (
        decision.specialist_task_id != task.task_id
        or decision.specialist_authority != task.authority_key
        or decision.specialist_task_digest
        != state["task_digests"].get(task.task_id)
    ):
        raise ValueError("specialist coordination decision does not match task")
    route = specialist_catalog.require(
        authority_key=decision.specialist_authority or "",
        version=decision.specialist_route_version or "",
        task=task,
    )
    result = await route.runner.run(task)
    summary = summarize_specialist_result(
        task=task,
        result=result,
        route=route,
        artifact_store=artifact_store,
    )
    warnings = [*state.get("warnings", []), *summary["warnings"]]
    if result.status is SpecialistResultStatus.COMPLETED:
        receipt = accept_specialist_result(
            task=task,
            result=result,
            route=route,
            artifact_store=artifact_store,
        )
        return {
            **base,
            "accepted_specialist_results": [
                *(item.to_dict() for item in accepted_results),
                receipt.to_dict(),
            ],
            "last_specialist_result": summary,
            "status": "running",
            "public_status": "specialist_task_completed",
            "warnings": warnings,
        }
    if result.status is SpecialistResultStatus.AWAITING_PREREQUISITE:
        return {
            **base,
            "last_specialist_result": summary,
            "status": "awaiting_prerequisite",
            "public_status": "awaiting_specialist_prerequisite",
            "prerequisites": list(summary["prerequisites"]),
            "warnings": warnings,
        }
    if result.status is SpecialistResultStatus.BLOCKED:
        return {
            **base,
            "last_specialist_result": summary,
            "status": "blocked",
            "public_status": "specialist_blocked",
            "blockers": list(summary["blockers"]),
            "warnings": warnings,
        }
    return {
        **base,
        "last_specialist_result": summary,
        "status": "failed",
        "public_status": "specialist_failed",
        "errors": list(summary["errors"]),
        "warnings": warnings,
    }


async def _run_workflow_transition(
    state: ResearchCompositionState,
    *,
    base: ResearchCompositionState,
    request: ResearchCompositionRequest,
    protocol: ExperimentProtocol,
    coordination: ResearchCoordination,
    accepted_results: tuple[AcceptedSpecialistResult, ...],
    workflow_catalog: WorkflowTemplateCatalog,
    tool_client: McpToolClient,
    artifact_store: ResearchArtifactStore,
    checkpointer: BaseCheckpointSaver[Any],
    max_workflow_tool_calls: int | None,
) -> ResearchCompositionState:
    if protocol.status is not ExperimentProtocolStatus.APPROVED:
        raise ValueError("workflow execution requires an approved protocol")
    validate_protocol_consumes_specialist_outputs(
        protocol=protocol,
        accepted_results=accepted_results,
    )
    compiled = compile_coordination_decision(
        decision=coordination.decision,
        objective=request.objective,
        protocol=protocol,
        artifact_store=artifact_store,
        catalog=workflow_catalog,
    )
    workflow_id = stable_research_id(
        "research_composition_workflow",
        {
            "composition_id": request.composition_id,
            "plan_id": compiled.plan.plan_id,
        },
    )
    saved_workflow_id = str(state.get("workflow_id") or "")
    saved_plan_id = str(state.get("plan_id") or "")
    if saved_workflow_id and saved_workflow_id != workflow_id:
        raise ValueError("composition workflow identity drift")
    if saved_plan_id and saved_plan_id != compiled.plan.plan_id:
        raise ValueError("composition workflow plan drift")
    try:
        execution = await execute_compiled_research_workflow(
            compiled=compiled,
            workflow_id=workflow_id,
            tool_client=tool_client,
            checkpointer=checkpointer,
            artifact_store=artifact_store,
            max_tool_calls=max_workflow_tool_calls,
        )
    except WorkflowExecutionInterrupted:
        return {
            **base,
            "workflow_id": workflow_id,
            "plan_id": compiled.plan.plan_id,
            "status": "interrupted",
            "public_status": "workflow_interrupted",
        }
    terminal = coordinate_research(
        objective=request.objective,
        protocol=protocol,
        outcome=execution.outcome,
        artifact_store=artifact_store,
        catalog=workflow_catalog,
        specialist_tasks=request.specialist_tasks,
        accepted_specialist_results=accepted_results,
        specialist_catalog=None,
    )
    if terminal.decision.action is not CoordinatorAction.REPORT_TERMINAL_STATE:
        raise ValueError("Coordinator did not report the executed workflow outcome")
    status_by_outcome: dict[WorkflowOutcomeStatus, ResearchCompositionStatus] = {
        WorkflowOutcomeStatus.COMPLETED: "completed",
        WorkflowOutcomeStatus.BLOCKED: "blocked",
        WorkflowOutcomeStatus.FAILED: "failed",
    }
    public_status_by_outcome = {
        WorkflowOutcomeStatus.COMPLETED: "terminal_workflow_completed",
        WorkflowOutcomeStatus.BLOCKED: "terminal_workflow_blocked",
        WorkflowOutcomeStatus.FAILED: "terminal_workflow_failed",
    }
    return {
        **base,
        "decision": terminal.decision.to_dict(),
        "workflow_id": workflow_id,
        "plan_id": compiled.plan.plan_id,
        "outcome_ref": execution.outcome_ref.to_dict(),
        "outcome_digest": json_payload_hash(execution.outcome.to_dict()),
        "status": status_by_outcome[execution.outcome.status],
        "public_status": public_status_by_outcome[execution.outcome.status],
        "warnings": [
            *state.get("warnings", []),
            *(item.to_dict() for item in execution.outcome.warnings),
        ],
        "blockers": [item.to_dict() for item in execution.outcome.blockers],
        "errors": [item.to_dict() for item in execution.outcome.errors],
    }


def _validate_checkpoint_identity(
    state: Mapping[str, Any],
    request: ResearchCompositionRequest,
) -> None:
    expected_tasks = {
        task.task_id: json_payload_hash(task.to_dict())
        for task in request.specialist_tasks
    }
    if state.get("composition_id") != request.composition_id:
        raise ValueError("composition checkpoint ID does not match request")
    if state.get("request_digest") != research_composition_digest(request):
        raise ValueError("composition checkpoint request digest drift")
    if state.get("objective_id") != request.objective.objective_id:
        raise ValueError("composition checkpoint objective identity drift")
    if state.get("objective_digest") != json_payload_hash(
        request.objective.to_dict()
    ):
        raise ValueError("composition checkpoint objective content drift")
    if state.get("task_digests") != expected_tasks:
        raise ValueError("composition checkpoint specialist task drift")


def _validated_protocol_fields(
    state: Mapping[str, Any],
    request: ResearchCompositionRequest,
    protocol: ExperimentProtocol | None,
    *,
    proposal_resolution: (
        tuple[ExperimentProtocolProposal, ArtifactReportRef] | None
    ),
) -> ResearchCompositionState:
    fields: ResearchCompositionState = {
        "protocol_id": str(state.get("protocol_id") or ""),
        "protocol_design_digest": str(
            state.get("protocol_design_digest") or ""
        ),
        "accepted_protocol_digest": str(
            state.get("accepted_protocol_digest") or ""
        ),
        "protocol_proposal_ref": dict(
            state.get("protocol_proposal_ref") or {}
        ),
        "protocol_proposal_digest": str(
            state.get("protocol_proposal_digest") or ""
        ),
    }
    if proposal_resolution is not None:
        proposal, proposal_ref = proposal_resolution
        observed_proposal_digest = str(
            proposal_ref.metadata.get("payload_sha256") or ""
        )
        saved_ref = fields["protocol_proposal_ref"]
        if saved_ref and saved_ref != proposal_ref.to_dict():
            raise ValueError("composition protocol proposal ref drift")
        if (
            fields["protocol_proposal_digest"]
            and fields["protocol_proposal_digest"]
            != observed_proposal_digest
        ):
            raise ValueError("composition protocol proposal payload drift")
        fields["protocol_proposal_ref"] = proposal_ref.to_dict()
        fields["protocol_proposal_digest"] = observed_proposal_digest
        if protocol is not None:
            validate_protocol_matches_proposal(
                protocol=protocol,
                proposal=proposal,
            )
    if protocol is None:
        return fields
    if protocol.objective_id != request.objective.objective_id:
        raise ValueError("composition protocol objective does not match request")
    observed_design_digest = protocol_design_digest(protocol)
    if fields["protocol_id"] and fields["protocol_id"] != protocol.protocol_id:
        raise ValueError("composition protocol identity drift")
    if (
        fields["protocol_design_digest"]
        and fields["protocol_design_digest"] != observed_design_digest
    ):
        raise ValueError("composition protocol design drift")
    fields["protocol_id"] = protocol.protocol_id
    fields["protocol_design_digest"] = observed_design_digest
    if protocol.status is ExperimentProtocolStatus.APPROVED:
        observed_digest = protocol_digest(protocol)
        if (
            fields["accepted_protocol_digest"]
            and fields["accepted_protocol_digest"] != observed_digest
        ):
            raise ValueError("composition approved protocol content drift")
        fields["accepted_protocol_digest"] = observed_digest
    return fields


def _accepted_results(
    state: Mapping[str, Any],
) -> tuple[AcceptedSpecialistResult, ...]:
    raw_results = state.get("accepted_specialist_results") or ()
    if not isinstance(raw_results, Sequence) or isinstance(raw_results, (str, bytes)):
        raise ValueError("accepted specialist results must be a sequence")
    if any(not isinstance(item, Mapping) for item in raw_results):
        raise ValueError("accepted specialist results must contain mappings")
    results = tuple(
        AcceptedSpecialistResult.from_dict(item)
        for item in raw_results
        if isinstance(item, Mapping)
    )
    if len(results) != len({item.task_id for item in results}):
        raise ValueError("accepted specialist result task IDs must be unique")
    return results


def _failed_state(
    state: Mapping[str, Any],
    code: str,
    message: str,
) -> ResearchCompositionState:
    issue = ResearchIssue(code=code, message=message)
    return {
        "status": "failed",
        "public_status": "failed_validation",
        "errors": [*list(state.get("errors", [])), issue.to_dict()],
        "blockers": list(state.get("blockers", [])),
        "warnings": list(state.get("warnings", [])),
        "prerequisites": [],
    }
