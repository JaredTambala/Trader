"""Tests for runtime metrics functional-core helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from trader.portfolio import Position
from trader.portfolio.models import PortfolioState
from trader.runtime import (
    MetricsSample,
    build_runtime_metrics_snapshot_record,
    compute_metrics_sample,
)
from trader.runtime.metrics import _positions_and_cash_from_portfolio_state
from trader.runtime.metrics import _latest_price_lookup_from_rows, _latest_price_query_plan
from trader.runtime.metrics_core import positions_and_cash_from_broker_payload


def test_compute_metrics_sample_values_positions_without_mutation() -> None:
    ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    positions = [
        Position(symbol="AAPL", qty=2.0, avg_price=90.0),
        Position(symbol="MSFT", qty=-1.0, avg_price=200.0),
        Position(symbol="NVDA", qty=5.0, avg_price=50.0),
    ]

    computation = compute_metrics_sample(
        positions=positions,
        cash=1000.0,
        price_lookup={"AAPL": 100.0, "MSFT": 250.0},
        ts=ts,
        baseline_equity=None,
        peak_equity=None,
    )

    assert computation is not None
    assert computation.baseline_equity == 950.0
    assert computation.peak_equity == 950.0
    assert computation.sample == MetricsSample(
        ts=ts,
        equity=950.0,
        cash=1000.0,
        net_exposure=-50.0,
        gross_exposure=450.0,
        return_since_start=0.0,
        drawdown=0.0,
    )


def test_compute_metrics_sample_uses_existing_baseline_and_peak() -> None:
    ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    computation = compute_metrics_sample(
        positions=[Position(symbol="AAPL", qty=1.0, avg_price=90.0)],
        cash=500.0,
        price_lookup={"AAPL": 125.0},
        ts=ts,
        baseline_equity=500.0,
        peak_equity=750.0,
    )

    assert computation is not None
    assert computation.baseline_equity == 500.0
    assert computation.peak_equity == 750.0
    assert computation.sample.equity == 625.0
    assert computation.sample.return_since_start == 0.25
    assert computation.sample.drawdown == pytest.approx(-0.16666666666666663)


def test_compute_metrics_sample_skips_empty_cashless_state() -> None:
    ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    assert (
        compute_metrics_sample(
            positions=[],
            cash=0.0,
            price_lookup={},
            ts=ts,
            baseline_equity=None,
            peak_equity=None,
        )
        is None
    )


def test_build_runtime_metrics_snapshot_record_serializes_payload() -> None:
    ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    sample = MetricsSample(
        ts=ts,
        equity=625.0,
        cash=500.0,
        net_exposure=125.0,
        gross_exposure=125.0,
        return_since_start=0.25,
        drawdown=-0.1,
    )

    record = build_runtime_metrics_snapshot_record(
        sample,
        run_id="run_1",
        asset_class="stocks",
        symbols=("AAPL",),
    ).to_record()

    assert record["ts"] == ts
    assert record["run_id"] == "run_1"
    assert record["session_id"] == "run_1"
    assert record["cycle_id"] is None
    assert json.loads(str(record["payload"])) == {
        "equity": 625.0,
        "cash": 500.0,
        "net_exposure": 125.0,
        "gross_exposure": 125.0,
        "return_since_start": 0.25,
        "drawdown": -0.1,
        "asset_class": "stocks",
        "symbols": ["AAPL"],
    }


def test_positions_and_cash_from_portfolio_state_preserves_loaded_values() -> None:
    state = PortfolioState(
        positions={
            "AAPL": Position(symbol="AAPL", qty=2.0, avg_price=90.0),
            "MSFT": Position(symbol="MSFT", qty=-1.0, avg_price=200.0),
        },
        cash_balance=500.0,
    )

    positions, cash = _positions_and_cash_from_portfolio_state(state)

    assert positions == (
        Position(symbol="AAPL", qty=2.0, avg_price=90.0),
        Position(symbol="MSFT", qty=-1.0, avg_price=200.0),
    )
    assert cash == 500.0


def test_positions_and_cash_from_broker_payload_normalizes_provider_values() -> None:
    positions, cash = positions_and_cash_from_broker_payload(
        account={"cash": "1250.50"},
        positions_raw=(
            {
                "symbol": "BTCUSD",
                "asset_class": "crypto",
                "qty": "2",
                "avg_entry_price": "50000",
                "side": "long",
            },
            {
                "symbol": "AAPL",
                "asset_class": "us_equity",
                "qty": "3",
                "avg_entry_price": "100",
                "side": "short",
            },
            {
                "symbol": "",
                "asset_class": "us_equity",
                "qty": "1",
            },
        ),
    )

    assert positions == (
        Position(symbol="BTC/USD", qty=2.0, avg_price=50000.0),
        Position(symbol="AAPL", qty=-3.0, avg_price=100.0),
    )
    assert cash == 1250.50


def test_latest_price_query_plan_uses_bounded_asset_class_table() -> None:
    stock_plan = _latest_price_query_plan(asset_class="stocks", symbols=(" aapl ", "MSFT"))
    crypto_plan = _latest_price_query_plan(asset_class="cryptocurrency", symbols=("BTC/USD",))

    assert stock_plan is not None
    assert "FROM stock_bar_events" in stock_plan.query
    assert "symbol IN (%s, %s)" in stock_plan.query
    assert stock_plan.parameters == ("AAPL", "MSFT")

    assert crypto_plan is not None
    assert "FROM crypto_bar_events" in crypto_plan.query
    assert crypto_plan.parameters == ("BTC/USD",)


def test_latest_price_query_plan_skips_empty_symbol_universe() -> None:
    assert _latest_price_query_plan(asset_class="stocks", symbols=("", " ")) is None


def test_latest_price_lookup_from_rows_normalizes_prices() -> None:
    assert _latest_price_lookup_from_rows((("AAPL", "101.25"), ("MSFT", 250))) == {
        "AAPL": 101.25,
        "MSFT": 250.0,
    }
