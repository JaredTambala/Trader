"""Cycle risk-context and per-order evaluation contracts.

Subject: Explicit risk inputs, stream price overrides, and manager-attributed rejection evidence.
Level: Deterministic risk-boundary unit contracts.
Collaborators: Real cycle risk helpers, core risk values, and a rejecting manager fake.
Guarantees: Each order is evaluated with bounded state and rejections retain reason and manager identity.
Non-goals: Portfolio loading, persistent logs, broker submission, or policy effectiveness.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader.cycle.risk import (
    _build_cycle_risk_context,
    _build_stream_risk_price_lookup,
    _evaluate_cycle_order_risk,
)
from trader.portfolio import Position
from trader.risk import RiskContext, RiskManager


class RejectSymbolRiskManager(RiskManager):
    """Test risk manager that rejects one configured symbol."""

    def __init__(self, symbol: str, reason: str) -> None:
        self.symbol = symbol
        self.reason = reason

    def validate(
        self,
        orders,
        context: RiskContext,
    ):
        del context
        return [order for order in orders if order.get("symbol") != self.symbol]

    def evaluate(
        self,
        orders,
        context: RiskContext,
    ):
        del context
        approved = []
        rejected = []
        for order in orders:
            if order.get("symbol") == self.symbol:
                rejected.append({**order, "rejection_reason": self.reason})
            else:
                approved.append(order)
        return approved, rejected


def test_build_stream_risk_price_lookup_uses_latest_prices_and_order_override() -> None:
    """Overlay the current order price onto the latest stream-price snapshot."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    price_lookup = _build_stream_risk_price_lookup(
        {
            "AAPL": (base_ts, 100.0),
            "MSFT": (base_ts, 200.0),
        },
        {"symbol": " aapl ", "price": "101.25"},
    )

    assert price_lookup == {"AAPL": 101.25, "MSFT": 200.0}


def test_build_cycle_risk_context_uses_explicit_state_without_storage() -> None:
    """Build complete risk context entirely from supplied normalized runtime state."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    position = Position(symbol="AAPL", qty=1.0, avg_price=90.0)
    open_order = {"client_order_id": "cid_open", "symbol": "AAPL"}
    order = {"symbol": "AAPL", "price": 105.0, "created_at": base_ts}

    context = _build_cycle_risk_context(
        positions={"AAPL": position},
        open_orders=[open_order],
        latest_prices={"AAPL": (base_ts - timedelta(minutes=1), 100.0)},
        order=order,
        run_id="run_1",
        cycle_id="cycle_1",
        halted=True,
        fallback_ts=base_ts + timedelta(minutes=5),
    )

    assert context.positions == {"AAPL": position}
    assert context.open_orders == [open_order]
    assert context.price_lookup == {"AAPL": 105.0}
    assert context.run_id == "run_1"
    assert context.cycle_id == "cycle_1"
    assert context.decision_ts == base_ts
    assert context.halted is True


def test_build_cycle_risk_context_uses_fallback_for_missing_order_time() -> None:
    """Use the cycle fallback timestamp when order evidence lacks creation time."""
    fallback_ts = datetime(2026, 1, 20, 12, 5, tzinfo=timezone.utc)

    context = _build_cycle_risk_context(
        positions={},
        open_orders=[],
        latest_prices={},
        order={"symbol": "AAPL"},
        run_id="run_1",
        cycle_id="cycle_1",
        halted=False,
        fallback_ts=fallback_ts,
    )

    assert context.decision_ts == fallback_ts


def test_evaluate_cycle_order_risk_returns_approved_and_manager_rejection_logs() -> (
    None
):
    """Return rejected orders with both policy reason and responsible manager identity."""
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    context = RiskContext(
        positions={},
        open_orders=[],
        price_lookup={},
        run_id="run_1",
        cycle_id="cycle_1",
        decision_ts=base_ts,
    )
    manager = RejectSymbolRiskManager("AAPL", "blocked_symbol")
    order = {"symbol": "AAPL", "side": "buy", "qty": 1.0}

    result = _evaluate_cycle_order_risk(
        order=order,
        context=context,
        risk_manager=manager,
    )

    assert result.approved_orders == ()
    assert result.rejected_orders == ({**order, "rejection_reason": "blocked_symbol"},)
    assert len(result.rejection_logs) == 1
    assert result.rejection_logs[0].order == result.rejected_orders[0]
    assert result.rejection_logs[0].manager_name == "RejectSymbolRiskManager"
