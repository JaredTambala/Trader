"""Resolve market-data provider context and discover available symbols.

The helpers normalize Data Agent discovery requests, select the configured
read-only catalog, and return bounded provider metadata. They do not load bars
or mutate the market-data store.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from typing import Any

from trader.event_store import EventStore
from trader.market_data.queries import (
    BarSymbolDiscoveryQuery,
    DiscoveredBarSymbol,
    EventStoreConnectionUnavailable,
    discover_bar_symbols,
)
from trader.symbols import canonicalize_symbol, normalize_asset_class

from trader_research.foundation import ApplicationResult, error_result, success_result

from .domain import (
    DATA_DISCOVER_SYMBOLS,
    _DEFAULT_BAR_TYPE,
    _DEFAULT_CONFIGURED_PROVIDER,
    _DISCOVERY_SOURCES,
    DataProviderCapability,
    DataProviderContext,
    DataProviderResolutionError,
    DataSymbolDiscoveryPolicy,
    DataSymbolDiscoveryRequest,
)


_PROVIDER_CAPABILITIES: Mapping[str, DataProviderCapability] = {
    "alpaca": DataProviderCapability(
        provider_key="alpaca",
        provider_aliases=("alpaca", "alpaca_data"),
        instrument_asset_classes={"stock": "stocks", "crypto": "crypto"},
        canonical_bar_source="alpaca",
        supports_symbol_catalog=False,
        requires_network=False,
        requires_credentials=False,
    ),
}
_PROVIDER_ALIAS_TO_KEY: Mapping[str, str] = {
    alias: capability.provider_key
    for capability in _PROVIDER_CAPABILITIES.values()
    for alias in capability.provider_aliases
}


def data_discover_symbols(
    event_store: EventStore,
    request: DataSymbolDiscoveryRequest,
    *,
    policy: DataSymbolDiscoveryPolicy | None = None,
) -> ApplicationResult:
    """Discover or validate provider-scoped symbols for the Data Agent.

    Args:
        event_store: Event store used for deterministic local discovery.
        request: Symbol discovery or exact validation request.
        policy: Optional provider catalog discovery policy.

    Returns:
        Data Agent result with `symbol_discovery_report`.
    """
    runtime_policy = policy or DataSymbolDiscoveryPolicy()
    try:
        source = _normalize_discovery_source(request.source)
        limit = _normalize_discovery_limit(request.limit)
        context = _provider_context_from_request(request)
        requested_symbols = _canonical_requested_symbols(request.symbols, context)
        report = _build_symbol_discovery_report(
            event_store=event_store,
            request=request,
            context=context,
            source=source,
            requested_symbols=requested_symbols,
            limit=limit,
            policy=runtime_policy,
        )
    except DataProviderResolutionError as exc:
        return _provider_error_result(
            command=DATA_DISCOVER_SYMBOLS,
            error=exc,
        )
    except EventStoreConnectionUnavailable as exc:
        return error_result(
            command=DATA_DISCOVER_SYMBOLS,
            code="event_store_connection_unavailable",
            message=str(exc),
            data={"request": _raw_symbol_discovery_request_payload(request)},
        )
    except ValueError as exc:
        return error_result(
            command=DATA_DISCOVER_SYMBOLS,
            code="validation_error",
            message=str(exc),
        )

    return success_result(
        command=DATA_DISCOVER_SYMBOLS,
        data={"symbol_discovery_report": report},
    )


def resolve_data_provider_context(
    *,
    provider: str | None = None,
    configured_provider: str | None = None,
    asset_class: str | None = None,
    configured_asset_class: str | None = None,
    instrument_type: str | None = None,
    bar_type: str | None = None,
) -> DataProviderContext:
    """Normalize provider, instrument, and bar selectors into a query context.

    The resolver treats a missing or `configured` provider as the configured data
    provider, rejects requests for a different provider, maps provider instrument
    types back to the event-store asset class, and verifies bar-type support. On
    any mismatch it raises `DataProviderResolutionError` with a stable code and
    detail payload suitable for tool results instead of letting later queries
    fail with ambiguous validation errors.
    """
    configured_provider_key = _normalize_provider_selector(configured_provider) or _DEFAULT_CONFIGURED_PROVIDER
    requested_provider_key = _normalize_provider_selector(provider)
    requested_provider = requested_provider_key if requested_provider_key not in {None, "configured"} else None
    resolved_provider_key = configured_provider_key
    if requested_provider is not None:
        requested_provider_key = _resolve_provider_alias(requested_provider)
        configured_alias_key = _resolve_provider_alias(configured_provider_key)
        if requested_provider_key != configured_alias_key:
            raise DataProviderResolutionError(
                "provider_not_configured",
                f"Requested provider {requested_provider} is not the configured provider {configured_provider_key}.",
                data={
                    "requested_provider": requested_provider,
                    "configured_provider": configured_provider_key,
                    "resolved_provider": None,
                    "provider_match": False,
                },
            )
        resolved_provider_key = configured_alias_key
    else:
        resolved_provider_key = _resolve_provider_alias(configured_provider_key)

    try:
        capability = _PROVIDER_CAPABILITIES[resolved_provider_key]
    except KeyError as exc:
        raise DataProviderResolutionError(
            "unsupported_provider",
            f"Unsupported configured data provider: {configured_provider_key}",
            data={
                "requested_provider": requested_provider,
                "configured_provider": configured_provider_key,
                "resolved_provider": resolved_provider_key,
                "provider_match": requested_provider is None or requested_provider == configured_provider_key,
            },
        ) from exc

    resolved_instrument = _resolve_instrument_type(
        instrument_type=instrument_type,
        asset_class=asset_class,
        configured_asset_class=configured_asset_class,
    )
    if resolved_instrument not in capability.instrument_asset_classes:
        raise DataProviderResolutionError(
            "unsupported_instrument_type",
            f"Provider {capability.provider_key} does not support instrument type {resolved_instrument}.",
            data={
                "requested_provider": requested_provider,
                "configured_provider": configured_provider_key,
                "resolved_provider": capability.provider_key,
                "provider_match": True,
                "instrument_type": resolved_instrument,
                "supported_instrument_types": list(capability.supported_instrument_types),
            },
        )

    resolved_bar_type = _normalize_bar_type(bar_type)
    if resolved_bar_type not in capability.bar_types:
        raise DataProviderResolutionError(
            "unsupported_bar_type",
            f"Provider {capability.provider_key} does not support bar type {resolved_bar_type}.",
            data={
                "requested_provider": requested_provider,
                "configured_provider": configured_provider_key,
                "resolved_provider": capability.provider_key,
                "provider_match": True,
                "instrument_type": resolved_instrument,
                "bar_type": resolved_bar_type,
                "supported_bar_types": list(capability.bar_types),
            },
        )

    legacy_asset_class = capability.instrument_asset_classes[resolved_instrument]
    if asset_class is not None:
        requested_asset_class = normalize_asset_class(asset_class)
        if requested_asset_class != legacy_asset_class:
            raise DataProviderResolutionError(
                "instrument_asset_class_mismatch",
                (
                    f"Instrument type {resolved_instrument} maps to {legacy_asset_class}, "
                    f"not requested asset class {requested_asset_class}."
                ),
                data={
                    "requested_provider": requested_provider,
                    "configured_provider": configured_provider_key,
                    "resolved_provider": capability.provider_key,
                    "provider_match": True,
                    "instrument_type": resolved_instrument,
                    "legacy_asset_class": legacy_asset_class,
                    "asset_class": requested_asset_class,
                },
            )

    return DataProviderContext(
        requested_provider=requested_provider,
        configured_provider=configured_provider_key,
        resolved_provider=capability.provider_key,
        provider_match=True,
        provider_key=capability.provider_key,
        configured_source=configured_provider_key,
        instrument_type=resolved_instrument,
        bar_type=resolved_bar_type,
        legacy_asset_class=legacy_asset_class,
        supports_symbol_catalog=capability.supports_symbol_catalog,
        supported_instrument_types=capability.supported_instrument_types,
        supported_bar_types=capability.bar_types,
        canonical_bar_source=capability.canonical_bar_source,
        requires_network=capability.requires_network,
        requires_credentials=capability.requires_credentials,
    )


def _provider_context_from_request(request: object) -> DataProviderContext:
    """Resolve provider context from any Data Agent request dataclass."""
    return resolve_data_provider_context(
        provider=getattr(request, "provider", None),
        configured_provider=getattr(request, "configured_provider", None),
        asset_class=getattr(request, "asset_class", None),
        configured_asset_class=getattr(request, "configured_asset_class", None),
        instrument_type=getattr(request, "instrument_type", None),
        bar_type=getattr(request, "bar_type", None),
    )


def _build_symbol_discovery_report(
    *,
    event_store: EventStore,
    request: DataSymbolDiscoveryRequest,
    context: DataProviderContext,
    source: str,
    requested_symbols: tuple[str, ...],
    limit: int,
    policy: DataSymbolDiscoveryPolicy,
) -> dict[str, Any]:
    """Build a provider-scoped symbol discovery report."""
    if source == "local":
        symbols, truncated = _discover_local_symbol_rows(event_store, request, context, requested_symbols, limit)
    elif source == "configured":
        if not request.configured_universe_available:
            raise ValueError("Configured symbol universe is unavailable.")
        symbols, truncated = _configured_symbol_rows(request, context, requested_symbols, limit)
    elif source == "configured_source":
        if request.configured_universe_available and request.configured_symbols:
            symbols, truncated = _configured_symbol_rows(request, context, requested_symbols, limit)
        else:
            symbols, truncated = _discover_local_symbol_rows(event_store, request, context, requested_symbols, limit)
    elif source in {"provider", "merged"}:
        symbols, truncated = _provider_symbol_rows(request, context, requested_symbols, limit, policy)
    else:
        raise ValueError(f"Unsupported symbol discovery source: {source}")

    existing = {str(row["symbol"]) for row in symbols if row.get("exists") is True}
    missing_symbols = [symbol for symbol in requested_symbols if symbol not in existing]
    report: dict[str, Any] = {
        "report_id": _symbol_discovery_report_id(request, context, source, requested_symbols),
        "instrument_type": context.instrument_type,
        "bar_type": context.bar_type,
        "legacy_asset_class": context.legacy_asset_class,
        "asset_class": context.legacy_asset_class,
        "requested_symbols": list(requested_symbols),
        "query": request.query,
        "source": source,
        "source_filter": request.source_filter,
        "requested_provider": context.requested_provider,
        "configured_provider": context.configured_provider,
        "resolved_provider": context.resolved_provider,
        "provider_match": context.provider_match,
        "provider_context": context.to_dict(),
        "limit": limit,
        "returned": len(symbols),
        "truncated": truncated,
        "all_requested_symbols_exist": not missing_symbols,
        "missing_symbols": missing_symbols,
        "symbols": symbols,
    }
    return report


def _discover_local_symbol_rows(
    event_store: EventStore,
    request: DataSymbolDiscoveryRequest,
    context: DataProviderContext,
    requested_symbols: tuple[str, ...],
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Discover symbols from local bar tables."""
    discovery_query = BarSymbolDiscoveryQuery(
        asset_class=context.legacy_asset_class,
        timeframe=request.timeframe,
        source=request.source_filter,
        symbols=requested_symbols,
        query=request.query,
        limit=limit,
        include_coverage=request.include_local_coverage,
    )
    local_symbols = discover_bar_symbols(event_store, discovery_query)
    rows = [
        _local_symbol_row(symbol, request=request, context=context, requested_symbols=requested_symbols)
        for symbol in local_symbols
    ]
    return rows, False


def _local_symbol_row(
    symbol: DiscoveredBarSymbol,
    *,
    request: DataSymbolDiscoveryRequest,
    context: DataProviderContext,
    requested_symbols: tuple[str, ...],
) -> dict[str, Any]:
    """Return one local symbol row for a discovery report."""
    row: dict[str, Any] = {
        "symbol": symbol.symbol,
        "raw_symbol": symbol.symbol,
        "instrument_type": context.instrument_type,
        "bar_type": context.bar_type,
        "legacy_asset_class": context.legacy_asset_class,
        "requested": symbol.symbol in requested_symbols,
        "exists": True,
        "name": None,
        "exchange": None,
        "status": None,
        "tradable": None,
        "source": "local",
    }
    if request.include_local_coverage:
        row["local_coverage"] = {
            "row_count": symbol.row_count,
            "first_ts": symbol.first_ts,
            "last_ts": symbol.last_ts,
            "timeframes": list(symbol.timeframes),
            "sources": list(symbol.sources),
        }
    return row


def _configured_symbol_rows(
    request: DataSymbolDiscoveryRequest,
    context: DataProviderContext,
    requested_symbols: tuple[str, ...],
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Discover symbols from the configured market-data universe."""
    configured_symbols = _canonical_requested_symbols(request.configured_symbols, context)
    requested_set = set(requested_symbols)
    query_text = str(request.query).strip().upper() if request.query is not None else None
    if requested_symbols:
        candidates = [symbol for symbol in configured_symbols if symbol in requested_set]
    elif query_text:
        candidates = [symbol for symbol in configured_symbols if query_text in symbol.upper()]
    else:
        candidates = list(configured_symbols)
    truncated = len(candidates) > limit
    rows = [
        {
            "symbol": symbol,
            "raw_symbol": symbol,
            "instrument_type": context.instrument_type,
            "bar_type": context.bar_type,
            "legacy_asset_class": context.legacy_asset_class,
            "requested": symbol in requested_set,
            "exists": True,
            "name": None,
            "exchange": None,
            "status": None,
            "tradable": None,
            "source": "configured",
        }
        for symbol in candidates[:limit]
    ]
    return rows, truncated


def _provider_symbol_rows(
    request: DataSymbolDiscoveryRequest,
    context: DataProviderContext,
    requested_symbols: tuple[str, ...],
    limit: int,
    policy: DataSymbolDiscoveryPolicy,
) -> tuple[list[dict[str, Any]], bool]:
    """Discover symbols from an explicit provider catalog adapter."""
    if not policy.allow_provider_discovery:
        raise DataProviderResolutionError(
            "provider_discovery_not_allowed",
            "Provider catalog discovery is not allowed by policy.",
            data={
                "requested_provider": context.requested_provider,
                "configured_provider": context.configured_provider,
                "resolved_provider": context.resolved_provider,
                "provider_match": context.provider_match,
            },
        )
    adapter = policy.catalog_providers.get(context.resolved_provider)
    if adapter is None:
        raise DataProviderResolutionError(
            "unsupported_provider_catalog",
            f"No symbol catalog adapter is registered for provider {context.resolved_provider}.",
            data={
                "requested_provider": context.requested_provider,
                "configured_provider": context.configured_provider,
                "resolved_provider": context.resolved_provider,
                "provider_match": context.provider_match,
            },
        )
    try:
        result = adapter.discover_symbols(request, context)
    except DataProviderResolutionError:
        raise
    except Exception as exc:
        raise DataProviderResolutionError(
            "provider_catalog_unavailable",
            f"Provider symbol catalog discovery failed: {exc}",
            data={
                "requested_provider": context.requested_provider,
                "configured_provider": context.configured_provider,
                "resolved_provider": context.resolved_provider,
                "provider_match": context.provider_match,
            },
        ) from exc
    requested_set = set(requested_symbols)
    rows: list[dict[str, Any]] = []
    for item in result.symbols[:limit]:
        symbol = canonicalize_symbol(str(item.get("symbol", "")), asset_class=context.legacy_asset_class)
        if not symbol:
            continue
        row = {
            "symbol": symbol,
            "raw_symbol": str(item.get("raw_symbol", item.get("symbol", symbol))),
            "instrument_type": context.instrument_type,
            "bar_type": context.bar_type,
            "legacy_asset_class": context.legacy_asset_class,
            "requested": symbol in requested_set,
            "exists": bool(item.get("exists", True)),
            "name": item.get("name"),
            "exchange": item.get("exchange"),
            "status": item.get("status"),
            "tradable": item.get("tradable"),
            "source": "provider",
        }
        rows.append(row)
    return rows, result.truncated or len(result.symbols) > limit


def _canonical_requested_symbols(symbols: Sequence[str], context: DataProviderContext) -> tuple[str, ...]:
    """Canonicalize symbols in the resolved provider namespace while preserving order."""
    canonical = (
        canonicalize_symbol(str(symbol), asset_class=context.legacy_asset_class)
        for symbol in symbols
        if str(symbol).strip()
    )
    return tuple(dict.fromkeys(symbol for symbol in canonical if symbol))


def _normalize_discovery_source(source: str | None) -> str:
    """Normalize and validate a symbol discovery source."""
    normalized = str(source or "local").strip().lower()
    if normalized not in _DISCOVERY_SOURCES:
        raise ValueError(f"Unsupported symbol discovery source: {source}")
    return normalized


def _normalize_discovery_limit(limit: int | None) -> int:
    """Normalize and validate symbol discovery limit at the research boundary."""
    try:
        normalized = 50 if limit is None else int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("Symbol discovery limit must be an integer") from exc
    if normalized < 1:
        raise ValueError("Symbol discovery limit must be at least 1")
    if normalized > 500:
        raise ValueError("Symbol discovery limit supports at most 500 symbols")
    return normalized


def _normalize_provider_selector(value: str | None) -> str | None:
    """Normalize provider selectors and aliases."""
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("-", "_")
    if not normalized or normalized == "configured":
        return None if not normalized else "configured"
    return normalized


def _resolve_provider_alias(provider_key: str) -> str:
    """Resolve a provider alias to a registered provider key when known."""
    return _PROVIDER_ALIAS_TO_KEY.get(provider_key, provider_key)


def _resolve_instrument_type(
    *,
    instrument_type: str | None,
    asset_class: str | None,
    configured_asset_class: str | None,
) -> str:
    """Resolve provider-scoped instrument type from explicit input or compatibility asset class."""
    if instrument_type is not None and str(instrument_type).strip():
        return _normalize_instrument_type(str(instrument_type))
    asset_value = asset_class if asset_class is not None else configured_asset_class
    if asset_value is None or not str(asset_value).strip():
        asset_value = "stocks"
    return _instrument_type_from_asset_class(asset_value)


def _normalize_instrument_type(value: str) -> str:
    """Normalize provider-scoped instrument type aliases."""
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"stocks", "stock", "equity", "us_equity", "us_stock"}:
        return "stock"
    if normalized in {"crypto", "cryptocurrency"}:
        return "crypto"
    return normalized


def _instrument_type_from_asset_class(asset_class: str | None) -> str:
    """Resolve current compatibility asset classes into provider-scoped instruments."""
    normalized = normalize_asset_class(asset_class)
    if normalized == "stocks":
        return "stock"
    if normalized == "crypto":
        return "crypto"
    return normalized


def _normalize_bar_type(value: str | None) -> str:
    """Normalize provider-scoped bar type aliases."""
    if value is None or not str(value).strip():
        return _DEFAULT_BAR_TYPE
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"bar", "bars", "trade_bars", "ohlcv"}:
        return _DEFAULT_BAR_TYPE
    return normalized


def _provider_error_result(
    *,
    command: str,
    error: DataProviderResolutionError,
) -> ApplicationResult:
    """Build a Data Agent application result from a provider error."""
    return error_result(
        command=command,
        code=error.code,
        message=str(error),
        data=error.data,
    )


def _merge_provider_context_fields(payload: dict[str, Any], context: DataProviderContext) -> None:
    """Expose common provider context fields at top level for report auditability."""
    payload.update(
        {
            "requested_provider": context.requested_provider,
            "configured_provider": context.configured_provider,
            "resolved_provider": context.resolved_provider,
            "provider_match": context.provider_match,
            "instrument_type": context.instrument_type,
            "bar_type": context.bar_type,
            "legacy_asset_class": context.legacy_asset_class,
        }
    )


def _symbol_discovery_report_id(
    request: DataSymbolDiscoveryRequest,
    context: DataProviderContext,
    source: str,
    requested_symbols: tuple[str, ...],
) -> str:
    """Build a stable symbol discovery report identifier."""
    payload = {
        "provider": context.resolved_provider,
        "instrument_type": context.instrument_type,
        "bar_type": context.bar_type,
        "legacy_asset_class": context.legacy_asset_class,
        "source": source,
        "symbols": list(requested_symbols),
        "query": request.query,
        "configured_symbols": list(_canonical_requested_symbols(request.configured_symbols, context)),
        "timeframe": request.timeframe,
        "source_filter": request.source_filter,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"symbol_discovery_{digest}"


def _raw_symbol_discovery_request_payload(request: DataSymbolDiscoveryRequest) -> dict[str, Any]:
    """Build error context for an unnormalized symbol discovery request."""
    return {
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "instrument_type": request.instrument_type,
        "bar_type": request.bar_type,
        "query": request.query,
        "source": request.source,
        "provider": request.provider,
        "configured_provider": request.configured_provider,
        "configured_asset_class": request.configured_asset_class,
        "configured_symbols": list(request.configured_symbols),
        "timeframe": request.timeframe,
        "source_filter": request.source_filter,
        "limit": request.limit,
        "active_only": request.active_only,
        "tradable_only": request.tradable_only,
        "include_local_coverage": request.include_local_coverage,
        "configured_universe_available": request.configured_universe_available,
    }
