"""Market data ingestion sources and helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import AsyncIterator, Iterable, Sequence

from ..event_store import EventStore


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StockBarEvent:
    """Normalized stock OHLCV bar ready for event-store persistence.

    Attributes mirror the `stock_bar_events` schema. `ts` is the provider bar
    timestamp, while `ingested_at` records when this process accepted the bar.
    """

    symbol: str
    timeframe: str
    ts: datetime
    ingested_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: float | None
    vwap: float | None
    source: str

    @property
    def table_name(self) -> str:
        """Return the event-store table used for normalized stock bar persistence writes."""
        return "stock_bar_events"

    def to_payload(self) -> dict[str, object]:
        """Convert the event to an event-store payload mapping.

        Returns:
            Dictionary with event fields suitable for insertion.

        Raises:
            None.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "ts": self.ts,
            "ingested_at": self.ingested_at,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "trade_count": self.trade_count,
            "vwap": self.vwap,
            "source": self.source,
        }


@dataclass(frozen=True)
class CryptoBarEvent:
    """Normalized crypto OHLCV bar ready for event-store persistence.

    Attributes mirror the `crypto_bar_events` schema. Crypto symbols keep the
    project's market-data spelling, which may differ from trading endpoints.
    """

    symbol: str
    timeframe: str
    ts: datetime
    ingested_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: float | None
    vwap: float | None
    source: str

    @property
    def table_name(self) -> str:
        """Return the event-store table used for normalized crypto bar persistence writes."""
        return "crypto_bar_events"

    def to_payload(self) -> dict[str, object]:
        """Convert the event to an event-store payload mapping.

        Returns:
            Dictionary with event fields suitable for insertion.

        Raises:
            None.
        """
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "ts": self.ts,
            "ingested_at": self.ingested_at,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "trade_count": self.trade_count,
            "vwap": self.vwap,
            "source": self.source,
        }


MarketDataEvent = StockBarEvent | CryptoBarEvent


class MarketDataSource(ABC):
    """Contract for polling or streaming normalized market-data events.

    Implementations should return `StockBarEvent` or `CryptoBarEvent` objects
    that can be persisted without additional provider-specific translation.
    """

    @abstractmethod
    def fetch(self) -> Sequence[MarketDataEvent]:
        """Return the latest market data events.

        Returns:
            Sequence of market data events.

        Raises:
            Exception: Implementations may raise on network or parsing errors.
        """

    async def stream(self) -> AsyncIterator[MarketDataEvent]:
        """Yield events asynchronously by adapting the synchronous fetch contract.

        Streaming providers can override this for live feeds; polling-only sources
        inherit a one-shot async iterator that yields the current `fetch()` result
        without changing persistence behavior in the ingestor.
        """
        for event in self.fetch():
            yield event


class NoOpMarketDataSource(MarketDataSource):
    """Market-data source for dry runs or disabled ingestion paths.

    It satisfies the source contract while deliberately producing no events.
    """

    def fetch(self) -> Sequence[MarketDataEvent]:
        """Return no events while satisfying the market-data source contract for disabled ingestion.

        Returns:
            Empty sequence.

        Raises:
            None.
        """
        return []


class StaticMarketDataSource(MarketDataSource):
    """Deterministic source that replays a fixed in-memory event sequence.

    Tests and examples use it to avoid network calls while exercising ingestion
    and cycle behavior with realistic event objects.
    """

    def __init__(self, events: Iterable[MarketDataEvent]) -> None:
        """Create a static source with predefined events.

        Args:
            events: Iterable of MarketDataEvent entries.

        Raises:
            None.
        """
        self._events = tuple(events)

    def fetch(self) -> Sequence[MarketDataEvent]:
        """Return the configured static events.

        Returns:
            Sequence of MarketDataEvent instances.

        Raises:
            None.
        """
        return list(self._events)


class MarketDataIngestor:
    """Fetches market-data events and writes them to the event store.

    The ingestor owns the persistence side effect for both polling and streaming
    paths: every yielded event is written to its declared table before being
    returned to the caller.
    """

    def __init__(self, event_store: EventStore, source: MarketDataSource) -> None:
        """Create an ingestor that persists events to the event store.

        Args:
            event_store: Event store to persist to.
            source: Market data source to fetch from.

        Raises:
            None.
        """
        self._event_store = event_store
        self._source = source

    def ingest(self) -> Sequence[MarketDataEvent]:
        """Fetch and persist market data events.

        Returns:
            Sequence of ingested events.

        Raises:
            Exception: Propagates source fetch or persistence errors.
        """
        events = self._source.fetch()
        for event in events:
            self._event_store.record_event(event.table_name, event.to_payload())
            logger.info(
                "Market data ingested symbol=%s ts=%s close=%s volume=%s source=%s",
                event.symbol,
                event.ts.isoformat(),
                event.close,
                event.volume,
                event.source,
            )
        logger.info("Market data ingestion complete count=%s", len(events))
        return events

    async def ingest_stream(self) -> AsyncIterator[MarketDataEvent]:
        """Persist streamed events before forwarding each event to downstream callers.

        The ingestor writes every event to the table named by the event, logs a
        stable symbol/timestamp/source record, yields the event only after the
        write succeeds, and logs a final count when the stream ends.
        """
        count = 0
        async for event in self._source.stream():
            self._event_store.record_event(event.table_name, event.to_payload())
            logger.info(
                "Market data ingested symbol=%s ts=%s close=%s volume=%s source=%s",
                event.symbol,
                event.ts.isoformat(),
                event.close,
                event.volume,
                event.source,
            )
            count += 1
            yield event
        logger.info("Market data ingestion complete count=%s", count)
