"""Expose process-isolated adapters for bounded research execution.

These adapters place enforceable wall-clock and process boundaries around
canonical services that cannot be safely interrupted in-process. Isolation does
not change artifact authority or bypass normal validation and persistence paths.
"""

from .postgres_optimization import PostgresBacktestOptimizationTrialExecutor

__all__ = ["PostgresBacktestOptimizationTrialExecutor"]
