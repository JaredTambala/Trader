"""Single execution cycle entry point."""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import uuid
import json
from typing import AsyncIterator, Mapping, Sequence

from .broker import AlpacaPaperBroker, Broker, InternalPaperBroker, NoOpBroker
from .config import Config
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
from .portfolio import Portfolio, Position
from .strategies import Strategy
from .risk import (
    RiskContext,
    RiskManager,
    RiskPipeline,
)
from .strategy_metadata import resolve_strategy_id, resolve_strategy_type
from .symbols import find_unmatched_positions, normalize_broker_positions


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CycleResult:
    run_id: str
    cycle_id: str
    status: str


def _log_order_status(
    status: str,
    order: Mapping[str, object],
    *,
    run_id: str,
    cycle_id: str,
    extra: str | None = None,
) -> None:
    """Emit a concise runtime log for order lifecycle state."""
    message = (
        "Order %s symbol=%s side=%s qty=%s run_id=%s cycle_id=%s client_order_id=%s"
        % (
            status,
            order.get("symbol"),
            order.get("side"),
            order.get("qty"),
            run_id,
            cycle_id,
            order.get("client_order_id"),
        )
    )
    if extra:
        message = f"{message} {extra}"
    logger.info(message)


def _iter_risk_managers(risk_manager: RiskManager) -> Sequence[RiskManager]:
    """Expand a risk manager into ordered components for logging."""
    if isinstance(risk_manager, RiskPipeline):
        return tuple(risk_manager.managers)
    return (risk_manager,)


def run_cycle(
    strategy: Strategy,
    risk_manager: RiskManager,
    event_store: EventStore | None = None,
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
        risk_manager: Risk manager pipeline used to validate candidate orders.
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
    strategy_id = resolve_strategy_id(strategy, config.strategy_id)
    strategy_type = resolve_strategy_type(strategy, config.strategy_type)
    logger.info(
        "Cycle start mode=%s strategy_type=%s strategy_id=%s event_store=%s market_data_source=%s asset_class=%s symbols=%s timeframe=%s",
        config.mode,
        strategy_type,
        strategy_id,
        config.event_store,
        config.market_data_source,
        config.market_data_asset_class,
        ",".join(config.market_data_symbols) if config.market_data_symbols else "<none>",
        config.strategy_timeframe,
    )
    owns_event_store = False
    if event_store is None:
        event_store = build_event_store(config)
        owns_event_store = True
        logger.info("Event store initialized backend=%s", config.event_store.lower())

    broker = broker or _build_broker(config, event_store)

    decision_ts = decision_ts or datetime.now(timezone.utc)
    if decision_ts.tzinfo is None:
        decision_ts = decision_ts.replace(tzinfo=timezone.utc)

    event_store = _apply_event_filters(event_store, config)
    event_store.flush()

    broker_kind = config.broker_type.lower()

    # Refresh portfolio from broker each cycle for Alpaca to avoid stale DB state.
    if broker_kind == "alpaca":
        portfolio = _load_portfolio_from_broker(
            broker=broker,
            event_store=event_store,
            run_id=run_id or "",
            cycle_id=None,
            decision_ts=decision_ts,
            config=config,
        )
        logger.info(
            "Portfolio loaded from Alpaca positions=%s cash=%s",
            len(portfolio.positions),
            portfolio.cash_balance,
        )
    elif portfolio is None:
        portfolio_asof = decision_ts if config.mode.lower() == "backtest" else None
        portfolio = Portfolio.from_event_store(event_store, asof_ts=portfolio_asof)
        logger.info("Portfolio loaded positions=%s", len(portfolio.positions))
    else:
        logger.info("Portfolio override positions=%s", len(portfolio.positions))

    if market_data_source is None:
        market_data_source = _build_market_data_source(config)

    run_type = (run_type or ("backtest" if config.mode.lower() == "backtest" else "trading")).lower()
    cycle_id = deterministic_cycle_id(strategy_id, decision_ts)
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
            strategy_id=strategy_id,
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
            strategy_id=strategy_id,
            mode=config.mode,
            decision_ts=decision_ts,
            started_at=started_at,
        )
        stream_mode = config.mode.lower() != "backtest"
        broker_kind = config.broker_type.lower()
        sync_portfolio_on_fill = broker_kind in {"alpaca", "internal"}
        processed_orders: Sequence[Mapping[str, object]] = []
        market_data_events: Sequence[MarketDataEvent] = []
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
                    asset_class=config.market_data_asset_class,
                    time_in_force=config.broker_time_in_force,
                    sync_portfolio_on_fill=sync_portfolio_on_fill,
                    broker_type=broker_kind,
                    config=config,
                    risk_manager=risk_manager,
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
                            asset_class=config.market_data_asset_class,
                            time_in_force=config.broker_time_in_force,
                            sync_portfolio_on_fill=sync_portfolio_on_fill,
                            broker_type=broker_kind,
                            config=config,
                            risk_manager=risk_manager,
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
                        asset_class=config.market_data_asset_class,
                        time_in_force=config.broker_time_in_force,
                        sync_portfolio_on_fill=sync_portfolio_on_fill,
                        broker_type=broker_kind,
                        config=config,
                        risk_manager=risk_manager,
                    )
                )

        if config.metrics_enable_snapshots:
            snapshot_ts = decision_ts if config.mode.lower() == "backtest" else datetime.now(timezone.utc)
            if not price_lookup and market_data_events:
                price_lookup = _build_price_lookup(market_data_events)
            if price_lookup:
                _record_metrics_snapshot(
                    event_store=event_store,
                    portfolio=portfolio,
                    price_lookup=price_lookup,
                    asof_ts=snapshot_ts,
                    run_id=run_id,
                    cycle_id=cycle_id,
                    asset_class=config.market_data_asset_class,
                    symbols=config.market_data_symbols,
                )

        if processed_orders:
            if sync_portfolio_on_fill and broker_kind == "alpaca":
                logger.info("Portfolio snapshot skipped; alpaca fills sync portfolio state")
            elif sync_portfolio_on_fill and broker_kind == "internal":
                snapshot_ts = decision_ts if config.mode.lower() == "backtest" else datetime.now(timezone.utc)
                snapshot = portfolio.snapshot(
                    asof_ts=snapshot_ts,
                    run_id=run_id,
                    cycle_id=cycle_id,
                    session_id=run_id,
                )
                snapshot.persist(event_store)
                logger.info("Portfolio snapshot recorded (broker fills) count=%s", len(snapshot.positions))
            else:
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
                strategy_id=strategy_id,
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
            strategy_id=strategy_id,
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
                strategy_id=strategy_id,
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
        return InternalPaperBroker(
            reject_probability=getattr(config, "internal_broker_reject_probability", 0.0),
            fill_delay_ms_mean=getattr(config, "internal_broker_fill_delay_ms_mean", 0.0),
            fill_delay_ms_stddev=getattr(config, "internal_broker_fill_delay_ms_stddev", 0.0),
            fill_qty_fraction_mean=getattr(config, "internal_broker_fill_qty_fraction_mean", 1.0),
            fill_qty_fraction_stddev=getattr(config, "internal_broker_fill_qty_fraction_stddev", 0.0),
            rng_seed=getattr(config, "internal_broker_rng_seed", None),
        )
    if broker_type in {"alpaca", "alpaca-paper", "alpaca_paper"}:
        return AlpacaPaperBroker(
            api_key=config.alpaca_api_key,
            secret_key=config.alpaca_secret_key,
            base_url=getattr(config, "alpaca_base_url", None),
            event_store=event_store,
        )
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
    asset_class: str,
    time_in_force: str,
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
                "session_id": run_id,
                "cycle_id": cycle_id,
                "client_order_id": client_order_id,
                "price": price,
                "created_at": order.get("created_at") or timestamp,
                "asset_class": asset_class,
                "time_in_force": order.get("time_in_force", time_in_force),
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
        session_id = order.get("session_id") or order.get("run_id")
        event_store.record_event(
            "order_events",
            {
                "order_event_id": f"order_evt_{uuid.uuid4().hex}",
                "client_order_id": order.get("client_order_id"),
                "run_id": order.get("run_id"),
                "session_id": session_id,
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
        rejection_reason = response.get("rejection_reason")
        order_payload = order if rejection_reason is None else {**order, "rejection_reason": rejection_reason}
        _record_order_events(
            event_store,
            [order_payload],
            status=status,
            broker_order_id=broker_order_id,
            event_ts=response.get("fill_ts") or datetime.now(timezone.utc),
        )
        if status in {"filled", "partially_filled"}:
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
                    "session_id": order.get("session_id") or order.get("run_id"),
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
    asset_class: str,
    time_in_force: str,
    sync_portfolio_on_fill: bool,
    broker_type: str,
    config: Config,
    risk_manager: RiskManager,
) -> tuple[Sequence[Mapping[str, object]], Mapping[str, float]]:
    """Process market data events through the async pipeline."""
    event_queue: asyncio.Queue[MarketDataEvent | None] = asyncio.Queue()
    order_queue: asyncio.Queue[Mapping[str, object] | None] = asyncio.Queue()
    validated_queue: asyncio.Queue[Mapping[str, object] | None] = asyncio.Queue()
    processed: list[Mapping[str, object]] = []
    latest_prices: dict[str, tuple[datetime, float]] = {}
    counters = {
        "orders_emitted": 0,
        "orders_rejected_locally": 0,
        "orders_validated": 0,
        "orders_submitted": 0,
        "broker_responses": 0,
    }

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
                    asset_class=asset_class,
                    time_in_force=time_in_force,
                )[0]
                _record_order_events(event_store, [enriched], status="created")
                _log_order_status("created", enriched, run_id=run_id, cycle_id=cycle_id)
                counters["orders_emitted"] += 1
                await order_queue.put(enriched)

    async def validator() -> None:
        """Handle validator."""
        while True:
            order = await order_queue.get()
            if order is None:
                await validated_queue.put(None)
                break
            symbol = str(order.get("symbol", "")).strip().upper()
            order_price = order.get("price")
            price_lookup = {sym: price for sym, (_, price) in latest_prices.items()}
            if symbol and order_price is not None:
                price_lookup[symbol] = float(order_price)
            context = RiskContext(
                positions=portfolio.positions,
                open_orders=_load_latest_order_events(event_store),
                price_lookup=price_lookup,
                run_id=run_id,
                cycle_id=cycle_id,
                decision_ts=order.get("created_at") or datetime.now(timezone.utc),
                halted=_load_halt_flag(event_store),
            )

            approved_orders = [order]
            rejected_orders: list[Mapping[str, object]] = []
            for manager in _iter_risk_managers(risk_manager):
                approved_orders, rejected = manager.evaluate(approved_orders, context)
                if rejected:
                    for rejected_order in rejected:
                        counters["orders_rejected_locally"] += 1
                        _log_order_status(
                            "rejected",
                            rejected_order,
                            run_id=run_id,
                            cycle_id=cycle_id,
                            extra="reason=%s manager=%s"
                            % (rejected_order.get("rejection_reason"), manager.__class__.__name__),
                        )
                    rejected_orders.extend(rejected)
                if not approved_orders:
                    break
            _record_order_events(event_store, rejected_orders, status="rejected")
            if approved_orders:
                _record_order_events(event_store, approved_orders, status="validated")
                _log_order_status("validated", approved_orders[0], run_id=run_id, cycle_id=cycle_id)
                counters["orders_validated"] += len(approved_orders)
                await validated_queue.put(approved_orders[0])

    async def submitter() -> None:
        """Handle submitter."""
        while True:
            order = await validated_queue.get()
            if order is None:
                break
            _record_order_events(event_store, [order], status="submitted")
            _log_order_status("submitted", order, run_id=run_id, cycle_id=cycle_id)
            counters["orders_submitted"] += 1
            responses = await asyncio.to_thread(broker.submit_orders, [order])
            _record_broker_responses(event_store, [order], responses)
            counters["broker_responses"] += len(responses)
            processed_order = order
            if responses:
                response = responses[0]
                status = str(response.get("status", "submitted"))
                _log_order_status(
                    f"broker_response status={status}",
                    order,
                    run_id=run_id,
                    cycle_id=cycle_id,
                    extra="broker_order_id=%s reason=%s"
                    % (response.get("broker_order_id"), response.get("rejection_reason")),
                )
                if status in {"rejected", "canceled", "expired", "error"}:
                    continue
                if sync_portfolio_on_fill and status in {"filled", "partially_filled"}:
                    fill_ts = response.get("fill_ts") or datetime.now(timezone.utc)
                    if broker_type == "alpaca":
                        _sync_portfolio_from_broker(
                            event_store=event_store,
                            broker=broker,
                            portfolio=portfolio,
                            run_id=run_id,
                            cycle_id=cycle_id,
                            asof_ts=fill_ts,
                            config=config,
                        )
                    elif broker_type == "internal":
                        _apply_fill_to_portfolio(
                            portfolio=portfolio,
                            order=order,
                            response=response,
                        )
                        snapshot = portfolio.snapshot(
                            asof_ts=fill_ts,
                            run_id=run_id,
                            cycle_id=cycle_id,
                            session_id=run_id,
                        )
                        snapshot.persist(event_store)
                        logger.info(
                            "Portfolio snapshot recorded (internal fill) count=%s",
                            len(snapshot.positions),
                        )
                fill_qty = response.get("fill_qty")
                fill_price = response.get("fill_price")
                if fill_qty is not None:
                    processed_order = {**processed_order, "qty": float(fill_qty)}
                if fill_price is not None:
                    processed_order = {**processed_order, "price": float(fill_price)}
            processed.append(processed_order)

    await asyncio.gather(producer(), signal_worker(), validator(), submitter())
    logger.info(
        "Cycle order summary run_id=%s cycle_id=%s orders_emitted=%s orders_rejected_locally=%s orders_validated=%s orders_submitted=%s broker_responses=%s",
        run_id,
        cycle_id,
        counters["orders_emitted"],
        counters["orders_rejected_locally"],
        counters["orders_validated"],
        counters["orders_submitted"],
        counters["broker_responses"],
    )
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


def _load_latest_order_events(event_store: EventStore) -> Sequence[Mapping[str, object]]:
    """Load the latest order event per client_order_id."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return []
    query = (
        "SELECT client_order_id, run_id, cycle_id, symbol, side, qty, order_type, "
        "status, broker_order_id, created_at "
        "FROM order_events ORDER BY created_at DESC, order_event_id DESC"
    )
    try:
        if hasattr(connection, "cursor"):
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
        else:
            rows = connection.execute(query).fetchall()
    except Exception as exc:
        logger.warning("Risk context order query failed: %s", exc)
        return []
    seen: set[str] = set()
    latest: list[Mapping[str, object]] = []
    for row in rows or []:
        client_order_id = row[0]
        if not client_order_id or client_order_id in seen:
            continue
        seen.add(client_order_id)
        latest.append(
            {
                "client_order_id": client_order_id,
                "run_id": row[1],
                "cycle_id": row[2],
                "symbol": row[3],
                "side": row[4],
                "qty": row[5],
                "order_type": row[6],
                "status": row[7],
                "broker_order_id": row[8],
                "created_at": row[9],
            }
        )
    return latest


def _load_halt_flag(event_store: EventStore) -> bool:
    """Load the global halt flag from config_kv."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return False
    query = "SELECT value FROM config_kv WHERE key = 'halt' LIMIT 1"
    try:
        if hasattr(connection, "cursor"):
            with connection.cursor() as cursor:
                cursor.execute(query)
                row = cursor.fetchone()
        else:
            row = connection.execute(query).fetchone()
    except Exception as exc:
        logger.warning("Risk context halt query failed: %s", exc)
        return False
    if not row:
        return False
    value = str(row[0]).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


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
    snapshot = portfolio.snapshot(
        asof_ts=asof_ts,
        run_id=run_id,
        cycle_id=cycle_id,
        session_id=run_id,
    )
    snapshot.persist(event_store)
    logger.info("Portfolio snapshot recorded count=%s", len(snapshot.positions))


def _apply_fill_to_portfolio(
    *,
    portfolio: Portfolio,
    order: Mapping[str, object],
    response: Mapping[str, object],
) -> None:
    """Apply a single fill to the in-memory portfolio (for internal broker)."""
    fill_qty = response.get("fill_qty", order.get("qty"))
    fill_price = response.get("fill_price", order.get("price"))
    symbol = str(order.get("symbol", "")).strip()
    side = str(order.get("side", "")).lower().strip()
    if not symbol or side not in {"buy", "sell"}:
        return
    try:
        qty = float(fill_qty) if fill_qty is not None else 0.0
    except (TypeError, ValueError):
        qty = 0.0
    if qty <= 0:
        return
    price_lookup = {symbol: float(fill_price)} if fill_price is not None else {}
    portfolio.apply_orders(
        [
            {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": fill_price,
            }
        ],
        price_lookup=price_lookup,
    )


def _load_portfolio_from_broker(
    *,
    broker: Broker,
    event_store: EventStore,
    run_id: str,
    cycle_id: str | None,
    decision_ts: datetime,
    config: Config,
) -> Portfolio:
    """Load portfolio state from a broker (Alpaca) each cycle."""
    get_account = getattr(broker, "get_account", None)
    get_positions = getattr(broker, "get_positions", None)
    if not callable(get_account) or not callable(get_positions):
        logger.warning("Broker portfolio load skipped; broker lacks account/position access")
        return Portfolio.from_event_store(event_store)

    try:
        account = get_account()
        cash_raw = account.get("cash", 0.0) if isinstance(account, Mapping) else 0.0
        cash = float(cash_raw) if cash_raw is not None else 0.0
        positions_raw = get_positions() or []
        normalized_positions = normalize_broker_positions(positions_raw)
        _validate_broker_positions(normalized_positions, config)
        positions: dict[str, Position] = {}
        for position in normalized_positions:
            positions[position.symbol] = Position(
                symbol=position.symbol,
                qty=position.qty,
                avg_price=position.avg_entry_price,
            )
        portfolio = Portfolio(positions=positions, cash_balance=cash)
        snapshot = portfolio.snapshot(
            asof_ts=decision_ts,
            run_id=run_id,
            cycle_id=cycle_id,
            session_id=run_id,
        )
        snapshot.persist(event_store)
        return portfolio
    except Exception as exc:  # pragma: no cover - external dependency
        logger.error("Broker portfolio load failed: %s", exc)
        raise


def _sync_portfolio_from_broker(
    *,
    event_store: EventStore,
    broker: Broker,
    portfolio: Portfolio,
    run_id: str,
    cycle_id: str | None,
    asof_ts: datetime,
    config: Config,
) -> None:
    """Refresh portfolio state from the broker after fills."""
    get_account = getattr(broker, "get_account", None)
    get_positions = getattr(broker, "get_positions", None)
    if not callable(get_account) or not callable(get_positions):
        logger.warning("Portfolio sync skipped; broker lacks account/position access")
        return

    account = get_account()
    cash_raw = account.get("cash", 0.0) if isinstance(account, Mapping) else 0.0
    cash = float(cash_raw) if cash_raw is not None else 0.0
    positions_raw = get_positions() or []
    normalized_positions = normalize_broker_positions(positions_raw)
    _validate_broker_positions(normalized_positions, config)
    positions: dict[str, Position] = {}
    for position in normalized_positions:
        positions[position.symbol] = Position(
            symbol=position.symbol,
            qty=position.qty,
            avg_price=position.avg_entry_price,
        )

    portfolio.positions = positions
    portfolio.cash_balance = cash
    snapshot = portfolio.snapshot(
        asof_ts=asof_ts,
        run_id=run_id,
        cycle_id=cycle_id,
        session_id=run_id,
    )
    snapshot.persist(event_store)
    logger.info("Portfolio synced from broker positions=%s cash=%s", len(positions), cash)


def _validate_broker_positions(positions, config: Config) -> None:
    """Fail closed when broker positions do not match the configured live universe."""
    mismatches = find_unmatched_positions(
        positions,
        configured_symbols=config.market_data_symbols,
        configured_asset_class=config.market_data_asset_class,
    )
    if not mismatches:
        return
    mismatch_text = ", ".join(
        "%s(asset_class=%s raw_symbol=%s raw_asset_class=%s qty=%s)"
        % (
            position.symbol,
            position.asset_class,
            position.raw_symbol,
            position.raw_asset_class or "<none>",
            position.qty,
        )
        for position in mismatches
    )
    raise ValueError(
        "Broker portfolio mismatch with configured trading universe "
        f"symbols={config.market_data_symbols} asset_class={config.market_data_asset_class}: {mismatch_text}"
    )


def _record_metrics_snapshot(
    *,
    event_store: EventStore,
    portfolio: Portfolio,
    price_lookup: Mapping[str, float],
    asof_ts: datetime,
    run_id: str,
    cycle_id: str | None,
    asset_class: str,
    symbols: Sequence[str],
) -> None:
    """Persist a schema-less metrics snapshot as JSON text."""
    equity = portfolio.cash_balance
    net = 0.0
    gross = 0.0
    for position in portfolio.positions.values():
        price = price_lookup.get(position.symbol)
        if price is None:
            continue
        notional = position.qty * price
        equity += notional
        net += notional
        gross += abs(notional)
    payload = {
        "equity": equity,
        "cash": portfolio.cash_balance,
        "net_exposure": net,
        "gross_exposure": gross,
        "asset_class": asset_class,
        "symbols": list(symbols),
    }
    event_store.record_event(
        "metrics_snapshots",
        {
            "ts": asof_ts,
            "run_id": run_id,
            "session_id": run_id,
            "cycle_id": cycle_id,
            "payload": json.dumps(payload),
        },
    )


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


def main() -> None:
    """Reject direct module execution in favor of injected wrapper scripts."""
    raise SystemExit(
        "trader.cycle is a library module. "
        "Construct a Strategy and RiskManager in your own wrapper script and call run_cycle(...)."
    )


if __name__ == "__main__":
    main()
