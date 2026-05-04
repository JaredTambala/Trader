"""Scenario tests for deterministic backtest accounting."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.support.duckdb_store import DuckDBEventStore
from trader.backtest import EquityPoint, _build_performance_summary, _compute_trade_stats
from trader.portfolio import Portfolio


def test_portfolio_apply_orders_supports_fee_amount() -> None:
    portfolio = Portfolio.empty(cash_balance=1000.0)

    portfolio.apply_orders(
        [{"symbol": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0, "fee_amount": 0.5}]
    )
    assert portfolio.positions["AAPL"].qty == 1.0
    assert portfolio.positions["AAPL"].avg_price == 100.0
    assert portfolio.cash_balance == pytest.approx(899.5)

    portfolio.apply_orders(
        [{"symbol": "AAPL", "side": "sell", "qty": 1.0, "price": 110.0, "fee_amount": 0.5}]
    )
    assert "AAPL" not in portfolio.positions
    assert portfolio.cash_balance == pytest.approx(1009.0)


def test_portfolio_average_price_after_multiple_buys() -> None:
    portfolio = Portfolio.empty(cash_balance=1000.0)
    portfolio.apply_orders([{"symbol": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0}])
    portfolio.apply_orders([{"symbol": "AAPL", "side": "buy", "qty": 3.0, "price": 110.0}])

    position = portfolio.positions["AAPL"]
    assert position.qty == 4.0
    assert position.avg_price == pytest.approx(107.5)
    assert portfolio.cash_balance == pytest.approx(570.0)


def test_trade_stats_capture_fees_slippage_and_realized_pnl(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    _record_order(store, "cid_buy", "cycle_1", "AAPL", "buy", 1.0, base_ts)
    _record_fill(
        store,
        "cid_buy",
        "cycle_1",
        fill_ts=base_ts,
        fill_qty=1.0,
        raw_fill_price=100.0,
        fill_price=100.1,
        fee_amount=0.1,
        slippage_amount=0.1,
    )
    _record_order(store, "cid_sell", "cycle_2", "AAPL", "sell", 1.0, base_ts)
    _record_fill(
        store,
        "cid_sell",
        "cycle_2",
        fill_ts=base_ts,
        fill_qty=1.0,
        raw_fill_price=110.0,
        fill_price=109.89,
        fee_amount=0.1,
        slippage_amount=0.11,
    )

    stats = _compute_trade_stats(
        store,
        "run_1",
        [
            EquityPoint(ts=base_ts, equity=1000.0),
            EquityPoint(ts=base_ts, equity=1009.59),
        ],
    )

    assert stats is not None
    assert stats.trade_count == 1
    assert stats.realized_pnl == pytest.approx(9.59)
    assert stats.total_fees == pytest.approx(0.2)
    assert stats.total_slippage == pytest.approx(0.21)
    assert stats.turnover == pytest.approx((100.1 + 109.89) / ((1000.0 + 1009.59) / 2.0))
    assert len(stats.trades) == 2
    assert stats.trades[0].realized_pnl is None
    assert stats.trades[1].realized_pnl == pytest.approx(9.59)


def test_trade_stats_partial_fill_keeps_open_position_without_realized_pnl(tmp_path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    _record_order(store, "cid_partial", "cycle_partial", "AAPL", "buy", 2.0, base_ts)
    _record_fill(
        store,
        "cid_partial",
        "cycle_partial",
        fill_ts=base_ts,
        fill_qty=1.0,
        raw_fill_price=100.0,
        fill_price=100.0,
        fee_amount=0.0,
        slippage_amount=0.0,
    )

    stats = _compute_trade_stats(store, "run_1", [EquityPoint(ts=base_ts, equity=1000.0)])

    assert stats is not None
    assert stats.trade_count == 0
    assert stats.realized_pnl is None
    assert len(stats.trades) == 1
    assert stats.trades[0].fill_qty == 1.0


def test_performance_summary_uses_known_turnover_and_drawdown() -> None:
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
    assert summary.avg_invested_pct == pytest.approx((0.5 + (200.0 / 900.0) + 0.0) / 3.0)


def _record_order(
    store: DuckDBEventStore,
    client_order_id: str,
    cycle_id: str,
    symbol: str,
    side: str,
    qty: float,
    created_at: datetime,
) -> None:
    store.record_event(
        "order_events",
        {
            "order_event_id": f"order_evt_{client_order_id}",
            "client_order_id": client_order_id,
            "run_id": "run_1",
            "session_id": "run_1",
            "cycle_id": cycle_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": "market",
            "status": "filled",
            "broker_order_id": None,
            "rejection_reason": None,
            "created_at": created_at,
        },
    )


def _record_fill(
    store: DuckDBEventStore,
    client_order_id: str,
    cycle_id: str,
    *,
    fill_ts: datetime,
    fill_qty: float,
    raw_fill_price: float,
    fill_price: float,
    fee_amount: float,
    slippage_amount: float,
) -> None:
    store.record_event(
        "fill_events",
        {
            "client_order_id": client_order_id,
            "run_id": "run_1",
            "session_id": "run_1",
            "cycle_id": cycle_id,
            "fill_ts": fill_ts,
            "fill_qty": fill_qty,
            "raw_fill_price": raw_fill_price,
            "fill_price": fill_price,
            "slippage_amount": slippage_amount,
            "fee_amount": fee_amount,
        },
    )
