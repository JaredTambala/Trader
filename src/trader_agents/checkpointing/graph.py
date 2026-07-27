"""LangGraph shell for resumable, externally executed research workflows."""

from __future__ import annotations

from typing import Any, Literal, Mapping

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from trader_research.foundation import json_payload_hash
from trader_research.governance import (
    ArtifactCardinality,
    CapabilityDefinition,
    RetryDisposition,
    WorkflowPlan,
    WorkflowStep,
    WorkflowStepResult,
    WorkflowStepStatus,
)

from .domain import (
    CheckpointStepSummary,
    MAX_STEP_ATTEMPTS,
    WorkflowCheckpointState,
    result_digest,
    validate_checkpoint_bounds,
    workflow_plan_digest,
)


def build_resumable_workflow_graph(
    *,
    plan: WorkflowPlan,
    checkpointer: BaseCheckpointSaver[Any],
) -> Any:
    """Compile a checkpointed shell that waits for external step results.

    The graph does not invoke MCP or service implementations. Each plan step
    produces a bounded interrupt request. A caller resumes the same thread with
    a `WorkflowStepResult` payload after external execution.

    Args:
        plan: Ready immutable workflow plan.
        checkpointer: LangGraph saver for operational state.

    Returns:
        Compiled graph supporting interruption and resume.
    """
    ordered_steps = _ordered_steps(plan)
    expected_digest = workflow_plan_digest(plan)
    capabilities = {
        item.capability_id: item for item in plan.capabilities
    }
    plan_slots = {item.slot_id: item for item in plan.artifact_slots}

    def prepare_next(
        state: WorkflowCheckpointState,
    ) -> WorkflowCheckpointState:
        _validate_state_identity(state, plan, expected_digest)
        validate_checkpoint_bounds(state)
        index = int(state.get("current_step_index", 0))
        if index >= len(ordered_steps):
            return {
                "status": "completed",
                "public_status": "completed",
                "pending_step_id": "",
            }
        step = ordered_steps[index]
        return {
            "status": "awaiting_result",
            "public_status": "awaiting_step_result",
            "pending_step_id": step.step_id,
        }

    def await_result(
        state: WorkflowCheckpointState,
    ) -> WorkflowCheckpointState:
        _validate_state_identity(state, plan, expected_digest)
        validate_checkpoint_bounds(state)
        index = int(state.get("current_step_index", 0))
        if index >= len(ordered_steps):
            return {
                "status": "completed",
                "public_status": "completed",
                "pending_step_id": "",
            }
        step = ordered_steps[index]
        capability = capabilities[step.capability_id]
        attempt = int(state.get("next_attempt", 1))
        raw_result = interrupt(
            {
                "kind": "workflow_step_result_required",
                "workflow_id": state["workflow_id"],
                "plan_id": plan.plan_id,
                "step_id": step.step_id,
                "capability_id": capability.capability_id,
                "producer_tool": capability.producer_tool,
                "side_effect": capability.side_effect.value,
                "attempt": attempt,
                "configuration_digest": _configuration_digest(step),
            }
        )
        try:
            result = WorkflowStepResult.from_dict(_mapping(raw_result))
            if result.idempotency_key not in state.get(
                "processed_result_digests",
                {},
            ):
                _validate_step_result(
                    state=state,
                    plan=plan,
                    step=step,
                    result=result,
                    attempt=attempt,
                    capability=capability,
                    plan_slots=plan_slots,
                )
        except ValueError as exc:
            return _terminal_error(state, "invalid_step_result", str(exc))
        return _record_result(state, result, len(ordered_steps))

    graph = StateGraph(WorkflowCheckpointState)
    graph.add_node("prepare_next_step", prepare_next)
    graph.add_node("await_step_result", await_result)
    graph.add_edge(START, "prepare_next_step")
    graph.add_conditional_edges(
        "prepare_next_step",
        _route_after_prepare,
        {"await": "await_step_result", "end": END},
    )
    graph.add_conditional_edges(
        "await_step_result",
        _route_after_result,
        {"continue": "prepare_next_step", "end": END},
    )
    return graph.compile(checkpointer=checkpointer)


def _record_result(
    state: WorkflowCheckpointState,
    result: WorkflowStepResult,
    step_count: int,
) -> WorkflowCheckpointState:
    attempts = list(state.get("step_attempts", []))
    processed = dict(state.get("processed_result_digests", {}))
    digest = result_digest(result)
    existing = processed.get(result.idempotency_key)
    if existing is not None:
        if existing != digest:
            return _terminal_error(
                state,
                "idempotency_conflict",
                "workflow step result idempotency key was reused with different content",
            )
        warnings = list(state.get("warnings", []))
        warnings.append(
            {
                "code": "duplicate_step_result_ignored",
                "message": (
                    f"Duplicate result {result.result_id} was already accepted."
                ),
                "details": {"idempotency_key": result.idempotency_key},
            }
        )
        return {
            "status": "ready",
            "public_status": "duplicate_result_ignored",
            "pending_step_id": "",
            "warnings": warnings,
        }
    if len(attempts) >= MAX_STEP_ATTEMPTS:
        return _terminal_error(
            state,
            "step_attempt_limit_exceeded",
            f"workflow supports at most {MAX_STEP_ATTEMPTS} step attempts",
        )
    processed[result.idempotency_key] = digest
    attempts.append(CheckpointStepSummary.from_result(result).to_dict())
    update: WorkflowCheckpointState = {
        "step_attempts": attempts,
        "processed_result_digests": processed,
        "pending_step_id": "",
        "warnings": [
            *state.get("warnings", []),
            *(item.to_dict() for item in result.warnings),
        ],
    }
    if result.status is WorkflowStepStatus.SUCCEEDED:
        next_index = int(state.get("current_step_index", 0)) + 1
        update.update(
            {
                "current_step_index": next_index,
                "next_attempt": 1,
                "status": "completed" if next_index >= step_count else "ready",
                "public_status": (
                    "completed"
                    if next_index >= step_count
                    else "step_succeeded"
                ),
            }
        )
        return update
    retryable = result.retry is RetryDisposition.RETRYABLE
    update["blockers"] = [
        *state.get("blockers", []),
        *(item.to_dict() for item in result.blockers),
    ]
    if retryable:
        update.update(
            {
                "next_attempt": int(state.get("next_attempt", 1)) + 1,
                "status": "ready",
                "public_status": "step_retry_required",
            }
        )
        return update
    update.update(
        {
            "status": (
                "blocked"
                if result.status is WorkflowStepStatus.BLOCKED
                else "failed"
            ),
            "public_status": (
                "blocked_terminal"
                if result.status is WorkflowStepStatus.BLOCKED
                else "failed_terminal"
            ),
        }
    )
    return update


def _validate_step_result(
    *,
    state: WorkflowCheckpointState,
    plan: WorkflowPlan,
    step: WorkflowStep,
    result: WorkflowStepResult,
    attempt: int,
    capability: CapabilityDefinition,
    plan_slots: Mapping[str, Any],
) -> None:
    if result.plan_id != plan.plan_id:
        raise ValueError("workflow step result plan_id does not match the plan")
    if result.step_id != step.step_id:
        raise ValueError("workflow step result step_id does not match the pending step")
    if result.attempt != attempt:
        raise ValueError("workflow step result attempt does not match the pending attempt")
    if result.command != capability.producer_tool:
        raise ValueError("workflow step result command does not match the capability")
    if result.side_effect is not capability.side_effect:
        raise ValueError(
            "workflow step result side_effect does not match the capability"
        )
    if result.requested_by != state["workflow_id"]:
        raise ValueError(
            "workflow step result requested_by must be the workflow_id"
        )
    if result.status is not WorkflowStepStatus.SUCCEEDED:
        return
    refs_by_type: dict[str, int] = {}
    for reference in result.produced_artifact_refs:
        refs_by_type[reference.artifact_type] = (
            refs_by_type.get(reference.artifact_type, 0) + 1
        )
    slots_by_type: dict[str, list[Any]] = {}
    for slot_id in step.output_bindings.values():
        slot = plan_slots[slot_id]
        slots_by_type.setdefault(slot.artifact_type, []).append(slot)
    unexpected_types = set(refs_by_type).difference(slots_by_type)
    if unexpected_types:
        raise ValueError(
            "successful step result contains undeclared artifact types: "
            + ", ".join(sorted(unexpected_types))
        )
    for artifact_type, slots in slots_by_type.items():
        count = refs_by_type.get(artifact_type, 0)
        minimum = sum(1 for slot in slots if slot.required)
        if count < minimum:
            raise ValueError(
                f"successful step result is missing required {artifact_type}"
            )
        has_unbounded_slot = any(
            slot.cardinality is ArtifactCardinality.ONE_OR_MORE
            for slot in slots
        )
        if not has_unbounded_slot and count > len(slots):
            raise ValueError(
                f"step result exceeds cardinality for {artifact_type}"
            )


def _validate_state_identity(
    state: WorkflowCheckpointState,
    plan: WorkflowPlan,
    expected_digest: str,
) -> None:
    if state.get("plan_id") != plan.plan_id:
        raise ValueError("checkpoint plan_id does not match the compiled plan")
    if state.get("plan_digest") != expected_digest:
        raise ValueError("checkpoint plan digest does not match the compiled plan")
    if not str(state.get("workflow_id") or "").strip():
        raise ValueError("checkpoint workflow_id is required")


def _ordered_steps(plan: WorkflowPlan) -> tuple[WorkflowStep, ...]:
    by_id = {item.step_id: item for item in plan.steps}
    order_index = {item.step_id: index for index, item in enumerate(plan.steps)}
    remaining = set(by_id)
    completed: set[str] = set()
    ordered: list[WorkflowStep] = []
    while remaining:
        ready = sorted(
            (
                step_id
                for step_id in remaining
                if set(by_id[step_id].depends_on).issubset(completed)
            ),
            key=order_index.__getitem__,
        )
        if not ready:
            raise ValueError("workflow step dependencies contain a cycle")
        for step_id in ready:
            ordered.append(by_id[step_id])
            completed.add(step_id)
            remaining.remove(step_id)
    return tuple(ordered)


def _configuration_digest(step: WorkflowStep) -> str:
    return json_payload_hash(dict(step.configuration))


def _terminal_error(
    state: WorkflowCheckpointState,
    code: str,
    message: str,
) -> WorkflowCheckpointState:
    return {
        "status": "failed",
        "public_status": "failed_validation",
        "pending_step_id": "",
        "errors": [
            *state.get("errors", []),
            {"code": code, "message": message, "details": {}},
        ],
    }


def _route_after_prepare(
    state: WorkflowCheckpointState,
) -> Literal["await", "end"]:
    return "await" if state.get("status") == "awaiting_result" else "end"


def _route_after_result(
    state: WorkflowCheckpointState,
) -> Literal["continue", "end"]:
    return (
        "continue"
        if state.get("status") in {"ready", "awaiting_result"}
        else "end"
    )


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}
