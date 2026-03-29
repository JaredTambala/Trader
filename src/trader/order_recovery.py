"""Startup recovery and local maintenance helpers for order state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Mapping, Sequence
import uuid

from .broker import Broker
from .data import EventStore
from .symbols import canonicalize_symbol, configured_symbol_set, normalize_asset_class


logger = logging.getLogger(__name__)

_OPEN_STATUSES = {"submitted", "accepted", "partially_filled", "error"}


@dataclass
class RecoveryReport:
    """Summary of a startup recovery or maintenance run."""

    mode: str
    local_open_before: int = 0
    local_closed_missing: int = 0
    local_updated_from_broker: int = 0
    adopted_broker_open: int = 0
    broker_open_in_scope: int = 0
    broker_open_out_of_scope: int = 0
    local_clean_start_closed: int = 0
    actions: list[Mapping[str, object]] = field(default_factory=list)
    in_scope_broker_open: list[Mapping[str, object]] = field(default_factory=list)
    out_of_scope_broker_open: list[Mapping[str, object]] = field(default_factory=list)
    local_open: list[Mapping[str, object]] = field(default_factory=list)


def inspect_recovery_state(
    *,
    event_store: EventStore,
    broker: Broker,
    configured_symbols: Sequence[str],
    configured_asset_class: str,
) -> RecoveryReport:
    """Inspect broker/local open order state without mutating event-store state."""
    local_latest = _load_latest_order_events(event_store)
    local_open = [event for event in local_latest if str(event.get("status", "")).lower() in _OPEN_STATUSES]
    broker_orders = _list_broker_orders(broker)
    broker_open = [order for order in broker_orders if str(order.get("status", "")).lower() in _OPEN_STATUSES]
    in_scope, out_of_scope = _partition_broker_orders(
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
    """Run read-only broker reconciliation to repair local order history."""
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
        if broker_order is None:
            payload = _append_order_event(
                event_store,
                event,
                status="canceled",
                rejection_reason="reconciled_missing",
                event_ts=datetime.now(timezone.utc),
            )
            report.local_closed_missing += 1
            report.actions.append({"action": "close_missing_local_open", "client_order_id": client_order_id, "payload": payload})
            continue

        broker_status = str(broker_order.get("status", "")).lower()
        local_status = str(event.get("status", "")).lower()
        if broker_status != local_status or (
            not event.get("broker_order_id") and broker_order.get("broker_order_id")
        ):
            payload = _append_order_event(
                event_store,
                {**event, **broker_order},
                status=broker_status,
                rejection_reason=broker_order.get("rejection_reason"),
                event_ts=_parse_timestamp(broker_order.get("fill_ts"))
                or _parse_timestamp(broker_order.get("created_at"))
                or datetime.now(timezone.utc),
            )
            report.local_updated_from_broker += 1
            report.actions.append({"action": "update_local_from_broker", "client_order_id": client_order_id, "payload": payload})
            if broker_status in {"filled", "partially_filled"}:
                _append_fill_event(event_store, {**event, **broker_order})

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
        client_order_id = str(order.get("client_order_id", ""))
        if not client_order_id or client_order_id in local_by_client:
            continue
        payload = _append_order_event(
            event_store,
            {
                **order,
                "run_id": run_id,
                "session_id": run_id,
                "cycle_id": None,
            },
            status=str(order.get("status", "submitted")).lower(),
            rejection_reason="adopted_from_broker",
            event_ts=_parse_timestamp(order.get("created_at")) or datetime.now(timezone.utc),
        )
        report.adopted_broker_open += 1
        report.actions.append({"action": "adopt_broker_open", "client_order_id": client_order_id, "payload": payload})

    return report


def run_local_clean_start(
    *,
    event_store: EventStore,
    configured_symbols: Sequence[str],
    configured_asset_class: str,
    run_id: str | None = None,
) -> RecoveryReport:
    """Close local open orders in scope without touching broker state."""
    local_latest = _load_latest_order_events(event_store)
    local_open = [event for event in local_latest if str(event.get("status", "")).lower() in _OPEN_STATUSES]
    in_scope, out_of_scope = _partition_local_orders(
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
        payload = _append_order_event(
            event_store,
            {
                **event,
                "run_id": run_id or event.get("run_id"),
                "session_id": run_id or event.get("session_id") or event.get("run_id"),
                "cycle_id": None,
            },
            status="canceled",
            rejection_reason="local_clean_start",
            event_ts=datetime.now(timezone.utc),
        )
        report.local_clean_start_closed += 1
        report.actions.append(
            {
                "action": "local_clean_start_close",
                "client_order_id": event.get("client_order_id"),
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


def _partition_broker_orders(
    orders: Sequence[Mapping[str, object]],
    *,
    configured_symbols: Sequence[str],
    configured_asset_class: str,
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]]]:
    """Split broker orders into in-scope and out-of-scope groups."""
    normalized_asset_class = normalize_asset_class(configured_asset_class)
    allowed_symbols = configured_symbol_set(configured_symbols, asset_class=normalized_asset_class)
    in_scope: list[Mapping[str, object]] = []
    out_of_scope: list[Mapping[str, object]] = []
    for order in orders:
        symbol = canonicalize_symbol(str(order.get("symbol", "")), asset_class=str(order.get("asset_class", "")))
        asset_class = normalize_asset_class(str(order.get("asset_class", "")))
        normalized = {**order, "symbol": symbol, "asset_class": asset_class}
        if asset_class != normalized_asset_class:
            out_of_scope.append(normalized)
            continue
        if allowed_symbols and symbol not in allowed_symbols:
            out_of_scope.append(normalized)
            continue
        in_scope.append(normalized)
    return in_scope, out_of_scope


def _partition_local_orders(
    orders: Sequence[Mapping[str, object]],
    *,
    configured_symbols: Sequence[str],
    configured_asset_class: str,
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]]]:
    """Split local open orders into in-scope and out-of-scope groups."""
    normalized_asset_class = normalize_asset_class(configured_asset_class)
    allowed_symbols = configured_symbol_set(configured_symbols, asset_class=normalized_asset_class)
    in_scope: list[Mapping[str, object]] = []
    out_of_scope: list[Mapping[str, object]] = []
    for order in orders:
        symbol = canonicalize_symbol(str(order.get("symbol", "")), asset_class=normalized_asset_class)
        normalized = {**order, "symbol": symbol}
        if allowed_symbols and symbol not in allowed_symbols:
            out_of_scope.append(normalized)
            continue
        in_scope.append(normalized)
    return in_scope, out_of_scope


def _append_order_event(
    event_store: EventStore,
    order: Mapping[str, object],
    *,
    status: str,
    rejection_reason: str | None,
    event_ts: datetime | None = None,
) -> Mapping[str, object]:
    """Append a normalized order event to the event store."""
    payload = {
        "order_event_id": f"order_evt_{uuid.uuid4().hex}",
        "client_order_id": order.get("client_order_id"),
        "run_id": order.get("run_id"),
        "session_id": order.get("session_id") or order.get("run_id"),
        "cycle_id": order.get("cycle_id"),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "qty": order.get("qty"),
        "order_type": order.get("order_type", "market"),
        "status": status,
        "broker_order_id": order.get("broker_order_id"),
        "rejection_reason": rejection_reason,
        "created_at": event_ts or datetime.now(timezone.utc),
    }
    event_store.record_event("order_events", payload)
    return payload


def _append_fill_event(event_store: EventStore, order: Mapping[str, object]) -> None:
    """Append a fill event when broker reconciliation reveals a fill."""
    fill_qty = order.get("fill_qty")
    fill_price = order.get("fill_price")
    if fill_qty is None or fill_price is None:
        return
    event_store.record_event(
        "fill_events",
        {
            "client_order_id": order.get("client_order_id"),
            "run_id": order.get("run_id"),
            "session_id": order.get("session_id") or order.get("run_id"),
            "cycle_id": order.get("cycle_id"),
            "fill_ts": order.get("fill_ts") or datetime.now(timezone.utc),
            "fill_qty": float(fill_qty),
            "fill_price": float(fill_price),
        },
    )


def _parse_timestamp(value: object) -> datetime | None:
    """Parse timestamps from broker payloads into timezone-aware datetimes."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _load_latest_order_events(event_store: EventStore) -> list[Mapping[str, object]]:
    """Load latest order event per client_order_id."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        return []
    query = (
        "SELECT client_order_id, run_id, session_id, cycle_id, symbol, side, qty, order_type, "
        "status, broker_order_id, rejection_reason, created_at "
        "FROM order_events ORDER BY created_at DESC"
    )
    if hasattr(connection, "cursor"):
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
    else:
        rows = connection.execute(query).fetchall()
    seen: set[str] = set()
    latest: list[Mapping[str, object]] = []
    for row in rows or []:
        client_order_id = row[0]
        if not client_order_id or client_order_id in seen:
            continue
        seen.add(client_order_id)
        latest.append(
            {
                "client_order_id": row[0],
                "run_id": row[1],
                "session_id": row[2],
                "cycle_id": row[3],
                "symbol": row[4],
                "side": row[5],
                "qty": row[6],
                "order_type": row[7],
                "status": row[8],
                "broker_order_id": row[9],
                "rejection_reason": row[10],
                "created_at": row[11],
            }
        )
    return latest


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
