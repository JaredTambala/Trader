"""Pure market-data query value objects and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from ..symbols import canonicalize_symbol, normalize_asset_class
from ..timeframes import normalize_timeframe


MAX_BAR_QUERY_SYMBOLS = 20
DEFAULT_BAR_FETCH_LIMIT = 1_000
MAX_BAR_FETCH_LIMIT = 10_000
DEFAULT_SYMBOL_DISCOVERY_LIMIT = 50
MAX_SYMBOL_DISCOVERY_LIMIT = 500

BAR_TABLE_BY_ASSET_CLASS = {
    "stocks": "stock_bar_events",
    "crypto": "crypto_bar_events",
}

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9./_-]{0,31}$")


class MarketDataQueryError(ValueError):
    """Base class for caller-visible market-data query validation failures.

    Query helpers raise this family for bad inputs or unavailable query
    connections so callers can separate user/request failures from storage bugs.
    """


class MarketDataQueryValidationError(MarketDataQueryError):
    """Raised when query symbols, windows, asset class, or limits are invalid."""


class EventStoreConnectionUnavailable(MarketDataQueryError):
    """Raised when a read helper needs SQL access but the store has no connection."""


@dataclass(frozen=True)
class BarQuery:
    """Validated request shape for bar-data reads.

    Attributes:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp.
        end: Inclusive requested end timestamp.
        source: Optional source filter.
        limit: Optional maximum number of bars to fetch.
    """

    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    start: datetime
    end: datetime
    source: str | None = None
    limit: int | None = None


@dataclass(frozen=True)
class BarCount:
    """Row count for one requested symbol."""

    symbol: str
    row_count: int


@dataclass(frozen=True)
class BarRange:
    """Timestamp coverage for one requested symbol."""

    symbol: str
    first_ts: datetime | None
    last_ts: datetime | None


@dataclass(frozen=True)
class BarTimestamp:
    """Timestamp for one fetched bar."""

    symbol: str
    ts: datetime


@dataclass(frozen=True)
class BarSourceCount:
    """Source-level row count for one symbol."""

    symbol: str
    source: str
    row_count: int


@dataclass(frozen=True)
class BarSymbolDiscoveryQuery:
    """Validated request shape for discovering local bar symbols.

    Attributes:
        asset_class: Requested asset class.
        timeframe: Optional bar timeframe filter.
        source: Optional source filter.
        symbols: Optional exact symbols to validate.
        query: Optional case-insensitive symbol substring filter.
        limit: Maximum number of symbols to return.
        include_coverage: Whether local coverage should be returned.
    """

    asset_class: str
    timeframe: str | None = None
    source: str | None = None
    symbols: tuple[str, ...] = tuple()
    query: str | None = None
    limit: int = DEFAULT_SYMBOL_DISCOVERY_LIMIT
    include_coverage: bool = False


@dataclass(frozen=True)
class DiscoveredBarSymbol:
    """Local symbol discovery result with optional coverage metadata for reporting."""

    symbol: str
    row_count: int
    first_ts: datetime | None
    last_ts: datetime | None
    timeframes: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class BarRecord:
    """Single bar record fetched from the event store."""

    symbol: str
    timeframe: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: float | None
    vwap: float | None
    source: str | None


def normalize_bar_query(query: BarQuery, *, default_limit: int | None = None) -> BarQuery:
    """Normalize and validate a bar query.

    Args:
        query: Raw query request.
        default_limit: Optional limit to apply when the request omits one.

    Returns:
        Normalized query with canonical symbols, asset class, timeframe, and UTC timestamps.

    Raises:
        MarketDataQueryValidationError: If the query fields are invalid.
    """
    symbols = tuple(str(symbol).strip() for symbol in query.symbols if str(symbol).strip())
    if not symbols:
        raise MarketDataQueryValidationError("Bar query requires at least one symbol")
    if len(symbols) > MAX_BAR_QUERY_SYMBOLS:
        raise MarketDataQueryValidationError(f"Bar query supports at most {MAX_BAR_QUERY_SYMBOLS} symbols")

    asset_class = normalize_asset_class(query.asset_class)
    if asset_class not in BAR_TABLE_BY_ASSET_CLASS:
        raise MarketDataQueryValidationError(f"Unsupported bar query asset class: {query.asset_class}")

    canonical_symbols = tuple(
        dict.fromkeys(canonicalize_symbol(symbol, asset_class=asset_class) for symbol in symbols)
    )
    invalid_symbols = [symbol for symbol in canonical_symbols if _SYMBOL_RE.fullmatch(symbol) is None]
    if invalid_symbols:
        raise MarketDataQueryValidationError(f"Invalid bar query symbol: {invalid_symbols[0]}")
    try:
        timeframe = normalize_timeframe(query.timeframe)
    except ValueError as exc:
        raise MarketDataQueryValidationError(str(exc)) from exc
    start = _normalize_datetime(query.start)
    end = _normalize_datetime(query.end)
    if end < start:
        raise MarketDataQueryValidationError("Bar query end must be at or after start")

    source = str(query.source).strip() if query.source is not None else None
    limit = _normalize_limit(query.limit, default_limit=default_limit)
    return BarQuery(
        symbols=canonical_symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        start=start,
        end=end,
        source=source or None,
        limit=limit,
    )


def normalize_bar_symbol_discovery_query(query: BarSymbolDiscoveryQuery) -> BarSymbolDiscoveryQuery:
    """Normalize and validate a local symbol discovery query.

    Args:
        query: Raw symbol discovery request.

    Returns:
        Normalized local symbol discovery query.

    Raises:
        MarketDataQueryValidationError: If request fields are invalid.
    """
    asset_class = normalize_asset_class(query.asset_class)
    if asset_class not in BAR_TABLE_BY_ASSET_CLASS:
        raise MarketDataQueryValidationError(f"Unsupported bar query asset class: {query.asset_class}")
    try:
        timeframe = normalize_timeframe(query.timeframe) if query.timeframe is not None else None
    except ValueError as exc:
        raise MarketDataQueryValidationError(str(exc)) from exc
    symbols = tuple(str(symbol).strip() for symbol in query.symbols if str(symbol).strip())
    canonical_symbols = tuple(
        dict.fromkeys(canonicalize_symbol(symbol, asset_class=asset_class) for symbol in symbols)
    )
    invalid_symbols = [symbol for symbol in canonical_symbols if _SYMBOL_RE.fullmatch(symbol) is None]
    if invalid_symbols:
        raise MarketDataQueryValidationError(f"Invalid bar query symbol: {invalid_symbols[0]}")
    query_text = str(query.query).strip().upper() if query.query is not None else None
    source = str(query.source).strip() if query.source is not None else None
    return BarSymbolDiscoveryQuery(
        asset_class=asset_class,
        timeframe=timeframe,
        source=source or None,
        symbols=canonical_symbols,
        query=query_text or None,
        limit=_normalize_symbol_discovery_limit(query.limit),
        include_coverage=bool(query.include_coverage),
    )


def _bar_record_from_row(row: object) -> BarRecord:
    """Build a bar record from a database row.

    Args:
        row: Positional database row.

    Returns:
        Typed bar record.
    """
    values = tuple(row)
    return BarRecord(
        symbol=str(values[0]),
        timeframe=str(values[1]),
        ts=_required_datetime(values[2]),
        open=float(values[3]),
        high=float(values[4]),
        low=float(values[5]),
        close=float(values[6]),
        volume=float(values[7]),
        trade_count=_optional_float(values[8]),
        vwap=_optional_float(values[9]),
        source=str(values[10]) if values[10] is not None else None,
    )


def _discovered_bar_symbol_from_row(row: object, *, include_coverage: bool) -> DiscoveredBarSymbol:
    """Build a discovered symbol record from a database row."""
    values = tuple(row)
    first_ts = _optional_datetime(values[2]) if include_coverage else None
    last_ts = _optional_datetime(values[3]) if include_coverage else None
    timeframes = tuple(item for item in str(values[4] or "").split(",") if item)
    sources = tuple(item for item in str(values[5] or "").split(",") if item)
    return DiscoveredBarSymbol(
        symbol=str(values[0]),
        row_count=int(values[1] or 0),
        first_ts=first_ts,
        last_ts=last_ts,
        timeframes=timeframes,
        sources=sources,
    )


def _normalize_datetime(value: datetime) -> datetime:
    """Normalize a datetime to UTC.

    Args:
        value: Datetime to normalize. Naive datetimes are treated as UTC.

    Returns:
        Timezone-aware UTC datetime.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _required_datetime(value: object) -> datetime:
    """Normalize a required database timestamp to UTC.

    Args:
        value: Database timestamp value.

    Returns:
        Timezone-aware UTC datetime.

    Raises:
        MarketDataQueryValidationError: If the value is missing.
    """
    normalized = _optional_datetime(value)
    if normalized is None:
        raise MarketDataQueryValidationError("Bar record timestamp is missing")
    return normalized


def _optional_datetime(value: object) -> datetime | None:
    """Normalize an optional database timestamp to UTC.

    Args:
        value: Database timestamp value.

    Returns:
        Timezone-aware UTC datetime, or `None` when no timestamp exists.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    return _normalize_datetime(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _optional_float(value: object) -> float | None:
    """Normalize an optional numeric database value.

    Args:
        value: Database numeric value.

    Returns:
        Float value, or `None` when the value is missing.
    """
    if value is None:
        return None
    return float(value)


def _normalize_limit(limit: int | None, *, default_limit: int | None) -> int | None:
    """Normalize and validate an optional fetch limit.

    Args:
        limit: Requested limit.
        default_limit: Limit to use when the request omits one.

    Returns:
        Normalized limit, or `None` for aggregate queries.

    Raises:
        MarketDataQueryValidationError: If the limit is outside the allowed range.
    """
    try:
        normalized = default_limit if limit is None else int(limit)
    except (TypeError, ValueError) as exc:
        raise MarketDataQueryValidationError("Bar fetch limit must be an integer") from exc
    if normalized is None:
        return None
    if normalized < 1:
        raise MarketDataQueryValidationError("Bar fetch limit must be at least 1")
    if normalized > MAX_BAR_FETCH_LIMIT:
        raise MarketDataQueryValidationError(f"Bar fetch limit supports at most {MAX_BAR_FETCH_LIMIT} rows")
    return normalized


def _normalize_symbol_discovery_limit(limit: int | None) -> int:
    """Normalize and validate a symbol discovery limit."""
    try:
        normalized = DEFAULT_SYMBOL_DISCOVERY_LIMIT if limit is None else int(limit)
    except (TypeError, ValueError) as exc:
        raise MarketDataQueryValidationError("Symbol discovery limit must be an integer") from exc
    if normalized < 1:
        raise MarketDataQueryValidationError("Symbol discovery limit must be at least 1")
    if normalized > MAX_SYMBOL_DISCOVERY_LIMIT:
        raise MarketDataQueryValidationError(
            f"Symbol discovery limit supports at most {MAX_SYMBOL_DISCOVERY_LIMIT} symbols"
        )
    return normalized
