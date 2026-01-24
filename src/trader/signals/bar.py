"""OHLCV bar primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Bar:
    """Normalized OHLCV bar used by bar-based signals."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None
    trade_count: float | None

