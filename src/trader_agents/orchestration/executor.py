"""Mechanical MCP executor for one compiled, checkpointed research workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from trader_mcp.constants import (
    REGISTERED_TOOL_NAMES,
    RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
    RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
)
from trader_research.foundation import (
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    json_payload_hash,
    parse_research_artifact_uri,
    stable_research_id,
)
from trader_research.governance import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    EXPERIMENT_PROTOCOL,
    PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
    RESEARCH_OBJECTIVE,
    WORKFLOW_OUTCOME,
    WORKFLOW_PLAN,
    ArtifactReportRef,
    CapabilitySideEffect,
    ResearchIssue,
    RetryDisposition,
    WorkflowOutcome,
    WorkflowOutcomeStatus,
    WorkflowStepResult,
    WorkflowStepStatus,
    agent_owner_for_tool,
    artifact_report_ref,
)

from trader_agents.checkpointing import (
    build_resumable_workflow_graph,
    build_workflow_checkpoint_state,
    workflow_public_state,
    workflow_thread_config,
)
from trader_agents.tool_client import McpToolClient

from .compiler import (
    CompiledResearchWorkflow,
    InvocationMode,
    ToolInvocation,
)


WORKFLOW_EXECUTOR_ACTOR = "workflow_executor"
_TERMINAL_STATUSES = frozenset({"completed", "blocked", "failed"})
_RETRYABLE_ERROR_CODES = frozenset(
    {
        "event_store_connection_unavailable",
        "provider_connection_unavailable",
        "request_timeout",
        "temporary_failure",
        "tool_transport_error",
    }
)


class WorkflowExecutionError(RuntimeError):
    """Raised when executor infrastructure cannot establish canonical state."""


class WorkflowExecutionInterrupted(RuntimeError):
    """Raised after a caller-requested pause with the checkpoint preserved."""

    def __init__(self, public_state: Mapping[str, Any]) -> None:
        """Capture the public checkpoint state available to a later resume."""
        super().__init__("workflow execution paused before the next tool call")
        self.public_state = dict(public_state)


@dataclass(frozen=True)
class WorkflowExecution:
    """Terminal result from one mechanical workflow execution.

    Attributes:
        outcome: Deterministic terminal workflow summary.
        public_state: Bounded checkpoint projection for operators.
        outcome_ref: Canonical persisted reference to the terminal outcome.
    """

    outcome: WorkflowOutcome
    public_state: Mapping[str, Any]
    outcome_ref: ArtifactReportRef


async def execute_compiled_research_workflow(
    *,
    compiled: CompiledResearchWorkflow,
    workflow_id: str,
    tool_client: McpToolClient,
    checkpointer: BaseCheckpointSaver[Any],
    artifact_store: ResearchArtifactStore,
    max_tool_calls: int | None = None,
) -> WorkflowExecution:
    """Run or resume a compiled workflow through registered MCP tools only.

    Matching canonical objective, protocol, plan, and outcome records are
    revalidated and reused on re-entry. Accepted workflow steps remain protected
    by the checkpoint shell, so resuming a completed or interrupted workflow does
    not repeat their registered MCP calls.

    Args:
        compiled: Deterministically compiled approved workflow.
        workflow_id: Stable operational identity and execution provenance.
        tool_client: MCP boundary used for registered workflow operations.
        checkpointer: Operational saver for accepted step progress.
        artifact_store: Canonical store shared with the MCP server.
        max_tool_calls: Optional deliberate interruption limit for this call.

    Returns:
        Terminal workflow outcome, bounded state, and canonical outcome ref.

    Raises:
        WorkflowExecutionInterrupted: If the requested call limit is reached.
        WorkflowExecutionError: If canonical state or MCP envelopes conflict.
        ValueError: If the workflow identity or call limit is invalid.
    """
    workflow_id = _required_text(workflow_id, "workflow_id")
    if max_tool_calls is not None and max_tool_calls < 0:
        raise ValueError("max_tool_calls cannot be negative")
    tool_calls = 0
    if not _workflow_registration_exists(
        compiled=compiled,
        workflow_id=workflow_id,
        artifact_store=artifact_store,
    ):
        await _register_workflow(
            compiled=compiled,
            workflow_id=workflow_id,
            tool_client=tool_client,
        )
        if not _workflow_registration_exists(
            compiled=compiled,
            workflow_id=workflow_id,
            artifact_store=artifact_store,
        ):
            raise WorkflowExecutionError(
                "workflow registration succeeded without canonical records"
            )
    graph = build_resumable_workflow_graph(
        plan=compiled.plan,
        checkpointer=checkpointer,
    )
    config = workflow_thread_config(workflow_id)
    snapshot = await graph.aget_state(config)
    if snapshot.values:
        state = dict(snapshot.values)
    else:
        state = dict(
            await graph.ainvoke(
                build_workflow_checkpoint_state(
                    workflow_id=workflow_id,
                    plan=compiled.plan,
                ),
                config,
            )
        )

    while str(state.get("status") or "") not in _TERMINAL_STATUSES:
        if max_tool_calls is not None and tool_calls >= max_tool_calls:
            raise WorkflowExecutionInterrupted(workflow_public_state(state))
        step_id = _required_text(
            state.get("pending_step_id"),
            "pending workflow step",
        )
        step = _step_by_id(compiled, step_id)
        capability = _capability_by_id(compiled, step.capability_id)
        invocation = compiled.invocation_for_step(step_id)
        if invocation.tool_name != capability.producer_tool:
            raise WorkflowExecutionError(
                "compiled invocation tool does not match capability"
            )
        if invocation.tool_name not in REGISTERED_TOOL_NAMES:
            raise WorkflowExecutionError(
                f"compiled invocation is not registered: {invocation.tool_name}"
            )
        bindings = _artifact_bindings(compiled, state)
        try:
            arguments = _build_arguments(
                invocation=invocation,
                bindings=bindings,
                artifact_store=artifact_store,
            )
        except (
            ResearchArtifactStoreError,
            ValueError,
            WorkflowExecutionError,
        ) as exc:
            result = _failed_result(
                workflow_id=workflow_id,
                plan_id=compiled.plan.plan_id,
                step_id=step_id,
                attempt=int(state.get("next_attempt", 1)),
                tool_name=invocation.tool_name,
                side_effect=capability.side_effect,
                code="workflow_input_revalidation_failed",
                message=str(exc),
                retry=RetryDisposition.TERMINAL,
            )
        else:
            arguments["requested_by"] = workflow_id
            arguments["actor"] = WORKFLOW_EXECUTOR_ACTOR
            tool_calls += 1
            attempt = int(state.get("next_attempt", 1))
            try:
                raw_response = await tool_client.call_tool(
                    invocation.tool_name,
                    arguments,
                )
            except Exception as exc:
                result = _failed_result(
                    workflow_id=workflow_id,
                    plan_id=compiled.plan.plan_id,
                    step_id=step_id,
                    attempt=attempt,
                    tool_name=invocation.tool_name,
                    side_effect=capability.side_effect,
                    code="tool_transport_error",
                    message=str(exc),
                    retry=(
                        RetryDisposition.RETRYABLE
                        if attempt < 3
                        else RetryDisposition.TERMINAL
                    ),
                )
            else:
                try:
                    raw_result = dict(raw_response)
                    result = _adapt_tool_result(
                        workflow_id=workflow_id,
                        plan_id=compiled.plan.plan_id,
                        step_id=step_id,
                        attempt=attempt,
                        capability_side_effect=capability.side_effect,
                        tool_name=invocation.tool_name,
                        arguments=arguments,
                        raw_result=raw_result,
                        artifact_store=artifact_store,
                    )
                except Exception as exc:
                    result = _failed_result(
                        workflow_id=workflow_id,
                        plan_id=compiled.plan.plan_id,
                        step_id=step_id,
                        attempt=attempt,
                        tool_name=invocation.tool_name,
                        side_effect=capability.side_effect,
                        code="workflow_result_revalidation_failed",
                        message=str(exc),
                        retry=RetryDisposition.TERMINAL,
                    )
        state = dict(
            await graph.ainvoke(
                Command(resume=result.to_dict()),
                config,
            )
        )

    outcome = _build_outcome(
        compiled=compiled,
        workflow_id=workflow_id,
        state=state,
    )
    outcome_ref = _existing_outcome_ref(
        outcome=outcome,
        workflow_id=workflow_id,
        artifact_store=artifact_store,
    )
    if outcome_ref is None:
        recorded_ref = await _record_outcome(
            outcome=outcome,
            workflow_id=workflow_id,
            tool_client=tool_client,
        )
        outcome_ref = _existing_outcome_ref(
            outcome=outcome,
            workflow_id=workflow_id,
            artifact_store=artifact_store,
        )
        if outcome_ref is None or outcome_ref.uri != recorded_ref.uri:
            raise WorkflowExecutionError(
                "workflow outcome succeeded without its canonical record"
            )
    return WorkflowExecution(
        outcome=outcome,
        public_state=workflow_public_state(state),
        outcome_ref=outcome_ref,
    )


async def _register_workflow(
    *,
    compiled: CompiledResearchWorkflow,
    workflow_id: str,
    tool_client: McpToolClient,
) -> None:
    result = dict(
        await tool_client.call_tool(
            RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
            {
                "objective": compiled.objective.to_dict(),
                "protocol": compiled.protocol.to_dict(),
                "workflow_plan": compiled.plan.to_dict(),
                "requested_by": workflow_id,
                "actor": WORKFLOW_EXECUTOR_ACTOR,
            },
        )
    )
    _require_successful_envelope(
        raw_result=result,
        tool_name=RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
    )


def _workflow_registration_exists(
    *,
    compiled: CompiledResearchWorkflow,
    workflow_id: str,
    artifact_store: ResearchArtifactStore,
) -> bool:
    expected = (
        (
            RESEARCH_OBJECTIVE,
            compiled.objective.objective_id,
            compiled.objective.to_dict(),
            compiled.objective.status.value,
        ),
        (
            EXPERIMENT_PROTOCOL,
            compiled.protocol.protocol_id,
            compiled.protocol.to_dict(),
            compiled.protocol.status.value,
        ),
        (
            WORKFLOW_PLAN,
            compiled.plan.plan_id,
            compiled.plan.to_dict(),
            compiled.plan.status.value,
        ),
    )
    found = 0
    for artifact_type, artifact_id, payload, status in expected:
        try:
            record = artifact_store.load_artifact_record(artifact_type, artifact_id)
        except ResearchArtifactNotFound:
            continue
        except ResearchArtifactStoreError as exc:
            raise WorkflowExecutionError(
                f"workflow registration lookup failed: {artifact_type}:{artifact_id}"
            ) from exc
        _validate_existing_workflow_record(
            record=record,
            artifact_type=artifact_type,
            payload=payload,
            status=status,
            workflow_id=workflow_id,
            producer_tool=RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
        )
        found += 1
    return found == len(expected)


async def _record_outcome(
    *,
    outcome: WorkflowOutcome,
    workflow_id: str,
    tool_client: McpToolClient,
) -> ArtifactReportRef:
    result = dict(
        await tool_client.call_tool(
            RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
            {
                "outcome": outcome.to_dict(),
                "requested_by": workflow_id,
                "actor": WORKFLOW_EXECUTOR_ACTOR,
            },
        )
    )
    envelope = _require_successful_envelope(
        raw_result=result,
        tool_name=RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
    )
    refs = _artifact_refs(envelope.get("artifacts"))
    if len(refs) != 1 or refs[0].artifact_type != outcome.artifact_type:
        raise WorkflowExecutionError(
            "workflow outcome tool did not return one canonical outcome ref"
        )
    return refs[0]


def _existing_outcome_ref(
    *,
    outcome: WorkflowOutcome,
    workflow_id: str,
    artifact_store: ResearchArtifactStore,
) -> ArtifactReportRef | None:
    try:
        record = artifact_store.load_artifact_record(
            WORKFLOW_OUTCOME,
            outcome.outcome_id,
        )
    except ResearchArtifactNotFound:
        return None
    except ResearchArtifactStoreError as exc:
        raise WorkflowExecutionError("workflow outcome lookup failed") from exc
    _validate_existing_workflow_record(
        record=record,
        artifact_type=WORKFLOW_OUTCOME,
        payload=outcome.to_dict(),
        status=outcome.status.value,
        workflow_id=workflow_id,
        producer_tool=RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
    )
    return ArtifactReportRef(
        artifact_id=record.artifact_id,
        artifact_type=record.artifact_type,
        domain_owner=record.domain_owner,
        uri=record.uri,
        metadata={
            "payload_sha256": json_payload_hash(record.payload),
            "producer_tool": record.producer_tool,
            "requested_by": record.requested_by,
            "actor": record.actor,
            "status": record.status,
        },
    )


def _validate_existing_workflow_record(
    *,
    record: ResearchArtifactRecord,
    artifact_type: str,
    payload: Mapping[str, Any],
    status: str,
    workflow_id: str,
    producer_tool: str,
) -> None:
    if record.artifact_type != artifact_type or record.payload != payload:
        raise WorkflowExecutionError(
            f"canonical workflow record content drift: {record.uri}"
        )
    if record.domain_owner != DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type]:
        raise WorkflowExecutionError(
            f"canonical workflow record authority drift: {record.uri}"
        )
    if record.producer_tool != producer_tool:
        raise WorkflowExecutionError(
            f"canonical workflow record producer drift: {record.uri}"
        )
    if record.requested_by != workflow_id or record.actor != WORKFLOW_EXECUTOR_ACTOR:
        raise WorkflowExecutionError(
            f"canonical workflow record provenance drift: {record.uri}"
        )
    if record.status != status:
        raise WorkflowExecutionError(
            f"canonical workflow record status drift: {record.uri}"
        )


def _build_arguments(
    *,
    invocation: ToolInvocation,
    bindings: Mapping[str, tuple[ArtifactReportRef, ...]],
    artifact_store: ResearchArtifactStore,
) -> dict[str, Any]:
    arguments = dict(invocation.static_arguments)
    for argument, slot_id in invocation.ref_arguments.items():
        arguments[argument] = _one_ref(bindings, slot_id).uri
    for argument, slot_id in invocation.ref_list_arguments.items():
        arguments[argument] = [item.uri for item in bindings.get(slot_id, ())]
    payloads = {
        argument: _load_pinned_payload(
            _one_ref(bindings, slot_id),
            artifact_store,
        )
        for argument, slot_id in invocation.payload_arguments.items()
    }
    if invocation.mode is InvocationMode.DIRECT:
        arguments.update(payloads)
        return arguments
    if invocation.mode is InvocationMode.RISK_STACK:
        arguments["risk_managers"] = [
            {
                "implementation_validation_ref": _one_ref(
                    bindings,
                    _required_text(entry.get("slot_id"), "risk slot_id"),
                ).uri,
                "parameters": dict(_mapping(entry.get("parameters"))),
                "tunable_fields": list(_sequence(entry.get("tunable_fields"))),
            }
            for entry in invocation.risk_entries
        ]
        return arguments
    if invocation.mode is InvocationMode.SELECTED_HOLDOUT_BACKTEST:
        optimization = _mapping(payloads.pop("optimization_run"))
        selected = _mapping(optimization.get("selected_child_refs"))
        strategy_ref = _required_text(
            selected.get("strategy_specification_validation_id"),
            "selected strategy validation",
        )
        risk_ref = selected.get("risk_stack_specification_validation_id")
        arguments.update(payloads)
        arguments["strategy_specification_validation_ref"] = strategy_ref
        arguments["risk_stack_specification_validation_ref"] = (
            str(risk_ref) if risk_ref is not None else None
        )
        arguments["selection_origin_ref"] = _required_text(
            optimization.get("optimization_run_id"),
            "optimization run ID",
        )
        return arguments
    raise WorkflowExecutionError(
        f"unsupported invocation mode: {invocation.mode.value}"
    )


def _adapt_tool_result(
    *,
    workflow_id: str,
    plan_id: str,
    step_id: str,
    attempt: int,
    capability_side_effect: CapabilitySideEffect,
    tool_name: str,
    arguments: Mapping[str, Any],
    raw_result: Mapping[str, Any],
    artifact_store: ResearchArtifactStore,
) -> WorkflowStepResult:
    envelope = _mapping(raw_result.get("structuredContent"))
    if not envelope:
        return _failed_result(
            workflow_id=workflow_id,
            plan_id=plan_id,
            step_id=step_id,
            attempt=attempt,
            tool_name=tool_name,
            side_effect=capability_side_effect,
            code="missing_structured_content",
            message="MCP result did not include structuredContent.",
            retry=RetryDisposition.TERMINAL,
        )
    if envelope.get("command") != tool_name:
        raise WorkflowExecutionError(
            "MCP envelope command does not match the compiled capability"
        )
    if envelope.get("agent_owner") != agent_owner_for_tool(tool_name):
        raise WorkflowExecutionError(
            "MCP envelope agent owner does not match tool registration"
        )
    if envelope.get("side_effect") != capability_side_effect.value:
        raise WorkflowExecutionError(
            "MCP envelope side effect does not match the compiled capability"
        )
    warnings = tuple(
        _issue(item, default_code="tool_warning")
        for item in _sequence(envelope.get("warnings"))
    )
    envelope_errors = tuple(
        _issue(item, default_code="tool_error")
        for item in _sequence(envelope.get("errors"))
    )
    ok = envelope.get("ok") is True and raw_result.get("isError") is not True
    key = stable_research_id(
        "workflow_step_request",
        {
            "workflow_id": workflow_id,
            "plan_id": plan_id,
            "step_id": step_id,
            "attempt": attempt,
            "tool_name": tool_name,
            "arguments": arguments,
        },
    )
    if not ok:
        blocker = envelope_errors or (
            ResearchIssue(
                code="tool_failed",
                message=f"{tool_name} returned an unsuccessful envelope.",
            ),
        )
        retry = (
            RetryDisposition.RETRYABLE
            if any(item.code in _RETRYABLE_ERROR_CODES for item in blocker)
            else RetryDisposition.TERMINAL
        )
        status = (
            WorkflowStepStatus.BLOCKED
            if _is_blocking_error(blocker)
            else WorkflowStepStatus.FAILED
        )
        return WorkflowStepResult(
            result_id=stable_research_id(
                "workflow_step_result",
                {"idempotency_key": key, "errors": [i.to_dict() for i in blocker]},
            ),
            plan_id=plan_id,
            step_id=step_id,
            attempt=attempt,
            command=tool_name,
            side_effect=capability_side_effect,
            status=status,
            requested_by=workflow_id,
            actor=WORKFLOW_EXECUTOR_ACTOR,
            idempotency_key=key,
            warnings=warnings,
            blockers=blocker,
            retry=retry,
        )
    refs = tuple(
        _pin_output_ref(item, artifact_store)
        for item in _artifact_refs(envelope.get("artifacts"))
    )
    return WorkflowStepResult(
        result_id=stable_research_id(
            "workflow_step_result",
            {
                "idempotency_key": key,
                "artifact_uris": [item.uri for item in refs],
                "warnings": [item.to_dict() for item in warnings],
            },
        ),
        plan_id=plan_id,
        step_id=step_id,
        attempt=attempt,
        command=tool_name,
        side_effect=capability_side_effect,
        status=WorkflowStepStatus.SUCCEEDED,
        requested_by=workflow_id,
        actor=WORKFLOW_EXECUTOR_ACTOR,
        idempotency_key=key,
        produced_artifact_refs=refs,
        warnings=warnings,
    )


def _failed_result(
    *,
    workflow_id: str,
    plan_id: str,
    step_id: str,
    attempt: int,
    tool_name: str,
    side_effect: CapabilitySideEffect,
    code: str,
    message: str,
    retry: RetryDisposition,
) -> WorkflowStepResult:
    issue = ResearchIssue(code=code, message=message)
    key = stable_research_id(
        "workflow_step_request",
        {
            "workflow_id": workflow_id,
            "plan_id": plan_id,
            "step_id": step_id,
            "attempt": attempt,
            "tool_name": tool_name,
        },
    )
    return WorkflowStepResult(
        result_id=stable_research_id(
            "workflow_step_result",
            {"idempotency_key": key, "issue": issue.to_dict()},
        ),
        plan_id=plan_id,
        step_id=step_id,
        attempt=attempt,
        command=tool_name,
        side_effect=side_effect,
        status=(
            WorkflowStepStatus.BLOCKED
            if retry is not RetryDisposition.NOT_APPLICABLE
            else WorkflowStepStatus.FAILED
        ),
        requested_by=workflow_id,
        actor=WORKFLOW_EXECUTOR_ACTOR,
        idempotency_key=key,
        blockers=(issue,),
        retry=retry,
    )


def _artifact_bindings(
    compiled: CompiledResearchWorkflow,
    state: Mapping[str, Any],
) -> dict[str, tuple[ArtifactReportRef, ...]]:
    bindings = {
        slot.slot_id: slot.artifact_refs
        for slot in compiled.plan.artifact_slots
        if slot.artifact_refs
    }
    steps = {item.step_id: item for item in compiled.plan.steps}
    slots = {item.slot_id: item for item in compiled.plan.artifact_slots}
    for attempt in _sequence(state.get("step_attempts")):
        row = _mapping(attempt)
        if row.get("status") != WorkflowStepStatus.SUCCEEDED.value:
            continue
        step = steps.get(str(row.get("step_id") or ""))
        if step is None:
            raise WorkflowExecutionError(
                "checkpoint attempt references an unknown workflow step"
            )
        refs = tuple(
            ArtifactReportRef.from_dict(item)
            for item in _mapping_sequence(row.get("produced_artifact_refs"))
        )
        for plan_slot_id in step.output_bindings.values():
            artifact_type = slots[plan_slot_id].artifact_type
            bindings[plan_slot_id] = tuple(
                item for item in refs if item.artifact_type == artifact_type
            )
    return bindings


def _load_pinned_payload(
    reference: ArtifactReportRef,
    artifact_store: ResearchArtifactStore,
) -> Mapping[str, Any]:
    record = artifact_store.load_artifact_record(
        reference.artifact_type,
        reference.artifact_id,
    )
    if record.domain_owner != reference.domain_owner:
        raise WorkflowExecutionError(f"artifact domain drift: {reference.uri}")
    expected_hash = str(reference.metadata.get("payload_sha256") or "")
    current_hash = json_payload_hash(record.payload)
    if expected_hash and expected_hash != current_hash:
        raise WorkflowExecutionError(f"artifact payload drift: {reference.uri}")
    return record.payload


def _pin_output_ref(
    reference: ArtifactReportRef,
    artifact_store: ResearchArtifactStore,
) -> ArtifactReportRef:
    record = artifact_store.load_artifact_record(
        reference.artifact_type,
        reference.artifact_id,
    )
    if record.domain_owner != reference.domain_owner:
        raise WorkflowExecutionError(f"tool artifact domain mismatch: {reference.uri}")
    return ArtifactReportRef(
        artifact_id=reference.artifact_id,
        artifact_type=reference.artifact_type,
        domain_owner=reference.domain_owner,
        uri=reference.uri,
        metadata={
            **dict(reference.metadata),
            "payload_sha256": json_payload_hash(record.payload),
            "producer_tool": record.producer_tool,
            "status": record.status,
        },
    )


def _artifact_refs(value: object) -> tuple[ArtifactReportRef, ...]:
    refs: list[ArtifactReportRef] = []

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            uri = item.get("uri")
            artifact_type = item.get("artifact_type")
            if isinstance(uri, str) and isinstance(artifact_type, str):
                parsed_type, artifact_id = parse_research_artifact_uri(uri)
                if parsed_type != artifact_type:
                    raise WorkflowExecutionError(
                        "MCP artifact URI type does not match artifact_type"
                    )
                refs.append(
                    ArtifactReportRef(
                        artifact_id=artifact_id,
                        artifact_type=artifact_type,
                        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
                        uri=uri,
                        metadata=_mapping(item.get("metadata")),
                    )
                )
                return
            for nested in item.values():
                visit(nested)
        elif isinstance(item, Sequence) and not isinstance(
            item,
            (str, bytes),
        ):
            for nested in item:
                visit(nested)

    visit(value)
    unique = {item.uri: item for item in refs}
    return tuple(unique[uri] for uri in sorted(unique))


def _build_outcome(
    *,
    compiled: CompiledResearchWorkflow,
    workflow_id: str,
    state: Mapping[str, Any],
) -> WorkflowOutcome:
    refs = tuple(
        {
            item.uri: item
            for attempt in _sequence(state.get("step_attempts"))
            for item in (
                ArtifactReportRef.from_dict(raw)
                for raw in _mapping_sequence(
                    _mapping(attempt).get("produced_artifact_refs")
                )
            )
        }.values()
    )
    review_types = {
        PARAMETER_OPTIMIZATION_EVALUATION_REPORT,
        PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
    }
    review_refs = tuple(item for item in refs if item.artifact_type in review_types)
    status_text = str(state.get("status") or "")
    status = WorkflowOutcomeStatus(status_text)
    warnings = tuple(
        _issue(item, default_code="workflow_warning")
        for item in _sequence(state.get("warnings"))
    )
    blockers = tuple(
        _issue(item, default_code="workflow_blocker")
        for item in _sequence(state.get("blockers"))
    )
    errors = tuple(
        _issue(item, default_code="workflow_error")
        for item in _sequence(state.get("errors"))
    )
    next_actions = {
        WorkflowOutcomeStatus.COMPLETED: (
            ("request_human_review",) if review_refs else ("request_evaluation",)
        ),
        WorkflowOutcomeStatus.BLOCKED: ("resolve_blockers",),
        WorkflowOutcomeStatus.FAILED: ("inspect_failure",),
    }[status]
    identity = {
        "workflow_id": workflow_id,
        "plan_id": compiled.plan.plan_id,
        "status": status.value,
        "artifact_uris": [item.uri for item in refs],
        "warnings": [item.to_dict() for item in warnings],
        "blockers": [item.to_dict() for item in blockers],
        "errors": [item.to_dict() for item in errors],
    }
    return WorkflowOutcome(
        outcome_id=stable_research_id("workflow_outcome", identity),
        workflow_id=workflow_id,
        plan_id=compiled.plan.plan_id,
        objective_ref=artifact_report_ref(
            RESEARCH_OBJECTIVE,
            compiled.objective.objective_id,
        ),
        protocol_ref=artifact_report_ref(
            EXPERIMENT_PROTOCOL,
            compiled.protocol.protocol_id,
        ),
        status=status,
        produced_artifact_refs=refs,
        review_verdict_refs=review_refs,
        next_permitted_actions=next_actions,
        requested_by=compiled.protocol.requested_by,
        actor="research_coordinator",
        warnings=warnings,
        blockers=blockers,
        errors=errors,
    )


def _require_successful_envelope(
    *,
    raw_result: Mapping[str, Any],
    tool_name: str,
) -> Mapping[str, Any]:
    envelope = _mapping(raw_result.get("structuredContent"))
    if (
        not envelope
        or envelope.get("command") != tool_name
        or envelope.get("ok") is not True
        or raw_result.get("isError") is True
    ):
        errors = _sequence(envelope.get("errors"))
        message = (
            str(_mapping(errors[0]).get("message"))
            if errors
            else f"{tool_name} did not return a successful envelope"
        )
        raise WorkflowExecutionError(message)
    if envelope.get("agent_owner") != agent_owner_for_tool(tool_name):
        raise WorkflowExecutionError(f"{tool_name} returned an unexpected agent owner")
    return envelope


def _is_blocking_error(issues: Sequence[ResearchIssue]) -> bool:
    return any(
        item.code.endswith(
            (
                "_not_allowed",
                "_required",
                "_unavailable",
                "_blocked",
            )
        )
        or item.code in _RETRYABLE_ERROR_CODES
        for item in issues
    )


def _issue(value: object, *, default_code: str) -> ResearchIssue:
    if isinstance(value, Mapping):
        code = str(value.get("code") or default_code)
        message = str(value.get("message") or value)
        details = _mapping(value.get("details"))
        return ResearchIssue(code=code, message=message, details=details)
    return ResearchIssue(code=default_code, message=str(value))


def _one_ref(
    bindings: Mapping[str, tuple[ArtifactReportRef, ...]],
    slot_id: str,
) -> ArtifactReportRef:
    values = bindings.get(slot_id, ())
    if len(values) != 1:
        raise WorkflowExecutionError(
            f"workflow slot {slot_id} requires exactly one canonical ref"
        )
    return values[0]


def _step_by_id(compiled: CompiledResearchWorkflow, step_id: str) -> Any:
    for step in compiled.plan.steps:
        if step.step_id == step_id:
            return step
    raise WorkflowExecutionError(f"unknown workflow step: {step_id}")


def _capability_by_id(
    compiled: CompiledResearchWorkflow,
    capability_id: str,
) -> Any:
    for capability in compiled.plan.capabilities:
        if capability.capability_id == capability_id:
            return capability
    raise WorkflowExecutionError(f"unknown workflow capability: {capability_id}")


def _required_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise WorkflowExecutionError(f"{label} is required")
    return text


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _mapping_sequence(value: object) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))
