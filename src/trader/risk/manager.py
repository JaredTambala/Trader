"""Abstract risk-manager contract for validating candidate orders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence, Tuple

from .context import RiskContext


@dataclass(frozen=True)
class RiskEvaluation:
    """Immutable result of approving and rejecting candidate orders."""

    approved: tuple[Mapping[str, object], ...]
    rejected: tuple[Mapping[str, object], ...]

    def as_tuple(self) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        """Return the legacy `(approved, rejected)` risk-manager tuple shape."""
        return self.approved, self.rejected


def split_approved_rejected_orders(
    orders: Iterable[Mapping[str, object]],
    approved_orders: Iterable[Mapping[str, object]],
    *,
    rejection_reason: str = "risk_rejected",
) -> RiskEvaluation:
    """Split original candidate orders from an approved subset.

    Args:
        orders: Original candidate order sequence supplied to a risk manager.
        approved_orders: Orders returned by `validate()`.
        rejection_reason: Reason assigned to orders absent from the approved
            subset.

    Returns:
        Immutable approved/rejected collections. Orders with explicit
        `client_order_id` are matched by that identifier. Orders without an ID
        are matched by object identity, which avoids approving every anonymous
        order when only one anonymous order survived validation.
    """
    order_list = tuple(orders)
    approved_tuple = tuple(approved_orders)
    approved_ids = {
        order.get("client_order_id")
        for order in approved_tuple
        if order.get("client_order_id") is not None
    }
    approved_object_ids = {
        id(order)
        for order in approved_tuple
        if order.get("client_order_id") is None
    }
    rejected: list[Mapping[str, object]] = []
    for order in order_list:
        client_order_id = order.get("client_order_id")
        if client_order_id is not None and client_order_id in approved_ids:
            continue
        if client_order_id is None and id(order) in approved_object_ids:
            continue
        rejected.append({**order, "rejection_reason": rejection_reason})
    return RiskEvaluation(approved=approved_tuple, rejected=tuple(rejected))


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
        return split_approved_rejected_orders(order_list, approved).as_tuple()
