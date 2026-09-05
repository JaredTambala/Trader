"""Citation-backed relative strength index implementation.

Source reference:
- Approved method card: ``method_card_rsi_seed_v1``.
- Registry method: ``rsi``.
- Detailed bibliographic/source evidence belongs in the approved method card and
  citation-validation report used when this implementation is registered.

Implements:
- Entrypoint ``trader_standard.indicators:RsiIndicator``.
- Trader runtime contract ``trader.indicators.Indicator``.
- Input bars are expected latest-first, matching Trader runtime convention.
- Compute close-to-close deltas in chronological order, average the first
  ``period`` gains and losses, then apply Wilder-style recursive smoothing.
- Return ``100 - (100 / (1 + RS))`` where ``RS = avg_gain / avg_loss``; a zero
  average loss returns ``100``.
- Outputs are latest-first and omit the ``period + 1`` warmup window; fixture
  validation expands warmup nulls for report comparison.
- No lookahead: every output uses only current and earlier chronological closes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from trader.indicators import Indicator
from trader.signals import Bar


@dataclass(frozen=True)
class RsiIndicator(Indicator):
    """Compute Wilder-style RSI values from latest-first close bars.

    The output is latest-first and omits the warmup window required to seed
    average gains and losses.
    """

    period: int

    @property
    def name(self) -> str:
        """Return the registry method name used for RSI audit and manifest metadata."""
        return "rsi"

    @property
    def window(self) -> int:
        """Return the close-count required to seed the first RSI output value."""
        return int(self.period) + 1

    def compute_series(self, bars: Sequence[Bar]) -> Sequence[float]:
        """Compute latest-first Wilder RSI values from chronological close deltas.

        The method seeds average gains and losses from the first period, applies
        recursive smoothing for later deltas, treats zero average loss as RSI 100,
        omits warmup observations, and returns completed values latest-first.
        """
        closes = [float(bar.close) for bar in reversed(bars)]
        if len(closes) < self.window:
            raise ValueError("Insufficient bars for RSI computation")

        deltas = [closes[idx] - closes[idx - 1] for idx in range(1, len(closes))]
        gains = [max(delta, 0.0) for delta in deltas]
        losses = [abs(min(delta, 0.0)) for delta in deltas]

        avg_gain = sum(gains[: self.period]) / self.period
        avg_loss = sum(losses[: self.period]) / self.period
        values = [_rsi_value(avg_gain, avg_loss)]

        for idx in range(self.period, len(deltas)):
            avg_gain = ((avg_gain * (self.period - 1)) + gains[idx]) / self.period
            avg_loss = ((avg_loss * (self.period - 1)) + losses[idx]) / self.period
            values.append(_rsi_value(avg_gain, avg_loss))

        return list(reversed(values))


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
