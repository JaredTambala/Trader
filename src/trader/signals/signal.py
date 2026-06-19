"""Signal interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Sequence

from trader.indicators import IndicatorObservation

from .bar import Bar


IndicatorAuditValue = IndicatorObservation | tuple[str, float, datetime]


class Signal(ABC):
    """Computes a scalar value from a window of OHLCV bars.

    Signals may compose indicators (e.g., SMA crossover) without caching.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable human-readable signal name used in strategy and audit payloads."""

    @property
    @abstractmethod
    def window(self) -> int:
        """Return the minimum latest-first bar count required before signal computation runs."""

    @abstractmethod
    def compute(self, bars: Sequence[Bar]) -> float:
        """Compute a scalar signal value from a bar window.

        Args:
            bars: Bars in descending timestamp order (latest first).

        Returns:
            Scalar signal value.
        """

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[IndicatorAuditValue]:
        """Return indicator values derived from a bar window.

        Args:
            bars: Bars in descending timestamp order (latest first).

        Returns:
            Sequence of auditable indicator observations or legacy (indicator_name, value, bar_ts) tuples.
        """
        return ()
