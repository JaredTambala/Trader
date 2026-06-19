"""Risk management contracts and composition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Sequence, Tuple

from .portfolio import Position


@dataclass(frozen=True)
class RiskContext:
    """Immutable market, portfolio, and runtime facts supplied to risk checks.

    Attributes:
        positions: Current positions keyed by symbol.
        open_orders: Latest local order lifecycle records still relevant to risk.
        price_lookup: Latest close/fill prices keyed by symbol.
        run_id: Run/session identifier for audit-aware risk decisions.
        cycle_id: Decision-cycle identifier for emitted rejection reasons.
        decision_ts: Timestamp of the decision being evaluated.
        halted: Whether the operator global halt flag is active.
    """

    positions: Mapping[str, Position]
    open_orders: Sequence[Mapping[str, object]]
    price_lookup: Mapping[str, float]
    run_id: str
    cycle_id: str
    decision_ts: datetime
    halted: bool = False


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


class RiskPipeline(RiskManager):
    """Composite risk manager that applies child managers in order.

    Rejections from each child are accumulated, and later managers see only the
    orders approved by earlier managers.
    """

    def __init__(self, managers: Sequence[RiskManager] | None = None) -> None:
        self._managers = list(managers or [])

    def add(self, manager: RiskManager) -> None:
        """Append a risk manager that will run after currently registered managers."""
        self._managers.append(manager)

    @property
    def managers(self) -> Sequence[RiskManager]:
        """Return the child managers in the order used for sequential validation."""
        return tuple(self._managers)

    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        """Return orders approved after every manager in the pipeline has run.

        This is the compatibility view of `evaluate`: it discards detailed
        rejection payloads and returns only the surviving orders from the ordered
        manager chain.
        """
        approved, _ = self.evaluate(orders, context)
        return approved

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        """Run child managers in order while accumulating rejected order payloads.

        Each manager receives only the orders approved by previous managers. The
        pipeline stops early when no orders remain, and returns both the final
        approved set and all rejection records emitted along the way.
        """
        approved: Sequence[Mapping[str, object]] = list(orders)
        rejected_all: list[Mapping[str, object]] = []
        for manager in self._managers:
            approved, rejected = manager.evaluate(approved, context)
            rejected_all.extend(rejected)
            if not approved:
                break
        return approved, rejected_all
