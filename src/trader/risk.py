"""Risk management interface for pre-trade validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping, Sequence


class RiskManager(ABC):
    """Validates candidate orders against risk limits."""

    @abstractmethod
    def validate(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Return only the orders that pass risk checks."""


class NoOpRiskManager(RiskManager):
    """Risk manager that allows all orders."""

    def validate(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        return list(orders)
