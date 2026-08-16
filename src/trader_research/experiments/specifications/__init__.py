"""Build and validate immutable strategy, risk-stack, and backtest contracts.

Specifications bind admitted behavior to normalized configuration and, at the
backtest boundary, exact Data evidence and execution assumptions. Each create
operation is paired with independent validation before execution is allowed.
"""

from .backtest import (
    create_backtest_specification,
    load_passed_backtest_specification,
    validate_backtest_specification,
)
from .risk import (
    create_risk_stack_specification,
    load_passed_risk_stack_specification,
    validate_risk_stack_specification,
)
from .strategy import (
    create_strategy_specification,
    load_passed_strategy_specification,
    validate_strategy_specification,
)

__all__ = [
    "create_backtest_specification",
    "create_risk_stack_specification",
    "create_strategy_specification",
    "load_passed_backtest_specification",
    "load_passed_risk_stack_specification",
    "load_passed_strategy_specification",
    "validate_backtest_specification",
    "validate_risk_stack_specification",
    "validate_strategy_specification",
]
