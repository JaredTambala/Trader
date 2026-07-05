"""Typed read-only market-data queries over the event store."""

from __future__ import annotations

from typing import Any

from ..event_store import EventStore
from .query_domain import (
    DEFAULT_BAR_FETCH_LIMIT,
    DEFAULT_SYMBOL_DISCOVERY_LIMIT,
    MAX_BAR_FETCH_LIMIT,
    MAX_BAR_QUERY_SYMBOLS,
    MAX_SYMBOL_DISCOVERY_LIMIT,
    BarCount,
    BarQuery,
    BarRange,
    BarRecord,
    BarSourceCount,
    BarSymbolDiscoveryQuery,
    BarTimestamp,
    DiscoveredBarSymbol,
    EventStoreConnectionUnavailable,
    MarketDataQueryError,
    MarketDataQueryValidationError,
    _bar_record_from_row,
    _discovered_bar_symbol_from_row,
    _optional_datetime,
    _required_datetime,
    normalize_bar_query,
    normalize_bar_symbol_discovery_query,
)
from .query_sql import (
    _bar_table_name,
    _symbol_discovery_where_clause,
    _symbol_discovery_where_params,
    _where_clause,
    _where_params,
)

__all__ = [
    "DEFAULT_BAR_FETCH_LIMIT",
    "DEFAULT_SYMBOL_DISCOVERY_LIMIT",
    "MAX_BAR_FETCH_LIMIT",
    "MAX_BAR_QUERY_SYMBOLS",
    "MAX_SYMBOL_DISCOVERY_LIMIT",
    "BarCount",
    "BarQuery",
    "BarRange",
    "BarRecord",
    "BarSourceCount",
    "BarSymbolDiscoveryQuery",
    "BarTimestamp",
    "DiscoveredBarSymbol",
    "EventStoreConnectionUnavailable",
    "MarketDataQueryError",
    "MarketDataQueryValidationError",
    "count_bar_rows",
    "count_bar_sources",
    "count_bar_symbols",
    "discover_bar_symbols",
    "fetch_bar_ranges",
    "fetch_bar_timestamps",
    "fetch_bars",
    "normalize_bar_query",
    "normalize_bar_symbol_discovery_query",
]


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
