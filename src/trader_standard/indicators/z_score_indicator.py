"""Citation-backed rolling z-score implementation.

Source reference:
- Approved method card: ``method_card_z_score_seed_v1``.
- Registry method: ``z_score``.
- Detailed bibliographic/source evidence belongs in the approved method card and
  citation-validation report used when this implementation is registered.

Implements:
- Entrypoint ``trader_standard.indicators:ZScoreIndicator``.
- Trader runtime contract ``trader.indicators.Indicator``.
- Input bars are expected latest-first, matching Trader runtime convention.
- For each completed trailing window of ``window_size`` close values, return
  ``(latest_close - mean) / sample_stddev``.
- A zero standard deviation returns ``None`` rather than an unbounded value.
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
class ZScoreIndicator(Indicator):
    """Compute trailing rolling close-price z-scores from latest-first bars.

    Windows with zero standard deviation return `None` instead of infinity.
    """

    window_size: int

    @property
    def name(self) -> str:
        """Return the registry method name used for z-score audit and manifest metadata."""
        return "z_score"

    @property
    def window(self) -> int:
        """Return the configured close-count required for one z-score output value calculation."""
        return int(self.window_size)

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float | None]:
        """Compute latest-first rolling z-scores from chronological close windows.

        For each completed window the latest close is standardized against the
        sample mean and standard deviation; zero-variance windows return `None`,
        warmup observations are omitted, and completed values return latest-first.
        """
        closes = [float(bar.close) for bar in reversed(bars)]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for z-score computation")
        values: list[float | None] = []
        for idx in range(0, len(closes) - self.window + 1):
            window_closes = closes[idx : idx + self.window]
            mean = sum(window_closes) / self.window
            variance = sum((close - mean) ** 2 for close in window_closes) / (self.window - 1)
            stddev = math.sqrt(variance)
            values.append(None if stddev == 0.0 else (window_closes[-1] - mean) / stddev)
        return list(reversed(values))
