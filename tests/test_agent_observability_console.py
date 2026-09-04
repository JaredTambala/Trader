"""Tests for configurable stderr delivery of public agent events."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
import json

import pytest

from trader_agents import (
    AgentConsoleConfig,
    AgentErrorCategory,
    AgentEventCorrelation,
    AgentEventError,
    AgentEventEmitter,
    AgentEventLevel,
    AgentEventName,
    CompositeObservabilityEventSink,
    ConsoleLogFormat,
    ConsoleObservabilityEventSink,
    RecordingObservabilityEventSink,
    TraceCorrelation,
    agent_console_config,
    build_agent_observability_event,
)


EVENT_TIME = datetime(2026, 9, 4, 9, 30, tzinfo=UTC)


def test_console_config_defaults_and_cli_overrides_environment() -> None:
    """INFO human output is default and explicit CLI values take precedence."""
    assert agent_console_config({}) == AgentConsoleConfig()
    assert agent_console_config(
        {
            "TRADER_AGENTS_LOG_LEVEL": "INFO",
            "TRADER_AGENTS_LOG_FORMAT": "human",
        },
        level_override="debug",
        format_override="JSON",
    ) == AgentConsoleConfig(
        level=AgentEventLevel.DEBUG,
        format=ConsoleLogFormat.JSON,
    )


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"TRADER_AGENTS_LOG_LEVEL": "WARNING"}, "DEBUG or INFO"),
        ({"TRADER_AGENTS_LOG_FORMAT": "yaml"}, "human or json"),
    ],
)
def test_console_config_rejects_unsupported_values(
    environment: dict[str, str],
    message: str,
) -> None:
    """Invalid console settings fail before runtime resources are opened."""
    with pytest.raises(ValueError, match=message):
        agent_console_config(environment)


def test_info_human_sink_filters_debug_and_labels_concurrency() -> None:
    """The default narrative is one line with role and process correlation."""
    stream = StringIO()
    sink = ConsoleObservabilityEventSink(stream=stream)
    sink.emit(_event(AgentEventName.SESSION_INSPECTED, sequence=1))
    sink.emit(
        _event(
            AgentEventName.SESSION_STARTED,
            sequence=2,
            fields={"operation": "start"},
        )
    )

    output = stream.getvalue()
    assert "agent.session.inspected" not in output
    assert output.count("\n") == 1
    assert "INFO agent.session.started" in output
    assert "session=session-1" in output
    assert "branch=branch-1" in output
    assert "role=research_coordinator" in output
    assert "process=process-1" in output
    assert 'operation="start"' in output


def test_debug_json_sink_writes_one_parseable_event_per_line() -> None:
    """DEBUG JSON output preserves the exact validated event representation."""
    stream = StringIO()
    sink = ConsoleObservabilityEventSink(
        config=AgentConsoleConfig(
            level=AgentEventLevel.DEBUG,
            format=ConsoleLogFormat.JSON,
        ),
        stream=stream,
    )
    event = _event(AgentEventName.SESSION_INSPECTED, sequence=1)
    sink.emit(event)

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == event.to_dict()


def test_info_threshold_keeps_warning_and_error_events_visible() -> None:
    """INFO filtering never suppresses explicit rejection or failure events."""
    stream = StringIO()
    sink = ConsoleObservabilityEventSink(stream=stream)
    error = AgentEventError(
        code="public_failure",
        category=AgentErrorCategory.DOMAIN_VALIDATION,
        message="A public boundary rejected the transition.",
    )

    sink.emit(
        _event(
            AgentEventName.MODEL_SCHEMA_REJECTED,
            sequence=1,
            call_id="model-call-1",
            error=error,
        )
    )
    sink.emit(
        _event(
            AgentEventName.SESSION_FAILED,
            sequence=2,
            error=error,
        )
    )

    output = stream.getvalue()
    assert "WARNING agent.model.schema_rejected" in output
    assert "ERROR agent.session.failed" in output


def test_process_emitter_allocates_sequence_and_fans_out() -> None:
    """One emitter gives console and recording sinks the same ordered events."""
    stream = StringIO()
    recording = RecordingObservabilityEventSink()
    emitter = AgentEventEmitter(
        sink=CompositeObservabilityEventSink(
            (
                ConsoleObservabilityEventSink(stream=stream),
                recording,
            )
        ),
        process_instance_id="process-shared",
        clock=lambda: EVENT_TIME,
    )
    correlation = TraceCorrelation(
        session_id="session-1",
        branch_id="branch-data",
        program_id="data-research-v1",
        model_profile_id="model-v1",
        tool_catalog_id="catalogue-v1",
        delegation_id="delegation-1",
        attempt_id="attempt-1",
    )

    first = emitter.emit(
        name=AgentEventName.DELEGATION_STARTED,
        correlation=correlation,
        role="data_research",
        fields={"task_id": "task-data"},
    )
    second = emitter.emit(
        name=AgentEventName.SPECIALIST_RETURNED,
        correlation=correlation,
        role="data_research",
        fields={"status": "ready"},
    )

    assert (first.sequence, second.sequence) == (1, 2)
    assert [event.to_dict() for event in recording.events] == [
        first.to_dict(),
        second.to_dict(),
    ]
    assert stream.getvalue().count("\n") == 2


def _event(
    name: AgentEventName,
    *,
    sequence: int,
    fields: dict[str, object] | None = None,
    call_id: str | None = None,
    error: AgentEventError | None = None,
):
    return build_agent_observability_event(
        name=name,
        timestamp=EVENT_TIME,
        sequence=sequence,
        correlation=AgentEventCorrelation(
            session_id="session-1",
            branch_id="branch-1",
            role="research_coordinator",
            program_id="research-coordinator-v1",
            model_profile_id="model-v1",
            tool_catalog_id="catalogue-v1",
            process_instance_id="process-1",
            call_id=call_id,
        ),
        fields=fields,
        error=error,
    )
