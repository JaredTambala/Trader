"""Dependency-free agent identity metadata for future LangGraph graphs."""

from __future__ import annotations

from dataclasses import dataclass

from trader_research.governance import AgentDefinition, get_agent_definition


@dataclass(frozen=True)
class AgentIdentity:
    """Runtime-facing identity metadata for an agent graph.

    Attributes:
        agent_key: Stable machine-readable agent key.
        display_name: Human-readable agent name used in envelopes and docs.
        role_policy: Short policy describing the agent's decision boundary.
        tool_allowlist: Tool names the agent identity may call initially.
        output_artifacts: Artifact filenames or types the agent may produce.
    """

    agent_key: str
    display_name: str
    role_policy: str
    tool_allowlist: tuple[str, ...]
    output_artifacts: tuple[str, ...]


_ROLE_POLICIES = {
    "quant_research_supervisor": (
        "Coordinate specialist handoffs, reproducible experiments, and deferred walk-forward optimization runs without "
        "forging specialist artifacts or issuing evaluation verdicts."
    ),
    "data_agent": (
        "Produce bounded dataset manifests, data-quality reports, and explicit load evidence without strategy verdicts."
    ),
    "experiment_design_agent": (
        "Propose explicit reproducible experiment protocols and expose every "
        "material assumption for operator approval without executing, approving, "
        "or revising experiments after results."
    ),
    "quant_methods_agent": (
        "Produce source-backed deterministic method, diagnostic, and statistical-inference artifacts without fetching "
        "market data or making verdicts."
    ),
    "ml_agent": (
        "Coordinate point-in-time feature, training, MLflow lineage, model evaluation, deployment-evidence, prediction, "
        "and drift tools without final trading recommendations, ungated alias promotion, or live-trading mutation."
    ),
    "hypothesis_agent": (
        "Produce falsifiable hypothesis cards without running backtests or deciding whether ideas passed."
    ),
    "evaluation_agent": (
        "Produce skeptical critique and stitched out-of-sample walk-forward reports without creating hypotheses, "
        "changing fold selections, or mutating data."
    ),
    "adversarial_agent": (
        "Produce robustness reports and independently audit walk-forward procedures without changing selections, "
        "making promotion decisions, or mutating live trading."
    ),
}


def build_agent_identity(agent_key_or_name: str) -> AgentIdentity:
    """Build static identity metadata from a registered agent definition.

    Args:
        agent_key_or_name: Stable key or display name for a registered agent.

    Returns:
        Runtime-facing identity metadata for the requested agent.

    Raises:
        KeyError: If no registered agent matches the supplied value.
    """
    definition = get_agent_definition(agent_key_or_name)
    return _identity_from_definition(definition)


def _identity_from_definition(definition: AgentDefinition) -> AgentIdentity:
    """Build identity metadata from a registered definition.

    Args:
        definition: Registered agent definition.

    Returns:
        Runtime-facing identity metadata.
    """
    return AgentIdentity(
        agent_key=definition.key,
        display_name=definition.display_name,
        role_policy=_ROLE_POLICIES[definition.key],
        tool_allowlist=definition.initial_tools,
        output_artifacts=definition.produced_artifacts,
    )
