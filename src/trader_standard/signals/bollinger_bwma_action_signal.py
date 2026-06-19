"""Citation-backed Bollinger/BWMA band action signal.

Source reference:
- Approved method card: ``method_card_bollinger_bwma_action_signal_algorithmic_trading_v1``.
- Registry method: ``bollinger_bwma_action_signal``.
- Source evidence is from the ingested ``Algorithmic Trading and Quantitative Strategies``
  textbook source and is held in the approved method card plus citation-validation report.

Implements:
- Entrypoint ``trader_standard.signals:BollingerBwmaActionSignal``.
- Trader runtime contract ``trader.signals.Signal``.
- Input bars are expected latest-first, matching Trader runtime convention.
- For the latest completed trailing window of ``period`` close values, compute the
  maintained Bollinger band components and emit ``1.0`` when the latest close is below
  the lower band, ``-1.0`` when it is above the upper band, and ``0.0`` otherwise.
- Warmup behavior requires at least ``period`` observations before any scalar signal is emitted.
- No-lookahead boundary: the scalar output uses only close values inside the latest
  trailing window and never reads future bars relative to the output timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from trader.signals import Bar, Signal

from trader_standard.indicators import BollingerBandsIndicator


@dataclass(frozen=True)
class BollingerBwmaActionSignal(Signal):
    """Emit maintained Bollinger/BWMA band actions from the latest close.

    The scalar is `1.0` below the lower band, `-1.0` above the upper band, and
    `0.0` inside the band.
    """

    period: int = 20
    stddev_multiplier: float = 2.0

    @property
    def name(self) -> str:
        """Return a parameterized Bollinger/BWMA action name for audit and manifest metadata."""
        mult = str(self.stddev_multiplier).replace(".", "_")
        return f"bollinger_bwma_action_{self.period}_{mult}"

    @property
    def window(self) -> int:
        """Return the trailing close-count required before a band action is valid."""
        return int(self.period)

    @property
    def indicator(self) -> BollingerBandsIndicator:
        """Return the maintained Bollinger indicator configured for this signal calculation and audit."""
        return BollingerBandsIndicator(period=self.period, stddev_multiplier=self.stddev_multiplier)

    def compute(self, bars: Sequence[Bar]) -> float:
        """Return the latest band action from the current close and computed bands.

        A close below the lower band returns `1.0`, a close above the upper band
        returns `-1.0`, and a close inside the band returns `0.0`.
        """
        series = self.indicator.compute_series(bars)
        current = series[0]
        current_close = float(bars[0].close)
        if current_close < current.lower:
            return 1.0
        if current_close > current.upper:
            return -1.0
        return 0.0

    def indicator_values(self, bars: Sequence[Bar]) -> Sequence[tuple[str, float, datetime]]:
        """Return current maintained band components as timestamped audit tuples for events."""
        series = self.indicator.compute_series(bars)
        if not series:
            raise ValueError("Insufficient bars for Bollinger/BWMA action signal indicator values")
        current = series[0]
        suffix = f"{self.period}_{str(self.stddev_multiplier).replace('.', '_')}"
        bar_ts = bars[0].ts
        return (
            (f"bollinger_bwma_middle_{suffix}", current.middle, bar_ts),
            (f"bollinger_bwma_upper_{suffix}", current.upper, bar_ts),
            (f"bollinger_bwma_lower_{suffix}", current.lower, bar_ts),
            (f"bollinger_bwma_bandwidth_{suffix}", current.bandwidth, bar_ts),
        )
