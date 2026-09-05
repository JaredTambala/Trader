"""Contracts for applying normalized order mappings to immutable portfolio state.

Subject: Multi-order transitions, input immutability, price lookup, cash changes, and missing-price evidence.
Level: Deterministic domain unit contracts.
Collaborators: Real input normalization and transition helpers with fixed portfolio and order mappings.
Guarantees: Mappings yield typed orders and new state while skipped cash updates remain inspectable.
Non-goals: Mutable portfolio methods, broker execution, market-price retrieval, persistence, or realized PnL.
"""

from __future__ import annotations

from trader.portfolio import PortfolioState, Position
from trader.portfolio.transitions import apply_portfolio_order_mappings


def test_apply_portfolio_order_mappings_normalizes_and_applies_orders() -> None:
    """Raw order mappings can be handled without mutating starting state."""
    starting_positions = {"AAPL": Position("AAPL", 2.0, 100.0)}
    state = PortfolioState(positions=starting_positions, cash_balance=1000.0)

    result = apply_portfolio_order_mappings(
        state,
        (
            {"symbol": " AAPL ", "side": "sell", "qty": "1", "fee_amount": "0.5"},
            {"symbol": "MSFT", "side": "buy", "qty": 2, "price": "10"},
        ),
        price_lookup={"AAPL": 120.0},
    )

    assert tuple(order.symbol for order in result.orders) == ("AAPL", "MSFT")
    assert starting_positions["AAPL"] == Position("AAPL", 2.0, 100.0)
    assert result.application.state.positions["AAPL"] == Position("AAPL", 1.0, 100.0)
    assert result.application.state.positions["MSFT"] == Position("MSFT", 2.0, 10.0)
    assert result.application.state.cash_balance == 1099.5


def test_apply_portfolio_order_mappings_reports_missing_prices() -> None:
    """Missing prices still update positions but surface a cash caveat."""
    state = PortfolioState(positions={}, cash_balance=1000.0)

    result = apply_portfolio_order_mappings(
        state,
        ({"symbol": "MSFT", "side": "buy", "qty": 2},),
        price_lookup={},
    )

    assert result.application.state.positions["MSFT"] == Position("MSFT", 2.0, None)
    assert result.application.state.cash_balance == 1000.0
    assert result.application.cash_update_skipped_symbols == ("MSFT",)
