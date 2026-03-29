"""Indicator primitives for derived time-series values."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from trader.signals.bar import Bar


class Indicator(ABC):
    """Compute derived values from a sequence of bars."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable indicator name."""

    @property
    @abstractmethod
    def window(self) -> int:
        """Number of bars required to compute the indicator."""

    @abstractmethod
    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
        """Compute a series of indicator values aligned with the bars.

        Args:
            bars: Bars in descending timestamp order (latest first).

        Returns:
            Sequence of indicator values aligned to bar indices (latest first).
        """
