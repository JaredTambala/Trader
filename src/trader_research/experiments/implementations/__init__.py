"""Register and validate executable research implementations.

This facade exposes content-addressed strategy, risk-manager, and optimization
objective admission. Registration records supplied source; validation performs
the safety, interface, and bounded fixture checks required before execution.
"""

from .domain import (
    ImplementationVersion,
    build_implementation_version,
    parameter_defaults,
    validate_parameters,
)
from .runtime import evaluate_objective, instantiate_risk_manager, instantiate_strategy
from .services import (
    load_passed_implementation,
    register_optimization_objective,
    register_risk_manager_implementation,
    register_strategy_implementation,
    validate_optimization_objective,
    validate_risk_manager_implementation,
    validate_strategy_implementation,
)
from .templates import (
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES,
    RESEARCH_LIST_STRATEGY_TEMPLATES,
    SUPPORTED_RISK_MANAGER_FAMILIES,
    SUPPORTED_STRATEGY_FAMILIES,
    list_risk_manager_templates,
    list_strategy_templates,
    normalize_strategy_family,
)

__all__ = [
    "ImplementationVersion",
    "build_implementation_version",
    "evaluate_objective",
    "instantiate_risk_manager",
    "instantiate_strategy",
    "load_passed_implementation",
    "parameter_defaults",
    "RESEARCH_LIST_RISK_MANAGER_TEMPLATES",
    "RESEARCH_LIST_STRATEGY_TEMPLATES",
    "register_optimization_objective",
    "register_risk_manager_implementation",
    "register_strategy_implementation",
    "SUPPORTED_RISK_MANAGER_FAMILIES",
    "SUPPORTED_STRATEGY_FAMILIES",
    "validate_optimization_objective",
    "validate_parameters",
    "validate_risk_manager_implementation",
    "validate_strategy_implementation",
    "list_risk_manager_templates",
    "list_strategy_templates",
    "normalize_strategy_family",
]
