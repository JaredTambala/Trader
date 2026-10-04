"""In-memory recent-bar reads for deterministic backtest replay."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from ..market_data import RecentBarReader, RecentBarRequest
from ..market_data.recent_bars import normalize_asset_class
from ..signals import Bar
from ..timeframes import normalize_timeframe


@dataclass(frozen=True)
class RecentBarReadStats:
    """Counters proving replay bar reads are served without database queries."""

    request_count: int
    bars_returned: int

    @property
    def query_count(self) -> int:
        """Expose the read count using qualification terminology."""
        return self.request_count


class InMemoryRecentBarReader(RecentBarReader):
    """Serve bounded latest-first windows from the runner's loaded bar objects."""

    def __init__(
        self,
        *,
        bars_by_symbol: Mapping[str, Sequence[Bar]],
        asset_class: str,
        timeframe: str,
    ) -> None:
        """Index existing chronological bars without copying the bar objects."""
        self._bars_by_symbol = {
            str(symbol).strip().upper(): bars for symbol, bars in bars_by_symbol.items()
        }
        self._asset_class = normalize_asset_class(asset_class)
        self._timeframe = normalize_timeframe(str(timeframe).strip())
        self._timestamps_by_symbol = {
            str(symbol).strip().upper(): tuple(_normalize_timestamp(bar.ts) for bar in bars)
            for symbol, bars in bars_by_symbol.items()
        }
        self._request_count = 0
        self._bars_returned = 0

    @property
    def stats(self) -> RecentBarReadStats:
        """Return immutable read counters for runtime qualification."""
        return RecentBarReadStats(
            request_count=self._request_count,
            bars_returned=self._bars_returned,
        )

    def read(self, request: RecentBarRequest) -> Sequence[Bar]:
        """Return a latest-first window with strict as-of and warmup semantics."""
        if request.asset_class != self._asset_class:
            raise ValueError(
                f"recent-bar reader asset class mismatch: expected {self._asset_class}, "
                f"received {request.asset_class}"
            )
        if request.timeframe != self._timeframe:
            raise ValueError(
                f"recent-bar reader timeframe mismatch: expected {self._timeframe}, "
                f"received {request.timeframe}"
            )
        symbol = request.symbol
        bars = self._bars_by_symbol.get(symbol, ())
        timestamps = self._timestamps_by_symbol.get(symbol, ())
        self._request_count += 1
        if not bars:
            return ()
        end_index = bisect_right(timestamps, request.as_of_ts)
        if end_index <= 0:
            return ()
        start_index = max(0, end_index - request.limit)
        window = tuple(reversed(bars[start_index:end_index]))
        self._bars_returned += len(window)
        return window


def _normalize_timestamp(value: datetime) -> datetime:
    """Normalize bar timestamps to UTC for bisect comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["InMemoryRecentBarReader", "RecentBarReadStats"]
