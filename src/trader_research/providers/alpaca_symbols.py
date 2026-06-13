"""Alpaca read-only symbol catalog adapter."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from trader.symbols import canonicalize_symbol

from trader_research.data import DataProviderContext, DataProviderResolutionError, DataSymbolDiscoveryRequest, SymbolCatalogResult


AlpacaClientFactory = Callable[[], Any]


@dataclass(frozen=True)
class AlpacaSymbolCatalogProvider:
    """Read-only Alpaca asset catalog adapter.

    The adapter calls Alpaca's asset listing endpoint only when injected into a
    `DataSymbolDiscoveryPolicy` with provider discovery enabled.
    """

    api_key: str
    secret_key: str
    base_url: str | None = None
    client_factory: AlpacaClientFactory | None = None

    provider_key: str = "alpaca"

    def discover_symbols(
        self,
        request: DataSymbolDiscoveryRequest,
        context: DataProviderContext,
    ) -> SymbolCatalogResult:
        """Return Alpaca asset symbols matching the request."""
        if not self.api_key or not self.secret_key:
            raise DataProviderResolutionError(
                "provider_credentials_missing",
                "Alpaca symbol catalog discovery requires Alpaca API credentials.",
                data={
                    "requested_provider": context.requested_provider,
                    "configured_provider": context.configured_provider,
                    "resolved_provider": context.resolved_provider,
                    "provider_match": context.provider_match,
                },
            )
        client = self.client_factory() if self.client_factory is not None else self._build_client()
        assets = self._fetch_assets(client, request, context)
        rows = _filter_assets(assets, request=request, context=context)
        limit = max(1, min(int(request.limit), 500))
        return SymbolCatalogResult(symbols=tuple(rows[:limit]), truncated=len(rows) > limit)

    def _build_client(self) -> Any:
        """Build the Alpaca trading client lazily."""
        from alpaca.trading.client import TradingClient

        return TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=True,
            raw_data=False,
            url_override=_trading_client_base_url(self.base_url),
        )

    def _fetch_assets(
        self,
        client: Any,
        request: DataSymbolDiscoveryRequest,
        context: DataProviderContext,
    ) -> Sequence[Any]:
        """Fetch assets from Alpaca using the read-only asset-listing API."""
        from alpaca.trading.enums import AssetClass, AssetStatus
        from alpaca.trading.requests import GetAssetsRequest

        asset_class = AssetClass.CRYPTO if context.instrument_type == "crypto" else AssetClass.US_EQUITY
        status = AssetStatus.ACTIVE if request.active_only else None
        return client.get_all_assets(GetAssetsRequest(asset_class=asset_class, status=status))


def _filter_assets(
    assets: Sequence[Any],
    *,
    request: DataSymbolDiscoveryRequest,
    context: DataProviderContext,
) -> list[dict[str, Any]]:
    """Filter and normalize Alpaca asset records."""
    requested = {
        canonicalize_symbol(symbol, asset_class=context.legacy_asset_class)
        for symbol in request.symbols
        if str(symbol).strip()
    }
    query = str(request.query).strip().upper() if request.query is not None else ""
    rows: list[dict[str, Any]] = []
    for asset in assets:
        raw_symbol = str(getattr(asset, "symbol", "") or "").strip().upper()
        if not raw_symbol:
            continue
        symbol = canonicalize_symbol(raw_symbol, asset_class=context.legacy_asset_class)
        name = getattr(asset, "name", None)
        if requested and symbol not in requested:
            continue
        if query and query not in symbol.upper() and query not in str(name or "").upper():
            continue
        tradable = getattr(asset, "tradable", None)
        if request.tradable_only and tradable is False:
            continue
        status = getattr(asset, "status", None)
        rows.append(
            {
                "symbol": symbol,
                "raw_symbol": raw_symbol,
                "name": name,
                "exchange": _enum_value(getattr(asset, "exchange", None)),
                "status": _enum_value(status),
                "tradable": tradable,
                "exists": True,
            }
        )
    return rows


def _enum_value(value: Any) -> Any:
    """Return enum values as JSON-friendly scalars."""
    return getattr(value, "value", value)


def _trading_client_base_url(value: str | None) -> str | None:
    """Return an Alpaca TradingClient-compatible base URL."""
    base_url = str(value or "").strip().rstrip("/")
    if not base_url:
        return None
    if base_url.endswith("/v2"):
        return base_url.removesuffix("/v2")
    return base_url
