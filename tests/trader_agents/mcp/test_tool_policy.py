"""Policy tests for role-scoped Agent access to MCP tools.

Subject: Code-owned catalogue visibility, authority denial, Data scope binding, and mutation-cost admission.
Level: In-process policy contract.
Collaborators: Real Agent tool catalogue and authorization policy with immutable synthetic sessions; no transport.
Guarantees: Agents cannot reach trading capabilities, widen scope, or mutate without an approved bounded plan.
Non-goals: MCP envelope handling, subprocess lifecycle, specialist reasoning, and provider-side data behavior."""

from __future__ import annotations
import pytest
from trader_agents import (
    AgentPhase,
    AgentRole,
    BudgetLedger,
    BudgetUsage,
    CoordinatorAction,
    CoordinatorDecision,
    PolicyContext,
    PolicyViolation,
    PublicIssue,
    ToolCallProposal,
    ToolPolicy,
    build_delegation,
    composite_data_scope_from_session,
    first_slice_tool_catalogue,
    strategy_build_contract_from_session,
)
from tests.trader_agents.support.runtime_contracts import _session, _task


def test_role_catalogue_and_policy_fail_closed() -> None:
    """Data cannot see broker tools or widen its approved composite scope."""
    session = _session()
    catalogue = first_slice_tool_catalogue()
    visible = catalogue.available(
        role=AgentRole.DATA_RESEARCH,
        phase=AgentPhase.INVESTIGATE,
        approval_policy=session.approval_policy,
    )
    assert "data_get_inventory" in {item.name for item in visible}
    assert all("broker" not in item.name for item in visible)
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-branch",
        task=_task("data", "data_research"),
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=4,
        reserved_tool_calls=8,
        reserved_tokens=4_000,
        attempt=1,
    )
    context = PolicyContext(
        session=session,
        role=AgentRole.DATA_RESEARCH,
        phase=AgentPhase.INVESTIGATE,
        program_id="data-research-v6",
        tool_catalogue=catalogue,
        usage=BudgetLedger(session.budget).usage,
        runtime_state={},
        loop_fingerprints={},
        delegation=delegation,
        data_scope=composite_data_scope_from_session(session),
    )
    proposal = ToolCallProposal(
        call_id="outside",
        tool_name="data_get_inventory",
        arguments={
            "symbols": ["SOL/USD"],
            "asset_class": "crypto",
            "timeframe": "1h",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-06-30T23:00:00Z",
        },
        purpose="Inspect an unapproved symbol.",
        expected_evidence=["inventory"],
    )
    with pytest.raises(PolicyViolation) as raised:
        ToolPolicy().authorize(proposal, context)
    assert raised.value.code == "data_scope_expansion"


def test_denied_trading_path_has_no_agent_capability() -> None:
    """No first-slice role can expose or authorize execution/trading tools."""
    catalogue = first_slice_tool_catalogue()
    session = _session(session_id="session-denied-trading")
    forbidden_fragments = {
        "backtest",
        "broker",
        "deploy",
        "execution",
        "optimization",
        "order",
        "paper",
        "trade",
    }
    for role in AgentRole:
        role_names = {
            definition.name
            for phase in AgentPhase
            for definition in catalogue.available(
                role=role,
                phase=phase,
                approval_policy=session.approval_policy,
            )
        }
        assert all(
            not any(fragment in name for fragment in forbidden_fragments)
            for name in role_names
        )

    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="strategy-denied-trading",
        task=_task("strategy-denied-trading", "strategy_engineering"),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=4,
        reserved_tool_calls=4,
        reserved_tokens=4_000,
        attempt=1,
    )
    context = PolicyContext(
        session=session,
        role=AgentRole.STRATEGY_ENGINEERING,
        phase=AgentPhase.TERMINAL,
        program_id="strategy-engineering-v6",
        tool_catalogue=catalogue,
        usage=BudgetUsage(),
        runtime_state={},
        loop_fingerprints={},
        delegation=delegation,
        build_contract=strategy_build_contract_from_session(
            session,
            branch_id=delegation.branch_id,
        ),
    )
    for tool_name in (
        "broker_submit_order",
        "research_run_backtest",
        "ml_create_deployment_manifest",
    ):
        proposal = ToolCallProposal(
            call_id=f"denied-{tool_name}",
            tool_name=tool_name,
            arguments={},
            purpose="Attempt the operator-requested paper deployment.",
            expected_evidence=["execution status"],
            mutation_reason="Attempt an out-of-authority action.",
        )
        with pytest.raises(PolicyViolation) as raised:
            ToolPolicy().authorize(proposal, context)
        assert raised.value.code == "tool_not_allowed"

    decision = CoordinatorDecision(
        action=CoordinatorAction.STOP_FAIL_CLOSED,
        summary=(
            "Admission is research evidence and does not authorize deployment "
            "or paper/live trading."
        ),
        criteria_applied=["first-slice authority boundary"],
        blockers=[
            PublicIssue(
                code="trading_authority_denied",
                message="Broker and deployment mutation require another workflow.",
            )
        ],
        permitted_next_actions=["hand off to a future human-approved workflow"],
    )
    assert decision.action.value == "stop_fail_closed"
    assert decision.blockers[0].code == "trading_authority_denied"


def test_data_backfill_requires_costed_matching_dry_run_plan() -> None:
    """Provider mutation cannot bypass the approved acquisition cost envelope."""
    session = _session()
    catalogue = first_slice_tool_catalogue()
    scope = composite_data_scope_from_session(session)
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-branch",
        task=_task("data", "data_research", mutation_requested=True),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=4,
        reserved_tool_calls=8,
        reserved_tokens=4_000,
        attempt=1,
    )
    arguments = {
        "symbols": ["BTC/USD", "ETH/USD"],
        "asset_class": "crypto",
        "timeframe": "1h",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-06-30T23:00:00Z",
        "mode": "backfill",
        "dry_run": False,
        "acquisition_plan_id": "plan-1",
        "operation_id": "runtime-bound-operation",
        "requested_by": session.session_id,
        "actor": "Data Research Agent",
    }
    proposal = ToolCallProposal(
        call_id="backfill-1",
        tool_name="data_ensure_loaded",
        arguments=arguments,
        purpose="Execute the approved matching acquisition plan.",
        expected_evidence=["post-load inventory and quality"],
        mutation_reason="Fill the approved Data gap.",
    )

    def _context(estimated_cost: float | None) -> PolicyContext:
        lifecycle = (
            {}
            if estimated_cost is None
            else {
                "acquisition_plan": {
                    "plan_id": "plan-1",
                    "estimated_cost": estimated_cost,
                }
            }
        )
        return PolicyContext(
            session=session,
            role=AgentRole.DATA_RESEARCH,
            phase=AgentPhase.REMEDIATE,
            program_id="data-research-v6",
            tool_catalogue=catalogue,
            usage=BudgetUsage(),
            runtime_state=lifecycle,
            loop_fingerprints={},
            delegation=delegation,
            data_scope=scope,
        )

    with pytest.raises(PolicyViolation) as missing:
        ToolPolicy().authorize(proposal, _context(None))
    assert missing.value.code == "acquisition_plan_required"

    with pytest.raises(PolicyViolation) as expensive:
        ToolPolicy().authorize(proposal, _context(10.01))
    assert expensive.value.code == "loading_cost_exceeded"

    authorized = ToolPolicy().authorize(proposal, _context(10.0))
    assert authorized.proposal.arguments["acquisition_plan_id"] == "plan-1"


def test_data_scope_policy_normalizes_equivalent_timezone_boundaries() -> None:
    """Equivalent aware timestamps do not become false scope expansions."""
    session = _session(session_id="session-timezone-normalization")
    catalogue = first_slice_tool_catalogue()
    scope = composite_data_scope_from_session(session)
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-timezone-branch",
        task=_task("data-timezone", "data_research"),
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=2,
        reserved_tool_calls=2,
        reserved_tokens=2_000,
        attempt=1,
    )
    proposal = ToolCallProposal(
        call_id="timezone-inventory",
        tool_name="data_get_inventory",
        arguments={
            "symbols": ["BTC/USD", "ETH/USD"],
            "asset_class": "crypto",
            "timeframe": "1h",
            "start": "2023-12-31T19:00:00-05:00",
            "end": "2024-06-30T19:00:00-04:00",
        },
        purpose="Read the exact scope using equivalent timezone offsets.",
        expected_evidence=["bounded inventory"],
    )
    context = PolicyContext(
        session=session,
        role=AgentRole.DATA_RESEARCH,
        phase=AgentPhase.INVESTIGATE,
        program_id="data-research-v6",
        tool_catalogue=catalogue,
        usage=BudgetUsage(),
        runtime_state={},
        loop_fingerprints={},
        delegation=delegation,
        data_scope=scope,
    )

    authorized = ToolPolicy().authorize(proposal, context)

    assert authorized.proposal.call_id == "timezone-inventory"
