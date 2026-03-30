"""MACD helper built from EMA components."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from trader.signals import Bar

from .ema_indicator import EmaIndicator


@dataclass(frozen=True)
class MacdValue:
    """Single aligned MACD observation."""

    macd_line: float
    signal_line: float
    histogram: float


@dataclass(frozen=True)
class MacdIndicator:
    """Compute MACD component series from OHLCV bars."""

    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9

    @property
    def window(self) -> int:
        return int(self.slow_period) + int(self.signal_period) - 1

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[MacdValue]:
        if len(bars) < self.window:
            raise ValueError("Insufficient bars for MACD computation")
        fast_series = list(EmaIndicator(period=self.fast_period).compute_series(bars))
        slow_series = list(EmaIndicator(period=self.slow_period).compute_series(bars))
        aligned_fast = fast_series[: len(slow_series)]
        macd_line = [fast - slow for fast, slow in zip(aligned_fast, slow_series, strict=False)]

        reversed_macd = list(reversed(macd_line))
        signal_values = list(EmaIndicator(period=self.signal_period).compute_series(_bars_from_values(reversed_macd)))
        aligned_macd = macd_line[: len(signal_values)]
        output: list[MacdValue] = []
        for macd, signal in zip(aligned_macd, signal_values, strict=False):
            output.append(MacdValue(macd_line=float(macd), signal_line=float(signal), histogram=float(macd - signal)))
        return output


def _bars_from_values(values: Sequence[float]) -> list[Bar]:
    base = datetime(2000, 1, 1, tzinfo=timezone.utc)
    bars: list[Bar] = []
    for idx, value in enumerate(values):
        ts = base + timedelta(minutes=idx)
        bars.append(
            Bar(
                ts=ts,
                open=float(value),
                high=float(value),
                low=float(value),
                close=float(value),
                volume=0.0,
                vwap=None,
                trade_count=None,
            )
        )
    return list(reversed(bars))
