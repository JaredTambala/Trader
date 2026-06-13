"""Typed read-only market-data queries over the event store."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from .data import EventStore
from .symbols import canonicalize_symbol, normalize_asset_class
from .timeframes import normalize_timeframe


MAX_BAR_QUERY_SYMBOLS = 20
DEFAULT_BAR_FETCH_LIMIT = 1_000
MAX_BAR_FETCH_LIMIT = 10_000
DEFAULT_SYMBOL_DISCOVERY_LIMIT = 50
MAX_SYMBOL_DISCOVERY_LIMIT = 500
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9./_-]{0,31}$")

_BAR_TABLE_BY_ASSET_CLASS = {
    "stocks": "stock_bar_events",
    "crypto": "crypto_bar_events",
}


class MarketDataQueryError(ValueError):
    """Base error for validated market-data query failures."""


class MarketDataQueryValidationError(MarketDataQueryError):
    """Raised when a market-data query request is invalid."""


class EventStoreConnectionUnavailable(MarketDataQueryError):
    """Raised when an event store cannot provide a queryable connection."""


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
    """Row count for one requested symbol.

    Attributes:
        symbol: Canonical symbol.
        row_count: Number of matching rows.
    """

    symbol: str
    row_count: int


@dataclass(frozen=True)
class BarRange:
    """Timestamp coverage for one requested symbol.

    Attributes:
        symbol: Canonical symbol.
        first_ts: First matching bar timestamp, if rows exist.
        last_ts: Last matching bar timestamp, if rows exist.
    """

    symbol: str
    first_ts: datetime | None
    last_ts: datetime | None


@dataclass(frozen=True)
class BarTimestamp:
    """Timestamp for one fetched bar.

    Attributes:
        symbol: Canonical symbol.
        ts: Bar timestamp.
    """

    symbol: str
    ts: datetime


@dataclass(frozen=True)
class BarSourceCount:
    """Source-level row count for one symbol.

    Attributes:
        symbol: Canonical symbol.
        source: Source label, or `unknown` for rows with no source.
        row_count: Number of matching rows.
    """

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
    """Local symbol discovery result.

    Attributes:
        symbol: Canonical symbol.
        row_count: Number of matching rows.
        first_ts: First matching bar timestamp, if requested.
        last_ts: Last matching bar timestamp, if requested.
        timeframes: Timeframes observed for the matching symbol.
        sources: Source labels observed for the matching symbol.
    """

    symbol: str
    row_count: int
    first_ts: datetime | None
    last_ts: datetime | None
    timeframes: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class BarRecord:
    """Single bar record fetched from the event store.

    Attributes:
        symbol: Canonical symbol.
        timeframe: Canonical timeframe.
        ts: Bar timestamp.
        open: Bar open price.
        high: Bar high price.
        low: Bar low price.
        close: Bar close price.
        volume: Bar volume.
        trade_count: Optional trade count.
        vwap: Optional volume-weighted average price.
        source: Optional source label.
    """

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
    if asset_class not in _BAR_TABLE_BY_ASSET_CLASS:
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


def count_bar_rows(event_store: EventStore, query: BarQuery) -> tuple[BarCount, ...]:
    """Count matching bar rows for each requested symbol.

    Args:
        event_store: Event store exposing a queryable connection.
        query: Bar query request.

    Returns:
        Per-symbol row counts, including zero counts for missing requested symbols.

    Raises:
        EventStoreConnectionUnavailable: If the event store has no query connection.
        MarketDataQueryValidationError: If the query is invalid.
    """
    normalized = normalize_bar_query(query)
    rows = _fetchall(
        _queryable_connection(event_store),
        f"""
        SELECT symbol, COUNT(*) AS row_count
        FROM {_bar_table_name(normalized.asset_class)}
        WHERE {_where_clause(normalized)}
        GROUP BY symbol
        """,
        _where_params(normalized),
    )
    counts = {str(row[0]): int(row[1] or 0) for row in rows}
    return tuple(BarCount(symbol=symbol, row_count=counts.get(symbol, 0)) for symbol in normalized.symbols)


def count_bar_symbols(event_store: EventStore, query: BarQuery) -> int:
    """Count distinct symbols with matching bar rows.

    Args:
        event_store: Event store exposing a queryable connection.
        query: Bar query request.

    Returns:
        Number of distinct matching symbols from the requested universe.

    Raises:
        EventStoreConnectionUnavailable: If the event store has no query connection.
        MarketDataQueryValidationError: If the query is invalid.
    """
    normalized = normalize_bar_query(query)
    row = _fetchone(
        _queryable_connection(event_store),
        f"""
        SELECT COUNT(DISTINCT symbol) AS symbol_count
        FROM {_bar_table_name(normalized.asset_class)}
        WHERE {_where_clause(normalized)}
        """,
        _where_params(normalized),
    )
    return int(row[0] or 0) if row is not None else 0


def fetch_bar_ranges(event_store: EventStore, query: BarQuery) -> tuple[BarRange, ...]:
    """Fetch timestamp coverage for each requested symbol.

    Args:
        event_store: Event store exposing a queryable connection.
        query: Bar query request.

    Returns:
        Per-symbol first and last timestamps, including empty ranges for missing requested symbols.

    Raises:
        EventStoreConnectionUnavailable: If the event store has no query connection.
        MarketDataQueryValidationError: If the query is invalid.
    """
    normalized = normalize_bar_query(query)
    rows = _fetchall(
        _queryable_connection(event_store),
        f"""
        SELECT symbol, MIN(ts) AS first_ts, MAX(ts) AS last_ts
        FROM {_bar_table_name(normalized.asset_class)}
        WHERE {_where_clause(normalized)}
        GROUP BY symbol
        """,
        _where_params(normalized),
    )
    ranges = {
        str(row[0]): BarRange(
            symbol=str(row[0]),
            first_ts=_optional_datetime(row[1]),
            last_ts=_optional_datetime(row[2]),
        )
        for row in rows
    }
    return tuple(
        ranges.get(symbol, BarRange(symbol=symbol, first_ts=None, last_ts=None))
        for symbol in normalized.symbols
    )


def fetch_bar_timestamps(event_store: EventStore, query: BarQuery) -> tuple[BarTimestamp, ...]:
    """Fetch all matching bar timestamps for a validated query.

    Args:
        event_store: Event store exposing a queryable connection.
        query: Bar query request.

    Returns:
        Matching symbol/timestamp pairs ordered by timestamp and symbol.

    Raises:
        EventStoreConnectionUnavailable: If the event store has no query connection.
        MarketDataQueryValidationError: If the query is invalid.
    """
    normalized = normalize_bar_query(query)
    rows = _fetchall(
        _queryable_connection(event_store),
        f"""
        SELECT symbol, ts
        FROM {_bar_table_name(normalized.asset_class)}
        WHERE {_where_clause(normalized)}
        ORDER BY ts ASC, symbol ASC
        """,
        _where_params(normalized),
    )
    return tuple(BarTimestamp(symbol=str(row[0]), ts=_required_datetime(row[1])) for row in rows)


def count_bar_sources(event_store: EventStore, query: BarQuery) -> tuple[BarSourceCount, ...]:
    """Count matching bar rows by symbol and source.

    Args:
        event_store: Event store exposing a queryable connection.
        query: Bar query request.

    Returns:
        Source-level row counts for matching rows.

    Raises:
        EventStoreConnectionUnavailable: If the event store has no query connection.
        MarketDataQueryValidationError: If the query is invalid.
    """
    normalized = normalize_bar_query(query)
    rows = _fetchall(
        _queryable_connection(event_store),
        f"""
        SELECT symbol, COALESCE(source, 'unknown') AS source, COUNT(*) AS row_count
        FROM {_bar_table_name(normalized.asset_class)}
        WHERE {_where_clause(normalized)}
        GROUP BY symbol, COALESCE(source, 'unknown')
        ORDER BY symbol ASC, source ASC
        """,
        _where_params(normalized),
    )
    return tuple(
        BarSourceCount(
            symbol=str(row[0]),
            source=str(row[1]),
            row_count=int(row[2] or 0),
        )
        for row in rows
    )


def fetch_bars(event_store: EventStore, query: BarQuery) -> tuple[BarRecord, ...]:
    """Fetch bounded bar records for a validated query.

    Args:
        event_store: Event store exposing a queryable connection.
        query: Bar query request.

    Returns:
        Matching bar records ordered by timestamp, symbol, and source.

    Raises:
        EventStoreConnectionUnavailable: If the event store has no query connection.
        MarketDataQueryValidationError: If the query is invalid.
    """
    normalized = normalize_bar_query(query, default_limit=DEFAULT_BAR_FETCH_LIMIT)
    rows = _fetchall(
        _queryable_connection(event_store),
        f"""
        SELECT symbol, COALESCE(timeframe, '1Min') AS timeframe, ts,
               open, high, low, close, volume, trade_count, vwap, source
        FROM {_bar_table_name(normalized.asset_class)}
        WHERE {_where_clause(normalized)}
        ORDER BY ts ASC, symbol ASC, source ASC
        LIMIT %s
        """,
        [*_where_params(normalized), normalized.limit],
    )
    return tuple(_bar_record_from_row(row) for row in rows)


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
    if asset_class not in _BAR_TABLE_BY_ASSET_CLASS:
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


def discover_bar_symbols(
    event_store: EventStore,
    query: BarSymbolDiscoveryQuery,
) -> tuple[DiscoveredBarSymbol, ...]:
    """Discover distinct local symbols with matching bar rows.

    Args:
        event_store: Event store exposing a queryable connection.
        query: Local symbol discovery query.

    Returns:
        Matching local symbols and optional coverage, ordered by symbol.

    Raises:
        EventStoreConnectionUnavailable: If the event store has no query connection.
        MarketDataQueryValidationError: If the query is invalid.
    """
    normalized = normalize_bar_symbol_discovery_query(query)
    rows = _fetchall(
        _queryable_connection(event_store),
        f"""
        SELECT symbol,
               COUNT(*) AS row_count,
               MIN(ts) AS first_ts,
               MAX(ts) AS last_ts,
               STRING_AGG(DISTINCT COALESCE(timeframe, '1Min'), ',' ORDER BY COALESCE(timeframe, '1Min')) AS timeframes,
               STRING_AGG(DISTINCT COALESCE(source, 'unknown'), ',' ORDER BY COALESCE(source, 'unknown')) AS sources
        FROM {_bar_table_name(normalized.asset_class)}
        WHERE {_symbol_discovery_where_clause(normalized)}
        GROUP BY symbol
        ORDER BY symbol ASC
        LIMIT %s
        """,
        [*_symbol_discovery_where_params(normalized), normalized.limit],
    )
    return tuple(_discovered_bar_symbol_from_row(row, include_coverage=normalized.include_coverage) for row in rows)


def _bar_table_name(asset_class: str) -> str:
    """Return the fixed bar table name for a normalized asset class.

    Args:
        asset_class: Normalized asset class.

    Returns:
        Internal bar table name.

    Raises:
        MarketDataQueryValidationError: If the asset class has no bar table.
    """
    try:
        return _BAR_TABLE_BY_ASSET_CLASS[asset_class]
    except KeyError as exc:
        raise MarketDataQueryValidationError(f"Unsupported bar query asset class: {asset_class}") from exc


def _queryable_connection(event_store: EventStore) -> Any:
    """Return a queryable connection from an event store.

    Args:
        event_store: Event store to inspect.

    Returns:
        Connection object that exposes cursor semantics.

    Raises:
        EventStoreConnectionUnavailable: If no queryable connection is available.
    """
    connector = getattr(event_store, "connection", None)
    connection = connector() if connector is not None else None
    if connection is None or not hasattr(connection, "cursor"):
        raise EventStoreConnectionUnavailable("Event store does not expose a queryable connection.")
    return connection


def _where_clause(query: BarQuery) -> str:
    """Build the fixed SQL predicate for a normalized query.

    Args:
        query: Normalized bar query.

    Returns:
        SQL predicate with placeholders only for bound parameters.
    """
    symbol_placeholders = ", ".join(["%s"] * len(query.symbols))
    clauses = [
        f"symbol IN ({symbol_placeholders})",
        "COALESCE(timeframe, '1Min') = %s",
        "ts >= %s",
        "ts <= %s",
    ]
    if query.source is not None:
        clauses.append("source = %s")
    return " AND ".join(clauses)


def _where_params(query: BarQuery) -> list[object]:
    """Build bound SQL parameters for a normalized query.

    Args:
        query: Normalized bar query.

    Returns:
        Parameter list matching `_where_clause`.
    """
    params: list[object] = [*query.symbols, query.timeframe, query.start, query.end]
    if query.source is not None:
        params.append(query.source)
    return params


def _symbol_discovery_where_clause(query: BarSymbolDiscoveryQuery) -> str:
    """Build the fixed SQL predicate for local symbol discovery."""
    clauses = ["1 = 1"]
    if query.symbols:
        placeholders = ", ".join(["%s"] * len(query.symbols))
        clauses.append(f"symbol IN ({placeholders})")
    if query.query is not None:
        clauses.append("UPPER(symbol) LIKE %s")
    if query.timeframe is not None:
        clauses.append("COALESCE(timeframe, '1Min') = %s")
    if query.source is not None:
        clauses.append("source = %s")
    return " AND ".join(clauses)


def _symbol_discovery_where_params(query: BarSymbolDiscoveryQuery) -> list[object]:
    """Build bound SQL parameters for local symbol discovery."""
    params: list[object] = [*query.symbols]
    if query.query is not None:
        params.append(f"%{query.query}%")
    if query.timeframe is not None:
        params.append(query.timeframe)
    if query.source is not None:
        params.append(query.source)
    return params


def _fetchone(connection: Any, query: str, params: list[object]) -> object | None:
    """Execute a parameterized read query and fetch one row.

    Args:
        connection: Queryable event-store connection.
        query: SQL query text owned by this core module.
        params: Bound query parameters.

    Returns:
        First row, or `None` when no row is returned.
    """
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchone()


def _fetchall(connection: Any, query: str, params: list[object]) -> list[object]:
    """Execute a parameterized read query and fetch all rows.

    Args:
        connection: Queryable event-store connection.
        query: SQL query text owned by this core module.
        params: Bound query parameters.

    Returns:
        List of result rows.
    """
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()


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
