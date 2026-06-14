"""Agent and tool ownership metadata for research workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class AgentDefinition:
    """Static definition for one research-agent identity.

    Attributes:
        key: Stable machine-readable agent key.
        display_name: Human-readable agent name used in envelopes and docs.
        mission: Short description of the agent's responsibility boundary.
        owned_artifacts: Artifact filenames or types owned by the agent.
        initial_tools: Tool names initially allowlisted for the agent.
    """

    key: str
    display_name: str
    mission: str
    owned_artifacts: tuple[str, ...]
    initial_tools: tuple[str, ...]


READ_ONLY_SUPPORT_TOOLS = ("mcp_health", "mcp_get_config")

DATA_AGENT_TOOLS = (
    "data_discover_symbols",
    "data_get_inventory",
    "data_summarize_quality",
    "data_ensure_loaded",
)

QUANTITATIVE_METHODS_TOOLS = (
    "knowledge_register_source",
    "knowledge_ingest_documents",
    "knowledge_get_ingestion_status",
    "knowledge_list_sources",
    "knowledge_search_methods",
    "knowledge_retrieve_evidence",
    "knowledge_create_method_card_draft",
    "knowledge_publish_method_card",
    "knowledge_validate_citations",
    "math_list_method_contracts",
    "math_validate_method_contract",
)

QUANTITATIVE_METHODS_COMPATIBILITY_TOOLS = (
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
            "symbol_discovery_report.json",
            "dataset_manifest.json",
            "data_quality_report.json",
            "load_result_envelope.json",
        ),
        initial_tools=(*READ_ONLY_SUPPORT_TOOLS, *DATA_AGENT_TOOLS),
    ),
    AgentDefinition(
        key="quant_methods_agent",
        display_name="Quantitative Methods Agent",
        mission=(
            "Produce auditable deterministic method contracts, validation reports, diagnostics, and statistical "
            "inference artifacts."
        ),
        owned_artifacts=(
            "indicator_contract.json",
            "statistical_test_contract.json",
            "indicator_validation_report.json",
            "signal_diagnostic_report.json",
            "multiple_testing_report.json",
            "cxx_kernel_manifest.json",
            "python_cpp_parity_report.json",
            "method_package_manifest.json",
            "statistical_test_report.json",
            "knowledge_source_manifest.json",
            "knowledge_ingestion_report.json",
            "knowledge_chunk_manifest.json",
            "knowledge_embedding_manifest.json",
            "method_card_draft.json",
            "method_card.json",
            "evidence_retrieval_report.json",
            "citation_validation_report.json",
        ),
        initial_tools=(*READ_ONLY_SUPPORT_TOOLS, *QUANTITATIVE_METHODS_TOOLS),
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
    """Normalize an agent lookup string.

    Args:
        value: Agent key or display name.

    Returns:
        Lowercase underscore-separated lookup key.
    """
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text


_AGENTS_BY_KEY: Mapping[str, AgentDefinition] = {agent.key: agent for agent in AGENT_DEFINITIONS}
_AGENT_ALIASES: Mapping[str, str] = {
    **{agent.key: agent.key for agent in AGENT_DEFINITIONS},
    **{_normalize_lookup(agent.display_name): agent.key for agent in AGENT_DEFINITIONS},
    "math_coder_agent": "quant_methods_agent",
    "math_coder": "quant_methods_agent",
}

TOOL_OWNER_BY_NAME: Mapping[str, str] = {
    **{tool: "Data Agent" for tool in DATA_AGENT_TOOLS},
    **{tool: "Quantitative Methods Agent" for tool in QUANTITATIVE_METHODS_TOOLS},
    **{tool: "Quantitative Methods Agent" for tool in QUANTITATIVE_METHODS_COMPATIBILITY_TOOLS},
    **{tool: "ML Agent" for tool in ML_AGENT_TOOLS},
    **{tool: "Hypothesis Agent" for tool in HYPOTHESIS_AGENT_TOOLS},
    **{tool: "Quant Research Supervisor Agent" for tool in QUANT_RESEARCH_SUPERVISOR_TOOLS},
    **{tool: "Evaluation Agent" for tool in EVALUATION_AGENT_TOOLS},
    **{tool: "Adversarial Agent" for tool in ADVERSARIAL_AGENT_TOOLS},
}


def get_agent_definition(agent_key_or_name: str) -> AgentDefinition:
    """Return a registered agent definition by key or display name.

    Args:
        agent_key_or_name: Stable key or display name for a registered agent.

    Returns:
        Matching agent definition.

    Raises:
        KeyError: If no registered agent matches the supplied value.
    """
    lookup = _normalize_lookup(agent_key_or_name)
    try:
        return _AGENTS_BY_KEY[_AGENT_ALIASES[lookup]]
    except KeyError as exc:
        raise KeyError(f"Unknown research agent: {agent_key_or_name}") from exc


def agent_owner_for_tool(tool_name: str) -> str:
    """Return the display name of the agent that owns a planned tool.

    Args:
        tool_name: Stable tool command identifier.

    Returns:
        Display name of the owning agent.

    Raises:
        KeyError: If the tool name is not registered.
    """
    try:
        return TOOL_OWNER_BY_NAME[tool_name]
    except KeyError as exc:
        raise KeyError(f"Unknown research tool: {tool_name}") from exc
