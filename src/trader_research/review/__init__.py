"""Expose independent Evaluation and Adversarial review capabilities.

Review services consume canonical experiment evidence, declare immutable attacks,
and persist skeptical findings under Review ownership. They do not execute
variants, mutate baselines, select optimizer parameters, or route workflows.
"""

from .adversarial import (
    create_parameter_optimization_audit_plan,
    generate_parameter_optimization_audit,
)
from .evaluation import generate_parameter_optimization_report

__all__ = [
    "create_parameter_optimization_audit_plan",
    "generate_parameter_optimization_audit",
    "generate_parameter_optimization_report",
]
