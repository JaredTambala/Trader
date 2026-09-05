"""OHLCV bar primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Bar:
    """Normalized OHLCV input consumed by indicators and strategies.

    Bars are generally passed latest-first. Optional `vwap` and `trade_count`
    fields preserve provider details when available without forcing every data
    source to supply them.
    """

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None
    trade_count: float | None
