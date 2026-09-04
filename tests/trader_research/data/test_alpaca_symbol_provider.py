"""Adapter-integration tests for research-owned Alpaca symbol catalogue discovery.

Subject: The Alpaca catalogue adapter used by the Data context for read-only symbol discovery.
Level: In-process adapter integration.
Collaborators: Real research service and provider adapter with an injected fake asset client; no network.
Guarantees: Catalogue calls are read-only, credentials fail explicitly, and provider URLs normalize safely.
Non-goals: Market-bar loading, live Alpaca authentication, trading, inventory, or data-quality assessment.
"""

from __future__ import annotations

from types import SimpleNamespace

from trader.event_store import NoOpEventStore
from trader_research.data import (
    DataSymbolDiscoveryPolicy,
    DataSymbolDiscoveryRequest,
    data_discover_symbols,
)
from trader_research.infrastructure.providers.alpaca import (
    AlpacaSymbolCatalogProvider,
    _trading_client_base_url,
)


class FakeAlpacaAssetClient:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def get_all_assets(self, filter: object = None) -> list[object]:
        self.calls.append(filter)
        return [
            SimpleNamespace(
                symbol="DEMO",
                name="Demo Inc.",
                exchange="TEST",
                status="active",
                tradable=True,
            ),
            SimpleNamespace(
                symbol="SKIP",
                name="Skip Inc.",
                exchange="TEST",
                status="active",
                tradable=False,
            ),
        ]


def test_alpaca_symbol_provider_uses_read_only_asset_listing() -> None:
    """Provider discovery lists assets once and returns only the requested tradable symbol."""
    client = FakeAlpacaAssetClient()
    provider = AlpacaSymbolCatalogProvider(
        api_key="key",
        secret_key="secret",
        client_factory=lambda: client,
    )

    envelope = data_discover_symbols(
        NoOpEventStore(),
        DataSymbolDiscoveryRequest(
            symbols=("DEMO",),
            asset_class="stocks",
            source="provider",
            provider="alpaca",
        ),
        policy=DataSymbolDiscoveryPolicy(
            allow_provider_discovery=True,
            catalog_providers={"alpaca": provider},
        ),
    )

    report = envelope.to_dict()["data"]["symbol_discovery_report"]
    assert envelope.ok is True
    assert len(client.calls) == 1
    assert report["symbols"][0]["symbol"] == "DEMO"
    assert report["symbols"][0]["tradable"] is True


def test_alpaca_symbol_provider_reports_missing_credentials() -> None:
    """Missing provider credentials become an explicit bounded service error before client construction."""
    provider = AlpacaSymbolCatalogProvider(api_key="", secret_key="")

    envelope = data_discover_symbols(
        NoOpEventStore(),
        DataSymbolDiscoveryRequest(
            symbols=("DEMO",),
            asset_class="stocks",
            source="provider",
            provider="alpaca",
        ),
        policy=DataSymbolDiscoveryPolicy(
            allow_provider_discovery=True,
            catalog_providers={"alpaca": provider},
        ),
    )

    assert envelope.ok is False
    assert envelope.errors[0]["code"] == "provider_credentials_missing"


def test_alpaca_symbol_provider_normalizes_trading_client_base_url() -> None:
    """Configured Alpaca API URLs normalize to the client origin without version suffixes."""
    assert (
        _trading_client_base_url("https://paper-api.alpaca.markets/v2")
        == "https://paper-api.alpaca.markets"
    )
    assert (
        _trading_client_base_url("https://paper-api.alpaca.markets/")
        == "https://paper-api.alpaca.markets"
    )
    assert _trading_client_base_url("") is None
