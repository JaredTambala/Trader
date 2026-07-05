"""Pure replay helpers for backtest market-data selection and valuation."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from ..market_data import CryptoBarEvent, MarketDataEvent, StockBarEvent
from ..signals import Bar


@dataclass(frozen=True)
class _BacktestBarSelection:
    """Decision for serving one symbol at one backtest timestamp."""

    bar: Bar | None
    warning: str | None
    warning_kind: str | None
    latest_ts: datetime | None = None


@dataclass
class _PriceState:
    """Mutable cursor state for replay portfolio valuation prices."""

    bars_by_symbol: Mapping[str, Sequence[Bar]]
    allow_price_carry_forward: bool = True

    def __post_init__(self) -> None:
        """Normalize derived fields after initialization."""
        self._indices: dict[str, int] = {symbol: 0 for symbol in self.bars_by_symbol}
        self._last_prices: dict[str, float] = {}

    def advance(self, ts: datetime) -> Mapping[str, float]:
        """Advance internal price cursors to a replay timestamp.

        With carry-forward enabled, last known prices remain available until a
        newer bar is seen. Without carry-forward, only exact-timestamp prices
        are returned so valuation gaps stay visible.
        """
        advanced = _advance_price_cursors(
            self.bars_by_symbol,
            indices=self._indices,
            previous_prices=self._last_prices,
            target=ts,
            allow_price_carry_forward=self.allow_price_carry_forward,
        )
        self._indices = dict(advanced.indices)
        self._last_prices = dict(advanced.prices)
        return dict(self._last_prices)


@dataclass(frozen=True)
class _PriceAdvanceResult:
    """Updated price cursor state for one replay timestamp."""

    indices: Mapping[str, int]
    prices: Mapping[str, float]


def _select_backtest_bar(
    *,
    symbol: str,
    bars: Sequence[Bar],
    timestamps: Sequence[datetime],
    target: datetime,
    allow_latest_prior_bar: bool,
) -> _BacktestBarSelection:
    """Select the bar to serve for one symbol at one decision timestamp."""
    target_ts = _normalize_timestamp(target)
    if not timestamps:
        return _BacktestBarSelection(bar=None, warning=None, warning_kind=None)
    idx = bisect_left(timestamps, target_ts)
    if idx < len(timestamps) and timestamps[idx] == target_ts:
        return _BacktestBarSelection(bar=bars[idx], warning=None, warning_kind=None)
    if not allow_latest_prior_bar:
        return _BacktestBarSelection(
            bar=None,
            warning=f"Missing exact bar for {symbol} at {target_ts.isoformat()}; skipped symbol.",
            warning_kind="missing_exact",
        )
    latest_idx = idx - 1
    if latest_idx < 0:
        return _BacktestBarSelection(
            bar=None,
            warning=f"No prior bar available for {symbol} at {target_ts.isoformat()}; skipped symbol.",
            warning_kind="no_prior",
        )
    latest_ts = timestamps[latest_idx]
    return _BacktestBarSelection(
        bar=bars[latest_idx],
        warning=f"Used latest prior bar for {symbol} at {target_ts.isoformat()} from {latest_ts.isoformat()}.",
        warning_kind="latest_prior",
        latest_ts=latest_ts,
    )


def _build_market_event(
    *,
    asset_class: str,
    symbol: str,
    timeframe: str,
    bar: Bar,
    source: str,
    ingested_at: datetime,
) -> MarketDataEvent:
    """Convert a normalized bar into the stock or crypto event-store shape."""
    common = dict(
        symbol=symbol,
        timeframe=timeframe,
        ts=_normalize_timestamp(bar.ts),
        ingested_at=_normalize_timestamp(ingested_at),
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=float(bar.volume),
        trade_count=float(bar.trade_count) if bar.trade_count is not None else None,
        vwap=float(bar.vwap) if bar.vwap is not None else None,
        source=source,
    )
    if asset_class in {"crypto", "cryptocurrency"}:
        return CryptoBarEvent(**common)
    return StockBarEvent(**common)


def _latest_prices_from_bars(bars_by_symbol: Mapping[str, Sequence[Bar]]) -> dict[str, tuple[datetime, float]]:
    """Return latest in-memory close prices per symbol."""
    latest: dict[str, tuple[datetime, float]] = {}
    for symbol, bars in bars_by_symbol.items():
        price = _latest_price_from_bars(bars)
        if price is not None:
            latest[symbol] = price
    return latest


def _latest_price_from_bars(bars: Sequence[Bar]) -> tuple[datetime, float] | None:
    """Return latest close price from an in-memory bar sequence."""
    if not bars:
        return None
    bar = bars[-1]
    return _normalize_timestamp(bar.ts), float(bar.close)


def _advance_price_cursors(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    indices: Mapping[str, int],
    previous_prices: Mapping[str, float],
    target: datetime,
    allow_price_carry_forward: bool,
) -> _PriceAdvanceResult:
    """Advance price cursors without mutating caller-owned state."""
    target_ts = _normalize_timestamp(target)
    if allow_price_carry_forward:
        return _advance_price_cursors_with_carry_forward(
            bars_by_symbol,
            indices=indices,
            previous_prices=previous_prices,
            target=target_ts,
        )
    return _advance_price_cursors_exact(
        bars_by_symbol,
        indices=indices,
        target=target_ts,
    )


def _advance_price_cursors_exact(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    indices: Mapping[str, int],
    target: datetime,
) -> _PriceAdvanceResult:
    """Advance cursors and return only exact-timestamp prices."""
    next_indices: dict[str, int] = {}
    current_prices: dict[str, float] = {}
    for symbol, bars in bars_by_symbol.items():
        idx = indices.get(symbol, 0)
        while idx < len(bars) and _normalize_timestamp(bars[idx].ts) < target:
            idx += 1
        if idx < len(bars) and _normalize_timestamp(bars[idx].ts) == target:
            current_prices[symbol] = float(bars[idx].close)
            idx += 1
        next_indices[symbol] = idx
    return _PriceAdvanceResult(indices=next_indices, prices=current_prices)


def _advance_price_cursors_with_carry_forward(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    indices: Mapping[str, int],
    previous_prices: Mapping[str, float],
    target: datetime,
) -> _PriceAdvanceResult:
    """Advance cursors while keeping latest known prices available."""
    next_indices: dict[str, int] = {}
    current_prices = dict(previous_prices)
    for symbol, bars in bars_by_symbol.items():
        idx = indices.get(symbol, 0)
        while idx < len(bars) and _normalize_timestamp(bars[idx].ts) <= target:
            current_prices[symbol] = float(bars[idx].close)
            idx += 1
        next_indices[symbol] = idx
    return _PriceAdvanceResult(indices=next_indices, prices=current_prices)


def _normalize_timestamp(value: datetime) -> datetime:
    """Normalize timestamp values to UTC-aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
