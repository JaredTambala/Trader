"""MACD crossover signal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from trader.signals import Bar, Signal

from trader_standard.indicators import MacdIndicator


@dataclass(frozen=True)
class MacdCrossoverSignal(Signal):
    """Signal that fires when MACD crosses its signal line."""

    indicator: MacdIndicator

    @property
    def name(self) -> str:
        return (
            f"macd_crossover_{self.indicator.fast_period}_"
            f"{self.indicator.slow_period}_{self.indicator.signal_period}"
        )

    @property
    def window(self) -> int:
        return self.indicator.window + 1

    def compute(self, bars: Sequence[Bar]) -> float:
        series = self.indicator.compute_series(bars)
        if len(series) < 2:
            raise ValueError("Insufficient bars for MACD crossover computation")
        prev = series[1]
        current = series[0]
        if prev.macd_line <= prev.signal_line and current.macd_line > current.signal_line:
            return 1.0
        if prev.macd_line >= prev.signal_line and current.macd_line < current.signal_line:
            return -1.0
        return 0.0

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[tuple[str, float, datetime]]:
        series = self.indicator.compute_series(bars)
        if not series:
            raise ValueError("Insufficient bars for MACD indicator values")
        current = series[0]
        suffix = f"{self.indicator.fast_period}_{self.indicator.slow_period}_{self.indicator.signal_period}"
        bar_ts = bars[0].ts
        return (
            (f"macd_line_{suffix}", current.macd_line, bar_ts),
            (f"macd_signal_{suffix}", current.signal_line, bar_ts),
            (f"macd_histogram_{suffix}", current.histogram, bar_ts),
        )
