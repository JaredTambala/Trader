"""Strategy interface and no-op implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping


class Strategy(ABC):
    """Generates trading signals for a defined universe."""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique identifier for the strategy version.

        Returns:
            Strategy identifier string.

        Raises:
            None.
        """

    @abstractmethod
    def generate_signals(self) -> Iterable[Mapping[str, object]]:
        """Return signal payloads to be validated and routed.

        Returns:
            Iterable of signal payload mappings.

        Raises:
            Exception: Implementations may raise on data or logic errors.
        """


class NoOpStrategy(Strategy):
    """Strategy that produces no signals."""

    @property
    def strategy_id(self) -> str:
        """Return the no-op strategy identifier.

        Returns:
            Strategy identifier string.

        Raises:
            None.
        """
        return "noop"

    def generate_signals(self) -> Iterable[Mapping[str, object]]:
        """Return an empty signal list.

        Returns:
            Empty iterable.

        Raises:
            None.
        """
        return []
