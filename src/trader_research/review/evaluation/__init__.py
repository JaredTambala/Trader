"""Expose Evaluation-owned services over canonical research evidence.

Evaluation independently loads experiment and review artifacts, applies declared
assessment rules, and persists bounded conclusions. It cannot repair protocols,
execute experiments, or replace missing evidence with narrative judgment.
"""

from .optimization import generate_parameter_optimization_report

__all__ = ["generate_parameter_optimization_report"]
