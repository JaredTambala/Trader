"""Backtest statistical-performance contracts.

Subject: Exposure, return, benchmark-relative, drawdown, and aggregate performance summaries.
Level: Pure numerical unit contracts.
Collaborators: Real performance helpers with fixed equity curves and return sequences.
Guarantees: Defined and undefined metric cases remain explicit, aligned, and numerically reproducible.
Non-goals: Trade-event matching, portfolio mutation, benchmark allocation, or strategy evaluation policy.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.backtest import EquityPoint, _build_performance_summary
from trader.backtest.performance import (
    _build_relative_metrics_from_returns,
    _summarize_exposure_samples,
    _summarize_return_performance,
)


def test_summarize_exposure_samples_handles_missing_invested_values() -> None:
    """Average available exposure fields while leaving wholly absent samples undefined."""
    empty = _summarize_exposure_samples(())
    assert empty.avg_net_exposure is None
    assert empty.avg_gross_exposure is None
    assert empty.avg_invested_pct is None

    summary = _summarize_exposure_samples(
        (
            (100.0, 120.0, 0.60),
            (-50.0, 80.0, None),
            (25.0, 25.0, 0.25),
        )
    )

    assert summary.avg_net_exposure == pytest.approx(25.0)
    assert summary.avg_gross_exposure == pytest.approx(75.0)
    assert summary.avg_invested_pct == pytest.approx(0.425)


def test_build_relative_metrics_from_returns_aligns_and_scores_series() -> None:
    """Align unequal return series before computing annualized relative performance metrics."""
    returns = (0.02, -0.01, 0.03, 0.99)
    benchmark_returns = (0.01, 0.0, 0.02)

    metrics = _build_relative_metrics_from_returns(
        returns=returns,
        benchmark_returns=benchmark_returns,
        periods_per_year=4.0,
    )

    aligned_returns = returns[:3]
    excess = [
        value - benchmark
        for value, benchmark in zip(aligned_returns, benchmark_returns)
    ]
    excess_mean = sum(excess) / len(excess)
    excess_variance = sum((value - excess_mean) ** 2 for value in excess) / len(excess)
    excess_std = excess_variance**0.5
    benchmark_mean = sum(benchmark_returns) / len(benchmark_returns)
    return_mean = sum(aligned_returns) / len(aligned_returns)
    benchmark_variance = sum(
        (value - benchmark_mean) ** 2 for value in benchmark_returns
    ) / len(benchmark_returns)
    covariance = sum(
        (value - return_mean) * (benchmark - benchmark_mean)
        for value, benchmark in zip(aligned_returns, benchmark_returns)
    ) / len(aligned_returns)
    expected_beta = covariance / benchmark_variance

    assert metrics.tracking_error == pytest.approx(excess_std * 2.0)
    assert metrics.information_ratio == pytest.approx((excess_mean / excess_std) * 2.0)
    assert metrics.beta == pytest.approx(expected_beta)
    assert metrics.alpha == pytest.approx(
        (return_mean - expected_beta * benchmark_mean) * 4.0
    )


def test_build_relative_metrics_from_returns_handles_missing_or_identical_series() -> (
    None
):
    """Keep unavailable ratios explicit and score identical nonempty series consistently."""
    empty = _build_relative_metrics_from_returns(
        returns=(),
        benchmark_returns=(0.01,),
        periods_per_year=4.0,
    )
    identical = _build_relative_metrics_from_returns(
        returns=(0.01, 0.02),
        benchmark_returns=(0.01, 0.02),
        periods_per_year=4.0,
    )

    assert empty.tracking_error is None
    assert empty.information_ratio is None
    assert empty.alpha is None
    assert empty.beta is None
    assert identical.tracking_error is None
    assert identical.information_ratio is None
    assert identical.alpha == pytest.approx(0.0)
    assert identical.beta == pytest.approx(1.0)


def test_summarize_return_performance_reports_curve_metrics() -> None:
    """Derive return, volatility, drawdown, duration, and ulcer evidence from equity."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    metrics = _summarize_return_performance(
        (
            EquityPoint(ts=base_ts, equity=100.0),
            EquityPoint(ts=base_ts, equity=90.0),
            EquityPoint(ts=base_ts, equity=99.0),
        ),
        periods_per_year=4.0,
    )

    assert metrics.start_equity == 100.0
    assert metrics.end_equity == 99.0
    assert metrics.total_return == pytest.approx(-0.01)
    assert metrics.volatility is not None
    assert metrics.sharpe is not None
    assert metrics.sortino is None
    assert metrics.max_drawdown == pytest.approx(0.1)
    assert metrics.max_drawdown_duration == 2
    assert metrics.ulcer_index is not None


def test_summarize_return_performance_handles_zero_starting_equity() -> None:
    """Leave return and growth undefined when starting equity cannot be divided."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    metrics = _summarize_return_performance(
        (
            EquityPoint(ts=base_ts, equity=0.0),
            EquityPoint(ts=base_ts, equity=10.0),
        ),
        periods_per_year=4.0,
    )

    assert metrics.start_equity == 0.0
    assert metrics.end_equity == 10.0
    assert metrics.total_return is None
    assert metrics.cagr is None


def test_performance_summary_uses_known_turnover_and_drawdown() -> None:
    """Combine curve, exposure, and supplied turnover into one performance summary."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    summary = _build_performance_summary(
        [
            EquityPoint(ts=base_ts, equity=1000.0),
            EquityPoint(ts=base_ts, equity=900.0),
            EquityPoint(ts=base_ts, equity=990.0),
        ],
        "1Min",
        exposure_samples=[
            (500.0, 500.0, 0.5),
            (200.0, 200.0, 200.0 / 900.0),
            (0.0, 0.0, 0.0),
        ],
        trade_stats=None,
    )

    assert summary.max_drawdown == pytest.approx(0.1)
    assert summary.max_drawdown_duration == 2
    assert summary.avg_net_exposure == pytest.approx((500.0 + 200.0 + 0.0) / 3.0)
    assert summary.avg_gross_exposure == pytest.approx((500.0 + 200.0 + 0.0) / 3.0)
    assert summary.avg_invested_pct == pytest.approx(
        (0.5 + (200.0 / 900.0) + 0.0) / 3.0
    )
