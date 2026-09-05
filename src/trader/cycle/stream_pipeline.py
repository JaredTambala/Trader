"""Async market-stream execution pipeline for decision cycles."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import AsyncIterator, Mapping, Sequence

from ..broker import Broker
from ..config import Config
from ..event_store import EventStore
from ..market_data import MarketDataEvent
from ..portfolio import Portfolio
from ..risk import RiskManager
from ..strategies import Strategy
from . import state as cycle_state
from .broker_state import _build_cycle_broker_response_plan
from .orders import _attach_order_metadata
from .portfolio_state import _sync_portfolio_for_broker_response
from .recording import _record_broker_responses, _record_order_events
from .risk import _build_cycle_risk_context, _evaluate_cycle_order_risk
from .stream import (
    CycleStreamRuntime,
    CycleStreamState,
    _build_cycle_stream_state,
    _latest_stream_prices,
    _plan_cycle_stream_market_event,
)


logger = logging.getLogger(__name__)


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
    if runtime.strategy.decision_scope == "universe_snapshot":
        await _generate_universe_snapshot_orders(
            runtime=runtime,
            state=state,
            event_queue=event_queue,
            order_queue=order_queue,
        )
        return
    if runtime.strategy.decision_scope != "per_symbol":
        raise ValueError(f"unsupported strategy decision scope: {runtime.strategy.decision_scope}")
    while True:
        event = await event_queue.get()
        if event is None:
            await order_queue.put(None)
            break
        plan = _plan_cycle_stream_market_event(
            event,
            enforce_staleness=runtime.enforce_staleness,
            now=datetime.now(timezone.utc),
            max_age_seconds=runtime.max_age_seconds,
        )
        if plan.should_skip:
            logger.warning("Skipping stale market data symbol=%s ts=%s", event.symbol, event.ts.isoformat())
            continue
        symbol = plan.symbol
        decision_ts = plan.decision_ts
        state.latest_prices[symbol] = (decision_ts, plan.close_price)
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
                price_lookup={symbol: plan.close_price},
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


async def _generate_universe_snapshot_orders(
    *,
    runtime: CycleStreamRuntime,
    state: CycleStreamState,
    event_queue: asyncio.Queue[MarketDataEvent | None],
    order_queue: asyncio.Queue[Mapping[str, object] | None],
) -> None:
    """Collect one complete same-time universe before invoking the strategy once."""
    plans = []
    while True:
        event = await event_queue.get()
        if event is None:
            break
        plan = _plan_cycle_stream_market_event(
            event,
            enforce_staleness=runtime.enforce_staleness,
            now=datetime.now(timezone.utc),
            max_age_seconds=runtime.max_age_seconds,
        )
        if plan.should_skip:
            raise RuntimeError(
                f"universe_snapshot contains stale market data for {plan.symbol} at {plan.decision_ts.isoformat()}"
            )
        plans.append(plan)
    expected = tuple(str(item).strip().upper() for item in runtime.config.market_data_symbols)
    actual = tuple(plan.symbol for plan in plans)
    if len(set(actual)) != len(actual):
        raise RuntimeError("universe_snapshot contains duplicate symbols")
    if set(actual) != set(expected) or len(actual) != len(expected):
        raise RuntimeError(
            f"universe_snapshot requires exactly the configured symbols: expected={list(expected)} actual={list(actual)}"
        )
    timestamps = {plan.decision_ts for plan in plans}
    if len(timestamps) != 1:
        raise RuntimeError("universe_snapshot market data is not aligned to one decision timestamp")
    decision_ts = timestamps.pop()
    price_lookup = {plan.symbol: plan.close_price for plan in plans}
    state.latest_prices.update(
        {plan.symbol: (decision_ts, plan.close_price) for plan in plans}
    )
    async for order in runtime.strategy.order_stream(
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
            price_lookup=price_lookup,
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
    await order_queue.put(None)


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
            open_orders=cycle_state._load_latest_order_events(runtime.event_store),
            latest_prices=state.latest_prices,
            order=order,
            run_id=runtime.run_id,
            cycle_id=runtime.cycle_id,
            halted=cycle_state._load_halt_flag(runtime.event_store),
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
            plan = _build_cycle_broker_response_plan(
                order,
                response,
                sync_portfolio_on_fill=runtime.sync_portfolio_on_fill,
                fallback_fill_ts=datetime.now(timezone.utc),
            )
            _log_order_status(
                f"broker_response status={plan.status}",
                order,
                run_id=runtime.run_id,
                cycle_id=runtime.cycle_id,
                extra="broker_order_id=%s reason=%s"
                % (response.get("broker_order_id"), response.get("rejection_reason")),
            )
            if plan.processed_order is None:
                continue
            processed_order = plan.processed_order
            if plan.should_sync_portfolio:
                _sync_portfolio_for_broker_response(
                    runtime=runtime,
                    order=order,
                    response=response,
                    fill_ts=plan.fill_ts,
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
    """Run streaming market events through signal, risk, and broker stages."""
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


__all__ = []
