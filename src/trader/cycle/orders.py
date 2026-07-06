"""Pure order-intent and lifecycle payload helpers for decision cycles.

The cycle orchestrator persists order events and broker fills, but the shape of
those records is deterministic business logic. This module keeps that logic in a
small, side-effect-free boundary so it can be tested without event stores,
brokers, clocks, or runtime configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

from ..identifiers import deterministic_client_order_id


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


@dataclass(frozen=True)
class CycleBrokerResponseRecordingPlan:
    """Prepared lifecycle and optional fill records for one broker response."""

    order_event: CycleOrderEventPayload
    fill_event: CycleFillEventPayload | None
    missing_fill_evidence: bool = False


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


def build_broker_response_recording_plan(
    order: Mapping[str, object],
    response: Mapping[str, object],
    *,
    terminal_ts: datetime,
    order_event_id: str,
) -> CycleBrokerResponseRecordingPlan:
    """Build the order and fill records implied by one broker response.

    Args:
        order: Enriched order payload matched by `client_order_id`.
        response: Broker response for the order.
        terminal_ts: Timestamp selected by the shell for terminal ordering.
        order_event_id: Explicit event identifier generated by the shell.

    Returns:
        Immutable recording plan. Fill records are present only for filled or
        partially-filled responses with fill quantity and price evidence.
    """
    status = str(response.get("status", "submitted"))
    rejection_reason = response.get("rejection_reason")
    order_payload = order if rejection_reason is None else {**order, "rejection_reason": rejection_reason}
    order_event = build_order_lifecycle_event_payload(
        order_payload,
        status=status,
        broker_order_id=response.get("broker_order_id"),
        created_at=terminal_ts,
        order_event_id=order_event_id,
    )
    fill_event: CycleFillEventPayload | None = None
    missing_fill_evidence = False
    if status in {"filled", "partially_filled"}:
        fill_event = build_broker_fill_event_payload(
            order,
            response,
            fill_ts=terminal_ts,
        )
        missing_fill_evidence = fill_event is None
    return CycleBrokerResponseRecordingPlan(
        order_event=order_event,
        fill_event=fill_event,
        missing_fill_evidence=missing_fill_evidence,
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


def _normalize_event_ts(value: datetime) -> datetime:
    """Normalize event timestamps to timezone-aware UTC values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "CycleBrokerResponseRecordingPlan",
    "CycleFillEventPayload",
    "CycleOrderEventPayload",
    "CycleOrderIntent",
    "EnrichedCycleOrder",
    "build_broker_response_recording_plan",
    "build_broker_fill_event_payload",
    "build_enriched_cycle_order",
    "build_order_lifecycle_event_payload",
    "enrich_cycle_order_intent",
    "normalize_cycle_order_intent",
    "resolve_order_lifecycle_event_timestamp",
    "resolve_terminal_event_timestamp",
]
