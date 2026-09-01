"""Declare research decision authority and tool-attribution metadata.

The registry distinguishes exclusive domain decisions from transport allowlists,
artifact producers, requesting workflows, and runtime actors. Lookup helpers
fail closed so an unknown role or decision cannot acquire authority by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from trader_research.foundation import (
    DATA_DOMAIN_OWNER,
    EXPERIMENTS_DOMAIN_OWNER,
    KNOWLEDGE_METHODOLOGY_DOMAIN_OWNER,
    ML_DOMAIN_OWNER,
    ORCHESTRATION_DOMAIN_OWNER,
    REVIEW_DOMAIN_OWNER,
)


@dataclass(frozen=True)
class AgentDefinition:
    """Static definition for one research-agent identity.

    Attributes:
        key: Stable machine-readable agent key.
        display_name: Human-readable agent name used in results and docs.
        mission: Short description of the agent's responsibility boundary.
        produced_artifacts: Artifact filenames or types the agent's tools may produce.
        initial_tools: Tool names initially allowlisted for the agent.
    """

    key: str
    display_name: str
    mission: str
    produced_artifacts: tuple[str, ...]
    initial_tools: tuple[str, ...]


@dataclass(frozen=True)
class DecisionAuthority:
    """Approved research decision boundary for a target orchestration role."""

    key: str
    display_name: str
    decision: str
    artifact_domains: tuple[str, ...]
    prohibited_authority: tuple[str, ...]
    optional_producer: bool = False


READ_ONLY_SUPPORT_TOOLS = ("mcp_health", "mcp_get_config")

DATA_AGENT_TOOLS = (
    "data_discover_symbols",
    "data_get_inventory",
    "data_summarize_quality",
    "data_ensure_loaded",
    "data_create_research_snapshot",
)

STRATEGY_ENGINEERING_TOOLS = (
    "research_list_strategy_templates",
    "research_list_risk_manager_templates",
    "research_search_implementations",
    "research_get_implementation",
    "research_compare_implementation",
    "coding_create_workspace",
    "coding_get_workspace",
    "coding_search_repository",
    "coding_read_repository_file",
    "coding_write_candidate_file",
    "coding_read_candidate_file",
    "coding_resolve_dependencies",
    "coding_run_check",
    "coding_package_candidate",
    "coding_destroy_workspace",
    "research_register_strategy_implementation",
    "research_validate_strategy_implementation",
    "research_register_risk_manager_implementation",
    "research_validate_risk_manager_implementation",
)

EXPERIMENT_DESIGN_AGENT_TOOLS = (
    "research_create_experiment_protocol_proposal",
)

QUANTITATIVE_METHODS_TOOLS = (
    "knowledge_register_source",
    "knowledge_ingest_documents",
    "knowledge_get_ingestion_status",
    "knowledge_list_sources",
    "knowledge_search_methods",
    "knowledge_list_method_card_sets",
    "knowledge_get_method_card_set",
    "knowledge_retrieve_evidence",
    "knowledge_get_evidence_chunks",
    "knowledge_discover_methodology_candidates",
    "knowledge_assemble_methodology_evidence",
    "knowledge_extract_methodology_fields",
    "knowledge_validate_methodology_candidate",
    "knowledge_create_method_card_draft",
    "knowledge_publish_method_card",
    "knowledge_update_method_card_status",
    "knowledge_validate_citations",
    "math_list_method_contracts",
    "math_validate_method_contract",
    "math_register_method_implementation",
    "math_run_indicator_fixtures",
    "math_run_signal_fixtures",
    "math_generate_python_method",
    "math_run_signal_diagnostics",
    "math_run_multiple_testing_report",
    "math_generate_cpp_kernel",
    "math_compile_kernel",
    "math_package_method_artifact",
    "research_register_optimization_objective",
    "research_validate_optimization_objective",
)

QUANTITATIVE_METHODS_COMPATIBILITY_TOOLS = (
    "math_list_indicator_contracts",
    "math_validate_indicator_contract",
)

ML_AGENT_TOOLS = (
    "ml_get_runtime",
    "ml_health",
    "ml_list_training_experiments",
    "ml_create_feature_set",
    "ml_validate_feature_set",
    "ml_create_training_dataset",
    "ml_create_time_series_split_plan",
    "ml_register_training_pipeline",
    "ml_validate_training_pipeline",
    "ml_create_training_spec",
    "ml_run_training",
    "ml_get_training_run",
    "ml_reconcile_mlflow_run",
    "ml_evaluate_model",
    "ml_compare_model_versions",
    "ml_register_model_version",
    "ml_get_model_version",
    "ml_list_model_versions",
    "ml_resolve_model_alias",
    "ml_assign_model_alias",
    "ml_create_deployment_manifest",
    "ml_validate_deployment",
    "ml_summarize_predictions",
    "ml_compute_drift_report",
)

HYPOTHESIS_AGENT_TOOLS = ("hypothesis_create_card",)

QUANT_RESEARCH_SUPERVISOR_TOOLS = (
    "research_create_plan",
    "research_get_backtest_results",
    "research_compare_backtest_results",
    "research_analyze_return_attribution",
    "research_generate_recommendation",
    "research_create_walk_forward_plan",
    "research_run_walk_forward_optimization",
    "research_get_walk_forward_results",
    "research_create_strategy_specification",
    "research_validate_strategy_specification",
    "research_create_risk_stack_specification",
    "research_validate_risk_stack_specification",
    "research_create_backtest_specification",
    "research_validate_backtest_specification",
    "research_run_backtest_specification",
    "research_get_optimizer_runtime",
    "research_create_parameter_optimization_plan",
    "research_run_parameter_optimization",
    "research_get_parameter_optimization_results",
    "research_run_parameter_optimization_variants",
    "research_project_experiment_tracking",
    "research_register_experiment_workflow",
    "research_record_workflow_outcome",
)

EVALUATION_AGENT_TOOLS = (
    "evaluation_generate_report",
    "evaluation_generate_walk_forward_report",
    "evaluation_generate_parameter_optimization_report",
)

ADVERSARIAL_AGENT_TOOLS = (
    "adversarial_run_robustness",
    "adversarial_audit_walk_forward",
    "adversarial_create_parameter_optimization_audit_plan",
    "adversarial_generate_parameter_optimization_audit",
)


AGENT_DEFINITIONS: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        key="quant_research_supervisor",
        display_name="Quant Research Supervisor Agent",
        mission="Coordinate research workflows and synthesize specialist-owned evidence.",
        produced_artifacts=(
            "experiment_plan.json",
            "research_suite.json",
            "comparison_report.json",
            "recommendation_report.json",
            "walk_forward_optimization_plan.json",
            "walk_forward_optimization_run.json",
            "strategy_specification.json",
            "strategy_specification_validation_report.json",
            "risk_stack_specification.json",
            "risk_stack_specification_validation_report.json",
            "backtest_specification.json",
            "backtest_specification_validation_report.json",
            "backtest_run.json",
            "parameter_optimization_plan.json",
            "parameter_optimization_run.json",
            "parameter_optimization_trial.json",
            "experiment_tracking_projection_report.json",
        ),
        initial_tools=QUANT_RESEARCH_SUPERVISOR_TOOLS,
    ),
    AgentDefinition(
        key="data_agent",
        display_name="Data Agent",
        mission="Produce trustworthy bounded market-data manifests and quality evidence.",
        produced_artifacts=(
            "symbol_discovery_report.json",
            "dataset_manifest.json",
            "data_quality_report.json",
            "load_result_result.json",
        ),
        initial_tools=(*READ_ONLY_SUPPORT_TOOLS, *DATA_AGENT_TOOLS),
    ),
    AgentDefinition(
        key="strategy_engineering_agent",
        display_name="Strategy Engineering Agent",
        mission=(
            "Compare, construct, test, package, and submit inert strategy or "
            "risk candidates without efficacy or trading authority."
        ),
        produced_artifacts=(
            "implementation_compatibility_report.json",
            "coding_candidate_package.json",
            "implementation_version.json",
            "implementation_validation_report.json",
        ),
        initial_tools=(*READ_ONLY_SUPPORT_TOOLS, *STRATEGY_ENGINEERING_TOOLS),
    ),
    AgentDefinition(
        key="experiment_design_agent",
        display_name="Experiment Design Agent",
        mission=(
            "Propose fair, reproducible, approval-aware experiment protocols "
            "without executing or approving them."
        ),
        produced_artifacts=("experiment_protocol_proposal.json",),
        initial_tools=(
            *READ_ONLY_SUPPORT_TOOLS,
            *EXPERIMENT_DESIGN_AGENT_TOOLS,
        ),
    ),
    AgentDefinition(
        key="quant_methods_agent",
        display_name="Quantitative Methods Agent",
        mission=(
            "Produce auditable deterministic method contracts, validation reports, diagnostics, and statistical "
            "inference artifacts."
        ),
        produced_artifacts=(
            "indicator_contract.json",
            "statistical_test_contract.json",
            "method_implementation_manifest.json",
            "indicator_validation_report.json",
            "signal_implementation_validation_report.json",
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
            "methodology_candidate.json",
            "methodology_evidence_packet.json",
            "methodology_field_extraction_report.json",
            "methodology_candidate_validation_report.json",
            "method_card_draft.json",
            "method_card.json",
            "evidence_retrieval_report.json",
            "evidence_chunk_dereference_report.json",
            "citation_validation_report.json",
            "optimization_objective_implementation.json",
            "optimization_objective_validation_report.json",
        ),
        initial_tools=(*READ_ONLY_SUPPORT_TOOLS, *QUANTITATIVE_METHODS_TOOLS),
    ),
    AgentDefinition(
        key="ml_agent",
        display_name="ML Agent",
        mission=(
            "Coordinate point-in-time feature engineering, fitting, MLflow model lineage, deployment evidence, "
            "predictions, and drift without live-trading authority."
        ),
        produced_artifacts=(
            "ml_feature_set_spec.json",
            "ml_feature_set_validation_report.json",
            "ml_training_dataset_manifest.json",
            "ml_time_series_split_plan.json",
            "ml_training_pipeline_manifest.json",
            "ml_training_pipeline_validation_report.json",
            "ml_training_spec.json",
            "mlflow_run_ref.json",
            "ml_model_evaluation_report.json",
            "ml_model_version_ref.json",
            "ml_model_promotion_report.json",
            "ml_deployment_manifest.json",
            "ml_deployment_validation_report.json",
            "ml_prediction_artifact.json",
            "ml_drift_report.json",
        ),
        initial_tools=(*READ_ONLY_SUPPORT_TOOLS, *ML_AGENT_TOOLS),
    ),
    AgentDefinition(
        key="hypothesis_agent",
        display_name="Hypothesis Agent",
        mission="Produce explicit falsifiable strategy hypothesis cards.",
        produced_artifacts=("hypothesis_card.json",),
        initial_tools=HYPOTHESIS_AGENT_TOOLS,
    ),
    AgentDefinition(
        key="evaluation_agent",
        display_name="Evaluation Agent",
        mission="Produce skeptical critique artifacts from research evidence.",
        produced_artifacts=(
            "evaluation_report.json",
            "parameter_optimization_evaluation_report.json",
            "walk_forward_evaluation_report.json",
        ),
        initial_tools=EVALUATION_AGENT_TOOLS,
    ),
    AgentDefinition(
        key="adversarial_agent",
        display_name="Adversarial Agent",
        mission="Produce robustness and stress-test artifacts for candidate strategies.",
        produced_artifacts=(
            "robustness_report.json",
            "parameter_optimization_audit_plan.json",
            "parameter_optimization_robustness_report.json",
            "walk_forward_robustness_report.json",
        ),
        initial_tools=ADVERSARIAL_AGENT_TOOLS,
    ),
)

DECISION_AUTHORITIES: tuple[DecisionAuthority, ...] = (
    DecisionAuthority(
        key="research_coordinator",
        display_name="Research Coordinator",
        decision="Select an approved workflow and resolve its prerequisites.",
        artifact_domains=(ORCHESTRATION_DOMAIN_OWNER,),
        prohibited_authority=(
            "experiment design",
            "experiment execution evidence",
            "robustness findings",
            "research quality verdicts",
        ),
    ),
    DecisionAuthority(
        key="data_agent",
        display_name="Data Agent",
        decision="Determine whether explicit market-data scope is available and fit.",
        artifact_domains=(DATA_DOMAIN_OWNER,),
        prohibited_authority=(
            "strategy logic",
            "optimization design",
            "performance conclusions",
        ),
    ),
    DecisionAuthority(
        key="strategy_engineering_agent",
        display_name="Strategy Engineering Agent",
        decision=(
            "Choose exact reuse, bounded adaptation, or new authorship and "
            "construct an inert candidate from an accepted build contract."
        ),
        artifact_domains=(EXPERIMENTS_DOMAIN_OWNER,),
        prohibited_authority=(
            "quantitative method semantics",
            "implementation admission",
            "experiment design",
            "performance conclusions",
            "deployment and trading",
        ),
    ),
    DecisionAuthority(
        key="experiment_design_agent",
        display_name="Experiment Design Agent",
        decision="Propose a fair, reproducible, approval-aware experiment protocol.",
        artifact_domains=(EXPERIMENTS_DOMAIN_OWNER,),
        prohibited_authority=(
            "experiment execution",
            "post-result protocol changes",
            "strategy quality verdicts",
        ),
    ),
    DecisionAuthority(
        key="robustness_agent",
        display_name="Robustness Agent",
        decision="Define attacks and judge sensitivity evidence from immutable variants.",
        artifact_domains=(REVIEW_DOMAIN_OWNER,),
        prohibited_authority=(
            "variant execution",
            "baseline mutation",
            "overall strategy quality verdicts",
        ),
    ),
    DecisionAuthority(
        key="evaluation_agent",
        display_name="Evaluation Agent",
        decision="Judge what the complete research evidence supports.",
        artifact_domains=(REVIEW_DOMAIN_OWNER,),
        prohibited_authority=(
            "protocol repair",
            "parameter selection",
            "experiment execution",
        ),
    ),
    DecisionAuthority(
        key="quant_methods_agent",
        display_name="Quantitative Methods Agent",
        decision="Produce optional source-backed and computational-method evidence.",
        artifact_domains=(KNOWLEDGE_METHODOLOGY_DOMAIN_OWNER,),
        prohibited_authority=(
            "market-data scope",
            "experiment execution",
            "strategy quality verdicts",
        ),
        optional_producer=True,
    ),
    DecisionAuthority(
        key="ml_agent",
        display_name="ML Agent",
        decision="Produce optional model-lifecycle and predictive evidence.",
        artifact_domains=(ML_DOMAIN_OWNER,),
        prohibited_authority=(
            "trading policy",
            "risk approval",
            "strategy quality verdicts",
        ),
        optional_producer=True,
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
_DECISION_AUTHORITIES_BY_KEY: Mapping[str, DecisionAuthority] = {
    authority.key: authority for authority in DECISION_AUTHORITIES
}
_AGENT_ALIASES: Mapping[str, str] = {
    **{agent.key: agent.key for agent in AGENT_DEFINITIONS},
    **{_normalize_lookup(agent.display_name): agent.key for agent in AGENT_DEFINITIONS},
    "math_coder_agent": "quant_methods_agent",
    "math_coder": "quant_methods_agent",
}

TOOL_STEWARD_BY_NAME: Mapping[str, str] = {
    **{tool: "Data Agent" for tool in DATA_AGENT_TOOLS},
    **{tool: "Strategy Engineering Agent" for tool in STRATEGY_ENGINEERING_TOOLS},
    **{
        tool: "Experiment Design Agent"
        for tool in EXPERIMENT_DESIGN_AGENT_TOOLS
    },
    **{tool: "Quantitative Methods Agent" for tool in QUANTITATIVE_METHODS_TOOLS},
    **{tool: "Quantitative Methods Agent" for tool in QUANTITATIVE_METHODS_COMPATIBILITY_TOOLS},
    **{tool: "ML Agent" for tool in ML_AGENT_TOOLS},
    **{tool: "Hypothesis Agent" for tool in HYPOTHESIS_AGENT_TOOLS},
    **{tool: "Quant Research Supervisor Agent" for tool in QUANT_RESEARCH_SUPERVISOR_TOOLS},
    **{tool: "Evaluation Agent" for tool in EVALUATION_AGENT_TOOLS},
    **{tool: "Adversarial Agent" for tool in ADVERSARIAL_AGENT_TOOLS},
}


def get_decision_authority(authority_key: str) -> DecisionAuthority:
    """Resolve one approved research decision authority by exact stable key.

    Unknown keys raise ``KeyError`` with research-specific context; no default
    authority is inferred from an agent name or tool allowlist.
    """
    try:
        return _DECISION_AUTHORITIES_BY_KEY[authority_key]
    except KeyError as exc:
        raise KeyError(f"Unknown research decision authority: {authority_key}") from exc


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
    """Return the display name of the agent allowlisted for a planned tool.

    Args:
        tool_name: Stable tool command identifier.

    Returns:
        Display name of the allowlisted agent.

    Raises:
        KeyError: If the tool name is not registered.
    """
    try:
        return TOOL_STEWARD_BY_NAME[tool_name]
    except KeyError as exc:
        raise KeyError(f"Unknown research tool: {tool_name}") from exc
