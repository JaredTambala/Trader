"""Canonical implementation registration and validation capability."""

from .domain import ImplementationVersion, build_implementation_version, parameter_defaults, validate_parameters
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

__all__ = [
    "ImplementationVersion",
    "build_implementation_version",
    "evaluate_objective",
    "instantiate_risk_manager",
    "instantiate_strategy",
    "load_passed_implementation",
    "parameter_defaults",
    "register_optimization_objective",
    "register_risk_manager_implementation",
    "register_strategy_implementation",
    "validate_optimization_objective",
    "validate_parameters",
    "validate_risk_manager_implementation",
    "validate_strategy_implementation",
]
