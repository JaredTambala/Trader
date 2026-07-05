"""Pure Alpaca broker value objects and mapping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from ..identifiers import deterministic_client_order_id
from ..symbols import canonicalize_symbol, normalize_asset_class
from .helpers import coerce_float as _coerce_float


ALPACA_STATUS_MAP = {
    "new": "submitted",
    "pending_new": "submitted",
    "accepted": "accepted",
    "accepted_for_bidding": "accepted",
    "partially_filled": "partially_filled",
    "filled": "filled",
    "done_for_day": "filled",
    "canceled": "canceled",
    "pending_cancel": "canceled",
    "expired": "expired",
    "rejected": "rejected",
    "replaced": "submitted",
    "pending_replace": "submitted",
    "held": "error",
    "suspended": "error",
    "stopped": "error",
}
"""Provider status values mapped to the local order lifecycle vocabulary."""

ALREADY_SUBMITTED_STATUSES = {"submitted", "accepted", "partially_filled", "filled"}
"""Local statuses that represent an already-submitted order."""

OPEN_ORDER_STATUSES = {"submitted", "accepted", "partially_filled", "error"}
"""Local statuses that still require broker reconciliation."""


@dataclass(frozen=True)
class AlpacaReconciliationOrderEvent:
    """Immutable order event prepared by Alpaca order reconciliation."""

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
    created_at: object

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
class AlpacaReconciliationFillEvent:
    """Immutable fill event prepared by Alpaca order reconciliation."""

    client_order_id: object | None
    run_id: object | None
    session_id: object | None
    cycle_id: object | None
    fill_ts: object
    fill_qty: float
    raw_fill_price: float
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
class AlpacaSubmissionErrorResponse:
    """Immutable broker response for a failed Alpaca submission attempt."""

    client_order_id: object | None
    rejection_reason: object | None

    def to_record(self) -> dict[str, object]:
        """Return a broker-contract-compatible error response mapping."""
        return {
            "client_order_id": self.client_order_id,
            "status": "error",
            "broker_order_id": None,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class AlpacaOrderRequestFields:
    """Provider-neutral fields needed to construct an Alpaca order request."""

    symbol: str
    qty: float
    side: str
    time_in_force: str
    order_type: str
    client_order_id: str
    limit_price: object | None

    def to_fallback_mapping(self) -> dict[str, object]:
        """Return the dict request shape used when alpaca-py classes are absent."""
        return {
            "symbol": self.symbol,
            "qty": self.qty,
            "side": self.side,
            "time_in_force": self.time_in_force,
            "type": self.order_type,
            "client_order_id": self.client_order_id,
            "limit_price": self.limit_price,
        }


def build_alpaca_reconciliation_order_event(
    local_event: Mapping[str, object],
    *,
    status: str,
    order_event_id: str,
    created_at: object,
    broker_order_id: object | None = None,
    rejection_reason: object | None = None,
) -> AlpacaReconciliationOrderEvent:
    """Build a deterministic order event for Alpaca reconciliation."""
    return AlpacaReconciliationOrderEvent(
        order_event_id=order_event_id,
        client_order_id=local_event.get("client_order_id"),
        run_id=local_event.get("run_id"),
        session_id=local_event.get("session_id") or local_event.get("run_id"),
        cycle_id=local_event.get("cycle_id"),
        symbol=local_event.get("symbol"),
        side=local_event.get("side"),
        qty=local_event.get("qty"),
        order_type=local_event.get("order_type", "market"),
        status=status,
        broker_order_id=broker_order_id,
        rejection_reason=rejection_reason,
        created_at=created_at,
    )


def build_alpaca_reconciliation_fill_event(
    local_event: Mapping[str, object],
    broker_order: Mapping[str, object],
    *,
    fill_ts: object,
) -> AlpacaReconciliationFillEvent | None:
    """Build a deterministic fill event for Alpaca reconciliation."""
    fill_qty = broker_order.get("fill_qty")
    fill_price = broker_order.get("fill_price")
    if fill_qty is None or fill_price is None:
        return None
    coerced_price = _coerce_float(fill_price)
    return AlpacaReconciliationFillEvent(
        client_order_id=local_event.get("client_order_id"),
        run_id=local_event.get("run_id"),
        session_id=local_event.get("session_id") or local_event.get("run_id"),
        cycle_id=local_event.get("cycle_id"),
        fill_ts=fill_ts,
        fill_qty=_coerce_float(fill_qty),
        raw_fill_price=coerced_price,
        fill_price=coerced_price,
        slippage_amount=None,
        fee_amount=None,
    )


def build_alpaca_submission_error_response(
    *,
    client_order_id: object | None,
    error: object,
) -> AlpacaSubmissionErrorResponse:
    """Build a deterministic error response for a failed Alpaca submission."""
    return AlpacaSubmissionErrorResponse(
        client_order_id=client_order_id,
        rejection_reason=str(error),
    )


def normalize_alpaca_order_request_fields(order: Mapping[str, object]) -> AlpacaOrderRequestFields:
    """Normalize canonical order fields before provider request construction."""
    symbol = str(order.get("symbol", "")).strip().upper()
    side = str(order.get("side", "")).lower().strip()
    qty = _coerce_float(order.get("qty", 0.0))
    time_in_force = str(order.get("time_in_force", "day")).lower()
    asset_class = str(order.get("asset_class", "")).lower()
    if asset_class in {"crypto", "cryptocurrency"} and "/" in symbol:
        symbol = symbol.replace("/", "")
    if asset_class in {"crypto", "cryptocurrency"} and time_in_force in {"day", "daytime"}:
        time_in_force = "gtc"
    order_type = str(order.get("order_type", "market")).lower()
    return AlpacaOrderRequestFields(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=time_in_force,
        order_type=order_type,
        client_order_id=str(order.get("client_order_id", "")),
        limit_price=order.get("limit_price") or order.get("price"),
    )


def ensure_alpaca_client_order_id(order: Mapping[str, object]) -> Mapping[str, object]:
    """Return an order mapping carrying a stable Alpaca client order ID."""
    if order.get("client_order_id"):
        return order
    cycle_id = str(order.get("cycle_id", ""))
    symbol = str(order.get("symbol", "")).strip().upper()
    side = str(order.get("side", "")).lower().strip()
    qty = _coerce_float(order.get("qty", 0.0))
    client_order_id = deterministic_client_order_id(cycle_id, symbol, side, qty)
    return {**order, "client_order_id": client_order_id}


def map_alpaca_status(status: str) -> str:
    """Map provider status strings to the local order lifecycle vocabulary."""
    return ALPACA_STATUS_MAP.get(status.lower(), "error") if status else "error"


def coerce_alpaca_value(source: object, key: str) -> object | None:
    """Read a provider field from either a mapping or object attribute."""
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(key)
    if hasattr(source, key):
        return getattr(source, key)
    return None


def coerce_alpaca_enumish(value: object | None) -> str | None:
    """Convert Alpaca enum instances or raw strings into lowercase text."""
    if value is None:
        return None
    raw = getattr(value, "value", value)
    text = str(raw).strip()
    return text.lower() if text else None


def parse_alpaca_timestamp(value: object | None) -> datetime | None:
    """Parse provider timestamps while tolerating absent or malformed values."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def normalize_alpaca_order_response(
    response: object,
    order: Mapping[str, object],
) -> Mapping[str, object]:
    """Convert an Alpaca response object or mapping into local order fields."""
    status_raw = coerce_alpaca_value(response, "status")
    status = map_alpaca_status(str(status_raw) if status_raw is not None else "")
    broker_order_id = coerce_alpaca_value(response, "id") or coerce_alpaca_value(response, "order_id")
    filled_qty = coerce_alpaca_value(response, "filled_qty")
    filled_avg_price = coerce_alpaca_value(response, "filled_avg_price")
    rejection_reason = (
        coerce_alpaca_value(response, "rejection_reason")
        or coerce_alpaca_value(response, "reject_reason")
        or coerce_alpaca_value(response, "rejected_reason")
    )
    raw_symbol = coerce_alpaca_value(response, "symbol") or order.get("symbol")
    raw_asset_class = coerce_alpaca_value(response, "asset_class") or order.get("asset_class")
    asset_class = normalize_asset_class(str(raw_asset_class) if raw_asset_class is not None else "")
    symbol = canonicalize_symbol(str(raw_symbol) if raw_symbol is not None else "", asset_class=asset_class)
    side = coerce_alpaca_enumish(coerce_alpaca_value(response, "side") or order.get("side"))
    order_type = coerce_alpaca_enumish(
        coerce_alpaca_value(response, "order_type")
        or coerce_alpaca_value(response, "type")
        or order.get("order_type")
    )
    qty_raw = coerce_alpaca_value(response, "qty") or order.get("qty")
    response_client_id = coerce_alpaca_value(response, "client_order_id")
    client_order_id = response_client_id or order.get("client_order_id")
    fill_ts = parse_alpaca_timestamp(
        coerce_alpaca_value(response, "filled_at") or coerce_alpaca_value(response, "updated_at")
    )
    created_at = parse_alpaca_timestamp(
        coerce_alpaca_value(response, "submitted_at")
        or coerce_alpaca_value(response, "created_at")
        or coerce_alpaca_value(response, "updated_at")
        or order.get("created_at")
    )
    return {
        "client_order_id": client_order_id,
        "status": status,
        "broker_order_id": broker_order_id,
        "symbol": symbol,
        "asset_class": asset_class,
        "side": side,
        "qty": _coerce_float(qty_raw, default=0.0) if qty_raw is not None else None,
        "order_type": order_type,
        "created_at": created_at,
        "fill_qty": _coerce_float(filled_qty, default=0.0) if filled_qty is not None else None,
        "fill_price": (
            _coerce_float(filled_avg_price, default=0.0)
            if filled_avg_price is not None
            else None
        ),
        "fill_ts": fill_ts,
        "rejection_reason": rejection_reason,
    }


__all__ = [
    "ALPACA_STATUS_MAP",
    "ALREADY_SUBMITTED_STATUSES",
    "OPEN_ORDER_STATUSES",
    "AlpacaOrderRequestFields",
    "AlpacaReconciliationFillEvent",
    "AlpacaReconciliationOrderEvent",
    "AlpacaSubmissionErrorResponse",
    "build_alpaca_reconciliation_fill_event",
    "build_alpaca_reconciliation_order_event",
    "build_alpaca_submission_error_response",
    "coerce_alpaca_enumish",
    "coerce_alpaca_value",
    "ensure_alpaca_client_order_id",
    "map_alpaca_status",
    "normalize_alpaca_order_response",
    "normalize_alpaca_order_request_fields",
    "parse_alpaca_timestamp",
]
