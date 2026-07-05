"""Data Agent services for discovery, inventory, quality, and loading.

The package is the canonical public surface for MCP-facing Data Agent
capabilities. Implementations live in `services` so callers can depend on a
bounded package rather than a broad top-level module.
"""

from .services import (
    DATA_DISCOVER_SYMBOLS,
    DATA_ENSURE_LOADED,
    DATA_GET_INVENTORY,
    DATA_SUMMARIZE_QUALITY,
    BackfillRunner,
    DataEnsureLoadedPolicy,
    DataEnsureLoadedRequest,
    DataInventoryRequest,
    DataProviderCapability,
    DataProviderContext,
    DataProviderResolutionError,
    DataQualityRequest,
    DataSymbolDiscoveryPolicy,
    DataSymbolDiscoveryRequest,
    SymbolCatalogProvider,
    SymbolCatalogResult,
    data_discover_symbols,
    data_ensure_loaded,
    data_summarize_quality,
    get_data_inventory,
    resolve_data_provider_context,
)

__all__ = [
    "DATA_DISCOVER_SYMBOLS",
    "DATA_ENSURE_LOADED",
    "DATA_GET_INVENTORY",
    "DATA_SUMMARIZE_QUALITY",
    "BackfillRunner",
    "DataEnsureLoadedPolicy",
    "DataEnsureLoadedRequest",
    "DataInventoryRequest",
    "DataProviderCapability",
    "DataProviderContext",
    "DataProviderResolutionError",
    "DataQualityRequest",
    "DataSymbolDiscoveryPolicy",
    "DataSymbolDiscoveryRequest",
    "SymbolCatalogProvider",
    "SymbolCatalogResult",
    "data_discover_symbols",
    "data_ensure_loaded",
    "data_summarize_quality",
    "get_data_inventory",
    "resolve_data_provider_context",
]
