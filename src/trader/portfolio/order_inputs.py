"""Pure normalization helpers for raw portfolio order mappings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

__all__ = ["PortfolioOrderInput", "normalize_portfolio_order_inputs"]


@dataclass(frozen=True)
class PortfolioOrderInput:
    """Normalized raw order input ready for portfolio state application."""

    symbol: str
    side: str
    qty: float
    price: float | None
    fee_amount: float


def normalize_portfolio_order_inputs(
    orders: tuple[Mapping[str, object], ...],
    *,
    price_lookup: Mapping[str, float],
) -> tuple[PortfolioOrderInput, ...]:
    """Normalize raw order mappings into typed portfolio order inputs.

    Blank symbols and non-positive quantities are ignored to preserve the
    existing portfolio shell behavior. Invalid quantities and sides fail with
    the same actionable error context as the prior inline normalization.
    """
    normalized: list[PortfolioOrderInput] = []
    for order in orders:
        symbol = str(order.get("symbol", "")).strip()
        side = str(order.get("side", "")).lower().strip()
        qty = order.get("qty", 0.0)
        if not symbol:
            continue
        try:
            qty_float = float(qty)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid qty for order: {order}") from exc
        if qty_float <= 0:
            continue
        if side not in {"buy", "sell"}:
            raise ValueError(f"Invalid side for order: {order}")
        price = order.get("price")
        if price is None:
            price = price_lookup.get(symbol)
        fee_amount = order.get("fee_amount")
        normalized.append(
            PortfolioOrderInput(
                symbol=symbol,
                side=side,
                qty=qty_float,
                price=float(price) if price is not None else None,
                fee_amount=float(fee_amount) if fee_amount is not None else 0.0,
            )
        )
    return tuple(normalized)
