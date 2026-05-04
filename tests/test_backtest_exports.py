"""Tests for backtest result serialization and export helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from trader.backtest import (
    BacktestAssumptions,
    BacktestResult,
    EquityPoint,
    FeeAssumptions,
    PerformanceSummary,
    PositionSummary,
    SlippageAssumptions,
    TradeRecord,
    export_backtest_equity_curve_csv,
    export_backtest_result_json,
    export_backtest_trades_csv,
    serialize_backtest_result,
)


def test_serialize_backtest_result_is_json_friendly() -> None:
    result = _sample_result()

    payload = serialize_backtest_result(result)

    assert payload["started_at"] == "2026-01-20T12:00:00+00:00"
    assert payload["equity_curve"][0]["ts"] == "2026-01-20T12:00:00+00:00"
    assert payload["assumptions"]["fees"]["fixed_per_order"] == 0.1
    assert payload["trades"][0]["realized_pnl"] is None
    assert payload["symbols"] == ["AAPL"]


def test_export_backtest_files_have_stable_columns(tmp_path: Path) -> None:
    result = _sample_result()

    json_path = export_backtest_result_json(result, tmp_path / "result.json")
    equity_path = export_backtest_equity_curve_csv(result, tmp_path / "equity.csv")
    trades_path = export_backtest_trades_csv(result, tmp_path / "trades.csv")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["total_fees"] == 0.2
    assert equity_path.read_text(encoding="utf-8").splitlines()[0] == "ts,strategy_equity,benchmark_equity"
    assert trades_path.read_text(encoding="utf-8").splitlines()[0] == (
        "client_order_id,cycle_id,symbol,side,fill_ts,fill_qty,raw_fill_price,fill_price,"
        "fee_amount,slippage_amount,notional,realized_pnl"
    )


def _sample_result() -> BacktestResult:
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    perf = PerformanceSummary(
        start_equity=1000.0,
        end_equity=1009.59,
        total_return=0.00959,
        cagr=None,
        volatility=None,
        sharpe=None,
        sortino=None,
        max_drawdown=0.0,
        max_drawdown_duration=0,
        calmar=None,
        ulcer_index=0.0,
        avg_net_exposure=100.0,
        avg_gross_exposure=100.0,
        avg_invested_pct=0.1,
        trade_count=1,
        hit_rate=1.0,
        profit_factor=None,
        expectancy=9.59,
        avg_win=9.59,
        avg_loss=None,
        turnover=0.2,
    )
    assumptions = BacktestAssumptions(
        fees=FeeAssumptions(fixed_per_order=0.1),
        slippage=SlippageAssumptions(bps=10.0),
    )
    return BacktestResult(
        total_runs=2,
        success_runs=2,
        failed_runs=0,
        started_at=base_ts,
        finished_at=base_ts,
        duration_seconds=1.0,
        asset_class="stocks",
        symbols=("AAPL",),
        timeframe="1Min",
        position_count=0,
        long_positions=0,
        short_positions=0,
        net_qty=0.0,
        gross_qty=0.0,
        net_notional=0.0,
        gross_notional=0.0,
        positions=(
            PositionSummary(
                symbol="AAPL",
                qty=0.0,
                avg_price=None,
                last_price=110.0,
                last_ts=base_ts,
                market_value=0.0,
                unrealized_pnl=None,
            ),
        ),
        assumptions=assumptions,
        warnings=("Used latest prior bar for AAPL.",),
        trades=(
            TradeRecord(
                client_order_id="cid_1",
                cycle_id="cycle_1",
                symbol="AAPL",
                side="buy",
                fill_ts=base_ts,
                fill_qty=1.0,
                raw_fill_price=100.0,
                fill_price=100.1,
                fee_amount=0.1,
                slippage_amount=0.1,
                notional=100.1,
                realized_pnl=None,
            ),
        ),
        realized_pnl=9.59,
        total_fees=0.2,
        total_slippage=0.21,
        strategy_performance=perf,
        benchmark_performance=perf,
        tracking_error=None,
        information_ratio=None,
        alpha=None,
        beta=None,
        equity_curve=(EquityPoint(ts=base_ts, equity=1000.0),),
        benchmark_curve=(EquityPoint(ts=base_ts, equity=1000.0),),
    )
