"""SQL construction helpers for read-only market-data queries."""

from __future__ import annotations

from .query_domain import (
    BAR_TABLE_BY_ASSET_CLASS,
    BarQuery,
    BarSymbolDiscoveryQuery,
    MarketDataQueryValidationError,
)


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
        return BAR_TABLE_BY_ASSET_CLASS[asset_class]
    except KeyError as exc:
        raise MarketDataQueryValidationError(f"Unsupported bar query asset class: {asset_class}") from exc


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
