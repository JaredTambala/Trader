"""Single execution cycle entry point."""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import uuid
from typing import AsyncIterator, Mapping, Sequence

from dotenv import load_dotenv
from .broker import Broker, InternalPaperBroker, NoOpBroker
from .config import Config, build_config, load_yaml_config, resolve_log_level
from .data import EventStore, FilteredEventStore, build_event_store
from .identifiers import (
    deterministic_client_order_id,
    deterministic_cycle_id,
    deterministic_run_session_id,
)
from .alpaca_market_data import AlpacaMarketDataSource
from .market_data import (
    MarketDataEvent,
    MarketDataIngestor,
    MarketDataSource,
    NoOpMarketDataSource,
    CryptoBarEvent,
    StockBarEvent,
)
from .portfolio import Portfolio
from .signal_generators import SimpleBarsSignalGenerator
from .signals import SmaCrossoverSignal
from .indicators import SmaIndicator
from .strategies import NoOpStrategy, SimpleStrategy, Strategy


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CycleResult:
    run_id: str
    cycle_id: str
    status: str


def run_cycle(
    event_store: EventStore | None = None,
    strategy: Strategy | None = None,
    broker: Broker | None = None,
    config: Config | None = None,
    config_snapshot: Mapping[str, object] | None = None,
    decision_ts: datetime | None = None,
    market_data_source: MarketDataSource | None = None,
    portfolio: Portfolio | None = None,
    ingest_market_data: bool = True,
    run_id: str | None = None,
    run_type: str | None = None,
) -> CycleResult:
    """Execute a cycle and record run events.

    Args:
        event_store: Optional event store; defaults to the configured backend.
        strategy: Strategy used to generate signals.
        risk_manager: Risk manager applied to candidate orders.
        broker: Broker used to submit orders.
        config: Configuration for the cycle.
        config_snapshot: Optional YAML configuration snapshot for run auditing.
        decision_ts: Optional decision timestamp for deterministic run IDs.
        market_data_source: Optional market data source override.
        portfolio: Optional in-memory portfolio override.
        ingest_market_data: Whether to persist fetched market data events.
        run_id: Optional run session identifier (backtest or trading).
        run_type: Optional run type override (backtest/trading).

    Returns:
        CycleResult describing the run outcome.

    Raises:
        Exception: Propagates any unexpected errors after recording a failed run.
    """
    if config is None:
        raise ValueError("config is required; load it from YAML and pass it in")
    logger.info(
        "Cycle start mode=%s strategy_type=%s strategy_id=%s event_store=%s market_data_source=%s asset_class=%s symbols=%s timeframe=%s",
        config.mode,
        config.strategy_type,
        config.strategy_id,
        config.event_store,
        config.market_data_source,
        config.market_data_asset_class,
        ",".join(config.market_data_symbols) if config.market_data_symbols else "<none>",
        config.strategy_timeframe,
    )
    broker = broker or _build_broker(config, event_store)

    owns_event_store = False
    if event_store is None:
        event_store = build_event_store(config)
        owns_event_store = True
        logger.info("Event store initialized backend=%s", config.event_store.lower())

    decision_ts = decision_ts or datetime.now(timezone.utc)
    if decision_ts.tzinfo is None:
        decision_ts = decision_ts.replace(tzinfo=timezone.utc)

    event_store = _apply_event_filters(event_store, config)
    event_store.flush()
    if portfolio is None:
        portfolio_asof = decision_ts if config.mode.lower() == "backtest" else None
        portfolio = Portfolio.from_event_store(event_store, asof_ts=portfolio_asof)
        logger.info("Portfolio loaded positions=%s", len(portfolio.positions))
    else:
        logger.info("Portfolio override positions=%s", len(portfolio.positions))
    strategy = strategy or _build_strategy(config, event_store)

    if market_data_source is None:
        market_data_source = _build_market_data_source(config)

    run_type = (run_type or ("backtest" if config.mode.lower() == "backtest" else "trading")).lower()
    cycle_id = deterministic_cycle_id(config.strategy_id, decision_ts)
    started_at = datetime.now(timezone.utc)
    owns_run_session = False
    run_session_status = "success"
    run_session_error: str | None = None
    if run_id is None:
        run_id = deterministic_run_session_id(run_type, started_at)
        event_store.record_run_session_start(
            run_id=run_id,
            run_type=run_type,
            started_at=started_at,
            config_snapshot=config_snapshot,
            mode=config.mode,
            symbols=config.market_data_symbols,
            timeframe=config.strategy_timeframe,
        )
        owns_run_session = True

    try:
        event_store.record_cycle_start(
            run_id=run_id,
            cycle_id=cycle_id,
            strategy_id=config.strategy_id,
            mode=config.mode,
            decision_ts=decision_ts,
            started_at=started_at,
        )
        stream_mode = config.mode.lower() != "backtest"
        processed_orders: Sequence[Mapping[str, object]] = []
        price_lookup: Mapping[str, float] = {}
        if ingest_market_data and stream_mode:
            event_counter = {"count": 0}
            processed_orders, price_lookup = asyncio.run(
                _process_market_stream_async(
                    event_store=event_store,
                    strategy=strategy,
                    broker=broker,
                    portfolio=portfolio,
                    run_id=run_id,
                    cycle_id=cycle_id,
                    event_stream=_event_stream_with_count(
                        MarketDataIngestor(event_store, market_data_source).ingest_stream(),
                        event_counter,
                    ),
                    max_age_seconds=config.market_data_max_age_seconds,
                    enforce_staleness=True,
                )
            )
            if event_counter["count"] == 0:
                market_data_events = _load_recent_market_data(event_store, config, decision_ts)
                freshness_ts = decision_ts if config.mode.lower() == "backtest" else datetime.now(timezone.utc)
                should_skip = _should_skip_trading(
                    market_data_events,
                    freshness_ts,
                    config.market_data_max_age_seconds,
                )
                if should_skip:
                    logger.warning("Skipping trading due to missing or stale market data")
                else:
                    processed_orders, price_lookup = asyncio.run(
                        _process_market_stream_async(
                            event_store=event_store,
                            strategy=strategy,
                            broker=broker,
                            portfolio=portfolio,
                            run_id=run_id,
                            cycle_id=cycle_id,
                            event_stream=_event_stream_from_list(market_data_events),
                            max_age_seconds=config.market_data_max_age_seconds,
                            enforce_staleness=False,
                        )
                    )
        else:
            if ingest_market_data:
                with event_store.transaction():
                    market_data_events = MarketDataIngestor(event_store, market_data_source).ingest()
            else:
                market_data_events = market_data_source.fetch()
                logger.info("Market data fetched without ingest count=%s", len(market_data_events))
            if not market_data_events:
                market_data_events = _load_recent_market_data(event_store, config, decision_ts)
            freshness_ts = decision_ts if config.mode.lower() == "backtest" else datetime.now(timezone.utc)
            should_skip = _should_skip_trading(
                market_data_events,
                freshness_ts,
                config.market_data_max_age_seconds,
            )

            if should_skip:
                logger.warning("Skipping trading due to missing or stale market data")
            else:
                processed_orders, price_lookup = asyncio.run(
                    _process_market_stream_async(
                        event_store=event_store,
                        strategy=strategy,
                        broker=broker,
                        portfolio=portfolio,
                        run_id=run_id,
                        cycle_id=cycle_id,
                        event_stream=_event_stream_from_list(market_data_events),
                        max_age_seconds=config.market_data_max_age_seconds,
                        enforce_staleness=False,
                    )
                )

        if processed_orders:
            snapshot_ts = decision_ts if config.mode.lower() == "backtest" else datetime.now(timezone.utc)
            _record_portfolio_snapshot(
                event_store=event_store,
                portfolio=portfolio,
                orders=processed_orders,
                market_data_events=[],
                asof_ts=snapshot_ts,
                run_id=run_id,
                cycle_id=cycle_id,
                price_lookup=price_lookup,
            )

            finished_at = datetime.now(timezone.utc)
            event_store.record_cycle_finish(
                run_id=run_id,
                cycle_id=cycle_id,
                strategy_id=config.strategy_id,
                mode=config.mode,
                decision_ts=decision_ts,
                started_at=started_at,
                finished_at=finished_at,
                status="success",
                error_message=None,
            )
    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        event_store.record_cycle_finish(
            run_id=run_id,
            cycle_id=cycle_id,
            strategy_id=config.strategy_id,
            mode=config.mode,
            decision_ts=decision_ts,
            started_at=started_at,
            finished_at=finished_at,
            status="failed",
            error_message=str(exc),
        )
        run_session_status = "failed"
        run_session_error = str(exc)
        raise
    finally:
        if owns_run_session:
            event_store.record_run_session_finish(
                run_id=run_id,
                run_type=run_type,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                status=run_session_status,
                error_message=run_session_error,
                mode=config.mode,
                symbols=config.market_data_symbols,
                timeframe=config.strategy_timeframe,
            )
        if owns_event_store:
            event_store.close()

    logger.info("Completed cycle", extra={"run_id": run_id, "cycle_id": cycle_id})
    return CycleResult(run_id=run_id, cycle_id=cycle_id, status="success")


async def _event_stream_with_count(
    event_stream: AsyncIterator[MarketDataEvent],
    counter: dict[str, int],
) -> AsyncIterator[MarketDataEvent]:
    """Wrap an async event stream and count items as they flow through."""
    async for event in event_stream:
        counter["count"] = counter.get("count", 0) + 1
        yield event


def _build_market_data_source(config: Config) -> MarketDataSource:
    """Construct the market data source based on configuration.

    Args:
        config: Loaded configuration values.

    Returns:
        A MarketDataSource instance.

    Raises:
        None.
    """
    source_name = config.market_data_source.lower()
    if source_name in {"", "noop"}:
        return NoOpMarketDataSource()

    if source_name == "alpaca":
        if not config.market_data_symbols:
            logger.warning("MARKET_DATA_SYMBOLS is empty; skipping market data ingestion")
            return NoOpMarketDataSource()
        asset_class = config.market_data_asset_class.lower()
        if asset_class not in {"stocks", "stock", "crypto", "cryptocurrency"}:
            logger.warning("Unknown MARKET_DATA_ASSET_CLASS; skipping market data ingestion", extra={"asset_class": asset_class})
            return NoOpMarketDataSource()
        if asset_class in {"stocks", "stock"} and (not config.alpaca_api_key or not config.alpaca_secret_key):
            logger.warning("Alpaca credentials missing; skipping market data ingestion")
            return NoOpMarketDataSource()
        return AlpacaMarketDataSource(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            base_url=config.alpaca_data_base_url,
            symbols=config.market_data_symbols,
            asset_class=asset_class,
            stock_feed=config.market_data_stock_feed,
        )

    logger.warning("Unknown MARKET_DATA_SOURCE; skipping market data ingestion", extra={"source": source_name})
    return NoOpMarketDataSource()


def _build_broker(config: Config, event_store: EventStore) -> Broker:
    """Build broker."""
    broker_type = (getattr(config, "broker_type", "noop") or "noop").lower()
    if broker_type in {"internal", "paper", "sim"}:
        return InternalPaperBroker()
    return NoOpBroker()


def _build_price_lookup(events: Sequence[MarketDataEvent]) -> Mapping[str, float]:
    """Build a price lookup map from market data events."""
    latest_prices: dict[str, tuple[datetime, float]] = {}
    for event in events:
        timestamp = _normalize_timestamp(event.ts)
        current = latest_prices.get(event.symbol)
        if current is None or timestamp > current[0]:
            latest_prices[event.symbol] = (timestamp, float(event.close))
    return {symbol: price for symbol, (_, price) in latest_prices.items()}


def _attach_order_metadata(
    orders: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    cycle_id: str,
    price_lookup: Mapping[str, float],
) -> Sequence[Mapping[str, object]]:
    """Attach run metadata to order payloads."""
    timestamp = datetime.now(timezone.utc)
    enriched: list[Mapping[str, object]] = []
    for order in orders:
        symbol = str(order.get("symbol", "")).strip().upper()
        side = str(order.get("side", "")).lower().strip()
        qty = float(order.get("qty", 0.0) or 0.0)
        price = price_lookup.get(symbol)
        client_order_id = order.get("client_order_id") or deterministic_client_order_id(
            cycle_id,
            symbol,
            side,
            qty,
        )
        enriched.append(
            {
                **order,
                "symbol": symbol,
                "run_id": run_id,
                "cycle_id": cycle_id,
                "client_order_id": client_order_id,
                "price": price,
                "created_at": order.get("created_at") or timestamp,
            }
        )
    return enriched


def _record_order_events(
    event_store: EventStore,
    orders: Sequence[Mapping[str, object]],
    *,
    status: str,
    broker_order_id: str | None = None,
    event_ts: datetime | None = None,
) -> None:
    """Persist order lifecycle events for candidate orders."""
    timestamp = event_ts or datetime.now(timezone.utc)
    for order in orders:
        event_store.record_event(
            "order_events",
            {
                "order_event_id": f"order_evt_{uuid.uuid4().hex}",
                "client_order_id": order.get("client_order_id"),
                "run_id": order.get("run_id"),
                "cycle_id": order.get("cycle_id"),
                "symbol": order.get("symbol"),
                "side": order.get("side"),
                "qty": order.get("qty"),
                "order_type": order.get("order_type", "market"),
                "status": status,
                "broker_order_id": broker_order_id,
                "rejection_reason": order.get("rejection_reason"),
                "created_at": timestamp,
            },
        )


def _record_broker_responses(
    event_store: EventStore,
    orders: Sequence[Mapping[str, object]],
    responses: Sequence[Mapping[str, object]],
) -> None:
    """Persist broker responses and fill events."""
    if not responses:
        return
    order_lookup = {order.get("client_order_id"): order for order in orders}
    for response in responses:
        client_order_id = response.get("client_order_id")
        order = order_lookup.get(client_order_id)
        if order is None:
            logger.warning("Broker response missing order mapping client_order_id=%s", client_order_id)
            continue
        status = str(response.get("status", "submitted"))
        broker_order_id = response.get("broker_order_id")
        _record_order_events(
            event_store,
            [order],
            status=status,
            broker_order_id=broker_order_id,
            event_ts=response.get("fill_ts") or datetime.now(timezone.utc),
        )
        if status == "filled":
            fill_qty = response.get("fill_qty", order.get("qty"))
            fill_price = response.get("fill_price", order.get("price"))
            if fill_qty is None or fill_price is None:
                logger.warning(
                    "Fill event missing price/qty client_order_id=%s",
                    client_order_id,
                )
                continue
            event_store.record_event(
                "fill_events",
                {
                    "client_order_id": client_order_id,
                    "run_id": order.get("run_id"),
                    "cycle_id": order.get("cycle_id"),
                    "fill_ts": response.get("fill_ts") or datetime.now(timezone.utc),
                    "fill_qty": float(fill_qty),
                    "fill_price": float(fill_price),
                },
            )


async def _process_market_stream_async(
    *,
    event_store: EventStore,
    strategy: Strategy,
    broker: Broker,
    portfolio: Portfolio,
    run_id: str,
    cycle_id: str,
    event_stream: AsyncIterator[MarketDataEvent],
    max_age_seconds: int,
    enforce_staleness: bool,
) -> tuple[Sequence[Mapping[str, object]], Mapping[str, float]]:
    """Process market data events through the async pipeline."""
    event_queue: asyncio.Queue[MarketDataEvent | None] = asyncio.Queue()
    order_queue: asyncio.Queue[Mapping[str, object] | None] = asyncio.Queue()
    validated_queue: asyncio.Queue[Mapping[str, object] | None] = asyncio.Queue()
    processed: list[Mapping[str, object]] = []
    latest_prices: dict[str, tuple[datetime, float]] = {}

    async def producer() -> None:
        """Handle producer."""
        async for event in event_stream:
            await event_queue.put(event)
        await event_queue.put(None)

    async def signal_worker() -> None:
        """Handle signal worker."""
        while True:
            event = await event_queue.get()
            if event is None:
                await order_queue.put(None)
                break
            now = datetime.now(timezone.utc)
            if enforce_staleness and _is_event_stale(event, now, max_age_seconds):
                logger.warning("Skipping stale market data symbol=%s ts=%s", event.symbol, event.ts.isoformat())
                continue
            symbol = event.symbol
            decision_ts = _normalize_timestamp(event.ts)
            latest_prices[symbol] = (decision_ts, float(event.close))
            async for order in strategy.order_stream_for_symbol(
                symbol,
                run_id=run_id,
                cycle_id=cycle_id,
                decision_ts=decision_ts,
                event_store=event_store,
                portfolio=portfolio,
            ):
                enriched = _attach_order_metadata(
                    [order],
                    run_id=run_id,
                    cycle_id=cycle_id,
                    price_lookup={symbol: float(event.close)},
                )[0]
                _record_order_events(event_store, [enriched], status="created")
                await order_queue.put(enriched)

    async def validator() -> None:
        """Handle validator."""
        risk_manager = strategy.get_risk_manager()
        while True:
            order = await order_queue.get()
            if order is None:
                await validated_queue.put(None)
                break
            approved, rejected = risk_manager.evaluate([order])
            _record_order_events(event_store, approved, status="validated")
            _record_order_events(event_store, rejected, status="rejected")
            if approved:
                await validated_queue.put(approved[0])

    async def submitter() -> None:
        """Handle submitter."""
        while True:
            order = await validated_queue.get()
            if order is None:
                break
            _record_order_events(event_store, [order], status="submitted")
            responses = await asyncio.to_thread(broker.submit_orders, [order])
            _record_broker_responses(event_store, [order], responses)
            processed.append(order)

    await asyncio.gather(producer(), signal_worker(), validator(), submitter())
    return processed, {symbol: price for symbol, (_, price) in latest_prices.items()}


async def _event_stream_from_list(events: Sequence[MarketDataEvent]) -> AsyncIterator[MarketDataEvent]:
    """Yield events from a list as an async stream."""
    for event in events:
        yield event


def _apply_event_filters(event_store: EventStore, config: Config) -> EventStore:
    """Apply event-store filters based on configuration flags."""
    allowed = {
        "runs",
        "run_events",
        "stock_bar_events",
        "crypto_bar_events",
        "config_kv",
    }
    if config.log_signal_events:
        allowed.add("signal_events")
    if config.log_indicator_events:
        allowed.add("indicator_events")
    if config.log_order_events:
        allowed.add("order_events")
    if config.log_fill_events:
        allowed.add("fill_events")
    if config.log_position_snapshots:
        allowed.add("position_snapshots")
    return FilteredEventStore(event_store, allowed_event_types=allowed)


def _should_skip_trading(
    market_data_events: Sequence[MarketDataEvent],
    now: datetime,
    max_age_seconds: int,
) -> bool:
    """Decide whether to skip trading based on market data freshness.

    Args:
        market_data_events: Events collected from ingestion.
        now: Current timestamp for staleness comparison.
        max_age_seconds: Maximum allowed staleness in seconds.

    Returns:
        True if trading should be skipped, otherwise False.

    Raises:
        ValueError: If max_age_seconds is negative.
    """
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    if not market_data_events:
        logger.warning("Skipping trading due to missing market data")
        return True

    latest_ts = max(_normalize_timestamp(event.ts) for event in market_data_events)
    age_seconds = (now - latest_ts).total_seconds()
    is_stale = age_seconds > max_age_seconds
    logger.info(
        "Market data freshness latest_ts=%s age_seconds=%.2f max_age_seconds=%s stale=%s",
        latest_ts.isoformat(),
        age_seconds,
        max_age_seconds,
        is_stale,
    )
    return is_stale


def _is_event_stale(event: MarketDataEvent, now: datetime, max_age_seconds: int) -> bool:
    """Return True if the event timestamp exceeds the max age."""
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    ts = _normalize_timestamp(event.ts)
    return (now - ts).total_seconds() > max_age_seconds


def _normalize_timestamp(timestamp: datetime) -> datetime:
    """Normalize timestamps to timezone-aware UTC.

    Args:
        timestamp: Input timestamp.

    Returns:
        UTC-aware datetime.

    Raises:
        None.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _load_recent_market_data(
    event_store: EventStore,
    config: Config,
    as_of_ts: datetime | None = None,
) -> Sequence[MarketDataEvent]:
    """Load the latest bar per symbol from the event store."""
    if not config.market_data_symbols:
        logger.warning("No symbols configured for market data lookup")
        return []

    asset_class = config.market_data_asset_class.lower()
    table = "crypto_bar_events" if asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
    timeframe = config.strategy_timeframe
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Market data lookup skipped; event store has no connection")
        return []

    if as_of_ts is not None:
        as_of_ts = _normalize_timestamp(as_of_ts)

    events: list[MarketDataEvent] = []
    if hasattr(connection, "cursor"):
        with connection.cursor() as cursor:
            for symbol in config.market_data_symbols:
                query = f"""
                        SELECT ts, ingested_at, open, high, low, close, volume, trade_count, vwap, source
                        FROM {table}
                        WHERE symbol = %s AND COALESCE(timeframe, '1Min') = %s
                        ORDER BY ts DESC
                        LIMIT 1
                    """
                params = [symbol.upper(), timeframe]
                if as_of_ts is not None:
                    query = f"""
                            SELECT ts, ingested_at, open, high, low, close, volume, trade_count, vwap, source
                            FROM {table}
                            WHERE symbol = %s AND COALESCE(timeframe, '1Min') = %s AND ts <= %s
                            ORDER BY ts DESC
                            LIMIT 1
                        """
                    params = [symbol.upper(), timeframe, as_of_ts]
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row is None:
                    continue
                events.append(_row_to_market_event(asset_class, symbol.upper(), timeframe, row))
    else:
        logger.warning("Market data lookup skipped; unsupported connection type")
    logger.info("Loaded recent market data from event store count=%s", len(events))
    return events


def _row_to_market_event(
    asset_class: str,
    symbol: str,
    timeframe: str,
    row: Sequence[object],
) -> MarketDataEvent:
    """Convert a row into a market data event."""
    common = dict(
        symbol=symbol,
        timeframe=timeframe,
        ts=row[0],
        ingested_at=row[1],
        open=float(row[2]),
        high=float(row[3]),
        low=float(row[4]),
        close=float(row[5]),
        volume=float(row[6]),
        trade_count=float(row[7]) if row[7] is not None else None,
        vwap=float(row[8]) if row[8] is not None else None,
        source=str(row[9]) if row[9] is not None else "event_store",
    )
    if asset_class in {"crypto", "cryptocurrency"}:
        return CryptoBarEvent(**common)
    return StockBarEvent(**common)


def _record_portfolio_snapshot(
    *,
    event_store: EventStore,
    portfolio: Portfolio,
    orders: Sequence[Mapping[str, object]],
    market_data_events: Sequence[MarketDataEvent],
    asof_ts: datetime,
    run_id: str,
    cycle_id: str | None,
    price_lookup: Mapping[str, float] | None = None,
) -> None:
    """Persist a portfolio snapshot based on executed order intents."""
    if not orders:
        logger.info("Portfolio snapshot skipped; no orders to apply")
        return

    price_lookup = price_lookup or _build_price_lookup(market_data_events)
    logger.debug("Portfolio pricing lookup symbols=%s", ",".join(price_lookup.keys()) or "<none>")

    portfolio.apply_orders(orders, price_lookup=price_lookup)
    snapshot = portfolio.snapshot(asof_ts=asof_ts, run_id=run_id, cycle_id=cycle_id)
    snapshot.persist(event_store)
    logger.info("Portfolio snapshot recorded count=%s", len(snapshot.positions))


def _log_startup_config(config: Config) -> None:
    """Log relevant configuration values for startup diagnostics."""
    masked = {
        "mode": config.mode,
        "strategy_type": config.strategy_type,
        "strategy_id": config.strategy_id,
        "strategy_timeframe": config.strategy_timeframe,
        "sma_short_window": config.sma_short_window,
        "sma_long_window": config.sma_long_window,
        "event_store": config.event_store,
        "market_data_source": config.market_data_source,
        "market_data_asset_class": config.market_data_asset_class,
        "market_data_stock_feed": config.market_data_stock_feed,
        "market_data_symbols": ",".join(config.market_data_symbols) or "<unset>",
        "market_data_max_age_seconds": config.market_data_max_age_seconds,
        "alpaca_api_key": _mask_secret(config.alpaca_api_key),
        "alpaca_secret_key": _mask_secret(config.alpaca_secret_key),
        "alpaca_data_base_url": config.alpaca_data_base_url,
        "pg_dsn": _mask_secret(config.pg_dsn),
        "pg_host": config.pg_host or "<unset>",
        "pg_port": config.pg_port,
        "pg_db": config.pg_db or "<unset>",
        "pg_user": config.pg_user or "<unset>",
        "pg_password": _mask_secret(config.pg_password),
    }
    formatted = ", ".join(f"{key}={value}" for key, value in masked.items())
    logger.info("Startup config: %s", formatted)


def _mask_secret(value: str | None) -> str:
    """Mask secret values for logging.

    Args:
        value: Secret string or None.

    Returns:
        Masked secret string.
    """
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}***{value[-4:]}"


def _configure_logging(level_name: str | None = None) -> None:
    """Configure logging from configuration defaults."""
    level_name = (level_name or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Logging configured level=%s", level_name)


def _build_strategy(config: Config, event_store: EventStore) -> Strategy:
    """Construct the configured strategy.

    Args:
        config: Loaded configuration values.
        event_store: Event store used by strategies that query data.

    Returns:
        Strategy instance.
    """
    strategy_type = (getattr(config, "strategy_type", "noop") or "noop").lower()
    if strategy_type == "sma":
        generator = SimpleBarsSignalGenerator(
            event_store=event_store,
            symbols=config.market_data_symbols,
            asset_class=config.market_data_asset_class,
            timeframe=config.strategy_timeframe,
            signals=[
                SmaCrossoverSignal(
                    short=SmaIndicator(period=config.sma_short_window),
                    long=SmaIndicator(period=config.sma_long_window),
                )
            ],
        )
        return SimpleStrategy(
            signal_generator=generator,
            primary_signal="sma_crossover",
        )
    return NoOpStrategy()


def main() -> None:
    """Module entry point for running a single cycle."""
    import argparse

    load_dotenv(".env")
    parser = argparse.ArgumentParser(description="Run a single trading cycle.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    args = parser.parse_args()

    config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(config_data))
    config = build_config(config_data)
    _log_startup_config(config)
    result = run_cycle(config=config, config_snapshot=config_data)
    logger.info(
        "Cycle complete",
        extra={"run_id": result.run_id, "cycle_id": result.cycle_id, "status": result.status},
    )


if __name__ == "__main__":
    main()
