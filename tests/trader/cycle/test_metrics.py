"""Cycle metrics snapshot contracts.

Subject: Valuation payload construction, event serialization, and market-price resolution for cycle metrics.
Level: Deterministic unit contracts.
Collaborators: Real cycle metrics builders, core position values, and package-owned market-event factories.
Guarantees: Priced positions and lineage fields produce stable JSON metrics without inventing missing values.
Non-goals: Metrics persistence, sampling schedules, broker accounts, or performance analysis.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from tests.trader.cycle.factories import stock_event as _stock_event
from trader.cycle import build_metrics_snapshot_event, build_metrics_snapshot_payload
from trader.cycle.metrics import _resolve_metrics_price_lookup
from trader.portfolio import Position


def test_build_metrics_snapshot_payload_excludes_unpriced_positions() -> None:
    """Value only priced positions while retaining the complete configured symbol scope."""
    positions = {
        "AAPL": Position(symbol="AAPL", qty=2.0, avg_price=90.0),
        "MSFT": Position(symbol="MSFT", qty=-1.0, avg_price=200.0),
        "NVDA": Position(symbol="NVDA", qty=5.0, avg_price=50.0),
    }

    payload = build_metrics_snapshot_payload(
        positions=positions,
        cash_balance=1000.0,
        price_lookup={"AAPL": 100.0, "MSFT": 250.0},
        asset_class="stocks",
        symbols=("AAPL", "MSFT", "NVDA"),
    )

    assert payload.equity == 950.0
    assert payload.cash == 1000.0
    assert payload.net_exposure == -50.0
    assert payload.gross_exposure == 450.0
    assert payload.to_payload() == {
        "equity": 950.0,
        "cash": 1000.0,
        "net_exposure": -50.0,
        "gross_exposure": 450.0,
        "asset_class": "stocks",
        "symbols": ["AAPL", "MSFT", "NVDA"],
    }


def test_build_metrics_snapshot_event_serializes_payload_deterministically() -> None:
    """Serialize valuation and cycle lineage into a stable metrics event."""
    asof_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    event = build_metrics_snapshot_event(
        positions={"AAPL": Position(symbol="AAPL", qty=1.0, avg_price=90.0)},
        cash_balance=500.0,
        price_lookup={"AAPL": 125.0},
        asof_ts=asof_ts,
        run_id="run_1",
        cycle_id="cycle_1",
        asset_class="stocks",
        symbols=("AAPL",),
    )

    record = event.to_record()
    assert record["ts"] == asof_ts
    assert record["run_id"] == "run_1"
    assert record["session_id"] == "run_1"
    assert record["cycle_id"] == "cycle_1"
    assert json.loads(str(record["payload"])) == {
        "equity": 625.0,
        "cash": 500.0,
        "net_exposure": 125.0,
        "gross_exposure": 125.0,
        "asset_class": "stocks",
        "symbols": ["AAPL"],
    }


def test_resolve_metrics_price_lookup_prefers_stream_prices_and_falls_back_to_events() -> (
    None
):
    """Prefer explicit stream prices and otherwise select the latest event close."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    older = _stock_event(ts=base_ts - timedelta(minutes=1), close=99.0)
    latest = _stock_event(ts=base_ts, close=101.0)

    assert _resolve_metrics_price_lookup(
        price_lookup={"AAPL": 105.0},
        market_data_events=[older, latest],
    ) == {"AAPL": 105.0}
    assert _resolve_metrics_price_lookup(
        price_lookup={},
        market_data_events=[older, latest],
    ) == {"AAPL": 101.0}
    assert _resolve_metrics_price_lookup(price_lookup={}, market_data_events=[]) == {}
