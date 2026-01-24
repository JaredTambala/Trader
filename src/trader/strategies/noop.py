"""No-op strategy implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from trader.data import EventStore
from trader.portfolio import Portfolio

from .base import Strategy


class NoOpStrategy(Strategy):
    """Strategy that produces no signals."""

    @property
    def strategy_id(self) -> str:
        """Return the strategy identifier."""
        return "noop"

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
