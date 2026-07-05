"""Pure risk-evaluation helpers for decision cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from ..portfolio import Position
from ..risk import RiskContext, RiskManager, RiskPipeline


@dataclass(frozen=True)
class CycleRiskRejectionLog:
    """Rejected order plus the risk manager that rejected it."""

    order: Mapping[str, object]
    manager_name: str


@dataclass(frozen=True)
class CycleRiskEvaluationResult:
    """Approved and rejected order payloads from cycle risk validation."""

    approved_orders: tuple[Mapping[str, object], ...]
    rejected_orders: tuple[Mapping[str, object], ...]
    rejection_logs: tuple[CycleRiskRejectionLog, ...]


def _iter_risk_managers(risk_manager: RiskManager) -> Sequence[RiskManager]:
    """Expand a risk manager into ordered components for evaluation."""
    if isinstance(risk_manager, RiskPipeline):
        return tuple(risk_manager.managers)
    return (risk_manager,)


def _build_stream_risk_price_lookup(
    latest_prices: Mapping[str, tuple[datetime, float]],
    order: Mapping[str, object],
) -> Mapping[str, float]:
    """Build the risk price lookup from stream prices and order price evidence."""
    price_lookup = {symbol: price for symbol, (_, price) in latest_prices.items()}
    symbol = str(order.get("symbol", "")).strip().upper()
    order_price = order.get("price")
    if symbol and order_price is not None:
        price_lookup[symbol] = float(order_price)
    return price_lookup


def _resolve_order_decision_ts(
    order: Mapping[str, object],
    fallback_ts: datetime,
) -> datetime:
    """Return the datetime risk managers should use for an order decision."""
    created_at = order.get("created_at")
    if isinstance(created_at, datetime):
        return created_at
    return fallback_ts


def _build_cycle_risk_context(
    *,
    positions: Mapping[str, Position],
    open_orders: Sequence[Mapping[str, object]],
    latest_prices: Mapping[str, tuple[datetime, float]],
    order: Mapping[str, object],
    run_id: str,
    cycle_id: str,
    halted: bool,
    fallback_ts: datetime,
) -> RiskContext:
    """Build a risk context from explicit cycle state without storage access."""
    return RiskContext(
        positions=positions,
        open_orders=open_orders,
        price_lookup=_build_stream_risk_price_lookup(latest_prices, order),
        run_id=run_id,
        cycle_id=cycle_id,
        decision_ts=_resolve_order_decision_ts(order, fallback_ts),
        halted=halted,
    )


def _evaluate_cycle_order_risk(
    *,
    order: Mapping[str, object],
    context: RiskContext,
    risk_manager: RiskManager,
) -> CycleRiskEvaluationResult:
    """Evaluate one enriched order through the configured risk manager chain."""
    approved_orders: Sequence[Mapping[str, object]] = [order]
    rejected_orders: list[Mapping[str, object]] = []
    rejection_logs: list[CycleRiskRejectionLog] = []
    for manager in _iter_risk_managers(risk_manager):
        approved_orders, rejected = manager.evaluate(approved_orders, context)
        if rejected:
            for rejected_order in rejected:
                rejection_logs.append(
                    CycleRiskRejectionLog(
                        order=rejected_order,
                        manager_name=manager.__class__.__name__,
                    )
                )
            rejected_orders.extend(rejected)
        if not approved_orders:
            break
    return CycleRiskEvaluationResult(
        approved_orders=tuple(approved_orders),
        rejected_orders=tuple(rejected_orders),
        rejection_logs=tuple(rejection_logs),
    )


__all__ = [
    "CycleRiskEvaluationResult",
    "CycleRiskRejectionLog",
]
