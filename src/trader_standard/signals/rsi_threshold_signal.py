"""RSI threshold signal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from trader.signals import Bar, Signal

from trader_standard.indicators import RsiIndicator


@dataclass(frozen=True)
class RsiThresholdSignal(Signal):
    """Signal that marks oversold and overbought RSI states."""

    indicator: RsiIndicator
    oversold: float = 30.0
    overbought: float = 70.0
    name_override: str | None = None

    @property
    def name(self) -> str:
        if self.name_override:
            return self.name_override
        return (
            f"rsi_threshold_{self.indicator.period}_"
            f"{_format_threshold(self.oversold)}_{_format_threshold(self.overbought)}"
        )

    @property
    def window(self) -> int:
        return self.indicator.window

    def compute(self, bars: Sequence[Bar]) -> float:
        series = self.indicator.compute_series(bars)
        value = series[0]
        if value <= self.oversold:
            return 1.0
        if value >= self.overbought:
            return -1.0
        return 0.0

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[tuple[str, float, datetime]]:
        series = self.indicator.compute_series(bars)
        if not series:
            raise ValueError("Insufficient bars for RSI indicator values")
        return ((f"rsi_{self.indicator.period}", float(series[0]), bars[0].ts),)


def _format_threshold(value: float) -> str:
    return str(value).replace(".", "_")
