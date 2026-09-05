"""Pure execution payload helpers for the internal paper broker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping

from ..identifiers import deterministic_client_order_id
from .helpers import coerce_float

__all__ = [
    "InternalBrokerResponse",
    "InternalFeeModel",
    "InternalOrderRequest",
    "_apply_slippage",
    "build_internal_fill_response",
    "build_internal_rejection_response",
    "calculate_internal_fee_amount",
    "normalize_internal_order",
]


@dataclass(frozen=True)
class InternalFeeModel:
    """Fee assumptions used by the internal paper broker."""

    fixed_per_order: float = 0.0
    bps: float = 0.0
    minimum: float = 0.0


@dataclass(frozen=True)
class InternalOrderRequest:
    """Normalized order request accepted by the internal paper broker."""

    client_order_id: object | None
    run_id: object | None
    cycle_id: object
    symbol: str
    side: str
    qty: float
    price: object | None
    order_type: str
    created_at: object | None


@dataclass(frozen=True)
class InternalBrokerResponse:
    """Canonical internal broker response prepared as an immutable value."""

    order_event_id: str
    client_order_id: object | None
    run_id: object | None
    cycle_id: object | None
    symbol: str
    status: str
    broker_order_id: object | None
    order_type: str
    qty: float
    fill_ts: datetime
    fill_qty: float | None
    fill_price: float | None
    raw_fill_price: float | None = None
    slippage_amount: float | None = None
    fee_amount: float | None = None
    rejection_reason: object | None = None

    def to_record(self) -> dict[str, object]:
        """Return a broker-contract-compatible response mapping."""
        record: dict[str, object] = {
            "order_event_id": self.order_event_id,
            "client_order_id": self.client_order_id,
            "run_id": self.run_id,
            "cycle_id": self.cycle_id,
            "symbol": self.symbol,
            "status": self.status,
            "broker_order_id": self.broker_order_id,
            "order_type": self.order_type,
            "qty": self.qty,
            "fill_ts": self.fill_ts,
            "fill_qty": self.fill_qty,
            "fill_price": self.fill_price,
        }
        if self.raw_fill_price is not None or self.slippage_amount is not None or self.fee_amount is not None:
            record["raw_fill_price"] = self.raw_fill_price
            record["slippage_amount"] = self.slippage_amount
            record["fee_amount"] = self.fee_amount
        if self.rejection_reason is not None:
            record["rejection_reason"] = self.rejection_reason
        return record


def normalize_internal_order(order: Mapping[str, object]) -> InternalOrderRequest | None:
    """Normalize an order mapping for internal broker execution.

    Args:
        order: Candidate order payload produced by the trading cycle.

    Returns:
        A normalized request, or `None` when the order has an invalid symbol,
        side, or quantity.

    Raises:
        ValueError: If the otherwise valid order lacks `cycle_id`.
    """
    symbol = str(order.get("symbol", "")).strip().upper()
    side = str(order.get("side", "")).lower().strip()
    qty = coerce_float(order.get("qty", 0.0))
    if not symbol or side not in {"buy", "sell"} or qty <= 0:
        return None
    cycle_id = order.get("cycle_id")
    if cycle_id is None:
        raise ValueError("cycle_id is required for internal broker orders")
    return InternalOrderRequest(
        client_order_id=order.get("client_order_id"),
        run_id=order.get("run_id"),
        cycle_id=cycle_id,
        symbol=symbol,
        side=side,
        qty=qty,
        price=order.get("price"),
        order_type=str(order.get("order_type", "market")),
        created_at=order.get("created_at"),
    )


def build_internal_rejection_response(
    request: InternalOrderRequest,
    *,
    order_event_id: str,
    fill_ts: datetime,
) -> InternalBrokerResponse:
    """Build a deterministic rejection response for an internal order."""
    return InternalBrokerResponse(
        order_event_id=order_event_id,
        client_order_id=request.client_order_id,
        run_id=request.run_id,
        cycle_id=request.cycle_id,
        symbol=request.symbol,
        status="rejected",
        broker_order_id=None,
        order_type=request.order_type,
        qty=request.qty,
        fill_ts=fill_ts,
        fill_qty=None,
        fill_price=None,
        rejection_reason="internal_reject_probability",
    )


def build_internal_fill_response(
    request: InternalOrderRequest,
    *,
    order_event_id: str,
    timestamp: datetime,
    delay_ms: float,
    fill_fraction: float,
    slippage_bps: float,
    fee_model: InternalFeeModel,
) -> InternalBrokerResponse:
    """Build a deterministic fill or error response for an internal order."""
    client_order_id = request.client_order_id or deterministic_client_order_id(
        str(request.cycle_id),
        request.symbol,
        request.side,
        request.qty,
    )
    fill_qty = request.qty * max(0.0, fill_fraction)
    status = "filled" if request.price is not None else "error"
    if request.price is not None and 0 < fill_qty < request.qty:
        status = "partially_filled"
    raw_fill_price = coerce_float(request.price, default=0.0) if request.price is not None else None
    base_fill_ts = request.created_at if isinstance(request.created_at, datetime) else timestamp
    fill_ts = base_fill_ts + timedelta(milliseconds=delay_ms, microseconds=3)
    fill_price = _apply_slippage(raw_fill_price, side=request.side, slippage_bps=slippage_bps)
    slippage_amount = 0.0
    fee_amount = 0.0
    if raw_fill_price is not None and fill_price is not None:
        slippage_amount = abs(fill_price - raw_fill_price) * fill_qty
        fee_amount = calculate_internal_fee_amount(fill_qty, fill_price, fee_model)
    return InternalBrokerResponse(
        order_event_id=order_event_id,
        client_order_id=client_order_id,
        run_id=request.run_id,
        cycle_id=request.cycle_id,
        symbol=request.symbol,
        status=status,
        broker_order_id=None,
        order_type=request.order_type,
        qty=request.qty,
        fill_ts=fill_ts,
        fill_qty=fill_qty if fill_price is not None else None,
        raw_fill_price=raw_fill_price,
        fill_price=fill_price,
        slippage_amount=slippage_amount,
        fee_amount=fee_amount,
    )


def calculate_internal_fee_amount(fill_qty: float, fill_price: float, fee_model: InternalFeeModel) -> float:
    """Calculate deterministic fixed, basis-point, and minimum fees."""
    bps_fee = abs(fill_qty * fill_price) * (fee_model.bps / 10_000.0)
    fee = fee_model.fixed_per_order + bps_fee
    if fee <= 0.0 and fee_model.minimum <= 0.0:
        return 0.0
    return max(fee_model.minimum, fee)


def _apply_slippage(raw_fill_price: float | None, *, side: str, slippage_bps: float) -> float | None:
    """Apply directional slippage to a raw fill price."""
    if raw_fill_price is None:
        return None
    if side == "buy":
        return raw_fill_price * (1.0 + (slippage_bps / 10_000.0))
    return raw_fill_price * (1.0 - (slippage_bps / 10_000.0))
