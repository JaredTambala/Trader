"""RSI threshold signal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from trader.signals import Bar, Signal

from trader_standard.indicators import RsiIndicator


@dataclass(frozen=True)
class RsiThresholdSignal(Signal):
    """Emit long/exit actions from RSI threshold crossings.

    Values at or below `oversold` return `1.0`; values at or above `overbought`
    return `-1.0`; middle-band values return `0.0`.
    """

    indicator: RsiIndicator
    oversold: float = 30.0
    overbought: float = 70.0
    name_override: str | None = None

    @property
    def name(self) -> str:
        """Return the override or parameterized RSI threshold name for strategy audit payloads."""
        if self.name_override:
            return self.name_override
        return (
            f"rsi_threshold_{self.indicator.period}_"
            f"{_format_threshold(self.oversold)}_{_format_threshold(self.overbought)}"
        )

    @property
    def window(self) -> int:
        """Return the underlying RSI warmup window required for threshold signal evaluation."""
        return self.indicator.window

    def compute(self, bars: Sequence[Bar]) -> float:
        """Return the latest RSI threshold action for oversold, overbought, or neutral.

        The first completed RSI value is compared with configured thresholds:
        oversold returns `1.0`, overbought returns `-1.0`, and middle values return
        `0.0`.
        """
        series = self.indicator.compute_series(bars)
        value = series[0]
        if value <= self.oversold:
            return 1.0
        if value >= self.overbought:
            return -1.0
        return 0.0

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[tuple[str, float, datetime]]:
        """Return the current RSI value as a timestamped legacy audit tuple for events."""
        series = self.indicator.compute_series(bars)
        if not series:
            raise ValueError("Insufficient bars for RSI indicator values")
        return ((f"rsi_{self.indicator.period}", float(series[0]), bars[0].ts),)


def _format_threshold(value: float) -> str:
    return str(value).replace(".", "_")
