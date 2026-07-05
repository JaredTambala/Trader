"""Tests for runtime metrics functional-core helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from trader.portfolio import Position
from trader.runtime import (
    MetricsSample,
    build_runtime_metrics_snapshot_record,
    compute_metrics_sample,
)


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
