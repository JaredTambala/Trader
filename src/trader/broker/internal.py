"""Internal paper broker implementation."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import random
import time
import uuid
from typing import Iterable, Mapping, Sequence

from .contracts import Broker
from .internal_execution import (
    InternalBrokerResponse,
    InternalFeeModel,
    InternalOrderRequest,
    _apply_slippage as _apply_slippage,
    build_internal_fill_response,
    build_internal_rejection_response,
    calculate_internal_fee_amount,
    normalize_internal_order,
)

__all__ = [
    "InternalBrokerResponse",
    "InternalFeeModel",
    "InternalOrderRequest",
    "InternalPaperBroker",
    "NoOpBroker",
    "_apply_slippage",
    "build_internal_fill_response",
    "build_internal_rejection_response",
    "calculate_internal_fee_amount",
    "normalize_internal_order",
]


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
