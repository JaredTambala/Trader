"""Typed recent-bar reads shared by runtime and replay strategies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, Sequence

from ..signals import Bar
from ..timeframes import normalize_timeframe


@dataclass(frozen=True)
class RecentBarRequest:
    """Describe one bounded, point-in-time recent-bar read."""

    symbol: str
    asset_class: str
    timeframe: str
    as_of_ts: datetime
    limit: int

    def __post_init__(self) -> None:
        """Normalize identifiers and reject an unbounded or ambiguous request."""
        symbol = str(self.symbol).strip().upper()
        asset_class = normalize_asset_class(self.asset_class)
        timeframe = normalize_timeframe(str(self.timeframe).strip())
        if not symbol:
            raise ValueError("recent-bar request symbol is required")
        if not asset_class:
            raise ValueError("recent-bar request asset_class is required")
        if not timeframe:
            raise ValueError("recent-bar request timeframe is required")
        if isinstance(self.limit, bool) or int(self.limit) <= 0:
            raise ValueError("recent-bar request limit must be positive")
        timestamp = self.as_of_ts
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "asset_class", asset_class)
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "as_of_ts", timestamp)
        object.__setattr__(self, "limit", int(self.limit))


class RecentBarReader(Protocol):
    """Read latest-first bars without exposing a persistence implementation."""

    def read(self, request: RecentBarRequest) -> Sequence[Bar]:
        """Return at most ``request.limit`` bars at or before ``request.as_of_ts``."""


def normalize_asset_class(value: str) -> str:
    """Normalize stock and crypto aliases to the bar-table asset classes."""
    normalized = str(value).strip().lower()
    return "crypto" if normalized in {"crypto", "cryptocurrency"} else "stocks"


__all__ = ["RecentBarReader", "RecentBarRequest", "normalize_asset_class"]
