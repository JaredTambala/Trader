"""Coordination policy tests for agendas, scheduling, joins, and loop detection.

Subject: Coordinator admission of model-proposed task graphs and computation of bounded executable work.
Level: In-process coordination contract.
Collaborators: Real agenda policy, scheduler, structured runner with static output, and shared public fixtures.
Guarantees: Only valid scoped DAGs schedule; joins, conflicts, ambiguity, specialist selection, and loops fail closed.
Non-goals: Full graph execution, specialist tool loops, Postgres recovery, and real model behavior."""

from __future__ import annotations
from collections.abc import Mapping
from dataclasses import replace
from typing import Any
import anyio
import pytest
from trader_agents import (
    AgentRole,
    BudgetLedger,
    BudgetUsage,
    CoordinatorAction,
    CoordinatorAgenda,
    CoordinatorDecision,
    PublicIssue,
    SpecialistReturn,
    SpecialistStatus,
    StaticJsonLlmClient,
    StructuredModelRunner,
    TraceCorrelation,
    build_delegation,
    composite_data_scope_from_session,
    compute_ready_set,
    development_model_profiles,
    first_slice_programs,
)
from trader_agents.coordination.coordinator import (
    _apply_coordinator_loop_policy,
    _data_scope_for_task,
    _validate_first_slice_agenda,
)
from trader_research.governance import ResearchSession
from tests.trader_agents.support.runtime_contracts import _budget, _session, _task


def test_scheduler_parallelizes_ready_work_and_honors_hard_joins() -> None:
    """Independent work runs together while dependent/conflicting work waits."""
    agenda = CoordinatorAgenda(
        objective_summary="Prepare exact Data and implementation evidence.",
        tasks=[
            _task("data", "data_research"),
            _task("strategy", "strategy_engineering"),
            _task(
                "data-remediation",
                "data_research",
                dependencies=["data"],
                mutation_requested=True,
            ),
        ],
    )
    first = compute_ready_set(
        agenda,
        completed_task_ids=[],
        mutation_keys_by_task={"data-remediation": ["dataset:prices"]},
        budget=_budget(),
        usage=BudgetLedger(_budget()).usage,
    )
    assert [item.task.task_id for item in first] == ["data", "strategy"]
    second = compute_ready_set(
        agenda,
        completed_task_ids=["data", "strategy"],
        active_mutation_keys=["dataset:prices"],
        mutation_keys_by_task={"data-remediation": ["dataset:prices"]},
        budget=_budget(),
        usage=BudgetLedger(_budget()).usage,
    )
    assert second == ()


def test_coordinator_semantic_loop_guard_ignores_paraphrase_and_new_attempt_id() -> (
    None
):
    """Equivalent revisions stop when prose and delegation identity change."""
    session = _session()
    task = _task("data", "data_research")
    agenda = CoordinatorAgenda(
        objective_summary="Resolve the approved Data scope.",
        tasks=[task, _task("strategy", "strategy_engineering")],
    )

    def _return(attempt: int) -> tuple[Any, SpecialistReturn]:
        delegation = build_delegation(
            session_id=session.session_id,
            branch_id="data-branch",
            task=task,
            required_input_refs=[],
            permitted_side_effects=["read_only", "local_mutating"],
            reserved_model_calls=4,
            reserved_tool_calls=8,
            reserved_tokens=4_000,
            attempt=attempt,
        )
        result = SpecialistReturn(
            delegation_id=delegation.delegation_id,
            session_id=session.session_id,
            branch_id=delegation.branch_id,
            attempt_id=delegation.attempt_id,
            role="data_research",
            program_id="data-research-v6",
            model_profile_id=session.model_profile_id,
            tool_catalog_id=session.tool_catalog_id,
            status=SpecialistStatus.BLOCKED,
            blockers=[
                PublicIssue(
                    code="data_missing",
                    message="The approved scope remains incomplete.",
                )
            ],
            budget_used=BudgetUsage(),
        )
        return delegation, result

    first_delegation, first_return = _return(1)
    second_delegation, second_return = _return(2)
    first = CoordinatorDecision(
        action=CoordinatorAction.REVISE,
        summary="Ask Data Research to inspect the unresolved gap again.",
        reviewed_delegation_ids=[first_delegation.delegation_id],
        criteria_applied=["complete approved coverage"],
        affected_task_ids=["data"],
        expected_information_gain="Determine whether the gap can be resolved.",
    )
    paraphrase = first.model_copy(
        update={
            "summary": "Retry the same missing Data investigation.",
            "reviewed_delegation_ids": [second_delegation.delegation_id],
            "expected_information_gain": "Check the unresolved coverage once more.",
        }
    )
    fingerprints: dict[str, int] = {}

    accepted = _apply_coordinator_loop_policy(
        first,
        agenda=agenda,
        new_returns=[first_return],
        delegations=[first_delegation],
        loop_fingerprints=fingerprints,
    )
    stopped = _apply_coordinator_loop_policy(
        paraphrase,
        agenda=agenda,
        new_returns=[second_return],
        delegations=[second_delegation],
        loop_fingerprints=fingerprints,
    )

    assert accepted.action.value == "revise"
    assert stopped.action.value == "stop_fail_closed"
    assert stopped.blockers[0].code == "low_information_loop"


def test_agenda_decomposes_disjoint_data_and_joins_before_construction() -> None:
    """Code-owned policy accepts complete disjoint fan-out and hard joins."""
    base_scope = composite_data_scope_from_session(_session())
    base_item = base_scope.items[0]
    data_scope = base_scope.model_copy(
        update={
            "items": [
                base_item.model_copy(
                    update={"item_id": "btc-prices", "symbols": ["BTC/USD"]}
                ),
                base_item.model_copy(
                    update={"item_id": "eth-prices", "symbols": ["ETH/USD"]}
                ),
            ]
        }
    )
    agenda = CoordinatorAgenda(
        objective_summary="Investigate both assets and construct one candidate.",
        tasks=[
            _task(
                "btc-data",
                "data_research",
                work_kind="investigate",
                join_mode="soft",
                scope_item_ids=["btc-prices"],
            ),
            _task(
                "eth-data",
                "data_research",
                work_kind="investigate",
                join_mode="soft",
                scope_item_ids=["eth-prices"],
            ),
            _task(
                "data-join",
                "data_research",
                work_kind="reconcile",
                dependencies=["btc-data", "eth-data"],
            ),
            _task(
                "catalogue",
                "strategy_engineering",
                work_kind="catalogue",
                join_mode="soft",
            ),
            _task(
                "construct",
                "strategy_engineering",
                work_kind="construct",
                dependencies=["catalogue", "data-join"],
            ),
        ],
    )

    _validate_first_slice_agenda(agenda, data_scope=data_scope)

    btc_scope = _data_scope_for_task(data_scope, agenda.tasks[0])
    assert [item.item_id for item in btc_scope.items] == ["btc-prices"]
    assert btc_scope.scope_id != data_scope.scope_id


def test_agenda_accepts_only_the_specialist_required_by_the_brief() -> None:
    """Coordinator agendas may select Data or Strategy without synthetic work."""
    data_scope = composite_data_scope_from_session(_session())
    data_agenda = CoordinatorAgenda(
        objective_summary="Establish whether the approved Data scope is ready.",
        tasks=[_task("data", "data_research")],
    )
    strategy_agenda = CoordinatorAgenda(
        objective_summary="Find an admitted implementation for the supplied brief.",
        tasks=[_task("strategy", "strategy_engineering")],
    )

    _validate_first_slice_agenda(data_agenda, data_scope=data_scope)
    _validate_first_slice_agenda(strategy_agenda, data_scope=data_scope)


def test_agenda_rejects_empty_executable_work() -> None:
    """A non-ambiguous agenda must select at least one specialist task."""
    with pytest.raises(ValueError, match="requires tasks"):
        CoordinatorAgenda(
            objective_summary="Investigate the approved research question.",
        )


def test_agenda_rejects_overlapping_parallel_data_scopes() -> None:
    """The model cannot assign the same mutable Data scope to parallel work."""
    base_scope = composite_data_scope_from_session(_session())
    base_item = base_scope.items[0]
    data_scope = base_scope.model_copy(
        update={
            "items": [
                base_item.model_copy(update={"item_id": "first"}),
                base_item.model_copy(update={"item_id": "second"}),
            ]
        }
    )
    agenda = CoordinatorAgenda(
        objective_summary="Invalid overlapping decomposition.",
        tasks=[
            _task(
                "one",
                "data_research",
                work_kind="investigate",
                scope_item_ids=["first"],
            ),
            _task(
                "two",
                "data_research",
                work_kind="investigate",
                scope_item_ids=["first", "second"],
            ),
            _task(
                "join",
                "data_research",
                work_kind="reconcile",
                dependencies=["one", "two"],
            ),
            _task("strategy", "strategy_engineering"),
        ],
    )

    with pytest.raises(ValueError, match="overlap"):
        _validate_first_slice_agenda(agenda, data_scope=data_scope)


def test_ambiguous_agenda_rejects_executable_tasks() -> None:
    """A declared material ambiguity cannot include speculative work."""
    session = _session()
    agenda = CoordinatorAgenda(
        objective_summary="Resolve the missing behavior before investigation.",
        material_ambiguities=["Failure behavior is not specified."],
        tasks=[_task("speculative-data", "data_research")],
    )

    with pytest.raises(ValueError, match="cannot contain tasks"):
        _validate_first_slice_agenda(
            agenda,
            data_scope=composite_data_scope_from_session(session),
        )


def test_distinct_briefs_produce_distinct_valid_agendas_under_same_policy() -> None:
    """Material ambiguity changes the model agenda without changing authority."""
    ready_session = _session(session_id="session-distinct-ready")
    ambiguous_session = replace(
        _session(session_id="session-distinct-ambiguous"),
        objective=(
            "Prepare the candidate, but the operator has not specified how "
            "equal-ranked assets should be allocated."
        ),
    )
    ready_payload = {
        "objective_summary": "Prepare exact Data and implementation evidence.",
        "material_ambiguities": [],
        "tasks": [
            _task(
                "data",
                "data_research",
                mutation_requested=True,
            ).model_dump(mode="json"),
            _task(
                "strategy",
                "strategy_engineering",
                mutation_requested=True,
            ).model_dump(mode="json"),
        ],
    }
    ambiguous_payload = {
        "objective_summary": "Resolve a material allocation ambiguity.",
        "material_ambiguities": ["Define allocation when asset ranks are equal."],
        "tasks": [],
    }
    program = first_slice_programs().for_role(AgentRole.RESEARCH_COORDINATOR)
    profile = development_model_profiles().get(program.model_profile_id)

    async def _agenda(
        session: ResearchSession,
        payload: Mapping[str, Any],
    ) -> CoordinatorAgenda:
        invocation = await StructuredModelRunner(
            StaticJsonLlmClient((payload,))
        ).invoke(
            program=program,
            profile=profile,
            output_type=CoordinatorAgenda,
            instruction="Interpret the brief into one bounded first-slice agenda.",
            public_context={
                "objective": session.objective,
                "approval_policy": session.approval_policy,
            },
            ledger=BudgetLedger(session.budget),
            correlation=TraceCorrelation(
                session_id=session.session_id,
                branch_id="root",
                program_id=program.program_id,
                model_profile_id=profile.profile_id,
                tool_catalog_id=session.tool_catalog_id,
            ),
        )
        return invocation.output

    async def _run() -> tuple[CoordinatorAgenda, CoordinatorAgenda]:
        return (
            await _agenda(ready_session, ready_payload),
            await _agenda(ambiguous_session, ambiguous_payload),
        )

    ready_agenda, ambiguous_agenda = anyio.run(_run)
    _validate_first_slice_agenda(
        ready_agenda,
        data_scope=composite_data_scope_from_session(ready_session),
    )
    _validate_first_slice_agenda(
        ambiguous_agenda,
        data_scope=composite_data_scope_from_session(ambiguous_session),
    )

    assert ready_session.approval_policy == ambiguous_session.approval_policy
    assert ready_session.tool_catalog_id == ambiguous_session.tool_catalog_id
    assert {task.role for task in ready_agenda.tasks} == {
        "data_research",
        "strategy_engineering",
    }
    assert ambiguous_agenda.tasks == []
    assert ready_agenda.model_dump(mode="json") != ambiguous_agenda.model_dump(
        mode="json"
    )
