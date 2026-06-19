"""Bollinger Band re-entry signal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from trader.signals import Bar, Signal

from trader_standard.indicators import BollingerBandsIndicator


@dataclass(frozen=True)
class BollingerBandSignal(Signal):
    """Emit long/flat actions from Bollinger lower-band re-entry.

    The signal returns `1.0` when price re-enters above the lower band and
    `-1.0` when price reaches the middle band, otherwise `0.0`.
    """

    indicator: BollingerBandsIndicator

    @property
    def name(self) -> str:
        """Return a parameterized Bollinger signal name for audit and strategy payloads."""
        mult = str(self.indicator.stddev_multiplier).replace(".", "_")
        return f"bollinger_band_{self.indicator.period}_{mult}"

    @property
    def window(self) -> int:
        """Return the indicator window plus one bar required for re-entry detection."""
        return self.indicator.window + 1

    def compute(self, bars: Sequence[Bar]) -> float:
        """Return the latest lower-band re-entry action from current and previous closes.

        Re-entry above the lower band returns `1.0`, reaching the middle band
        returns `-1.0`, and all other states return `0.0`.
        """
        series = self.indicator.compute_series(bars)
        if len(series) < 2:
            raise ValueError("Insufficient bars for Bollinger Band computation")
        current = series[0]
        previous = series[1]
        current_close = float(bars[0].close)
        previous_close = float(bars[1].close)
        if previous_close < previous.lower and current_close >= current.lower:
            return 1.0
        if current_close >= current.middle:
            return -1.0
        return 0.0

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[tuple[str, float, datetime]]:
        """Return current Bollinger band components as timestamped legacy audit tuples for events."""
        series = self.indicator.compute_series(bars)
        if not series:
            raise ValueError("Insufficient bars for Bollinger Band indicator values")
        current = series[0]
        suffix = f"{self.indicator.period}_{str(self.indicator.stddev_multiplier).replace('.', '_')}"
        bar_ts = bars[0].ts
        return (
            (f"bollinger_middle_{suffix}", current.middle, bar_ts),
            (f"bollinger_upper_{suffix}", current.upper, bar_ts),
            (f"bollinger_lower_{suffix}", current.lower, bar_ts),
            (f"bollinger_bandwidth_{suffix}", current.bandwidth, bar_ts),
        )
