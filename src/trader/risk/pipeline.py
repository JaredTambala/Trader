"""Ordered composition for multiple risk managers."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence, Tuple

from .context import RiskContext
from .manager import RiskManager


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
