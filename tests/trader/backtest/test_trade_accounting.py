"""Backtest fill application and realized-trade accounting contracts.

Subject: Portfolio fills, position transitions, event matching, costs, realized PnL, and turnover.
Level: Deterministic unit contracts with bounded DuckDB adapter coverage.
Collaborators: Real accounting helpers, core portfolios, and temporary DuckDB event stores where queried.
Guarantees: Filled orders produce reproducible cash, position, trade, fee, slippage, and turnover evidence.
Non-goals: Replay selection, result serialization, statistical performance, or provider execution fidelity.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.support.duckdb_store import DuckDBEventStore
from trader.backtest import EquityPoint, _compute_trade_stats
from trader.backtest.models import (
    FillAccountingEvent as _FillAccountingEvent,
    OrderAccountingEvent as _OrderAccountingEvent,
)
from trader.backtest.trade_accounting import (
    _PositionAccountingState,
    _apply_fill_to_position_state,
    _compute_trade_stats_from_events,
    _compute_turnover,
    _summarize_realized_trade_pnls,
)
from trader.portfolio import Portfolio


def test_portfolio_apply_orders_supports_fee_amount() -> None:
    """Debit fees on buys and sells while preserving correct terminal cash."""
    portfolio = Portfolio.empty(cash_balance=1000.0)

    portfolio.apply_orders(
        [
            {
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "price": 100.0,
                "fee_amount": 0.5,
            }
        ]
    )
    assert portfolio.positions["AAPL"].qty == 1.0
    assert portfolio.positions["AAPL"].avg_price == 100.0
    assert portfolio.cash_balance == pytest.approx(899.5)

    portfolio.apply_orders(
        [
            {
                "symbol": "AAPL",
                "side": "sell",
                "qty": 1.0,
                "price": 110.0,
                "fee_amount": 0.5,
            }
        ]
    )
    assert "AAPL" not in portfolio.positions
    assert portfolio.cash_balance == pytest.approx(1009.0)


def test_portfolio_average_price_after_multiple_buys() -> None:
    """Recalculate weighted entry price and cash after adding long quantity."""
    portfolio = Portfolio.empty(cash_balance=1000.0)
    portfolio.apply_orders(
        [{"symbol": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0}]
    )
    portfolio.apply_orders(
        [{"symbol": "AAPL", "side": "buy", "qty": 3.0, "price": 110.0}]
    )

    position = portfolio.positions["AAPL"]
    assert position.qty == 4.0
    assert position.avg_price == pytest.approx(107.5)
    assert portfolio.cash_balance == pytest.approx(570.0)


def test_apply_fill_to_position_state_opens_and_adds_long_position() -> None:
    """Open and enlarge long state without prematurely realizing profit or loss."""
    opened = _apply_fill_to_position_state(
        None, side="buy", qty=2.0, effective_unit_price=100.0
    )
    assert opened.state == _PositionAccountingState(qty=2.0, avg_price=100.0)
    assert opened.realized_pnl is None

    added = _apply_fill_to_position_state(
        opened.state,
        side="buy",
        qty=2.0,
        effective_unit_price=110.0,
    )

    assert added.state == _PositionAccountingState(qty=4.0, avg_price=105.0)
    assert added.realized_pnl is None


def test_apply_fill_to_position_state_closes_and_reverses_long_position() -> None:
    """Realize long reductions and establish short state only beyond full closure."""
    current = _PositionAccountingState(qty=2.0, avg_price=100.0)

    reduced = _apply_fill_to_position_state(
        current,
        side="sell",
        qty=1.0,
        effective_unit_price=110.0,
    )
    assert reduced.state == _PositionAccountingState(qty=1.0, avg_price=100.0)
    assert reduced.realized_pnl == pytest.approx(10.0)

    closed = _apply_fill_to_position_state(
        current,
        side="sell",
        qty=2.0,
        effective_unit_price=95.0,
    )
    assert closed.state is None
    assert closed.realized_pnl == pytest.approx(-10.0)

    reversed_position = _apply_fill_to_position_state(
        current,
        side="sell",
        qty=3.0,
        effective_unit_price=90.0,
    )
    assert reversed_position.state == _PositionAccountingState(qty=-1.0, avg_price=90.0)
    assert reversed_position.realized_pnl == pytest.approx(-20.0)


def test_apply_fill_to_position_state_adds_and_reverses_short_position() -> None:
    """Average added shorts and realize gains when a buy reverses direction."""
    current = _PositionAccountingState(qty=-1.0, avg_price=100.0)

    added = _apply_fill_to_position_state(
        current,
        side="sell",
        qty=3.0,
        effective_unit_price=90.0,
    )
    assert added.state == _PositionAccountingState(qty=-4.0, avg_price=92.5)
    assert added.realized_pnl is None

    reversed_position = _apply_fill_to_position_state(
        _PositionAccountingState(qty=-2.0, avg_price=50.0),
        side="buy",
        qty=3.0,
        effective_unit_price=45.0,
    )
    assert reversed_position.state == _PositionAccountingState(qty=1.0, avg_price=45.0)
    assert reversed_position.realized_pnl == pytest.approx(10.0)


def test_compute_turnover_uses_average_equity_when_available() -> None:
    """Measure traded notional against average nonzero equity across the curve."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    turnover = _compute_turnover(
        traded_notional=300.0,
        equity_curve=(
            EquityPoint(ts=base_ts, equity=100.0),
            EquityPoint(ts=base_ts, equity=200.0),
        ),
    )

    assert turnover == pytest.approx(2.0)


def test_compute_turnover_is_empty_without_average_equity() -> None:
    """Leave turnover undefined when no positive average-equity denominator exists."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    assert _compute_turnover(traded_notional=300.0, equity_curve=()) is None
    assert (
        _compute_turnover(
            traded_notional=300.0,
            equity_curve=(EquityPoint(ts=base_ts, equity=0.0),),
        )
        is None
    )


def test_trade_stats_capture_fees_slippage_and_realized_pnl(tmp_path) -> None:
    """Reconstruct round-trip costs and realized PnL from persisted execution events."""
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
    assert stats.turnover == pytest.approx(
        (100.1 + 109.89) / ((1000.0 + 1009.59) / 2.0)
    )
    assert len(stats.trades) == 2
    assert stats.trades[0].realized_pnl is None
    assert stats.trades[1].realized_pnl == pytest.approx(9.59)


def test_trade_stats_from_events_is_database_free_and_deterministic() -> None:
    """Compute deterministic trade statistics directly from normalized order and fill events."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    stats = _compute_trade_stats_from_events(
        order_events=(
            _OrderAccountingEvent("cid_buy", "AAPL", "buy", "cycle_1"),
            _OrderAccountingEvent("cid_buy", "AAPL", "buy", "duplicate_ignored"),
            _OrderAccountingEvent("cid_sell", "AAPL", "sell", "cycle_2"),
        ),
        fill_events=(
            _FillAccountingEvent("cid_buy", base_ts, 1.0, 100.1, 100.0, 0.1, 0.1),
            _FillAccountingEvent("cid_sell", base_ts, 1.0, 109.89, 110.0, 0.1, 0.11),
        ),
        equity_curve=(
            EquityPoint(ts=base_ts, equity=1000.0),
            EquityPoint(ts=base_ts, equity=1009.59),
        ),
    )

    assert stats.trade_count == 1
    assert stats.hit_rate == 1.0
    assert stats.realized_pnl == pytest.approx(9.59)
    assert stats.total_fees == pytest.approx(0.2)
    assert stats.total_slippage == pytest.approx(0.21)
    assert len(stats.trades) == 2
    assert stats.trades[0].cycle_id == "cycle_1"
    assert stats.trades[1].realized_pnl == pytest.approx(9.59)


def test_trade_stats_from_events_ignores_unmatched_and_invalid_fills() -> None:
    """Exclude fills lacking order identity or a positive quantity and price."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    stats = _compute_trade_stats_from_events(
        order_events=(_OrderAccountingEvent("cid_valid", "AAPL", "buy", "cycle_1"),),
        fill_events=(
            _FillAccountingEvent(None, base_ts, 1.0, 100.0, None, 0.0, 0.0),
            _FillAccountingEvent("missing_order", base_ts, 1.0, 100.0, None, 0.0, 0.0),
            _FillAccountingEvent("cid_valid", base_ts, 0.0, 100.0, None, 0.0, 0.0),
            _FillAccountingEvent("cid_valid", base_ts, 1.0, 0.0, None, 0.0, 0.0),
        ),
        equity_curve=(EquityPoint(ts=base_ts, equity=1000.0),),
    )

    assert stats.trade_count == 0
    assert stats.realized_pnl is None
    assert stats.total_fees == 0.0
    assert stats.total_slippage == 0.0
    assert stats.trades == ()


def test_summarize_realized_trade_pnls_handles_empty_and_mixed_outcomes() -> None:
    """Summarize wins, losses, flats, expectancy, and profit factor explicitly."""
    empty = _summarize_realized_trade_pnls(())
    assert empty.trade_count == 0
    assert empty.hit_rate is None
    assert empty.realized_pnl is None

    summary = _summarize_realized_trade_pnls((10.0, -4.0, 0.0))

    assert summary.trade_count == 3
    assert summary.hit_rate == pytest.approx(1.0 / 3.0)
    assert summary.avg_win == pytest.approx(10.0)
    assert summary.avg_loss == pytest.approx(-4.0)
    assert summary.profit_factor == pytest.approx(2.5)
    assert summary.expectancy == pytest.approx((1.0 / 3.0 * 10.0) + (2.0 / 3.0 * -4.0))
    assert summary.realized_pnl == pytest.approx(6.0)


def test_summarize_realized_trade_pnls_leaves_profit_factor_empty_without_losses() -> (
    None
):
    """Leave profit factor undefined when realized outcomes contain no losses."""
    summary = _summarize_realized_trade_pnls((2.0, 3.0))

    assert summary.trade_count == 2
    assert summary.hit_rate == 1.0
    assert summary.profit_factor is None
    assert summary.expectancy == pytest.approx(2.5)
    assert summary.realized_pnl == pytest.approx(5.0)


def test_trade_stats_partial_fill_keeps_open_position_without_realized_pnl(
    tmp_path,
) -> None:
    """Record a partial opening fill without inventing a completed trade outcome."""
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

    stats = _compute_trade_stats(
        store, "run_1", [EquityPoint(ts=base_ts, equity=1000.0)]
    )

    assert stats is not None
    assert stats.trade_count == 0
    assert stats.realized_pnl is None
    assert len(stats.trades) == 1
    assert stats.trades[0].fill_qty == 1.0


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
