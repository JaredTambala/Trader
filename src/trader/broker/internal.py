"""Internal paper broker implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import random
import time
import uuid
from typing import Iterable, Mapping, Sequence

from ..identifiers import deterministic_client_order_id
from .contracts import Broker
from .helpers import coerce_float


@dataclass(frozen=True)
class InternalFeeModel:
    """Fee model used by the internal paper broker."""

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


class NoOpBroker(Broker):
    """Broker implementation for dry runs that intentionally executes nothing.

    The no-op broker satisfies the `Broker` contract for tests and workflows
    that want the rest of the cycle to run without producing order lifecycle
    side effects beyond the pre-submission events recorded by the cycle.
    """

    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Accept orders without executing them.

        Args:
            orders: Iterable of order payloads.

        Returns:
            An empty list, since no orders are actually submitted.

        Raises:
            None.
        """
        return []


class InternalPaperBroker(Broker):
    """Deterministic paper broker used by backtests and local simulations.

    The broker consumes normalized order payloads from the cycle, applies the
    configured rejection, delay, partial-fill, slippage, and fee assumptions,
    and returns canonical broker response mappings. It does not persist events
    itself; the cycle records returned responses and fill events so the event
    store remains the single audit path.
    """

    def __init__(
        self,
        *,
        reject_probability: float = 0.0,
        fill_delay_ms_mean: float = 0.0,
        fill_delay_ms_stddev: float = 0.0,
        fill_qty_fraction_mean: float = 1.0,
        fill_qty_fraction_stddev: float = 0.0,
        slippage_bps: float = 0.0,
        fee_fixed_per_order: float = 0.0,
        fee_bps: float = 0.0,
        fee_minimum: float = 0.0,
        sleep_on_fill_delay: bool = True,
        rng_seed: int | None = None,
    ) -> None:
        """Configure the paper execution model.

        Args:
            reject_probability: Probability in `[0, 1]` that a valid order is
                returned as rejected.
            fill_delay_ms_mean: Mean simulated delay added to fill timestamps.
            fill_delay_ms_stddev: Standard deviation for simulated delay.
            fill_qty_fraction_mean: Mean fraction of requested quantity filled.
            fill_qty_fraction_stddev: Standard deviation for fill fraction.
            slippage_bps: Basis points applied against the raw order price.
            fee_fixed_per_order: Fixed fee added to every successful fill.
            fee_bps: Notional-based fee in basis points.
            fee_minimum: Minimum fee when a non-zero fee model is configured.
            sleep_on_fill_delay: Whether simulated latency should also block
                wall-clock execution.
            rng_seed: Optional seed used to make rejection, delay, and fill
                fraction deterministic in tests and reproducible backtests.
        """
        self._logger = logging.getLogger(__name__)
        self._reject_probability = max(0.0, min(float(reject_probability), 1.0))
        self._fill_delay_ms_mean = max(0.0, float(fill_delay_ms_mean))
        self._fill_delay_ms_stddev = max(0.0, float(fill_delay_ms_stddev))
        self._fill_qty_fraction_mean = max(0.0, float(fill_qty_fraction_mean))
        self._fill_qty_fraction_stddev = max(0.0, float(fill_qty_fraction_stddev))
        self._slippage_bps = max(0.0, float(slippage_bps))
        self._fee_fixed_per_order = max(0.0, float(fee_fixed_per_order))
        self._fee_bps = max(0.0, float(fee_bps))
        self._fee_minimum = max(0.0, float(fee_minimum))
        self._sleep_on_fill_delay = bool(sleep_on_fill_delay)
        self._rng = random.Random(rng_seed)

    def submit_orders(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Convert candidate orders into canonical simulated broker responses.

        The method validates each order locally, skips malformed payloads with a
        warning, requires `cycle_id` for traceability, and preserves or derives a
        deterministic `client_order_id`. Orders with a price receive filled or
        partially-filled responses after slippage and fee calculation; orders
        without a price produce an `error` response because the broker cannot
        infer an execution price.

        Args:
            orders: Normalized order payloads produced by the cycle after risk
                validation.

        Returns:
            Canonical response mappings for valid orders. Each response includes
            lifecycle status, fill timestamp, filled quantity/price when known,
            and fee/slippage fields for accounting.

        Raises:
            ValueError: If a valid order lacks `cycle_id`; responses must be
                traceable to a cycle before they can be persisted.
        """
        responses: list[Mapping[str, object]] = []
        timestamp = datetime.now(timezone.utc)
        fee_model = InternalFeeModel(
            fixed_per_order=self._fee_fixed_per_order,
            bps=self._fee_bps,
            minimum=self._fee_minimum,
        )
        for order in orders:
            request = normalize_internal_order(order)
            if request is None:
                self._logger.warning("Skipping invalid order payload=%s", order)
                continue
            if self._reject_probability > 0 and self._rng.random() < self._reject_probability:
                responses.append(
                    build_internal_rejection_response(
                        request,
                        order_event_id=f"order_evt_{uuid.uuid4().hex}",
                        fill_ts=timestamp,
                    ).to_record()
                )
                continue
            delay_ms = 0.0
            if self._fill_delay_ms_mean or self._fill_delay_ms_stddev:
                delay_ms = max(
                    0.0,
                    self._rng.gauss(self._fill_delay_ms_mean, self._fill_delay_ms_stddev),
                )
            if delay_ms and self._sleep_on_fill_delay:
                time.sleep(delay_ms / 1000.0)
            fill_fraction = 1.0
            if self._fill_qty_fraction_mean or self._fill_qty_fraction_stddev:
                fill_fraction = max(
                    0.0,
                    self._rng.gauss(self._fill_qty_fraction_mean, self._fill_qty_fraction_stddev),
                )
            response = build_internal_fill_response(
                request,
                order_event_id=f"order_evt_{uuid.uuid4().hex}",
                timestamp=timestamp,
                delay_ms=delay_ms,
                fill_fraction=fill_fraction,
                slippage_bps=self._slippage_bps,
                fee_model=fee_model,
            )
            if request.price is None:
                self._logger.warning("Missing price for order; fill skipped symbol=%s", request.symbol)
            responses.append(response.to_record())
        return responses

    def _compute_fee_amount(self, fill_qty: float, fill_price: float) -> float:
        """Apply the configured fixed, basis-point, and minimum fee model.

        The result is deterministic for a given fill quantity and price. A zero
        fee model returns `0.0` instead of applying a minimum by accident.
        """
        return calculate_internal_fee_amount(
            fill_qty,
            fill_price,
            InternalFeeModel(
                fixed_per_order=self._fee_fixed_per_order,
                bps=self._fee_bps,
                minimum=self._fee_minimum,
            ),
        )


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
    """Build a deterministic fill or error response for an internal order.

    Args:
        request: Normalized order request.
        order_event_id: Explicit response event identifier.
        timestamp: Broker submission timestamp for orders without `created_at`.
        delay_ms: Simulated latency in milliseconds.
        fill_fraction: Simulated filled fraction of requested quantity.
        slippage_bps: Basis points applied against the raw order price.
        fee_model: Fee assumptions to apply to successful fills.

    Returns:
        An immutable broker response value object.
    """
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
