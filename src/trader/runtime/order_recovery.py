"""Pure order-recovery value objects and payload builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Sequence

from ..symbols import canonicalize_symbol, configured_symbol_set, normalize_asset_class

__all__ = [
    "OPEN_STATUSES",
    "FillEventPayload",
    "LocalOrderRecoveryPlan",
    "OrderEventPayload",
    "OrderRecoveryQuery",
    "RecoveryReport",
    "build_fill_event_payload",
    "build_latest_order_events_query",
    "build_order_event_payload",
    "latest_order_events_from_rows",
    "parse_timestamp",
    "partition_broker_orders",
    "partition_local_orders",
    "plan_broker_open_adoption",
    "plan_local_clean_start_close",
    "plan_local_open_order_recovery",
]

OPEN_STATUSES = {"submitted", "accepted", "partially_filled", "error"}


@dataclass
class RecoveryReport:
    """Observable summary of startup reconciliation or local cleanup actions.

    Counts describe what was found locally and at the broker, while `actions`
    carries appended event payloads for audit. Broker-open lists are split by
    configured trading universe so operators can distinguish resumable in-scope
    orders from unsafe out-of-scope exposure.
    """

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


@dataclass(frozen=True)
class OrderEventPayload:
    """Immutable order-event payload prepared for event-store persistence."""

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
        """Return an event-store-compatible mapping for this payload."""
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
class FillEventPayload:
    """Immutable fill-event payload prepared for event-store persistence."""

    client_order_id: object | None
    run_id: object | None
    session_id: object | None
    cycle_id: object | None
    fill_ts: object
    fill_qty: float
    fill_price: float

    def to_record(self) -> dict[str, object]:
        """Return an event-store-compatible mapping for this payload."""
        return {
            "client_order_id": self.client_order_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "cycle_id": self.cycle_id,
            "fill_ts": self.fill_ts,
            "fill_qty": self.fill_qty,
            "fill_price": self.fill_price,
        }


@dataclass(frozen=True)
class LocalOrderRecoveryPlan:
    """Planned local recovery action for one open order."""

    action: str
    order: Mapping[str, object]
    status: str
    rejection_reason: object | None
    event_ts: datetime
    should_record_fill: bool = False


@dataclass(frozen=True)
class OrderRecoveryQuery:
    """SQL statement and parameters for order-recovery shell reads."""

    sql: str
    params: tuple[object, ...] = ()


def partition_broker_orders(
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


def partition_local_orders(
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


def build_order_event_payload(
    order: Mapping[str, object],
    *,
    status: str,
    rejection_reason: object | None,
    event_ts: datetime,
    order_event_id: str,
) -> OrderEventPayload:
    """Build a deterministic order-event payload from an order snapshot.

    Args:
        order: Local or broker order fields used as the source snapshot.
        status: Lifecycle status to assign to the emitted order event.
        rejection_reason: Reason associated with terminal or rejected states.
        event_ts: Explicit timestamp for the event.
        order_event_id: Explicit event identifier generated by the caller.

    Returns:
        An immutable payload value object. The input mapping is not mutated.
    """
    return OrderEventPayload(
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
        broker_order_id=order.get("broker_order_id"),
        rejection_reason=rejection_reason,
        created_at=event_ts,
    )


def build_fill_event_payload(
    order: Mapping[str, object],
    *,
    fallback_fill_ts: datetime,
) -> FillEventPayload | None:
    """Build a deterministic fill-event payload when fill fields are present.

    Args:
        order: Local or broker order fields used as the source snapshot.
        fallback_fill_ts: Timestamp to use when the order has no fill timestamp.

    Returns:
        An immutable fill payload, or `None` when the order has no fill quantity
        or fill price. The input mapping is not mutated.
    """
    fill_qty = order.get("fill_qty")
    fill_price = order.get("fill_price")
    if fill_qty is None or fill_price is None:
        return None
    return FillEventPayload(
        client_order_id=order.get("client_order_id"),
        run_id=order.get("run_id"),
        session_id=order.get("session_id") or order.get("run_id"),
        cycle_id=order.get("cycle_id"),
        fill_ts=order.get("fill_ts") or fallback_fill_ts,
        fill_qty=float(fill_qty),
        fill_price=float(fill_price),
    )


def plan_local_open_order_recovery(
    local_event: Mapping[str, object],
    broker_order: Mapping[str, object] | None,
    *,
    fallback_ts: datetime,
) -> LocalOrderRecoveryPlan | None:
    """Plan local recovery for one locally open order.

    Args:
        local_event: Latest local lifecycle event for the order.
        broker_order: Matching broker state, or `None` when missing.
        fallback_ts: Timestamp supplied by the shell when broker evidence does
            not carry a parseable event timestamp.

    Returns:
        A recovery plan, or `None` when the local order already matches broker
        state and no append-only event is needed.
    """
    if broker_order is None:
        return LocalOrderRecoveryPlan(
            action="close_missing_local_open",
            order=local_event,
            status="canceled",
            rejection_reason="reconciled_missing",
            event_ts=fallback_ts,
        )

    broker_status = str(broker_order.get("status", "")).lower()
    local_status = str(local_event.get("status", "")).lower()
    missing_broker_id = not local_event.get("broker_order_id") and bool(broker_order.get("broker_order_id"))
    if broker_status == local_status and not missing_broker_id:
        return None

    event_ts = (
        parse_timestamp(broker_order.get("fill_ts"))
        or parse_timestamp(broker_order.get("created_at"))
        or fallback_ts
    )
    return LocalOrderRecoveryPlan(
        action="update_local_from_broker",
        order={**local_event, **broker_order},
        status=broker_status,
        rejection_reason=broker_order.get("rejection_reason"),
        event_ts=event_ts,
        should_record_fill=broker_status in {"filled", "partially_filled"},
    )


def plan_broker_open_adoption(
    broker_order: Mapping[str, object],
    *,
    known_local_client_order_ids: set[str],
    run_id: str | None,
    fallback_ts: datetime,
) -> LocalOrderRecoveryPlan | None:
    """Plan adoption of one in-scope broker-open order absent from local state.

    Args:
        broker_order: Normalized in-scope broker order.
        known_local_client_order_ids: Client order IDs already present locally.
        run_id: Recovery run/session ID to attach to adopted orders.
        fallback_ts: Timestamp supplied by the shell when broker evidence lacks
            a parseable creation timestamp.

    Returns:
        A local event plan, or `None` when the broker order cannot or should not
        be adopted.
    """
    client_order_id = str(broker_order.get("client_order_id", ""))
    if not client_order_id or client_order_id in known_local_client_order_ids:
        return None
    return LocalOrderRecoveryPlan(
        action="adopt_broker_open",
        order={
            **broker_order,
            "run_id": run_id,
            "session_id": run_id,
            "cycle_id": None,
        },
        status=str(broker_order.get("status", "submitted")).lower(),
        rejection_reason="adopted_from_broker",
        event_ts=parse_timestamp(broker_order.get("created_at")) or fallback_ts,
    )


def plan_local_clean_start_close(
    local_event: Mapping[str, object],
    *,
    run_id: str | None,
    event_ts: datetime,
) -> LocalOrderRecoveryPlan:
    """Plan a local-only clean-start cancellation for one scoped order."""
    return LocalOrderRecoveryPlan(
        action="local_clean_start_close",
        order={
            **local_event,
            "run_id": run_id or local_event.get("run_id"),
            "session_id": run_id or local_event.get("session_id") or local_event.get("run_id"),
            "cycle_id": None,
        },
        status="canceled",
        rejection_reason="local_clean_start",
        event_ts=event_ts,
    )


def build_latest_order_events_query() -> OrderRecoveryQuery:
    """Build the newest-first order-event query used by recovery shells."""
    return OrderRecoveryQuery(
        sql=(
            "SELECT client_order_id, run_id, session_id, cycle_id, symbol, side, qty, order_type, "
            "status, broker_order_id, rejection_reason, created_at "
            "FROM order_events ORDER BY created_at DESC, order_event_id DESC"
        )
    )


def parse_timestamp(value: object) -> datetime | None:
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


def latest_order_events_from_rows(rows: Sequence[Sequence[object]]) -> list[Mapping[str, object]]:
    """Map newest-first order-event rows to latest events per client order id."""
    seen: set[object] = set()
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
