"""Public Data Agent application facade.

Callers enter through this package surface. The domain, catalog, inventory,
quality, and loading modules remain implementation details of the Data context.
External provider adapters live under :mod:`trader_research.infrastructure`.
"""

from .catalog import data_discover_symbols, resolve_data_provider_context
from .domain import (
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
)
from .evidence import DATA_CREATE_RESEARCH_SNAPSHOT, create_data_research_snapshot
from .inventory import get_data_inventory
from .loading import data_ensure_loaded
from .quality import data_summarize_quality

__all__ = [
    "DATA_DISCOVER_SYMBOLS",
    "DATA_CREATE_RESEARCH_SNAPSHOT",
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
    "create_data_research_snapshot",
    "data_ensure_loaded",
    "data_summarize_quality",
    "get_data_inventory",
    "resolve_data_provider_context",
]
