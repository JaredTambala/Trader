"""Tests for portfolio primitives."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.support.duckdb_store import DuckDBEventStore
from trader.portfolio import Portfolio, Position, load_latest_cash, load_latest_positions


def test_portfolio_apply_orders_updates_positions() -> None:
    portfolio = Portfolio.empty(cash_balance=1000.0)

    portfolio.apply_orders(
        [
            {"symbol": "AAPL", "side": "buy", "qty": 2},
        ],
        price_lookup={"AAPL": 100.0},
    )

    position = portfolio.positions["AAPL"]
    assert position.qty == 2.0
    assert position.avg_price == 100.0
    assert portfolio.cash_balance == 800.0

    portfolio.apply_orders(
        [
            {"symbol": "AAPL", "side": "sell", "qty": 1},
        ],
        price_lookup={"AAPL": 110.0},
    )

    position = portfolio.positions["AAPL"]
    assert position.qty == 1.0
    assert position.avg_price == 100.0
    assert portfolio.cash_balance == 910.0

    portfolio.apply_orders(
        [
            {"symbol": "AAPL", "side": "sell", "qty": 1},
        ],
        price_lookup={"AAPL": 110.0},
    )
    assert "AAPL" not in portfolio.positions
    assert portfolio.cash_balance == 1020.0


def test_portfolio_snapshot_persists_latest_positions(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime.now(timezone.utc)

    snapshot = Portfolio(positions={"MSFT": Position("MSFT", 3.0, 250.0)}, cash_balance=500.0).snapshot(
        asof_ts=now
    )
    snapshot.persist(store)

    later = now + timedelta(minutes=1)
    snapshot = Portfolio(positions={"MSFT": Position("MSFT", 4.0, 255.0)}, cash_balance=750.0).snapshot(
        asof_ts=later
    )
    snapshot.persist(store)

    positions = load_latest_positions(store)
    assert len(positions) == 1
    assert positions[0].symbol == "MSFT"
    assert positions[0].qty == 4.0
    assert positions[0].avg_price == 255.0
    assert load_latest_cash(store) == 750.0
