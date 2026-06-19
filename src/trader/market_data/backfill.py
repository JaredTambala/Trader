"""Historical market data backfill using Alpaca REST APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import calendar
import logging
import re
from typing import Mapping, Sequence

from alpaca.data.enums import DataFeed
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from ..config import Config
from ..event_store import EventStore, PostgresEventStore, build_event_store
from ..notifications import notify_market_data
from ..timeframes import parse_timeframe
from .domain import CryptoBarEvent, StockBarEvent


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


def _normalize_bars(bars: object) -> Sequence[object]:
    """Normalize bar collections into a sequence."""
    if isinstance(bars, Sequence) and not isinstance(bars, (str, bytes)):
        return bars
    return [bars]


def _build_bar_event(
    asset_class: str,
    symbol: str,
    bar: object,
    ingested_at: datetime,
    source: str,
    timeframe: str | None = None,
) -> StockBarEvent | CryptoBarEvent | None:
    """Convert a bar payload into an event."""
    ts_value = _bar_value(bar, "t", ("t", "timestamp", "time"))
    open_value = _bar_value(bar, "o", ("o", "open"))
    high_value = _bar_value(bar, "h", ("h", "high"))
    low_value = _bar_value(bar, "l", ("l", "low"))
    close_value = _bar_value(bar, "c", ("c", "close", "price"))
    volume_value = _bar_value(bar, "v", ("v", "volume"))
    if None in (ts_value, open_value, high_value, low_value, close_value, volume_value):
        return None

    trade_count = _optional_float(_bar_value(bar, "n", ("n", "trade_count")))
    vwap = _optional_float(_bar_value(bar, "vw", ("vw", "vwap")))
    common = dict(
        symbol=str(symbol),
        ts=_coerce_timestamp(ts_value),
        ingested_at=ingested_at,
        open=float(open_value),
        high=float(high_value),
        low=float(low_value),
        close=float(close_value),
        volume=float(volume_value),
        trade_count=trade_count,
        vwap=vwap,
        source=source,
    )
    if asset_class.lower() in {"crypto", "cryptocurrency"}:
        if not timeframe:
            raise ValueError("timeframe is required for crypto bars")
        return CryptoBarEvent(timeframe=timeframe, **common)
    if not timeframe:
        raise ValueError("timeframe is required for stock bars")
    return StockBarEvent(timeframe=timeframe, **common)


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


def _bar_value(bar: object, attr: str, keys: tuple[str, ...]) -> object | None:
    """Extract a value from bar objects or mappings."""
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
    """Convert Alpaca timestamp values into UTC datetimes."""
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
    """Convert numeric values to float when present."""
    if value is None:
        return None
    return float(value)


def _normalize_stock_feed(feed: str | None) -> DataFeed:
    """Normalize stock feed configuration for Alpaca requests."""
    if not feed:
        return DataFeed.IEX
    feed_value = feed.strip().lower()
    if feed_value == "sip":
        return DataFeed.SIP
    return DataFeed.IEX


def _parse_timeframe(value: str) -> TimeFrame:
    """Parse Alpaca timeframe strings like 5Min, 15T, 1Hour, 1Day, 1Week, 3Month."""
    return parse_timeframe(value)


def _parse_symbols_value(value: object | None) -> list[str] | None:
    """Parse optional backfill symbols from a comma string or sequence."""
    if value is None:
        return None
    if isinstance(value, str):
        symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
        return symbols or None
    if isinstance(value, (list, tuple)):
        symbols = [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
        return symbols or None
    raise ValueError("backfill.symbols must be a string or list")


def _parse_datetime(value: str) -> datetime:
    """Parse ISO datetime config values, accepting a trailing `Z` UTC suffix."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _resolve_window_from_config(backfill: Mapping[str, object], now: datetime) -> tuple[datetime, datetime]:
    """Resolve the backfill window from YAML configuration."""
    start_value = backfill.get("start")
    end_value = backfill.get("end")
    if start_value or end_value:
        if not start_value:
            raise ValueError("backfill.start is required when backfill.end is provided")
        start = _parse_datetime(str(start_value))
        end = _parse_datetime(str(end_value)) if end_value else now
        return start, end
    since = str(backfill.get("since", "60m"))
    return _resolve_since(since, now)


def _resolve_since(value: str, now: datetime) -> tuple[datetime, datetime]:
    """Resolve a single since duration string into a time window.

    Args:
        value: Duration string (e.g. 90m, 6h, 14d, 6mo).
        now: End timestamp for the window.

    Returns:
        Tuple of (start, end) timestamps.

    Raises:
        ValueError: If the duration string is invalid.
    """
    raw = value.strip().lower()
    match = re.match(r"^(\d+)\s*([a-z]+)$", raw)
    if not match:
        raise ValueError(f"Invalid since value: {value}")
    amount = int(match.group(1))
    unit = match.group(2)
    if amount <= 0:
        raise ValueError("since must be positive")
    if unit in {"m", "min", "mins", "minute", "minutes"}:
        return now - timedelta(minutes=amount), now
    if unit in {"h", "hr", "hrs", "hour", "hours"}:
        return now - timedelta(hours=amount), now
    if unit in {"d", "day", "days"}:
        return now - timedelta(days=amount), now
    if unit in {"mo", "mon", "month", "months"}:
        return _subtract_months(now, amount), now
    raise ValueError(f"Invalid since unit: {unit}")


def _subtract_months(value: datetime, months: int) -> datetime:
    """Subtract calendar months from a datetime, clamping to month end.

    Args:
        value: Reference datetime.
        months: Number of months to subtract.

    Returns:
        Adjusted datetime with the same time and tzinfo.
    """
    if months <= 0:
        raise ValueError("months must be positive")
    total_months = value.year * 12 + (value.month - 1) - months
    year = total_months // 12
    month = total_months % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(value.day, last_day)
    return value.replace(year=year, month=month, day=day)


if __name__ == "__main__":
    raise SystemExit(
        "trader.market_data.backfill is a library module. "
        "Use run_market_data_backfill.py (external entrypoint) to start backfills."
    )
