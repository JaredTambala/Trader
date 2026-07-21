"""Process-isolated execution adapters for canonical research services."""

from .postgres_optimization import PostgresBacktestOptimizationTrialExecutor

__all__ = ["PostgresBacktestOptimizationTrialExecutor"]
