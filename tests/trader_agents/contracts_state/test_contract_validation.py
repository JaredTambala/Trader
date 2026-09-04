"""Contract validation tests for public Agent model outputs.

Subject: Strict agenda, specialist-turn, and parameter value contracts at Agent trust boundaries.
Level: In-process contract.
Collaborators: Real Pydantic Agent contracts and shared task builders; no graph or external service.
Guarantees: Cycles, unknown fields, type ambiguity, and out-of-bounds parameters fail before execution.
Non-goals: Coordinator policy, model quality, tool authorization, and persistence."""

from __future__ import annotations
import pytest
from pydantic import ValidationError
from trader_agents import CoordinatorAgenda, DataAgentTurn, ParameterContract
from tests.trader_agents.support.runtime_contracts import _task


def test_agenda_rejects_cycles_and_unknown_fields() -> None:
    """The model cannot smuggle fields or submit an unschedulable DAG."""
    with pytest.raises(ValidationError, match="cycle"):
        CoordinatorAgenda(
            objective_summary="Inspect Data and implementation evidence.",
            tasks=[
                _task("data", "data_research", dependencies=["strategy"]),
                _task(
                    "strategy",
                    "strategy_engineering",
                    dependencies=["data"],
                ),
            ],
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        DataAgentTurn.model_validate(
            {
                "action": "change_phase",
                "public_rationale": "Coverage gap requires approved remediation.",
                "next_phase": "remediate",
                "hidden_reasoning": "do not persist",
            }
        )


def test_parameter_contract_enforces_declared_type_and_bounds() -> None:
    """Typed build inputs reject bool-as-int ambiguity and out-of-range defaults before implementation."""
    with pytest.raises(ValidationError, match="integer parameter"):
        ParameterContract(
            name="window",
            value_type="integer",
            default=True,
            minimum=1,
            maximum=100,
            tunable=True,
            semantics="Lookback bars.",
        )
    with pytest.raises(ValidationError, match="above maximum"):
        ParameterContract(
            name="window",
            value_type="integer",
            default=101,
            minimum=1,
            maximum=100,
            tunable=True,
            semantics="Lookback bars.",
        )
