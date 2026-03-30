"""Exponential moving average (EMA) indicator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from trader.indicators import Indicator
from trader.signals import Bar


@dataclass(frozen=True)
class EmaIndicator(Indicator):
    """Compute EMA values for a series of bars."""

    period: int

    @property
    def name(self) -> str:
        return "ema"

    @property
    def window(self) -> int:
        return int(self.period)

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
        closes = [float(bar.close) for bar in reversed(bars)]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for EMA computation")
        multiplier = 2.0 / (self.window + 1.0)
        ema_values: list[float] = []
        seed = sum(closes[: self.window]) / self.window
        ema_values.append(seed)
        for close in closes[self.window :]:
            ema_values.append((close - ema_values[-1]) * multiplier + ema_values[-1])
        return list(reversed(ema_values))
