"""Pure portfolio order arithmetic helpers."""

from __future__ import annotations

__all__ = ["cash_balance_after_order", "compute_avg_price"]


def compute_avg_price(
    *,
    current_qty: float,
    current_avg_price: float | None,
    delta: float,
    new_qty: float,
    price: float | None,
) -> float | None:
    """Compute average entry price after a position quantity change.

    Adding to an existing position recalculates weighted average cost. Reducing
    without crossing zero preserves the prior cost basis, closing returns
    `None`, and crossing sides starts the new position at the execution price.
    """
    if new_qty == 0:
        return None
    if price is None:
        return current_avg_price
    if current_qty == 0 or current_avg_price is None:
        return price

    adding_same_side = (current_qty > 0 and delta > 0) or (current_qty < 0 and delta < 0)
    if adding_same_side:
        return ((current_qty * current_avg_price) + (delta * price)) / new_qty

    reducing = abs(delta) < abs(current_qty)
    if reducing:
        return current_avg_price

    return price


def cash_balance_after_order(
    *,
    cash_balance: float,
    side: str,
    qty: float,
    price: float | None,
    fee_amount: float,
) -> float:
    """Return cash balance after one order without mutating portfolio state."""
    if price is None:
        return cash_balance - fee_amount

    notional = qty * price
    if side == "buy":
        return cash_balance - notional - fee_amount
    return cash_balance + notional - fee_amount
