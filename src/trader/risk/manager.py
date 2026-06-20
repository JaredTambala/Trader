"""Abstract risk-manager contract for validating candidate orders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping, Sequence, Tuple

from .context import RiskContext


class RiskManager(ABC):
    """Interface for approving or rejecting candidate order intents.

    Implementations should be deterministic for a given `RiskContext` and leave
    persistence to the cycle, which records approved and rejected orders.
    """

    @abstractmethod
    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        """Return the candidate orders this manager allows to continue downstream.

        Implementations should keep input order for approved orders and avoid
        mutating the supplied mappings. Detailed rejection reasons can be provided
        by overriding `evaluate`; otherwise rejected orders receive the default
        `risk_rejected` reason.
        """

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        """Split candidate orders into approved and rejected collections.

        Subclasses may override this to provide detailed rejection payloads. The
        default implementation calls `validate()` and marks missing orders with
        a generic `risk_rejected` reason so the cycle can persist them.
        """
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
