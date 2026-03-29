"""SMA crossover signal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from trader.indicators import SmaIndicator
from .bar import Bar
from .signal import Signal


@dataclass(frozen=True)
class SmaCrossoverSignal(Signal):
    """Signal that fires when short/long SMA cross."""

    short: SmaIndicator
    long: SmaIndicator

    @property
    def name(self) -> str:
        """Return the indicator or signal name."""
        return "sma_crossover"

    @property
    def window(self) -> int:
        """Return the configured window size."""
        return max(self.short.window, self.long.window) + 1

    def compute(self, bars: Sequence[Bar]) -> float:
        """Compute the signal value for the latest data."""
        short_series = self.short.compute_series(bars)
        long_series = self.long.compute_series(bars)
        if len(short_series) < 2 or len(long_series) < 2:
            raise ValueError("Insufficient bars for SMA crossover computation")

        prev_short = short_series[1]
        prev_long = long_series[1]
        current_short = short_series[0]
        current_long = long_series[0]

        if prev_short <= prev_long and current_short > current_long:
            return 1.0
        if prev_short >= prev_long and current_short < current_long:
            return -1.0
        return 0.0

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[tuple[str, float, datetime]]:
        """Return indicator values used to derive the signal."""
        short_series = self.short.compute_series(bars)
        long_series = self.long.compute_series(bars)
        if not short_series or not long_series:
            raise ValueError("Insufficient bars for SMA indicator values")
        bar_ts = bars[0].ts
        return (
            (f"sma_short_{self.short.period}", float(short_series[0]), bar_ts),
            (f"sma_long_{self.long.period}", float(long_series[0]), bar_ts),
        )
