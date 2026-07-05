"""Backtest execution, result lookup, and comparison services."""

from .services import (
    RESEARCH_COMPARE_BACKTEST_RESULTS,
    RESEARCH_GET_BACKTEST_RESULTS,
    RESEARCH_RUN_BACKTEST,
    BacktestDataScope,
    compare_backtest_results,
    get_backtest_results,
    run_baseline_backtest,
)

__all__ = [
    "RESEARCH_COMPARE_BACKTEST_RESULTS",
    "RESEARCH_GET_BACKTEST_RESULTS",
    "RESEARCH_RUN_BACKTEST",
    "BacktestDataScope",
    "compare_backtest_results",
    "get_backtest_results",
    "run_baseline_backtest",
]
