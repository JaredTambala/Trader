"""Static names and identifiers for the MCP research server."""

from __future__ import annotations

from typing import Final


SERVER_NAME: Final = "trader-research-mcp"
"""Name advertised by the MCP server."""

MCP_SERVER_OWNER: Final = "MCP Server"
"""Agent-owner label for MCP support tools."""

MCP_HEALTH_TOOL: Final = "mcp_health"
"""Tool name for MCP server health."""

MCP_CONFIG_TOOL: Final = "mcp_get_config"
"""Tool name for MCP server configuration."""

ML_CREATE_DEPLOYMENT_MANIFEST_TOOL: Final = "ml_create_deployment_manifest"
"""Tool name for creating one immutable raw-inference deployment manifest."""

ML_VALIDATE_DEPLOYMENT_TOOL: Final = "ml_validate_deployment"
"""Tool name for validating deployment lineage and local model parity."""

DATA_GET_INVENTORY_TOOL: Final = "data_get_inventory"
"""Tool name for read-only Data Agent inventory."""

DATA_DISCOVER_SYMBOLS_TOOL: Final = "data_discover_symbols"
"""Tool name for read-only Data Agent symbol discovery."""

DATA_SUMMARIZE_QUALITY_TOOL: Final = "data_summarize_quality"
"""Tool name for read-only Data Agent data-quality summaries."""

DATA_ENSURE_LOADED_TOOL: Final = "data_ensure_loaded"
"""Tool name for explicit Data Agent data inspection/loading."""

DATA_CREATE_RESEARCH_SNAPSHOT_TOOL: Final = "data_create_research_snapshot"
"""Tool name for persisting one exact Data-domain research snapshot."""

KNOWLEDGE_REGISTER_SOURCE_TOOL: Final = "knowledge_register_source"
"""Tool name for registering Quant Methods knowledge sources."""

KNOWLEDGE_INGEST_DOCUMENTS_TOOL: Final = "knowledge_ingest_documents"
"""Tool name for ingesting registered knowledge sources."""

KNOWLEDGE_GET_INGESTION_STATUS_TOOL: Final = "knowledge_get_ingestion_status"
"""Tool name for reporting knowledge ingestion status."""

KNOWLEDGE_LIST_SOURCES_TOOL: Final = "knowledge_list_sources"
"""Tool name for listing registered knowledge sources."""

KNOWLEDGE_SEARCH_METHODS_TOOL: Final = "knowledge_search_methods"
"""Tool name for searching method-card metadata."""

KNOWLEDGE_LIST_METHOD_CARD_SETS_TOOL: Final = "knowledge_list_method_card_sets"
"""Tool name for listing stable method-card set summaries."""

KNOWLEDGE_GET_METHOD_CARD_SET_TOOL: Final = "knowledge_get_method_card_set"
"""Tool name for reading stable method-card set revision history."""

KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL: Final = "knowledge_retrieve_evidence"
"""Tool name for retrieving citeable method evidence."""

KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL: Final = "knowledge_get_evidence_chunks"
"""Tool name for dereferencing citeable evidence chunks into stored text."""

KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL: Final = (
    "knowledge_discover_methodology_candidates"
)
"""Tool name for discovering methodology candidates from ingested source chunks."""

KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL: Final = (
    "knowledge_assemble_methodology_evidence"
)
"""Tool name for assembling role-labeled methodology evidence packets."""

KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL: Final = (
    "knowledge_extract_methodology_fields"
)
"""Tool name for extracting evidence-backed methodology fields from a candidate."""

KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL: Final = (
    "knowledge_validate_methodology_candidate"
)
"""Tool name for validating extracted methodology candidates before draft-card creation."""

KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL: Final = "knowledge_create_method_card_draft"
"""Tool name for promoting a validated methodology candidate into a method-card draft."""

KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL: Final = "knowledge_publish_method_card"
"""Tool name for publishing approved method cards from drafts."""

KNOWLEDGE_UPDATE_METHOD_CARD_STATUS_TOOL: Final = "knowledge_update_method_card_status"
"""Tool name for retiring persisted method cards without deleting audit records."""

KNOWLEDGE_VALIDATE_CITATIONS_TOOL: Final = "knowledge_validate_citations"
"""Tool name for validating method evidence citations."""

MATH_LIST_METHOD_CONTRACTS_TOOL: Final = "math_list_method_contracts"
"""Tool name for listing maintained Quant Methods contracts."""

MATH_VALIDATE_METHOD_CONTRACT_TOOL: Final = "math_validate_method_contract"
"""Tool name for validating one Quant Methods contract."""

MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL: Final = "math_register_method_implementation"
"""Tool name for registering a Python method implementation manifest."""

MATH_RUN_INDICATOR_FIXTURES_TOOL: Final = "math_run_indicator_fixtures"
"""Tool name for running deterministic indicator fixtures."""

MATH_RUN_SIGNAL_FIXTURES_TOOL: Final = "math_run_signal_fixtures"
"""Tool name for running deterministic signal fixtures."""

MATH_GENERATE_PYTHON_METHOD_TOOL: Final = "math_generate_python_method"
"""Tool name for generating and validating a quarantined Python method."""

MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL: Final = "math_run_signal_diagnostics"
"""Tool name for running signal-composition diagnostics."""

MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL: Final = "math_run_multiple_testing_report"
"""Tool name for running multiple-testing controls over signal candidates."""

MATH_GENERATE_CPP_KERNEL_TOOL: Final = "math_generate_cpp_kernel"
"""Tool name for generating template-restricted C++ kernels."""

MATH_COMPILE_KERNEL_TOOL: Final = "math_compile_kernel"
"""Tool name for compiling generated C++ kernels."""

MATH_PACKAGE_METHOD_ARTIFACT_TOOL: Final = "math_package_method_artifact"
"""Tool name for packaging validated Python method implementations for strategy handoff."""

RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL: Final = "research_list_strategy_templates"
"""Tool name for listing maintained strategy templates."""

RESEARCH_SEARCH_IMPLEMENTATIONS_TOOL: Final = "research_search_implementations"
"""Tool name for searching maintained and admitted implementations."""

RESEARCH_GET_IMPLEMENTATION_TOOL: Final = "research_get_implementation"
"""Tool name for resolving one exact implementation version."""

RESEARCH_COMPARE_IMPLEMENTATION_TOOL: Final = "research_compare_implementation"
"""Tool name for field-level build-contract compatibility evidence."""

CODING_CREATE_WORKSPACE_TOOL: Final = "coding_create_workspace"
"""Tool name for provisioning one isolated candidate-attempt workspace."""

CODING_GET_WORKSPACE_TOOL: Final = "coding_get_workspace"
"""Tool name for reading bounded workspace status."""

CODING_SEARCH_REPOSITORY_TOOL: Final = "coding_search_repository"
"""Tool name for bounded search of the pinned Trader snapshot."""

CODING_READ_REPOSITORY_FILE_TOOL: Final = "coding_read_repository_file"
"""Tool name for bounded reads from the pinned Trader snapshot."""

CODING_WRITE_CANDIDATE_FILE_TOOL: Final = "coding_write_candidate_file"
"""Tool name for writing one bounded candidate-workspace file."""

CODING_READ_CANDIDATE_FILE_TOOL: Final = "coding_read_candidate_file"
"""Tool name for reading one bounded candidate-workspace file."""

CODING_RESOLVE_DEPENDENCIES_TOOL: Final = "coding_resolve_dependencies"
"""Tool name for validating dependencies against the pinned image policy."""

CODING_RUN_CHECK_TOOL: Final = "coding_run_check"
"""Tool name for running one allowlisted isolated candidate check."""

CODING_PACKAGE_CANDIDATE_TOOL: Final = "coding_package_candidate"
"""Tool name for packaging exact inert candidate source and tests."""

CODING_DESTROY_WORKSPACE_TOOL: Final = "coding_destroy_workspace"
"""Tool name for removing one exact disposable coding workspace."""

RESEARCH_GET_BACKTEST_RESULTS_TOOL: Final = "research_get_backtest_results"
"""Tool name for reading a canonical persisted backtest run."""

RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL: Final = "research_compare_backtest_results"
"""Tool name for comparing canonical persisted backtest runs."""

RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL: Final = (
    "research_list_risk_manager_templates"
)
"""Tool name for listing maintained risk-manager implementations."""

RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL: Final = (
    "research_register_strategy_implementation"
)
RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL: Final = (
    "research_validate_strategy_implementation"
)
RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL: Final = (
    "research_register_risk_manager_implementation"
)
RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL: Final = (
    "research_validate_risk_manager_implementation"
)
RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL: Final = (
    "research_register_optimization_objective"
)
RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL: Final = (
    "research_validate_optimization_objective"
)
RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL: Final = (
    "research_create_strategy_specification"
)
RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL: Final = (
    "research_validate_strategy_specification"
)
RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL: Final = (
    "research_create_risk_stack_specification"
)
RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL: Final = (
    "research_validate_risk_stack_specification"
)
RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL: Final = (
    "research_create_backtest_specification"
)
RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL: Final = (
    "research_validate_backtest_specification"
)
RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL: Final = "research_run_backtest_specification"
RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL: Final = "research_get_optimizer_runtime"
RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL: Final = (
    "research_create_parameter_optimization_plan"
)
RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL: Final = "research_run_parameter_optimization"
RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL: Final = (
    "research_get_parameter_optimization_results"
)
RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL: Final = (
    "research_run_parameter_optimization_variants"
)
RESEARCH_PROJECT_EXPERIMENT_TRACKING_TOOL: Final = (
    "research_project_experiment_tracking"
)
RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL: Final = (
    "research_create_experiment_protocol_proposal"
)
RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL: Final = (
    "research_register_experiment_workflow"
)
RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL: Final = (
    "research_record_workflow_outcome"
)
EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL: Final = (
    "evaluation_generate_parameter_optimization_report"
)
ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL: Final = (
    "adversarial_create_parameter_optimization_audit_plan"
)
ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL: Final = (
    "adversarial_generate_parameter_optimization_audit"
)

SUPPORT_TOOL_NAMES: Final = (MCP_HEALTH_TOOL, MCP_CONFIG_TOOL)
"""Read-only support tool names exposed by the MCP server."""

DATA_TOOL_NAMES: Final = (
    DATA_DISCOVER_SYMBOLS_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    DATA_ENSURE_LOADED_TOOL,
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
)
"""Data Agent tool names exposed by the MCP server."""

CODING_TOOL_NAMES: Final = (
    CODING_CREATE_WORKSPACE_TOOL,
    CODING_GET_WORKSPACE_TOOL,
    CODING_SEARCH_REPOSITORY_TOOL,
    CODING_READ_REPOSITORY_FILE_TOOL,
    CODING_WRITE_CANDIDATE_FILE_TOOL,
    CODING_READ_CANDIDATE_FILE_TOOL,
    CODING_RESOLVE_DEPENDENCIES_TOOL,
    CODING_RUN_CHECK_TOOL,
    CODING_PACKAGE_CANDIDATE_TOOL,
    CODING_DESTROY_WORKSPACE_TOOL,
)
"""Strategy Engineering Coding Workspace tool names."""

EXPERIMENT_DESIGN_TOOL_NAMES: Final = (
    RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL,
)
"""Experiment Design Agent tool names exposed by the MCP server."""

ML_TOOL_NAMES: Final = (
    ML_CREATE_DEPLOYMENT_MANIFEST_TOOL,
    ML_VALIDATE_DEPLOYMENT_TOOL,
)
"""ML Agent deployment tool names exposed by the MCP server."""

KNOWLEDGE_TOOL_NAMES: Final = (
    KNOWLEDGE_REGISTER_SOURCE_TOOL,
    KNOWLEDGE_INGEST_DOCUMENTS_TOOL,
    KNOWLEDGE_GET_INGESTION_STATUS_TOOL,
    KNOWLEDGE_LIST_SOURCES_TOOL,
    KNOWLEDGE_SEARCH_METHODS_TOOL,
    KNOWLEDGE_LIST_METHOD_CARD_SETS_TOOL,
    KNOWLEDGE_GET_METHOD_CARD_SET_TOOL,
    KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL,
    KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL,
    KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL,
    KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL,
    KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL,
    KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL,
    KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL,
    KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL,
    KNOWLEDGE_UPDATE_METHOD_CARD_STATUS_TOOL,
    KNOWLEDGE_VALIDATE_CITATIONS_TOOL,
)
"""Quant Methods knowledge tool names exposed by the MCP server."""

MATH_TOOL_NAMES: Final = (
    MATH_LIST_METHOD_CONTRACTS_TOOL,
    MATH_VALIDATE_METHOD_CONTRACT_TOOL,
    MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL,
    MATH_RUN_INDICATOR_FIXTURES_TOOL,
    MATH_RUN_SIGNAL_FIXTURES_TOOL,
    MATH_GENERATE_PYTHON_METHOD_TOOL,
    MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL,
    MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL,
    MATH_GENERATE_CPP_KERNEL_TOOL,
    MATH_COMPILE_KERNEL_TOOL,
    MATH_PACKAGE_METHOD_ARTIFACT_TOOL,
    RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL,
    RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL,
)
"""Quant Methods math tool names exposed by the MCP server."""

RESEARCH_TOOL_NAMES: Final = (
    RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL,
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL,
    RESEARCH_SEARCH_IMPLEMENTATIONS_TOOL,
    RESEARCH_GET_IMPLEMENTATION_TOOL,
    RESEARCH_COMPARE_IMPLEMENTATION_TOOL,
    RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL,
    RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL,
    RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL,
    RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL,
    RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL,
    RESEARCH_GET_BACKTEST_RESULTS_TOOL,
    RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL,
    RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL,
    RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL,
    RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL,
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL,
    RESEARCH_PROJECT_EXPERIMENT_TRACKING_TOOL,
    RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
    RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
)
"""Quant Research Supervisor tool names exposed by the MCP server."""

EVALUATION_TOOL_NAMES: Final = (EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,)
"""Evaluation Agent tool names exposed by the MCP server."""

ADVERSARIAL_TOOL_NAMES: Final = (
    ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL,
    ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL,
)
"""Adversarial Agent tool names exposed by the MCP server."""

REGISTERED_TOOL_NAMES: Final = (
    *SUPPORT_TOOL_NAMES,
    *DATA_TOOL_NAMES,
    *CODING_TOOL_NAMES,
    *EXPERIMENT_DESIGN_TOOL_NAMES,
    *ML_TOOL_NAMES,
    *KNOWLEDGE_TOOL_NAMES,
    *MATH_TOOL_NAMES,
    *RESEARCH_TOOL_NAMES,
    *EVALUATION_TOOL_NAMES,
    *ADVERSARIAL_TOOL_NAMES,
)
"""All tool names currently exposed by the MCP server."""

SUPPORT_TOOL_DESCRIPTIONS: Final = {
    MCP_HEALTH_TOOL: "Return MCP server health and envelope metadata.",
    MCP_CONFIG_TOOL: "Return current MCP server safety and tool configuration.",
}
"""Descriptions for read-only support tools exposed by the MCP server."""

DATA_TOOL_DESCRIPTIONS: Final = {
    DATA_DISCOVER_SYMBOLS_TOOL: "Discover or validate provider-scoped market-data symbols before data queries.",
    DATA_GET_INVENTORY_TOOL: "Return bounded market-data inventory and dataset manifest.",
    DATA_SUMMARIZE_QUALITY_TOOL: "Return bounded market-data quality gaps and completeness.",
    DATA_ENSURE_LOADED_TOOL: "Inspect, sample-load, or plan bounded market-data loading.",
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL: (
        "Persist one exact inventory and quality pair as canonical Data-domain evidence."
    ),
}
"""Descriptions for Data Agent tools exposed by the MCP server."""

CODING_TOOL_DESCRIPTIONS: Final = {
    CODING_CREATE_WORKSPACE_TOOL: (
        "Create or idempotently reopen one isolated candidate-attempt workspace."
    ),
    CODING_GET_WORKSPACE_TOOL: "Return bounded status for one exact coding workspace.",
    CODING_SEARCH_REPOSITORY_TOOL: (
        "Search bounded text in the pinned read-only Trader repository snapshot."
    ),
    CODING_READ_REPOSITORY_FILE_TOOL: (
        "Read one bounded text file from the pinned Trader repository snapshot."
    ),
    CODING_WRITE_CANDIDATE_FILE_TOOL: (
        "Write one complete bounded file inside an active candidate workspace."
    ),
    CODING_READ_CANDIDATE_FILE_TOOL: (
        "Read one bounded file from an active candidate workspace."
    ),
    CODING_RESOLVE_DEPENDENCIES_TOOL: (
        "Validate requested dependencies against the pinned container policy without installing them."
    ),
    CODING_RUN_CHECK_TOOL: (
        "Run one allowlisted check in the configured networkless isolated container."
    ),
    CODING_PACKAGE_CANDIDATE_TOOL: (
        "Package exact inert candidate source and file hashes without executing code."
    ),
    CODING_DESTROY_WORKSPACE_TOOL: "Destroy one exact disposable candidate workspace.",
}
"""Descriptions for Strategy Engineering Coding Workspace tools."""

EXPERIMENT_DESIGN_TOOL_DESCRIPTIONS: Final = {
    RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL: (
        "Persist one immutable approval-aware protocol proposal over canonical "
        "implementation and Data evidence."
    ),
}
"""Descriptions for Experiment Design Agent tools exposed by the MCP server."""

ML_TOOL_DESCRIPTIONS: Final = {
    ML_CREATE_DEPLOYMENT_MANIFEST_TOOL: (
        "Create an immutable ML-owned manifest for one pinned model, feature set, adapter, and raw output contract."
    ),
    ML_VALIDATE_DEPLOYMENT_TOOL: (
        "Revalidate deployment lineage and execute the configured adapter parity fixture."
    ),
}
"""Descriptions for ML Agent deployment tools exposed by the MCP server."""

KNOWLEDGE_TOOL_DESCRIPTIONS: Final = {
    KNOWLEDGE_REGISTER_SOURCE_TOOL: "Register a local PDF, Markdown, or text source for Quant Methods evidence.",
    KNOWLEDGE_INGEST_DOCUMENTS_TOOL: "Extract, chunk, embed, and index registered Quant Methods knowledge sources.",
    KNOWLEDGE_GET_INGESTION_STATUS_TOOL: "Return knowledge source and ingestion status.",
    KNOWLEDGE_LIST_SOURCES_TOOL: "List registered Quant Methods knowledge sources.",
    KNOWLEDGE_SEARCH_METHODS_TOOL: "Search approved Quant Methods method-card metadata.",
    KNOWLEDGE_LIST_METHOD_CARD_SETS_TOOL: "List stable Quant Methods method-card sets and current pointers.",
    KNOWLEDGE_GET_METHOD_CARD_SET_TOOL: "Return one method-card set with revision history.",
    KNOWLEDGE_RETRIEVE_EVIDENCE_TOOL: "Retrieve citeable Quant Methods evidence chunks.",
    KNOWLEDGE_GET_EVIDENCE_CHUNKS_TOOL: "Dereference citeable Quant Methods evidence chunks into bounded stored text.",
    KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES_TOOL: (
        "Discover source-backed methodology candidates from ingested knowledge chunks."
    ),
    KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE_TOOL: (
        "Assemble role-labeled methodology evidence packets from discovered candidates."
    ),
    KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS_TOOL: (
        "Extract nullable methodology fields from a role-labeled evidence packet or source-backed candidate."
    ),
    KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL: (
        "Validate field-level evidence for a methodology candidate."
    ),
    KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL: (
        "Create an evidence-backed method-card draft from a passed methodology-candidate validation report."
    ),
    KNOWLEDGE_PUBLISH_METHOD_CARD_TOOL: "Publish an approved Quant Methods method card from a draft with explicit approval.",
    KNOWLEDGE_UPDATE_METHOD_CARD_STATUS_TOOL: (
        "Mark a persisted Quant Methods method card rejected or superseded while preserving the stored audit record."
    ),
    KNOWLEDGE_VALIDATE_CITATIONS_TOOL: "Validate source, chunk, locator, and method-card citations.",
}
"""Descriptions for Quant Methods knowledge tools exposed by the MCP server."""

MATH_TOOL_DESCRIPTIONS: Final = {
    MATH_LIST_METHOD_CONTRACTS_TOOL: "List maintained Quantitative Methods method contracts.",
    MATH_VALIDATE_METHOD_CONTRACT_TOOL: "Validate a Quantitative Methods contract against registry and evidence rules.",
    MATH_REGISTER_METHOD_IMPLEMENTATION_TOOL: "Register a citation-backed Python method implementation manifest.",
    MATH_RUN_INDICATOR_FIXTURES_TOOL: "Run deterministic fixtures for a registered Python Indicator implementation.",
    MATH_RUN_SIGNAL_FIXTURES_TOOL: "Run deterministic fixtures for a registered Python Signal implementation.",
    MATH_GENERATE_PYTHON_METHOD_TOOL: "Generate a quarantined Python method draft and validate it with fixtures.",
    MATH_RUN_SIGNAL_DIAGNOSTICS_TOOL: "Run diagnostics for declared signal-composition candidates against forward returns.",
    MATH_RUN_MULTIPLE_TESTING_REPORT_TOOL: "Run Benjamini-Hochberg controls over a declared signal candidate family.",
    MATH_GENERATE_CPP_KERNEL_TOOL: "Generate a template-restricted C++ kernel from a validated Python reference.",
    MATH_COMPILE_KERNEL_TOOL: "Compile a generated C++ kernel in an isolated local build directory.",
    MATH_PACKAGE_METHOD_ARTIFACT_TOOL: "Package a validated Python method implementation for strategy handoff.",
    RESEARCH_REGISTER_OPTIMIZATION_OBJECTIVE_TOOL: (
        "Register a versioned objective that receives only a closed OptimizationObservation."
    ),
    RESEARCH_VALIDATE_OPTIMIZATION_OBJECTIVE_TOOL: (
        "Validate objective safety and deterministic closed-observation behavior."
    ),
}
"""Descriptions for Quant Methods method tools exposed by the MCP server."""

RESEARCH_TOOL_DESCRIPTIONS: Final = {
    RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL: "List neutral metadata for maintained strategy implementations.",
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL: "List neutral metadata for maintained risk implementations.",
    RESEARCH_SEARCH_IMPLEMENTATIONS_TOOL: (
        "Search maintained metadata and exact admitted implementation versions using typed and lexical constraints."
    ),
    RESEARCH_GET_IMPLEMENTATION_TOOL: (
        "Resolve one exact implementation version and matching admission evidence."
    ),
    RESEARCH_COMPARE_IMPLEMENTATION_TOOL: (
        "Produce deterministic field-level compatibility evidence for one build contract and version."
    ),
    RESEARCH_REGISTER_STRATEGY_IMPLEMENTATION_TOOL: "Register a content-addressed strategy implementation version.",
    RESEARCH_VALIDATE_STRATEGY_IMPLEMENTATION_TOOL: "Validate strategy source and deterministic runtime behavior.",
    RESEARCH_REGISTER_RISK_MANAGER_IMPLEMENTATION_TOOL: (
        "Register a content-addressed risk-manager implementation version."
    ),
    RESEARCH_VALIDATE_RISK_MANAGER_IMPLEMENTATION_TOOL: (
        "Validate risk-manager source and deterministic runtime behavior."
    ),
    RESEARCH_CREATE_STRATEGY_SPECIFICATION_TOOL: "Create an immutable data-scope-free strategy specification.",
    RESEARCH_VALIDATE_STRATEGY_SPECIFICATION_TOOL: "Validate a strategy specification and pinned implementation.",
    RESEARCH_CREATE_RISK_STACK_SPECIFICATION_TOOL: "Create an immutable ordered risk-stack specification.",
    RESEARCH_VALIDATE_RISK_STACK_SPECIFICATION_TOOL: "Validate a risk-stack specification and source hashes.",
    RESEARCH_CREATE_BACKTEST_SPECIFICATION_TOOL: "Bind passed behavior to one Data Agent scope and cost policy.",
    RESEARCH_VALIDATE_BACKTEST_SPECIFICATION_TOOL: "Validate a canonical backtest specification and snapshots.",
    RESEARCH_RUN_BACKTEST_SPECIFICATION_TOOL: "Run one passed DB-backed backtest specification.",
    RESEARCH_GET_BACKTEST_RESULTS_TOOL: "Read a canonical DB-backed backtest run.",
    RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL: "Compare canonical DB-backed backtest runs.",
    RESEARCH_GET_OPTIMIZER_RUNTIME_TOOL: "List optimizer profiles without initializing provider state.",
    RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN_TOOL: "Create a provider-neutral bounded optimization plan.",
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_TOOL: "Run or resume a canonical parameter optimization ledger.",
    RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS_TOOL: "Read canonical optimization results without provider access.",
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS_TOOL: "Execute immutable Adversarial-requested optimization variants.",
    RESEARCH_PROJECT_EXPERIMENT_TRACKING_TOOL: "Project canonical run evidence to a configured analytical sink.",
    RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL: (
        "Persist one approved objective, experiment protocol, and ready workflow plan."
    ),
    RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL: (
        "Persist one bounded terminal workflow outcome over canonical evidence refs."
    ),
}
"""Descriptions for Quant Research Supervisor tools exposed by the MCP server."""

EVALUATION_TOOL_DESCRIPTIONS: Final = {
    EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL: (
        "Evaluate an optimization selection on its sealed untouched holdout."
    ),
}
"""Descriptions for Evaluation Agent tools exposed by the MCP server."""

ADVERSARIAL_TOOL_DESCRIPTIONS: Final = {
    ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN_TOOL: (
        "Plan independent attacks against an immutable optimization procedure."
    ),
    ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT_TOOL: (
        "Judge supplied variant and stress evidence without changing the selection."
    ),
}

CAPABILITY_REGISTRATION_FLAGS: Final = {
    "broker_mutating_tools_registered": False,
    "raw_sql_tools_registered": False,
    "symbol_discovery_tools_registered": True,
    "data_loading_tools_registered": True,
    "coding_workspace_tools_registered": True,
    "knowledge_tools_registered": True,
    "methodology_candidate_tools_registered": True,
    "math_method_tools_registered": True,
    "implementation_registry_tools_registered": True,
    "ml_deployment_tools_registered": True,
    "canonical_specification_tools_registered": True,
    "backtest_tools_registered": True,
    "optimization_tools_registered": True,
    "experiment_tracking_projection_tools_registered": True,
    "evaluation_tools_registered": True,
    "adversarial_tools_registered": True,
    "orchestration_tools_registered": True,
    "experiment_design_tools_registered": True,
}
"""Safety flags for registered and intentionally unregistered tool families."""
