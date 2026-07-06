"""Pure builders for backtest result value objects."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from .models import (
    BacktestAssumptions,
    BacktestResult,
    EquityPoint,
    PerformanceSummary,
    PortfolioSummary,
    TradeStats as _TradeStats,
)
from .performance import _RelativeMetrics, _empty_performance_summary

__all__ = [
    "_build_completed_backtest_result",
    "_build_empty_backtest_result",
]


def _build_empty_backtest_result(
    *,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    assumptions: BacktestAssumptions,
    run_id: str,
    timestamp: datetime,
    warning: str,
) -> BacktestResult:
    """Build a zero-run backtest result from explicit shell-provided values."""
    empty_summary = _empty_performance_summary()
    return BacktestResult(
        total_runs=0,
        success_runs=0,
        failed_runs=0,
        started_at=timestamp,
        finished_at=timestamp,
        duration_seconds=0.0,
        asset_class=asset_class,
        symbols=tuple(symbols),
        timeframe=timeframe,
        position_count=0,
        long_positions=0,
        short_positions=0,
        net_qty=0.0,
        gross_qty=0.0,
        net_notional=None,
        gross_notional=None,
        positions=tuple(),
        assumptions=assumptions,
        warnings=(warning,),
        trades=tuple(),
        realized_pnl=None,
        total_fees=0.0,
        total_slippage=0.0,
        strategy_performance=empty_summary,
        benchmark_performance=empty_summary,
        tracking_error=None,
        information_ratio=None,
        alpha=None,
        beta=None,
        equity_curve=tuple(),
        benchmark_curve=tuple(),
        run_id=run_id,
    )


def _build_completed_backtest_result(
    *,
    total_runs: int,
    failed_runs: int,
    started_at: datetime,
    finished_at: datetime,
    asset_class: str,
    symbols: Sequence[str],
    timeframe: str,
    portfolio_summary: PortfolioSummary,
    assumptions: BacktestAssumptions,
    warnings: Sequence[str],
    trade_stats: _TradeStats,
    strategy_performance: PerformanceSummary,
    benchmark_performance: PerformanceSummary,
    relative_metrics: _RelativeMetrics,
    equity_curve: Sequence[EquityPoint],
    benchmark_curve: Sequence[EquityPoint],
    run_id: str,
) -> BacktestResult:
    """Assemble a completed backtest result from explicit summary values."""
    return BacktestResult(
        total_runs=total_runs,
        success_runs=total_runs - failed_runs,
        failed_runs=failed_runs,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=(finished_at - started_at).total_seconds(),
        asset_class=asset_class,
        symbols=tuple(symbols),
        timeframe=timeframe,
        position_count=portfolio_summary.position_count,
        long_positions=portfolio_summary.long_positions,
        short_positions=portfolio_summary.short_positions,
        net_qty=portfolio_summary.net_qty,
        gross_qty=portfolio_summary.gross_qty,
        net_notional=portfolio_summary.net_notional,
        gross_notional=portfolio_summary.gross_notional,
        positions=portfolio_summary.positions,
        assumptions=assumptions,
        warnings=tuple(warnings),
        trades=trade_stats.trades,
        realized_pnl=trade_stats.realized_pnl,
        total_fees=trade_stats.total_fees,
        total_slippage=trade_stats.total_slippage,
        strategy_performance=strategy_performance,
        benchmark_performance=benchmark_performance,
        tracking_error=relative_metrics.tracking_error,
        information_ratio=relative_metrics.information_ratio,
        alpha=relative_metrics.alpha,
        beta=relative_metrics.beta,
        equity_curve=tuple(equity_curve),
        benchmark_curve=tuple(benchmark_curve),
        run_id=run_id,
    )
