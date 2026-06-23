"""Citation-backed historical volatility implementation.

Source reference:
- Approved method card: ``method_card_historical_volatility_larcher_vol2_v1``.
- Registry method: ``historical_volatility_annualized``.
- Detailed bibliographic/source evidence belongs in the approved method card and
  citation-validation report used when this implementation is registered.

Implements:
- Entrypoint ``trader_standard.indicators:HistoricalVolatilityIndicator``.
- Trader runtime contract ``trader.indicators.Indicator``.
- Input bars are expected latest-first, matching Trader runtime convention.
- For each completed trailing window of ``return_window`` continuous returns,
  return the sample standard deviation multiplied by
  ``sqrt(annualization_factor)``.
- Warmup behavior: the first emitted value needs ``return_window + 1`` close
  prices, so fixture validation expands ``return_window`` warmup nulls.
- No lookahead: every output uses only closes ending at that output timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from trader.indicators import Indicator
from trader.signals import Bar


@dataclass(frozen=True)
class HistoricalVolatilityIndicator(Indicator):
    """Compute annualized rolling volatility from continuous close-to-close returns."""

    return_window: int
    annualization_factor: float = 252.0
    ddof: int = 1

    @property
    def name(self) -> str:
        """Return the registry method name used for historical-volatility audit metadata."""
        return "historical_volatility_annualized"

    @property
    def window(self) -> int:
        """Return the close-count required for the first volatility output value."""
        return int(self.return_window) + 1

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
        """Compute latest-first annualized rolling volatility from log returns.

        The implementation validates the configured degrees of freedom and close
        prices, computes chronological close-to-close log returns, emits one value
        per completed trailing return window, and converts back to latest-first
        runtime order.
        """
        if self.return_window < 2:
            raise ValueError("return_window must be at least 2")
        if self.annualization_factor <= 0.0:
            raise ValueError("annualization_factor must be positive")
        if self.ddof < 0 or self.ddof >= self.return_window:
            raise ValueError("ddof must be non-negative and smaller than return_window")

        closes = [float(bar.close) for bar in reversed(bars)]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for historical volatility computation")
        if any(close <= 0.0 for close in closes):
            raise ValueError("historical volatility requires positive close prices")

        returns = [
            math.log(current / previous)
            for previous, current in zip(closes, closes[1:], strict=False)
        ]
        annualization_scale = math.sqrt(float(self.annualization_factor))
        values: list[float] = []
        for idx in range(0, len(returns) - self.return_window + 1):
            window_returns = returns[idx : idx + self.return_window]
            mean = sum(window_returns) / self.return_window
            variance = sum((item - mean) ** 2 for item in window_returns) / (self.return_window - self.ddof)
            values.append(math.sqrt(variance) * annualization_scale)
        return list(reversed(values))
