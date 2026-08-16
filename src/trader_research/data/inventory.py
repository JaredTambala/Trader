"""Inspect stored market data and build deterministic dataset manifests.

Inventory reads are bounded by a normalized Data Agent request and preserve the
requested symbol order. The module reports available coverage without fetching
new data or mutating the event store.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

from trader.event_store import EventStore
from trader.market_data.queries import (
    BarQuery,
    EventStoreConnectionUnavailable,
    count_bar_rows,
    count_bar_sources,
    fetch_bar_ranges,
    normalize_bar_query,
)

from trader_research.foundation import ApplicationResult, error_result, success_result

from .catalog import (
    _merge_provider_context_fields,
    _provider_context_from_request,
    _provider_error_result,
)
from .domain import DATA_GET_INVENTORY, DataInventoryRequest, DataProviderResolutionError


def get_data_inventory(event_store: EventStore, request: DataInventoryRequest) -> ApplicationResult:
    """Return a Data Agent inventory result for existing market data.

    Args:
        event_store: Event store that exposes a read-only database connection.
        request: Bounded inventory request.

    Returns:
        Data Agent tool result with an embedded dataset manifest.
    """
    try:
        provider_context = _provider_context_from_request(request)
        query = _bar_query_from_request(request)
        manifest, warnings = _build_manifest(event_store, query)
        manifest["provider_context"] = provider_context.to_dict()
        _merge_provider_context_fields(manifest, provider_context)
    except DataProviderResolutionError as exc:
        return _provider_error_result(
            command=DATA_GET_INVENTORY,
            error=exc,
        )
    except EventStoreConnectionUnavailable as exc:
        return error_result(
            command=DATA_GET_INVENTORY,
            code="event_store_connection_unavailable",
            message=str(exc),
            data={"request": _raw_request_payload(request)},
        )
    except ValueError as exc:
        return error_result(
            command=DATA_GET_INVENTORY,
            code="validation_error",
            message=str(exc),
        )

    return success_result(
        command=DATA_GET_INVENTORY,
        data={"dataset_manifest": manifest},
        warnings=warnings,
    )


def _bar_query_from_request(request: DataInventoryRequest) -> BarQuery:
    """Convert a Data Agent inventory request into a normalized bar query.

    Args:
        request: Raw inventory request.

    Returns:
        Normalized core bar query.

    Raises:
        MarketDataQueryValidationError: If request fields are invalid.
    """
    provider_context = _provider_context_from_request(request)
    return _bar_query_from_fields(
        symbols=request.symbols,
        asset_class=provider_context.legacy_asset_class,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        source=request.source,
    )


def _bar_query_from_fields(
    *,
    symbols: tuple[str, ...],
    asset_class: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    source: str | None,
) -> BarQuery:
    """Convert request fields into a normalized bar query.

    Args:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp.
        end: Inclusive requested end timestamp.
        source: Optional source filter.

    Returns:
        Normalized core bar query.

    Raises:
        MarketDataQueryValidationError: If request fields are invalid.
    """
    return normalize_bar_query(
        BarQuery(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            source=source,
        )
    )


def _build_manifest(event_store: EventStore, query: BarQuery) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Build an embedded dataset manifest from typed market-data queries.

    Args:
        event_store: Event store to inspect.
        query: Normalized bar query.

    Returns:
        Tuple containing the manifest payload and non-fatal warnings.

    Raises:
        EventStoreConnectionUnavailable: If no queryable connection is available.
        MarketDataQueryValidationError: If the query is invalid.
    """
    counts = {item.symbol: item.row_count for item in count_bar_rows(event_store, query)}
    ranges = {item.symbol: item for item in fetch_bar_ranges(event_store, query)}
    source_counts = _source_counts_by_symbol(event_store, query)

    symbol_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_rows = 0
    for symbol in query.symbols:
        row_count = counts.get(symbol, 0)
        coverage = ranges[symbol]
        total_rows += row_count
        symbol_rows.append(
            {
                "symbol": symbol,
                "row_count": row_count,
                "first_ts": coverage.first_ts,
                "last_ts": coverage.last_ts,
                "sources": source_counts.get(symbol, {}),
            }
        )
        warnings.extend(_symbol_warnings(symbol, row_count, coverage.first_ts, coverage.last_ts, query))

    manifest = {
        "dataset_id": _dataset_id(query),
        "asset_class": query.asset_class,
        "symbols": list(query.symbols),
        "timeframe": query.timeframe,
        "requested_window": {
            "start": query.start,
            "end": query.end,
        },
        "source_filter": query.source,
        "total_rows": total_rows,
        "complete": not warnings,
        "symbols_detail": symbol_rows,
    }
    return manifest, tuple(warnings)


def _source_counts_by_symbol(event_store: EventStore, query: BarQuery) -> dict[str, dict[str, int]]:
    """Return source counts grouped by symbol.

    Args:
        event_store: Event store to inspect.
        query: Normalized bar query.

    Returns:
        Mapping from symbol to source-count mapping.

    Raises:
        EventStoreConnectionUnavailable: If no queryable connection is available.
        MarketDataQueryValidationError: If the query is invalid.
    """
    grouped: dict[str, dict[str, int]] = {}
    for item in count_bar_sources(event_store, query):
        grouped.setdefault(item.symbol, {})[item.source] = item.row_count
    return grouped


def _symbol_warnings(
    symbol: str,
    row_count: int,
    first_ts: datetime | None,
    last_ts: datetime | None,
    query: BarQuery,
) -> list[str]:
    """Build non-fatal coverage warnings for one symbol.

    Args:
        symbol: Canonical symbol inspected.
        row_count: Number of rows found.
        first_ts: First bar timestamp found, if any.
        last_ts: Last bar timestamp found, if any.
        query: Normalized bar query.

    Returns:
        List of warning messages.
    """
    if row_count == 0:
        return [f"No bars found for {symbol}."]
    warnings: list[str] = []
    if first_ts is not None and first_ts > query.start:
        warnings.append(f"First bar for {symbol} is after requested start.")
    if last_ts is not None and last_ts < query.end:
        warnings.append(f"Last bar for {symbol} is before requested end.")
    return warnings


def _dataset_id(query: BarQuery) -> str:
    """Build a stable dataset identifier for a normalized query.

    Args:
        query: Normalized bar query.

    Returns:
        Stable dataset identifier.
    """
    payload = _query_payload(query)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"dataset_{digest}"


def _query_payload(query: BarQuery) -> dict[str, Any]:
    """Build the stable query payload used for hashing.

    Args:
        query: Normalized bar query.

    Returns:
        JSON-compatible query payload.
    """
    return {
        "symbols": list(query.symbols),
        "asset_class": query.asset_class,
        "timeframe": query.timeframe,
        "start": query.start.isoformat(),
        "end": query.end.isoformat(),
        "source": query.source,
    }


def _raw_request_payload(request: DataInventoryRequest) -> dict[str, Any]:
    """Build error context for an unnormalized request.

    Args:
        request: Raw inventory request.

    Returns:
        JSON-compatible request payload.
    """
    return {
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "timeframe": request.timeframe,
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "source": request.source,
        "provider": request.provider,
        "instrument_type": request.instrument_type,
        "bar_type": request.bar_type,
        "configured_provider": request.configured_provider,
        "configured_asset_class": request.configured_asset_class,
    }
