"""Contract test for normalized Agent session inputs and runtime pins.

Subject: Application entry normalization of Data scope, strategy build contract, and immutable runtime identities.
Level: In-process contract.
Collaborators: Real session adapters and code-owned profile, program, and tool registries; no graph execution.
Guarantees: An admitted session resolves exact bounded inputs and passes only matching runtime pins.
Non-goals: Model calls, MCP execution, checkpointing, and lifecycle completion."""

from __future__ import annotations
from trader_agents import (
    composite_data_scope_from_session,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
    strategy_build_contract_from_session,
    validate_runtime_pins,
)
from tests.trader_agents.support.runtime_contracts import _session


def test_session_inputs_and_runtime_pins_normalize_exact_contracts() -> None:
    """A session enters runtime only through strict Data and build contracts."""
    session = _session()
    scope = composite_data_scope_from_session(session)
    contract = strategy_build_contract_from_session(
        session,
        branch_id="strategy-branch",
    )
    validate_runtime_pins(
        session,
        model_profiles=development_model_profiles(),
        agent_programs=first_slice_programs(),
        tool_catalogue=first_slice_tool_catalogue(),
    )
    assert scope.session_id == session.session_id
    assert {symbol for item in scope.items for symbol in item.symbols} == {
        "BTC/USD",
        "ETH/USD",
    }
    assert contract.provenance == "operator_specified"
    assert contract.branch_id == "strategy-branch"
