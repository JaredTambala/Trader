"""Immutable portfolio value objects used by state-transition logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Position:
    """Position quantity and cost basis for one symbol.

    Attributes:
        symbol: Canonical symbol spelling used by runtime config and brokers.
        qty: Signed position quantity; negative values represent shorts.
        avg_price: Average entry price for the open position when known.
    """

    symbol: str
    qty: float
    avg_price: float | None


@dataclass(frozen=True)
class PortfolioState:
    """Immutable portfolio state used by pure position/cash calculations.

    Attributes:
        positions: Current positions keyed by symbol. Callers may pass any
            mapping; calculation helpers copy before updating.
        cash_balance: Cash balance before applying portfolio decisions.
    """

    positions: Mapping[str, Position]
    cash_balance: float


@dataclass(frozen=True)
class PortfolioOrder:
    """Validated order input for pure portfolio state transitions.

    Attributes:
        symbol: Canonical symbol being traded.
        side: Normalized order side, either `buy` or `sell`.
        qty: Positive order quantity.
        price: Optional execution/reference price used for cash and cost basis.
        fee_amount: Fee charged for the order.
    """

    symbol: str
    side: str
    qty: float
    price: float | None = None
    fee_amount: float = 0.0

    def __post_init__(self) -> None:
        """Validate the normalized order before state transitions use it."""
        if not self.symbol.strip():
            raise ValueError("portfolio order symbol is required")
        if self.side not in {"buy", "sell"}:
            raise ValueError(f"portfolio order side must be buy or sell: {self.side}")
        if self.qty <= 0:
            raise ValueError("portfolio order qty must be positive")

    @property
    def signed_qty_delta(self) -> float:
        """Return the signed position quantity delta represented by the order."""
        return self.qty if self.side == "buy" else -self.qty


@dataclass(frozen=True)
class PortfolioOrderApplication:
    """Result of applying one or more orders to immutable portfolio state.

    Attributes:
        state: Updated portfolio state.
        cash_update_skipped_symbols: Symbols whose cash update was skipped
            because no execution/reference price was available.
    """

    state: PortfolioState
    cash_update_skipped_symbols: tuple[str, ...] = ()


__all__ = [
    "PortfolioOrder",
    "PortfolioOrderApplication",
    "PortfolioState",
    "Position",
]
