"""Production decision-cycle orchestration.

This module coordinates market-data ingestion, strategy order generation, risk
validation, broker submission, portfolio updates, metrics, and append-only audit
events for one trading or backtest decision timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import uuid
import json
from typing import AsyncIterator, Literal, Mapping, Sequence

from ..broker import AlpacaPaperBroker, Broker, InternalPaperBroker, NoOpBroker
from ..config import Config
from ..event_store import EventStore, FilteredEventStore, build_event_store
from ..identifiers import (
    deterministic_client_order_id,
    deterministic_cycle_id,
    deterministic_run_session_id,
)
from ..market_data import (
    MarketDataEvent,
    MarketDataIngestor,
    MarketDataSource,
    NoOpMarketDataSource,
    CryptoBarEvent,
    StockBarEvent,
)
from ..market_data.alpaca import AlpacaMarketDataSource
from ..portfolio import Portfolio, Position
from ..strategies import Strategy
from ..risk import (
    RiskContext,
    RiskManager,
    RiskPipeline,
)
from ..strategy_metadata import resolve_strategy_id, resolve_strategy_type
from ..symbols import BrokerPositionView, find_unmatched_positions, normalize_broker_positions


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CycleResult:
    """Terminal identity and status for one completed decision cycle.

    Attributes:
        run_id: Session/run identifier that groups one or more cycles.
        cycle_id: Deterministic identifier for this decision timestamp.
        status: Terminal cycle status such as `success`, `failed`, or `halted`.
    """

    run_id: str
    cycle_id: str
    status: str


@dataclass(frozen=True)
class CycleOrderIntent:
    """Normalized strategy order intent before cycle metadata enrichment."""

    source: Mapping[str, object]
    symbol: str
    side: str
    qty: float


@dataclass(frozen=True)
class EnrichedCycleOrder:
    """Strategy order intent enriched with cycle, pricing, and venue metadata."""

    source: Mapping[str, object]
    symbol: str
    run_id: str
    session_id: str
    cycle_id: str
    client_order_id: object
    price: object | None
    created_at: object
    asset_class: str
    time_in_force: object

    def to_record(self) -> dict[str, object]:
        """Return a mapping suitable for risk checks and broker submission."""
        return {
            **self.source,
            "symbol": self.symbol,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "cycle_id": self.cycle_id,
            "client_order_id": self.client_order_id,
            "price": self.price,
            "created_at": self.created_at,
            "asset_class": self.asset_class,
            "time_in_force": self.time_in_force,
        }


@dataclass(frozen=True)
class MarketDataReadiness:
    """Pure assessment of whether market data is usable for a trading decision."""

    should_skip: bool
    max_age_seconds: int
    latest_ts: datetime | None
    age_seconds: float | None
    is_stale: bool
    reason: str | None


@dataclass(frozen=True)
class MarketDataEventFreshness:
    """Pure freshness assessment for one streaming market-data event."""

    ts: datetime
    age_seconds: float
    max_age_seconds: int
    is_stale: bool


@dataclass(frozen=True)
class MetricsSnapshotPayload:
    """Computed portfolio metrics payload for a cycle snapshot."""

    equity: float
    cash: float
    net_exposure: float
    gross_exposure: float
    asset_class: str
    symbols: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        """Return the JSON-compatible metrics payload."""
        return {
            "equity": self.equity,
            "cash": self.cash,
            "net_exposure": self.net_exposure,
            "gross_exposure": self.gross_exposure,
            "asset_class": self.asset_class,
            "symbols": list(self.symbols),
        }


@dataclass(frozen=True)
class MetricsSnapshotEvent:
    """Event-store record for one computed metrics snapshot."""

    ts: datetime
    run_id: str
    session_id: str
    cycle_id: str | None
    payload: MetricsSnapshotPayload

    def to_record(self) -> dict[str, object]:
        """Return an event-store-compatible metrics snapshot record."""
        return {
            "ts": self.ts,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "cycle_id": self.cycle_id,
            "payload": json.dumps(self.payload.to_payload()),
        }


@dataclass(frozen=True)
class CycleExecutionPlan:
    """Pure execution decisions derived from cycle configuration."""

    run_type: str
    broker_kind: str
    stream_mode: bool
    sync_portfolio_on_fill: bool
    portfolio_source: str | None


@dataclass(frozen=True)
class CycleIdentity:
    """Deterministic run and cycle identity for one decision timestamp."""

    run_id: str
    cycle_id: str
    owns_run_session: bool


@dataclass(frozen=True)
class CycleRunSessionOutcome:
    """Terminal run-session status derived from the cycle result."""

    status: str
    error_message: str | None


@dataclass(frozen=True)
class CycleWorkflowResult:
    """Cycle result paired with the run-session outcome it implies."""

    cycle_result: CycleResult
    run_session_outcome: CycleRunSessionOutcome


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


PortfolioSnapshotAction = Literal[
    "none",
    "skip_alpaca_synced",
    "persist_broker_fill_snapshot",
    "persist_order_intent_snapshot",
]


@dataclass(frozen=True)
class CyclePortfolioSnapshotPlan:
    """Decision describing how processed orders should affect portfolio snapshots."""

    action: PortfolioSnapshotAction


@dataclass(frozen=True)
class CycleMarketDataPipelineResult:
    """Orders, bars, and prices produced by cycle market-data processing."""

    processed_orders: Sequence[Mapping[str, object]]
    market_data_events: Sequence[MarketDataEvent]
    price_lookup: Mapping[str, float]


@dataclass(frozen=True)
class RecentMarketDataQuery:
    """SQL and parameters for loading one symbol's latest stored market bar."""

    sql: str
    params: tuple[object, ...]


@dataclass(frozen=True)
class CycleRiskRejectionLog:
    """Rejected order plus the risk manager that rejected it."""

    order: Mapping[str, object]
    manager_name: str


@dataclass(frozen=True)
class CycleRiskEvaluationResult:
    """Approved and rejected order payloads from cycle risk validation."""

    approved_orders: tuple[Mapping[str, object], ...]
    rejected_orders: tuple[Mapping[str, object], ...]
    rejection_logs: tuple[CycleRiskRejectionLog, ...]


@dataclass(frozen=True)
class CycleStreamRuntime:
    """Immutable dependencies shared by market-stream pipeline stages."""

    event_store: EventStore
    strategy: Strategy
    broker: Broker
    portfolio: Portfolio
    run_id: str
    cycle_id: str
    max_age_seconds: int
    enforce_staleness: bool
    asset_class: str
    time_in_force: str
    sync_portfolio_on_fill: bool
    broker_type: str
    config: Config
    risk_manager: RiskManager


@dataclass
class CycleStreamCounters:
    """Mutable counters for one market-stream pipeline execution."""

    orders_emitted: int = 0
    orders_rejected_locally: int = 0
    orders_validated: int = 0
    orders_submitted: int = 0
    broker_responses: int = 0


@dataclass
class CycleStreamState:
    """Mutable state accumulated while market-stream pipeline stages run."""

    processed_orders: list[Mapping[str, object]]
    latest_prices: dict[str, tuple[datetime, float]]
    counters: CycleStreamCounters


@dataclass(frozen=True)
class CycleOrderEventPayload:
    """Immutable order lifecycle event prepared by the decision cycle."""

    order_event_id: str
    client_order_id: object | None
    run_id: object | None
    session_id: object | None
    cycle_id: object | None
    symbol: object | None
    side: object | None
    qty: object | None
    order_type: object
    status: str
    broker_order_id: object | None
    rejection_reason: object | None
    created_at: datetime

    def to_record(self) -> dict[str, object]:
        """Return an event-store-compatible order event mapping."""
        return {
            "order_event_id": self.order_event_id,
            "client_order_id": self.client_order_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "cycle_id": self.cycle_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "order_type": self.order_type,
            "status": self.status,
            "broker_order_id": self.broker_order_id,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class CycleFillEventPayload:
    """Immutable fill event prepared from a broker response."""

    client_order_id: object | None
    run_id: object | None
    session_id: object | None
    cycle_id: object | None
    fill_ts: datetime
    fill_qty: float
    raw_fill_price: object | None
    fill_price: float
    slippage_amount: object | None
    fee_amount: object | None

    def to_record(self) -> dict[str, object]:
        """Return an event-store-compatible fill event mapping."""
        return {
            "client_order_id": self.client_order_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "cycle_id": self.cycle_id,
            "fill_ts": self.fill_ts,
            "fill_qty": self.fill_qty,
            "raw_fill_price": self.raw_fill_price,
            "fill_price": self.fill_price,
            "slippage_amount": self.slippage_amount,
            "fee_amount": self.fee_amount,
        }


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


def _resolve_cycle_run_type(mode: str, run_type: str | None) -> str:
    """Return the effective run type for cycle lifecycle records."""
    return (run_type or ("backtest" if mode.lower() == "backtest" else "trading")).lower()


def _build_cycle_execution_plan(
    *,
    mode: str,
    broker_type: str,
    portfolio_source: str | None,
    run_type: str | None,
) -> CycleExecutionPlan:
    """Build deterministic cycle execution decisions from explicit inputs."""
    broker_kind = (broker_type or "noop").lower()
    effective_run_type = _resolve_cycle_run_type(mode, run_type)
    return CycleExecutionPlan(
        run_type=effective_run_type,
        broker_kind=broker_kind,
        stream_mode=mode.lower() != "backtest",
        sync_portfolio_on_fill=broker_kind in {"alpaca", "internal"},
        portfolio_source=portfolio_source,
    )


def _build_cycle_identity(
    *,
    strategy_id: str,
    decision_ts: datetime,
    run_type: str,
    started_at: datetime,
    run_id: str | None,
) -> CycleIdentity:
    """Build deterministic run/cycle identity without touching storage."""
    owns_run_session = run_id is None
    effective_run_id = (
        deterministic_run_session_id(run_type, started_at)
        if owns_run_session
        else run_id
    )
    return CycleIdentity(
        run_id=effective_run_id,
        cycle_id=deterministic_cycle_id(strategy_id, decision_ts),
        owns_run_session=owns_run_session,
    )


def _build_cycle_run_session_outcome(
    status: str,
    error_message: str | None = None,
) -> CycleRunSessionOutcome:
    """Build a terminal run-session outcome value."""
    return CycleRunSessionOutcome(status=status, error_message=error_message)


def _should_load_broker_portfolio(plan: CycleExecutionPlan) -> bool:
    """Return whether broker state should be authoritative for this cycle."""
    return (
        plan.run_type != "backtest"
        and plan.broker_kind == "alpaca"
        and plan.portfolio_source == "alpaca"
    )


def _resolve_portfolio_asof_ts(mode: str, decision_ts: datetime) -> datetime | None:
    """Return the portfolio read timestamp used by backtests."""
    return decision_ts if mode.lower() == "backtest" else None


def _resolve_cycle_snapshot_ts(
    *,
    mode: str,
    decision_ts: datetime,
    current_ts: datetime,
) -> datetime:
    """Return the timestamp to use for cycle snapshots in this mode."""
    return decision_ts if mode.lower() == "backtest" else current_ts


def _build_post_order_portfolio_snapshot_plan(
    *,
    processed_orders: Sequence[Mapping[str, object]],
    sync_portfolio_on_fill: bool,
    broker_kind: str,
) -> CyclePortfolioSnapshotPlan:
    """Decide how portfolio state should be persisted after submitted orders."""
    if not processed_orders:
        return CyclePortfolioSnapshotPlan(action="none")
    if sync_portfolio_on_fill and broker_kind == "alpaca":
        return CyclePortfolioSnapshotPlan(action="skip_alpaca_synced")
    if sync_portfolio_on_fill and broker_kind == "internal":
        return CyclePortfolioSnapshotPlan(action="persist_broker_fill_snapshot")
    return CyclePortfolioSnapshotPlan(action="persist_order_intent_snapshot")


def _should_use_stream_ingestion(*, ingest_market_data: bool, stream_mode: bool) -> bool:
    """Return whether the cycle should use streaming market-data ingestion."""
    return ingest_market_data and stream_mode


def _resolve_market_data_freshness_ts(
    *,
    mode: str,
    decision_ts: datetime,
    current_ts: datetime,
) -> datetime:
    """Return the timestamp used for cycle market-data freshness checks."""
    return decision_ts if mode.lower() == "backtest" else current_ts


def _empty_market_data_pipeline_result() -> CycleMarketDataPipelineResult:
    """Return an empty market-data processing result."""
    return CycleMarketDataPipelineResult(
        processed_orders=(),
        market_data_events=(),
        price_lookup={},
    )


def _record_owned_run_session_start(
    *,
    event_store: EventStore,
    owns_run_session: bool,
    run_id: str,
    run_type: str,
    started_at: datetime,
    strategy_id: str,
    config_snapshot: Mapping[str, object] | None,
    mode: str,
    symbols: Sequence[str],
    timeframe: str,
) -> None:
    """Record run-session start when this cycle owns the session lifecycle."""
    if not owns_run_session:
        return
    event_store.record_run_session_start(
        run_id=run_id,
        run_type=run_type,
        started_at=started_at,
        strategy_id=strategy_id,
        config_snapshot=config_snapshot,
        mode=mode,
        symbols=symbols,
        timeframe=timeframe,
    )


def _record_owned_run_session_finish(
    *,
    event_store: EventStore,
    owns_run_session: bool,
    run_id: str,
    run_type: str,
    started_at: datetime,
    outcome: CycleRunSessionOutcome,
    strategy_id: str,
    mode: str,
    symbols: Sequence[str],
    timeframe: str,
) -> None:
    """Record run-session finish when this cycle owns the session lifecycle."""
    if not owns_run_session:
        return
    event_store.record_run_session_finish(
        run_id=run_id,
        run_type=run_type,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        status=outcome.status,
        error_message=outcome.error_message,
        strategy_id=strategy_id,
        mode=mode,
        symbols=symbols,
        timeframe=timeframe,
    )


def _resolve_decision_ts(
    decision_ts: datetime | None,
    *,
    current_ts: datetime,
) -> datetime:
    """Return the cycle decision timestamp normalized to timezone-aware UTC."""
    resolved = decision_ts or current_ts
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    return resolved


def _should_halt_cycle(*, run_type: str, halted: bool) -> bool:
    """Return whether the global halt flag should stop this cycle."""
    return run_type != "backtest" and halted


def _record_terminal_cycle_finish(
    *,
    event_store: EventStore,
    run_id: str,
    cycle_id: str,
    strategy_id: str,
    mode: str,
    decision_ts: datetime,
    started_at: datetime,
    status: str,
    error_message: str | None,
) -> None:
    """Record terminal completion state for one decision cycle."""
    event_store.record_cycle_finish(
        run_id=run_id,
        cycle_id=cycle_id,
        strategy_id=strategy_id,
        mode=mode,
        decision_ts=decision_ts,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        status=status,
        error_message=error_message,
    )


def _record_successful_cycle_finish(
    *,
    event_store: EventStore,
    run_id: str,
    cycle_id: str,
    strategy_id: str,
    mode: str,
    decision_ts: datetime,
    started_at: datetime,
) -> None:
    """Record successful completion for one decision cycle."""
    _record_terminal_cycle_finish(
        event_store=event_store,
        run_id=run_id,
        cycle_id=cycle_id,
        strategy_id=strategy_id,
        mode=mode,
        decision_ts=decision_ts,
        started_at=started_at,
        status="success",
        error_message=None,
    )


def _record_halted_cycle_finish(
    *,
    event_store: EventStore,
    run_id: str,
    cycle_id: str,
    strategy_id: str,
    mode: str,
    decision_ts: datetime,
    started_at: datetime,
) -> None:
    """Record global-halt completion for one decision cycle."""
    _record_terminal_cycle_finish(
        event_store=event_store,
        run_id=run_id,
        cycle_id=cycle_id,
        strategy_id=strategy_id,
        mode=mode,
        decision_ts=decision_ts,
        started_at=started_at,
        status="halted",
        error_message="global_halt",
    )


def _record_failed_cycle_finish(
    *,
    event_store: EventStore,
    run_id: str,
    cycle_id: str,
    strategy_id: str,
    mode: str,
    decision_ts: datetime,
    started_at: datetime,
    error_message: str,
) -> None:
    """Record failed completion for one decision cycle."""
    _record_terminal_cycle_finish(
        event_store=event_store,
        run_id=run_id,
        cycle_id=cycle_id,
        strategy_id=strategy_id,
        mode=mode,
        decision_ts=decision_ts,
        started_at=started_at,
        status="failed",
        error_message=error_message,
    )


def _load_cycle_portfolio(
    *,
    broker: Broker,
    event_store: EventStore,
    run_id: str,
    cycle_id: str,
    decision_ts: datetime,
    config: Config,
    execution_plan: CycleExecutionPlan,
    portfolio: Portfolio | None,
) -> Portfolio:
    """Load the portfolio used for strategy decisions in one cycle."""
    if _should_load_broker_portfolio(execution_plan):
        loaded = _load_portfolio_from_broker(
            broker=broker,
            event_store=event_store,
            run_id=run_id,
            cycle_id=cycle_id,
            decision_ts=decision_ts,
            config=config,
        )
        logger.info(
            "Broker refresh reason=cycle_portfolio_source_alpaca positions=%s cash=%s",
            len(loaded.positions),
            loaded.cash_balance,
        )
        return loaded
    if portfolio is None:
        portfolio_asof = _resolve_portfolio_asof_ts(config.mode, decision_ts)
        loaded = Portfolio.from_event_store(event_store, asof_ts=portfolio_asof)
        logger.info("Portfolio loaded positions=%s", len(loaded.positions))
        return loaded
    logger.info("Portfolio override positions=%s", len(portfolio.positions))
    return portfolio


def _record_post_order_portfolio_snapshot(
    *,
    event_store: EventStore,
    portfolio: Portfolio,
    processed_orders: Sequence[Mapping[str, object]],
    sync_portfolio_on_fill: bool,
    broker_kind: str,
    mode: str,
    decision_ts: datetime,
    run_id: str,
    cycle_id: str,
    price_lookup: Mapping[str, float],
) -> None:
    """Persist portfolio state after processed orders when the broker requires it."""
    snapshot_plan = _build_post_order_portfolio_snapshot_plan(
        processed_orders=processed_orders,
        sync_portfolio_on_fill=sync_portfolio_on_fill,
        broker_kind=broker_kind,
    )
    if snapshot_plan.action == "none":
        return
    if snapshot_plan.action == "skip_alpaca_synced":
        logger.info("Portfolio snapshot skipped; alpaca fills sync portfolio state")
        return

    snapshot_ts = _resolve_cycle_snapshot_ts(
        mode=mode,
        decision_ts=decision_ts,
        current_ts=datetime.now(timezone.utc),
    )
    if snapshot_plan.action == "persist_broker_fill_snapshot":
        snapshot = portfolio.snapshot(
            asof_ts=snapshot_ts,
            run_id=run_id,
            cycle_id=cycle_id,
            session_id=run_id,
        )
        snapshot.persist(event_store)
        logger.info("Portfolio snapshot recorded (broker fills) count=%s", len(snapshot.positions))
        return

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


def _resolve_metrics_price_lookup(
    *,
    price_lookup: Mapping[str, float],
    market_data_events: Sequence[MarketDataEvent],
) -> Mapping[str, float]:
    """Return the price lookup used for metrics snapshots."""
    if price_lookup:
        return price_lookup
    if market_data_events:
        return _build_price_lookup(market_data_events)
    return {}


def _record_cycle_metrics_snapshot_if_enabled(
    *,
    event_store: EventStore,
    portfolio: Portfolio,
    price_lookup: Mapping[str, float],
    market_data_events: Sequence[MarketDataEvent],
    metrics_enabled: bool,
    mode: str,
    decision_ts: datetime,
    run_id: str,
    cycle_id: str,
    asset_class: str,
    symbols: Sequence[str],
) -> Mapping[str, float]:
    """Record metrics snapshot when enabled and return the resolved prices."""
    resolved_price_lookup = _resolve_metrics_price_lookup(
        price_lookup=price_lookup,
        market_data_events=market_data_events,
    )
    if not metrics_enabled or not resolved_price_lookup:
        return resolved_price_lookup

    snapshot_ts = _resolve_cycle_snapshot_ts(
        mode=mode,
        decision_ts=decision_ts,
        current_ts=datetime.now(timezone.utc),
    )
    _record_metrics_snapshot(
        event_store=event_store,
        portfolio=portfolio,
        price_lookup=resolved_price_lookup,
        asof_ts=snapshot_ts,
        run_id=run_id,
        cycle_id=cycle_id,
        asset_class=asset_class,
        symbols=symbols,
    )
    return resolved_price_lookup


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


def _build_price_lookup(events: Sequence[MarketDataEvent]) -> Mapping[str, float]:
    """Return the latest close price per symbol from fetched market events."""
    latest_prices: dict[str, tuple[datetime, float]] = {}
    for event in events:
        timestamp = _normalize_timestamp(event.ts)
        current = latest_prices.get(event.symbol)
        if current is None or timestamp > current[0]:
            latest_prices[event.symbol] = (timestamp, float(event.close))
    return {symbol: price for symbol, (_, price) in latest_prices.items()}


def normalize_cycle_order_intent(order: Mapping[str, object]) -> CycleOrderIntent:
    """Normalize symbol, side, and quantity from a strategy order intent.

    Args:
        order: Raw strategy order intent.

    Returns:
        Immutable normalized order intent. The original mapping is preserved as
        source data and is not mutated.
    """
    return CycleOrderIntent(
        source=order,
        symbol=str(order.get("symbol", "")).strip().upper(),
        side=str(order.get("side", "")).lower().strip(),
        qty=float(order.get("qty", 0.0) or 0.0),
    )


def enrich_cycle_order_intent(
    intent: CycleOrderIntent,
    *,
    run_id: str,
    cycle_id: str,
    created_at: datetime,
    price_lookup: Mapping[str, float],
    asset_class: str,
    time_in_force: str,
) -> EnrichedCycleOrder:
    """Attach deterministic cycle metadata to a normalized order intent.

    Args:
        intent: Normalized order intent.
        run_id: Runtime session identifier.
        cycle_id: Decision-cycle identifier.
        created_at: Cycle decision timestamp used when the intent has no
            explicit `created_at`.
        price_lookup: Latest prices keyed by normalized symbol.
        asset_class: Venue asset class attached for broker submission.
        time_in_force: Default broker time-in-force.

    Returns:
        Immutable enriched order. Use `to_record()` for the legacy mapping
        shape consumed by risk managers and brokers.
    """
    client_order_id = intent.source.get("client_order_id") or deterministic_client_order_id(
        cycle_id,
        intent.symbol,
        intent.side,
        intent.qty,
    )
    return EnrichedCycleOrder(
        source=intent.source,
        symbol=intent.symbol,
        run_id=run_id,
        session_id=run_id,
        cycle_id=cycle_id,
        client_order_id=client_order_id,
        price=price_lookup.get(intent.symbol),
        created_at=intent.source.get("created_at") or created_at,
        asset_class=asset_class,
        time_in_force=intent.source.get("time_in_force", time_in_force),
    )


def build_enriched_cycle_order(
    order: Mapping[str, object],
    *,
    run_id: str,
    cycle_id: str,
    created_at: datetime,
    price_lookup: Mapping[str, float],
    asset_class: str,
    time_in_force: str,
) -> EnrichedCycleOrder:
    """Normalize and enrich one strategy order intent without side effects."""
    return enrich_cycle_order_intent(
        normalize_cycle_order_intent(order),
        run_id=run_id,
        cycle_id=cycle_id,
        created_at=created_at,
        price_lookup=price_lookup,
        asset_class=asset_class,
        time_in_force=time_in_force,
    )


def _attach_order_metadata(
    orders: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    cycle_id: str,
    created_at: datetime,
    price_lookup: Mapping[str, float],
    asset_class: str,
    time_in_force: str,
) -> Sequence[Mapping[str, object]]:
    """Attach cycle identity, deterministic IDs, prices, and venue metadata.

    Strategy orders are intentionally small intents. Before risk and broker
    stages they are enriched with traceability fields, the latest known price,
    asset class, and time-in-force so downstream code can persist and execute
    them without consulting global config again.
    """
    enriched: list[Mapping[str, object]] = []
    for order in orders:
        enriched.append(
            build_enriched_cycle_order(
                order,
                run_id=run_id,
                cycle_id=cycle_id,
                created_at=created_at,
                price_lookup=price_lookup,
                asset_class=asset_class,
                time_in_force=time_in_force,
            ).to_record()
        )
    return enriched


def resolve_order_lifecycle_event_timestamp(
    order: Mapping[str, object],
    *,
    status: str,
    fallback_ts: datetime,
    event_ts: datetime | None = None,
) -> datetime:
    """Choose a deterministic lifecycle timestamp for a cycle order event.

    Args:
        order: Enriched order payload with optional `created_at`.
        status: Lifecycle status being persisted.
        fallback_ts: Explicit timestamp supplied by the shell when the order
            does not carry a datetime `created_at`.
        event_ts: Optional explicit timestamp that takes precedence.

    Returns:
        Timestamp for the lifecycle event. Created, validated, submitted, and
        rejected events receive stable microsecond ordering from `created_at`.
    """
    if event_ts is not None:
        return event_ts
    base_ts = order.get("created_at")
    if isinstance(base_ts, datetime):
        status_offsets = {
            "created": 0,
            "validated": 1,
            "submitted": 2,
            "rejected": 2,
        }
        return base_ts + timedelta(microseconds=status_offsets.get(status, 0))
    return fallback_ts


def build_order_lifecycle_event_payload(
    order: Mapping[str, object],
    *,
    status: str,
    broker_order_id: object | None,
    created_at: datetime,
    order_event_id: str,
) -> CycleOrderEventPayload:
    """Build a deterministic cycle order lifecycle payload.

    Args:
        order: Enriched order payload produced by the cycle.
        status: Lifecycle status being persisted.
        broker_order_id: Optional broker-side order identifier.
        created_at: Timestamp selected for this lifecycle event.
        order_event_id: Explicit event identifier generated by the shell.

    Returns:
        Immutable payload value object. The input mapping is not mutated.
    """
    return CycleOrderEventPayload(
        order_event_id=order_event_id,
        client_order_id=order.get("client_order_id"),
        run_id=order.get("run_id"),
        session_id=order.get("session_id") or order.get("run_id"),
        cycle_id=order.get("cycle_id"),
        symbol=order.get("symbol"),
        side=order.get("side"),
        qty=order.get("qty"),
        order_type=order.get("order_type", "market"),
        status=status,
        broker_order_id=broker_order_id,
        rejection_reason=order.get("rejection_reason"),
        created_at=created_at,
    )


def build_broker_fill_event_payload(
    order: Mapping[str, object],
    response: Mapping[str, object],
    *,
    fill_ts: datetime,
) -> CycleFillEventPayload | None:
    """Build a deterministic fill event payload from a broker response.

    Args:
        order: Enriched order payload matched by `client_order_id`.
        response: Broker response for the order.
        fill_ts: Resolved fill timestamp for event-store ordering.

    Returns:
        Immutable fill payload, or `None` when the resolved quantity or price
        is `None`. Missing response keys fall back to the original order, while
        explicit response `None` values are treated as missing evidence.
    """
    fill_qty = response.get("fill_qty", order.get("qty"))
    fill_price = response.get("fill_price", order.get("price"))
    if fill_qty is None or fill_price is None:
        return None
    return CycleFillEventPayload(
        client_order_id=response.get("client_order_id"),
        run_id=order.get("run_id"),
        session_id=order.get("session_id") or order.get("run_id"),
        cycle_id=order.get("cycle_id"),
        fill_ts=fill_ts,
        fill_qty=float(fill_qty),
        raw_fill_price=response.get("raw_fill_price"),
        fill_price=float(fill_price),
        slippage_amount=response.get("slippage_amount"),
        fee_amount=response.get("fee_amount"),
    )


def resolve_terminal_event_timestamp(
    *,
    proposed_ts: object | None,
    latest_order_ts: datetime | None,
    fallback_ts: datetime,
) -> datetime:
    """Choose a deterministic terminal timestamp for broker response events.

    Args:
        proposed_ts: Broker-supplied terminal timestamp, when available.
        latest_order_ts: Latest local lifecycle timestamp for the order.
        fallback_ts: Explicit fallback timestamp supplied by the shell when the
            broker response has no datetime timestamp.

    Returns:
        A timezone-aware timestamp that preserves broker time when it sorts
        after local lifecycle rows, otherwise one microsecond after the latest
        local lifecycle timestamp.
    """
    candidate = (
        _normalize_event_ts(proposed_ts)
        if isinstance(proposed_ts, datetime)
        else _normalize_event_ts(fallback_ts)
    )
    latest = _normalize_event_ts(latest_order_ts) if latest_order_ts is not None else None
    if latest is None or candidate > latest:
        return candidate
    return latest + timedelta(microseconds=1)


def _record_order_events(
    event_store: EventStore,
    orders: Sequence[Mapping[str, object]],
    *,
    status: str,
    broker_order_id: str | None = None,
    event_ts: datetime | None = None,
) -> None:
    """Append local order lifecycle events with stable timestamp ordering.

    When an explicit timestamp is not supplied, created/validated/submitted
    events receive microsecond offsets from the order creation time. That keeps
    lifecycle queries deterministic even when all statuses are produced inside
    the same decision cycle.
    """
    for order in orders:
        timestamp = resolve_order_lifecycle_event_timestamp(
            order,
            status=status,
            fallback_ts=datetime.now(timezone.utc),
            event_ts=event_ts,
        )
        payload = build_order_lifecycle_event_payload(
            order,
            status=status,
            broker_order_id=broker_order_id,
            created_at=timestamp,
            order_event_id=f"order_evt_{uuid.uuid4().hex}",
        )
        event_store.record_event(
            "order_events",
            payload.to_record(),
        )


def _record_broker_responses(
    event_store: EventStore,
    orders: Sequence[Mapping[str, object]],
    responses: Sequence[Mapping[str, object]],
) -> None:
    """Append terminal broker responses and fill events for submitted orders.

    Broker responses are matched back to enriched order payloads by
    `client_order_id`. Terminal order events are recorded first; fill events are
    written only when the broker supplied both quantity and price so accounting
    never fabricates execution evidence.
    """
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
        resolved_fill_ts = _resolve_terminal_event_ts(
            event_store,
            client_order_id=str(client_order_id) if client_order_id is not None else None,
            proposed_ts=response.get("fill_ts"),
        )
        _record_order_events(
            event_store,
            [order_payload],
            status=status,
            broker_order_id=broker_order_id,
            event_ts=resolved_fill_ts,
        )
        if status in {"filled", "partially_filled"}:
            fill_payload = build_broker_fill_event_payload(
                order,
                response,
                fill_ts=resolved_fill_ts,
            )
            if fill_payload is None:
                logger.warning(
                    "Fill event missing price/qty client_order_id=%s",
                    client_order_id,
                )
                continue
            event_store.record_event("fill_events", fill_payload.to_record())


def _resolve_terminal_event_ts(
    event_store: EventStore,
    *,
    client_order_id: str | None,
    proposed_ts: object | None,
) -> datetime:
    """Choose a terminal event timestamp that sorts after local lifecycle rows.

    Brokers may return fill timestamps equal to or earlier than locally recorded
    submitted events. This helper preserves provider time when safe and nudges
    it forward by one microsecond only when needed to maintain append ordering.
    """
    latest_order_ts = _latest_order_event_ts(event_store, client_order_id)
    return resolve_terminal_event_timestamp(
        proposed_ts=proposed_ts,
        latest_order_ts=latest_order_ts,
        fallback_ts=datetime.now(timezone.utc),
    )


def _latest_order_event_ts(
    event_store: EventStore,
    client_order_id: str | None,
) -> datetime | None:
    """Return the newest local lifecycle timestamp for one client order ID.

    The lookup supports in-memory test stores, DuckDB-style connections, and
    Postgres-style connections because timestamp ordering is used by both unit
    tests and production broker reconciliation.
    """
    if not client_order_id:
        return None
    events = getattr(event_store, "events", None)
    if isinstance(events, dict):
        latest: datetime | None = None
        for event in events.get("order_events", []):
            if event.get("client_order_id") != client_order_id:
                continue
            created_at = event.get("created_at")
            if not isinstance(created_at, datetime):
                continue
            created_at = _normalize_event_ts(created_at)
            latest = created_at if latest is None or created_at > latest else latest
        return latest

    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return None
    placeholder = "?" if connection.__class__.__module__.startswith("duckdb") else "%s"
    query = (
        "SELECT created_at FROM order_events "
        f"WHERE client_order_id = {placeholder} "
        "ORDER BY created_at DESC LIMIT 1"
    )
    try:
        if hasattr(connection, "cursor"):
            with connection.cursor() as cursor:
                cursor.execute(query, [client_order_id])
                row = cursor.fetchone()
        else:
            row = connection.execute(query, [client_order_id]).fetchone()
    except Exception:
        return None
    if not row or row[0] is None:
        return None
    if isinstance(row[0], datetime):
        return _normalize_event_ts(row[0])
    return None


def _normalize_event_ts(value: datetime) -> datetime:
    """Normalize event timestamps to timezone-aware UTC values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _build_stream_risk_price_lookup(
    latest_prices: Mapping[str, tuple[datetime, float]],
    order: Mapping[str, object],
) -> Mapping[str, float]:
    """Build the risk price lookup from stream prices and order price evidence."""
    price_lookup = {symbol: price for symbol, (_, price) in latest_prices.items()}
    symbol = str(order.get("symbol", "")).strip().upper()
    order_price = order.get("price")
    if symbol and order_price is not None:
        price_lookup[symbol] = float(order_price)
    return price_lookup


def _resolve_order_decision_ts(
    order: Mapping[str, object],
    fallback_ts: datetime,
) -> datetime:
    """Return the datetime risk managers should use for an order decision."""
    created_at = order.get("created_at")
    if isinstance(created_at, datetime):
        return created_at
    return fallback_ts


def _build_cycle_risk_context(
    *,
    positions: Mapping[str, Position],
    open_orders: Sequence[Mapping[str, object]],
    latest_prices: Mapping[str, tuple[datetime, float]],
    order: Mapping[str, object],
    run_id: str,
    cycle_id: str,
    halted: bool,
    fallback_ts: datetime,
) -> RiskContext:
    """Build a risk context from explicit cycle state without storage access."""
    return RiskContext(
        positions=positions,
        open_orders=open_orders,
        price_lookup=_build_stream_risk_price_lookup(latest_prices, order),
        run_id=run_id,
        cycle_id=cycle_id,
        decision_ts=_resolve_order_decision_ts(order, fallback_ts),
        halted=halted,
    )


def _evaluate_cycle_order_risk(
    *,
    order: Mapping[str, object],
    context: RiskContext,
    risk_manager: RiskManager,
) -> CycleRiskEvaluationResult:
    """Evaluate one enriched order through the configured risk manager chain."""
    approved_orders: Sequence[Mapping[str, object]] = [order]
    rejected_orders: list[Mapping[str, object]] = []
    rejection_logs: list[CycleRiskRejectionLog] = []
    for manager in _iter_risk_managers(risk_manager):
        approved_orders, rejected = manager.evaluate(approved_orders, context)
        if rejected:
            for rejected_order in rejected:
                rejection_logs.append(
                    CycleRiskRejectionLog(
                        order=rejected_order,
                        manager_name=manager.__class__.__name__,
                    )
                )
            rejected_orders.extend(rejected)
        if not approved_orders:
            break
    return CycleRiskEvaluationResult(
        approved_orders=tuple(approved_orders),
        rejected_orders=tuple(rejected_orders),
        rejection_logs=tuple(rejection_logs),
    )


def _resolve_broker_response_status(response: Mapping[str, object]) -> str:
    """Return the normalized broker response status for cycle decisions."""
    return str(response.get("status", "submitted"))


def _should_sync_portfolio_for_broker_response(
    *,
    status: str,
    sync_portfolio_on_fill: bool,
) -> bool:
    """Return whether a broker response should trigger portfolio synchronization."""
    return sync_portfolio_on_fill and status in {"filled", "partially_filled"}


def _build_processed_order_from_broker_response(
    order: Mapping[str, object],
    response: Mapping[str, object],
) -> Mapping[str, object] | None:
    """Build the processed-order evidence carried forward after broker response."""
    status = _resolve_broker_response_status(response)
    if status in {"rejected", "canceled", "expired", "error"}:
        return None
    processed_order = order
    fill_qty = response.get("fill_qty")
    fill_price = response.get("fill_price")
    if fill_qty is not None:
        processed_order = {**processed_order, "qty": float(fill_qty)}
    if fill_price is not None:
        processed_order = {**processed_order, "price": float(fill_price)}
    return processed_order


def _build_cycle_stream_state() -> CycleStreamState:
    """Create empty mutable state for one market-stream pipeline run."""
    return CycleStreamState(
        processed_orders=[],
        latest_prices={},
        counters=CycleStreamCounters(),
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


def _sync_portfolio_for_broker_response(
    *,
    runtime: CycleStreamRuntime,
    order: Mapping[str, object],
    response: Mapping[str, object],
    fill_ts: object,
) -> None:
    """Apply broker-fill portfolio side effects for supported broker types."""
    if runtime.broker_type == "alpaca":
        _sync_portfolio_from_broker(
            event_store=runtime.event_store,
            broker=runtime.broker,
            portfolio=runtime.portfolio,
            run_id=runtime.run_id,
            cycle_id=runtime.cycle_id,
            asof_ts=fill_ts,
            config=runtime.config,
        )
    elif runtime.broker_type == "internal":
        _apply_fill_to_portfolio(
            portfolio=runtime.portfolio,
            order=order,
            response=response,
        )
        snapshot = runtime.portfolio.snapshot(
            asof_ts=fill_ts,
            run_id=runtime.run_id,
            cycle_id=runtime.cycle_id,
            session_id=runtime.run_id,
        )
        snapshot.persist(runtime.event_store)
        logger.info(
            "Portfolio snapshot recorded (internal fill) count=%s",
            len(snapshot.positions),
        )


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


def _latest_stream_prices(state: CycleStreamState) -> Mapping[str, float]:
    """Return latest stream prices in the legacy mapping shape."""
    return {symbol: price for symbol, (_, price) in state.latest_prices.items()}


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


def _latest_order_events_query() -> str:
    """Return the query used to load latest order lifecycle rows."""
    return (
        "SELECT client_order_id, run_id, cycle_id, symbol, side, qty, order_type, "
        "status, broker_order_id, created_at "
        "FROM order_events ORDER BY created_at DESC, order_event_id DESC"
    )


def _latest_order_event_row_to_record(row: Sequence[object]) -> Mapping[str, object]:
    """Convert one order-event row into a risk-context record."""
    return {
        "client_order_id": row[0],
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


def _dedupe_latest_order_event_rows(
    rows: Sequence[Sequence[object]],
) -> tuple[Mapping[str, object], ...]:
    """Return one newest order-event record per client order ID."""
    seen: set[str] = set()
    latest: list[Mapping[str, object]] = []
    for row in rows:
        client_order_id = row[0]
        if not client_order_id:
            continue
        client_order_key = str(client_order_id)
        if client_order_key in seen:
            continue
        seen.add(client_order_key)
        latest.append(_latest_order_event_row_to_record(row))
    return tuple(latest)


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


def assess_market_data_readiness(
    market_data_events: Sequence[MarketDataEvent],
    *,
    now: datetime,
    max_age_seconds: int,
) -> MarketDataReadiness:
    """Assess market-data availability and freshness without side effects.

    Args:
        market_data_events: Market-data events available to the cycle.
        now: Timestamp used for staleness comparison.
        max_age_seconds: Maximum allowed age in seconds.

    Returns:
        Immutable readiness result describing whether trading should be skipped.

    Raises:
        ValueError: If `max_age_seconds` is negative.
    """
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    if not market_data_events:
        return MarketDataReadiness(
            should_skip=True,
            max_age_seconds=max_age_seconds,
            latest_ts=None,
            age_seconds=None,
            is_stale=False,
            reason="missing_market_data",
        )
    normalized_now = _normalize_timestamp(now)
    latest_ts = max(_normalize_timestamp(event.ts) for event in market_data_events)
    age_seconds = (normalized_now - latest_ts).total_seconds()
    is_stale = age_seconds > max_age_seconds
    return MarketDataReadiness(
        should_skip=is_stale,
        max_age_seconds=max_age_seconds,
        latest_ts=latest_ts,
        age_seconds=age_seconds,
        is_stale=is_stale,
        reason="stale_market_data" if is_stale else None,
    )


def _is_event_stale(event: MarketDataEvent, now: datetime, max_age_seconds: int) -> bool:
    """Return whether one market-data event is older than the allowed window."""
    return assess_market_data_event_freshness(
        event,
        now=now,
        max_age_seconds=max_age_seconds,
    ).is_stale


def assess_market_data_event_freshness(
    event: MarketDataEvent,
    *,
    now: datetime,
    max_age_seconds: int,
) -> MarketDataEventFreshness:
    """Assess freshness for one market-data event without side effects.

    Args:
        event: Market-data event being considered by streaming mode.
        now: Timestamp used for staleness comparison.
        max_age_seconds: Maximum allowed age in seconds.

    Returns:
        Immutable freshness result with normalized timestamp and age.

    Raises:
        ValueError: If `max_age_seconds` is negative.
    """
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    ts = _normalize_timestamp(event.ts)
    age_seconds = (_normalize_timestamp(now) - ts).total_seconds()
    is_stale = age_seconds > max_age_seconds
    return MarketDataEventFreshness(
        ts=ts,
        age_seconds=age_seconds,
        max_age_seconds=max_age_seconds,
        is_stale=is_stale,
    )


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


def _market_data_event_table_name(asset_class: str) -> str:
    """Return the persisted market-data table for an asset class."""
    return "crypto_bar_events" if asset_class.lower() in {"crypto", "cryptocurrency"} else "stock_bar_events"


def _build_recent_market_data_query(
    *,
    table: str,
    symbol: str,
    timeframe: str,
    as_of_ts: datetime | None,
) -> RecentMarketDataQuery:
    """Build a latest-bar lookup query for one symbol and optional upper bound."""
    where_clause = "WHERE symbol = %s AND COALESCE(timeframe, '1Min') = %s"
    params: tuple[object, ...] = (symbol.upper(), timeframe)
    if as_of_ts is not None:
        where_clause = f"{where_clause} AND ts <= %s"
        params = (*params, as_of_ts)
    sql = f"""
            SELECT ts, ingested_at, open, high, low, close, volume, trade_count, vwap, source
            FROM {table}
            {where_clause}
            ORDER BY ts DESC
            LIMIT 1
        """
    return RecentMarketDataQuery(sql=sql, params=params)


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


def _row_to_market_event(
    asset_class: str,
    symbol: str,
    timeframe: str,
    row: Sequence[object],
) -> MarketDataEvent:
    """Convert a stored stock/crypto bar row into the matching event object."""
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
    """Apply processed orders to portfolio state and persist a snapshot.

    This path is used when order intents are the best available local evidence.
    Price lookup comes from current market data unless the caller supplies a
    broker/fill-derived lookup.
    """
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
    """Apply one internal-broker fill to in-memory portfolio accounting."""
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
                "fee_amount": response.get("fee_amount"),
            }
        ],
        price_lookup=price_lookup,
    )


def _coerce_broker_cash(account: object) -> float:
    """Return a numeric cash balance from a broker account payload."""
    cash_raw = account.get("cash", 0.0) if isinstance(account, Mapping) else 0.0
    return float(cash_raw) if cash_raw is not None else 0.0


def _broker_position_views_to_positions(
    positions: Sequence[BrokerPositionView],
) -> dict[str, Position]:
    """Convert normalized broker position views into runtime positions."""
    return {
        position.symbol: Position(
            symbol=position.symbol,
            qty=position.qty,
            avg_price=position.avg_entry_price,
        )
        for position in positions
    }


def _build_portfolio_from_broker_payload(
    *,
    account: object,
    positions_raw: Sequence[Mapping[str, object]],
    config: Config,
) -> Portfolio:
    """Build a validated runtime portfolio from broker account and position payloads."""
    normalized_positions = normalize_broker_positions(positions_raw)
    _validate_broker_positions(normalized_positions, config)
    return Portfolio(
        positions=_broker_position_views_to_positions(normalized_positions),
        cash_balance=_coerce_broker_cash(account),
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
    """Refresh portfolio state from broker account/positions before a cycle.

    Live Alpaca mode treats broker state as authoritative when configured. The
    positions are normalized, checked against the configured universe, persisted
    as a snapshot, and returned as the portfolio used for strategy decisions.
    """
    get_account = getattr(broker, "get_account", None)
    get_positions = getattr(broker, "get_positions", None)
    if not callable(get_account) or not callable(get_positions):
        logger.warning("Broker portfolio load skipped; broker lacks account/position access")
        return Portfolio.from_event_store(event_store)

    try:
        account = get_account()
        positions_raw = get_positions() or []
        portfolio = _build_portfolio_from_broker_payload(
            account=account,
            positions_raw=positions_raw,
            config=config,
        )
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
    """Refresh and persist broker-authoritative portfolio state after a fill."""
    get_account = getattr(broker, "get_account", None)
    get_positions = getattr(broker, "get_positions", None)
    if not callable(get_account) or not callable(get_positions):
        logger.warning("Portfolio sync skipped; broker lacks account/position access")
        return

    logger.info("Broker refresh reason=post_fill_sync run_id=%s cycle_id=%s", run_id, cycle_id)
    account = get_account()
    positions_raw = get_positions() or []
    broker_portfolio = _build_portfolio_from_broker_payload(
        account=account,
        positions_raw=positions_raw,
        config=config,
    )
    portfolio.positions = dict(broker_portfolio.positions)
    portfolio.cash_balance = broker_portfolio.cash_balance
    snapshot = portfolio.snapshot(
        asof_ts=asof_ts,
        run_id=run_id,
        cycle_id=cycle_id,
        session_id=run_id,
    )
    snapshot.persist(event_store)
    logger.info(
        "Portfolio synced from broker positions=%s cash=%s reason=post_fill_sync",
        len(portfolio.positions),
        portfolio.cash_balance,
    )


def _validate_broker_positions(positions, config: Config) -> None:
    """Fail closed when broker positions are outside the configured universe."""
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
    """Persist point-in-time equity, cash, and exposure metrics.

    Metrics are stored as JSON so dashboards can evolve without schema changes.
    Positions without current prices are excluded from exposure calculations
    instead of carrying stale valuations silently.
    """
    event = build_metrics_snapshot_event(
        positions=portfolio.positions,
        cash_balance=portfolio.cash_balance,
        price_lookup=price_lookup,
        asof_ts=asof_ts,
        run_id=run_id,
        cycle_id=cycle_id,
        asset_class=asset_class,
        symbols=symbols,
    )
    event_store.record_event(
        "metrics_snapshots",
        event.to_record(),
    )


def build_metrics_snapshot_payload(
    *,
    positions: Mapping[str, Position],
    cash_balance: float,
    price_lookup: Mapping[str, float],
    asset_class: str,
    symbols: Sequence[str],
) -> MetricsSnapshotPayload:
    """Compute portfolio equity and exposure metrics without side effects.

    Args:
        positions: Current positions keyed by symbol.
        cash_balance: Current portfolio cash balance.
        price_lookup: Current prices keyed by symbol.
        asset_class: Configured asset class for the cycle.
        symbols: Configured trading symbols for the cycle.

    Returns:
        Immutable metrics payload. Positions without a current price are
        excluded from exposure and equity calculations.
    """
    equity = cash_balance
    net = 0.0
    gross = 0.0
    for position in positions.values():
        price = price_lookup.get(position.symbol)
        if price is None:
            continue
        notional = position.qty * price
        equity += notional
        net += notional
        gross += abs(notional)
    return MetricsSnapshotPayload(
        equity=equity,
        cash=cash_balance,
        net_exposure=net,
        gross_exposure=gross,
        asset_class=asset_class,
        symbols=tuple(symbols),
    )


def build_metrics_snapshot_event(
    *,
    positions: Mapping[str, Position],
    cash_balance: float,
    price_lookup: Mapping[str, float],
    asof_ts: datetime,
    run_id: str,
    cycle_id: str | None,
    asset_class: str,
    symbols: Sequence[str],
) -> MetricsSnapshotEvent:
    """Build a metrics snapshot event from explicit portfolio inputs."""
    return MetricsSnapshotEvent(
        ts=asof_ts,
        run_id=run_id,
        session_id=run_id,
        cycle_id=cycle_id,
        payload=build_metrics_snapshot_payload(
            positions=positions,
            cash_balance=cash_balance,
            price_lookup=price_lookup,
            asset_class=asset_class,
            symbols=symbols,
        ),
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
