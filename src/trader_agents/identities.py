"""Dependency-free agent identity metadata for future LangGraph graphs."""

from __future__ import annotations

from dataclasses import dataclass

from trader_research.agents import AgentDefinition, get_agent_definition


@dataclass(frozen=True)
class AgentIdentity:
    """Runtime-facing identity metadata for an agent graph."""

    agent_key: str
    display_name: str
    role_policy: str
    tool_allowlist: tuple[str, ...]
    output_artifacts: tuple[str, ...]


_ROLE_POLICIES = {
    "quant_research_supervisor": (
        "Coordinate specialist handoffs and synthesize research recommendations without forging specialist artifacts."
    ),
    "data_agent": (
        "Produce bounded dataset manifests, data-quality reports, and explicit load evidence without strategy verdicts."
    ),
    "math_coder_agent": (
        "Produce deterministic indicator and statistical-test artifacts without fetching data or making verdicts."
    ),
    "ml_agent": (
        "Produce feature, model, prediction, and drift artifacts without final trading recommendations."
    ),
    "hypothesis_agent": (
        "Produce falsifiable hypothesis cards without running backtests or deciding whether ideas passed."
    ),
    "evaluation_agent": (
        "Produce skeptical critique reports without creating hypotheses or mutating data."
    ),
    "adversarial_agent": (
        "Produce robustness reports without promotion decisions or live-trading mutation."
    ),
}


def build_agent_identity(agent_key_or_name: str) -> AgentIdentity:
    """Build static identity metadata from a registered agent definition."""
    definition = get_agent_definition(agent_key_or_name)
    return _identity_from_definition(definition)


def _identity_from_definition(definition: AgentDefinition) -> AgentIdentity:
    return AgentIdentity(
        agent_key=definition.key,
        display_name=definition.display_name,
        role_policy=_ROLE_POLICIES[definition.key],
        tool_allowlist=definition.initial_tools,
        output_artifacts=definition.owned_artifacts,
    )
