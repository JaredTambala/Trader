"""Randomized smoke-test strategy for paper trading."""

from __future__ import annotations

from datetime import datetime
import logging
import random
from typing import Mapping, Sequence

from trader.event_store import EventStore
from trader.portfolio import Portfolio
from trader.strategies import Strategy
from trader.strategy_metadata import StrategyInfo


logger = logging.getLogger(__name__)


class RandomStrategy(Strategy):
    """Connectivity-test strategy that emits bounded random market orders.

    Probabilities are normalized when they sum above one, and an optional RNG
    seed makes smoke tests reproducible.
    """

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
        """Return the stable random strategy identifier stored in run metadata and artifacts."""
        return "random"

    @property
    def strategy_info(self) -> StrategyInfo:
        """Return randomized strategy metadata, probabilities, and configured symbols for run artifacts."""
        return StrategyInfo(
            strategy_id="random",
            name="random",
            version="1",
            description="Randomized connectivity strategy.",
            parameters={
                "symbols": list(self._symbols),
                "order_qty": self._order_qty,
                "buy_probability": self._buy_probability,
                "sell_probability": self._sell_probability,
            },
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
        """Generate bounded random buy/sell market-order intents for configured symbols.

        Each symbol draws once from the configured RNG; buy and sell probabilities
        decide whether to emit a market order, and no order is emitted when the
        roll falls outside both probabilities.
        """
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
