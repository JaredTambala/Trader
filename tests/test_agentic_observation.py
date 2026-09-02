"""Tests for deterministic public agentic trajectory observation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.support.agentic_assessment import assess_agentic_scenario
from tests.support.agentic_observation import (
    LifecycleTrace,
    PublicTraceSpan,
    ScenarioTrajectoryEvidence,
    assert_mlflow_sessions_absent,
    build_agentic_scenario_result,
    deterministic_invariant_verdicts,
    load_mlflow_lifecycle_traces,
    trajectory_evidence_refs,
)
from tests.support.agentic_scenarios import build_agentic_scenario_sessions
from trader_agents.programs import first_slice_programs
from trader_agents.contracts import AgentRole
from trader_agents.tracing import MlflowTraceSink


_FREEZE = "a" * 40


def test_public_trajectory_proves_all_code_owned_invariants() -> None:
    """Derive safety verdicts from state, trace, resolution, and journals."""
    session = build_agentic_scenario_sessions(
        "exact_reuse",
        repetition=1,
        freeze_revision=_FREEZE,
    )[0]
    state, trace, resolved, mutations = _passing_evidence(session)
    evidence = ScenarioTrajectoryEvidence(
        scenario_id="exact_reuse",
        repetition=1,
        sessions=(session,),
        public_states=(state,),
        traces=(trace,),
        resolved_evidence_refs=frozenset(resolved),
        mutation_acceptance_counts=mutations,
    )

    verdicts = deterministic_invariant_verdicts(evidence)

    assert all(verdicts.values())
    assert trajectory_evidence_refs(evidence) == frozenset(resolved)

    assessment = assess_agentic_scenario(evidence)
    assert all(assessment.trajectory_assertions.values())
    assert assessment.grounded_decision is True
    result = build_agentic_scenario_result(evidence, assessment)
    assert result.status == "passed"
    assert result.terminal_actions == ("conclude",)
    assert result.required_role_coverage == 1.0
    assert result.model_calls == 2
    assert result.tool_calls == 5


def test_invariants_fail_for_unresolved_ref_replay_and_scope_drift() -> None:
    """Do not let plausible final state hide missing evidence or unsafe lineage."""
    session = build_agentic_scenario_sessions(
        "exact_reuse",
        repetition=1,
        freeze_revision=_FREEZE,
    )[0]
    state, trace, resolved, mutations = _passing_evidence(session)
    drifted = dict(state)
    drifted["agenda"] = {
        **state["agenda"],
        "tasks": [
            {
                **state["agenda"]["tasks"][0],
                "scope_item_ids": ["substituted-prices"],
            },
            state["agenda"]["tasks"][1],
        ],
    }
    evidence = ScenarioTrajectoryEvidence(
        scenario_id="exact_reuse",
        repetition=1,
        sessions=(session,),
        public_states=(drifted,),
        traces=(trace,),
        resolved_evidence_refs=frozenset(set(resolved) - {resolved[0]}),
        mutation_acceptance_counts={**mutations, next(iter(mutations)): 2},
    )

    verdicts = deterministic_invariant_verdicts(evidence)

    assert verdicts["scope_preserved"] is False
    assert verdicts["canonical_refs_resolve"] is False
    assert verdicts["no_replayed_accepted_mutation"] is False


def test_result_counts_model_work_lost_before_checkpoint_from_traces() -> None:
    """Charge a completed provider call even when final state omitted its use."""
    session = build_agentic_scenario_sessions(
        "exact_reuse",
        repetition=1,
        freeze_revision=_FREEZE,
    )[0]
    state, trace, resolved, mutations = _passing_evidence(session)
    coordinator = (
        first_slice_programs().for_role(AgentRole.RESEARCH_COORDINATOR).program_id
    )
    lost_trace = LifecycleTrace(
        trace_id="tr-" + "b" * 32,
        session_id=session.session_id,
        operation="resume",
        spans=(
            _span(
                "agent.session.resume",
                session.session_id,
                coordinator,
                **{"trader.lifecycle_operation": "resume"},
            ),
            _span(
                "agent.model.research_coordinator",
                session.session_id,
                coordinator,
                **_model_identity("lost-before-checkpoint"),
            ),
            _model_result_span(
                "lost-before-checkpoint",
                session.session_id,
                coordinator,
                input_tokens=10,
                output_tokens=5,
            ),
            _model_validation_span(
                "lost-before-checkpoint",
                session.session_id,
                coordinator,
            ),
        ),
    )
    evidence = ScenarioTrajectoryEvidence(
        scenario_id="exact_reuse",
        repetition=1,
        sessions=(session,),
        public_states=(state,),
        traces=(trace, lost_trace),
        resolved_evidence_refs=frozenset(resolved),
        mutation_acceptance_counts=mutations,
    )

    assessment = assess_agentic_scenario(evidence)
    result = build_agentic_scenario_result(evidence, assessment)

    assert result.model_calls == 3
    assert result.total_tokens == 315
    assert result.deterministic_invariants["budgets_within_limits"] is False
    assert result.status == "blocked"


def test_scenario_evidence_requires_every_frozen_variant() -> None:
    """Do not score a paired-brief scenario from only one favorable variant."""
    session = build_agentic_scenario_sessions(
        "distinct_briefs",
        repetition=1,
        freeze_revision=_FREEZE,
    )[0]
    state, trace, resolved, mutations = _passing_evidence(session)

    with pytest.raises(ValueError, match="every frozen session variant"):
        ScenarioTrajectoryEvidence(
            scenario_id="distinct_briefs",
            repetition=1,
            sessions=(session,),
            public_states=(state,),
            traces=(trace,),
            resolved_evidence_refs=frozenset(resolved),
            mutation_acceptance_counts=mutations,
        )


def test_public_span_rejects_raw_secret_and_credential_uri_attributes() -> None:
    """Fail before unsafe MLflow attributes enter qualification evidence."""
    base = {
        "trader.session_id": "session",
        "trader.program_id": "research-coordinator-v4",
    }
    with pytest.raises(ValueError, match="forbidden"):
        PublicTraceSpan(
            name="agent.model.research_coordinator",
            attributes={**base, "trader.raw_prompt": "hidden"},
        )
    with pytest.raises(ValueError, match="credential-shaped"):
        PublicTraceSpan(
            name="agent.model.research_coordinator",
            attributes={
                **base,
                "trader.artifact_ref": "postgresql://user:secret@localhost/db",
            },
        )


def test_lifecycle_trace_requires_one_matching_root_and_consistent_session() -> None:
    """Reject orphaned child spans and cross-session trace contamination."""
    root = PublicTraceSpan(
        name="agent.session.start",
        attributes={
            "trader.session_id": "session-a",
            "trader.lifecycle_operation": "start",
        },
    )
    child = PublicTraceSpan(
        name="agent.model.research_coordinator",
        attributes={"trader.session_id": "session-b"},
    )
    with pytest.raises(ValueError, match="owning session"):
        LifecycleTrace(
            trace_id="tr-" + "a" * 32,
            session_id="session-a",
            operation="start",
            spans=(root, child),
        )


def test_real_mlflow_loader_returns_only_requested_redacted_lifecycle_trace(
    tmp_path: Path,
) -> None:
    """Query a local backend and normalize one nested runtime trajectory."""
    import mlflow

    previous_uri = mlflow.get_tracking_uri()
    tracking_uri = f"sqlite:///{tmp_path / 'observation-traces.db'}"
    experiment = "agentic-observation-test"
    sink = MlflowTraceSink(tracking_uri=tracking_uri, experiment_name=experiment)
    try:
        assert_mlflow_sessions_absent(
            tracking_uri=tracking_uri,
            experiment_name=experiment,
            session_ids=["session-observed"],
        )
        with sink.span(
            "agent.session.start",
            span_type="CHAIN",
            attributes={
                "trader.session_id": "session-observed",
                "trader.branch_id": "root",
                "trader.program_id": "research-coordinator-v4",
                "trader.lifecycle_operation": "start",
            },
        ):
            with sink.span(
                "agent.model.research_coordinator",
                span_type="LLM",
                attributes={
                    "trader.session_id": "session-observed",
                    "trader.branch_id": "root",
                    "trader.program_id": "research-coordinator-v4",
                    "trader.output_contract": "CoordinatorAgenda",
                },
            ):
                pass
        with sink.span(
            "agent.session.inspect",
            span_type="CHAIN",
            attributes={
                "trader.session_id": "another-session",
                "trader.branch_id": "root",
                "trader.program_id": "research-coordinator-v4",
                "trader.lifecycle_operation": "inspect",
            },
        ):
            pass
        traces = load_mlflow_lifecycle_traces(
            tracking_uri=tracking_uri,
            experiment_name=experiment,
            session_ids=["session-observed"],
        )
        with pytest.raises(ValueError, match="already contains"):
            assert_mlflow_sessions_absent(
                tracking_uri=tracking_uri,
                experiment_name=experiment,
                session_ids=["session-observed"],
            )
    finally:
        mlflow.set_tracking_uri(previous_uri)

    assert len(traces) == 1
    assert traces[0].session_id == "session-observed"
    assert traces[0].operation == "start"
    assert {span.name for span in traces[0].spans} == {
        "agent.session.start",
        "agent.model.research_coordinator",
    }


def _passing_evidence(
    session: Any,
) -> tuple[dict[str, Any], LifecycleTrace, list[str], dict[str, int]]:
    """Build one coherent public state/trace/journal fixture."""
    programs = first_slice_programs()
    coordinator = programs.for_role(AgentRole.RESEARCH_COORDINATOR).program_id
    data = programs.for_role(AgentRole.DATA_RESEARCH).program_id
    strategy = programs.for_role(AgentRole.STRATEGY_ENGINEERING).program_id
    session_ref = f"research://postgres/research_session/{session.session_id}"
    decision_ref = "research://postgres/agent_decision_receipt/decision-1"
    manifest_ref = "research://postgres/dataset_manifest/manifest-1"
    quality_ref = "research://postgres/data_quality_report/quality-1"
    comparison_ref = "research://postgres/implementation_comparison/comparison-1"
    validation_ref = "research://postgres/implementation_validation_report/validation-1"
    state = {
        "session_id": session.session_id,
        "agenda": {
            "objective_summary": "Verify Data and exact implementation reuse.",
            "material_ambiguities": [],
            "tasks": [
                {
                    "task_id": "data",
                    "role": "data_research",
                    "work_kind": "complete",
                    "join_mode": "hard",
                    "scope_item_ids": ["primary-prices"],
                },
                {
                    "task_id": "strategy",
                    "role": "strategy_engineering",
                    "work_kind": "complete",
                    "join_mode": "hard",
                    "scope_item_ids": [],
                },
            ],
        },
        "branch_by_task": {"data": "branch-data", "strategy": "branch-strategy"},
        "delegations": [
            {
                "delegation_id": "delegation-data",
                "attempt_id": "attempt-data",
                "branch_id": "branch-data",
                "task": {"task_id": "data", "role": "data_research"},
            },
            {
                "delegation_id": "delegation-strategy",
                "attempt_id": "attempt-strategy",
                "branch_id": "branch-strategy",
                "task": {
                    "task_id": "strategy",
                    "role": "strategy_engineering",
                },
            },
        ],
        "evidence_refs": [
            {"uri": session_ref},
            {"uri": manifest_ref},
            {"uri": quality_ref},
            {"uri": comparison_ref},
            {"uri": validation_ref},
            {"uri": decision_ref},
        ],
        "decision_receipt_ref": {"uri": decision_ref},
        "decision": {
            "action": "conclude",
            "cited_evidence_refs": [
                {"uri": manifest_ref},
                {"uri": comparison_ref},
                {"uri": validation_ref},
            ],
        },
        "budget_usage": {
            "model_calls": 2,
            "tool_calls": 5,
            "input_tokens": 200,
            "output_tokens": 100,
            "duration_ms": 1000,
            "mutations": 2,
            "revisions": 0,
        },
    }
    spans = (
        _span(
            "agent.session.start",
            session.session_id,
            coordinator,
            **{"trader.lifecycle_operation": "start"},
        ),
        _span(
            "agent.model.research_coordinator",
            session.session_id,
            coordinator,
            **_model_identity("coordinator-model-call"),
        ),
        _model_result_span(
            "coordinator-model-call",
            session.session_id,
            coordinator,
            input_tokens=100,
            output_tokens=50,
        ),
        _model_validation_span(
            "coordinator-model-call",
            session.session_id,
            coordinator,
        ),
        _span(
            "agent.model.data_research",
            session.session_id,
            data,
            **_model_identity("data-model-call"),
        ),
        _model_result_span(
            "data-model-call",
            session.session_id,
            data,
            input_tokens=100,
            output_tokens=50,
        ),
        _model_validation_span(
            "data-model-call",
            session.session_id,
            data,
        ),
        _tool_span(
            "research_create_agent_session",
            "session-create",
            session.session_id,
            coordinator,
            "local_mutating",
        ),
        _result_span(
            "research_create_agent_session",
            "session-create",
            session.session_id,
            coordinator,
            [session_ref],
        ),
        _tool_span(
            "data_get_inventory",
            "data-inventory",
            session.session_id,
            data,
            "read_only",
        ),
        _result_span(
            "data_get_inventory",
            "data-inventory",
            session.session_id,
            data,
            [manifest_ref],
        ),
        _tool_span(
            "data_summarize_quality",
            "data-quality",
            session.session_id,
            data,
            "read_only",
        ),
        _result_span(
            "data_summarize_quality",
            "data-quality",
            session.session_id,
            data,
            [quality_ref],
        ),
        _tool_span(
            "research_compare_implementation",
            "strategy-compare",
            session.session_id,
            strategy,
            "read_only",
        ),
        _result_span(
            "research_compare_implementation",
            "strategy-compare",
            session.session_id,
            strategy,
            [comparison_ref, validation_ref],
        ),
        _tool_span(
            "research_record_agent_decision",
            "decision-write",
            session.session_id,
            coordinator,
            "local_mutating",
        ),
        _result_span(
            "research_record_agent_decision",
            "decision-write",
            session.session_id,
            coordinator,
            [decision_ref],
        ),
    )
    trace = LifecycleTrace(
        trace_id="tr-" + "a" * 32,
        session_id=session.session_id,
        operation="start",
        spans=spans,
    )
    resolved = [
        session_ref,
        manifest_ref,
        quality_ref,
        comparison_ref,
        validation_ref,
        decision_ref,
    ]
    return state, trace, resolved, {"session-create": 1, "decision-write": 1}


def _span(
    name: str,
    session_id: str,
    program_id: str,
    **attributes: Any,
) -> PublicTraceSpan:
    """Build one correlated public span."""
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


def _tool_span(
    tool_name: str,
    call_id: str,
    session_id: str,
    program_id: str,
    side_effect: str,
) -> PublicTraceSpan:
    """Build one authorized dispatch span."""
    return _span(
        f"agent.mcp.{tool_name}",
        session_id,
        program_id,
        **{
            "trader.tool_name": tool_name,
            "trader.call_id": call_id,
            "trader.side_effect": side_effect,
        },
    )


def _model_result_span(
    model_call_id: str,
    session_id: str,
    program_id: str,
    *,
    input_tokens: int,
    output_tokens: int,
) -> PublicTraceSpan:
    """Build terminal public accounting for one fake provider call."""
    return _span(
        "agent.model_result." + program_id.split("-v", 1)[0].replace("-", "_"),
        session_id,
        program_id,
        **{
            **_model_identity(model_call_id),
            "trader.model_provider": "static",
            "trader.model_name": "static-json",
            "trader.input_tokens": input_tokens,
            "trader.output_tokens": output_tokens,
            "trader.duration_ms": 10,
            "trader.result_ok": True,
        },
    )


def _model_validation_span(
    model_call_id: str,
    session_id: str,
    program_id: str,
) -> PublicTraceSpan:
    """Build one successful strict-schema verdict for fake model output."""
    role = program_id.split("-v", 1)[0].replace("-", "_")
    return _span(
        f"agent.model_validation.{role}",
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
        "trader.output_contract": "FixtureContract",
        "trader.schema_repair": 0,
    }


def _result_span(
    tool_name: str,
    call_id: str,
    session_id: str,
    program_id: str,
    references: list[str],
) -> PublicTraceSpan:
    """Build one normalized MCP result span."""
    return _span(
        f"agent.mcp_result.{tool_name}",
        session_id,
        program_id,
        **{
            "trader.tool_name": tool_name,
            "trader.call_id": call_id,
            "trader.result_ok": True,
            "trader.evidence_refs": references,
            "trader.evidence_types": [
                reference.removeprefix("research://postgres/").split("/", 1)[0]
                for reference in references
            ],
        },
    )
