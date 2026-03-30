"""Simple moving average (SMA) indicator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from trader.indicators import Indicator
from trader.signals import Bar


@dataclass(frozen=True)
class SmaIndicator(Indicator):
    """Compute SMA values for a series of bars."""

    period: int

    @property
    def name(self) -> str:
        """Return the indicator or signal name."""
        return "sma"

    @property
    def window(self) -> int:
        """Return the configured window size."""
        return int(self.period)

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
        """Compute the indicator series from input data."""
        closes = [bar.close for bar in bars]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for SMA computation")
        values: list[float] = []
        for idx in range(0, len(closes) - self.window + 1):
            window_closes = closes[idx : idx + self.window]
            values.append(sum(window_closes) / self.window)
        return values
