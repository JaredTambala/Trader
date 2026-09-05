"""Market-data and order pipeline orchestration for decision cycles."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Sequence

from ..broker import Broker
from ..config import Config
from ..event_store import EventStore
from ..market_data import MarketDataEvent, MarketDataIngestor, MarketDataSource
from ..portfolio import Portfolio
from ..risk import RiskManager
from ..strategies import Strategy
from . import state as cycle_state
from .adapters import _build_market_data_source
from .lifecycle import (
    CycleExecutionPlan,
    _resolve_market_data_freshness_ts,
    _should_use_stream_ingestion,
)
from .market_data import CycleMarketDataPipelineResult
from .readiness import MarketDataReadiness, assess_market_data_readiness
from .stream_pipeline import (
    _event_stream_from_list,
    _event_stream_with_count,
    _run_market_event_stream_pipeline,
)


logger = logging.getLogger(__name__)


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

    market_data_events = cycle_state._load_recent_market_data(event_store, config, decision_ts)
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
        market_data_events = cycle_state._load_recent_market_data(event_store, config, decision_ts)
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
    readiness = assess_market_data_readiness(
        market_data_events,
        now=freshness_ts,
        max_age_seconds=config.market_data_max_age_seconds,
    )
    _log_market_data_readiness(readiness)
    if readiness.should_skip:
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


def _log_market_data_readiness(readiness: MarketDataReadiness) -> None:
    """Log market-data readiness while keeping readiness assessment pure."""
    if readiness.reason == "missing_market_data":
        logger.warning("Skipping trading due to missing market data")
        return
    if readiness.latest_ts is None or readiness.age_seconds is None:
        return
    logger.info(
        "Market data freshness latest_ts=%s age_seconds=%.2f max_age_seconds=%s stale=%s",
        readiness.latest_ts.isoformat(),
        readiness.age_seconds,
        readiness.max_age_seconds,
        readiness.is_stale,
    )


__all__ = []
