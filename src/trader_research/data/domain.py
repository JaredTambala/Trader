"""Data Agent request, provider, and policy value objects."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from trader.event_store import EventStore


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
    value required by existing event-store queries, allowing results to expose
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
        """Serialize provider resolution details into a JSON-safe result payload.

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
    """Resolution failure that preserves a stable code and result-ready details.

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
    result can distinguish a complete exact validation from a bounded preview.
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

    @property
    def provider_key(self) -> str:
        """Return the provider key used to register this adapter."""

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
