"""MACD crossover signal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from trader.indicators import IndicatorObservation
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

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[IndicatorObservation]:
        series = self.indicator.compute_series(bars)
        if not series:
            raise ValueError("Insufficient bars for MACD indicator values")
        current = series[0]
        suffix = f"{self.indicator.fast_period}_{self.indicator.slow_period}_{self.indicator.signal_period}"
        return (
            IndicatorObservation(
                indicator_name=f"macd_{suffix}",
                ts=bars[0].ts,
                value=current.histogram,
                payload={
                    "fast_period": self.indicator.fast_period,
                    "slow_period": self.indicator.slow_period,
                    "signal_period": self.indicator.signal_period,
                    "macd_line": current.macd_line,
                    "signal_line": current.signal_line,
                    "histogram": current.histogram,
                },
            ),
        )
