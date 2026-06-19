"""Alpaca market data ingestion using alpaca-py clients."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Callable, Mapping, Sequence

from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.enums import DataFeed
from alpaca.data.requests import (
    CryptoBarsRequest,
    CryptoLatestBarRequest,
    StockBarsRequest,
    StockLatestBarRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from .domain import CryptoBarEvent, MarketDataSource, StockBarEvent


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlpacaRequestSpec:
    """Alpaca request strategy used by the polling source.

    Attributes:
        request_builder: Function that builds the alpaca-py request object.
        timeframe: Alpaca timeframe object attached to the request.
        limit: Maximum bars requested per symbol.
        method: Client method family to call, such as latest-bar reads.
        feed: Optional data feed for stock requests.
    """

    request_builder: Callable[[Sequence[str], datetime, datetime, object, int, object | None], object]
    timeframe: object
    limit: int
    method: str
    feed: object | None


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
            ts_value = _bar_value(bar, "t", ("t", "timestamp", "time"))
            open_value = _bar_value(bar, "o", ("o", "open"))
            high_value = _bar_value(bar, "h", ("h", "high"))
            low_value = _bar_value(bar, "l", ("l", "low"))
            close_value = _bar_value(bar, "c", ("c", "close", "price"))
            volume_value = _bar_value(bar, "v", ("v", "volume"))
            if None in (ts_value, open_value, high_value, low_value, close_value, volume_value):
                logger.warning(
                    "Incomplete market data bar symbol=%s bar=%s",
                    symbol,
                    _serialize_bar(bar),
                )
                continue

            trade_count = _optional_float(_bar_value(bar, "n", ("n", "trade_count")))
            vwap = _optional_float(_bar_value(bar, "vw", ("vw", "vwap")))
            common = dict(
                symbol=symbol,
                ts=_coerce_timestamp(ts_value),
                ingested_at=ingested_at,
                open=float(open_value),
                high=float(high_value),
                low=float(low_value),
                close=float(close_value),
                volume=float(volume_value),
                trade_count=trade_count,
                vwap=vwap,
                source="alpaca",
            )
            if self._asset_class in {"crypto", "cryptocurrency"}:
                events.append(CryptoBarEvent(timeframe=timeframe_label, **common))
            else:
                events.append(StockBarEvent(timeframe=timeframe_label, **common))

        logger.info("Alpaca fetch complete count=%s", len(events))
        return events


def _default_request_spec(asset_class: str, stock_feed: str | None = None) -> AlpacaRequestSpec:
    """Return default request parameters for Alpaca bars.

    Args:
        asset_class: Asset class identifier.
        stock_feed: Stock feed identifier (iex or sip).

    Returns:
        AlpacaRequestSpec with request builder, timeframe, and limit.

    Raises:
        None.
    """
    asset_class = asset_class.lower()
    if asset_class in {"crypto", "cryptocurrency"}:
        return AlpacaRequestSpec(
            request_builder=_build_crypto_latest_bar_request,
            timeframe=TimeFrame(amount=1, unit=TimeFrameUnit.Minute),
            limit=1,
            method="latest_bar",
            feed=None,
        )
    feed = _normalize_stock_feed(stock_feed)
    return AlpacaRequestSpec(
        request_builder=_build_latest_bar_request,
        timeframe=TimeFrame(amount=1, unit=TimeFrameUnit.Minute),
        limit=1,
        method="latest_bar",
        feed=feed,
    )


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


def _build_bars_request(
    symbols: Sequence[str],
    start: datetime,
    end: datetime,
    timeframe: object,
    limit: int,
    feed: object | None,
) -> object:
    """Build a StockBarsRequest for alpaca-py.

    Args:
        symbols: Symbols to request.
        start: Start time.
        end: End time.
        timeframe: Alpaca timeframe.
        limit: Max bars per symbol.
        feed: Stock data feed (iex or sip).

    Returns:
        StockBarsRequest instance.
    """
    return StockBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
        feed=feed,
    )


def _build_latest_bar_request(
    symbols: Sequence[str],
    start: datetime,
    end: datetime,
    timeframe: object,
    limit: int,
    feed: object | None,
) -> object:
    """Build a StockLatestBarRequest for alpaca-py.

    Args:
        symbols: Symbols to request.
        start: Ignored for latest bar request.
        end: Ignored for latest bar request.
        timeframe: Ignored for latest bar request.
        limit: Ignored for latest bar request.
        feed: Stock data feed (iex or sip).

    Returns:
        StockLatestBarRequest instance.
    """
    return StockLatestBarRequest(symbol_or_symbols=list(symbols), feed=feed)


def _build_crypto_bars_request(
    symbols: Sequence[str],
    start: datetime,
    end: datetime,
    timeframe: object,
    limit: int,
    feed: object | None,
) -> object:
    """Build a CryptoBarsRequest for alpaca-py.

    Args:
        symbols: Symbols to request.
        start: Start time.
        end: End time.
        timeframe: Alpaca timeframe.
        limit: Max bars per symbol.
        feed: Ignored for crypto requests.

    Returns:
        CryptoBarsRequest instance.
    """
    return CryptoBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
    )


def _build_crypto_latest_bar_request(
    symbols: Sequence[str],
    start: datetime,
    end: datetime,
    timeframe: object,
    limit: int,
    feed: object | None,
) -> object:
    """Build a CryptoLatestBarRequest for alpaca-py.

    Args:
        symbols: Symbols to request.
        start: Ignored for latest bar request.
        end: Ignored for latest bar request.
        timeframe: Ignored for latest bar request.
        limit: Ignored for latest bar request.
        feed: Ignored for crypto requests.

    Returns:
        CryptoLatestBarRequest instance.
    """
    return CryptoLatestBarRequest(symbol_or_symbols=list(symbols))


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


def _extract_bar_data(response: object) -> Mapping[str, Sequence[object]]:
    """Normalize Alpaca responses into a symbol-to-bars mapping.

    Args:
        response: Alpaca response object.

    Returns:
        Mapping of symbol to bar sequence.
    """
    if hasattr(response, "data"):
        return response.data
    if isinstance(response, Mapping):
        return response
    return {}


def _bar_value(bar: object, attr: str, keys: tuple[str, ...]) -> object | None:
    """Extract a value from bar objects or mappings.

    Args:
        bar: Alpaca bar object or mapping.
        attr: Attribute name to check on objects.
        keys: Mapping keys to check if bar is a dict.

    Returns:
        Extracted value or None.
    """
    if hasattr(bar, attr):
        return getattr(bar, attr)
    for key in keys:
        if hasattr(bar, key):
            return getattr(bar, key)
    if isinstance(bar, Mapping):
        for key in keys:
            if key in bar:
                return bar[key]
    return None


def _coerce_timestamp(value: object) -> datetime:
    """Convert Alpaca timestamp values into UTC datetimes.

    Args:
        value: Timestamp value from Alpaca response.

    Returns:
        UTC-aware datetime.

    Raises:
        ValueError: If the value cannot be converted.
    """
    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, str):
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Unsupported timestamp value")

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _optional_float(value: object) -> float | None:
    """Convert numeric values to float when present.

    Args:
        value: Value to convert.

    Returns:
        Float value or None.

    Raises:
        ValueError: If conversion fails.
    """
    if value is None:
        return None
    return float(value)


def _normalize_stock_feed(feed: str | None) -> DataFeed | None:
    """Normalize stock feed configuration for Alpaca requests.

    Args:
        feed: Feed identifier string.

    Returns:
        DataFeed enum or None when unspecified.
    """
    if not feed:
        return None
    feed_value = feed.strip().lower()
    if feed_value == "sip":
        return DataFeed.SIP
    return DataFeed.IEX


def _serialize_bar(bar: object) -> str:
    """Render bar data for logging without raising errors.

    Args:
        bar: Alpaca bar object or mapping.

    Returns:
        String representation for debug logs.
    """
    if isinstance(bar, Mapping):
        return str(bar)
    if hasattr(bar, "__dict__"):
        return str(bar.__dict__)
    return repr(bar)
