"""Broker interface for order execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping, Sequence


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
