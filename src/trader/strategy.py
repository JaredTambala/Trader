"""Strategy interface and no-op implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping


class Strategy(ABC):
    """Generates trading signals for a defined universe."""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique identifier for the strategy version."""

    @abstractmethod
    def generate_signals(self) -> Iterable[Mapping[str, object]]:
        """Return signal payloads to be validated and routed."""


class NoOpStrategy(Strategy):
    """Strategy that produces no signals."""

    @property
    def strategy_id(self) -> str:
        return "noop"

    def generate_signals(self) -> Iterable[Mapping[str, object]]:
        return []
