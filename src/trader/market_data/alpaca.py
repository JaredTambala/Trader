"""Alpaca market data ingestion using alpaca-py clients."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Sequence

from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from .alpaca_payloads import (
    AlpacaRequestSpec,
    _bar_value as _bar_value,
    _build_bars_request as _build_bars_request,
    _build_crypto_bars_request as _build_crypto_bars_request,
    _build_crypto_latest_bar_request as _build_crypto_latest_bar_request,
    _build_latest_bar_request as _build_latest_bar_request,
    _coerce_timestamp as _coerce_timestamp,
    _default_request_spec as _default_request_spec,
    _extract_bar_data as _extract_bar_data,
    _normalize_stock_feed as _normalize_stock_feed,
    _optional_float as _optional_float,
    _serialize_bar as _serialize_bar,
    build_alpaca_bar_event,
)

from .domain import CryptoBarEvent, MarketDataSource, StockBarEvent


logger = logging.getLogger(__name__)


class AlpacaMarketDataSource(MarketDataSource):
    """Polling source that converts Alpaca bar responses into local events.

    The source builds the appropriate stock or crypto data client, requests a
    short recent window, selects the latest complete bar per configured symbol,
    and normalizes provider-specific bar objects or mappings into
    `StockBarEvent`/`CryptoBarEvent` instances.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        base_url: str,
        symbols: Sequence[str],
        asset_class: str = "stocks",
        stock_feed: str | None = None,
        client: object | None = None,
        request_spec: AlpacaRequestSpec | None = None,
    ) -> None:
        """Initialize the Alpaca market data source.

        Args:
            api_key: Alpaca API key (required for stocks).
            secret_key: Alpaca secret key (required for stocks).
            base_url: Alpaca data API base URL.
            symbols: Symbols to request.
            asset_class: Asset class ("stocks" or "crypto").
            stock_feed: Stock data feed (iex or sip).
            client: Optional alpaca-py client override.
            request_spec: Optional request spec override (timeframe/limit).

        Raises:
            ValueError: If asset_class is unsupported.
        """
        self._symbols = [symbol.upper() for symbol in symbols]
        self._asset_class = asset_class.lower()
        self._request_spec = request_spec or _default_request_spec(self._asset_class, stock_feed)

        if client is None:
            client = _build_client(self._asset_class, api_key, secret_key, base_url)

        self._client = client

    def fetch(self) -> Sequence[StockBarEvent | CryptoBarEvent]:
        """Fetch the latest bar per symbol from Alpaca.

        Returns:
            Sequence of MarketDataEvent items.

        Raises:
            Exception: Propagates Alpaca client errors.
            ValueError: If bar timestamps are malformed.
        """
        if not self._symbols:
            return []

        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(minutes=5)
        logger.info(
            "Alpaca fetch start asset_class=%s symbols=%s timeframe=%s limit=%s",
            self._asset_class,
            ",".join(self._symbols),
            self._request_spec.timeframe,
            self._request_spec.limit,
        )
        request = self._request_spec.request_builder(
            self._symbols,
            window_start,
            window_end,
            self._request_spec.timeframe,
            self._request_spec.limit,
            self._request_spec.feed,
        )

        response = _fetch_data(self._client, self._asset_class, self._request_spec.method, request)
        data = _extract_bar_data(response)
        ingested_at = datetime.now(timezone.utc)
        timeframe_label = str(self._request_spec.timeframe)

        events: list[StockBarEvent | CryptoBarEvent] = []
        for symbol in self._symbols:
            bars = data.get(symbol, [])
            if not bars:
                logger.warning("Missing market data bar", extra={"symbol": symbol})
                continue

            bar = bars[-1] if isinstance(bars, Sequence) else bars
            event = build_alpaca_bar_event(
                asset_class=self._asset_class,
                symbol=symbol,
                bar=bar,
                ingested_at=ingested_at,
                timeframe=timeframe_label,
            )
            if event is None:
                logger.warning(
                    "Incomplete market data bar symbol=%s bar=%s",
                    symbol,
                    _serialize_bar(bar),
                )
                continue
            events.append(event)

        logger.info("Alpaca fetch complete count=%s", len(events))
        return events


def _build_client(asset_class: str, api_key: str, secret_key: str, base_url: str) -> object:
    """Create an alpaca-py historical data client.

    Args:
        asset_class: Asset class identifier.
        api_key: Alpaca API key.
        secret_key: Alpaca secret key.
        base_url: Alpaca data base URL.

    Returns:
        Alpaca historical data client instance.

    Raises:
        ValueError: If asset_class is unsupported.
    """
    asset_class = asset_class.lower()
    if asset_class in {"crypto", "cryptocurrency"}:
        return CryptoHistoricalDataClient(url_override=base_url)
    if asset_class in {"stocks", "stock"}:
        return StockHistoricalDataClient(api_key, secret_key, url_override=base_url)
    raise ValueError(f"Unsupported asset class: {asset_class}")


def _fetch_data(client: object, asset_class: str, method: str, request: object) -> object:
    """Fetch market data using the correct alpaca-py method.

    Args:
        client: Alpaca historical data client.
        asset_class: Asset class identifier.
        method: Request type ("bars" or "latest_bar").
        request: Request payload.

    Returns:
        Alpaca response object.
    """
    asset_class = asset_class.lower()
    if asset_class in {"crypto", "cryptocurrency"}:
        if method == "latest_bar":
            return client.get_crypto_latest_bar(request)
        return client.get_crypto_bars(request)
    if method == "latest_bar":
        return client.get_stock_latest_bar(request)
    return client.get_stock_bars(request)
