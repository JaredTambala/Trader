"""Portfolio loading, synchronization, and snapshot helpers for cycles."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Mapping, Sequence

from ..broker import Broker
from ..config import Config
from ..event_store import EventStore
from ..market_data import MarketDataEvent
from ..portfolio import Portfolio, persist_portfolio_snapshot
from .broker_state import _build_portfolio_from_broker_payload
from .lifecycle import (
    CycleExecutionPlan,
    _build_post_order_portfolio_snapshot_plan,
    _resolve_cycle_snapshot_ts,
    _resolve_portfolio_asof_ts,
    _should_load_broker_portfolio,
)
from .market_data import _build_price_lookup
from .metrics import _resolve_metrics_price_lookup, build_metrics_snapshot_event
from .stream import CycleStreamRuntime


logger = logging.getLogger(__name__)


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
        persist_portfolio_snapshot(snapshot, event_store)
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
    persist_portfolio_snapshot(snapshot, event_store)
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
        persist_portfolio_snapshot(snapshot, event_store)
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
    persist_portfolio_snapshot(snapshot, event_store)
    logger.info(
        "Portfolio synced from broker positions=%s cash=%s reason=post_fill_sync",
        len(portfolio.positions),
        portfolio.cash_balance,
    )


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
        persist_portfolio_snapshot(snapshot, runtime.event_store)
        logger.info(
            "Portfolio snapshot recorded (internal fill) count=%s",
            len(snapshot.positions),
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


__all__ = [
    "_load_cycle_portfolio",
    "_record_cycle_metrics_snapshot_if_enabled",
    "_record_post_order_portfolio_snapshot",
    "_sync_portfolio_for_broker_response",
]
