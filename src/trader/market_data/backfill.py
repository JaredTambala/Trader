"""Historical market data backfill using Alpaca REST APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Mapping, Sequence

from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from ..config import Config
from ..event_store import EventStore, PostgresEventStore, build_event_store
from ..runtime.notifications import notify_market_data
from .domain import CryptoBarEvent, StockBarEvent
from .backfill_payloads import (
    _bar_value as _bar_value,
    _build_bar_event as _build_bar_event,
    _coerce_timestamp as _coerce_timestamp,
    _normalize_bars as _normalize_bars,
    _normalize_stock_feed as _normalize_stock_feed,
    _optional_float as _optional_float,
    _parse_datetime as _parse_datetime,
    _parse_symbols_value as _parse_symbols_value,
    _parse_timeframe as _parse_timeframe,
    _resolve_since as _resolve_since,
    _resolve_window_from_config as _resolve_window_from_config,
    _subtract_months as _subtract_months,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackfillSpec:
    """Bounded historical bar request for market-data backfill.

    Attributes:
        start: Inclusive UTC start timestamp requested from Alpaca.
        end: Inclusive UTC end timestamp requested from Alpaca.
        timeframe: Alpaca timeframe used for returned bars and persisted labels.
        limit: Optional provider result limit; `None` fetches all available bars
            in the requested window.
    """

    start: datetime
    end: datetime
    timeframe: TimeFrame
    limit: int | None


class MarketDataBackfillRunner:
    """Run a historical backfill and persist Alpaca bars to the event store."""

    def __init__(
        self,
        config: Config,
        spec: BackfillSpec,
        symbols: Sequence[str] | None = None,
        asset_class: str | None = None,
        event_store: EventStore | None = None,
        notify_channel: str | None = None,
    ) -> None:
        """Resolve backfill dependencies, symbol scope, asset class, and notification settings.

        Args:
            config: Loaded configuration values.
            spec: Backfill window/timeframe configuration.
            symbols: Optional symbol override.
            asset_class: Optional asset class override.
            event_store: Optional event store override.
            notify_channel: Optional Postgres notify channel override.

        Raises:
            ValueError: If the asset class is unsupported.
        """
        self._config = config
        self._spec = spec
        self._asset_class = (asset_class or config.market_data_asset_class).lower()
        self._symbols = list(symbols) if symbols else list(config.market_data_symbols)
        self._event_store = event_store or build_event_store(config)
        self._owns_event_store = event_store is None
        self._client = _build_client(self._asset_class, config)
        self._notify_channel = notify_channel

    def run(self) -> int:
        """Execute the backfill and persist bars.

        Returns:
            Count of bars persisted.

        Raises:
            ValueError: If configuration is incomplete.
        """
        if not self._symbols:
            logger.warning("MARKET_DATA_SYMBOLS is empty; nothing to backfill")
            if self._owns_event_store:
                self._event_store.close()
            return 0
        logger.info(
            "Backfill start asset_class=%s symbols=%s timeframe=%s start=%s end=%s",
            self._asset_class,
            ",".join(self._symbols),
            self._spec.timeframe,
            self._spec.start.isoformat(),
            self._spec.end.isoformat(),
        )
        if self._spec.limit is None:
            logger.info("Backfill running without a total limit; all pages will be fetched")
        else:
            logger.info("Backfill limit set total=%s", self._spec.limit)

        request = _build_request(
            self._asset_class,
            self._symbols,
            self._spec,
            self._config.market_data_stock_feed,
        )
        response = _fetch_bars(self._client, self._asset_class, request)
        data = _extract_bar_data(response)
        ingested_at = datetime.now(timezone.utc)

        count = 0
        events_by_table: dict[str, list[StockBarEvent | CryptoBarEvent]] = {}
        for symbol, bars in data.items():
            symbol_count = 0
            for bar in _normalize_bars(bars):
                event = _build_bar_event(
                    self._asset_class,
                    symbol,
                    bar,
                    ingested_at,
                    source="alpaca",
                    timeframe=str(self._spec.timeframe),
                )
                if event is None:
                    continue
                events_by_table.setdefault(event.table_name, []).append(event)
                count += 1
                symbol_count += 1
            logger.info("Backfill staged symbol=%s count=%s", symbol, symbol_count)

        with self._event_store.transaction():
            if isinstance(self._event_store, PostgresEventStore):
                connection = self._event_store.connection()
                for table_name, events in events_by_table.items():
                    logger.info("Backfill upsert table=%s count=%s", table_name, len(events))
                    _upsert_events_postgres(connection, table_name, events)
            else:
                for events in events_by_table.values():
                    for event in events:
                        self._event_store.record_event(event.table_name, event.to_payload())

        self._notify_backfill(events_by_table)

        if self._owns_event_store:
            self._event_store.close()

        logger.info(
            "Backfill complete count=%s start=%s end=%s timeframe=%s",
            count,
            self._spec.start.isoformat(),
            self._spec.end.isoformat(),
            self._spec.timeframe,
        )
        return count

    def _notify_backfill(
        self,
        events_by_table: Mapping[str, Sequence[StockBarEvent | CryptoBarEvent]],
    ) -> None:
        """Send a notification for the latest bar per symbol."""
        latest_by_symbol: dict[str, datetime] = {}
        for events in events_by_table.values():
            for event in events:
                current = latest_by_symbol.get(event.symbol)
                if current is None or event.ts > current:
                    latest_by_symbol[event.symbol] = event.ts

        if not latest_by_symbol:
            return

        notified_count = 0
        for symbol, ts in latest_by_symbol.items():
            if notify_market_data(
                self._event_store,
                {
                    "symbol": symbol,
                "timeframe": str(self._spec.timeframe),
                "ts": ts.isoformat(),
                "asset_class": self._asset_class,
                "source": "backfill",
            },
            channel=self._notify_channel,
        ):
                notified_count += 1
        if notified_count:
            logger.debug("Backfill notifications sent count=%s", notified_count)


def _build_client(asset_class: str, config: Config) -> object:
    """Construct the Alpaca historical data client."""
    asset_class = asset_class.lower()
    if asset_class in {"crypto", "cryptocurrency"}:
        return CryptoHistoricalDataClient(url_override=config.alpaca_data_base_url)
    if asset_class in {"stocks", "stock"}:
        if not config.alpaca_api_key or not config.alpaca_secret_key:
            raise ValueError("Alpaca API key and secret are required for stock backfill")
        return StockHistoricalDataClient(
            config.alpaca_api_key,
            config.alpaca_secret_key,
            url_override=config.alpaca_data_base_url,
        )
    raise ValueError(f"Unsupported asset class: {asset_class}")


def _build_request(
    asset_class: str,
    symbols: Sequence[str],
    spec: BackfillSpec,
    stock_feed: str,
) -> object:
    """Build the Alpaca bars request."""
    asset_class = asset_class.lower()
    if asset_class in {"crypto", "cryptocurrency"}:
        return CryptoBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=spec.timeframe,
            start=spec.start,
            end=spec.end,
            limit=spec.limit,
        )
    feed = _normalize_stock_feed(stock_feed)
    return StockBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=spec.timeframe,
        start=spec.start,
        end=spec.end,
        limit=spec.limit,
        feed=feed,
    )


def _fetch_bars(client: object, asset_class: str, request: object) -> object:
    """Fetch historical bars from Alpaca."""
    asset_class = asset_class.lower()
    if asset_class in {"crypto", "cryptocurrency"}:
        return client.get_crypto_bars(request)
    return client.get_stock_bars(request)


def _extract_bar_data(response: object) -> Mapping[str, Sequence[object]]:
    """Normalize Alpaca responses into a symbol-to-bars mapping."""
    if hasattr(response, "data"):
        return response.data
    if isinstance(response, Mapping):
        return response
    return {}


def _upsert_events_postgres(
    connection: object,
    table_name: str,
    events: Sequence[StockBarEvent | CryptoBarEvent],
) -> None:
    """Insert events into Postgres with ON CONFLICT DO NOTHING."""
    if not events:
        return
    payloads = [event.to_payload() for event in events]
    columns = list(payloads[0].keys())
    from psycopg import sql

    query = sql.SQL(
        "INSERT INTO {table} ({fields}) VALUES ({values}) "
        "ON CONFLICT (symbol, timeframe, ts, source) DO NOTHING"
    ).format(
        table=sql.Identifier(table_name),
        fields=sql.SQL(", ").join(sql.Identifier(col) for col in columns),
        values=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    with connection.cursor() as cursor:
        cursor.executemany(query, [list(payload.values()) for payload in payloads])


if __name__ == "__main__":
    raise SystemExit(
        "trader.market_data.backfill is a library module. "
        "Use run_market_data_backfill.py (external entrypoint) to start backfills."
    )
