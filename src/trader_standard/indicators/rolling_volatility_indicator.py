"""Citation-backed rolling volatility implementation.

Source reference:
- Approved method card: ``method_card_rolling_volatility_seed_v1``.
- Registry method: ``rolling_volatility``.
- Detailed bibliographic/source evidence belongs in the approved method card and
  citation-validation report used when this implementation is registered.

Implements:
- Entrypoint ``trader_standard.indicators:RollingVolatilityIndicator``.
- Trader runtime contract ``trader.indicators.Indicator``.
- Input bars are expected latest-first, matching Trader runtime convention.
- For each completed trailing window of ``window_size`` close values, return
  ``sqrt(sum((close - mean) ** 2) / (window_size - ddof))``.
- ``ddof=1`` is the default sample standard-deviation convention.
- Outputs are latest-first and omit warmup observations; fixture validation
  expands warmup nulls for report comparison.
- No lookahead: every output uses only close values inside its trailing window.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from trader.indicators import Indicator
from trader.signals import Bar


@dataclass(frozen=True)
class RollingVolatilityIndicator(Indicator):
    """Compute trailing close-price standard deviation from latest-first bars.

    The returned series omits warmup windows and uses the configured `ddof`.
    """

    window_size: int
    ddof: int = 1

    @property
    def name(self) -> str:
        """Return the registry method name used for volatility audit and manifest metadata."""
        return "rolling_volatility"

    @property
    def window(self) -> int:
        """Return the configured close-count required for one volatility output value calculation."""
        return int(self.window_size)

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
        """Compute latest-first rolling standard deviation over close-price windows.

        The implementation validates `ddof`, computes variance over each complete
        chronological window, omits warmup observations, and returns the completed
        volatility values in latest-first runtime order.
        """
        closes = [float(bar.close) for bar in reversed(bars)]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for rolling volatility computation")
        if self.ddof < 0 or self.ddof >= self.window:
            raise ValueError("ddof must be non-negative and smaller than window")
        values: list[float] = []
        for idx in range(0, len(closes) - self.window + 1):
            window_closes = closes[idx : idx + self.window]
            mean = sum(window_closes) / self.window
            variance = sum((close - mean) ** 2 for close in window_closes) / (self.window - self.ddof)
            values.append(math.sqrt(variance))
        return list(reversed(values))
