"""Contracts for pure portfolio quantity, average-cost, and cash arithmetic.

Subject: Position adds, reductions, closes, reversals, fee handling, and missing-price cash updates.
Level: Parameterized pure numerical unit contracts.
Collaborators: Real order-math functions supplied only with explicit scalar values.
Guarantees: Long and short transitions use reproducible average costs and side-correct cash movements.
Non-goals: Input parsing, mutable state application, realized PnL, persistence, or execution-price selection.
"""

from __future__ import annotations

import pytest

from trader.portfolio.order_math import cash_balance_after_order, compute_avg_price


@pytest.mark.parametrize(
    ("current_qty", "current_avg", "delta", "new_qty", "price", "expected"),
    [
        (0.0, None, 2.0, 2.0, 100.0, 100.0),
        (2.0, 100.0, 2.0, 4.0, 120.0, 110.0),
        (2.0, 100.0, -1.0, 1.0, 120.0, 100.0),
        (2.0, 100.0, -2.0, 0.0, 120.0, None),
        (2.0, 100.0, -3.0, -1.0, 120.0, 120.0),
        (-2.0, 100.0, -2.0, -4.0, 80.0, 90.0),
        (-2.0, 100.0, 3.0, 1.0, 80.0, 80.0),
        (2.0, 100.0, 1.0, 3.0, None, 100.0),
    ],
)
def test_compute_avg_price_handles_position_transitions(
    current_qty: float,
    current_avg: float | None,
    delta: float,
    new_qty: float,
    price: float | None,
    expected: float | None,
) -> None:
    """Ensure average-cost math handles adds, reductions, closes, and reversals."""
    assert (
        compute_avg_price(
            current_qty=current_qty,
            current_avg_price=current_avg,
            delta=delta,
            new_qty=new_qty,
            price=price,
        )
        == expected
    )


def test_cash_balance_after_order_applies_notional_and_fees() -> None:
    """Ensure cash math handles buy, sell, and missing-price fee-only updates."""
    assert (
        cash_balance_after_order(
            cash_balance=1000.0,
            side="buy",
            qty=2.0,
            price=100.0,
            fee_amount=0.5,
        )
        == 799.5
    )
    assert (
        cash_balance_after_order(
            cash_balance=1000.0,
            side="sell",
            qty=2.0,
            price=100.0,
            fee_amount=0.5,
        )
        == 1199.5
    )
    assert (
        cash_balance_after_order(
            cash_balance=1000.0,
            side="buy",
            qty=2.0,
            price=None,
            fee_amount=0.5,
        )
        == 999.5
    )
