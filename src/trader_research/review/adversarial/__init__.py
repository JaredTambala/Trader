"""Expose independent robustness planning and judgment services.

Adversarial services identify assumptions to attack and assess results from
separately executed immutable variants. They preserve baseline evidence and do
not issue the final overall strategy-quality verdict.
"""

from .optimization import (
    create_parameter_optimization_audit_plan,
    generate_parameter_optimization_audit,
)

__all__ = ["create_parameter_optimization_audit_plan", "generate_parameter_optimization_audit"]
