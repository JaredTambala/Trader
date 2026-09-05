"""Runtime order recovery and local maintenance workflows.

Startup recovery reconciles locally persisted order lifecycle events with the
broker's current open-order state before live trading starts. Local clean-start
helpers intentionally avoid broker side effects and only append scoped local
events after an operator has handled external venue state.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Mapping, Sequence
import uuid

from ..broker import Broker
from ..event_store import EventStore
from .order_recovery import (
    OPEN_STATUSES,
    FillEventPayload,
    LocalOrderRecoveryPlan,
    OrderEventPayload,
    RecoveryReport,
    build_fill_event_payload,
    build_latest_order_events_query,
    build_order_event_payload,
    latest_order_events_from_rows,
    partition_broker_orders,
    partition_local_orders,
    plan_broker_open_adoption,
    plan_local_clean_start_close,
    plan_local_open_order_recovery,
)


logger = logging.getLogger(__name__)

__all__ = [
    "FillEventPayload",
    "LocalOrderRecoveryPlan",
    "OrderEventPayload",
    "RecoveryReport",
    "build_fill_event_payload",
    "build_order_event_payload",
    "inspect_recovery_state",
    "run_local_clean_start",
    "run_startup_recovery",
]


def inspect_recovery_state(
    *,
    event_store: EventStore,
    broker: Broker,
    configured_symbols: Sequence[str],
    configured_asset_class: str,
) -> RecoveryReport:
    """Compare local and broker open-order state without writing events.

    This report-only path is used by operators and tests to see what recovery
    would act on. It loads latest local order events, reads broker orders when
    supported, filters open statuses, and partitions broker orders by configured
    symbol/asset-class scope.
    """
    local_latest = _load_latest_order_events(event_store)
    local_open = [event for event in local_latest if str(event.get("status", "")).lower() in OPEN_STATUSES]
    broker_orders = _list_broker_orders(broker)
    broker_open = [order for order in broker_orders if str(order.get("status", "")).lower() in OPEN_STATUSES]
    in_scope, out_of_scope = partition_broker_orders(
        broker_open,
        configured_symbols=configured_symbols,
        configured_asset_class=configured_asset_class,
    )
    return RecoveryReport(
        mode="report",
        local_open_before=len(local_open),
        broker_open_in_scope=len(in_scope),
        broker_open_out_of_scope=len(out_of_scope),
        in_scope_broker_open=in_scope,
        out_of_scope_broker_open=out_of_scope,
        local_open=local_open,
    )


def run_startup_recovery(
    *,
    event_store: EventStore,
    broker: Broker,
    configured_symbols: Sequence[str],
    configured_asset_class: str,
    mode: str,
    run_id: str | None = None,
) -> RecoveryReport:
    """Reconcile startup order state and append only missing lifecycle events.

    Local open orders missing from the broker are closed as canceled, local
    orders with changed broker status receive a new lifecycle event, and
    in-scope broker-open orders missing locally are adopted. Out-of-scope broker
    opens always fail closed; `fail_closed` mode also rejects in-scope broker
    opens instead of adopting them.
    """
    normalized_mode = str(mode or "resume").strip().lower()
    if normalized_mode not in {"resume", "fail_closed"}:
        raise ValueError(f"Unsupported startup recovery mode: {mode}")

    report = inspect_recovery_state(
        event_store=event_store,
        broker=broker,
        configured_symbols=configured_symbols,
        configured_asset_class=configured_asset_class,
    )
    report.mode = normalized_mode

    broker_by_client = {
        str(order.get("client_order_id")): order
        for order in report.in_scope_broker_open + report.out_of_scope_broker_open
        if order.get("client_order_id")
    }
    local_by_client = {
        str(event.get("client_order_id")): event
        for event in _load_latest_order_events(event_store)
        if event.get("client_order_id")
    }

    for event in report.local_open:
        client_order_id = str(event.get("client_order_id", ""))
        broker_order = broker_by_client.get(client_order_id)
        if broker_order is None and event.get("broker_order_id"):
            broker_order = _get_broker_order_by_id(broker, str(event["broker_order_id"]))
        plan = plan_local_open_order_recovery(
            event,
            broker_order,
            fallback_ts=datetime.now(timezone.utc),
        )
        if plan is None:
            continue
        payload = _append_order_event(
            event_store,
            plan.order,
            status=plan.status,
            rejection_reason=plan.rejection_reason,
            event_ts=plan.event_ts,
        )
        if plan.action == "close_missing_local_open":
            report.local_closed_missing += 1
        elif plan.action == "update_local_from_broker":
            report.local_updated_from_broker += 1
        report.actions.append({"action": plan.action, "client_order_id": client_order_id, "payload": payload})
        if plan.should_record_fill:
            _append_fill_event(event_store, plan.order)

    if report.out_of_scope_broker_open:
        mismatch_text = ", ".join(
            "%s(asset_class=%s)"
            % (order.get("symbol"), order.get("asset_class"))
            for order in report.out_of_scope_broker_open
        )
        raise ValueError(f"Broker open orders outside configured universe: {mismatch_text}")

    if normalized_mode == "fail_closed" and report.in_scope_broker_open:
        raise ValueError(
            "Broker open orders exist in configured universe: "
            + ", ".join(str(order.get("client_order_id")) for order in report.in_scope_broker_open)
        )

    for order in report.in_scope_broker_open:
        plan = plan_broker_open_adoption(
            order,
            known_local_client_order_ids=set(local_by_client),
            run_id=run_id,
            fallback_ts=datetime.now(timezone.utc),
        )
        if plan is None:
            continue
        payload = _append_order_event(
            event_store,
            plan.order,
            status=plan.status,
            rejection_reason=plan.rejection_reason,
            event_ts=plan.event_ts,
        )
        report.adopted_broker_open += 1
        report.actions.append(
            {
                "action": plan.action,
                "client_order_id": plan.order.get("client_order_id"),
                "payload": payload,
            }
        )

    return report


def run_local_clean_start(
    *,
    event_store: EventStore,
    configured_symbols: Sequence[str],
    configured_asset_class: str,
    run_id: str | None = None,
) -> RecoveryReport:
    """Append local cancellations for scoped open orders without broker calls.

    This maintenance path deliberately does not contact or cancel broker-side
    orders. It is for resetting local event-store state after an operator has
    already handled venue state separately.
    """
    local_latest = _load_latest_order_events(event_store)
    local_open = [event for event in local_latest if str(event.get("status", "")).lower() in OPEN_STATUSES]
    in_scope, out_of_scope = partition_local_orders(
        local_open,
        configured_symbols=configured_symbols,
        configured_asset_class=configured_asset_class,
    )
    report = RecoveryReport(
        mode="clean_start",
        local_open_before=len(local_open),
        local_open=local_open,
        broker_open_in_scope=0,
        broker_open_out_of_scope=0,
        in_scope_broker_open=[],
        out_of_scope_broker_open=[],
    )
    for event in in_scope:
        plan = plan_local_clean_start_close(
            event,
            run_id=run_id,
            event_ts=datetime.now(timezone.utc),
        )
        payload = _append_order_event(
            event_store,
            plan.order,
            status=plan.status,
            rejection_reason=plan.rejection_reason,
            event_ts=plan.event_ts,
        )
        report.local_clean_start_closed += 1
        report.actions.append(
            {
                "action": plan.action,
                "client_order_id": plan.order.get("client_order_id"),
                "payload": payload,
            }
        )
    if out_of_scope:
        report.actions.append(
            {
                "action": "local_clean_start_skipped_out_of_scope",
                "count": len(out_of_scope),
            }
        )
    return report


def _append_order_event(
    event_store: EventStore,
    order: Mapping[str, object],
    *,
    status: str,
    rejection_reason: object | None,
    event_ts: datetime | None = None,
) -> Mapping[str, object]:
    """Append a normalized order event to the event store."""
    payload = build_order_event_payload(
        order,
        status=status,
        rejection_reason=rejection_reason,
        event_ts=event_ts or datetime.now(timezone.utc),
        order_event_id=f"order_evt_{uuid.uuid4().hex}",
    ).to_record()
    event_store.record_event("order_events", payload)
    return payload


def _append_fill_event(event_store: EventStore, order: Mapping[str, object]) -> None:
    """Append a fill event when broker reconciliation reveals a fill."""
    payload = build_fill_event_payload(order, fallback_fill_ts=datetime.now(timezone.utc))
    if payload is None:
        return
    event_store.record_event("fill_events", payload.to_record())


def _load_latest_order_events(event_store: EventStore) -> list[Mapping[str, object]]:
    """Load latest order event per client_order_id."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return []
    query = build_latest_order_events_query()
    if hasattr(connection, "cursor"):
        with connection.cursor() as cursor:
            cursor.execute(query.sql, query.params)
            rows = cursor.fetchall()
    else:
        rows = connection.execute(query.sql, query.params).fetchall()
    return latest_order_events_from_rows(rows or [])


def _list_broker_orders(broker: Broker) -> list[Mapping[str, object]]:
    """List broker orders using the broker adapter if supported."""
    lister = getattr(broker, "list_orders", None)
    if not callable(lister):
        return []
    return list(lister())


def _get_broker_order_by_id(broker: Broker, broker_order_id: str) -> Mapping[str, object] | None:
    """Fetch a broker order by id when supported."""
    getter = getattr(broker, "get_order_by_id", None)
    if not callable(getter):
        return None
    try:
        return getter(broker_order_id)
    except Exception as exc:  # pragma: no cover - external dependency
        logger.warning("Broker order lookup failed broker_order_id=%s: %s", broker_order_id, exc)
        return None
