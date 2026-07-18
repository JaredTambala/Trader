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

DATA_GET_INVENTORY_TOOL: Final = "data_get_inventory"
"""Tool name for read-only Data Agent inventory."""

DATA_DISCOVER_SYMBOLS_TOOL: Final = "data_discover_symbols"
"""Tool name for read-only Data Agent symbol discovery."""

DATA_SUMMARIZE_QUALITY_TOOL: Final = "data_summarize_quality"
"""Tool name for read-only Data Agent data-quality summaries."""

DATA_ENSURE_LOADED_TOOL: Final = "data_ensure_loaded"
"""Tool name for explicit Data Agent data inspection/loading."""

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
"""Tool name for extracting rich methodology fields from a candidate."""

KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL: Final = (
    "knowledge_validate_methodology_candidate"
)
"""Tool name for validating extracted methodology candidates before draft-card creation."""

KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT_TOOL: Final = (
    "knowledge_create_rich_method_card_draft"
)
"""Tool name for promoting a validated methodology candidate into a rich method-card draft."""

KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL: Final = "knowledge_create_method_card_draft"
"""Tool name for creating draft method cards from validated evidence."""

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
)
"""Data Agent tool names exposed by the MCP server."""

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
    KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT_TOOL,
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
}
"""Descriptions for Data Agent tools exposed by the MCP server."""

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
        "Extract rich nullable methodology fields from a role-labeled evidence packet or source-backed candidate."
    ),
    KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE_TOOL: (
        "Validate field-level evidence for a rich methodology candidate."
    ),
    KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT_TOOL: (
        "Create a rich method-card draft from a passed methodology-candidate validation report."
    ),
    KNOWLEDGE_CREATE_METHOD_CARD_DRAFT_TOOL: (
        "Create a legacy/projection draft method card; canonical methodology cards use rich validated drafts."
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
    "knowledge_tools_registered": True,
    "methodology_candidate_tools_registered": True,
    "math_method_tools_registered": True,
    "implementation_registry_tools_registered": True,
    "canonical_specification_tools_registered": True,
    "backtest_tools_registered": True,
    "optimization_tools_registered": True,
    "experiment_tracking_projection_tools_registered": True,
    "evaluation_tools_registered": True,
    "adversarial_tools_registered": True,
}
"""Safety flags for registered and intentionally unregistered tool families."""
