"""Model-runtime tests for strict structured invocation and accounting.

Subject: Schema-bound provider invocation, one bounded structural repair, redacted spans, and interrupted-call accounting.
Level: In-process adapter contract.
Collaborators: Real structured runner with static or interrupting fake model clients and recording sinks.
Guarantees: Every physical model call is charged and observed without persisting raw model content.
Non-goals: Semantic decision repair, live provider behavior, tool execution, and graph orchestration."""

from __future__ import annotations
import asyncio
from typing import Any
import anyio
import pytest
from trader_agents import (
    AgentRole,
    AgentEventEmitter,
    AgentEventName,
    BudgetLedger,
    DataAgentTurn,
    LlmTokenUsage,
    RecordingObservabilityEventSink,
    RecordingTraceSink,
    StaticJsonLlmClient,
    StructuredModelRunner,
    development_model_profiles,
    first_slice_programs,
)
from tests.trader_agents.support.runtime_contracts import _budget, _correlation
from tests.trader_agents.support.runtime_faults import _InterruptingJsonLlmClient


def test_structured_model_repairs_once_and_records_redacted_spans() -> None:
    """Malformed public JSON receives one bounded schema-only repair."""
    valid = {
        "action": "change_phase",
        "public_rationale": "Inventory evidence shows an approved loading gap.",
        "next_phase": "remediate",
    }
    client = StaticJsonLlmClient(
        responses=({}, valid),
        usages=(LlmTokenUsage(10, 4), LlmTokenUsage(12, 6)),
    )
    traces = RecordingTraceSink()
    event_sink = RecordingObservabilityEventSink()
    event_emitter = AgentEventEmitter(
        sink=event_sink,
        process_instance_id="model-repair-process",
    )
    runner = StructuredModelRunner(
        client=client,
        trace_sink=traces,
        event_emitter=event_emitter,
    )
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    profile = development_model_profiles().get(program.model_profile_id)
    ledger = BudgetLedger(_budget())

    async def _run() -> Any:
        return await runner.invoke(
            program=program,
            profile=profile,
            output_type=DataAgentTurn,
            instruction="Choose the next evidence-producing action.",
            public_context={"observations": []},
            ledger=ledger,
            correlation=_correlation(program.program_id),
        )

    result = anyio.run(_run)
    assert result.output.action == "change_phase"
    assert result.schema_repairs == 1
    assert ledger.usage.model_calls == 2
    assert len(client.requests) == 2
    assert {span["status"] for span in traces.spans} == {"completed"}
    result_spans = [
        span
        for span in traces.spans
        if span["name"] == "agent.model_result.data_research"
    ]
    assert len(result_spans) == 2
    assert (
        sum(int(span["attributes"]["trader.input_tokens"]) for span in result_spans)
        == 22
    )
    assert (
        sum(int(span["attributes"]["trader.output_tokens"]) for span in result_spans)
        == 10
    )
    assert all(span["attributes"]["trader.result_ok"] for span in result_spans)
    validation_spans = [
        span
        for span in traces.spans
        if span["name"] == "agent.model_validation.data_research"
    ]
    assert [span["attributes"]["trader.schema_valid"] for span in validation_spans] == [
        False,
        True,
    ]
    assert [
        span["attributes"]["trader.schema_repair"] for span in validation_spans
    ] == [0, 1]
    assert (
        len(
            {
                span["attributes"]["trader.model_invocation_id"]
                for span in validation_spans
            }
        )
        == 1
    )
    assert all("prompt" not in str(span["attributes"]) for span in traces.spans)
    event_names = [event.name for event in event_sink.events]
    assert event_names.count(AgentEventName.MODEL_CALL_STARTED) == 2
    assert event_names.count(AgentEventName.MODEL_CALL_COMPLETED) == 2
    assert event_names.count(AgentEventName.MODEL_SCHEMA_REJECTED) == 1
    assert event_names.count(AgentEventName.MODEL_SCHEMA_ACCEPTED) == 1
    rejected = next(
        event
        for event in event_sink.events
        if event.name is AgentEventName.MODEL_SCHEMA_REJECTED
    )
    assert rejected.error is not None
    assert rejected.error.code == "model_schema_invalid"
    assert rejected.error.retryable is True


def test_interrupted_model_call_records_terminal_public_accounting() -> None:
    """Account for a physical provider attempt that yields no model payload."""
    traces = RecordingTraceSink()
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    profile = development_model_profiles().get(program.model_profile_id)
    ledger = BudgetLedger(_budget())
    runner = StructuredModelRunner(
        client=_InterruptingJsonLlmClient(()),
        trace_sink=traces,
    )

    async def _run() -> None:
        await runner.invoke(
            program=program,
            profile=profile,
            output_type=DataAgentTurn,
            instruction="Choose the next evidence-producing action.",
            public_context={"observations": []},
            ledger=ledger,
            correlation=_correlation(program.program_id),
        )

    with pytest.raises(asyncio.CancelledError):
        anyio.run(_run)

    assert ledger.usage.model_calls == 1
    assert traces.spans[0]["status"] == "error"
    assert traces.spans[1]["name"] == "agent.model_result.data_research"
    assert traces.spans[1]["attributes"]["trader.result_ok"] is False
    assert traces.spans[1]["attributes"]["trader.input_tokens"] == 0
    assert traces.spans[1]["attributes"]["trader.output_tokens"] == 0
