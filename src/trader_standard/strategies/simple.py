"""Simple strategy implementation.

This is the minimal portfolio-unaware strategy for Stage 0:
- uses a `SignalGenerator` to compute signal values,
- persists `signal_events`,
- emits basic buy/sell market orders from the primary signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import AsyncIterator, Mapping, Sequence

from trader.data import EventStore
from trader.portfolio import Portfolio
from trader.signal_generators import SignalGenerator
from trader.strategies import Strategy


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SimpleStrategy(Strategy):
    """Minimal strategy that turns signal outputs into buy/sell market orders."""

    signal_generator: SignalGenerator
    primary_signal: str
    target_qty_when_positive: float = 1.0

    @property
    def strategy_id(self) -> str:
        """Return the strategy identifier."""
        return "simple"

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
        logger.info(
            "Generating orders strategy=%s run_id=%s symbols=%s",
            self.strategy_id,
            run_id,
            ",".join(self.signal_generator.symbols) if hasattr(self.signal_generator, "symbols") else "<unknown>",
        )
        by_symbol = self.signal_generator.generate(
            as_of_ts=decision_ts,
            run_id=run_id,
            cycle_id=cycle_id,
        )
        orders = self._orders_from_signals(
            by_symbol,
            run_id=run_id,
            cycle_id=cycle_id,
            event_store=event_store,
        )
        logger.info("Orders generated count=%s", len(orders))
        return orders

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
        """Generate candidate orders for a single symbol."""
        if getattr(self.signal_generator, "supports_symbol_generation", False):
            signals = self.signal_generator.generate_for_symbol(
                symbol,
                as_of_ts=decision_ts,
                run_id=run_id,
                cycle_id=cycle_id,
            )
            if not signals:
                return []
            return self._orders_from_signals(
                {symbol: signals},
                run_id=run_id,
                cycle_id=cycle_id,
                event_store=event_store,
            )
        orders = self.generate_orders(
            run_id=run_id,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            event_store=event_store,
            portfolio=portfolio,
        )
        symbol_norm = symbol.strip().upper()
        return [
            order
            for order in orders
            if str(order.get("symbol", "")).strip().upper() == symbol_norm
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
        """Stream candidate orders asynchronously."""
        symbols = self.signal_generator.symbols if hasattr(self.signal_generator, "symbols") else ()
        if getattr(self.signal_generator, "supports_symbol_generation", False) and symbols:
            for symbol in symbols:
                signals = self.signal_generator.generate_for_symbol(
                    symbol,
                    as_of_ts=decision_ts,
                    run_id=run_id,
                    cycle_id=cycle_id,
                )
                if not signals:
                    continue
                orders = self._orders_from_signals(
                    {symbol: signals},
                    run_id=run_id,
                    cycle_id=cycle_id,
                    event_store=event_store,
                )
                for order in orders:
                    yield order
        else:
            orders = self.generate_orders(
                run_id=run_id,
                cycle_id=cycle_id,
                decision_ts=decision_ts,
                event_store=event_store,
                portfolio=portfolio,
            )
            for order in orders:
                yield order

    def _orders_from_signals(
        self,
        by_symbol: Mapping[str, Mapping[str, float]],
        *,
        run_id: str,
        cycle_id: str,
        event_store: EventStore,
    ) -> list[Mapping[str, object]]:
        """Handle orders from signals."""
        generated_at = datetime.now(timezone.utc)
        orders: list[Mapping[str, object]] = []
        for symbol, signals in by_symbol.items():
            value = signals.get(self.primary_signal)
            if value is None:
                continue
            logger.debug("Signal value symbol=%s signal=%s value=%s", symbol, self.primary_signal, value)
            if value > 0:
                target_qty = self.target_qty_when_positive
                side = "buy"
            elif value < 0:
                target_qty = self.target_qty_when_positive
                side = "sell"
            else:
                target_qty = 0.0
                side = None
            event_store.record_event(
                "signal_events",
                {
                    "run_id": run_id,
                    "session_id": run_id,
                    "cycle_id": cycle_id,
                    "symbol": symbol,
                    "signal_value": float(value),
                    "target_qty": float(target_qty),
                    "generated_at": generated_at,
                },
            )
            if target_qty <= 0 or side is None:
                continue
            orders.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "qty": float(target_qty),
                    "order_type": "market",
                }
            )
        return orders
