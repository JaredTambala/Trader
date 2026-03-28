"""Strategy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncIterator, Mapping, Sequence

from trader.data import EventStore
from trader.portfolio import Portfolio


class Strategy(ABC):
    """Produces broker-ready orders from data, signals, and portfolio state."""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique identifier for the strategy version."""

    @abstractmethod
    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        """Generate broker-ready order intents for the current decision point."""

    def generate_orders_for_symbol(
        self,
        symbol: str,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> Sequence[Mapping[str, object]]:
        """Generate order intents for a single symbol."""
        return [
            order
            for order in self.generate_orders(
                run_id=run_id,
                cycle_id=cycle_id,
                decision_ts=decision_ts,
                event_store=event_store,
                portfolio=portfolio,
            )
            if str(order.get("symbol", "")).strip().upper() == symbol.strip().upper()
        ]

    async def order_stream(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> AsyncIterator[Mapping[str, object]]:
        """Yield order intents as soon as they are produced."""
        for order in self.generate_orders(
            run_id=run_id,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            event_store=event_store,
            portfolio=portfolio,
        ):
            yield order

    async def order_stream_for_symbol(
        self,
        symbol: str,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store: EventStore,
        portfolio: Portfolio,
    ) -> AsyncIterator[Mapping[str, object]]:
        """Yield order intents for a single symbol as soon as they are produced."""
        for order in self.generate_orders_for_symbol(
            symbol,
            run_id=run_id,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            event_store=event_store,
            portfolio=portfolio,
        ):
            yield order
