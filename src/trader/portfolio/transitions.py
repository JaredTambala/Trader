"""Pure portfolio state transitions for validated orders."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Mapping

from .models import PortfolioOrder, PortfolioOrderApplication, PortfolioState, Position
from .order_inputs import normalize_portfolio_order_inputs
from .order_math import cash_balance_after_order, compute_avg_price


@dataclass(frozen=True)
class PortfolioOrderMappingApplication:
    """Result of normalizing raw order mappings and applying them to state.

    Attributes:
        orders: Validated portfolio orders derived from raw input mappings.
        application: Updated state and caveats from applying those orders.
    """

    orders: tuple[PortfolioOrder, ...]
    application: PortfolioOrderApplication


def apply_portfolio_order_mappings(
    state: PortfolioState,
    orders: tuple[Mapping[str, object], ...],
    *,
    price_lookup: Mapping[str, float],
) -> PortfolioOrderMappingApplication:
    """Normalize raw order mappings and apply them without mutating inputs."""
    portfolio_orders = tuple(
        PortfolioOrder(
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=order.price,
            fee_amount=order.fee_amount,
        )
        for order in normalize_portfolio_order_inputs(
            orders,
            price_lookup=price_lookup,
        )
    )
    return PortfolioOrderMappingApplication(
        orders=portfolio_orders,
        application=apply_portfolio_orders(state, portfolio_orders),
    )


def apply_portfolio_orders(
    state: PortfolioState,
    orders: Iterable[PortfolioOrder],
) -> PortfolioOrderApplication:
    """Apply validated orders to portfolio state without mutating inputs.

    Args:
        state: Starting portfolio positions and cash balance.
        orders: Validated orders in execution order.

    Returns:
        Updated state plus cash-update caveats for the imperative shell to log.
    """
    current_state = PortfolioState(positions=dict(state.positions), cash_balance=state.cash_balance)
    skipped_symbols: list[str] = []
    for order in orders:
        result = apply_portfolio_order(current_state, order)
        current_state = result.state
        skipped_symbols.extend(result.cash_update_skipped_symbols)
    return PortfolioOrderApplication(
        state=current_state,
        cash_update_skipped_symbols=tuple(skipped_symbols),
    )


def apply_portfolio_order(
    state: PortfolioState,
    order: PortfolioOrder,
) -> PortfolioOrderApplication:
    """Apply one validated order to portfolio state without side effects.

    The calculation updates quantity, average price, and cash deterministically.
    Missing prices still update positions and fees, but report a skipped cash
    update so callers can decide how to log or surface the caveat.

    Args:
        state: Starting portfolio positions and cash balance.
        order: Validated order to apply.

    Returns:
        Updated portfolio state and any cash-update skipped symbol.
    """
    positions = dict(state.positions)
    current = positions.get(order.symbol, Position(symbol=order.symbol, qty=0.0, avg_price=None))
    delta = order.signed_qty_delta
    new_qty = current.qty + delta
    new_avg = compute_avg_price(
        current_qty=current.qty,
        current_avg_price=current.avg_price,
        delta=delta,
        new_qty=new_qty,
        price=order.price,
    )
    cash_balance = cash_balance_after_order(
        cash_balance=state.cash_balance,
        side=order.side,
        qty=order.qty,
        price=order.price,
        fee_amount=order.fee_amount,
    )

    if abs(new_qty) < 1e-12:
        positions.pop(order.symbol, None)
    else:
        positions[order.symbol] = Position(symbol=order.symbol, qty=new_qty, avg_price=new_avg)

    skipped = (order.symbol,) if order.price is None else ()
    return PortfolioOrderApplication(
        state=PortfolioState(positions=positions, cash_balance=cash_balance),
        cash_update_skipped_symbols=skipped,
    )


__all__ = [
    "PortfolioOrderMappingApplication",
    "apply_portfolio_order",
    "apply_portfolio_order_mappings",
    "apply_portfolio_orders",
]
