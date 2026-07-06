"""Pure portfolio update planning helpers for cycle broker responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

__all__ = ["InternalFillPortfolioApplication", "build_internal_fill_portfolio_application"]


@dataclass(frozen=True)
class InternalFillPortfolioApplication:
    """Normalized portfolio application derived from an internal broker fill."""

    order: Mapping[str, object]
    price_lookup: Mapping[str, float]


def build_internal_fill_portfolio_application(
    *,
    order: Mapping[str, object],
    response: Mapping[str, object],
) -> InternalFillPortfolioApplication | None:
    """Build the portfolio-order input for one internal broker fill response.

    Args:
        order: Enriched order submitted to the internal broker.
        response: Broker response containing optional fill evidence.

    Returns:
        Normalized portfolio application data, or `None` when the response has
        no usable symbol, side, or positive fill quantity.
    """
    fill_qty = response.get("fill_qty", order.get("qty"))
    fill_price = response.get("fill_price", order.get("price"))
    symbol = str(order.get("symbol", "")).strip()
    side = str(order.get("side", "")).lower().strip()
    if not symbol or side not in {"buy", "sell"}:
        return None
    try:
        qty = float(fill_qty) if fill_qty is not None else 0.0
    except (TypeError, ValueError):
        qty = 0.0
    if qty <= 0:
        return None
    price_lookup = {symbol: float(fill_price)} if fill_price is not None else {}
    return InternalFillPortfolioApplication(
        order={
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": fill_price,
            "fee_amount": response.get("fee_amount"),
        },
        price_lookup=price_lookup,
    )
