"""Risk management interfaces and built-in implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Sequence, Tuple

from .portfolio import Position


@dataclass(frozen=True)
class RiskContext:
    """Context for risk evaluation."""

    positions: Mapping[str, Position]
    open_orders: Sequence[Mapping[str, object]]
    price_lookup: Mapping[str, float]
    run_id: str
    cycle_id: str
    decision_ts: datetime
    halted: bool = False


class RiskManager(ABC):
    """Validates candidate orders against risk limits."""

    @abstractmethod
    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        """Return only the orders that pass risk checks."""

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        """Return approved and rejected orders with rejection reasons."""
        order_list = list(orders)
        approved = list(self.validate(order_list, context))
        approved_ids = {order.get("client_order_id") for order in approved}
        rejected: list[Mapping[str, object]] = []
        for order in order_list:
            client_order_id = order.get("client_order_id")
            if client_order_id in approved_ids:
                continue
            rejected.append({**order, "rejection_reason": "risk_rejected"})
        return approved, rejected


class NoOpRiskManager(RiskManager):
    """Risk manager that allows all orders."""

    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        return list(orders)


class RiskPipeline(RiskManager):
    """Run multiple risk managers sequentially."""

    def __init__(self, managers: Sequence[RiskManager] | None = None) -> None:
        self._managers = list(managers or [])

    def add(self, manager: RiskManager) -> None:
        """Append a manager to the pipeline."""
        self._managers.append(manager)

    @property
    def managers(self) -> Sequence[RiskManager]:
        """Return the ordered child managers."""
        return tuple(self._managers)

    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        approved, _ = self.evaluate(orders, context)
        return approved

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        approved = list(orders)
        rejected_all: list[Mapping[str, object]] = []
        for manager in self._managers:
            approved, rejected = manager.evaluate(approved, context)
            rejected_all.extend(rejected)
            if not approved:
                break
        return approved, rejected_all


class HaltRiskManager(RiskManager):
    """Reject all orders when the runtime is halted."""

    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        approved, _ = self.evaluate(orders, context)
        return approved

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        order_list = list(orders)
        if not context.halted:
            return order_list, []
        return [], [{**order, "rejection_reason": "halted"} for order in order_list]


class MaxOrdersPerRunRiskManager(RiskManager):
    """Reject orders once the configured per-run limit is exceeded."""

    def __init__(self, *, limit: int) -> None:
        self._limit = max(0, int(limit))

    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        approved, _ = self.evaluate(orders, context)
        return approved

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        order_list = list(orders)
        if self._limit == 0:
            return [], [{**order, "rejection_reason": "max_orders_per_run"} for order in order_list]
        approved = order_list[: self._limit]
        rejected = [{**order, "rejection_reason": "max_orders_per_run"} for order in order_list[self._limit :]]
        return approved, rejected


class MaxGrossExposureRiskManager(RiskManager):
    """Reject orders that would push gross exposure over a USD limit."""

    def __init__(self, *, limit_usd: float) -> None:
        self._limit_usd = float(limit_usd)

    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        approved, _ = self.evaluate(orders, context)
        return approved

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        current_gross = _gross_exposure(context.positions, context.price_lookup)
        approved: list[Mapping[str, object]] = []
        rejected: list[Mapping[str, object]] = []

        for order in orders:
            price = _resolve_order_price(order, context)
            if price is None:
                rejected.append({**order, "rejection_reason": "missing_price"})
                continue
            qty = float(order.get("qty") or 0.0)
            proposed = current_gross + abs(price * qty)
            if proposed > self._limit_usd:
                rejected.append({**order, "rejection_reason": "max_gross_usd"})
                continue
            approved.append(order)
            current_gross = proposed

        return approved, rejected


class MaxPositionUsdPerSymbolRiskManager(RiskManager):
    """Reject orders that would push symbol exposure over a USD limit."""

    def __init__(self, *, limit_usd: float) -> None:
        self._limit_usd = float(limit_usd)

    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        approved, _ = self.evaluate(orders, context)
        return approved

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        approved: list[Mapping[str, object]] = []
        rejected: list[Mapping[str, object]] = []

        for order in orders:
            symbol = str(order.get("symbol", "")).strip().upper()
            if not symbol:
                approved.append(order)
                continue

            price = _resolve_order_price(order, context)
            if price is None:
                rejected.append({**order, "rejection_reason": "missing_price"})
                continue

            qty = float(order.get("qty") or 0.0)
            side = str(order.get("side", "")).strip().lower()
            delta = qty if side == "buy" else -qty
            current_qty = context.positions.get(symbol, Position(symbol, 0.0, None)).qty
            proposed_qty = current_qty + delta
            if abs(proposed_qty * price) > self._limit_usd:
                rejected.append({**order, "rejection_reason": "max_pos_usd_per_symbol"})
                continue
            approved.append(order)

        return approved, rejected


class OpenBuyOrderLimitRiskManager(RiskManager):
    """Reject buy orders when an open buy order already exists for the symbol."""

    _OPEN_STATUSES = {"submitted", "accepted", "partially_filled"}

    def __init__(self, *, max_open_buy_orders_per_symbol: int = 1) -> None:
        self._limit = max(1, int(max_open_buy_orders_per_symbol))
        self._reserved_symbols: set[str] = set()

    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        approved, _ = self.evaluate(orders, context)
        return approved

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        order_list = list(orders)
        approved: list[Mapping[str, object]] = []
        rejected: list[Mapping[str, object]] = []
        for order in order_list:
            symbol = str(order.get("symbol", "")).strip().upper()
            side = str(order.get("side", "")).strip().lower()
            if side != "buy" or not symbol:
                approved.append(order)
                continue

            if symbol in self._reserved_symbols:
                rejected.append({**order, "rejection_reason": "open_buy_order_pending"})
                continue

            open_count = _count_open_buy_orders(context.open_orders, symbol)
            if open_count >= self._limit:
                rejected.append({**order, "rejection_reason": "open_buy_order_exists"})
                continue

            self._reserved_symbols.add(symbol)
            approved.append(order)

        return approved, rejected


def _resolve_order_price(order: Mapping[str, object], context: RiskContext) -> float | None:
    symbol = str(order.get("symbol", "")).strip().upper()
    price = order.get("price")
    if price is not None:
        return float(price)
    if symbol:
        fallback = context.price_lookup.get(symbol)
        if fallback is not None:
            return float(fallback)
    return None


def _count_open_buy_orders(open_orders: Sequence[Mapping[str, object]], symbol: str) -> int:
    count = 0
    for order in open_orders:
        if str(order.get("symbol", "")).strip().upper() != symbol:
            continue
        if str(order.get("side", "")).strip().lower() != "buy":
            continue
        status = str(order.get("status", "")).strip().lower()
        if status in OpenBuyOrderLimitRiskManager._OPEN_STATUSES:
            count += 1
    return count


def _gross_exposure(positions: Mapping[str, Position], price_lookup: Mapping[str, float]) -> float:
    gross = 0.0
    for symbol, pos in positions.items():
        price = price_lookup.get(symbol)
        if price is None:
            continue
        gross += abs(float(pos.qty) * float(price))
    return gross
