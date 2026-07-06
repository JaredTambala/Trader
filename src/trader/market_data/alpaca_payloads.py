"""Pure Alpaca market-data request and payload helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

from alpaca.data.enums import DataFeed
from alpaca.data.requests import (
    CryptoBarsRequest,
    CryptoLatestBarRequest,
    StockBarsRequest,
    StockLatestBarRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from .domain import CryptoBarEvent, StockBarEvent

__all__ = [
    "AlpacaRequestSpec",
    "_bar_value",
    "_build_bars_request",
    "_build_crypto_bars_request",
    "_build_crypto_latest_bar_request",
    "_build_latest_bar_request",
    "_coerce_timestamp",
    "_default_request_spec",
    "_extract_bar_data",
    "_normalize_stock_feed",
    "_optional_float",
    "_serialize_bar",
    "build_alpaca_bar_event",
]


@dataclass(frozen=True)
class AlpacaRequestSpec:
    """Alpaca request strategy used by the polling source.

    Attributes:
        request_builder: Function that builds the alpaca-py request object.
        timeframe: Alpaca timeframe object attached to the request.
        limit: Maximum bars requested per symbol.
        method: Client method family to call, such as latest-bar reads.
        feed: Optional data feed for stock requests.
    """

    request_builder: Callable[[Sequence[str], datetime, datetime, object, int, object | None], object]
    timeframe: object
    limit: int
    method: str
    feed: object | None


def _default_request_spec(asset_class: str, stock_feed: str | None = None) -> AlpacaRequestSpec:
    """Return default request parameters for Alpaca bars."""
    asset_class = asset_class.lower()
    if asset_class in {"crypto", "cryptocurrency"}:
        return AlpacaRequestSpec(
            request_builder=_build_crypto_latest_bar_request,
            timeframe=TimeFrame(amount=1, unit=TimeFrameUnit.Minute),
            limit=1,
            method="latest_bar",
            feed=None,
        )
    feed = _normalize_stock_feed(stock_feed)
    return AlpacaRequestSpec(
        request_builder=_build_latest_bar_request,
        timeframe=TimeFrame(amount=1, unit=TimeFrameUnit.Minute),
        limit=1,
        method="latest_bar",
        feed=feed,
    )


def _build_bars_request(
    symbols: Sequence[str],
    start: datetime,
    end: datetime,
    timeframe: object,
    limit: int,
    feed: object | None,
) -> object:
    """Build a StockBarsRequest for alpaca-py."""
    return StockBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
        feed=feed,
    )


def _build_latest_bar_request(
    symbols: Sequence[str],
    start: datetime,
    end: datetime,
    timeframe: object,
    limit: int,
    feed: object | None,
) -> object:
    """Build a StockLatestBarRequest for alpaca-py."""
    return StockLatestBarRequest(symbol_or_symbols=list(symbols), feed=feed)


def _build_crypto_bars_request(
    symbols: Sequence[str],
    start: datetime,
    end: datetime,
    timeframe: object,
    limit: int,
    feed: object | None,
) -> object:
    """Build a CryptoBarsRequest for alpaca-py."""
    return CryptoBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
    )


def _build_crypto_latest_bar_request(
    symbols: Sequence[str],
    start: datetime,
    end: datetime,
    timeframe: object,
    limit: int,
    feed: object | None,
) -> object:
    """Build a CryptoLatestBarRequest for alpaca-py."""
    return CryptoLatestBarRequest(symbol_or_symbols=list(symbols))


def _extract_bar_data(response: object) -> Mapping[str, Sequence[object]]:
    """Normalize Alpaca responses into a symbol-to-bars mapping."""
    if hasattr(response, "data"):
        return response.data
    if isinstance(response, Mapping):
        return response
    return {}


def build_alpaca_bar_event(
    *,
    asset_class: str,
    symbol: str,
    bar: object,
    ingested_at: datetime,
    timeframe: str,
    source: str = "alpaca",
) -> StockBarEvent | CryptoBarEvent | None:
    """Convert one Alpaca bar payload into a local market-data event."""
    ts_value = _bar_value(bar, "t", ("t", "timestamp", "time"))
    open_value = _bar_value(bar, "o", ("o", "open"))
    high_value = _bar_value(bar, "h", ("h", "high"))
    low_value = _bar_value(bar, "l", ("l", "low"))
    close_value = _bar_value(bar, "c", ("c", "close", "price"))
    volume_value = _bar_value(bar, "v", ("v", "volume"))
    if None in (ts_value, open_value, high_value, low_value, close_value, volume_value):
        return None

    common = dict(
        symbol=symbol,
        ts=_coerce_timestamp(ts_value),
        ingested_at=ingested_at,
        open=float(open_value),
        high=float(high_value),
        low=float(low_value),
        close=float(close_value),
        volume=float(volume_value),
        trade_count=_optional_float(_bar_value(bar, "n", ("n", "trade_count"))),
        vwap=_optional_float(_bar_value(bar, "vw", ("vw", "vwap"))),
        source=source,
    )
    if asset_class in {"crypto", "cryptocurrency"}:
        return CryptoBarEvent(timeframe=timeframe, **common)
    return StockBarEvent(timeframe=timeframe, **common)


def _bar_value(bar: object, attr: str, keys: tuple[str, ...]) -> object | None:
    """Extract a value from bar objects or mappings."""
    if hasattr(bar, attr):
        return getattr(bar, attr)
    for key in keys:
        if hasattr(bar, key):
            return getattr(bar, key)
    if isinstance(bar, Mapping):
        for key in keys:
            if key in bar:
                return bar[key]
    return None


def _coerce_timestamp(value: object) -> datetime:
    """Convert Alpaca timestamp values into UTC datetimes."""
    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, str):
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Unsupported timestamp value")

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _optional_float(value: object) -> float | None:
    """Convert numeric values to float when present."""
    if value is None:
        return None
    return float(value)


def _normalize_stock_feed(feed: str | None) -> DataFeed | None:
    """Normalize stock feed configuration for Alpaca requests."""
    if not feed:
        return None
    feed_value = feed.strip().lower()
    if feed_value == "sip":
        return DataFeed.SIP
    return DataFeed.IEX


def _serialize_bar(bar: object) -> str:
    """Render bar data for logging without raising errors."""
    if isinstance(bar, Mapping):
        return str(bar)
    if hasattr(bar, "__dict__"):
        return str(bar.__dict__)
    return repr(bar)
