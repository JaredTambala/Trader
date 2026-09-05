"""Event-store recording helpers for decision cycles.

This module is an explicit imperative-shell boundary: helpers here append cycle,
order, broker, and fill evidence to the configured event store. Payload shaping
stays delegated to pure value builders in sibling modules.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Mapping, Sequence
import uuid

from ..event_store import EventStore
from .lifecycle import CycleRunSessionOutcome
from .orders import (
    _normalize_event_ts,
    build_broker_response_recording_plan,
    build_order_lifecycle_event_payload,
    resolve_order_lifecycle_event_timestamp,
    resolve_terminal_event_timestamp,
)


logger = logging.getLogger(__name__)


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
        resolved_fill_ts = _resolve_terminal_event_ts(
            event_store,
            client_order_id=str(client_order_id) if client_order_id is not None else None,
            proposed_ts=response.get("fill_ts"),
        )
        plan = build_broker_response_recording_plan(
            order,
            response,
            terminal_ts=resolved_fill_ts,
            order_event_id=f"order_evt_{uuid.uuid4().hex}",
        )
        event_store.record_event("order_events", plan.order_event.to_record())
        if plan.missing_fill_evidence:
            logger.warning(
                "Fill event missing price/qty client_order_id=%s",
                client_order_id,
            )
        if plan.fill_event is not None:
            event_store.record_event("fill_events", plan.fill_event.to_record())


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


__all__ = [
    "_record_broker_responses",
    "_record_failed_cycle_finish",
    "_record_halted_cycle_finish",
    "_record_order_events",
    "_record_owned_run_session_finish",
    "_record_owned_run_session_start",
    "_record_successful_cycle_finish",
]
