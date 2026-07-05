"""Production decision-cycle orchestration.

This module coordinates market-data ingestion, strategy order generation, risk
validation, broker submission, portfolio updates, metrics, and append-only audit
events for one trading or backtest decision timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Mapping, Sequence

from ..broker import AlpacaPaperBroker, Broker, InternalPaperBroker, NoOpBroker
from ..config import Config
from ..event_store import EventStore, FilteredEventStore, build_event_store
from ..market_data import (
    MarketDataEvent,
    MarketDataIngestor,
    MarketDataSource,
    NoOpMarketDataSource,
)
from ..market_data.alpaca import AlpacaMarketDataSource
from ..portfolio import Portfolio
from ..strategies import Strategy
from ..risk import RiskManager
from ..strategy_metadata import resolve_strategy_id, resolve_strategy_type
from .broker_state import (
    _build_processed_order_from_broker_response,
    _resolve_broker_response_status,
    _should_sync_portfolio_for_broker_response,
)
from .filters import _allowed_cycle_event_types
from .lifecycle import (
    CycleExecutionPlan,
    CycleIdentity,
    CycleResult,
    CycleWorkflowResult,
    _build_cycle_execution_plan,
    _build_cycle_identity,
    _build_cycle_run_session_outcome,
    _resolve_decision_ts,
    _resolve_market_data_freshness_ts,
    _should_halt_cycle,
    _should_use_stream_ingestion,
)
from .market_data import (
    CycleMarketDataPipelineResult,
    _build_recent_market_data_query,
    _market_data_event_table_name,
    _row_to_market_event,
)
from .portfolio_state import (
    _load_cycle_portfolio,
    _record_cycle_metrics_snapshot_if_enabled,
    _record_post_order_portfolio_snapshot,
    _sync_portfolio_for_broker_response,
)
from .orders import (
    _attach_order_metadata,
)
from .order_state import (
    _dedupe_latest_order_event_rows,
    _latest_order_events_query,
)
from .readiness import (
    _is_event_stale,
    _normalize_timestamp,
    assess_market_data_readiness,
)
from .recording import (
    _record_broker_responses,
    _record_failed_cycle_finish,
    _record_halted_cycle_finish,
    _record_order_events,
    _record_owned_run_session_finish,
    _record_owned_run_session_start,
    _record_successful_cycle_finish,
)
from .risk import (
    _build_cycle_risk_context,
    _evaluate_cycle_order_risk,
)
from .stream import (
    CycleStreamRuntime,
    CycleStreamState,
    _build_cycle_stream_state,
    _latest_stream_prices,
)
from .startup import _startup_config_log_values


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CycleRuntimeSetup:
    """Runtime dependencies and identities prepared before executing a cycle."""

    event_store: EventStore
    owns_event_store: bool
    broker: Broker
    decision_ts: datetime
    execution_plan: CycleExecutionPlan
    started_at: datetime
    cycle_identity: CycleIdentity


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


def _initialize_cycle_runtime(
    *,
    config: Config,
    event_store: EventStore | None,
    broker: Broker | None,
    decision_ts: datetime | None,
    run_type: str | None,
    run_id: str | None,
    strategy_id: str,
) -> CycleRuntimeSetup:
    """Prepare runtime dependencies and deterministic identities for a cycle."""
    owns_event_store = False
    if event_store is None:
        event_store = build_event_store(config)
        owns_event_store = True
        logger.info("Event store initialized backend=%s", config.event_store.lower())

    resolved_broker = broker or _build_broker(config, event_store)
    resolved_decision_ts = _resolve_decision_ts(
        decision_ts,
        current_ts=datetime.now(timezone.utc),
    )

    filtered_event_store = _apply_event_filters(event_store, config)
    filtered_event_store.flush()

    raw_broker_kind = config.broker_type.lower()
    execution_plan = _build_cycle_execution_plan(
        mode=config.mode,
        broker_type=config.broker_type,
        portfolio_source=getattr(
            config,
            "trader_service_portfolio_source",
            "alpaca" if raw_broker_kind == "alpaca" else "db",
        ),
        run_type=run_type,
    )
    started_at = datetime.now(timezone.utc)
    cycle_identity = _build_cycle_identity(
        strategy_id=strategy_id,
        decision_ts=resolved_decision_ts,
        run_type=execution_plan.run_type,
        started_at=started_at,
        run_id=run_id,
    )
    return CycleRuntimeSetup(
        event_store=filtered_event_store,
        owns_event_store=owns_event_store,
        broker=resolved_broker,
        decision_ts=resolved_decision_ts,
        execution_plan=execution_plan,
        started_at=started_at,
        cycle_identity=cycle_identity,
    )


def _run_market_data_pipeline_for_plan(
    *,
    event_store: EventStore,
    strategy: Strategy,
    risk_manager: RiskManager,
    broker: Broker,
    config: Config,
    execution_plan: CycleExecutionPlan,
    portfolio: Portfolio,
    run_id: str,
    cycle_id: str,
    decision_ts: datetime,
    market_data_source: MarketDataSource | None,
    ingest_market_data: bool,
) -> CycleMarketDataPipelineResult:
    """Run the market-data/order pipeline selected by the execution plan."""
    resolved_market_data_source = market_data_source or _build_market_data_source(config)
    if _should_use_stream_ingestion(
        ingest_market_data=ingest_market_data,
        stream_mode=execution_plan.stream_mode,
    ):
        return _run_streaming_market_data_pipeline(
            event_store=event_store,
            strategy=strategy,
            broker=broker,
            portfolio=portfolio,
            run_id=run_id,
            cycle_id=cycle_id,
            market_data_source=resolved_market_data_source,
            config=config,
            decision_ts=decision_ts,
            sync_portfolio_on_fill=execution_plan.sync_portfolio_on_fill,
            broker_kind=execution_plan.broker_kind,
            risk_manager=risk_manager,
        )
    return _run_batch_market_data_pipeline(
        event_store=event_store,
        strategy=strategy,
        broker=broker,
        portfolio=portfolio,
        run_id=run_id,
        cycle_id=cycle_id,
        market_data_source=resolved_market_data_source,
        config=config,
        decision_ts=decision_ts,
        ingest_market_data=ingest_market_data,
        sync_portfolio_on_fill=execution_plan.sync_portfolio_on_fill,
        broker_kind=execution_plan.broker_kind,
        risk_manager=risk_manager,
    )


def _execute_cycle_workflow(
    *,
    event_store: EventStore,
    strategy: Strategy,
    risk_manager: RiskManager,
    broker: Broker,
    config: Config,
    execution_plan: CycleExecutionPlan,
    strategy_id: str,
    run_id: str,
    cycle_id: str,
    decision_ts: datetime,
    started_at: datetime,
    market_data_source: MarketDataSource | None,
    portfolio: Portfolio | None,
    ingest_market_data: bool,
) -> CycleWorkflowResult:
    """Run the side-effecting cycle workflow after setup is complete."""
    event_store.record_cycle_start(
        run_id=run_id,
        cycle_id=cycle_id,
        strategy_id=strategy_id,
        mode=config.mode,
        decision_ts=decision_ts,
        started_at=started_at,
    )
    if _should_halt_cycle(run_type=execution_plan.run_type, halted=_load_halt_flag(event_store)):
        logger.warning("Cycle halted by global halt run_id=%s cycle_id=%s", run_id, cycle_id)
        _record_halted_cycle_finish(
            event_store=event_store,
            run_id=run_id,
            cycle_id=cycle_id,
            strategy_id=strategy_id,
            mode=config.mode,
            decision_ts=decision_ts,
            started_at=started_at,
        )
        return CycleWorkflowResult(
            cycle_result=CycleResult(run_id=run_id, cycle_id=cycle_id, status="halted"),
            run_session_outcome=_build_cycle_run_session_outcome("halted", "global_halt"),
        )

    loaded_portfolio = _load_cycle_portfolio(
        broker=broker,
        event_store=event_store,
        run_id=run_id,
        cycle_id=cycle_id,
        decision_ts=decision_ts,
        config=config,
        execution_plan=execution_plan,
        portfolio=portfolio,
    )

    market_data_result = _run_market_data_pipeline_for_plan(
        event_store=event_store,
        strategy=strategy,
        risk_manager=risk_manager,
        broker=broker,
        config=config,
        execution_plan=execution_plan,
        portfolio=loaded_portfolio,
        run_id=run_id,
        cycle_id=cycle_id,
        decision_ts=decision_ts,
        market_data_source=market_data_source,
        ingest_market_data=ingest_market_data,
    )
    processed_orders = market_data_result.processed_orders
    market_data_events = market_data_result.market_data_events
    price_lookup = _record_cycle_metrics_snapshot_if_enabled(
        event_store=event_store,
        portfolio=loaded_portfolio,
        price_lookup=market_data_result.price_lookup,
        market_data_events=market_data_events,
        metrics_enabled=config.metrics_enable_snapshots,
        mode=config.mode,
        decision_ts=decision_ts,
        run_id=run_id,
        cycle_id=cycle_id,
        asset_class=config.market_data_asset_class,
        symbols=config.market_data_symbols,
    )

    _record_post_order_portfolio_snapshot(
        event_store=event_store,
        portfolio=loaded_portfolio,
        processed_orders=processed_orders,
        sync_portfolio_on_fill=execution_plan.sync_portfolio_on_fill,
        broker_kind=execution_plan.broker_kind,
        mode=config.mode,
        decision_ts=decision_ts,
        run_id=run_id,
        cycle_id=cycle_id,
        price_lookup=price_lookup,
    )
    _record_successful_cycle_finish(
        event_store=event_store,
        run_id=run_id,
        cycle_id=cycle_id,
        strategy_id=strategy_id,
        mode=config.mode,
        decision_ts=decision_ts,
        started_at=started_at,
    )
    return CycleWorkflowResult(
        cycle_result=CycleResult(run_id=run_id, cycle_id=cycle_id, status="success"),
        run_session_outcome=_build_cycle_run_session_outcome("success"),
    )


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
    runtime_setup = _initialize_cycle_runtime(
        config=config,
        event_store=event_store,
        broker=broker,
        decision_ts=decision_ts,
        run_type=run_type,
        run_id=run_id,
        strategy_id=strategy_id,
    )
    event_store = runtime_setup.event_store
    broker = runtime_setup.broker
    decision_ts = runtime_setup.decision_ts
    execution_plan = runtime_setup.execution_plan
    run_type = execution_plan.run_type
    started_at = runtime_setup.started_at
    cycle_identity = runtime_setup.cycle_identity
    run_id = cycle_identity.run_id
    cycle_id = cycle_identity.cycle_id
    owns_run_session = cycle_identity.owns_run_session
    owns_event_store = runtime_setup.owns_event_store
    run_session_outcome = _build_cycle_run_session_outcome("success")
    _record_owned_run_session_start(
        event_store=event_store,
        owns_run_session=owns_run_session,
        run_id=run_id,
        run_type=run_type,
        started_at=started_at,
        strategy_id=strategy_id,
        config_snapshot=config_snapshot,
        mode=config.mode,
        symbols=config.market_data_symbols,
        timeframe=config.strategy_timeframe,
    )

    workflow_result: CycleWorkflowResult | None = None
    try:
        workflow_result = _execute_cycle_workflow(
            event_store=event_store,
            strategy=strategy,
            risk_manager=risk_manager,
            broker=broker,
            config=config,
            execution_plan=execution_plan,
            strategy_id=strategy_id,
            run_id=run_id,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            started_at=started_at,
            market_data_source=market_data_source,
            portfolio=portfolio,
            ingest_market_data=ingest_market_data,
        )
        run_session_outcome = workflow_result.run_session_outcome
    except Exception as exc:
        _record_failed_cycle_finish(
            event_store=event_store,
            run_id=run_id,
            cycle_id=cycle_id,
            strategy_id=strategy_id,
            mode=config.mode,
            decision_ts=decision_ts,
            started_at=started_at,
            error_message=str(exc),
        )
        run_session_outcome = _build_cycle_run_session_outcome("failed", str(exc))
        raise
    finally:
        _record_owned_run_session_finish(
            event_store=event_store,
            owns_run_session=owns_run_session,
            run_id=run_id,
            run_type=run_type,
            started_at=started_at,
            outcome=run_session_outcome,
            strategy_id=strategy_id,
            mode=config.mode,
            symbols=config.market_data_symbols,
            timeframe=config.strategy_timeframe,
        )
        if owns_event_store:
            event_store.close()

    if workflow_result is None:
        raise RuntimeError("cycle workflow did not produce a result")
    if workflow_result.cycle_result.status == "success":
        logger.info("Completed cycle", extra={"run_id": run_id, "cycle_id": cycle_id})
    return workflow_result.cycle_result


async def _event_stream_with_count(
    event_stream: AsyncIterator[MarketDataEvent],
    counter: dict[str, int],
) -> AsyncIterator[MarketDataEvent]:
    """Wrap an async event stream and count items as they flow through."""
    async for event in event_stream:
        counter["count"] = counter.get("count", 0) + 1
        yield event


def _run_market_event_stream_pipeline(
    *,
    event_store: EventStore,
    strategy: Strategy,
    broker: Broker,
    portfolio: Portfolio,
    run_id: str,
    cycle_id: str,
    event_stream: AsyncIterator[MarketDataEvent],
    config: Config,
    enforce_staleness: bool,
    sync_portfolio_on_fill: bool,
    broker_kind: str,
    risk_manager: RiskManager,
) -> tuple[Sequence[Mapping[str, object]], Mapping[str, float]]:
    """Run a market-event stream through strategy, risk, and broker stages."""
    return asyncio.run(
        _process_market_stream_async(
            event_store=event_store,
            strategy=strategy,
            broker=broker,
            portfolio=portfolio,
            run_id=run_id,
            cycle_id=cycle_id,
            event_stream=event_stream,
            max_age_seconds=config.market_data_max_age_seconds,
            enforce_staleness=enforce_staleness,
            asset_class=config.market_data_asset_class,
            time_in_force=config.broker_time_in_force,
            sync_portfolio_on_fill=sync_portfolio_on_fill,
            broker_type=broker_kind,
            config=config,
            risk_manager=risk_manager,
        )
    )


def _run_streaming_market_data_pipeline(
    *,
    event_store: EventStore,
    strategy: Strategy,
    broker: Broker,
    portfolio: Portfolio,
    run_id: str,
    cycle_id: str,
    market_data_source: MarketDataSource,
    config: Config,
    decision_ts: datetime,
    sync_portfolio_on_fill: bool,
    broker_kind: str,
    risk_manager: RiskManager,
) -> CycleMarketDataPipelineResult:
    """Run stream ingestion with recent-bar fallback when the stream is empty."""
    event_counter = {"count": 0}
    processed_orders, price_lookup = _run_market_event_stream_pipeline(
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
        config=config,
        enforce_staleness=True,
        sync_portfolio_on_fill=sync_portfolio_on_fill,
        broker_kind=broker_kind,
        risk_manager=risk_manager,
    )
    if event_counter["count"] != 0:
        return CycleMarketDataPipelineResult(
            processed_orders=processed_orders,
            market_data_events=(),
            price_lookup=price_lookup,
        )

    market_data_events = _load_recent_market_data(event_store, config, decision_ts)
    return _run_market_data_events_pipeline(
        event_store=event_store,
        strategy=strategy,
        broker=broker,
        portfolio=portfolio,
        run_id=run_id,
        cycle_id=cycle_id,
        market_data_events=market_data_events,
        config=config,
        decision_ts=decision_ts,
        sync_portfolio_on_fill=sync_portfolio_on_fill,
        broker_kind=broker_kind,
        risk_manager=risk_manager,
    )


def _run_batch_market_data_pipeline(
    *,
    event_store: EventStore,
    strategy: Strategy,
    broker: Broker,
    portfolio: Portfolio,
    run_id: str,
    cycle_id: str,
    market_data_source: MarketDataSource,
    config: Config,
    decision_ts: datetime,
    ingest_market_data: bool,
    sync_portfolio_on_fill: bool,
    broker_kind: str,
    risk_manager: RiskManager,
) -> CycleMarketDataPipelineResult:
    """Run non-stream market-data ingestion/fetching through the order pipeline."""
    if ingest_market_data:
        with event_store.transaction():
            market_data_events = MarketDataIngestor(event_store, market_data_source).ingest()
    else:
        market_data_events = market_data_source.fetch()
        logger.info("Market data fetched without ingest count=%s", len(market_data_events))
    if not market_data_events:
        market_data_events = _load_recent_market_data(event_store, config, decision_ts)
    return _run_market_data_events_pipeline(
        event_store=event_store,
        strategy=strategy,
        broker=broker,
        portfolio=portfolio,
        run_id=run_id,
        cycle_id=cycle_id,
        market_data_events=market_data_events,
        config=config,
        decision_ts=decision_ts,
        sync_portfolio_on_fill=sync_portfolio_on_fill,
        broker_kind=broker_kind,
        risk_manager=risk_manager,
    )


def _run_market_data_events_pipeline(
    *,
    event_store: EventStore,
    strategy: Strategy,
    broker: Broker,
    portfolio: Portfolio,
    run_id: str,
    cycle_id: str,
    market_data_events: Sequence[MarketDataEvent],
    config: Config,
    decision_ts: datetime,
    sync_portfolio_on_fill: bool,
    broker_kind: str,
    risk_manager: RiskManager,
) -> CycleMarketDataPipelineResult:
    """Run already-loaded market-data events through freshness and order stages."""
    freshness_ts = _resolve_market_data_freshness_ts(
        mode=config.mode,
        decision_ts=decision_ts,
        current_ts=datetime.now(timezone.utc),
    )
    should_skip = _should_skip_trading(
        market_data_events,
        freshness_ts,
        config.market_data_max_age_seconds,
    )
    if should_skip:
        logger.warning("Skipping trading due to missing or stale market data")
        return CycleMarketDataPipelineResult(
            processed_orders=(),
            market_data_events=market_data_events,
            price_lookup={},
        )

    processed_orders, price_lookup = _run_market_event_stream_pipeline(
        event_store=event_store,
        strategy=strategy,
        broker=broker,
        portfolio=portfolio,
        run_id=run_id,
        cycle_id=cycle_id,
        event_stream=_event_stream_from_list(market_data_events),
        config=config,
        enforce_staleness=False,
        sync_portfolio_on_fill=sync_portfolio_on_fill,
        broker_kind=broker_kind,
        risk_manager=risk_manager,
    )
    return CycleMarketDataPipelineResult(
        processed_orders=processed_orders,
        market_data_events=market_data_events,
        price_lookup=price_lookup,
    )


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
    """Construct the broker implementation requested by configuration.

    The internal broker is used for deterministic local/backtest execution,
    Alpaca is used for paper trading with event-store-backed idempotency, and
    the no-op broker is the safe fallback for dry-run configurations.
    """
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


async def _produce_market_events(
    event_stream: AsyncIterator[MarketDataEvent],
    event_queue: asyncio.Queue[MarketDataEvent | None],
) -> None:
    """Read upstream market events and terminate the queue with a sentinel."""
    async for event in event_stream:
        await event_queue.put(event)
    await event_queue.put(None)


async def _generate_stream_orders(
    *,
    runtime: CycleStreamRuntime,
    state: CycleStreamState,
    event_queue: asyncio.Queue[MarketDataEvent | None],
    order_queue: asyncio.Queue[Mapping[str, object] | None],
) -> None:
    """Generate enriched order intents from fresh per-symbol market events."""
    while True:
        event = await event_queue.get()
        if event is None:
            await order_queue.put(None)
            break
        now = datetime.now(timezone.utc)
        if runtime.enforce_staleness and _is_event_stale(
            event,
            now,
            runtime.max_age_seconds,
        ):
            logger.warning("Skipping stale market data symbol=%s ts=%s", event.symbol, event.ts.isoformat())
            continue
        symbol = event.symbol
        decision_ts = _normalize_timestamp(event.ts)
        state.latest_prices[symbol] = (decision_ts, float(event.close))
        async for order in runtime.strategy.order_stream_for_symbol(
            symbol,
            run_id=runtime.run_id,
            cycle_id=runtime.cycle_id,
            decision_ts=decision_ts,
            event_store=runtime.event_store,
            portfolio=runtime.portfolio,
        ):
            enriched = _attach_order_metadata(
                [order],
                run_id=runtime.run_id,
                cycle_id=runtime.cycle_id,
                created_at=decision_ts,
                price_lookup={symbol: float(event.close)},
                asset_class=runtime.asset_class,
                time_in_force=runtime.time_in_force,
            )[0]
            _record_order_events(runtime.event_store, [enriched], status="created")
            _log_order_status(
                "created",
                enriched,
                run_id=runtime.run_id,
                cycle_id=runtime.cycle_id,
            )
            state.counters.orders_emitted += 1
            await order_queue.put(enriched)


async def _validate_stream_orders(
    *,
    runtime: CycleStreamRuntime,
    state: CycleStreamState,
    order_queue: asyncio.Queue[Mapping[str, object] | None],
    validated_queue: asyncio.Queue[Mapping[str, object] | None],
) -> None:
    """Evaluate queued orders against the configured risk managers."""
    while True:
        order = await order_queue.get()
        if order is None:
            await validated_queue.put(None)
            break
        context = _build_cycle_risk_context(
            positions=runtime.portfolio.positions,
            open_orders=_load_latest_order_events(runtime.event_store),
            latest_prices=state.latest_prices,
            order=order,
            run_id=runtime.run_id,
            cycle_id=runtime.cycle_id,
            halted=_load_halt_flag(runtime.event_store),
            fallback_ts=datetime.now(timezone.utc),
        )

        evaluation = _evaluate_cycle_order_risk(
            order=order,
            context=context,
            risk_manager=runtime.risk_manager,
        )
        for rejection in evaluation.rejection_logs:
            state.counters.orders_rejected_locally += 1
            _log_order_status(
                "rejected",
                rejection.order,
                run_id=runtime.run_id,
                cycle_id=runtime.cycle_id,
                extra="reason=%s manager=%s"
                % (rejection.order.get("rejection_reason"), rejection.manager_name),
            )
        _record_order_events(runtime.event_store, evaluation.rejected_orders, status="rejected")
        if evaluation.approved_orders:
            _record_order_events(runtime.event_store, evaluation.approved_orders, status="validated")
            _log_order_status(
                "validated",
                evaluation.approved_orders[0],
                run_id=runtime.run_id,
                cycle_id=runtime.cycle_id,
            )
            state.counters.orders_validated += len(evaluation.approved_orders)
            await validated_queue.put(evaluation.approved_orders[0])


async def _submit_stream_orders(
    *,
    runtime: CycleStreamRuntime,
    state: CycleStreamState,
    validated_queue: asyncio.Queue[Mapping[str, object] | None],
) -> None:
    """Submit validated orders and persist broker/accounting side effects."""
    while True:
        order = await validated_queue.get()
        if order is None:
            break
        _record_order_events(runtime.event_store, [order], status="submitted")
        _log_order_status(
            "submitted",
            order,
            run_id=runtime.run_id,
            cycle_id=runtime.cycle_id,
        )
        state.counters.orders_submitted += 1
        responses = await asyncio.to_thread(runtime.broker.submit_orders, [order])
        _record_broker_responses(runtime.event_store, [order], responses)
        state.counters.broker_responses += len(responses)
        processed_order = order
        if responses:
            response = responses[0]
            status = _resolve_broker_response_status(response)
            _log_order_status(
                f"broker_response status={status}",
                order,
                run_id=runtime.run_id,
                cycle_id=runtime.cycle_id,
                extra="broker_order_id=%s reason=%s"
                % (response.get("broker_order_id"), response.get("rejection_reason")),
            )
            processed_order = _build_processed_order_from_broker_response(order, response)
            if processed_order is None:
                continue
            if _should_sync_portfolio_for_broker_response(
                status=status,
                sync_portfolio_on_fill=runtime.sync_portfolio_on_fill,
            ):
                fill_ts = response.get("fill_ts") or datetime.now(timezone.utc)
                _sync_portfolio_for_broker_response(
                    runtime=runtime,
                    order=order,
                    response=response,
                    fill_ts=fill_ts,
                )
        state.processed_orders.append(processed_order)


def _log_cycle_stream_summary(runtime: CycleStreamRuntime, state: CycleStreamState) -> None:
    """Log final order counters for one market-stream pipeline run."""
    counters = state.counters
    logger.info(
        "Cycle order summary run_id=%s cycle_id=%s orders_emitted=%s orders_rejected_locally=%s orders_validated=%s orders_submitted=%s broker_responses=%s",
        runtime.run_id,
        runtime.cycle_id,
        counters.orders_emitted,
        counters.orders_rejected_locally,
        counters.orders_validated,
        counters.orders_submitted,
        counters.broker_responses,
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
    """Run streaming market events through signal, risk, and broker stages.

    The pipeline keeps one producer, one strategy worker, one risk validator,
    and one broker submitter connected by queues. Each stage records the audit
    events it owns so order lifecycle state remains observable even when a later
    stage rejects, errors, or receives no broker fill.
    """
    event_queue: asyncio.Queue[MarketDataEvent | None] = asyncio.Queue()
    order_queue: asyncio.Queue[Mapping[str, object] | None] = asyncio.Queue()
    validated_queue: asyncio.Queue[Mapping[str, object] | None] = asyncio.Queue()
    runtime = CycleStreamRuntime(
        event_store=event_store,
        strategy=strategy,
        broker=broker,
        portfolio=portfolio,
        run_id=run_id,
        cycle_id=cycle_id,
        max_age_seconds=max_age_seconds,
        enforce_staleness=enforce_staleness,
        asset_class=asset_class,
        time_in_force=time_in_force,
        sync_portfolio_on_fill=sync_portfolio_on_fill,
        broker_type=broker_type,
        config=config,
        risk_manager=risk_manager,
    )
    state = _build_cycle_stream_state()

    await asyncio.gather(
        _produce_market_events(event_stream, event_queue),
        _generate_stream_orders(
            runtime=runtime,
            state=state,
            event_queue=event_queue,
            order_queue=order_queue,
        ),
        _validate_stream_orders(
            runtime=runtime,
            state=state,
            order_queue=order_queue,
            validated_queue=validated_queue,
        ),
        _submit_stream_orders(
            runtime=runtime,
            state=state,
            validated_queue=validated_queue,
        ),
    )
    _log_cycle_stream_summary(runtime, state)
    return state.processed_orders, _latest_stream_prices(state)


async def _event_stream_from_list(events: Sequence[MarketDataEvent]) -> AsyncIterator[MarketDataEvent]:
    """Adapt a synchronous event sequence to the streaming pipeline protocol."""
    for event in events:
        yield event


def _apply_event_filters(event_store: EventStore, config: Config) -> EventStore:
    """Wrap the event store so optional observability streams respect config.

    Core lifecycle, market-data, config, and metrics events are always allowed.
    Signal, indicator, order, fill, and portfolio events are included only when
    the corresponding logging flags are enabled.
    """
    return FilteredEventStore(
        event_store,
        allowed_event_types=_allowed_cycle_event_types(config),
    )


def _load_latest_order_events(event_store: EventStore) -> Sequence[Mapping[str, object]]:
    """Load latest local order state for risk-context open-order checks.

    Rows are read newest first and de-duplicated by `client_order_id` so risk
    managers see one current status per order rather than every historical
    lifecycle transition.
    """
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return []
    query = _latest_order_events_query()
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
    return _dedupe_latest_order_event_rows(rows or [])


def _load_halt_flag(event_store: EventStore) -> bool:
    """Read the operator halt flag used to block non-backtest trading."""
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
    readiness = assess_market_data_readiness(
        market_data_events,
        now=now,
        max_age_seconds=max_age_seconds,
    )
    if readiness.reason == "missing_market_data":
        logger.warning("Skipping trading due to missing market data")
        return readiness.should_skip
    if readiness.latest_ts is None or readiness.age_seconds is None:
        return readiness.should_skip
    logger.info(
        "Market data freshness latest_ts=%s age_seconds=%.2f max_age_seconds=%s stale=%s",
        readiness.latest_ts.isoformat(),
        readiness.age_seconds,
        readiness.max_age_seconds,
        readiness.is_stale,
    )
    return readiness.should_skip


def _load_recent_market_data(
    event_store: EventStore,
    config: Config,
    as_of_ts: datetime | None = None,
) -> Sequence[MarketDataEvent]:
    """Load the most recent stored bar for each configured symbol.

    Backtests pass `as_of_ts` to prevent looking into the future; live runs omit
    it and receive the latest persisted bar. Missing symbols are skipped so the
    caller can decide whether the remaining data is fresh enough to trade.
    """
    if not config.market_data_symbols:
        logger.warning("No symbols configured for market data lookup")
        return []

    asset_class = config.market_data_asset_class.lower()
    table = _market_data_event_table_name(asset_class)
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
                lookup = _build_recent_market_data_query(
                    table=table,
                    symbol=symbol,
                    timeframe=timeframe,
                    as_of_ts=as_of_ts,
                )
                cursor.execute(lookup.sql, list(lookup.params))
                row = cursor.fetchone()
                if row is None:
                    continue
                events.append(_row_to_market_event(asset_class, symbol.upper(), timeframe, row))
    else:
        logger.warning("Market data lookup skipped; unsupported connection type")
    logger.info("Loaded recent market data from event store count=%s", len(events))
    return events


def _log_startup_config(config: Config) -> None:
    """Log relevant configuration values for startup diagnostics."""
    masked = _startup_config_log_values(config)
    formatted = ", ".join(f"{key}={value}" for key, value in masked.items())
    logger.info("Startup config: %s", formatted)


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
    """Reject direct execution because cycles require injected dependencies.

    A cycle needs a concrete strategy and risk manager supplied by the caller.
    Wrapper scripts own those dependencies and call `run_cycle` explicitly.
    """
    raise SystemExit(
        "trader.cycle is a library module. "
        "Construct a Strategy and RiskManager in your own wrapper script and call run_cycle(...)."
    )


if __name__ == "__main__":
    main()
