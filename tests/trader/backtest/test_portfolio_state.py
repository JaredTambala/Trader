"""Backtest portfolio initialization and valuation contracts.

Subject: Backtest-only position parsing, selection, initialization, valuation, and benchmark holdings.
Level: Deterministic unit contracts.
Collaborators: Real backtest benchmark and portfolio-state helpers with in-memory core portfolio values.
Guarantees: Portfolio inputs and prices produce explicit immutable holdings, valuations, summaries, and warnings.
Non-goals: Event persistence, replay scheduling, trade matching, performance ratios, or broker execution.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trader.backtest.benchmark import (
    _allocate_buy_hold_cash,
    _compute_equity,
    _compute_portfolio_state_equity,
)
from trader.backtest.portfolio_state import (
    _fill_missing_initial_avg_prices,
    _parse_initial_position,
    _select_positions_for_symbols,
    _summarize_portfolio_positions,
)
from trader.portfolio import Portfolio, PortfolioState, Position


def test_compute_equity_returns_named_valuation_and_skips_unpriced_positions() -> None:
    """Value priced long and short positions while excluding unavailable market prices."""
    portfolio = Portfolio(
        positions={
            "AAPL": Position(symbol="AAPL", qty=2.0, avg_price=90.0),
            "MSFT": Position(symbol="MSFT", qty=-1.0, avg_price=210.0),
            "TSLA": Position(symbol="TSLA", qty=3.0, avg_price=20.0),
        },
        cash_balance=1000.0,
    )

    valuation = _compute_equity(portfolio, {"AAPL": 100.0, "MSFT": 200.0})

    assert valuation.equity == pytest.approx(1000.0)
    assert valuation.net_notional == pytest.approx(0.0)
    assert valuation.gross_notional == pytest.approx(400.0)
    assert valuation.invested_pct == pytest.approx(0.4)


def test_compute_equity_leaves_invested_pct_empty_when_equity_is_zero() -> None:
    """Leave the investment ratio undefined when net portfolio equity is zero."""
    portfolio = Portfolio(
        positions={"AAPL": Position(symbol="AAPL", qty=-1.0, avg_price=100.0)},
        cash_balance=100.0,
    )

    valuation = _compute_equity(portfolio, {"AAPL": 100.0})

    assert valuation.equity == 0.0
    assert valuation.net_notional == pytest.approx(-100.0)
    assert valuation.gross_notional == pytest.approx(100.0)
    assert valuation.invested_pct is None


def test_compute_portfolio_state_equity_uses_immutable_state() -> None:
    """Value an immutable portfolio snapshot using the same signed-exposure rules."""
    state = PortfolioState(
        positions={
            "AAPL": Position(symbol="AAPL", qty=2.0, avg_price=90.0),
            "MSFT": Position(symbol="MSFT", qty=-1.0, avg_price=210.0),
        },
        cash_balance=1000.0,
    )

    valuation = _compute_portfolio_state_equity(state, {"AAPL": 100.0, "MSFT": 200.0})

    assert valuation.equity == pytest.approx(1000.0)
    assert valuation.net_notional == pytest.approx(0.0)
    assert valuation.gross_notional == pytest.approx(400.0)
    assert valuation.invested_pct == pytest.approx(0.4)


def test_allocate_buy_hold_cash_adds_equal_weight_quantities_to_existing_holdings() -> (
    None
):
    """Allocate cash equally across priced symbols while retaining existing quantities."""
    holdings = _allocate_buy_hold_cash(
        holdings={"AAPL": 1.0},
        cash_balance=600.0,
        symbols=("AAPL", "MSFT"),
        first_prices={"AAPL": 100.0, "MSFT": 50.0},
    )

    assert holdings.cash_balance == 0.0
    assert holdings.positions["AAPL"] == pytest.approx(4.0)
    assert holdings.positions["MSFT"] == pytest.approx(6.0)


def test_allocate_buy_hold_cash_preserves_cash_when_no_symbols_have_prices() -> None:
    """Keep benchmark cash uninvested when no requested symbol has a price."""
    holdings = _allocate_buy_hold_cash(
        holdings={"AAPL": 1.0},
        cash_balance=600.0,
        symbols=("AAPL", "MSFT"),
        first_prices={},
    )

    assert holdings.cash_balance == 600.0
    assert holdings.positions == {"AAPL": 1.0}


def test_allocate_buy_hold_cash_preserves_zero_price_allocation_semantics() -> None:
    """Consume the equal allocation while omitting quantities for zero-priced symbols."""
    holdings = _allocate_buy_hold_cash(
        holdings={},
        cash_balance=600.0,
        symbols=("AAPL", "MSFT"),
        first_prices={"AAPL": 0.0, "MSFT": 50.0},
    )

    assert holdings.cash_balance == 0.0
    assert "AAPL" not in holdings.positions
    assert holdings.positions["MSFT"] == pytest.approx(6.0)


def test_parse_initial_position_normalizes_symbol_and_numeric_fields() -> None:
    """Normalize a configured initial position into a typed portfolio value."""
    position = _parse_initial_position(
        {
            "symbol": " aapl ",
            "qty": "2.5",
            "avg_price": "100.25",
        }
    )

    assert position == Position(symbol="AAPL", qty=2.5, avg_price=100.25)


def test_parse_initial_position_rejects_invalid_entries() -> None:
    """Reject malformed initial positions with field-specific configuration errors."""
    with pytest.raises(ValueError, match="entries must be mappings"):
        _parse_initial_position("AAPL")
    with pytest.raises(ValueError, match="requires symbol"):
        _parse_initial_position({"qty": 1.0})
    with pytest.raises(ValueError, match="requires qty"):
        _parse_initial_position({"symbol": "AAPL"})
    with pytest.raises(ValueError, match="Invalid qty"):
        _parse_initial_position({"symbol": "AAPL", "qty": "not-a-number"})
    with pytest.raises(ValueError, match="Invalid avg_price"):
        _parse_initial_position(
            {"symbol": "AAPL", "qty": 1.0, "avg_price": "not-a-number"}
        )


def test_summarize_portfolio_positions_values_longs_shorts_and_unpriced_positions() -> (
    None
):
    """Summarize signed positions while retaining explicit evidence for unpriced holdings."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    summary = _summarize_portfolio_positions(
        (
            Position(symbol="MSFT", qty=-2.0, avg_price=50.0),
            Position(symbol="AAPL", qty=3.0, avg_price=90.0),
            Position(symbol="TSLA", qty=4.0, avg_price=20.0),
        ),
        {
            "AAPL": (base_ts, 100.0),
            "MSFT": (base_ts, 40.0),
        },
    )

    assert summary.position_count == 3
    assert summary.long_positions == 2
    assert summary.short_positions == 1
    assert summary.net_qty == pytest.approx(5.0)
    assert summary.gross_qty == pytest.approx(9.0)
    assert summary.net_notional == pytest.approx(
        (3.0 * 100.0) + (-2.0 * 40.0) + (4.0 * 20.0)
    )
    assert summary.gross_notional == pytest.approx(300.0 + 80.0 + 80.0)
    assert [position.symbol for position in summary.positions] == [
        "AAPL",
        "MSFT",
        "TSLA",
    ]
    assert summary.positions[0].market_value == pytest.approx(300.0)
    assert summary.positions[0].unrealized_pnl == pytest.approx(30.0)
    assert summary.positions[1].market_value == pytest.approx(-80.0)
    assert summary.positions[1].unrealized_pnl == pytest.approx(20.0)
    assert summary.positions[2].last_price is None
    assert summary.positions[2].market_value is None
    assert summary.positions[2].unrealized_pnl is None


def test_summarize_portfolio_positions_leaves_notional_empty_without_price_basis() -> (
    None
):
    """Leave notional values undefined when neither market nor entry price exists."""
    summary = _summarize_portfolio_positions(
        (Position(symbol="AAPL", qty=3.0, avg_price=None),),
        {},
    )

    assert summary.position_count == 1
    assert summary.net_qty == pytest.approx(3.0)
    assert summary.gross_qty == pytest.approx(3.0)
    assert summary.net_notional is None
    assert summary.gross_notional is None
    assert summary.positions[0].last_price is None
    assert summary.positions[0].market_value is None


def test_select_positions_for_symbols_reports_ignored_positions_without_logging() -> (
    None
):
    """Return selected positions and ignored symbols as data instead of logging."""
    positions = (
        Position(symbol="AAPL", qty=1.0, avg_price=100.0),
        Position(symbol="MSFT", qty=2.0, avg_price=50.0),
        Position(symbol="TSLA", qty=3.0, avg_price=20.0),
    )

    selection = _select_positions_for_symbols(positions, {"AAPL", "TSLA"})

    assert selection.selected == (positions[0], positions[2])
    assert selection.ignored_symbols == ("MSFT",)


def test_select_positions_for_symbols_keeps_all_positions_when_universe_is_empty() -> (
    None
):
    """Treat an empty requested universe as no position-selection restriction."""
    positions = (
        Position(symbol="AAPL", qty=1.0, avg_price=100.0),
        Position(symbol="MSFT", qty=2.0, avg_price=50.0),
    )

    selection = _select_positions_for_symbols(positions, set())

    assert selection.selected == positions
    assert selection.ignored_symbols == ()


def test_fill_missing_initial_avg_prices_uses_first_prices_without_mutation() -> None:
    """Fill available entry prices on new values without mutating configured positions."""
    positions = (
        Position(symbol="AAPL", qty=1.0, avg_price=None),
        Position(symbol="MSFT", qty=2.0, avg_price=55.0),
        Position(symbol="TSLA", qty=3.0, avg_price=None),
    )

    result = _fill_missing_initial_avg_prices(positions, {"AAPL": 100.0})

    assert result.positions == (
        Position(symbol="AAPL", qty=1.0, avg_price=100.0),
        Position(symbol="MSFT", qty=2.0, avg_price=55.0),
        Position(symbol="TSLA", qty=3.0, avg_price=None),
    )
    assert result.missing_price_symbols == ("TSLA",)
    assert positions[0].avg_price is None


def test_fill_missing_initial_avg_prices_reports_all_unresolved_symbols() -> None:
    """Report every initial holding whose entry price remains unresolved."""
    result = _fill_missing_initial_avg_prices(
        (
            Position(symbol="AAPL", qty=1.0, avg_price=None),
            Position(symbol="MSFT", qty=2.0, avg_price=None),
        ),
        {},
    )

    assert result.positions == (
        Position(symbol="AAPL", qty=1.0, avg_price=None),
        Position(symbol="MSFT", qty=2.0, avg_price=None),
    )
    assert result.missing_price_symbols == ("AAPL", "MSFT")
