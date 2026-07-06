"""Backtest result logging helpers."""

from __future__ import annotations

import logging

from .models import (
    BacktestResult,
)
from .result_builders import (
    _build_completed_backtest_result,
    _build_empty_backtest_result,
)

__all__ = [
    "_build_completed_backtest_result",
    "_build_empty_backtest_result",
    "_log_backtest_result",
]


logger = logging.getLogger(__name__)


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
