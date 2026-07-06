"""Pure payload and window helpers for market-data backfills."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import calendar
import re
from typing import Mapping, Sequence

from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame

from ..timeframes import parse_timeframe
from .domain import CryptoBarEvent, StockBarEvent

__all__ = [
    "_bar_value",
    "_build_bar_event",
    "_coerce_timestamp",
    "_normalize_bars",
    "_normalize_stock_feed",
    "_optional_float",
    "_parse_datetime",
    "_parse_symbols_value",
    "_parse_timeframe",
    "_resolve_since",
    "_resolve_window_from_config",
    "_subtract_months",
]


def _normalize_bars(bars: object) -> Sequence[object]:
    """Normalize bar collections into a sequence."""
    if isinstance(bars, Sequence) and not isinstance(bars, (str, bytes)):
        return bars
    return [bars]


def _build_bar_event(
    asset_class: str,
    symbol: str,
    bar: object,
    ingested_at: datetime,
    source: str,
    timeframe: str | None = None,
) -> StockBarEvent | CryptoBarEvent | None:
    """Convert a bar payload into an event."""
    ts_value = _bar_value(bar, "t", ("t", "timestamp", "time"))
    open_value = _bar_value(bar, "o", ("o", "open"))
    high_value = _bar_value(bar, "h", ("h", "high"))
    low_value = _bar_value(bar, "l", ("l", "low"))
    close_value = _bar_value(bar, "c", ("c", "close", "price"))
    volume_value = _bar_value(bar, "v", ("v", "volume"))
    if None in (ts_value, open_value, high_value, low_value, close_value, volume_value):
        return None

    trade_count = _optional_float(_bar_value(bar, "n", ("n", "trade_count")))
    vwap = _optional_float(_bar_value(bar, "vw", ("vw", "vwap")))
    common = dict(
        symbol=str(symbol),
        ts=_coerce_timestamp(ts_value),
        ingested_at=ingested_at,
        open=float(open_value),
        high=float(high_value),
        low=float(low_value),
        close=float(close_value),
        volume=float(volume_value),
        trade_count=trade_count,
        vwap=vwap,
        source=source,
    )
    if asset_class.lower() in {"crypto", "cryptocurrency"}:
        if not timeframe:
            raise ValueError("timeframe is required for crypto bars")
        return CryptoBarEvent(timeframe=timeframe, **common)
    if not timeframe:
        raise ValueError("timeframe is required for stock bars")
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


def _normalize_stock_feed(feed: str | None) -> DataFeed:
    """Normalize stock feed configuration for Alpaca requests."""
    if not feed:
        return DataFeed.IEX
    feed_value = feed.strip().lower()
    if feed_value == "sip":
        return DataFeed.SIP
    return DataFeed.IEX


def _parse_timeframe(value: str) -> TimeFrame:
    """Parse Alpaca timeframe strings like 5Min, 15T, 1Hour, 1Day, 1Week, 3Month."""
    return parse_timeframe(value)


def _parse_symbols_value(value: object | None) -> list[str] | None:
    """Parse optional backfill symbols from a comma string or sequence."""
    if value is None:
        return None
    if isinstance(value, str):
        symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
        return symbols or None
    if isinstance(value, (list, tuple)):
        symbols = [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
        return symbols or None
    raise ValueError("backfill.symbols must be a string or list")


def _parse_datetime(value: str) -> datetime:
    """Parse ISO datetime config values, accepting a trailing `Z` UTC suffix."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _resolve_window_from_config(backfill: Mapping[str, object], now: datetime) -> tuple[datetime, datetime]:
    """Resolve the backfill window from YAML configuration."""
    start_value = backfill.get("start")
    end_value = backfill.get("end")
    if start_value or end_value:
        if not start_value:
            raise ValueError("backfill.start is required when backfill.end is provided")
        start = _parse_datetime(str(start_value))
        end = _parse_datetime(str(end_value)) if end_value else now
        return start, end
    since = str(backfill.get("since", "60m"))
    return _resolve_since(since, now)


def _resolve_since(value: str, now: datetime) -> tuple[datetime, datetime]:
    """Resolve a single since duration string into a time window."""
    raw = value.strip().lower()
    match = re.match(r"^(\d+)\s*([a-z]+)$", raw)
    if not match:
        raise ValueError(f"Invalid since value: {value}")
    amount = int(match.group(1))
    unit = match.group(2)
    if amount <= 0:
        raise ValueError("since must be positive")
    if unit in {"m", "min", "mins", "minute", "minutes"}:
        return now - timedelta(minutes=amount), now
    if unit in {"h", "hr", "hrs", "hour", "hours"}:
        return now - timedelta(hours=amount), now
    if unit in {"d", "day", "days"}:
        return now - timedelta(days=amount), now
    if unit in {"mo", "mon", "month", "months"}:
        return _subtract_months(now, amount), now
    raise ValueError(f"Invalid since unit: {unit}")


def _subtract_months(value: datetime, months: int) -> datetime:
    """Subtract calendar months from a datetime, clamping to month end."""
    if months <= 0:
        raise ValueError("months must be positive")
    total_months = value.year * 12 + (value.month - 1) - months
    year = total_months // 12
    month = total_months % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(value.day, last_day)
    return value.replace(year=year, month=month, day=day)
