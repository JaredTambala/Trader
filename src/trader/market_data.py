"""Market data ingestion sources and helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Iterable, Sequence

from .data import EventStore


logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class StockBarEvent:
    """Bar event for stock market data."""

    symbol: str
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
        return "stock_bar_events"

    def to_payload(self) -> dict[str, object]:
        """Convert the event to a DuckDB payload mapping.

        Returns:
            Dictionary with event fields suitable for insertion.

        Raises:
            None.
        """
        return {
            "symbol": self.symbol,
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
    """Bar event for crypto market data."""

    symbol: str
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
        return "crypto_bar_events"

    def to_payload(self) -> dict[str, object]:
        """Convert the event to a DuckDB payload mapping.

        Returns:
            Dictionary with event fields suitable for insertion.

        Raises:
            None.
        """
        return {
            "symbol": self.symbol,
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
    """Fetches market data events from an upstream source."""

    @abstractmethod
    def fetch(self) -> Sequence[MarketDataEvent]:
        """Return the latest market data events.

        Returns:
            Sequence of market data events.

        Raises:
            Exception: Implementations may raise on network or parsing errors.
        """


class NoOpMarketDataSource(MarketDataSource):
    """Market data source that returns no events."""

    def fetch(self) -> Sequence[MarketDataEvent]:
        """Return an empty event list.

        Returns:
            Empty sequence.

        Raises:
            None.
        """
        return []


class StaticMarketDataSource(MarketDataSource):
    """Market data source for tests and local runs."""

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
    """Persists market data events from an upstream source."""

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
