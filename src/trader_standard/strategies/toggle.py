"""Position-toggle strategy for smoke testing paper execution."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Mapping, Sequence

from trader.data import EventStore
from trader.portfolio import Portfolio
from trader.strategies import Strategy
from trader.strategy_metadata import StrategyInfo


logger = logging.getLogger(__name__)


class ToggleUnitStrategy(Strategy):
    """Smoke-test strategy that toggles each symbol between flat and long.

    A flat or short symbol receives a buy for the configured unit size; a long
    symbol receives a sell for the current position quantity.
    """

    def __init__(
        self,
        *,
        symbols: Sequence[str],
        order_qty: float = 1.0,
    ) -> None:
        self._symbols = tuple(symbols)
        self._order_qty = max(0.0, float(order_qty))

    @property
    def strategy_id(self) -> str:
        """Return the stable toggle strategy identifier stored in run metadata and artifacts."""
        return "toggle"

    @property
    def strategy_info(self) -> StrategyInfo:
        """Return toggle strategy metadata, symbols, and unit order sizing for artifacts."""
        return StrategyInfo(
            strategy_id="toggle",
            name="toggle",
            version="1",
            description="Buy when flat and sell when long.",
            parameters={"symbols": list(self._symbols), "order_qty": self._order_qty},
            author="trader_standard",
            source=f"{self.__class__.__module__}.{self.__class__.__qualname__}",
        )

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        """Generate one market order per symbol based on current position state.

        Flat or short symbols receive a configured buy quantity, while long symbols
        receive a sell for the current position quantity so repeated cycles toggle
        between flat and long exposure.
        """
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
