"""Production decision-cycle orchestration.

This module coordinates market-data ingestion, strategy order generation, risk
validation, broker submission, portfolio updates, metrics, and append-only audit
events for one trading or backtest decision timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from datetime import datetime, timezone
from typing import Mapping

from ..broker import Broker
from ..config import Config
from ..event_store import EventStore, build_event_store
from ..market_data import MarketDataSource
from ..portfolio import Portfolio
from ..strategies import Strategy
from ..risk import RiskManager
from ..strategy_metadata import resolve_strategy_id, resolve_strategy_type
from . import state as cycle_state
from .adapters import _apply_event_filters, _build_broker
from .cli import main
from .lifecycle import (
    CycleExecutionPlan,
    CycleIdentity,
    CycleResult,
    CycleWorkflowResult,
    _build_cycle_execution_plan,
    _build_cycle_identity,
    _build_cycle_run_session_outcome,
    _resolve_decision_ts,
    _should_halt_cycle,
)
from .pipeline import _run_market_data_pipeline_for_plan
from .portfolio_state import (
    _load_cycle_portfolio,
    _record_cycle_metrics_snapshot_if_enabled,
    _record_post_order_portfolio_snapshot,
)
from .recording import (
    _record_failed_cycle_finish,
    _record_halted_cycle_finish,
    _record_owned_run_session_finish,
    _record_owned_run_session_start,
    _record_successful_cycle_finish,
)


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
    if _should_halt_cycle(run_type=execution_plan.run_type, halted=cycle_state._load_halt_flag(event_store)):
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


if __name__ == "__main__":
    main()
