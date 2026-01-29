"""Position-toggle strategy for smoke testing paper execution."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Mapping, Sequence

from trader.data import EventStore
from trader.portfolio import Portfolio
from trader.risk import NoOpRiskManager, RiskManager

from .base import Strategy


logger = logging.getLogger(__name__)


class ToggleUnitStrategy(Strategy):
    """Buy one unit when flat, sell one unit when long."""

    def __init__(
        self,
        *,
        symbols: Sequence[str],
        order_qty: float = 1.0,
        risk_manager: RiskManager | None = None,
    ) -> None:
        self._symbols = tuple(symbols)
        self._order_qty = max(0.0, float(order_qty))
        self._risk_manager = risk_manager or NoOpRiskManager()

    @property
    def strategy_id(self) -> str:
        """Return the strategy identifier."""
        return "toggle"

    def get_risk_manager(self) -> RiskManager:
        """Return the risk manager used by this strategy."""
        return self._risk_manager

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        """Generate toggle orders based on current position state."""
        if not self._symbols or self._order_qty <= 0:
            return []
        orders: list[Mapping[str, object]] = []
        for symbol in self._symbols:
            current = portfolio.positions.get(symbol)
            qty = current.qty if current else 0.0
            if qty <= 0:
                orders.append(
                    {
                        "symbol": symbol,
                        "side": "buy",
                        "qty": float(self._order_qty),
                        "order_type": "market",
                    }
                )
            else:
                orders.append(
                    {
                        "symbol": symbol,
                        "side": "sell",
                        "qty": float(qty),
                        "order_type": "market",
                    }
                )
        if orders:
            logger.info("ToggleUnitStrategy emitted orders count=%s", len(orders))
        return orders
