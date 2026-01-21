"""Streaming market data ingestion using Alpaca websocket APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import signal
import argparse
from typing import Mapping, Sequence

from alpaca.data.enums import CryptoFeed, DataFeed
from alpaca.data.live.crypto import CryptoDataStream
from alpaca.data.live.stock import StockDataStream
from dotenv import load_dotenv

from .config import Config, load_config
from .data import EventStore, build_event_store
from .market_data import CryptoBarEvent, StockBarEvent


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamContext:
    """Shared state for streaming callbacks."""

    event_store: EventStore
    asset_class: str
    source: str
    timeframe: str


class MarketDataStreamRunner:
    """Run Alpaca websocket streaming and persist bars to DuckDB."""

    def __init__(
        self,
        config: Config,
        event_store: EventStore | None = None,
        symbols: Sequence[str] | None = None,
    ) -> None:
        """Initialize the streaming runner.

        Args:
            config: Loaded configuration values.
            event_store: Optional event store override.
            symbols: Optional symbol override for streaming.

        Raises:
            ValueError: If config contains unsupported values.
        """
        self._config = config
        self._asset_class = config.market_data_asset_class.lower()
        self._symbols = list(symbols) if symbols else list(config.market_data_symbols)
        self._stream = _build_stream(config)
        self._event_store = event_store or build_event_store(config)
        self._owns_event_store = event_store is None
        self._context = StreamContext(
            event_store=self._event_store,
            asset_class=self._asset_class,
            source="alpaca",
            timeframe="1Min",
        )

    def run(self) -> None:
        """Start the streaming loop and persist incoming bars.

        Raises:
            ValueError: If configuration is incomplete.
        """
        if self._config.market_data_source.lower() != "alpaca":
            logger.warning("MARKET_DATA_SOURCE is not alpaca; skipping streaming")
            if self._owns_event_store:
                self._event_store.close()
            return
        if not self._symbols:
            logger.warning("MARKET_DATA_SYMBOLS is empty; nothing to stream")
            if self._owns_event_store:
                self._event_store.close()
            return

        self._stream.subscribe_bars(self._handle_bar, *self._symbols)
        _install_signal_handlers(self._stream)
        logger.info(
            "Market data stream started asset_class=%s symbols=%s",
            self._asset_class,
            ",".join(self._symbols),
        )
        try:
            self._stream.run()
        finally:
            if self._owns_event_store:
                self._event_store.close()

    async def _handle_bar(self, bar: object) -> None:
        """Handle a single bar event from the websocket stream.

        Args:
            bar: Alpaca bar object or mapping payload.

        Raises:
            None.
        """
        event = _build_bar_event(self._context, bar)
        if event is None:
            logger.warning("Skipping incomplete market data bar")
            return
        try:
            self._event_store.record_event(event.table_name, event.to_payload())
        except Exception as exc:
            logger.exception("Failed to persist market data bar: %s", exc)
            return
        logger.info(
            "Market data streamed symbol=%s ts=%s close=%s volume=%s source=%s",
            event.symbol,
            event.ts.isoformat(),
            event.close,
            event.volume,
            event.source,
        )


def _build_stream(config: Config) -> StockDataStream | CryptoDataStream:
    """Construct the Alpaca websocket stream client.

    Args:
        config: Loaded configuration values.

    Returns:
        Alpaca websocket client instance.

    Raises:
        ValueError: If required credentials or asset class are missing.
    """
    asset_class = config.market_data_asset_class.lower()
    if not config.alpaca_api_key or not config.alpaca_secret_key:
        raise ValueError("Alpaca API key and secret are required for streaming")
    if asset_class in {"stocks", "stock"}:
        feed = _normalize_stock_feed(config.market_data_stock_feed)
        return StockDataStream(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            feed=feed,
        )
    if asset_class in {"crypto", "cryptocurrency"}:
        return CryptoDataStream(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            feed=CryptoFeed.US,
        )
    raise ValueError(f"Unsupported asset class: {config.market_data_asset_class}")


def _install_signal_handlers(stream: object) -> None:
    """Register SIGINT/SIGTERM handlers to stop streaming cleanly.

    Args:
        stream: Alpaca websocket stream client.

    Raises:
        None.
    """
    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("Shutdown signal received (%s); stopping stream", signum)
        stream.stop()
        stream.close()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


def _build_bar_event(context: StreamContext, bar: object) -> StockBarEvent | CryptoBarEvent | None:
    """Convert a websocket bar payload into a bar event.

    Args:
        context: Stream metadata for event creation.
        bar: Alpaca bar object or mapping payload.

    Returns:
        StockBarEvent or CryptoBarEvent, or None if data is incomplete.
    """
    symbol = _bar_value(bar, "symbol", ("symbol", "S", "s"))
    ts_value = _bar_value(bar, "t", ("t", "timestamp", "time"))
    open_value = _bar_value(bar, "o", ("o", "open"))
    high_value = _bar_value(bar, "h", ("h", "high"))
    low_value = _bar_value(bar, "l", ("l", "low"))
    close_value = _bar_value(bar, "c", ("c", "close", "price"))
    volume_value = _bar_value(bar, "v", ("v", "volume"))
    if None in (symbol, ts_value, open_value, high_value, low_value, close_value, volume_value):
        return None

    trade_count = _optional_float(_bar_value(bar, "n", ("n", "trade_count")))
    vwap = _optional_float(_bar_value(bar, "vw", ("vw", "vwap")))
    common = dict(
        symbol=str(symbol),
        ts=_coerce_timestamp(ts_value),
        ingested_at=datetime.now(timezone.utc),
        open=float(open_value),
        high=float(high_value),
        low=float(low_value),
        close=float(close_value),
        volume=float(volume_value),
        trade_count=trade_count,
        vwap=vwap,
        source=context.source,
    )
    if context.asset_class in {"crypto", "cryptocurrency"}:
        return CryptoBarEvent(timeframe=context.timeframe, **common)
    return StockBarEvent(timeframe=context.timeframe, **common)


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
    """
    if value is None:
        return None
    return float(value)


def _normalize_stock_feed(feed: str | None) -> DataFeed:
    """Normalize stock feed configuration for Alpaca streams.

    Args:
        feed: Feed identifier string.

    Returns:
        DataFeed enum (defaults to IEX).
    """
    if not feed:
        return DataFeed.IEX
    feed_value = feed.strip().lower()
    if feed_value == "sip":
        return DataFeed.SIP
    return DataFeed.IEX


def _parse_symbols_arg(value: str) -> list[str]:
    """Parse a comma-delimited symbol list for CLI overrides.

    Args:
        value: Comma-separated string of symbols.

    Returns:
        List of normalized symbols.
    """
    symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
    return symbols


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the stream runner."""
    parser = argparse.ArgumentParser(description="Stream Alpaca market data bars.")
    parser.add_argument(
        "--symbols",
        help="Comma-separated symbols to stream (overrides MARKET_DATA_SYMBOLS).",
    )
    return parser.parse_args()


def main() -> None:
    """Module entry point for market data streaming."""
    load_dotenv(".env")
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    config = load_config()
    symbols = _parse_symbols_arg(args.symbols) if args.symbols else None
    runner = MarketDataStreamRunner(config, symbols=symbols)
    runner.run()


if __name__ == "__main__":
    main()
