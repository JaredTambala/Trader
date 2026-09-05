"""Backtest result-assembly contracts.

Subject: Construction of empty and completed immutable backtest result values.
Level: Pure unit contracts.
Collaborators: Real result builders supplied with explicit domain summaries and metrics.
Guarantees: Builder inputs map completely onto stable result identity, timing, outcomes, and evidence fields.
Non-goals: Computing metrics, serializing exports, running cycles, or persisting results.
"""

from __future__ import annotations

from datetime import datetime, timezone

from trader.backtest import (
    BacktestAssumptions,
    EquityPoint,
    PortfolioSummary,
    PositionSummary,
    TradeRecord,
)
from trader.backtest.models import TradeStats as _TradeStats
from trader.backtest.performance import _RelativeMetrics, _empty_performance_summary
from trader.backtest.result_builders import (
    _build_completed_backtest_result,
    _build_empty_backtest_result,
)


def test_build_empty_backtest_result_uses_explicit_values() -> None:
    """Build identified zero-run evidence with empty performance and a causal warning."""
    timestamp = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    assumptions = BacktestAssumptions()

    result = _build_empty_backtest_result(
        asset_class="stocks",
        symbols=("AAPL", "MSFT"),
        timeframe="1Min",
        assumptions=assumptions,
        run_id="run_empty",
        timestamp=timestamp,
        warning="No bars found for backtest window.",
    )

    assert result.run_id == "run_empty"
    assert result.started_at == timestamp
    assert result.finished_at == timestamp
    assert result.duration_seconds == 0.0
    assert result.asset_class == "stocks"
    assert result.symbols == ("AAPL", "MSFT")
    assert result.assumptions == assumptions
    assert result.warnings == ("No bars found for backtest window.",)
    assert result.strategy_performance.start_equity is None
    assert result.benchmark_performance.start_equity is None


def test_build_completed_backtest_result_maps_summaries_and_metrics() -> None:
    """Map supplied outcomes, accounting, curves, and relative metrics without recomputation."""
    started_at = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 1, 20, 12, 1, tzinfo=timezone.utc)
    position = PositionSummary(
        symbol="AAPL",
        qty=2.0,
        avg_price=100.0,
        last_price=110.0,
        last_ts=finished_at,
        market_value=220.0,
        unrealized_pnl=20.0,
    )
    trade = TradeRecord(
        client_order_id="cid_1",
        cycle_id="cycle_1",
        symbol="AAPL",
        side="sell",
        fill_ts=finished_at,
        fill_qty=1.0,
        raw_fill_price=110.0,
        fill_price=109.9,
        fee_amount=0.1,
        slippage_amount=0.1,
        notional=109.9,
        realized_pnl=9.9,
    )
    performance = _empty_performance_summary()

    result = _build_completed_backtest_result(
        total_runs=3,
        failed_runs=1,
        started_at=started_at,
        finished_at=finished_at,
        asset_class="stocks",
        symbols=("AAPL",),
        timeframe="1Min",
        portfolio_summary=PortfolioSummary(
            position_count=1,
            long_positions=1,
            short_positions=0,
            net_qty=2.0,
            gross_qty=2.0,
            net_notional=220.0,
            gross_notional=220.0,
            positions=(position,),
        ),
        assumptions=BacktestAssumptions(),
        warnings=("warning",),
        trade_stats=_TradeStats(
            trade_count=1,
            hit_rate=1.0,
            profit_factor=None,
            expectancy=9.9,
            avg_win=9.9,
            avg_loss=None,
            turnover=0.2,
            realized_pnl=9.9,
            trades=(trade,),
            total_fees=0.1,
            total_slippage=0.1,
        ),
        strategy_performance=performance,
        benchmark_performance=performance,
        relative_metrics=_RelativeMetrics(
            tracking_error=0.1,
            information_ratio=0.2,
            alpha=0.3,
            beta=0.4,
        ),
        equity_curve=(EquityPoint(ts=started_at, equity=1000.0),),
        benchmark_curve=(EquityPoint(ts=started_at, equity=990.0),),
        run_id="run_1",
    )

    assert result.total_runs == 3
    assert result.success_runs == 2
    assert result.failed_runs == 1
    assert result.duration_seconds == 60.0
    assert result.positions == (position,)
    assert result.trades == (trade,)
    assert result.total_fees == 0.1
    assert result.total_slippage == 0.1
    assert result.tracking_error == 0.1
    assert result.information_ratio == 0.2
    assert result.alpha == 0.3
    assert result.beta == 0.4
    assert result.warnings == ("warning",)
