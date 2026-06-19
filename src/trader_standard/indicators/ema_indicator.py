"""Citation-backed exponential moving average implementation.

Source reference:
- Approved method card: ``method_card_ema_seed_v1``.
- Registry method: ``ema``.
- Detailed bibliographic/source evidence belongs in the approved method card and
  citation-validation report used when this implementation is registered.

Implements:
- Entrypoint ``trader_standard.indicators:EmaIndicator``.
- Trader runtime contract ``trader.indicators.Indicator``.
- Input bars are expected latest-first, matching Trader runtime convention.
- The chronological seed is the simple average of the first ``period`` closes.
- Subsequent values use smoothing multiplier ``2 / (period + 1)``.
- Outputs are latest-first and omit warmup observations; fixture validation
  expands warmup nulls for report comparison.
- No lookahead: every output uses only current and earlier chronological closes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from trader.indicators import Indicator
from trader.signals import Bar


@dataclass(frozen=True)
class EmaIndicator(Indicator):
    """Compute no-lookahead exponential moving averages for latest-first bars.

    Warmup observations are omitted from the returned latest-first series.
    """

    period: int

    @property
    def name(self) -> str:
        """Return the registry method name used for EMA audit and manifest metadata."""
        return "ema"

    @property
    def window(self) -> int:
        """Return the configured close-count required to seed the first EMA output value."""
        return int(self.period)

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
        """Compute latest-first EMA values with chronological smoothing and no lookahead.

        Input bars are reversed to seed the earliest complete window, then each
        later close updates the EMA with multiplier `2 / (period + 1)`. Warmup
        values are omitted and the completed series is returned latest-first.
        """
        closes = [float(bar.close) for bar in reversed(bars)]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for EMA computation")
        multiplier = 2.0 / (self.window + 1.0)
        ema_values: list[float] = []
        seed = sum(closes[: self.window]) / self.window
        ema_values.append(seed)
        for close in closes[self.window :]:
            ema_values.append((close - ema_values[-1]) * multiplier + ema_values[-1])
        return list(reversed(ema_values))
