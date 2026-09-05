"""Workflow contracts for the no-cherry-picking Agent campaign runner.

Subject: Application-owned scenario ordering, execution, evidence assessment, recovery processes, and safe diagnostics.
Level: In-process application workflow.
Collaborators: Real campaign/observation contracts with deterministic controller and worker fakes; no external service.
Guarantees: Every frozen scenario is assessed, mutation retries count once, recovery order is fixed, and failures are redacted.
Non-goals: Live model quality, actual subprocesses, PostgreSQL persistence, and release acceptance.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import anyio
import pytest

from tests.trader_agents.application_runtime.support import agentic_campaign
from tests.trader_agents.application_runtime.support.agentic_campaign import (
    AgenticCampaignRunner,
    successful_mutation_counts_from_traces,
)
from tests.trader_agents.observability.support.agentic_observation import LifecycleTrace, PublicTraceSpan
from tests.trader_agents.contracts_state.support.agentic_scenarios import (
    AgenticScenarioInput,
    build_agentic_scenario_sessions,
)
from trader_agents.contracts.domain import AgentRole
from trader_agents.model_runtime.programs import first_slice_programs
from trader_research.governance import ResearchSession


_FREEZE = "a" * 40


@dataclass
class _FixtureController:
    """Resolve every fake canonical ref and successful control mutation."""

    traces: tuple[LifecycleTrace, ...] = ()
    prepared: list[str] = field(default_factory=list)

    async def prepare(
        self,
        scenario: AgenticScenarioInput,
        sessions: Sequence[ResearchSession],
        base_environment: Mapping[str, str],
    ) -> Mapping[str, str]:
        """Retain fixture identity and return explicit trace configuration."""
        del sessions
        self.prepared.append(scenario.scenario_id)
        return {
            **base_environment,
            "TRADER_AGENTS_MLFLOW_TRACKING_URI": "sqlite:///campaign.db",
            "TRADER_AGENTS_MLFLOW_EXPERIMENT": "campaign-test",
        }

    async def resolve_evidence_refs(
        self,
        references: frozenset[str],
    ) -> frozenset[str]:
        """Treat every explicit fake Postgres URI as independently resolved."""
        return references

    async def mutation_acceptance_counts(
        self,
        traces: Sequence[LifecycleTrace],
    ) -> Mapping[str, int]:
        """Count successful immutable control mutations from result spans."""
        return successful_mutation_counts_from_traces(traces)


def test_runner_builds_and_assesses_material_ambiguity_without_delegation() -> None:
    """Execute one frozen session and produce a passing fail-closed result."""
    controller = _FixtureController()
    captured_setup: list[bool] = []

    async def execute(
        session: ResearchSession,
        environment: Mapping[str, str],
        setup_checkpoint_schema: bool,
    ) -> Mapping[str, object]:
        del environment
        captured_setup.append(setup_checkpoint_schema)
        state, trace = _ambiguity_state_and_trace(session)
        controller.traces = (trace,)
        return state

    def load_traces(
        tracking_uri: str,
        experiment: str,
        session_ids: Sequence[str],
    ) -> tuple[LifecycleTrace, ...]:
        assert tracking_uri == "sqlite:///campaign.db"
        assert experiment == "campaign-test"
        assert session_ids == [controller.traces[0].session_id]
        return controller.traces

    runner = AgenticCampaignRunner(
        freeze_revision=_FREEZE,
        base_environment={},
        fixture_controller=controller,
        session_executor=execute,
        trace_loader=load_traces,
    )

    result = anyio.run(runner.run_repetition, "material_ambiguity", 1)

    assert result.status == "passed"
    assert result.terminal_actions == ("ask_operator",)
    assert result.delegated_roles == ()
    assert result.required_role_coverage == 1.0
    assert "build_contract_validation" in result.evidence_types
    assert result.forbidden_tool_calls == 0
    assert captured_setup == [True]
    assert controller.prepared == ["material_ambiguity"]


def test_mutation_counts_use_runtime_operation_identity_across_lost_response() -> None:
    """Collapse an interrupted attempt and successful retry into one acceptance."""
    session_id = "session-replayed-operation"
    program_id = first_slice_programs().for_role(AgentRole.DATA_RESEARCH).program_id
    operation_id = "operation-stable-across-processes"
    attributes = {
        "trader.tool_name": "data_ensure_loaded",
        "trader.side_effect": "local_mutating",
        "trader.argument.operation_id": operation_id,
    }
    trace = LifecycleTrace(
        trace_id="tr-" + "b" * 32,
        session_id=session_id,
        operation="start",
        spans=(
            _span(
                "agent.session.start",
                session_id,
                program_id,
                **{"trader.lifecycle_operation": "start"},
            ),
            _span(
                "agent.mcp.data_ensure_loaded",
                session_id,
                program_id,
                **{**attributes, "trader.call_id": "model-call-first"},
            ),
            _span(
                "agent.mcp_result.data_ensure_loaded",
                session_id,
                program_id,
                **{
                    **attributes,
                    "trader.call_id": "model-call-first",
                    "trader.result_ok": False,
                },
            ),
            _span(
                "agent.mcp.data_ensure_loaded",
                session_id,
                program_id,
                **{**attributes, "trader.call_id": "model-call-retry"},
            ),
            _span(
                "agent.mcp_result.data_ensure_loaded",
                session_id,
                program_id,
                **{
                    **attributes,
                    "trader.call_id": "model-call-retry",
                    "trader.result_ok": True,
                },
            ),
        ),
    )

    assert successful_mutation_counts_from_traces((trace,)) == {operation_id: 1}


def test_recovery_executor_uses_three_faulted_processes_then_clean_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require the reviewed fault order and reserve schema setup for process one."""
    session = build_agentic_scenario_sessions(
        "crash_and_lost_response",
        repetition=1,
        freeze_revision=_FREEZE,
    )[0]
    calls: list[tuple[str, bool]] = []

    async def _worker(
        worker_session: ResearchSession,
        environment: Mapping[str, str],
        *,
        fault_mode: str,
        setup_checkpoint_schema: bool,
        timeout_seconds: int,
    ) -> agentic_campaign._WorkerOutcome:
        del environment, timeout_seconds
        assert worker_session == session
        calls.append((fault_mode, setup_checkpoint_schema))
        if fault_mode == "none":
            return agentic_campaign._WorkerOutcome(
                returncode=0,
                stdout=(
                    agentic_campaign.STATE_RESULT_PREFIX
                    + f'{{"session_id":"{session.session_id}"}}'
                ),
                stderr="",
            )
        return agentic_campaign._WorkerOutcome(
            returncode=agentic_campaign.FAULT_EXIT_CODE,
            stdout=(
                agentic_campaign.FAULT_RESULT_PREFIX + f'{{"mode":"{fault_mode}"}}'
            ),
            stderr="",
        )

    monkeypatch.setattr(agentic_campaign, "_run_session_worker", _worker)

    async def _run_recovery() -> Mapping[str, object]:
        return await agentic_campaign._execute_recovery_session(
            session,
            {},
            setup_checkpoint_schema=True,
        )

    state = anyio.run(_run_recovery)

    assert state["session_id"] == session.session_id
    assert calls == [
        ("before_data_mutation", True),
        ("after_data_mutation", False),
        ("before_return_reconciliation", False),
        ("none", False),
    ]


def test_worker_failure_diagnostic_never_reproduces_process_output() -> None:
    """Hash potentially secret subprocess output in raised diagnostics."""
    outcome = agentic_campaign._WorkerOutcome(
        returncode=9,
        stdout="public marker with api-key-value",
        stderr="postgresql://operator:password@localhost/trader",
    )

    diagnostic = agentic_campaign._worker_failure("qualification", outcome)

    assert "api-key-value" not in diagnostic
    assert "password" not in diagnostic
    assert "sha256:" in diagnostic
    assert "exit=9" in diagnostic


def _ambiguity_state_and_trace(
    session: ResearchSession,
) -> tuple[dict[str, Any], LifecycleTrace]:
    """Return one coherent interrupted public state and lifecycle trace."""
    programs = first_slice_programs()
    coordinator = programs.for_role(AgentRole.RESEARCH_COORDINATOR).program_id
    session_ref = f"research://postgres/research_session/{session.session_id}"
    decision_ref = "research://postgres/agent_decision_receipt/ambiguity-decision"
    state = {
        "session_id": session.session_id,
        "agenda": {
            "objective_summary": "The stale-price failure behavior is missing.",
            "material_ambiguities": ["The stale-price failure behavior is missing."],
            "tasks": [],
        },
        "branch_by_task": {},
        "delegations": [],
        "specialist_returns": [],
        "evidence_refs": [{"uri": session_ref}, {"uri": decision_ref}],
        "decision": {
            "action": "ask_operator",
            "summary": "The missing failure behavior requires operator authority.",
            "operator_question": "Define the missing stale-price failure behavior.",
            "cited_evidence_refs": [],
            "blockers": [],
        },
        "decision_receipt_ref": {"uri": decision_ref},
        "budget_usage": {
            "model_calls": 2,
            "tool_calls": 2,
            "input_tokens": 200,
            "output_tokens": 100,
            "duration_ms": 100,
            "mutations": 2,
            "revisions": 0,
        },
    }
    spans = (
        _span(
            "agent.session.start",
            session.session_id,
            coordinator,
            **{
                "trader.lifecycle_operation": "start",
                "trader.process_instance_id": "a" * 32,
            },
        ),
        _span(
            "agent.model.research_coordinator",
            session.session_id,
            coordinator,
            **_model_identity("coordinator-agenda"),
        ),
        _model_result(
            "coordinator-agenda",
            session.session_id,
            coordinator,
        ),
        _model_validation(
            "coordinator-agenda",
            session.session_id,
            coordinator,
        ),
        _span(
            "agent.model.research_coordinator",
            session.session_id,
            coordinator,
            **_model_identity("coordinator-decision"),
        ),
        _model_result(
            "coordinator-decision",
            session.session_id,
            coordinator,
        ),
        _model_validation(
            "coordinator-decision",
            session.session_id,
            coordinator,
        ),
        _tool(
            "research_create_agent_session",
            "create-session",
            session.session_id,
            coordinator,
        ),
        _result(
            "research_create_agent_session",
            "create-session",
            session.session_id,
            coordinator,
            [session_ref],
        ),
        _tool(
            "research_record_agent_decision",
            "record-decision",
            session.session_id,
            coordinator,
        ),
        _result(
            "research_record_agent_decision",
            "record-decision",
            session.session_id,
            coordinator,
            [decision_ref],
        ),
    )
    return state, LifecycleTrace(
        trace_id="tr-" + "a" * 32,
        session_id=session.session_id,
        operation="start",
        spans=spans,
    )


def _span(
    name: str,
    session_id: str,
    program_id: str,
    **attributes: Any,
) -> PublicTraceSpan:
    """Build one bounded fake public span."""
    return PublicTraceSpan(
        name=name,
        attributes={
            "trader.session_id": session_id,
            "trader.branch_id": "root",
            "trader.program_id": program_id,
            **attributes,
        },
        start_time_ns=10,
        end_time_ns=20,
    )


def _tool(
    tool_name: str,
    call_id: str,
    session_id: str,
    program_id: str,
) -> PublicTraceSpan:
    """Build one local-mutating control dispatch."""
    return _span(
        f"agent.mcp.{tool_name}",
        session_id,
        program_id,
        **{
            "trader.tool_name": tool_name,
            "trader.call_id": call_id,
            "trader.side_effect": "local_mutating",
        },
    )


def _model_result(
    model_call_id: str,
    session_id: str,
    program_id: str,
) -> PublicTraceSpan:
    """Build terminal public accounting for one fake provider call."""
    return _span(
        "agent.model_result.research_coordinator",
        session_id,
        program_id,
        **{
            **_model_identity(model_call_id),
            "trader.model_provider": "static",
            "trader.model_name": "static-json",
            "trader.input_tokens": 100,
            "trader.output_tokens": 50,
            "trader.duration_ms": 10,
            "trader.result_ok": True,
        },
    )


def _model_validation(
    model_call_id: str,
    session_id: str,
    program_id: str,
) -> PublicTraceSpan:
    """Build one successful strict-schema verdict for fake model output."""
    return _span(
        "agent.model_validation.research_coordinator",
        session_id,
        program_id,
        **{
            **_model_identity(model_call_id),
            "trader.schema_valid": True,
            "trader.validation_error_count": 0,
        },
    )


def _model_identity(model_call_id: str) -> dict[str, str | int]:
    """Return matching fake invocation, call, contract, and repair identity."""
    return {
        "trader.model_invocation_id": f"invocation-{model_call_id}",
        "trader.model_call_id": model_call_id,
        "trader.output_contract": "CoordinatorDecision",
        "trader.schema_repair": 0,
    }


def _result(
    tool_name: str,
    call_id: str,
    session_id: str,
    program_id: str,
    refs: list[str],
) -> PublicTraceSpan:
    """Build one successful canonical control result."""
    return _span(
        f"agent.mcp_result.{tool_name}",
        session_id,
        program_id,
        **{
            "trader.tool_name": tool_name,
            "trader.call_id": call_id,
            "trader.result_ok": True,
            "trader.evidence_refs": refs,
            "trader.evidence_types": [
                ref.removeprefix("research://postgres/").split("/", 1)[0]
                for ref in refs
            ],
        },
    )
