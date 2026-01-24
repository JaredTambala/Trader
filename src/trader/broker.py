"""Broker interface for order execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
import uuid
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from .identifiers import deterministic_client_order_id


class Broker(ABC):
    """Submits orders to a trading venue or paper broker."""

    @abstractmethod
    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Submit orders and return broker responses.

        Args:
            orders: Iterable of order payloads ready for execution.

        Returns:
            Sequence of broker response payloads.

        Raises:
            Exception: Implementations raise if submission fails or is rejected.
        """


class NoOpBroker(Broker):
    """Broker that accepts orders without executing them."""

    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Accept orders without executing them.

        Args:
            orders: Iterable of order payloads.

        Returns:
            An empty list, since no orders are actually submitted.

        Raises:
            None.
        """
        return []


class InternalPaperBroker(Broker):
    """Deterministic paper broker that fills immediately at the provided price."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self._logger = logging.getLogger(__name__)

    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Submit orders to the broker backend."""
        responses: list[Mapping[str, object]] = []
        timestamp = datetime.now(timezone.utc)
        for order in orders:
            symbol = str(order.get("symbol", "")).strip().upper()
            side = str(order.get("side", "")).lower().strip()
            qty = float(order.get("qty", 0.0) or 0.0)
            run_id = order.get("run_id")
            cycle_id = order.get("cycle_id")
            price = order.get("price")
            if not symbol or side not in {"buy", "sell"} or qty <= 0:
                self._logger.warning("Skipping invalid order payload=%s", order)
                continue
            if cycle_id is None:
                raise ValueError("cycle_id is required for internal broker orders")
            client_order_id = order.get("client_order_id") or deterministic_client_order_id(
                str(cycle_id),
                symbol,
                side,
                qty,
            )
            status = "filled" if price is not None else "error"
            created_at = order.get("created_at") or timestamp
            fill_price = float(price) if price is not None else None
            if fill_price is None:
                self._logger.warning("Missing price for order; fill skipped symbol=%s", symbol)
            responses.append(
                {
                    "order_event_id": f"order_evt_{uuid.uuid4().hex}",
                    "client_order_id": client_order_id,
                    "run_id": run_id,
                    "cycle_id": cycle_id,
                    "symbol": symbol,
                    "status": status,
                    "broker_order_id": None,
                    "order_type": str(order.get("order_type", "market")),
                    "qty": qty,
                    "fill_ts": created_at,
                    "fill_qty": qty if fill_price is not None else None,
                    "fill_price": fill_price,
                }
            )
        return responses
