"""No-op strategy implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from trader.data import EventStore
from trader.portfolio import Portfolio
from trader.strategies import Strategy
from trader.strategy_metadata import StrategyInfo


class NoOpStrategy(Strategy):
    """Strategy implementation that intentionally emits no orders.

    It is used for infrastructure tests, dry runs, and backtests where the
    surrounding runtime behavior is under test instead of strategy logic.
    """

    @property
    def strategy_id(self) -> str:
        """Return the stable no-op strategy identifier stored in run metadata and artifacts."""
        return "noop"

    @property
    def strategy_info(self) -> StrategyInfo:
        """Return structured no-op strategy metadata for run persistence and artifact exports."""
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
        """Return no candidate orders for every decision point and portfolio state."""
        return []
