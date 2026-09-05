"""SMA stretch signal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from trader.signals import Bar, Signal

from trader_standard.indicators import SmaIndicator


@dataclass(frozen=True)
class SmaStretchSignal(Signal):
    """Emit actions from price stretch around a simple moving average.

    Prices sufficiently below the SMA return `1.0`; prices sufficiently above
    return `-1.0`; values inside the band return `0.0`.
    """

    indicator: SmaIndicator
    min_pct_below: float = 0.02
    min_pct_above: float = 0.0

    @property
    def name(self) -> str:
        """Return a parameterized SMA stretch name for strategy and audit event payloads."""
        below = str(self.min_pct_below).replace(".", "_")
        above = str(self.min_pct_above).replace(".", "_")
        return f"sma_stretch_{self.indicator.period}_{below}_{above}"

    @property
    def window(self) -> int:
        """Return the underlying SMA warmup window required for stretch signal evaluation."""
        return self.indicator.window

    def compute(self, bars: Sequence[Bar]) -> float:
        """Return the latest SMA stretch action from close distance to average.

        A close sufficiently below the SMA returns `1.0`, a close sufficiently
        above returns `-1.0`, and a close inside the configured stretch band
        returns `0.0`.
        """
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
        """Return current SMA and stretch percentage as timestamped audit tuples for events."""
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
