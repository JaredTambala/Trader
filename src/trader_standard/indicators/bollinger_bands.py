"""Citation-backed Bollinger WMA band-rule implementation.

Source reference:
- Approved method card: ``method_card_bollinger_wma_band_rule_algorithmic_trading_v1``.
- Registry method: ``bollinger_wma_band_rule``.
- Source evidence is from the ingested ``Algorithmic Trading and Quantitative Strategies``
  textbook source and is held in the approved method card plus citation-validation report.

Implements:
- Entrypoint ``trader_standard.indicators:BollingerBandsIndicator``.
- Trader runtime contract ``trader.indicators.Indicator``.
- Input bars are expected latest-first, matching Trader runtime convention.
- For each completed trailing window of ``period`` close values, compute the center band
  as the arithmetic mean, compute the population standard deviation over the same
  window, and set upper/lower bands to ``middle +/- stddev_multiplier * deviation``.
- ``bandwidth`` is reported as ``(upper - lower) / middle`` when ``middle`` is non-zero.
- Outputs are latest-first and omit warmup observations; fixture validation expands
  warmup nulls for report comparison.
- No-lookahead boundary: every output uses only close values inside its trailing
  window and never reads future bars relative to that output timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from trader.indicators import Indicator
from trader.signals import Bar


@dataclass(frozen=True)
class BollingerBandValue:
    """Single aligned Bollinger Band observation."""

    middle: float
    upper: float
    lower: float
    bandwidth: float


@dataclass(frozen=True)
class BollingerBandsIndicator(Indicator):
    """Compute Bollinger Band components from OHLCV bars."""

    period: int = 20
    stddev_multiplier: float = 2.0

    @property
    def name(self) -> str:
        return "bollinger_wma_band_rule"

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
