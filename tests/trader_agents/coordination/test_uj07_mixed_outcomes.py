"""Mixed specialist outcomes and lost-response recovery for UJ-07.

Subject: Task-level downstream eligibility and public specialist-return recovery.
Level: In-process contract plus a fresh Python process over retained JSON state.
Collaborators: Real agenda, checkpoint, delegation, return, and scheduler contracts; no model or MCP transport.
Guarantees: Negative and partial returns remain visible but cannot unlock dependencies or conclude; a retained terminal return recovers once without crossing branch or attempt identity.
Non-goals: Scientific quality, provider behavior, live canonical reads, or Console rendering.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from trader_agents import (
    AgentRole,
    BudgetUsage,
    CoordinatorAction,
    CoordinatorAgenda,
    CoordinatorDecision,
    SpecialistReturn,
    SpecialistStatus,
    build_delegation,
    build_specialist_checkpoint_state,
    compute_ready_set,
    first_slice_programs,
    validate_agent_checkpoint_state,
    validate_specialist_checkpoint_state,
)
from trader_agents.coordination.coordinator import (
    _accept_specialist_returns,
    _eligible_task_ids,
    _validate_coordinator_decision,
)
from trader_research.foundation import json_payload_hash
from tests.trader_agents.coordination.support.uj07_specialist_fixture import (
    build_joined_checkpoint,
    build_uj07_fixture,
)
from tests.trader_agents.support.runtime_contracts import _budget, _task


@pytest.mark.parametrize(
    ("data_status", "strategy_status", "eligible"),
    [
        (SpecialistStatus.READY, SpecialistStatus.READY, ["data", "strategy"]),
        (SpecialistStatus.PARTIAL, SpecialistStatus.READY, ["strategy"]),
        (SpecialistStatus.FAILED, SpecialistStatus.READY, ["strategy"]),
        (SpecialistStatus.BLOCKED, SpecialistStatus.READY, ["strategy"]),
        (SpecialistStatus.READY, SpecialistStatus.CONDITIONAL, ["data"]),
    ],
)
def test_only_ready_current_returns_unlock_a_dependent_task(
    data_status: SpecialistStatus,
    strategy_status: SpecialistStatus,
    eligible: list[str],
) -> None:
    """A retained terminal outcome is not automatically downstream permission."""
    # The retained fixture deliberately models the four qualified outcomes;
    # a conditional specialist return uses the same typed return contract.
    fixture = build_uj07_fixture(
        data_status=data_status,
        strategy_status=(
            SpecialistStatus.PARTIAL
            if strategy_status is SpecialistStatus.CONDITIONAL
            else strategy_status
        ),
    )
    state = build_joined_checkpoint(fixture)
    if strategy_status is SpecialistStatus.CONDITIONAL:
        result = fixture.branches[1].result.model_copy(
            update={"status": strategy_status}
        )
        state["specialist_returns"] = [
            fixture.branches[0].result.model_dump(mode="json"),
            result.model_dump(mode="json"),
        ]
        state["accepted_return_digests"] = {
            fixture.branches[0].result.delegation_id: json_payload_hash(
                fixture.branches[0].result.model_dump(mode="json")
            ),
            result.delegation_id: json_payload_hash(result.model_dump(mode="json")),
        }
    validate_agent_checkpoint_state(state)
    assert _eligible_task_ids(state) == eligible
    agenda = CoordinatorAgenda(
        objective_summary="Join Data and Strategy before evaluation.",
        tasks=[
            *(branch.delegation.task for branch in fixture.branches),
            _task("evaluation", "data_research", dependencies=["data", "strategy"]),
        ],
    )
    ready = compute_ready_set(
        agenda,
        completed_task_ids=["data", "strategy"],
        eligible_dependency_ids=_eligible_task_ids(state),
        budget=_budget(),
        usage=BudgetUsage(),
    )
    assert [item.task.task_id for item in ready] == (
        ["evaluation"] if len(eligible) == 2 else []
    )


def test_mixed_outcome_cannot_be_concluded_as_ready() -> None:
    """A ready sibling never masks a partial Data return at the same hard join."""
    fixture = build_uj07_fixture(data_status=SpecialistStatus.PARTIAL)
    state = build_joined_checkpoint(fixture)
    agenda = CoordinatorAgenda.model_validate(state["agenda"])
    returns = [branch.result for branch in fixture.branches]
    decision = CoordinatorDecision(
        action=CoordinatorAction.CONCLUDE,
        summary="Both branches are ready.",
        reviewed_delegation_ids=[item.delegation_id for item in returns],
        cited_evidence_refs=returns[1].evidence_refs,
        criteria_applied=["both branches ready"],
    )
    with pytest.raises(ValueError, match="every current agenda task to be ready"):
        _validate_coordinator_decision(
            decision,
            agenda=agenda,
            delegations=[branch.delegation for branch in fixture.branches],
            new_returns=returns,
            all_returns=returns,
            verified_refs=[
                item.model_dump(mode="json") for item in returns[1].evidence_refs
            ],
            completed_task_ids=["data", "strategy"],
        )


def test_ready_sibling_of_same_role_cannot_hide_partial_task() -> None:
    """Conclusion checks every task, including two tasks owned by one role."""
    fixture = build_uj07_fixture(data_status=SpecialistStatus.PARTIAL)
    data, strategy = fixture.branches
    extra_task = _task("data-extra", "data_research")
    extra = build_delegation(
        session_id=fixture.session_id,
        branch_id=f"{fixture.session_id}/data-extra",
        task=extra_task,
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=2,
        reserved_tool_calls=4,
        reserved_tokens=1_000,
        attempt=1,
    )
    extra_return = SpecialistReturn.model_validate(
        {
            **data.result.model_dump(mode="json"),
            "delegation_id": extra.delegation_id,
            "branch_id": extra.branch_id,
            "attempt_id": extra.attempt_id,
            "status": "ready",
        }
    )
    agenda = CoordinatorAgenda(
        objective_summary="Review all three exact tasks.",
        tasks=[data.delegation.task, strategy.delegation.task, extra_task],
    )
    decision = CoordinatorDecision(
        action=CoordinatorAction.CONCLUDE,
        summary="All three tasks are ready.",
        reviewed_delegation_ids=[
            data.result.delegation_id,
            strategy.result.delegation_id,
            extra_return.delegation_id,
        ],
        cited_evidence_refs=strategy.result.evidence_refs,
        criteria_applied=["all task outcomes"],
    )
    with pytest.raises(ValueError, match="every current agenda task to be ready"):
        _validate_coordinator_decision(
            decision,
            agenda=agenda,
            delegations=[data.delegation, strategy.delegation, extra],
            new_returns=[data.result, strategy.result, extra_return],
            all_returns=[data.result, strategy.result, extra_return],
            verified_refs=[
                item.model_dump(mode="json") for item in strategy.result.evidence_refs
            ],
            completed_task_ids=["data", "strategy", "data-extra"],
        )


def test_stale_retry_and_incompatible_runtime_pins_cannot_replace_return() -> None:
    """An old attempt and foreign program, profile, or catalogue fail admission."""
    fixture = build_uj07_fixture()
    state = build_joined_checkpoint(fixture)
    data = fixture.branches[0]
    with pytest.raises(ValueError, match="stale specialist attempt"):
        _accept_specialist_returns(
            state,
            delegations=[data.delegation],
            results=[data.result],
            current_attempts={"data": 2},
            programs=first_slice_programs(),
        )
    for change, message in (
        ({"program_id": "foreign"}, "program is incompatible"),
        ({"model_profile_id": "foreign"}, "model profile is incompatible"),
        ({"tool_catalog_id": "foreign"}, "tool catalogue is incompatible"),
    ):
        with pytest.raises(ValueError, match=message):
            _accept_specialist_returns(
                state,
                delegations=[data.delegation],
                results=[data.result.model_copy(update=change)],
                current_attempts={"data": 1},
                programs=first_slice_programs(),
            )


def test_new_partial_revision_revokes_old_ready_eligibility() -> None:
    """A previously ready attempt cannot qualify a later partial revision."""
    fixture = build_uj07_fixture()
    state = build_joined_checkpoint(fixture)
    data = fixture.branches[0]
    retry = build_delegation(
        session_id=fixture.session_id,
        branch_id=data.branch_id,
        task=data.delegation.task,
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=2,
        reserved_tool_calls=4,
        reserved_tokens=1_000,
        attempt=2,
    )
    revised = SpecialistReturn.model_validate(
        {
            **data.result.model_dump(mode="json"),
            "delegation_id": retry.delegation_id,
            "attempt_id": retry.attempt_id,
            "status": "partial",
        }
    )
    state["delegations"] = [
        *(branch.delegation.model_dump(mode="json") for branch in fixture.branches),
        retry.model_dump(mode="json"),
    ]
    state["specialist_returns"] = [
        *(branch.result.model_dump(mode="json") for branch in fixture.branches),
        revised.model_dump(mode="json"),
    ]
    state["accepted_return_digests"] = {
        **state["accepted_return_digests"],
        revised.delegation_id: json_payload_hash(revised.model_dump(mode="json")),
    }
    state["task_attempts"] = {"data": 2, "strategy": 1}
    validate_agent_checkpoint_state(state)
    assert _eligible_task_ids(state) == ["strategy"]


def test_lost_branch_response_recovers_from_retained_terminal_in_fresh_process(
    tmp_path: Path,
) -> None:
    """A replacement process admits a lost Strategy response exactly once."""
    fixture = build_uj07_fixture(strategy_status=SpecialistStatus.PARTIAL)
    data, strategy = fixture.branches
    coordinator = build_joined_checkpoint(fixture)
    coordinator["specialist_returns"] = [data.result.model_dump(mode="json")]
    coordinator["accepted_return_digests"] = {
        data.result.delegation_id: json_payload_hash(
            data.result.model_dump(mode="json")
        )
    }
    coordinator["completed_task_ids"] = ["data"]
    coordinator["active_delegations"] = [strategy.delegation.model_dump(mode="json")]
    validate_agent_checkpoint_state(coordinator)
    assert _eligible_task_ids(coordinator) == ["data"]
    unavailable_conclusion = CoordinatorDecision(
        action=CoordinatorAction.CONCLUDE,
        summary="Both specialists have returned ready.",
        reviewed_delegation_ids=[data.result.delegation_id],
        cited_evidence_refs=data.result.evidence_refs,
        criteria_applied=["both branch responses present"],
    )
    with pytest.raises(ValueError, match="every agenda task to be completed"):
        _validate_coordinator_decision(
            unavailable_conclusion,
            agenda=CoordinatorAgenda.model_validate(coordinator["agenda"]),
            delegations=[branch.delegation for branch in fixture.branches],
            new_returns=[data.result],
            all_returns=[data.result],
            verified_refs=[
                item.model_dump(mode="json") for item in data.result.evidence_refs
            ],
            completed_task_ids=["data"],
        )

    specialist = build_specialist_checkpoint_state(
        session_id=fixture.session_id,
        session_digest="a" * 64,
        delegation=strategy.delegation,
        role=AgentRole.STRATEGY_ENGINEERING,
        phase="review",
        program_id=strategy.result.program_id,
        model_profile_id=strategy.result.model_profile_id,
        tool_catalog_id=strategy.result.tool_catalog_id,
    )
    specialist["terminal_return"] = strategy.result.model_dump(mode="json")
    specialist["status"] = "completed"
    validate_specialist_checkpoint_state(specialist)
    script = """
import json
import sys
from trader_agents import SpecialistDelegation, SpecialistReturn, first_slice_programs, validate_agent_checkpoint_state, validate_specialist_checkpoint_state
from trader_agents.coordination.coordinator import _accept_specialist_returns, _eligible_task_ids
bundle = json.loads(sys.stdin.read())
coordinator, specialist = bundle["coordinator"], bundle["specialist"]
validate_agent_checkpoint_state(coordinator)
validate_specialist_checkpoint_state(specialist)
delegation = SpecialistDelegation.model_validate(coordinator["active_delegations"][0])
result = SpecialistReturn.model_validate(specialist["terminal_return"])
accepted, digests = _accept_specialist_returns(coordinator, delegations=[delegation], results=[result], current_attempts=coordinator["task_attempts"], programs=first_slice_programs())
coordinator["specialist_returns"].extend(item.model_dump(mode="json") for item in accepted)
coordinator["accepted_return_digests"] = digests
coordinator["completed_task_ids"].append(delegation.task.task_id)
coordinator["active_delegations"] = []
validate_agent_checkpoint_state(coordinator)
again, _ = _accept_specialist_returns(coordinator, delegations=[delegation], results=[result], current_attempts=coordinator["task_attempts"], programs=first_slice_programs())
print(json.dumps({"accepted": len(accepted), "duplicate": len(again), "eligible": _eligible_task_ids(coordinator), "statuses": [item["status"] for item in coordinator["specialist_returns"]]}, sort_keys=True))
"""
    repository_root = Path(__file__).resolve().parents[3]
    python_path = os.pathsep.join((str(repository_root), str(repository_root / "src")))
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps({"coordinator": coordinator, "specialist": specialist}),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": python_path},
    )
    verdict = json.loads(result.stdout)
    assert verdict == {
        "accepted": 1,
        "duplicate": 0,
        "eligible": ["data"],
        "statuses": ["ready", "partial"],
    }
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository_root, text=True
    ).strip()
    report = {
        "fixture": "uj07-mixed-specialist-outcomes-v1",
        "contract": "SpecialistReturn/CoordinatorAgenda",
        "contract_digest": json_payload_hash(SpecialistReturn.model_json_schema()),
        "checkout_commit": commit,
        "evidence_revision": data.result.evidence_refs[0].source_hash,
        "verdict": verdict,
    }
    path = tmp_path / "uj07-mixed-outcomes-verifier.json"
    path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    assert json.loads(path.read_text()) == report
