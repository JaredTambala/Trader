"""Backtest result construction and logging helpers."""

from __future__ import annotations

from datetime import datetime
import logging
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


logger = logging.getLogger(__name__)


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


def _log_backtest_result(result: BacktestResult) -> None:
    """Emit human-readable summary logs for a completed backtest result."""
    logger.info(
        "Backtest complete total=%s success=%s failed=%s duration_seconds=%.2f",
        result.total_runs,
        result.success_runs,
        result.failed_runs,
        result.duration_seconds,
    )
    logger.info(
        "Backtest portfolio positions=%s long=%s short=%s net_qty=%.4f gross_qty=%.4f net_notional=%s gross_notional=%s",
        result.position_count,
        result.long_positions,
        result.short_positions,
        result.net_qty,
        result.gross_qty,
        _format_optional_float(result.net_notional),
        _format_optional_float(result.gross_notional),
    )
    logger.info(
        "Backtest performance total_return=%s cagr=%s volatility=%s sharpe=%s sortino=%s max_drawdown=%s",
        _format_optional_pct(result.strategy_performance.total_return),
        _format_optional_pct(result.strategy_performance.cagr),
        _format_optional_pct(result.strategy_performance.volatility),
        _format_optional_float(result.strategy_performance.sharpe),
        _format_optional_float(result.strategy_performance.sortino),
        _format_optional_pct(result.strategy_performance.max_drawdown),
    )
    logger.info(
        "Backtest benchmark total_return=%s cagr=%s volatility=%s sharpe=%s sortino=%s max_drawdown=%s",
        _format_optional_pct(result.benchmark_performance.total_return),
        _format_optional_pct(result.benchmark_performance.cagr),
        _format_optional_pct(result.benchmark_performance.volatility),
        _format_optional_float(result.benchmark_performance.sharpe),
        _format_optional_float(result.benchmark_performance.sortino),
        _format_optional_pct(result.benchmark_performance.max_drawdown),
    )
    logger.info(
        "Backtest relative tracking_error=%s information_ratio=%s alpha=%s beta=%s",
        _format_optional_pct(result.tracking_error),
        _format_optional_float(result.information_ratio),
        _format_optional_pct(result.alpha),
        _format_optional_float(result.beta),
    )
    for position in result.positions:
        logger.info(
            "Backtest position symbol=%s qty=%.4f avg_price=%s last_price=%s last_ts=%s market_value=%s pnl=%s",
            position.symbol,
            position.qty,
            _format_optional_float(position.avg_price),
            _format_optional_float(position.last_price),
            position.last_ts.isoformat() if position.last_ts else "<unset>",
            _format_optional_float(position.market_value),
            _format_optional_float(position.unrealized_pnl),
        )


def _format_optional_float(value: float | None) -> str:
    """Format an optional float for logs, using `<unset>` for missing values."""
    if value is None:
        return "<unset>"
    return f"{value:.4f}"


def _format_optional_pct(value: float | None) -> str:
    """Format an optional ratio as a percentage for logs."""
    if value is None:
        return "<unset>"
    return f"{value:.2%}"
