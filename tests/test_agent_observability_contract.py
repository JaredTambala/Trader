"""Contract tests for sink-neutral agent observability events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

from pydantic import ValidationError
import pytest

from trader_agents import (
    OBSERVABILITY_SCHEMA_VERSION,
    AgentErrorCategory,
    AgentEventAuthority,
    AgentEventCorrelation,
    AgentEventError,
    AgentEventLevel,
    AgentEventName,
    AgentObservabilityEvent,
    AgenticSliceResult,
    AgendaTaskProposal,
    BudgetUsage,
    CanonicalEvidenceRef,
    CoordinatorAction,
    CoordinatorAgenda,
    CoordinatorDecision,
    DataAgentTurn,
    NoOpObservabilityEventSink,
    ProjectionDetail,
    RecordingObservabilityEventSink,
    SpecialistReturn,
    SpecialistStatus,
    ToolCallProposal,
    ToolObservation,
    build_agent_observability_event,
    project_agent_turn,
    project_budget_usage,
    project_checkpoint,
    project_coordinator_agenda,
    project_coordinator_decision,
    project_policy_result,
    project_specialist_return,
    project_terminal_result,
    project_tool_call_proposal,
    project_tool_observation,
    validate_agent_event_stream,
    validate_observability_fields,
)
from trader_agents.tracing import NoOpTraceSink


EVENT_TIME = datetime(2026, 9, 3, 12, tzinfo=UTC)


def test_event_contract_fixes_visibility_authority_and_json_encoding() -> None:
    """Semantic names determine sink-neutral visibility and authority."""
    correlation = _correlation(transition_sequence=7)
    event = build_agent_observability_event(
        name=AgentEventName.DECISION_COMMITTED,
        timestamp=EVENT_TIME,
        sequence=4,
        correlation=correlation,
        fields={"summary": "Conclude from accepted evidence", "count": 2},
    )

    assert event.schema_version == OBSERVABILITY_SCHEMA_VERSION
    assert event.level is AgentEventLevel.INFO
    assert event.authority is AgentEventAuthority.CANONICAL_RECORD
    assert event.timestamp == EVENT_TIME
    assert event.to_json() == event.to_json()
    assert event.to_json() == json.dumps(
        event.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
    )

    with pytest.raises(ValidationError, match="requires level info"):
        AgentObservabilityEvent(
            name=AgentEventName.DECISION_COMMITTED,
            level=AgentEventLevel.DEBUG,
            authority=AgentEventAuthority.CANONICAL_RECORD,
            timestamp=EVENT_TIME,
            sequence=4,
            correlation=correlation,
        )


@pytest.mark.parametrize(
    "event_name",
    [
        AgentEventName.MODEL_RESPONSE_RECEIVED,
        AgentEventName.MODEL_SCHEMA_ACCEPTED,
        AgentEventName.ACTION_DOMAIN_ACCEPTED,
        AgentEventName.TOOL_POLICY_AUTHORIZED,
        AgentEventName.TOOL_EXECUTION_STARTED,
        AgentEventName.TOOL_EXECUTION_COMPLETED,
    ],
)
def test_trust_stage_events_require_exact_call_identity(
    event_name: AgentEventName,
) -> None:
    """Receipt, validation, admission, policy, and execution stay distinct."""
    with pytest.raises(ValidationError, match="requires call_id correlation"):
        build_agent_observability_event(
            name=event_name,
            timestamp=EVENT_TIME,
            sequence=1,
            correlation=_correlation(),
        )

    event = build_agent_observability_event(
        name=event_name,
        timestamp=EVENT_TIME,
        sequence=1,
        correlation=_correlation(call_id="call-1"),
    )
    assert event.name is event_name


def test_failure_events_require_classified_public_errors() -> None:
    """Provider failure cannot be emitted as an unclassified completion."""
    with pytest.raises(ValidationError, match="requires a public error"):
        build_agent_observability_event(
            name=AgentEventName.MODEL_CALL_FAILED,
            timestamp=EVENT_TIME,
            sequence=1,
            correlation=_correlation(call_id="model-call-1"),
        )

    event = build_agent_observability_event(
        name=AgentEventName.MODEL_CALL_FAILED,
        timestamp=EVENT_TIME,
        sequence=1,
        correlation=_correlation(call_id="model-call-1"),
        error=AgentEventError(
            code="provider_unavailable",
            category=AgentErrorCategory.MODEL_PROVIDER,
            message="The configured model provider is unavailable.",
            retryable=True,
        ),
    )
    assert event.level is AgentEventLevel.ERROR


def test_delegation_events_require_delegation_and_attempt_identity() -> None:
    """Specialist concurrency identity is complete or absent as one unit."""
    with pytest.raises(ValidationError, match="both be present or absent"):
        _correlation(delegation_id="delegation-1")
    with pytest.raises(ValidationError, match="requires delegation and attempt"):
        build_agent_observability_event(
            name=AgentEventName.DELEGATION_STARTED,
            timestamp=EVENT_TIME,
            sequence=1,
            correlation=_correlation(),
        )

    event = build_agent_observability_event(
        name=AgentEventName.DELEGATION_STARTED,
        timestamp=EVENT_TIME,
        sequence=1,
        correlation=_correlation(
            branch_id="branch-data",
            delegation_id="delegation-1",
            attempt_id="attempt-1",
        ),
    )
    assert event.correlation.attempt_id == "attempt-1"


@pytest.mark.parametrize(
    "unsafe_fields",
    [
        {"prompt": "raw prompt"},
        {"trader.source_code": "print('unsafe')"},
        {"nested": {"retrieved_chunks": ["raw source"]}},
        {"provider_credentials": "secret"},
        {"tool": {"raw_payload": {"symbol": "BTC/USD"}}},
    ],
)
def test_field_validation_rejects_unsafe_keys_recursively(
    unsafe_fields: dict[str, object],
) -> None:
    """Dotted, nested, singular, and plural unsafe field names fail closed."""
    with pytest.raises(ValueError, match="not allowed"):
        validate_observability_fields(unsafe_fields)


def test_field_validation_rejects_non_json_and_oversized_values() -> None:
    """All sink inputs are JSON-native and bounded before rendering."""
    with pytest.raises(ValueError, match="JSON-native"):
        validate_observability_fields({"values": {"one", "two"}})
    with pytest.raises(ValueError, match="JSON-native"):
        validate_observability_fields({"values": ("one", "two")})
    with pytest.raises(ValueError, match="4000 characters"):
        validate_observability_fields({"summary": "x" * 4_001})
    with pytest.raises(ValueError, match="64 items"):
        validate_observability_fields({"items": list(range(65))})
    with pytest.raises(ValueError, match="12000 bytes"):
        validate_observability_fields(
            {f"field_{index}": "x" * 200 for index in range(60)}
        )


def test_sinks_revalidate_events_after_caller_mutation() -> None:
    """Selecting a no-op or recording sink cannot bypass redaction."""
    event = build_agent_observability_event(
        name=AgentEventName.SESSION_STARTED,
        timestamp=EVENT_TIME,
        sequence=1,
        correlation=_correlation(),
        fields={"operation": "start"},
    )
    event.fields["raw_prompt"] = "must never reach a sink"

    for sink in (NoOpObservabilityEventSink(), RecordingObservabilityEventSink()):
        with pytest.raises(ValidationError, match="not allowed"):
            sink.emit(event)


def test_recording_sink_preserves_process_local_order_and_concurrency() -> None:
    """Parallel processes may share sequence values without losing identity."""
    sink = RecordingObservabilityEventSink()
    process_a = _correlation(process_instance_id="process-a")
    process_b = _correlation(process_instance_id="process-b")
    events = [
        build_agent_observability_event(
            name=AgentEventName.SESSION_STARTED,
            timestamp=EVENT_TIME,
            sequence=1,
            correlation=process_a,
        ),
        build_agent_observability_event(
            name=AgentEventName.SESSION_STARTED,
            timestamp=EVENT_TIME,
            sequence=1,
            correlation=process_b,
        ),
        build_agent_observability_event(
            name=AgentEventName.SESSION_INSPECTED,
            timestamp=EVENT_TIME + timedelta(seconds=1),
            sequence=2,
            correlation=process_a,
        ),
    ]
    for event in events:
        sink.emit(event)

    assert [event.stream_position for event in sink.events] == [
        ("process-a", 1),
        ("process-b", 1),
        ("process-a", 2),
    ]
    assert validate_agent_event_stream(sink.events) == tuple(sink.events)

    duplicate = events[2].model_copy(update={"sequence": 1})
    with pytest.raises(ValueError, match="increase within a process"):
        sink.emit(duplicate)


def test_schema_specific_projections_exclude_arbitrary_tool_payloads() -> None:
    """Public agent state is projected by schema rather than generic dumping."""
    proposal = _tool_proposal()
    observation = _tool_observation()
    agenda = _agenda()
    specialist_return = _specialist_return()
    decision = _decision()
    terminal_result = AgenticSliceResult(
        session_id="session-1",
        branch_id="branch-1",
        status="completed",
        summary="The bounded data question is resolved.",
        data_return=specialist_return,
        decision=decision,
        budget_used=specialist_return.budget_used,
        permitted_next_actions=["Design the bounded experiment."],
    )

    projections = {
        "agenda": project_coordinator_agenda(
            agenda,
            detail=ProjectionDetail.DEBUG,
        ),
        "turn": project_agent_turn(
            DataAgentTurn(
                action="call_tool",
                public_rationale="Inspect the bounded inventory first.",
                tool_call=proposal,
            ),
            detail=ProjectionDetail.DEBUG,
        ),
        "proposal": project_tool_call_proposal(
            proposal,
            detail=ProjectionDetail.DEBUG,
        ),
        "observation": project_tool_observation(
            observation,
            detail=ProjectionDetail.DEBUG,
        ),
        "policy": project_policy_result(
            proposal,
            authorized=True,
            side_effect="read_only",
            fingerprint="f" * 64,
            detail=ProjectionDetail.DEBUG,
        ),
        "return": project_specialist_return(
            specialist_return,
            detail=ProjectionDetail.DEBUG,
        ),
        "decision": project_coordinator_decision(
            decision,
            detail=ProjectionDetail.DEBUG,
        ),
        "terminal": project_terminal_result(
            terminal_result,
            detail=ProjectionDetail.DEBUG,
        ),
        "budget": project_budget_usage(specialist_return.budget_used),
        "checkpoint": project_checkpoint(
            checkpoint_digest="a" * 64,
            transition_sequence=3,
            status="running",
            phase="investigate",
        ),
    }
    encoded = json.dumps(projections, sort_keys=True)

    assert "do-not-log-key" not in encoded
    assert "do-not-log-source" not in encoded
    assert "BTC/USD" not in encoded
    assert projections["proposal"]["argument_count"] == 3
    assert projections["observation"]["summary_values"] == {"row_count": 21}
    assert projections["checkpoint"]["checkpoint_digest"] == "a" * 64


def test_policy_denial_projection_requires_stable_public_error() -> None:
    """A denied proposal cannot be represented without an actionable code."""
    proposal = _tool_proposal()
    with pytest.raises(ValueError, match="require a code and message"):
        project_policy_result(proposal, authorized=False)

    projection = project_policy_result(
        proposal,
        authorized=False,
        denial_code="tool_not_allowed",
        denial_message="This role may not call that tool.",
    )
    error = AgentEventError(
        code="tool_not_allowed",
        category=AgentErrorCategory.POLICY,
        message="This role may not call that tool.",
    )
    event = build_agent_observability_event(
        name=AgentEventName.TOOL_POLICY_DENIED,
        timestamp=EVENT_TIME,
        sequence=1,
        correlation=_correlation(call_id=proposal.call_id),
        fields=projection,
        error=error,
    )

    assert event.level is AgentEventLevel.WARNING
    assert event.error == error


def test_legacy_trace_sink_uses_the_same_recursive_redaction_boundary() -> None:
    """An existing MLflow span cannot admit fields rejected by events."""
    with pytest.raises(ValueError, match="not allowed"):
        with NoOpTraceSink().span(
            "agent.invalid",
            span_type="CHAIN",
            attributes={"trader.source_code": "do not persist"},
        ):
            pass


def _correlation(**updates: object) -> AgentEventCorrelation:
    values = {
        "session_id": "session-1",
        "branch_id": "branch-1",
        "role": "research_coordinator",
        "program_id": "research-coordinator-v1",
        "model_profile_id": "ollama-lfm25-8b-json-v1",
        "tool_catalog_id": "first-agentic-slice-v1",
        "process_instance_id": "process-1",
    }
    values.update(updates)
    return AgentEventCorrelation.model_validate(values)


def _evidence() -> CanonicalEvidenceRef:
    return CanonicalEvidenceRef(
        artifact_type="dataset_manifest",
        artifact_id="manifest-1",
        domain_owner="data_research",
        uri="research://postgres/dataset_manifest/manifest-1",
    )


def _tool_proposal() -> ToolCallProposal:
    return ToolCallProposal(
        call_id="call-1",
        tool_name="data_get_inventory",
        arguments={
            "symbols": ["BTC/USD"],
            "api_key": "do-not-log-key",
            "raw_payload": {"source": "do-not-log-source"},
        },
        purpose="Inspect available data coverage.",
        expected_evidence=["dataset inventory"],
    )


def _tool_observation() -> ToolObservation:
    return ToolObservation(
        call_id="call-1",
        tool_name="data_get_inventory",
        ok=True,
        command="data_get_inventory",
        agent_owner="data_research",
        side_effect="read_only",
        summary={
            "row_count": 21,
            "source_code": "do-not-log-source",
            "symbol": "BTC/USD",
        },
        evidence_refs=[_evidence()],
    )


def _agenda() -> CoordinatorAgenda:
    return CoordinatorAgenda(
        objective_summary="Establish data readiness for a bounded study.",
        tasks=[
            AgendaTaskProposal(
                task_id="task-data",
                role="data_research",
                work_kind="investigate",
                question="Is the requested data scope complete?",
                required_evidence=["dataset manifest"],
                expected_information_gain="Resolve data coverage uncertainty.",
            )
        ],
    )


def _specialist_return() -> SpecialistReturn:
    return SpecialistReturn(
        delegation_id="delegation-1",
        session_id="session-1",
        branch_id="branch-data",
        attempt_id="attempt-1",
        role="data_research",
        program_id="data-research-v1",
        model_profile_id="ollama-lfm25-8b-json-v1",
        tool_catalog_id="first-agentic-slice-v1",
        status=SpecialistStatus.READY,
        answered_questions=["The requested inventory is available."],
        findings=["Twenty-one bounded inventory rows were found."],
        evidence_refs=[_evidence()],
        budget_used=BudgetUsage(model_calls=1, tool_calls=1, input_tokens=20),
    )


def _decision() -> CoordinatorDecision:
    return CoordinatorDecision(
        action=CoordinatorAction.CONCLUDE,
        summary="The accepted evidence resolves the data question.",
        reviewed_delegation_ids=["delegation-1"],
        cited_evidence_refs=[_evidence()],
        criteria_applied=["Requested data scope is complete."],
        affected_task_ids=["task-data"],
        permitted_next_actions=["Design the bounded experiment."],
    )
