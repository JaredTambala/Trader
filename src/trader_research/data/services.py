"""Data Agent services for market-data inventory."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from trader.config import build_config, load_yaml_config
from trader.event_store import EventStore
from trader.market_data.quality import summarize_bar_quality
from trader.market_data.backfill import BackfillSpec, MarketDataBackfillRunner
from trader.market_data.queries import (
    BarSymbolDiscoveryQuery,
    BarQuery,
    DiscoveredBarSymbol,
    EventStoreConnectionUnavailable,
    count_bar_rows,
    count_bar_sources,
    discover_bar_symbols,
    fetch_bar_ranges,
    normalize_bar_query,
)
from trader.market_data.sample import load_sample_market_data_csv
from trader.symbols import canonicalize_symbol, normalize_asset_class
from trader.timeframes import parse_timeframe

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope


DATA_GET_INVENTORY = "data_get_inventory"
DATA_SUMMARIZE_QUALITY = "data_summarize_quality"
DATA_ENSURE_LOADED = "data_ensure_loaded"
DATA_DISCOVER_SYMBOLS = "data_discover_symbols"
_SAMPLE_CSV = Path(__file__).resolve().parents[3] / "examples/data/demo_stock_1min.csv"
_ENSURE_MODES = {"existing", "sample", "backfill"}
_DEFAULT_CONFIGURED_PROVIDER = "alpaca"
_DEFAULT_BAR_TYPE = "trade_bar"
_DISCOVERY_SOURCES = {"local", "configured", "configured_source", "provider", "merged"}


BackfillRunner = Callable[["DataEnsureLoadedRequest", EventStore], Mapping[str, Any]]
"""Callable used by explicit non-dry-run backfill requests."""


@dataclass(frozen=True)
class DataProviderCapability:
    """Static capabilities used to validate Data Agent provider requests.

    A capability describes the provider aliases accepted from config or tool
    input, the provider-specific instrument types that map back to the core
    event-store asset classes, and the bar types this adapter can serve. The
    flags intentionally separate catalog/network/credential support from local
    storage so read-only tools can explain unavailable provider discovery without
    attempting network access.
    """

    provider_key: str
    provider_aliases: tuple[str, ...]
    instrument_asset_classes: Mapping[str, str]
    bar_types: tuple[str, ...] = (_DEFAULT_BAR_TYPE,)
    canonical_bar_source: str | None = None
    supports_symbol_catalog: bool = False
    requires_network: bool = False
    requires_credentials: bool = False

    @property
    def supported_instrument_types(self) -> tuple[str, ...]:
        """Return provider-scoped instrument types with registered local data support for validation."""
        return tuple(self.instrument_asset_classes.keys())


@dataclass(frozen=True)
class DataProviderContext:
    """Normalized provider context shared by inventory, quality, and discovery tools.

    The context records both the caller's requested provider and the configured
    provider, plus the resolved provider key used for capability lookup. It also
    carries the provider-scoped instrument/bar terms and the legacy asset-class
    value required by existing event-store queries, allowing envelopes to expose
    modern provider semantics without changing the core storage schema.
    """

    requested_provider: str | None
    configured_provider: str
    resolved_provider: str
    provider_match: bool
    provider_key: str
    configured_source: str
    instrument_type: str
    bar_type: str
    legacy_asset_class: str
    supports_symbol_catalog: bool
    supported_instrument_types: tuple[str, ...]
    supported_bar_types: tuple[str, ...]
    canonical_bar_source: str | None = None
    requires_network: bool = False
    requires_credentials: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize provider resolution details into a JSON-safe envelope payload.

        The mapping keeps requested/configured/resolved provider fields together
        with instrument, bar, legacy asset-class, catalog support, and credential
        flags so tool callers can understand exactly which provider semantics were
        applied to a query.
        """
        return {
            "requested_provider": self.requested_provider,
            "configured_provider": self.configured_provider,
            "resolved_provider": self.resolved_provider,
            "provider_match": self.provider_match,
            "provider_key": self.provider_key,
            "configured_source": self.configured_source,
            "instrument_type": self.instrument_type,
            "bar_type": self.bar_type,
            "legacy_asset_class": self.legacy_asset_class,
            "supports_symbol_catalog": self.supports_symbol_catalog,
            "supported_instrument_types": list(self.supported_instrument_types),
            "supported_bar_types": list(self.supported_bar_types),
            "canonical_bar_source": self.canonical_bar_source,
            "requires_network": self.requires_network,
            "requires_credentials": self.requires_credentials,
        }


class DataProviderResolutionError(ValueError):
    """Resolution failure that preserves a stable code and envelope-ready details.

    Data Agent entrypoints catch this exception separately from generic validation
    errors so callers receive machine-readable provider mismatch, unsupported
    instrument, or unsupported bar-type codes. The `data` payload is copied on
    construction to keep the failure context stable after the exception is raised.
    """

    def __init__(self, code: str, message: str, *, data: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.data = dict(data)


@dataclass(frozen=True)
class SymbolCatalogResult:
    """Provider catalog response after symbols have been adapted for tool output.

    `symbols` contains JSON-compatible provider rows, already filtered or shaped
    by the adapter according to the discovery request. `truncated` tells the Data
    Agent whether the provider had more matches than the requested limit so the
    envelope can distinguish a complete exact validation from a bounded preview.
    """

    symbols: tuple[Mapping[str, Any], ...]
    truncated: bool = False


class SymbolCatalogProvider(Protocol):
    """Interface for optional provider-backed symbol catalog discovery.

    Implementations must not mutate local state and should return provider-scoped
    rows in a JSON-compatible shape. The policy layer decides whether this network
    or credential-backed lookup is allowed; the Data Agent falls back to local or
    configured symbols when no adapter is registered.
    """

    provider_key: str

    def discover_symbols(
        self,
        request: "DataSymbolDiscoveryRequest",
        context: DataProviderContext,
    ) -> SymbolCatalogResult:
        """Return provider-scoped symbol rows matching the validated discovery request and context."""


@dataclass(frozen=True)
class DataSymbolDiscoveryPolicy:
    """Runtime switchboard for provider symbol discovery integrations.

    The policy keeps provider catalog access explicit because discovery can depend
    on credentials or network availability. By default tools use only local or
    configured universes; callers that opt in supply adapters keyed by provider so
    source=`provider` and source=`merged` requests can be handled predictably.
    """

    allow_provider_discovery: bool = False
    catalog_providers: Mapping[str, SymbolCatalogProvider] = field(default_factory=dict)


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


@dataclass(frozen=True)
class DataInventoryRequest:
    """Request for read-only Data Agent inventory.

    Attributes:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp.
        end: Inclusive requested end timestamp.
        source: Optional source filter.
    """

    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    start: datetime
    end: datetime
    source: str | None = None
    provider: str | None = None
    instrument_type: str | None = None
    bar_type: str | None = None
    configured_provider: str | None = None
    configured_asset_class: str | None = None


@dataclass(frozen=True)
class DataQualityRequest:
    """Request for read-only Data Agent quality summary.

    Attributes:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp.
        end: Inclusive requested end timestamp.
        source: Optional source filter.
    """

    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    start: datetime
    end: datetime
    source: str | None = None
    provider: str | None = None
    instrument_type: str | None = None
    bar_type: str | None = None
    configured_provider: str | None = None
    configured_asset_class: str | None = None


@dataclass(frozen=True)
class DataEnsureLoadedRequest:
    """Request for explicit Data Agent data inspection or loading.

    Attributes:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp.
        end: Inclusive requested end timestamp.
        mode: Ensure mode: `existing`, `sample`, or `backfill`.
        source: Optional source filter.
        dry_run: Whether backfill mode should plan only.
    """

    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    start: datetime
    end: datetime
    mode: str
    source: str | None = None
    dry_run: bool = True
    provider: str | None = None
    instrument_type: str | None = None
    bar_type: str | None = None
    configured_provider: str | None = None
    configured_asset_class: str | None = None


@dataclass(frozen=True)
class DataSymbolDiscoveryRequest:
    """Validated input for local, configured, or provider-backed symbol discovery.

    Empty `symbols` plus a query performs bounded search, while explicit symbols
    ask the tool to validate exact provider-scoped identifiers. Provider,
    instrument, and bar-type fields are normalized before querying storage or an
    optional catalog adapter; flags such as `include_local_coverage` and
    `configured_universe_available` control which evidence can appear in the
    resulting discovery report.
    """

    symbols: tuple[str, ...] = tuple()
    asset_class: str | None = None
    instrument_type: str | None = None
    bar_type: str | None = None
    query: str | None = None
    source: str = "local"
    provider: str | None = None
    configured_provider: str | None = None
    configured_asset_class: str | None = None
    configured_symbols: tuple[str, ...] = tuple()
    timeframe: str | None = None
    source_filter: str | None = None
    limit: int = 50
    active_only: bool = True
    tradable_only: bool = True
    include_local_coverage: bool = False
    configured_universe_available: bool = True


@dataclass(frozen=True)
class DataEnsureLoadedPolicy:
    """Runtime policy for local data-loading behavior.

    Attributes:
        allow_data_loading: Whether local mutating sample/backfill behavior is allowed.
        sample_csv_path: Checked-in sample CSV path used by sample mode.
        backfill_config_path: Optional bounded config path for non-dry-run backfill.
        backfill_runner: Optional injected runner for non-dry-run backfill.
    """

    allow_data_loading: bool = False
    sample_csv_path: Path = _SAMPLE_CSV
    backfill_config_path: Path | None = None
    backfill_runner: BackfillRunner | None = None


def get_data_inventory(event_store: EventStore, request: DataInventoryRequest) -> ToolEnvelope:
    """Return a Data Agent inventory envelope for existing market data.

    Args:
        event_store: Event store that exposes a read-only database connection.
        request: Bounded inventory request.

    Returns:
        Data Agent tool envelope with an embedded dataset manifest.
    """
    try:
        provider_context = _provider_context_from_request(request)
        query = _bar_query_from_request(request)
        manifest, warnings = _build_manifest(event_store, query)
        manifest["provider_context"] = provider_context.to_dict()
        _merge_provider_context_fields(manifest, provider_context)
    except DataProviderResolutionError as exc:
        return _provider_error_envelope(
            command=DATA_GET_INVENTORY,
            side_effect=SideEffect.READ_ONLY,
            error=exc,
        )
    except EventStoreConnectionUnavailable as exc:
        return error_envelope(
            command=DATA_GET_INVENTORY,
            side_effect=SideEffect.READ_ONLY,
            code="event_store_connection_unavailable",
            message=str(exc),
            data={"request": _raw_request_payload(request)},
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_GET_INVENTORY,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=str(exc),
        )

    return success_envelope(
        command=DATA_GET_INVENTORY,
        side_effect=SideEffect.READ_ONLY,
        data={"dataset_manifest": manifest},
        warnings=warnings,
    )


def data_summarize_quality(event_store: EventStore, request: DataQualityRequest) -> ToolEnvelope:
    """Return a read-only Data Agent data-quality envelope.

    Args:
        event_store: Event store that exposes a read-only database connection.
        request: Bounded quality request.

    Returns:
        Data Agent tool envelope with an embedded data-quality report.
    """
    try:
        provider_context = _provider_context_from_request(request)
        query = _bar_query_from_fields(
            symbols=request.symbols,
            asset_class=provider_context.legacy_asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
        )
        report, warnings = summarize_bar_quality(event_store, query)
        report["provider_context"] = provider_context.to_dict()
        _merge_provider_context_fields(report, provider_context)
    except DataProviderResolutionError as exc:
        return _provider_error_envelope(
            command=DATA_SUMMARIZE_QUALITY,
            side_effect=SideEffect.READ_ONLY,
            error=exc,
        )
    except EventStoreConnectionUnavailable as exc:
        return error_envelope(
            command=DATA_SUMMARIZE_QUALITY,
            side_effect=SideEffect.READ_ONLY,
            code="event_store_connection_unavailable",
            message=str(exc),
            data={"request": _raw_quality_request_payload(request)},
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_SUMMARIZE_QUALITY,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=str(exc),
        )

    return success_envelope(
        command=DATA_SUMMARIZE_QUALITY,
        side_effect=SideEffect.READ_ONLY,
        data={"data_quality_report": report},
        warnings=warnings,
    )


def data_ensure_loaded(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    *,
    policy: DataEnsureLoadedPolicy | None = None,
) -> ToolEnvelope:
    """Inspect or explicitly load bounded market data for the Data Agent.

    Args:
        event_store: Event store used for inspection and allowed local writes.
        request: Bounded ensure-loaded request.
        policy: Runtime policy controlling local mutation.

    Returns:
        Data Agent tool envelope containing load evidence or structured errors.
    """
    runtime_policy = policy or DataEnsureLoadedPolicy()
    try:
        provider_context = _provider_context_from_request(request)
        query = _bar_query_from_fields(
            symbols=request.symbols,
            asset_class=provider_context.legacy_asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
        )
        mode = _normalize_ensure_mode(request.mode)
    except DataProviderResolutionError as exc:
        return _provider_error_envelope(
            command=DATA_ENSURE_LOADED,
            side_effect=SideEffect.LOCAL_MUTATING,
            error=exc,
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_ENSURE_LOADED,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="validation_error",
            message=str(exc),
        )
    normalized_request = DataEnsureLoadedRequest(
        symbols=query.symbols,
        asset_class=query.asset_class,
        timeframe=query.timeframe,
        start=query.start,
        end=query.end,
        mode=mode,
        source=query.source,
        dry_run=request.dry_run,
        provider=provider_context.resolved_provider,
        instrument_type=provider_context.instrument_type,
        bar_type=provider_context.bar_type,
        configured_provider=provider_context.configured_provider,
        configured_asset_class=provider_context.legacy_asset_class,
    )

    if mode == "sample" and not runtime_policy.allow_data_loading:
        return _ensure_error("data_loading_not_allowed", "Sample data loading is not allowed by policy.")
    if mode == "backfill" and not request.dry_run and not runtime_policy.allow_data_loading:
        return _ensure_error("data_loading_not_allowed", "Non-dry-run backfill is not allowed by policy.")

    inspection = _inspect_data(event_store, normalized_request)
    if inspection.get("error") is not None:
        return inspection["error"]

    try:
        if mode == "existing":
            return _ensure_existing(normalized_request, inspection)
        if mode == "sample":
            return _ensure_sample(event_store, normalized_request, runtime_policy, inspection)
        return _ensure_backfill(event_store, normalized_request, runtime_policy, inspection)
    except ValueError as exc:
        return _ensure_error("data_loading_failed", str(exc))


def data_discover_symbols(
    event_store: EventStore,
    request: DataSymbolDiscoveryRequest,
    *,
    policy: DataSymbolDiscoveryPolicy | None = None,
) -> ToolEnvelope:
    """Discover or validate provider-scoped symbols for the Data Agent.

    Args:
        event_store: Event store used for deterministic local discovery.
        request: Symbol discovery or exact validation request.
        policy: Optional provider catalog discovery policy.

    Returns:
        Data Agent envelope with `symbol_discovery_report`.
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
        return _provider_error_envelope(
            command=DATA_DISCOVER_SYMBOLS,
            side_effect=SideEffect.READ_ONLY,
            error=exc,
        )
    except EventStoreConnectionUnavailable as exc:
        return error_envelope(
            command=DATA_DISCOVER_SYMBOLS,
            side_effect=SideEffect.READ_ONLY,
            code="event_store_connection_unavailable",
            message=str(exc),
            data={"request": _raw_symbol_discovery_request_payload(request)},
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_DISCOVER_SYMBOLS,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=str(exc),
        )

    return success_envelope(
        command=DATA_DISCOVER_SYMBOLS,
        side_effect=SideEffect.READ_ONLY,
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
    detail payload suitable for tool envelopes instead of letting later queries
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


def _provider_error_envelope(
    *,
    command: str,
    side_effect: SideEffect,
    error: DataProviderResolutionError,
) -> ToolEnvelope:
    """Build a Data Agent envelope from a provider resolution error."""
    return error_envelope(
        command=command,
        side_effect=side_effect,
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


def _raw_quality_request_payload(request: DataQualityRequest) -> dict[str, Any]:
    """Build error context for an unnormalized quality request.

    Args:
        request: Raw quality request.

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


def _normalize_ensure_mode(mode: str) -> str:
    """Normalize and validate an ensure-loaded mode.

    Args:
        mode: Requested mode.

    Returns:
        Normalized mode.

    Raises:
        ValueError: If the mode is unsupported.
    """
    normalized = str(mode).strip().lower()
    if normalized not in _ENSURE_MODES:
        raise ValueError(f"Unsupported data ensure mode: {mode}")
    return normalized


def _inspect_data(event_store: EventStore, request: DataEnsureLoadedRequest) -> dict[str, Any]:
    """Inspect current inventory and quality for ensure-loaded workflows.

    Args:
        event_store: Event store to inspect.
        request: Ensure-loaded request.

    Returns:
        Mapping containing manifest, quality report, warnings, or an error envelope.
    """
    inventory_envelope = get_data_inventory(
        event_store,
        DataInventoryRequest(
            symbols=request.symbols,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
            provider=request.provider,
            instrument_type=request.instrument_type,
            bar_type=request.bar_type,
            configured_provider=request.configured_provider,
            configured_asset_class=request.configured_asset_class,
        ),
    )
    if not inventory_envelope.ok:
        return {"error": _retarget_error(inventory_envelope)}

    quality_envelope = data_summarize_quality(
        event_store,
        DataQualityRequest(
            symbols=request.symbols,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
            provider=request.provider,
            instrument_type=request.instrument_type,
            bar_type=request.bar_type,
            configured_provider=request.configured_provider,
            configured_asset_class=request.configured_asset_class,
        ),
    )
    if not quality_envelope.ok:
        return {"error": _retarget_error(quality_envelope)}

    inventory_data = inventory_envelope.to_dict()["data"]
    quality_data = quality_envelope.to_dict()["data"]
    return {
        "manifest": inventory_data["dataset_manifest"],
        "quality_report": quality_data["data_quality_report"],
        "warnings": [*inventory_envelope.warnings, *quality_envelope.warnings],
    }


def _ensure_existing(request: DataEnsureLoadedRequest, inspection: Mapping[str, Any]) -> ToolEnvelope:
    """Build an ensure-loaded result for inspect-only existing mode.

    Args:
        request: Ensure-loaded request.
        inspection: Current data inspection payload.

    Returns:
        Successful or failed ensure-loaded envelope.
    """
    quality_report = dict(inspection["quality_report"])
    load_result = {
        "mode": "existing",
        "status": "already_loaded" if quality_report["complete"] else "data_missing",
        "rows_loaded": 0,
        "dry_run": True,
        "provider_context": _provider_context_from_request(request).to_dict(),
        "post_load_manifest": inspection["manifest"],
        "post_load_quality_report": quality_report,
    }
    if not quality_report["complete"]:
        return _ensure_error(
            "data_missing",
            "Requested data is incomplete in existing mode.",
            data={"load_result": load_result},
        )
    return success_envelope(
        command=DATA_ENSURE_LOADED,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"load_result": load_result},
        warnings=tuple(inspection.get("warnings", ())),
    )


def _ensure_sample(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    policy: DataEnsureLoadedPolicy,
    inspection: Mapping[str, Any],
) -> ToolEnvelope:
    """Load the checked-in sample CSV and inspect post-load coverage.

    Args:
        event_store: Event store that receives sample rows.
        request: Ensure-loaded request.
        policy: Runtime loading policy.
        inspection: Pre-load inspection payload.

    Returns:
        Ensure-loaded envelope with sample-load evidence.
    """
    rows_loaded = load_sample_market_data_csv(event_store, policy.sample_csv_path)
    post_load = _inspect_data(event_store, request)
    if post_load.get("error") is not None:
        return post_load["error"]
    quality_report = dict(post_load["quality_report"])
    load_result = {
        "mode": "sample",
        "status": "loaded" if quality_report["complete"] else "loaded_incomplete",
        "rows_loaded": rows_loaded,
        "dry_run": False,
        "provider_context": _provider_context_from_request(request).to_dict(),
        "sample_csv_path": str(policy.sample_csv_path),
        "pre_load_manifest": inspection["manifest"],
        "post_load_manifest": post_load["manifest"],
        "post_load_quality_report": quality_report,
    }
    if not quality_report["complete"]:
        return _ensure_error(
            "data_missing",
            "Sample data was loaded but the requested data is still incomplete.",
            data={"load_result": load_result},
        )
    return success_envelope(
        command=DATA_ENSURE_LOADED,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"load_result": load_result},
        warnings=tuple(post_load.get("warnings", ())),
    )


def _ensure_backfill(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    policy: DataEnsureLoadedPolicy,
    inspection: Mapping[str, Any],
) -> ToolEnvelope:
    """Plan or run bounded backfill behavior.

    Args:
        event_store: Event store used for allowed local writes.
        request: Ensure-loaded request.
        policy: Runtime loading policy.
        inspection: Pre-backfill inspection payload.

    Returns:
        Ensure-loaded envelope with a dry-run plan or backfill run evidence.
    """
    plan = {
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "provider_context": _provider_context_from_request(request).to_dict(),
        "timeframe": request.timeframe,
        "start": request.start,
        "end": request.end,
        "source": request.source,
        "dry_run": request.dry_run,
        "network_calls": 0 if request.dry_run else None,
        "writes": 0 if request.dry_run else None,
        "config_path": str(policy.backfill_config_path) if policy.backfill_config_path else None,
    }
    if request.dry_run:
        return success_envelope(
            command=DATA_ENSURE_LOADED,
            side_effect=SideEffect.LOCAL_MUTATING,
            data={
                "load_result": {
                    "mode": "backfill",
                    "status": "planned",
                    "rows_loaded": 0,
                    "dry_run": True,
                    "provider_context": _provider_context_from_request(request).to_dict(),
                    "backfill_plan": plan,
                    "pre_load_manifest": inspection["manifest"],
                    "pre_load_quality_report": inspection["quality_report"],
                }
            },
            warnings=tuple(inspection.get("warnings", ())),
        )
    if policy.backfill_runner is None and policy.backfill_config_path is None:
        return _ensure_error(
            "backfill_runner_required",
            "Non-dry-run backfill requires an injected runner or bounded config path.",
            data={
                "load_result": {
                    "mode": "backfill",
                    "status": "not_run",
                    "provider_context": _provider_context_from_request(request).to_dict(),
                    "backfill_plan": plan,
                }
            },
        )
    try:
        runner_result = (
            dict(policy.backfill_runner(request, event_store))
            if policy.backfill_runner is not None
            else _run_configured_backfill(event_store, request, policy)
        )
    except Exception as exc:
        return _ensure_error(
            "backfill_failed",
            str(exc),
            data={
                "load_result": {
                    "mode": "backfill",
                    "status": "failed",
                    "provider_context": _provider_context_from_request(request).to_dict(),
                    "backfill_plan": plan,
                }
            },
        )
    post_load = _inspect_data(event_store, request)
    if post_load.get("error") is not None:
        return post_load["error"]
    return success_envelope(
        command=DATA_ENSURE_LOADED,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={
            "load_result": {
                "mode": "backfill",
                "status": "ran",
                "rows_loaded": int(runner_result.get("rows_loaded", runner_result.get("rows_written", 0)) or 0),
                "dry_run": False,
                "provider_context": _provider_context_from_request(request).to_dict(),
                "backfill_plan": plan,
                "runner_result": runner_result,
                "pre_load_manifest": inspection["manifest"],
                "post_load_manifest": post_load["manifest"],
                "post_load_quality_report": post_load["quality_report"],
            }
        },
        warnings=tuple(post_load.get("warnings", ())),
    )


def _run_configured_backfill(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    policy: DataEnsureLoadedPolicy,
) -> dict[str, Any]:
    """Run platform backfill through the Data Agent tool boundary.

    Args:
        event_store: Event store used for allowed local writes.
        request: Normalized ensure-loaded request.
        policy: Runtime policy with a bounded trader config path.

    Returns:
        Backfill runner evidence.

    Raises:
        ValueError: If no bounded config path is supplied or the config is invalid.
    """
    if policy.backfill_config_path is None:
        raise ValueError("Non-dry-run backfill requires a bounded config path.")
    config_data = load_yaml_config(policy.backfill_config_path)
    config = build_config(config_data)
    service_cfg = config_data.get("trader_service", {})
    if service_cfg is None:
        service_cfg = {}
    if not isinstance(service_cfg, Mapping):
        raise ValueError("trader_service section must be a mapping")
    notify_channel = service_cfg.get("notify_channel")
    spec = BackfillSpec(
        start=request.start,
        end=request.end,
        timeframe=parse_timeframe(request.timeframe),
        limit=None,
    )
    runner = MarketDataBackfillRunner(
        config,
        spec,
        symbols=request.symbols,
        asset_class=request.asset_class,
        event_store=event_store,
        notify_channel=str(notify_channel) if notify_channel else None,
    )
    rows_written = runner.run()
    return {
        "runner": "MarketDataBackfillRunner",
        "config_path": str(policy.backfill_config_path),
        "rows_written": rows_written,
        "rows_loaded": rows_written,
        "source": "alpaca",
    }


def _retarget_error(envelope: ToolEnvelope) -> ToolEnvelope:
    """Return an ensure-loaded error from another Data Agent envelope.

    Args:
        envelope: Failed envelope from inventory or quality inspection.

    Returns:
        Failed ensure-loaded envelope preserving the first error code/message.
    """
    first_error = dict(envelope.errors[0]) if envelope.errors else {}
    return error_envelope(
        command=DATA_ENSURE_LOADED,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=str(first_error.get("code", "error")),
        message=str(first_error.get("message", "Data inspection failed.")),
        data=envelope.data,
    )


def _ensure_error(code: str, message: str, *, data: Mapping[str, Any] | None = None) -> ToolEnvelope:
    """Build a failed ensure-loaded envelope.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable error message.
        data: Optional error context.

    Returns:
        Failed Data Agent ensure-loaded envelope.
    """
    return error_envelope(
        command=DATA_ENSURE_LOADED,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
        data=data,
    )
