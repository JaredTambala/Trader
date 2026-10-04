"""Pure risk-evaluation helpers for decision cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from ..portfolio import Position
from ..risk import RiskContext, RiskManager, RiskPipeline
from ..risk.evidence import (
    RiskComposition,
    RiskDecisionTrace,
    RiskManagerDescriptor,
    build_risk_composition,
    build_risk_decision_id,
    normalize_order,
    orders_differ,
)


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
    decision_traces: tuple[RiskDecisionTrace, ...] = ()
    composition: RiskComposition | None = None


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
    decision_traces: list[RiskDecisionTrace] = []
    managers = _iter_risk_managers(risk_manager)
    composition = build_risk_composition(managers)
    for manager_position, manager in enumerate(managers):
        manager_input = tuple(approved_orders)
        approved_orders, rejected = manager.evaluate(manager_input, context)
        approved_orders = tuple(approved_orders)
        rejected = tuple(rejected)
        descriptor = composition.managers[manager_position]
        decision_traces.extend(
            _build_decision_traces(
                manager_input=manager_input,
                approved_orders=approved_orders,
                rejected_orders=rejected,
                descriptor=descriptor,
                manager_position=manager_position,
                composition=composition,
                context=context,
            )
        )
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
        decision_traces=tuple(decision_traces),
        composition=composition,
    )


def _build_decision_traces(
    *,
    manager_input: Sequence[Mapping[str, object]],
    approved_orders: Sequence[Mapping[str, object]],
    rejected_orders: Sequence[Mapping[str, object]],
    descriptor: RiskManagerDescriptor,
    manager_position: int,
    composition: RiskComposition,
    context: RiskContext,
) -> tuple[RiskDecisionTrace, ...]:
    """Attribute every manager input to an approved, transformed, or rejected outcome."""
    approved_by_key = _orders_by_key(approved_orders)
    rejected_by_key = _orders_by_key(rejected_orders)
    traces: list[RiskDecisionTrace] = []
    for input_position, before in enumerate(manager_input):
        key = _order_key(before, input_position)
        approved = approved_by_key.get(key)
        rejected = rejected_by_key.get(key)
        if approved is not None:
            outcome = "transformed" if orders_differ(before, approved) else "approved"
            reason = "order_transformed" if outcome == "transformed" else "approved"
            after_order = normalize_order(approved)
        else:
            outcome = "rejected"
            reason = str((rejected or {}).get("rejection_reason") or "risk_rejected")
            after_order = None
        client_order_id = _optional_order_id(before)
        traces.append(
            RiskDecisionTrace(
                risk_decision_id=build_risk_decision_id(
                    run_id=context.run_id,
                    cycle_id=context.cycle_id,
                    client_order_id=client_order_id,
                    manager_position=manager_position,
                    before_order=before,
                ),
                composition_fingerprint=composition.composition_fingerprint,
                run_id=context.run_id,
                session_id=context.run_id,
                cycle_id=context.cycle_id,
                client_order_id=client_order_id,
                decision_ts=context.decision_ts,
                manager_id=descriptor.manager_id,
                manager_type=descriptor.manager_type,
                manager_position=manager_position,
                outcome=outcome,
                reason_code=reason,
                before_order=normalize_order(before) or {},
                after_order=after_order,
            )
        )
    return tuple(traces)


def _orders_by_key(orders: Sequence[Mapping[str, object]]) -> dict[tuple[str, object], Mapping[str, object]]:
    """Index manager outputs by stable client ID or deterministic position fallback."""
    result: dict[tuple[str, object], Mapping[str, object]] = {}
    for position, order in enumerate(orders):
        result[_order_key(order, position)] = order
        client_order_id = _optional_order_id(order)
        if client_order_id is not None:
            result[("client_order_id", client_order_id)] = order
    return result


def _order_key(order: Mapping[str, object], position: int) -> tuple[str, object]:
    client_order_id = _optional_order_id(order)
    return ("client_order_id", client_order_id) if client_order_id is not None else ("position", position)


def _optional_order_id(order: Mapping[str, object]) -> str | None:
    value = order.get("client_order_id")
    return str(value) if value is not None else None


__all__ = [
    "CycleRiskEvaluationResult",
    "CycleRiskRejectionLog",
]
