"""Risk management interface for pre-trade validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping, Sequence, Tuple


class RiskManager(ABC):
    """Validates candidate orders against risk limits.

    External risk managers should subclass this and implement ``validate``.
    """

    @abstractmethod
    def validate(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Return only the orders that pass risk checks.

        Args:
            orders: Iterable of candidate order payloads.

        Returns:
            Sequence of orders that passed validation.

        Raises:
            Exception: Implementations may raise on validation errors.
        """

    def evaluate(
        self, orders: Iterable[Mapping[str, object]]
    ) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        """Return approved and rejected orders with rejection reasons.

        Args:
            orders: Iterable of candidate order payloads.

        Returns:
            Tuple of (approved_orders, rejected_orders). Rejected orders include
            a `rejection_reason` key for auditability.
        """
        order_list = list(orders)
        approved = list(self.validate(order_list))
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

    def validate(self, orders: Iterable[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
        """Return all orders unchanged.

        Args:
            orders: Iterable of candidate order payloads.

        Returns:
            List of all orders.

        Raises:
            None.
        """
        return list(orders)
