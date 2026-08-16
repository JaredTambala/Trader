"""Declare stable operation identifiers for optimization artifact writers.

These constants are persisted as producer metadata and shared with MCP
adapters. Keeping them dependency-free prevents transport naming from leaking
into the optimization domain logic.
"""

RESEARCH_GET_OPTIMIZER_RUNTIME = "research_get_optimizer_runtime"
RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN = "research_create_parameter_optimization_plan"
RESEARCH_RUN_PARAMETER_OPTIMIZATION = "research_run_parameter_optimization"
RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS = "research_get_parameter_optimization_results"
RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS = "research_run_parameter_optimization_variants"
