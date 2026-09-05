"""EMA crossover signal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from trader.indicators import IndicatorObservation
from trader.signals import Bar, Signal

from trader_standard.indicators import EmaIndicator


@dataclass(frozen=True)
class EmaCrossoverSignal(Signal):
    """Emit actions when fast and slow EMA series cross.

    Crosses above return `1.0`, crosses below return `-1.0`, and unchanged
    ordering returns `0.0`.
    """

    fast: EmaIndicator
    slow: EmaIndicator

    @property
    def name(self) -> str:
        """Return a parameterized signal name for audit, strategy, and metadata payloads."""
        return f"ema_crossover_{self.fast.period}_{self.slow.period}"

    @property
    def window(self) -> int:
        """Return the larger EMA window plus one bar needed to detect a crossover."""
        return max(self.fast.window, self.slow.window) + 1

    def compute(self, bars: Sequence[Bar]) -> float:
        """Return the latest EMA crossover action from current and previous values.

        A fast EMA cross above the slow EMA returns `1.0`, a cross below returns
        `-1.0`, and unchanged ordering returns `0.0`.
        """
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

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[IndicatorObservation]:
        """Return current fast and slow EMA observations for signal audit payloads."""
        fast_series = self.fast.compute_series(bars)
        slow_series = self.slow.compute_series(bars)
        if not fast_series or not slow_series:
            raise ValueError("Insufficient bars for EMA indicator values")
        bar_ts = bars[0].ts
        return (
            IndicatorObservation(
                indicator_name=f"ema_fast_{self.fast.period}",
                ts=bar_ts,
                value=float(fast_series[0]),
                payload={"base_indicator": "ema", "period": self.fast.period, "role": "fast"},
            ),
            IndicatorObservation(
                indicator_name=f"ema_slow_{self.slow.period}",
                ts=bar_ts,
                value=float(slow_series[0]),
                payload={"base_indicator": "ema", "period": self.slow.period, "role": "slow"},
            ),
        )
