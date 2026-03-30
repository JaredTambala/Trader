"""EMA crossover signal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from trader.signals import Bar, Signal

from trader_standard.indicators import EmaIndicator


@dataclass(frozen=True)
class EmaCrossoverSignal(Signal):
    """Signal that fires when short/long EMA cross."""

    fast: EmaIndicator
    slow: EmaIndicator

    @property
    def name(self) -> str:
        return f"ema_crossover_{self.fast.period}_{self.slow.period}"

    @property
    def window(self) -> int:
        return max(self.fast.window, self.slow.window) + 1

    def compute(self, bars: Sequence[Bar]) -> float:
        fast_series = self.fast.compute_series(bars)
        slow_series = self.slow.compute_series(bars)
        if len(fast_series) < 2 or len(slow_series) < 2:
            raise ValueError("Insufficient bars for EMA crossover computation")
        prev_fast = fast_series[1]
        prev_slow = slow_series[1]
        current_fast = fast_series[0]
        current_slow = slow_series[0]
        if prev_fast <= prev_slow and current_fast > current_slow:
            return 1.0
        if prev_fast >= prev_slow and current_fast < current_slow:
            return -1.0
        return 0.0

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[tuple[str, float, datetime]]:
        fast_series = self.fast.compute_series(bars)
        slow_series = self.slow.compute_series(bars)
        if not fast_series or not slow_series:
            raise ValueError("Insufficient bars for EMA indicator values")
        bar_ts = bars[0].ts
        return (
            (f"ema_fast_{self.fast.period}", float(fast_series[0]), bar_ts),
            (f"ema_slow_{self.slow.period}", float(slow_series[0]), bar_ts),
        )
