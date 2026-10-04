"""Unit contracts for provider context and research symbol discovery.

Subject: Provider normalization plus local, configured, and injected-catalogue symbol discovery paths.
Level: In-process unit contract.
Collaborators: Real Data services, shared DuckDB, sample bars, no-op store, and a fake catalogue.
Guarantees: Provider mismatches fail early and discovery reports normalized identity and coverage evidence.
Non-goals: The concrete Alpaca adapter, provider network calls, backfill execution, or workflow routing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tests.support.duckdb_store import DuckDBEventStore
from trader.event_store import NoOpEventStore
from trader.market_data.sample import load_sample_market_data_csv
from trader_research.data import (
    DataEnsureLoadedRequest,
    DataInventoryRequest,
    DataProviderResolutionError,
    DataQualityRequest,
    DataSymbolDiscoveryPolicy,
    DataSymbolDiscoveryRequest,
    SymbolCatalogResult,
    data_discover_symbols,
    data_ensure_loaded,
    data_summarize_quality,
    get_data_inventory,
    resolve_data_provider_context,
)


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


def test_provider_context_resolves_alpaca_stock_defaults() -> None:
    """Default stock requests resolve to normalized Alpaca trade-bar provider context."""
    context = resolve_data_provider_context(asset_class="stocks")

    assert context.resolved_provider == "alpaca"
    assert context.instrument_type == "stock"
    assert context.bar_type == "trade_bar"
    assert context.legacy_asset_class == "stocks"
    assert context.provider_match is True


def test_provider_context_rejects_mismatched_provider() -> None:
    """A requested provider differing from configuration fails with both identities visible."""
    try:
        resolve_data_provider_context(
            provider="polygon", configured_provider="alpaca", asset_class="stocks"
        )
    except DataProviderResolutionError as exc:
        assert exc.code == "provider_not_configured"
        assert exc.data["requested_provider"] == "polygon"
        assert exc.data["configured_provider"] == "alpaca"
        assert exc.data["resolved_provider"] is None
    else:
        raise AssertionError("expected provider_not_configured")


def test_provider_context_rejects_unsupported_instrument_and_bar_type() -> None:
    """Unsupported instruments and bar types fail with distinct provider-resolution codes."""
    for kwargs, code in (
        ({"asset_class": "forex"}, "unsupported_instrument_type"),
        ({"asset_class": "stocks", "bar_type": "quote_bar"}, "unsupported_bar_type"),
    ):
        try:
            resolve_data_provider_context(**kwargs)
        except DataProviderResolutionError as exc:
            assert exc.code == code
        else:
            raise AssertionError(f"expected {code}")


def test_existing_data_tools_fail_fast_on_provider_mismatch() -> None:
    """Inventory, quality, and readiness share the same early provider-mismatch rejection."""
    common = {
        "symbols": ("DEMO",),
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
        "provider": "polygon",
        "configured_provider": "alpaca",
    }

    inventory = get_data_inventory(NoOpEventStore(), DataInventoryRequest(**common))
    quality = data_summarize_quality(NoOpEventStore(), DataQualityRequest(**common))
    ensure = data_ensure_loaded(
        NoOpEventStore(), DataEnsureLoadedRequest(**common, mode="existing")
    )

    assert inventory.errors[0]["code"] == "provider_not_configured"
    assert quality.errors[0]["code"] == "provider_not_configured"
    assert ensure.errors[0]["code"] == "provider_not_configured"


def test_existing_data_tools_include_provider_context_on_success(
    tmp_path: Path,
) -> None:
    """Successful inventory evidence retains normalized provider, instrument, and bar-type identity."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)

    envelope = get_data_inventory(
        store,
        DataInventoryRequest(
            symbols=("DEMO",),
            asset_class="stocks",
            timeframe="1Min",
            start=datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
            end=datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc),
            provider="alpaca",
            configured_provider="alpaca",
        ),
    )

    assert envelope.ok is True
    manifest = envelope.to_dict()["data"]["dataset_manifest"]
    assert manifest["resolved_provider"] == "alpaca"
    assert manifest["instrument_type"] == "stock"
    assert manifest["bar_type"] == "trade_bar"


def test_symbol_discovery_validates_local_symbols_with_coverage(tmp_path: Path) -> None:
    """Local discovery distinguishes present and missing symbols while attaching stored coverage evidence."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)

    envelope = data_discover_symbols(
        store,
        DataSymbolDiscoveryRequest(
            symbols=("DEMO", "MISSING"),
            asset_class="stocks",
            source="local",
            include_local_coverage=True,
        ),
    )

    report = envelope.to_dict()["data"]["symbol_discovery_report"]
    assert envelope.ok is True
    assert report["resolved_provider"] == "alpaca"
    assert report["instrument_type"] == "stock"
    assert report["all_requested_symbols_exist"] is False
    assert report["missing_symbols"] == ["MISSING"]
    assert report["symbols"][0]["symbol"] == "DEMO"
    assert report["symbols"][0]["local_coverage"]["row_count"] == 12


def test_symbol_discovery_validates_configured_crypto_symbols() -> None:
    """Configured crypto discovery normalizes symbols and identifies absent requested assets."""
    envelope = data_discover_symbols(
        NoOpEventStore(),
        DataSymbolDiscoveryRequest(
            symbols=("BTCUSD", "ETHUSD"),
            asset_class="crypto",
            source="configured",
            configured_provider="alpaca",
            configured_asset_class="crypto",
            configured_symbols=("BTC/USD",),
        ),
    )

    report = envelope.to_dict()["data"]["symbol_discovery_report"]
    assert envelope.ok is True
    assert report["instrument_type"] == "crypto"
    assert report["legacy_asset_class"] == "crypto"
    assert report["requested_symbols"] == ["BTC/USD", "ETH/USD"]
    assert report["missing_symbols"] == ["ETH/USD"]
    assert report["symbols"][0]["symbol"] == "BTC/USD"


def test_symbol_discovery_rejects_provider_source_without_policy() -> None:
    """Provider-backed discovery remains unavailable until policy explicitly permits external catalogue use."""
    envelope = data_discover_symbols(
        NoOpEventStore(),
        DataSymbolDiscoveryRequest(
            symbols=("DEMO",), asset_class="stocks", source="provider"
        ),
    )

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == "provider_discovery_not_allowed"


class FakeCatalogProvider:
    provider_key = "alpaca"

    def discover_symbols(
        self,
        request: DataSymbolDiscoveryRequest,
        context: object,
    ) -> SymbolCatalogResult:
        return SymbolCatalogResult(
            symbols=(
                {
                    "symbol": "DEMO",
                    "raw_symbol": "DEMO",
                    "name": "Demo Inc.",
                    "exchange": "TEST",
                    "status": "active",
                    "tradable": True,
                },
            )
        )


class MetadataCatalogProvider:
    """Return injected catalogue metadata for capability-state contracts."""

    provider_key = "alpaca"

    def __init__(self, result: SymbolCatalogResult) -> None:
        self.result = result

    def discover_symbols(
        self,
        request: DataSymbolDiscoveryRequest,
        context: object,
    ) -> SymbolCatalogResult:
        return self.result


def test_symbol_discovery_uses_injected_provider_catalog_adapter() -> None:
    """Authorized discovery consumes an injected catalogue and reports its normalized provider metadata."""
    envelope = data_discover_symbols(
        NoOpEventStore(),
        DataSymbolDiscoveryRequest(
            symbols=("DEMO",), asset_class="stocks", source="provider"
        ),
        policy=DataSymbolDiscoveryPolicy(
            allow_provider_discovery=True,
            catalog_providers={"alpaca": FakeCatalogProvider()},
        ),
    )

    report = envelope.to_dict()["data"]["symbol_discovery_report"]
    assert envelope.ok is True
    assert report["all_requested_symbols_exist"] is True
    assert report["symbols"][0]["source"] == "provider"
    assert report["symbols"][0]["exchange"] == "TEST"


def test_symbol_discovery_publishes_complete_and_load_capable_state() -> None:
    """A complete provider catalogue keeps discovery evidence separate from load capability."""
    envelope = data_discover_symbols(
        NoOpEventStore(),
        DataSymbolDiscoveryRequest(symbols=("DEMO",), asset_class="stocks", source="provider"),
        policy=DataSymbolDiscoveryPolicy(
            allow_provider_discovery=True,
            catalog_providers={
                "alpaca": MetadataCatalogProvider(
                    SymbolCatalogResult(
                        symbols=({"symbol": "DEMO"},),
                        completeness="complete",
                        freshness="fresh",
                        can_load=True,
                        load_capability="load_capable",
                    )
                )
            },
        ),
    )

    report = envelope.to_dict()["data"]["symbol_discovery_report"]
    assert report["discovery_capability"] == {
        "completeness": "complete",
        "freshness": "fresh",
        "can_discover": True,
        "can_load": True,
        "load_capability": "load_capable",
        "reason": None,
    }


def test_symbol_discovery_publishes_partial_and_stale_provider_state() -> None:
    """Bounded or stale catalogues remain explicit instead of appearing complete."""
    for metadata in (
        {"completeness": "partial", "freshness": "fresh"},
        {"completeness": "stale", "freshness": "stale"},
    ):
        envelope = data_discover_symbols(
            NoOpEventStore(),
            DataSymbolDiscoveryRequest(asset_class="stocks", source="provider"),
            policy=DataSymbolDiscoveryPolicy(
                allow_provider_discovery=True,
                catalog_providers={
                    "alpaca": MetadataCatalogProvider(
                        SymbolCatalogResult(symbols=(), **metadata)  # type: ignore[arg-type]
                    )
                },
            ),
        )
        report = envelope.to_dict()["data"]["symbol_discovery_report"]
        assert report["catalogue_completeness"] == metadata["completeness"]
        assert report["catalogue_freshness"] == metadata["freshness"]
        assert report["can_load"] is False
        assert report["load_capability"] == "discover_only"


def test_symbol_discovery_preserves_provider_load_capable_stale_state() -> None:
    """A stale catalogue can still report explicit provider loading capability."""
    envelope = data_discover_symbols(
        NoOpEventStore(),
        DataSymbolDiscoveryRequest(asset_class="stocks", source="provider"),
        policy=DataSymbolDiscoveryPolicy(
            allow_provider_discovery=True,
            catalog_providers={
                "alpaca": MetadataCatalogProvider(
                    SymbolCatalogResult(
                        symbols=(),
                        completeness="stale",
                        freshness="stale",
                        can_load=True,
                        load_capability="load_capable",
                    )
                )
            },
        ),
    )

    report = envelope.to_dict()["data"]["symbol_discovery_report"]
    assert report["catalogue_completeness"] == "stale"
    assert report["catalogue_freshness"] == "stale"
    assert report["can_load"] is True
    assert report["load_capability"] == "load_capable"


def test_symbol_discovery_publishes_provider_unavailable_state() -> None:
    """A provider policy with no adapter exposes unavailable catalogue and load state."""
    envelope = data_discover_symbols(
        NoOpEventStore(),
        DataSymbolDiscoveryRequest(asset_class="stocks", source="provider"),
        policy=DataSymbolDiscoveryPolicy(allow_provider_discovery=True),
    )

    payload = envelope.to_dict()
    assert payload["ok"] is False
    assert payload["data"]["discovery_capability"]["completeness"] == "unavailable"
    assert payload["data"]["discovery_capability"]["load_capability"] == "unavailable"


def test_symbol_discovery_publishes_unavailable_state_for_provider_failure() -> None:
    """Policy or provider failures expose unavailable capability evidence in MCP data."""
    envelope = data_discover_symbols(
        NoOpEventStore(),
        DataSymbolDiscoveryRequest(asset_class="stocks", source="provider"),
    )

    payload = envelope.to_dict()
    assert payload["ok"] is False
    assert payload["data"]["discovery_capability"] == {
        "completeness": "unavailable",
        "freshness": "unknown",
        "can_discover": False,
        "can_load": False,
        "load_capability": "unavailable",
        "reason": "Provider catalogue discovery is not allowed by policy.",
    }


def test_configured_symbol_discovery_publishes_unavailable_state() -> None:
    """An unavailable configured universe is a typed state rather than a generic validation error."""
    envelope = data_discover_symbols(
        NoOpEventStore(),
        DataSymbolDiscoveryRequest(
            asset_class="stocks",
            source="configured",
            configured_universe_available=False,
        ),
    )

    report = envelope.to_dict()["data"]["symbol_discovery_report"]
    assert report["catalogue_completeness"] == "unavailable"
    assert report["can_discover"] is False
    assert report["load_capability"] == "unavailable"
