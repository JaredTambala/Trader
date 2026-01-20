"""Risk management interface for pre-trade validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping, Sequence


class RiskManager(ABC):
    """Validates candidate orders against risk limits."""

    @abstractmethod
    def validate(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Return only the orders that pass risk checks.

        Args:
            orders: Iterable of candidate order payloads.

        Returns:
            Sequence of orders that passed validation.

        Raises:
            Exception: Implementations may raise on validation errors.
        """


class NoOpRiskManager(RiskManager):
    """Risk manager that allows all orders."""

    def validate(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Return all orders unchanged.

        Args:
            orders: Iterable of candidate order payloads.

        Returns:
            List of all orders.

        Raises:
            None.
        """
        return list(orders)
