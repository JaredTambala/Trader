"""Broker interface for order execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping, Sequence


class Broker(ABC):
    """Submits orders to a trading venue or paper broker."""

    @abstractmethod
    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Submit orders and return broker responses."""


class NoOpBroker(Broker):
    """Broker that accepts orders without executing them."""

    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        return []
