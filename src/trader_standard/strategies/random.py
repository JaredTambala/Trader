"""Randomized smoke-test strategy for paper trading."""

from __future__ import annotations

from datetime import datetime
import logging
import random
from typing import Mapping, Sequence

from trader.data import EventStore
from trader.portfolio import Portfolio
from trader.strategies import Strategy


logger = logging.getLogger(__name__)


class RandomStrategy(Strategy):
    """Strategy that emits small random buy/sell orders for connectivity tests."""

    def __init__(
        self,
        *,
        symbols: Sequence[str],
        order_qty: float = 0.001,
        buy_probability: float = 0.45,
        sell_probability: float = 0.45,
        rng_seed: int | None = None,
    ) -> None:
        self._symbols = tuple(symbols)
        self._order_qty = max(0.0, float(order_qty))
        self._buy_probability = max(0.0, float(buy_probability))
        self._sell_probability = max(0.0, float(sell_probability))
        total = self._buy_probability + self._sell_probability
        if total > 1.0:
            self._buy_probability /= total
            self._sell_probability /= total
            logger.warning(
                "RandomStrategy probabilities normalized buy=%s sell=%s",
                self._buy_probability,
                self._sell_probability,
            )
        self._rng = random.Random(rng_seed)

    @property
    def strategy_id(self) -> str:
        """Return the strategy identifier."""
        return "random"

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        """Generate random small orders for smoke testing."""
        if not self._symbols or self._order_qty <= 0:
            return []
        orders: list[Mapping[str, object]] = []
        for symbol in self._symbols:
            roll = self._rng.random()
            if roll < self._buy_probability:
                side = "buy"
            elif roll < self._buy_probability + self._sell_probability:
                side = "sell"
            else:
                continue
            orders.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "qty": float(self._order_qty),
                    "order_type": "market",
                }
            )
        if orders:
            logger.info("RandomStrategy emitted orders count=%s", len(orders))
        return orders
