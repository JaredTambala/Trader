"""Risk management contracts and composition."""

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
        approved: Sequence[Mapping[str, object]] = list(orders)
        rejected_all: list[Mapping[str, object]] = []
        for manager in self._managers:
            approved, rejected = manager.evaluate(approved, context)
            rejected_all.extend(rejected)
            if not approved:
                break
        return approved, rejected_all
