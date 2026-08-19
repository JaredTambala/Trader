"""Run bounded specialist policies through code-registered actions.

The graph validates task authority, policy decisions, action registration,
canonical input/output bindings, side-effect permissions, policy gates, and
handoff provenance at every boundary. Registered handlers may call MCP, but the
shell stores only typed decisions, canonical handoffs, bounded action summaries,
and issues. It performs no persistence and contains no provider-specific logic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal, TypedDict, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from trader_research.foundation import json_payload_hash, parse_research_artifact_uri
from trader_research.governance import (
    ArtifactCardinality,
    ArtifactSlot,
    CapabilityDefinition,
    Prerequisite,
    ResearchIssue,
    SpecialistHandoff,
    get_decision_authority,
)

from .catalog import RegisteredSpecialistAction, SpecialistActionCatalog
from .domain import (
    SpecialistActionOutcome,
    SpecialistActionStatus,
    SpecialistActionSummary,
    SpecialistDecision,
    SpecialistPolicyAction,
    SpecialistResult,
    SpecialistResultStatus,
    SpecialistTask,
)
from .policy import (
    SpecialistActionExecutionError,
    SpecialistPolicy,
    SpecialistPolicyContext,
    SpecialistPolicyError,
)


SpecialistGraphStatus = Literal["ready", "running", "completed", "blocked", "failed"]
"""Lifecycle values exposed by the shared specialist graph shell."""


def _retain_first_digest(current: str, incoming: str) -> str:
    """Keep the first task digest written to a checkpoint thread."""
    return current or incoming


class SpecialistGraphState(TypedDict, total=False):
    """JSON-safe operational state for one bounded specialist task.

    Attributes:
        identity: Registered decision-authority metadata for the specialist.
        task: Validated specialist task payload.
        task_digest: Digest of the task currently supplied to the graph.
        accepted_task_digest: First task digest retained for checkpoint drift checks.
        decision: Latest bounded specialist policy decision.
        result: Terminal public specialist result, when available.
        handoffs: Canonical handoffs accepted from registered actions.
        output_bindings: Requested task-slot IDs to accepted handoff IDs.
        action_summaries: Bounded action-attempt summaries.
        processed_action_digests: Accepted action attempts keyed by decision digest.
        decision_count: Number of validated policy decisions.
        next_route: Internal graph route selected by the last node.
        status: Current graph lifecycle status.
        public_status: Operator-facing bounded status.
        prerequisites: Unresolved prerequisite payloads.
        warnings: Structured non-fatal issues.
        blockers: Structured domain blockers.
        errors: Structured policy, validation, or action failures.
    """

    identity: dict[str, Any]
    task: dict[str, Any]
    task_digest: str
    accepted_task_digest: Annotated[str, _retain_first_digest]
    decision: dict[str, Any]
    result: dict[str, Any]
    handoffs: list[dict[str, Any]]
    output_bindings: dict[str, list[str]]
    action_summaries: list[dict[str, Any]]
    processed_action_digests: dict[str, str]
    decision_count: int
    next_route: str
    status: SpecialistGraphStatus
    public_status: str
    prerequisites: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    blockers: list[dict[str, Any]]
    errors: list[dict[str, Any]]


def build_specialist_initial_state(task: SpecialistTask) -> SpecialistGraphState:
    """Build checkpoint-safe initial state for one specialist task.

    Args:
        task: Validated task addressed to a registered specialist authority.

    Returns:
        Initial graph state containing public task and authority metadata only.
    """
    task_digest = specialist_task_digest(task)
    return {
        "identity": _identity_payload(task.authority_key),
        "task": task.to_dict(),
        "task_digest": task_digest,
        "accepted_task_digest": task_digest,
        "decision": {},
        "result": {},
        "handoffs": [],
        "output_bindings": {},
        "action_summaries": [],
        "processed_action_digests": {},
        "decision_count": 0,
        "next_route": "select_specialist_action",
        "status": "ready",
        "public_status": "ready",
        "prerequisites": [],
        "warnings": [],
        "blockers": [],
        "errors": [],
    }


def build_specialist_graph(
    *,
    catalog: SpecialistActionCatalog,
    policy: SpecialistPolicy,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    max_policy_decisions: int = 8,
    max_action_attempts: int = 16,
) -> Any:
    """Build a reusable specialist policy-and-action graph.

    The catalog and policy are injected code dependencies. Graph state cannot
    register actions or replace handlers. When supplied, the checkpointer stores
    only the bounded operational state declared by ``SpecialistGraphState``.

    Args:
        catalog: Code-owned actions for exactly one specialist authority.
        policy: Provider-neutral policy returning one typed next decision.
        checkpointer: Optional LangGraph saver for resumable operational state.
        max_policy_decisions: Maximum decisions accepted during one invocation.
        max_action_attempts: Maximum registered actions executed during a run.

    Returns:
        Compiled LangGraph graph over ``SpecialistGraphState``.

    Raises:
        ValueError: If either execution budget is not positive.
    """
    if max_policy_decisions <= 0:
        raise ValueError("max_policy_decisions must be positive")
    if max_action_attempts <= 0:
        raise ValueError("max_action_attempts must be positive")

    async def select_action(state: SpecialistGraphState) -> SpecialistGraphState:
        return await _select_action(
            state,
            catalog=catalog,
            policy=policy,
            max_policy_decisions=max_policy_decisions,
            max_action_attempts=max_action_attempts,
        )

    async def execute_action(state: SpecialistGraphState) -> SpecialistGraphState:
        return await _execute_action(
            state,
            catalog=catalog,
            max_action_attempts=max_action_attempts,
        )

    graph = StateGraph(SpecialistGraphState)
    graph.add_node("select_specialist_action", select_action)
    graph.add_node("execute_registered_action", execute_action)
    graph.add_edge(START, "select_specialist_action")
    graph.add_conditional_edges(
        "select_specialist_action",
        _route_after_policy,
        {
            "execute_registered_action": "execute_registered_action",
            "done": END,
        },
    )
    graph.add_conditional_edges(
        "execute_registered_action",
        _route_after_action,
        {
            "select_specialist_action": "select_specialist_action",
            "done": END,
        },
    )
    return graph.compile(checkpointer=checkpointer)


def specialist_task_digest(task: SpecialistTask) -> str:
    """Return the content digest that a specialist checkpoint must retain."""
    return json_payload_hash(task.to_dict())


def specialist_thread_config(task: SpecialistTask) -> dict[str, Any]:
    """Build an isolated LangGraph thread configuration for a specialist task."""
    thread_id = f"specialist:{task.authority_key}:{task.task_id}"
    return {"configurable": {"thread_id": thread_id}}


class SpecialistTaskConflictError(RuntimeError):
    """Raised when a checkpoint thread is reused for changed task content."""


async def run_specialist_task(
    *,
    graph: Any,
    task: SpecialistTask,
) -> SpecialistGraphState:
    """Run or resume one checkpointed specialist task without replaying work.

    The graph must have been compiled with a checkpointer. Existing terminal
    state is returned directly. An interrupted non-terminal thread continues
    from its saved next node, while changed content under the same task identity
    is rejected before graph execution.

    Args:
        graph: Specialist graph compiled with a LangGraph checkpointer.
        task: Exact bounded task to start or resume.

    Returns:
        Latest bounded specialist graph state.

    Raises:
        SpecialistTaskConflictError: If saved task identity or content differs.
    """
    config = specialist_thread_config(task)
    snapshot = await graph.aget_state(config)
    expected_digest = specialist_task_digest(task)
    if snapshot.values:
        state = cast(SpecialistGraphState, dict(snapshot.values))
        if (
            state.get("accepted_task_digest") != expected_digest
            or state.get("task_digest") != expected_digest
            or state.get("task") != task.to_dict()
        ):
            raise SpecialistTaskConflictError(
                "specialist checkpoint task content does not match the supplied task"
            )
        if state.get("status") in {"completed", "blocked", "failed"}:
            return state
        return cast(SpecialistGraphState, dict(await graph.ainvoke(None, config)))
    return cast(
        SpecialistGraphState,
        dict(await graph.ainvoke(build_specialist_initial_state(task), config)),
    )


def specialist_public_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Project graph state to the stable caller-visible specialist surface.

    Internal routing state is omitted. The projection contains no raw MCP
    result, tool arguments, prompt, scratchpad, credential, or full artifact.

    Args:
        state: Completed or interrupted specialist graph state.

    Returns:
        Bounded public task, decision, result, handoffs, summaries, and issues.
    """
    return {
        "identity": dict(_mapping(state.get("identity"))),
        "task": dict(_mapping(state.get("task"))),
        "decision": dict(_mapping(state.get("decision"))),
        "result": dict(_mapping(state.get("result"))),
        "handoffs": [dict(item) for item in _mapping_sequence(state.get("handoffs"))],
        "output_bindings": {
            str(key): list(value)
            for key, value in _mapping(state.get("output_bindings")).items()
        },
        "action_summaries": [
            dict(item) for item in _mapping_sequence(state.get("action_summaries"))
        ],
        "decision_count": int(state.get("decision_count", 0)),
        "status": str(state.get("status") or "failed"),
        "public_status": str(state.get("public_status") or "failed_validation"),
        "prerequisites": [
            dict(item) for item in _mapping_sequence(state.get("prerequisites"))
        ],
        "warnings": [dict(item) for item in _mapping_sequence(state.get("warnings"))],
        "blockers": [dict(item) for item in _mapping_sequence(state.get("blockers"))],
        "errors": [dict(item) for item in _mapping_sequence(state.get("errors"))],
    }


async def _select_action(
    state: SpecialistGraphState,
    *,
    catalog: SpecialistActionCatalog,
    policy: SpecialistPolicy,
    max_policy_decisions: int,
    max_action_attempts: int,
) -> SpecialistGraphState:
    try:
        context = _context_from_state(state)
        _validate_identity(state, context.task)
        _validate_catalog_scope(catalog, context.task)
        _validate_task_checkpoint(state, context.task)
        _validate_action_checkpoint(
            state,
            context,
            max_action_attempts=max_action_attempts,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return _failed_state(
            state,
            code="invalid_specialist_state",
            message=str(exc),
        )
    if context.decision_count >= max_policy_decisions:
        return _failed_state(
            state,
            context=context,
            code="specialist_policy_loop_limit_exceeded",
            message="Specialist policy exceeded its decision budget.",
        )
    try:
        proposed = await policy.decide(context)
    except SpecialistPolicyError as exc:
        return _failed_state(
            state,
            context=context,
            code=exc.code,
            message=str(exc),
        )
    try:
        decision = (
            proposed
            if isinstance(proposed, SpecialistDecision)
            else SpecialistDecision.from_dict(proposed)
        )
        _validate_decision_scope(decision, context.task)
    except (TypeError, ValueError) as exc:
        return _failed_state(
            state,
            context=context,
            code="invalid_specialist_decision",
            message=str(exc),
        )

    decision_count = context.decision_count + 1
    common: SpecialistGraphState = {
        "decision": decision.to_dict(),
        "decision_count": decision_count,
        "prerequisites": [],
        "blockers": [],
        "errors": [],
    }
    if decision.action is SpecialistPolicyAction.RUN_REGISTERED_ACTION:
        try:
            registration = catalog.require(
                decision.action_id or "",
                decision.action_version or "",
            )
            _validate_action_decision(
                context=context,
                decision=decision,
                capability=registration.capability,
            )
        except ValueError as exc:
            return _failed_state(
                {**state, **common},
                context=context,
                code="invalid_registered_action",
                message=str(exc),
            )
        return {
            **common,
            "next_route": "execute_registered_action",
            "status": "running",
            "public_status": "running_registered_action",
        }
    if decision.action is SpecialistPolicyAction.REQUEST_PREREQUISITE:
        result = _terminal_result(
            context,
            status=SpecialistResultStatus.AWAITING_PREREQUISITE,
            prerequisites=decision.prerequisites,
            warnings=_state_issues(state, "warnings"),
        )
        return {
            **common,
            "result": result.to_dict(),
            "next_route": "done",
            "status": "blocked",
            "public_status": "awaiting_prerequisite",
            "prerequisites": [item.to_dict() for item in decision.prerequisites],
        }
    if decision.action is SpecialistPolicyAction.BLOCK:
        result = _terminal_result(
            context,
            status=SpecialistResultStatus.BLOCKED,
            warnings=_state_issues(state, "warnings"),
            blockers=decision.blockers,
        )
        return {
            **common,
            "result": result.to_dict(),
            "next_route": "done",
            "status": "blocked",
            "public_status": "blocked",
            "blockers": [item.to_dict() for item in decision.blockers],
        }
    try:
        _validate_task_completion(context)
        result = _terminal_result(
            context,
            status=SpecialistResultStatus.COMPLETED,
            warnings=_state_issues(state, "warnings"),
        )
    except ValueError as exc:
        return _failed_state(
            {**state, **common},
            context=context,
            code="invalid_specialist_completion",
            message=str(exc),
        )
    return {
        **common,
        "result": result.to_dict(),
        "next_route": "done",
        "status": "completed",
        "public_status": "completed",
    }


async def _execute_action(
    state: SpecialistGraphState,
    *,
    catalog: SpecialistActionCatalog,
    max_action_attempts: int,
) -> SpecialistGraphState:
    try:
        context = _context_from_state(state)
        _validate_task_checkpoint(state, context.task)
        _validate_action_checkpoint(
            state,
            context,
            max_action_attempts=max_action_attempts,
        )
        decision = SpecialistDecision.from_dict(_mapping(state.get("decision")))
        _validate_decision_scope(decision, context.task)
        if decision.action is not SpecialistPolicyAction.RUN_REGISTERED_ACTION:
            raise ValueError("pending specialist decision is not executable")
        registration = catalog.require(
            decision.action_id or "",
            decision.action_version or "",
        )
        _validate_action_decision(
            context=context,
            decision=decision,
            capability=registration.capability,
        )
        replay = _accepted_action_replay(
            state=state,
            context=context,
            decision=decision,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return _failed_state(
            state,
            code="invalid_pending_specialist_action",
            message=str(exc),
        )
    if replay:
        return {
            "next_route": "select_specialist_action",
            "status": "running",
            "public_status": "accepted_action_replay_ignored",
            "blockers": [],
            "errors": [],
        }
    if len(context.action_summaries) >= max_action_attempts:
        return _failed_state(
            state,
            context=context,
            code="specialist_action_limit_exceeded",
            message="Specialist graph exceeded its registered-action budget.",
        )
    try:
        raw_outcome = await registration.handler.run(
            context=context,
            decision=decision,
        )
    except SpecialistActionExecutionError as exc:
        return _failed_state(
            state,
            context=context,
            code=exc.code,
            message=str(exc),
        )
    try:
        outcome = (
            raw_outcome
            if isinstance(raw_outcome, SpecialistActionOutcome)
            else SpecialistActionOutcome.from_dict(raw_outcome)
        )
        handoffs, bindings = _accept_action_outcome(
            context=context,
            decision=decision,
            registration=registration,
            outcome=outcome,
        )
    except (TypeError, ValueError) as exc:
        return _failed_state(
            state,
            context=context,
            code="invalid_specialist_action_outcome",
            message=str(exc),
        )

    summary = SpecialistActionSummary.from_outcome(outcome)
    summaries = (*context.action_summaries, summary)
    action_key = _action_attempt_key(context, decision)
    processed_action_digests = dict(state.get("processed_action_digests", {}))
    processed_action_digests[action_key] = json_payload_hash(summary.to_dict())
    warnings = (*_state_issues(state, "warnings"), *outcome.warnings)
    updated_context = SpecialistPolicyContext(
        task=context.task,
        handoffs=handoffs,
        output_bindings=bindings,
        action_summaries=summaries,
        decision_count=context.decision_count,
    )
    common: SpecialistGraphState = {
        "handoffs": [handoff.to_dict() for handoff in handoffs],
        "output_bindings": {key: list(value) for key, value in bindings.items()},
        "action_summaries": [item.to_dict() for item in summaries],
        "processed_action_digests": processed_action_digests,
        "warnings": [item.to_dict() for item in warnings],
        "prerequisites": [],
    }
    if outcome.status is SpecialistActionStatus.SUCCEEDED:
        return {
            **common,
            "next_route": "select_specialist_action",
            "status": "running",
            "public_status": "action_completed",
            "blockers": [],
            "errors": [],
        }
    if outcome.status is SpecialistActionStatus.BLOCKED:
        result = _terminal_result(
            updated_context,
            status=SpecialistResultStatus.BLOCKED,
            warnings=warnings,
            blockers=outcome.blockers,
        )
        return {
            **common,
            "result": result.to_dict(),
            "next_route": "done",
            "status": "blocked",
            "public_status": "blocked",
            "blockers": [item.to_dict() for item in outcome.blockers],
            "errors": [],
        }
    result = _terminal_result(
        updated_context,
        status=SpecialistResultStatus.FAILED,
        warnings=warnings,
        errors=outcome.errors,
    )
    return {
        **common,
        "result": result.to_dict(),
        "next_route": "done",
        "status": "failed",
        "public_status": "action_failed",
        "blockers": [],
        "errors": [item.to_dict() for item in outcome.errors],
    }


def _context_from_state(state: Mapping[str, Any]) -> SpecialistPolicyContext:
    context = SpecialistPolicyContext(
        task=SpecialistTask.from_dict(_mapping(state.get("task"))),
        handoffs=tuple(
            SpecialistHandoff.from_dict(item)
            for item in _mapping_sequence(state.get("handoffs"))
        ),
        output_bindings={
            str(key): _text_tuple(value, f"output_bindings.{key}")
            for key, value in _mapping(state.get("output_bindings")).items()
        },
        action_summaries=tuple(
            SpecialistActionSummary.from_dict(item)
            for item in _mapping_sequence(state.get("action_summaries"))
        ),
        decision_count=int(state.get("decision_count", 0)),
    )
    _validate_bound_task_slots(
        context.task,
        context.handoffs,
        context.output_bindings,
        require_all=False,
    )
    return context


def _validate_identity(state: Mapping[str, Any], task: SpecialistTask) -> None:
    if dict(_mapping(state.get("identity"))) != _identity_payload(task.authority_key):
        raise ValueError("state identity does not match the specialist authority")


def _validate_catalog_scope(
    catalog: SpecialistActionCatalog,
    task: SpecialistTask,
) -> None:
    if catalog.authority_key != task.authority_key:
        raise ValueError("specialist action catalog authority does not match task")


def _validate_task_checkpoint(
    state: Mapping[str, Any],
    task: SpecialistTask,
) -> None:
    expected = specialist_task_digest(task)
    if state.get("task_digest") != expected:
        raise ValueError("specialist task digest does not match task content")
    if state.get("accepted_task_digest") != expected:
        raise ValueError("specialist checkpoint contains task drift")


def _action_attempt_key(
    context: SpecialistPolicyContext,
    decision: SpecialistDecision,
) -> str:
    return json_payload_hash(
        {
            "task_id": context.task.task_id,
            "decision_count": context.decision_count,
            "decision": decision.to_dict(),
        }
    )


def _validate_action_checkpoint(
    state: Mapping[str, Any],
    context: SpecialistPolicyContext,
    *,
    max_action_attempts: int,
) -> None:
    processed = _mapping(state.get("processed_action_digests"))
    if len(context.action_summaries) > max_action_attempts:
        raise ValueError("specialist checkpoint exceeds its action budget")
    if len(processed) != len(context.action_summaries):
        raise ValueError(
            "specialist checkpoint action summaries and digests do not match"
        )
    if any(
        not isinstance(key, str) or not key or not isinstance(value, str) or not value
        for key, value in processed.items()
    ):
        raise ValueError("specialist checkpoint contains an invalid action digest")
    expected_digests = sorted(
        json_payload_hash(summary.to_dict()) for summary in context.action_summaries
    )
    if sorted(str(value) for value in processed.values()) != expected_digests:
        raise ValueError(
            "specialist checkpoint action result conflicts with its accepted digest"
        )


def _accepted_action_replay(
    *,
    state: Mapping[str, Any],
    context: SpecialistPolicyContext,
    decision: SpecialistDecision,
) -> bool:
    action_key = _action_attempt_key(context, decision)
    accepted_digest = _mapping(state.get("processed_action_digests")).get(action_key)
    if accepted_digest is None:
        return False
    if not context.action_summaries:
        raise ValueError(
            "accepted specialist action digest has no matching action summary"
        )
    summary = context.action_summaries[-1]
    if (
        summary.action_id != decision.action_id
        or summary.action_version != decision.action_version
        or accepted_digest != json_payload_hash(summary.to_dict())
    ):
        raise ValueError("specialist action replay conflicts with accepted result")
    return True


def _validate_decision_scope(
    decision: SpecialistDecision,
    task: SpecialistTask,
) -> None:
    if decision.task_id != task.task_id:
        raise ValueError("specialist decision task_id does not match task")
    if decision.authority_key != task.authority_key:
        raise ValueError("specialist decision authority does not match task")


def _validate_action_decision(
    *,
    context: SpecialistPolicyContext,
    decision: SpecialistDecision,
    capability: CapabilityDefinition,
) -> None:
    task = context.task
    if capability.side_effect not in task.permitted_side_effects:
        raise ValueError(
            f"specialist task does not permit {capability.side_effect.value} actions"
        )
    missing_gates = sorted(
        set(capability.policy_gates) - set(task.approved_policy_gates)
    )
    if missing_gates:
        raise ValueError(
            "specialist action requires unapproved policy gates: "
            + ", ".join(missing_gates)
        )
    input_slots = {slot.slot_id: slot for slot in capability.input_slots}
    output_slots = {slot.slot_id: slot for slot in capability.output_slots}
    unknown_inputs = sorted(set(decision.input_bindings) - set(input_slots))
    if unknown_inputs:
        raise ValueError(
            "specialist action has unknown input bindings: " + ", ".join(unknown_inputs)
        )
    unknown_outputs = sorted(set(decision.output_bindings) - set(output_slots))
    if unknown_outputs:
        raise ValueError(
            "specialist action has unknown output bindings: "
            + ", ".join(unknown_outputs)
        )
    available_refs = {reference.uri: reference for reference in context.available_refs}
    for slot in capability.input_slots:
        bound_uris = decision.input_bindings.get(slot.slot_id, ())
        _validate_cardinality(slot, len(bound_uris), label="action input")
        for uri in bound_uris:
            reference = available_refs.get(uri)
            if reference is None:
                raise ValueError(f"specialist action input is not available: {uri}")
            if (
                reference.artifact_type != slot.artifact_type
                or reference.domain_owner != slot.domain_owner
            ):
                raise ValueError(
                    f"specialist action input {slot.slot_id} has the wrong artifact type"
                )
    task_slots = {slot.slot_id: slot for slot in task.requested_outputs}
    for output_slot in capability.output_slots:
        target_slot_id = decision.output_bindings.get(output_slot.slot_id)
        if target_slot_id is None:
            if output_slot.required:
                raise ValueError(
                    f"specialist action output {output_slot.slot_id} is not bound"
                )
            continue
        target_slot = task_slots.get(target_slot_id)
        if target_slot is None:
            raise ValueError(
                f"specialist action targets unknown task slot: {target_slot_id}"
            )
        if (
            target_slot.artifact_type != output_slot.artifact_type
            or target_slot.domain_owner != output_slot.domain_owner
        ):
            raise ValueError(
                f"specialist output {output_slot.slot_id} does not match task slot "
                f"{target_slot_id}"
            )


def _accept_action_outcome(
    *,
    context: SpecialistPolicyContext,
    decision: SpecialistDecision,
    registration: RegisteredSpecialistAction,
    outcome: SpecialistActionOutcome,
) -> tuple[tuple[SpecialistHandoff, ...], dict[str, tuple[str, ...]]]:
    capability = registration.capability
    if (
        outcome.action_id != capability.capability_id
        or outcome.action_version != capability.version
    ):
        raise ValueError(
            "specialist action outcome identity does not match registration"
        )
    declared_outputs = {slot.slot_id: slot for slot in capability.output_slots}
    unknown_outputs = sorted(set(outcome.outputs) - set(declared_outputs))
    if unknown_outputs:
        raise ValueError(
            "specialist action returned undeclared outputs: "
            + ", ".join(unknown_outputs)
        )
    existing_ids = {handoff.handoff_id for handoff in context.handoffs}
    accepted = list(context.handoffs)
    bindings = {key: tuple(value) for key, value in context.output_bindings.items()}
    authority = get_decision_authority(context.task.authority_key)
    for output_slot in capability.output_slots:
        produced = outcome.outputs.get(output_slot.slot_id, ())
        if outcome.status is SpecialistActionStatus.SUCCEEDED:
            _validate_cardinality(output_slot, len(produced), label="action output")
        elif produced:
            _validate_max_cardinality(output_slot, len(produced), label="action output")
        target_slot_id = decision.output_bindings.get(output_slot.slot_id)
        if produced and target_slot_id is None:
            raise ValueError(
                f"specialist action output {output_slot.slot_id} has no task binding"
            )
        for handoff in produced:
            if handoff.handoff_id in existing_ids:
                raise ValueError(
                    f"specialist action repeated handoff_id: {handoff.handoff_id}"
                )
            if handoff.artifact_uri is None:
                raise ValueError(
                    "specialist action handoffs require canonical artifact URIs"
                )
            if handoff.artifact_type != output_slot.artifact_type:
                raise ValueError(
                    f"specialist action output {output_slot.slot_id} has the wrong artifact type"
                )
            if handoff.domain_owner != output_slot.domain_owner:
                raise ValueError("specialist action handoff has the wrong domain owner")
            if handoff.domain_owner not in authority.artifact_domains:
                raise ValueError(
                    "specialist action handoff exceeds specialist authority"
                )
            if handoff.producer_tool != capability.producer_tool:
                raise ValueError(
                    "specialist action handoff has the wrong producer tool"
                )
            if handoff.requested_by != context.task.requested_by:
                raise ValueError("specialist action handoff has the wrong requester")
            if handoff.actor != authority.display_name:
                raise ValueError("specialist action handoff has the wrong actor")
            parse_research_artifact_uri(handoff.artifact_uri)
            existing_ids.add(handoff.handoff_id)
            accepted.append(handoff)
            current = bindings.get(target_slot_id or "", ())
            bindings[target_slot_id or ""] = (*current, handoff.handoff_id)
    _validate_bound_task_slots(
        context.task, tuple(accepted), bindings, require_all=False
    )
    return tuple(accepted), bindings


def _validate_task_completion(context: SpecialistPolicyContext) -> None:
    _validate_bound_task_slots(
        context.task,
        context.handoffs,
        context.output_bindings,
        require_all=True,
    )


def _validate_bound_task_slots(
    task: SpecialistTask,
    handoffs: tuple[SpecialistHandoff, ...],
    bindings: Mapping[str, tuple[str, ...]],
    *,
    require_all: bool,
) -> None:
    task_slots = {slot.slot_id: slot for slot in task.requested_outputs}
    unknown_slots = sorted(set(bindings) - set(task_slots))
    if unknown_slots:
        raise ValueError(
            "specialist result binds unknown task slots: " + ", ".join(unknown_slots)
        )
    handoffs_by_id = {handoff.handoff_id: handoff for handoff in handoffs}
    all_bound_ids: list[str] = []
    for slot in task.requested_outputs:
        handoff_ids = bindings.get(slot.slot_id, ())
        if require_all:
            _validate_cardinality(slot, len(handoff_ids), label="task output")
        else:
            _validate_max_cardinality(slot, len(handoff_ids), label="task output")
        for handoff_id in handoff_ids:
            handoff = handoffs_by_id.get(handoff_id)
            if handoff is None:
                raise ValueError(
                    f"task output binding references unknown handoff: {handoff_id}"
                )
            if (
                handoff.artifact_type != slot.artifact_type
                or handoff.domain_owner != slot.domain_owner
            ):
                raise ValueError(
                    f"task output binding {slot.slot_id} has the wrong artifact type"
                )
            all_bound_ids.append(handoff_id)
    if len(all_bound_ids) != len(set(all_bound_ids)):
        raise ValueError("specialist handoffs cannot resolve more than one task slot")
    if set(all_bound_ids) != set(handoffs_by_id):
        raise ValueError(
            "every specialist handoff must resolve one requested task slot"
        )


def _validate_cardinality(slot: ArtifactSlot, count: int, *, label: str) -> None:
    _validate_max_cardinality(slot, count, label=label)
    if not slot.required:
        return
    if slot.cardinality is ArtifactCardinality.EXACTLY_ONE and count != 1:
        raise ValueError(f"required {label} {slot.slot_id} needs exactly one artifact")
    if slot.cardinality is ArtifactCardinality.ONE_OR_MORE and count < 1:
        raise ValueError(f"required {label} {slot.slot_id} needs one or more artifacts")


def _validate_max_cardinality(
    slot: ArtifactSlot,
    count: int,
    *,
    label: str,
) -> None:
    if (
        slot.cardinality
        in {
            ArtifactCardinality.EXACTLY_ONE,
            ArtifactCardinality.ZERO_OR_ONE,
        }
        and count > 1
    ):
        raise ValueError(f"{label} {slot.slot_id} accepts at most one artifact")


def _terminal_result(
    context: SpecialistPolicyContext,
    *,
    status: SpecialistResultStatus,
    prerequisites: tuple[Prerequisite, ...] = (),
    warnings: tuple[ResearchIssue, ...] = (),
    blockers: tuple[ResearchIssue, ...] = (),
    errors: tuple[ResearchIssue, ...] = (),
) -> SpecialistResult:
    authority = get_decision_authority(context.task.authority_key)
    return SpecialistResult(
        task_id=context.task.task_id,
        authority_key=context.task.authority_key,
        status=status,
        requested_by=context.task.requested_by,
        actor=authority.display_name,
        handoffs=context.handoffs,
        output_bindings=context.output_bindings,
        prerequisites=prerequisites,
        warnings=warnings,
        blockers=blockers,
        errors=errors,
    )


def _failed_state(
    state: Mapping[str, Any],
    *,
    code: str,
    message: str,
    context: SpecialistPolicyContext | None = None,
) -> SpecialistGraphState:
    issue = ResearchIssue(code=code, message=message)
    result: dict[str, Any] = {}
    if context is not None:
        result = _terminal_result(
            context,
            status=SpecialistResultStatus.FAILED,
            warnings=_state_issues(state, "warnings"),
            errors=(issue,),
        ).to_dict()
    return {
        "result": result,
        "next_route": "done",
        "status": "failed",
        "public_status": "failed_validation",
        "prerequisites": [],
        "blockers": [],
        "errors": [issue.to_dict()],
    }


def _identity_payload(authority_key: str) -> dict[str, Any]:
    authority = get_decision_authority(authority_key)
    return {
        "authority_key": authority.key,
        "display_name": authority.display_name,
        "decision": authority.decision,
        "artifact_domains": list(authority.artifact_domains),
        "prohibited_authority": list(authority.prohibited_authority),
        "optional_producer": authority.optional_producer,
    }


def _state_issues(
    state: Mapping[str, Any],
    key: str,
) -> tuple[ResearchIssue, ...]:
    return tuple(
        ResearchIssue.from_dict(item) for item in _mapping_sequence(state.get(key))
    )


def _route_after_policy(state: SpecialistGraphState) -> str:
    return (
        "execute_registered_action"
        if state.get("next_route") == "execute_registered_action"
        and state.get("status") == "running"
        else "done"
    )


def _route_after_action(state: SpecialistGraphState) -> str:
    return (
        "select_specialist_action"
        if state.get("next_route") == "select_specialist_action"
        and state.get("status") == "running"
        else "done"
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("specialist graph state field must be an object")
    return value


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ValueError("specialist graph state field must be an array")
    items: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("specialist graph array entries must be objects")
        items.append(item)
    return tuple(items)


def _text_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ValueError(f"{label} must be an array")
    normalized = tuple(str(item) for item in value)
    if any(not item.strip() for item in normalized):
        raise ValueError(f"{label} entries must be non-empty strings")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} entries must be unique")
    return normalized
