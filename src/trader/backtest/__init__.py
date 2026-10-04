"""Backtest package public API."""

from .core import (
    BacktestRunner,
    main,
    run_cycle,
)
from .data import BacktestMarketDataSource
from .recent_bars import InMemoryRecentBarReader, RecentBarReadStats
from .exports import (
    export_backtest_equity_curve_csv,
    export_backtest_result_json,
    export_backtest_trades_csv,
    serialize_backtest_result,
)
from .models import (
    BacktestAssumptions,
    BacktestEvidenceCoverage,
    BacktestResult,
    BacktestSpec,
    DataAssumptions,
    EquityPoint,
    FeeAssumptions,
    PerformanceSummary,
    PortfolioSummary,
    PositionSummary,
    SlippageAssumptions,
    TradeRecord,
    build_backtest_assumptions,
)
from .performance import _build_performance_summary
from .persistence import persist_backtest_result, _compute_trade_stats
from .review_scope import (
    BacktestReviewScope,
    BacktestVariant,
    ReviewInitialPosition,
    build_backtest_review_scope,
    build_backtest_variant,
    build_data_scope_id,
)

__all__ = [
    "BacktestAssumptions",
    "BacktestEvidenceCoverage",
    "BacktestMarketDataSource",
    "BacktestResult",
    "BacktestReviewScope",
    "BacktestRunner",
    "InMemoryRecentBarReader",
    "RecentBarReadStats",
    "BacktestVariant",
    "BacktestSpec",
    "DataAssumptions",
    "EquityPoint",
    "FeeAssumptions",
    "PerformanceSummary",
    "PortfolioSummary",
    "PositionSummary",
    "ReviewInitialPosition",
    "SlippageAssumptions",
    "TradeRecord",
    "build_backtest_assumptions",
    "build_backtest_review_scope",
    "build_backtest_variant",
    "build_data_scope_id",
    "export_backtest_equity_curve_csv",
    "export_backtest_result_json",
    "export_backtest_trades_csv",
    "main",
    "persist_backtest_result",
    "run_cycle",
    "serialize_backtest_result",
    "_build_performance_summary",
    "_compute_trade_stats",
]
