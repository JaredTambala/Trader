"""Citation-backed simple moving average implementation.

Source reference:
- Approved method card: ``method_card_sma_seed_v1``.
- Registry method: ``sma``.
- Detailed bibliographic/source evidence belongs in the approved method card and
  citation-validation report used when this implementation is registered.

Implements:
- Entrypoint ``trader_standard.indicators:SmaIndicator``.
- Trader runtime contract ``trader.indicators.Indicator``.
- Input bars are expected latest-first, matching Trader runtime convention.
- For each completed trailing window of ``period`` close values, return the
  arithmetic mean ``sum(close) / period``.
- Outputs are latest-first and omit warmup observations; fixture validation
  expands warmup nulls for report comparison.
- No lookahead: every output uses only close values inside its trailing window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from trader.indicators import Indicator
from trader.signals import Bar


@dataclass(frozen=True)
class SmaIndicator(Indicator):
    """Compute simple moving averages over trailing latest-first bar windows.

    Returned values align with the latest bar in each completed window.
    """

    period: int

    @property
    def name(self) -> str:
        """Return the registry method name used for SMA audit and manifest metadata."""
        return "sma"

    @property
    def window(self) -> int:
        """Return the configured trailing close-count required for one SMA output value."""
        return int(self.period)

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
        """Compute latest-first SMA values from completed trailing close windows.

        The method raises on insufficient bars, omits warmup observations, and
        returns values aligned to the latest bar in each completed period window.
        """
        closes = [bar.close for bar in bars]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for SMA computation")
        values: list[float] = []
        for idx in range(0, len(closes) - self.window + 1):
            window_closes = closes[idx : idx + self.window]
            values.append(sum(window_closes) / self.window)
        return values
