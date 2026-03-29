"""Signal interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Sequence

from .bar import Bar


class Signal(ABC):
    """Computes a scalar value from a window of OHLCV bars.

    Signals may compose indicators (e.g., SMA crossover) without caching.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable signal name."""

    @property
    @abstractmethod
    def window(self) -> int:
        """Number of bars required to compute the signal."""

    @abstractmethod
    def compute(self, bars: Sequence[Bar]) -> float:
        """Compute a scalar signal value from a bar window.

        Args:
            bars: Bars in descending timestamp order (latest first).

        Returns:
            Scalar signal value.
        """

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[tuple[str, float, datetime]]:
        """Return indicator values derived from a bar window.

        Args:
            bars: Bars in descending timestamp order (latest first).

        Returns:
            Sequence of (indicator_name, value, bar_ts) tuples.
        """
        return ()
