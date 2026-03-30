"""Bollinger Band helpers."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from trader.signals import Bar


@dataclass(frozen=True)
class BollingerBandValue:
    """Single aligned Bollinger Band observation."""

    middle: float
    upper: float
    lower: float
    bandwidth: float


@dataclass(frozen=True)
class BollingerBandsIndicator:
    """Compute Bollinger Band components from OHLCV bars."""

    period: int = 20
    stddev_multiplier: float = 2.0

    @property
    def window(self) -> int:
        return int(self.period)

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[BollingerBandValue]:
        closes = [float(bar.close) for bar in bars]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for Bollinger Band computation")
        values: list[BollingerBandValue] = []
        for idx in range(0, len(closes) - self.window + 1):
            window_closes = closes[idx : idx + self.window]
            middle = sum(window_closes) / self.window
            variance = sum((close - middle) ** 2 for close in window_closes) / self.window
            deviation = math.sqrt(variance)
            upper = middle + self.stddev_multiplier * deviation
            lower = middle - self.stddev_multiplier * deviation
            bandwidth = 0.0 if middle == 0.0 else (upper - lower) / middle
            values.append(
                BollingerBandValue(
                    middle=float(middle),
                    upper=float(upper),
                    lower=float(lower),
                    bandwidth=float(bandwidth),
                )
            )
        return values
