"""No-op strategy implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from trader.data import EventStore
from trader.portfolio import Portfolio
from trader.strategies import Strategy
from trader.strategy_metadata import StrategyInfo


class NoOpStrategy(Strategy):
    """Strategy that produces no signals."""

    @property
    def strategy_id(self) -> str:
        """Return the strategy identifier."""
        return "noop"

    @property
    def strategy_info(self) -> StrategyInfo:
        """Return structured strategy metadata."""
        return StrategyInfo(
            strategy_id="noop",
            name="noop",
            version="1",
            description="No-op strategy.",
            parameters={},
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
        """Generate candidate orders for the current data."""
        return []
