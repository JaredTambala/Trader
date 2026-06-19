"""Strategy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncIterator, Mapping, Sequence

from trader.data import EventStore
from trader.portfolio import Portfolio


class Strategy(ABC):
    """Contract for turning event-store/portfolio state into order intents.

    Strategies receive run and cycle identifiers so generated orders can be
    traced through risk, broker submission, and event persistence. The base
    class also provides per-symbol and async streaming adapters for realtime
    market-data paths.
    """

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Return the stable strategy/version identifier stored in run metadata and artifacts."""

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
        """Generate order intents for the current decision point.

        Returned mappings should contain at least symbol, side, quantity, and
        order type. The cycle adds traceability, prices, asset class, and
        time-in-force before risk validation and broker submission.
        """

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
        """Generate decision-point orders and keep only the requested canonical symbol.

        The default adapter calls batch generation, then compares symbols
        case-insensitively after trimming whitespace. Strategies with native
        per-symbol logic can override this to avoid computing the full universe.
        """
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
        """Yield batch-generated orders through the async strategy-stream interface.

        Realtime cycle code can consume strategies uniformly as streams while the
        default implementation still delegates to synchronous `generate_orders`.
        """
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
        """Yield per-symbol orders through the async strategy-stream interface.

        The default implementation delegates to `generate_orders_for_symbol`, so
        native per-symbol overrides automatically flow through streaming cycle
        execution as well.
        """
        for order in self.generate_orders_for_symbol(
            symbol,
            run_id=run_id,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            event_store=event_store,
            portfolio=portfolio,
        ):
            yield order
