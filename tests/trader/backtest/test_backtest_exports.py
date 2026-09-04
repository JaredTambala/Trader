"""Protect stable machine-readable representations of completed backtest evidence.

Subject: Result serialization, JSON/CSV exports, and persisted metrics snapshot payloads.
Level: Deterministic unit and temporary-filesystem contracts.
Collaborators: Real export/payload builders with a fixed in-memory result and temporary paths.
Guarantees: Timestamps, nested values, columns, alignment gaps, and lineage fields serialize predictably.
Non-goals: Running backtests, database writes, user-interface rendering, or analytical interpretation.
"""

from __future__ import annotations

import json
from dataclasses import replace
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
from trader.backtest.export_payloads import (
    _build_equity_curve_csv_rows,
    _build_trade_csv_rows,
)
from trader.backtest.persistence_payloads import build_backtest_metrics_snapshot_payload


def test_serialize_backtest_result_is_json_friendly() -> None:
    """Normalize timestamps, tuples, assumptions, and trades into JSON-compatible values."""
    result = _sample_result()

    payload = serialize_backtest_result(result)

    assert payload["started_at"] == "2026-01-20T12:00:00+00:00"
    assert payload["equity_curve"][0]["ts"] == "2026-01-20T12:00:00+00:00"
    assert payload["assumptions"]["fees"]["fixed_per_order"] == 0.1
    assert payload["trades"][0]["realized_pnl"] is None
    assert payload["symbols"] == ["AAPL"]


def test_export_backtest_files_have_stable_columns(tmp_path: Path) -> None:
    """Write reviewable result files with stable JSON values and CSV headers."""
    result = _sample_result()

    json_path = export_backtest_result_json(result, tmp_path / "result.json")
    equity_path = export_backtest_equity_curve_csv(result, tmp_path / "equity.csv")
    trades_path = export_backtest_trades_csv(result, tmp_path / "trades.csv")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["total_fees"] == 0.2
    assert (
        equity_path.read_text(encoding="utf-8").splitlines()[0]
        == "ts,strategy_equity,benchmark_equity"
    )
    assert trades_path.read_text(encoding="utf-8").splitlines()[0] == (
        "client_order_id,cycle_id,symbol,side,fill_ts,fill_qty,raw_fill_price,fill_price,"
        "fee_amount,slippage_amount,notional,realized_pnl"
    )


def test_build_equity_curve_csv_rows_aligns_short_benchmark_curve() -> None:
    """Represent a missing benchmark point without shifting strategy-equity timestamps."""
    result = _sample_result()
    extra_point = EquityPoint(
        ts=datetime(2026, 1, 20, 12, 1, tzinfo=timezone.utc),
        equity=1010.0,
    )
    result = replace(
        result,
        equity_curve=(*result.equity_curve, extra_point),
        benchmark_curve=result.benchmark_curve[:1],
    )

    rows = _build_equity_curve_csv_rows(result)

    assert rows == (
        {
            "ts": "2026-01-20T12:00:00+00:00",
            "strategy_equity": 1000.0,
            "benchmark_equity": 1000.0,
        },
        {
            "ts": "2026-01-20T12:01:00+00:00",
            "strategy_equity": 1010.0,
            "benchmark_equity": None,
        },
    )


def test_build_trade_csv_rows_uses_stable_trade_accounting_fields() -> None:
    """Project each trade onto the complete ordered accounting export schema."""
    result = _sample_result()

    rows = _build_trade_csv_rows(result.trades)

    assert rows == (
        {
            "client_order_id": "cid_1",
            "cycle_id": "cycle_1",
            "symbol": "AAPL",
            "side": "buy",
            "fill_ts": "2026-01-20T12:00:00+00:00",
            "fill_qty": 1.0,
            "raw_fill_price": 100.0,
            "fill_price": 100.1,
            "fee_amount": 0.1,
            "slippage_amount": 0.1,
            "notional": 100.1,
            "realized_pnl": None,
        },
    )


def test_build_backtest_metrics_snapshot_payload_is_json_stable() -> None:
    """Build a JSON-stable metrics event with explicit run and session lineage."""
    result = _sample_result()
    ts = datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc)

    payload = build_backtest_metrics_snapshot_payload(
        run_id="run_1",
        result=result,
        ts=ts,
    )

    serialized = json.loads(str(payload["payload"]))
    assert payload["ts"] == ts
    assert payload["run_id"] == "run_1"
    assert payload["session_id"] == "run_1"
    assert payload["cycle_id"] is None
    assert serialized["symbols"] == ["AAPL"]
    assert serialized["total_fees"] == 0.2


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
