"""Historical market data backfill using Alpaca REST APIs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import calendar
import logging
import re
import uuid
from typing import Mapping, Sequence

from alpaca.data.enums import DataFeed
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv

from .config import Config, load_config
from .data import DuckDBEventStore, EventStore
from .market_data import CryptoBarEvent, StockBarEvent


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackfillSpec:
    """Configuration for a historical backfill run."""

    start: datetime
    end: datetime
    timeframe: TimeFrame
    limit: int | None


class MarketDataBackfillRunner:
    """Run a historical backfill and persist Alpaca bars to DuckDB."""

    def __init__(
        self,
        config: Config,
        spec: BackfillSpec,
        symbols: Sequence[str] | None = None,
        asset_class: str | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        """Initialize the backfill runner.

        Args:
            config: Loaded configuration values.
            spec: Backfill window/timeframe configuration.
            symbols: Optional symbol override.
            asset_class: Optional asset class override.
            event_store: Optional event store override.

        Raises:
            ValueError: If the asset class is unsupported.
        """
        self._config = config
        self._spec = spec
        self._asset_class = (asset_class or config.market_data_asset_class).lower()
        self._symbols = list(symbols) if symbols else list(config.market_data_symbols)
        self._event_store = event_store or DuckDBEventStore(config.db_path)
        self._owns_event_store = event_store is None
        self._client = _build_client(self._asset_class, config)

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
            if isinstance(self._event_store, DuckDBEventStore):
                connection = self._event_store.connection()
                for table_name, events in events_by_table.items():
                    _merge_events(connection, table_name, events)
            else:
                for events in events_by_table.values():
                    for event in events:
                        self._event_store.record_event(event.table_name, event.to_payload())

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


def _merge_events(
    connection: object,
    table_name: str,
    events: Sequence[StockBarEvent | CryptoBarEvent],
) -> None:
    """Merge staged events into the target table with deduplication.

    Args:
        connection: DuckDB connection.
        table_name: Destination table.
        events: Events to merge.

    Raises:
        Exception: Propagates DuckDB execution errors.
    """
    if not events:
        return
    payloads = [event.to_payload() for event in events]
    columns = list(payloads[0].keys())
    staging_table = f"staging_{table_name}_{uuid.uuid4().hex}"
    connection.execute(
        f"CREATE TEMP TABLE {staging_table} AS SELECT {', '.join(columns)} FROM {table_name} WHERE 1=0"
    )
    placeholders = ", ".join(["?"] * len(columns))
    connection.executemany(
        f"INSERT INTO {staging_table} ({', '.join(columns)}) VALUES ({placeholders})",
        [list(payload.values()) for payload in payloads],
    )
    insert_columns = ", ".join(columns)
    source_columns = ", ".join([f"source.{col}" for col in columns])
    connection.execute(
        f"""
        MERGE INTO {table_name} AS target
        USING {staging_table} AS source
        ON target.symbol = source.symbol
            AND target.timeframe = source.timeframe
            AND target.ts = source.ts
            AND target.source = source.source
        WHEN NOT MATCHED THEN
            INSERT ({insert_columns}) VALUES ({source_columns})
        """
    )
    connection.execute(f"DROP TABLE {staging_table}")


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
    match = re.match(r"^(\d+)\s*([a-zA-Z]+)$", value.strip())
    if not match:
        raise ValueError(f"Invalid timeframe: {value}")
    amount = int(match.group(1))
    unit_raw = match.group(2).lower()
    if amount <= 0:
        raise ValueError(f"Invalid timeframe amount: {amount}")
    if unit_raw in {"min", "mins", "minute", "minutes", "t"}:
        if amount > 59:
            raise ValueError("Minute timeframe must be 1-59")
        unit = TimeFrameUnit.Minute
    elif unit_raw in {"hour", "hours", "hr", "h"}:
        if amount > 23:
            raise ValueError("Hour timeframe must be 1-23")
        unit = TimeFrameUnit.Hour
    elif unit_raw in {"day", "days", "d"}:
        if amount != 1:
            raise ValueError("Day timeframe must be 1Day or 1D")
        unit = TimeFrameUnit.Day
    elif unit_raw in {"week", "weeks", "w"}:
        if amount != 1:
            raise ValueError("Week timeframe must be 1Week or 1W")
        unit = TimeFrameUnit.Week
    elif unit_raw in {"month", "months", "m"}:
        if amount not in {1, 2, 3, 4, 6, 12}:
            raise ValueError("Month timeframe must be 1,2,3,4,6,12")
        unit = TimeFrameUnit.Month
    else:
        raise ValueError(f"Invalid timeframe unit: {unit_raw}")
    return TimeFrame(amount=amount, unit=unit)


def _parse_symbols_arg(value: str) -> list[str]:
    """Parse a comma-delimited symbol list for CLI overrides."""
    symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
    return symbols


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for a backfill run."""
    parser = argparse.ArgumentParser(description="Backfill Alpaca market data bars.")
    parser.add_argument(
        "--symbols",
        help="Comma-separated symbols to backfill (overrides MARKET_DATA_SYMBOLS).",
    )
    parser.add_argument(
        "--asset-class",
        choices=["stocks", "stock", "crypto", "cryptocurrency"],
        help="Asset class override (stocks or crypto).",
    )
    parser.add_argument(
        "--timeframe",
        default="1Min",
        help="Bar timeframe (e.g. 5Min, 15T, 1Hour, 1Day, 1Week, 3Month).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional total cap on returned bars; omit to fetch all pages.",
    )
    parser.add_argument(
        "--since",
        default="60m",
        help="Backfill window (e.g. 90m, 6h, 14d, 6mo).",
    )
    return parser.parse_args()


def _resolve_window(args: argparse.Namespace, now: datetime) -> tuple[datetime, datetime]:
    """Resolve the backfill window from CLI arguments.

    Args:
        args: Parsed CLI arguments.
        now: End timestamp for the window.

    Returns:
        Tuple of (start, end) timestamps.

    Raises:
        ValueError: If provided values are invalid.
    """
    return _resolve_since(args.since, now)


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


def main() -> None:
    """Module entry point for running a historical backfill."""
    load_dotenv(".env")
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    config = load_config()

    end = datetime.now(timezone.utc)
    start, end = _resolve_window(args, end)
    spec = BackfillSpec(
        start=start,
        end=end,
        timeframe=_parse_timeframe(args.timeframe),
        limit=args.limit,
    )
    symbols = _parse_symbols_arg(args.symbols) if args.symbols else None
    runner = MarketDataBackfillRunner(
        config,
        spec,
        symbols=symbols,
        asset_class=args.asset_class,
    )
    runner.run()


if __name__ == "__main__":
    main()
