"""Pure backtest performance, benchmark, and trade-accounting helpers."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from ..timeframes import normalize_timeframe
from .models import (
    EquityPoint,
    PerformanceSummary,
    TradeStats as _TradeStats,
)


@dataclass(frozen=True)
class _RelativeMetrics:
    """Benchmark-relative return statistics for a backtest equity curve."""

    tracking_error: float | None
    information_ratio: float | None
    alpha: float | None
    beta: float | None


@dataclass(frozen=True)
class _ReturnPerformanceMetrics:
    """Risk and return metrics derived only from an equity curve."""

    start_equity: float
    end_equity: float
    total_return: float | None
    cagr: float | None
    volatility: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None
    max_drawdown_duration: int | None
    calmar: float | None
    ulcer_index: float | None


@dataclass(frozen=True)
class _ExposureSummary:
    """Average exposure metrics derived from timestamp-level samples."""

    avg_net_exposure: float | None
    avg_gross_exposure: float | None
    avg_invested_pct: float | None


@dataclass(frozen=True)
class _DrawdownSummary:
    max_drawdown: float | None
    max_drawdown_duration: int | None
    ulcer_index: float | None


def _empty_performance_summary() -> PerformanceSummary:
    """Return an empty performance summary for degenerate runs."""
    return PerformanceSummary(
        start_equity=None,
        end_equity=None,
        total_return=None,
        cagr=None,
        volatility=None,
        sharpe=None,
        sortino=None,
        max_drawdown=None,
        max_drawdown_duration=None,
        calmar=None,
        ulcer_index=None,
        avg_net_exposure=None,
        avg_gross_exposure=None,
        avg_invested_pct=None,
        trade_count=None,
        hit_rate=None,
        profit_factor=None,
        expectancy=None,
        avg_win=None,
        avg_loss=None,
        turnover=None,
    )


def _build_performance_summary(
    equity_curve: Sequence[EquityPoint],
    timeframe: str,
    *,
    exposure_samples: Sequence[tuple[float, float, float | None]] | None,
    trade_stats: _TradeStats | None = None,
) -> PerformanceSummary:
    """Compute risk/return/exposure metrics for an equity curve.

    Curves with fewer than two points return an empty summary. Trade statistics
    are merged when available so the result combines time-series performance and
    fill-derived accounting in one object.
    """
    if len(equity_curve) < 2:
        return _empty_performance_summary()
    return_metrics = _summarize_return_performance(
        equity_curve,
        periods_per_year=_annualization_factor(timeframe),
    )
    exposure = _summarize_exposure_samples(exposure_samples or ())
    return PerformanceSummary(
        start_equity=return_metrics.start_equity,
        end_equity=return_metrics.end_equity,
        total_return=return_metrics.total_return,
        cagr=return_metrics.cagr,
        volatility=return_metrics.volatility,
        sharpe=return_metrics.sharpe,
        sortino=return_metrics.sortino,
        max_drawdown=return_metrics.max_drawdown,
        max_drawdown_duration=return_metrics.max_drawdown_duration,
        calmar=return_metrics.calmar,
        ulcer_index=return_metrics.ulcer_index,
        avg_net_exposure=exposure.avg_net_exposure,
        avg_gross_exposure=exposure.avg_gross_exposure,
        avg_invested_pct=exposure.avg_invested_pct,
        trade_count=trade_stats.trade_count if trade_stats else None,
        hit_rate=trade_stats.hit_rate if trade_stats else None,
        profit_factor=trade_stats.profit_factor if trade_stats else None,
        expectancy=trade_stats.expectancy if trade_stats else None,
        avg_win=trade_stats.avg_win if trade_stats else None,
        avg_loss=trade_stats.avg_loss if trade_stats else None,
        turnover=trade_stats.turnover if trade_stats else None,
    )


def _summarize_return_performance(
    equity_curve: Sequence[EquityPoint],
    *,
    periods_per_year: float,
) -> _ReturnPerformanceMetrics:
    """Compute return, volatility, and drawdown metrics from an equity curve."""
    start_equity = equity_curve[0].equity
    end_equity = equity_curve[-1].equity
    returns = _returns_from_curve(equity_curve)
    total_return = None
    if start_equity != 0:
        total_return = (end_equity / start_equity) - 1.0
    cagr = _compute_cagr(start_equity, end_equity, len(returns), periods_per_year)
    volatility = _annualize_volatility(returns, periods_per_year)
    sharpe = _compute_sharpe(returns, periods_per_year)
    sortino = _compute_sortino(returns, periods_per_year)
    drawdown = _compute_drawdowns(equity_curve)
    calmar = None
    if cagr is not None and drawdown.max_drawdown not in {None, 0.0}:
        calmar = cagr / drawdown.max_drawdown
    return _ReturnPerformanceMetrics(
        start_equity=start_equity,
        end_equity=end_equity,
        total_return=total_return,
        cagr=cagr,
        volatility=volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=drawdown.max_drawdown,
        max_drawdown_duration=drawdown.max_drawdown_duration,
        calmar=calmar,
        ulcer_index=drawdown.ulcer_index,
    )


def _summarize_exposure_samples(
    exposure_samples: Sequence[tuple[float, float, float | None]],
) -> _ExposureSummary:
    """Average net, gross, and invested exposure samples."""
    if not exposure_samples:
        return _ExposureSummary(
            avg_net_exposure=None,
            avg_gross_exposure=None,
            avg_invested_pct=None,
        )
    sample_count = len(exposure_samples)
    invested_values = [sample[2] for sample in exposure_samples if sample[2] is not None]
    avg_invested = None
    if invested_values:
        avg_invested = sum(invested_values) / len(invested_values)
    return _ExposureSummary(
        avg_net_exposure=sum(sample[0] for sample in exposure_samples) / sample_count,
        avg_gross_exposure=sum(sample[1] for sample in exposure_samples) / sample_count,
        avg_invested_pct=avg_invested,
    )


def _build_relative_metrics(
    *,
    strategy_curve: Sequence[EquityPoint],
    benchmark_curve: Sequence[EquityPoint],
    timeframe: str,
) -> _RelativeMetrics:
    """Compute tracking, information-ratio, alpha, and beta versus benchmark."""
    returns = _returns_from_curve(strategy_curve)
    benchmark_returns = _returns_from_curve(benchmark_curve)
    return _build_relative_metrics_from_returns(
        returns=returns,
        benchmark_returns=benchmark_returns,
        periods_per_year=_annualization_factor(timeframe),
    )


def _build_relative_metrics_from_returns(
    *,
    returns: Sequence[float],
    benchmark_returns: Sequence[float],
    periods_per_year: float,
) -> _RelativeMetrics:
    """Compute benchmark-relative metrics from aligned period return inputs."""
    length = min(len(returns), len(benchmark_returns))
    if length == 0:
        return _RelativeMetrics(None, None, None, None)
    returns = returns[:length]
    benchmark_returns = benchmark_returns[:length]
    excess = [r - b for r, b in zip(returns, benchmark_returns)]
    excess_std = _variance(excess) ** 0.5 if excess else 0.0
    tracking_error = None if excess_std == 0.0 else excess_std * (periods_per_year ** 0.5)
    info_ratio = None
    if excess_std != 0.0:
        info_ratio = _mean(excess) / excess_std * (periods_per_year ** 0.5)
    beta = _compute_beta(returns, benchmark_returns)
    alpha = None
    if beta is not None:
        alpha = _mean(returns) - beta * _mean(benchmark_returns)
        alpha = alpha * periods_per_year
    return _RelativeMetrics(tracking_error, info_ratio, alpha, beta)


def _compute_drawdowns(equity_curve: Sequence[EquityPoint]) -> _DrawdownSummary:
    """Compute drawdown metrics from an equity curve."""
    if not equity_curve:
        return _DrawdownSummary(None, None, None)
    peak = equity_curve[0].equity
    max_drawdown = 0.0
    max_duration = 0
    current_duration = 0
    drawdown_values: list[float] = []
    for point in equity_curve:
        equity = point.equity
        if equity >= peak:
            peak = equity
            current_duration = 0
            drawdown_values.append(0.0)
            continue
        drawdown = (peak - equity) / peak if peak != 0 else 0.0
        drawdown_values.append(drawdown)
        current_duration += 1
        if drawdown > max_drawdown:
            max_drawdown = drawdown
        if current_duration > max_duration:
            max_duration = current_duration
    ulcer_index = None
    if drawdown_values:
        ulcer_index = (_mean([value ** 2 for value in drawdown_values])) ** 0.5
    return _DrawdownSummary(max_drawdown, max_duration, ulcer_index)


def _returns_from_curve(curve: Sequence[EquityPoint]) -> list[float]:
    """Compute period returns from an equity curve."""
    returns: list[float] = []
    for prev, current in zip(curve, curve[1:]):
        if prev.equity == 0:
            continue
        returns.append((current.equity / prev.equity) - 1.0)
    return returns


def _annualization_factor(timeframe: str) -> float:
    """Return the annualization factor for the timeframe."""
    tf = normalize_timeframe(timeframe)
    amount, unit = _parse_timeframe_parts(tf)
    if unit == "month":
        return 12.0 / amount
    if unit == "week":
        return 52.0 / amount
    if unit == "day":
        return 365.0 / amount
    if unit == "hour":
        return (365.0 * 24.0) / amount
    return (365.0 * 24.0 * 60.0) / amount


def _parse_timeframe_parts(timeframe: str) -> tuple[int, str]:
    """Return numeric amount and lowercase unit from a normalized timeframe."""
    tf = normalize_timeframe(timeframe)
    for unit in ("Min", "Hour", "Day", "Week", "Month"):
        if tf.endswith(unit):
            amount = int(tf[: -len(unit)])
            return amount, unit.lower()
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _mean(values: Sequence[float]) -> float:
    """Compute the arithmetic mean of values."""
    return sum(values) / len(values) if values else 0.0


def _variance(values: Sequence[float]) -> float:
    """Compute the variance of values."""
    if not values:
        return 0.0
    avg = _mean(values)
    return _mean([(value - avg) ** 2 for value in values])


def _annualize_volatility(returns: Sequence[float], periods_per_year: float) -> float | None:
    """Annualize volatility using the timeframe factor."""
    if not returns:
        return None
    return (_variance(returns) ** 0.5) * (periods_per_year ** 0.5)


def _compute_cagr(
    start_equity: float,
    end_equity: float,
    periods: int,
    periods_per_year: float,
) -> float | None:
    """Compute the compound annual growth rate."""
    if start_equity <= 0 or periods <= 0:
        return None
    years = periods / periods_per_year
    if years <= 0:
        return None
    ratio = end_equity / start_equity
    if ratio <= 0:
        return None
    exponent = 1.0 / years
    try:
        return math.exp(math.log(ratio) * exponent) - 1.0
    except OverflowError:
        return float("inf")


def _compute_sharpe(returns: Sequence[float], periods_per_year: float) -> float | None:
    """Compute annualized Sharpe ratio when returns have non-zero variance."""
    if not returns:
        return None
    std = _variance(returns) ** 0.5
    if std == 0.0:
        return None
    return _mean(returns) / std * (periods_per_year ** 0.5)


def _compute_sortino(returns: Sequence[float], periods_per_year: float) -> float | None:
    """Compute annualized Sortino ratio from downside return variance."""
    downside = [value for value in returns if value < 0]
    if not downside:
        return None
    downside_std = _variance(downside) ** 0.5
    if downside_std == 0.0:
        return None
    return _mean(returns) / downside_std * (periods_per_year ** 0.5)


def _compute_beta(returns: Sequence[float], benchmark_returns: Sequence[float]) -> float | None:
    """Compute beta against the benchmark series."""
    if not returns or not benchmark_returns:
        return None
    length = min(len(returns), len(benchmark_returns))
    returns = returns[:length]
    benchmark_returns = benchmark_returns[:length]
    var_bench = _variance(benchmark_returns)
    if var_bench == 0:
        return None
    avg_returns = _mean(returns)
    avg_bench = _mean(benchmark_returns)
    cov = _mean([(r - avg_returns) * (b - avg_bench) for r, b in zip(returns, benchmark_returns)])
    return cov / var_bench
