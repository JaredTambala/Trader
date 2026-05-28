"""Agent and tool ownership metadata for research workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class AgentDefinition:
    """Static definition for one research-agent identity."""

    key: str
    display_name: str
    mission: str
    owned_artifacts: tuple[str, ...]
    initial_tools: tuple[str, ...]


READ_ONLY_SUPPORT_TOOLS = ("mcp_health", "mcp_get_config")

DATA_AGENT_TOOLS = (
    "data_get_inventory",
    "data_summarize_quality",
    "data_ensure_loaded",
)

MATH_CODER_TOOLS = (
    "math_list_indicator_contracts",
    "math_validate_indicator_contract",
)

ML_AGENT_TOOLS = (
    "ml_create_feature_manifest",
    "ml_summarize_model_artifact",
)

HYPOTHESIS_AGENT_TOOLS = ("hypothesis_create_card",)

QUANT_RESEARCH_SUPERVISOR_TOOLS = (
    "research_create_plan",
    "research_list_strategy_templates",
    "research_validate_strategy_candidate",
    "research_run_backtest",
    "research_get_backtest_results",
    "research_analyze_return_attribution",
    "research_generate_recommendation",
    "research_run_experiment",
)

EVALUATION_AGENT_TOOLS = ("evaluation_generate_report",)

ADVERSARIAL_AGENT_TOOLS = ("adversarial_run_robustness",)


AGENT_DEFINITIONS: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        key="quant_research_supervisor",
        display_name="Quant Research Supervisor Agent",
        mission="Coordinate research workflows and synthesize specialist-owned evidence.",
        owned_artifacts=(
            "experiment_plan.json",
            "research_suite.json",
            "comparison_report.json",
            "recommendation_report.json",
        ),
        initial_tools=QUANT_RESEARCH_SUPERVISOR_TOOLS,
    ),
    AgentDefinition(
        key="data_agent",
        display_name="Data Agent",
        mission="Produce trustworthy bounded market-data manifests and quality evidence.",
        owned_artifacts=(
            "dataset_manifest.json",
            "data_quality_report.json",
            "load_result_envelope.json",
        ),
        initial_tools=(*READ_ONLY_SUPPORT_TOOLS, *DATA_AGENT_TOOLS),
    ),
    AgentDefinition(
        key="math_coder_agent",
        display_name="Math Coder Agent",
        mission="Produce auditable deterministic indicator and statistical-test artifacts.",
        owned_artifacts=(
            "indicator_metadata.json",
            "indicator_test_report.json",
            "statistical_test_report.json",
        ),
        initial_tools=MATH_CODER_TOOLS,
    ),
    AgentDefinition(
        key="ml_agent",
        display_name="ML Agent",
        mission="Produce versioned feature, model, prediction, and drift artifacts.",
        owned_artifacts=(
            "feature_dataset_manifest.json",
            "model_card.json",
            "prediction_artifact.json",
            "drift_report.json",
        ),
        initial_tools=ML_AGENT_TOOLS,
    ),
    AgentDefinition(
        key="hypothesis_agent",
        display_name="Hypothesis Agent",
        mission="Produce explicit falsifiable strategy hypothesis cards.",
        owned_artifacts=("hypothesis_card.json",),
        initial_tools=HYPOTHESIS_AGENT_TOOLS,
    ),
    AgentDefinition(
        key="evaluation_agent",
        display_name="Evaluation Agent",
        mission="Produce skeptical critique artifacts from research evidence.",
        owned_artifacts=("evaluation_report.json",),
        initial_tools=EVALUATION_AGENT_TOOLS,
    ),
    AgentDefinition(
        key="adversarial_agent",
        display_name="Adversarial Agent",
        mission="Produce robustness and stress-test artifacts for candidate strategies.",
        owned_artifacts=("robustness_report.json",),
        initial_tools=ADVERSARIAL_AGENT_TOOLS,
    ),
)


def _normalize_lookup(value: str) -> str:
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text


_AGENTS_BY_KEY: Mapping[str, AgentDefinition] = {agent.key: agent for agent in AGENT_DEFINITIONS}
_AGENT_ALIASES: Mapping[str, str] = {
    **{agent.key: agent.key for agent in AGENT_DEFINITIONS},
    **{_normalize_lookup(agent.display_name): agent.key for agent in AGENT_DEFINITIONS},
}

TOOL_OWNER_BY_NAME: Mapping[str, str] = {
    **{tool: "Data Agent" for tool in DATA_AGENT_TOOLS},
    **{tool: "Math Coder Agent" for tool in MATH_CODER_TOOLS},
    **{tool: "ML Agent" for tool in ML_AGENT_TOOLS},
    **{tool: "Hypothesis Agent" for tool in HYPOTHESIS_AGENT_TOOLS},
    **{tool: "Quant Research Supervisor Agent" for tool in QUANT_RESEARCH_SUPERVISOR_TOOLS},
    **{tool: "Evaluation Agent" for tool in EVALUATION_AGENT_TOOLS},
    **{tool: "Adversarial Agent" for tool in ADVERSARIAL_AGENT_TOOLS},
}


def get_agent_definition(agent_key_or_name: str) -> AgentDefinition:
    """Return a registered agent definition by key or display name."""
    lookup = _normalize_lookup(agent_key_or_name)
    try:
        return _AGENTS_BY_KEY[_AGENT_ALIASES[lookup]]
    except KeyError as exc:
        raise KeyError(f"Unknown research agent: {agent_key_or_name}") from exc


def agent_owner_for_tool(tool_name: str) -> str:
    """Return the display name of the agent that owns a planned tool."""
    try:
        return TOOL_OWNER_BY_NAME[tool_name]
    except KeyError as exc:
        raise KeyError(f"Unknown research tool: {tool_name}") from exc
