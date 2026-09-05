"""Execute and query backtests backed by canonical research specifications.

The public services require passed specification evidence, persist complete run
artifacts, and expose deterministic comparison reads. They do not accept ad hoc
strategy behavior outside the implementation and specification chain.
"""

from .execution import (
    compare_backtest_results,
    get_backtest_results,
    run_backtest_specification,
)

__all__ = [
    "compare_backtest_results",
    "get_backtest_results",
    "run_backtest_specification",
]
