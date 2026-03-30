"""SMA stretch signal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from trader.signals import Bar, Signal

from trader_standard.indicators import SmaIndicator


@dataclass(frozen=True)
class SmaStretchSignal(Signal):
    """Signal that marks price deviation from a simple moving average."""

    indicator: SmaIndicator
    min_pct_below: float = 0.02
    min_pct_above: float = 0.0

    @property
    def name(self) -> str:
        below = str(self.min_pct_below).replace(".", "_")
        above = str(self.min_pct_above).replace(".", "_")
        return f"sma_stretch_{self.indicator.period}_{below}_{above}"

    @property
    def window(self) -> int:
        return self.indicator.window

    def compute(self, bars: Sequence[Bar]) -> float:
        series = self.indicator.compute_series(bars)
        if not series:
            raise ValueError("Insufficient bars for SMA stretch computation")
        current_sma = series[0]
        current_close = float(bars[0].close)
        if current_close <= current_sma * (1.0 - self.min_pct_below):
            return 1.0
        if current_close >= current_sma * (1.0 + self.min_pct_above):
            return -1.0
        return 0.0

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[tuple[str, float, datetime]]:
        series = self.indicator.compute_series(bars)
        if not series:
            raise ValueError("Insufficient bars for SMA stretch indicator values")
        current_sma = series[0]
        current_close = float(bars[0].close)
        stretch_pct = 0.0 if current_sma == 0.0 else (current_close - current_sma) / current_sma
        bar_ts = bars[0].ts
        return (
            (f"sma_mean_{self.indicator.period}", float(current_sma), bar_ts),
            (f"sma_stretch_pct_{self.indicator.period}", float(stretch_pct), bar_ts),
        )
