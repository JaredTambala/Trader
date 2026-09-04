"""Contracts for maintained risk managers composed through the core risk protocol.

Subject: Halts, order limits, exposure limits, open-buy guards, anonymous identity, and sequential composition.
Level: Deterministic implementation and protocol-composition unit contracts.
Collaborators: Real maintained managers, core risk values and pipeline, and bounded test-only managers.
Guarantees: Maintained controls reject unsafe orders with stable reasons and compose without losing order identity.
Non-goals: Broker submission, event persistence, live account reads, configuration parsing, or strategy generation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from trader.portfolio import Position
from trader.risk import (
    RiskContext,
    RiskManager,
    RiskPipeline,
    evaluate_risk_pipeline,
    split_approved_rejected_orders,
)
from trader_standard.risk import (
    HaltRiskManager,
    MaxGrossExposureRiskManager,
    MaxOrdersPerRunRiskManager,
    MaxPositionUsdPerSymbolRiskManager,
    OpenBuyOrderLimitRiskManager,
)


def _context(
    *,
    positions: dict[str, Position] | None = None,
    open_orders: list[dict[str, object]] | None = None,
    price_lookup: dict[str, float] | None = None,
    halted: bool = False,
) -> RiskContext:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return RiskContext(
        positions=positions or {},
        open_orders=open_orders or [],
        price_lookup=price_lookup or {},
        run_id="run1",
        cycle_id="cycle1",
        decision_ts=now,
        halted=halted,
    )


class _ApproveFirstOnlyRiskManager(RiskManager):
    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        del context
        return list(orders)[:1]


class _RejectBySymbolRiskManager(RiskManager):
    def __init__(self, rejected_symbol: str, reason: str) -> None:
        self._rejected_symbol = rejected_symbol
        self._reason = reason

    def validate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> Sequence[Mapping[str, object]]:
        del context
        return [
            order for order in orders if order.get("symbol") != self._rejected_symbol
        ]

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ):
        approved = self.validate(orders, context)
        return split_approved_rejected_orders(
            orders,
            approved,
            rejection_reason=self._reason,
        ).as_tuple()


def test_split_approved_rejected_orders_handles_anonymous_orders_by_identity() -> None:
    """Ensure anonymous orders are matched by object identity instead of shared missing IDs."""
    approved_order = {"symbol": "AAPL", "side": "buy", "qty": 1.0}
    rejected_order = {"symbol": "MSFT", "side": "buy", "qty": 1.0}

    result = split_approved_rejected_orders(
        [approved_order, rejected_order],
        [approved_order],
    )

    assert result.approved == (approved_order,)
    assert result.rejected == ({**rejected_order, "rejection_reason": "risk_rejected"},)


def test_default_risk_manager_evaluate_does_not_approve_every_anonymous_order() -> None:
    """Ensure default evaluation preserves one manager's selective anonymous-order approval."""
    context = _context()
    manager = _ApproveFirstOnlyRiskManager()

    approved, rejected = manager.evaluate(
        [
            {"symbol": "AAPL", "side": "buy", "qty": 1.0},
            {"symbol": "MSFT", "side": "buy", "qty": 1.0},
        ],
        context,
    )

    assert [order["symbol"] for order in approved] == ["AAPL"]
    assert [order["symbol"] for order in rejected] == ["MSFT"]
    assert rejected[0]["rejection_reason"] == "risk_rejected"


def test_halt_risk_manager_rejects_all_orders() -> None:
    """Ensure a global halt rejects every candidate with the explicit halted reason."""
    context = _context(halted=True)
    manager = HaltRiskManager()

    approved, rejected = manager.evaluate(
        [{"client_order_id": "o1", "symbol": "AAPL", "side": "buy", "qty": 1.0}],
        context,
    )

    assert approved == []
    assert len(rejected) == 1
    assert rejected[0]["rejection_reason"] == "halted"


def test_max_orders_per_run_risk_manager_limits_order_count() -> None:
    """Ensure the per-run order limit retains only the allowed prefix and reasons."""
    context = _context()
    manager = MaxOrdersPerRunRiskManager(limit=1)

    approved, rejected = manager.evaluate(
        [
            {"client_order_id": "o1", "symbol": "AAPL", "side": "buy", "qty": 1.0},
            {"client_order_id": "o2", "symbol": "MSFT", "side": "buy", "qty": 1.0},
        ],
        context,
    )

    assert len(approved) == 1
    assert len(rejected) == 1
    assert rejected[0]["client_order_id"] == "o2"
    assert rejected[0]["rejection_reason"] == "max_orders_per_run"


def test_max_gross_exposure_risk_manager_rejects_when_limit_exceeded() -> None:
    """Ensure a candidate increasing gross exposure beyond its limit is rejected."""
    context = _context(
        positions={"AAPL": Position(symbol="AAPL", qty=1.0, avg_price=100.0)},
        price_lookup={"AAPL": 100.0, "MSFT": 50.0},
    )
    manager = MaxGrossExposureRiskManager(limit_usd=125.0)

    approved, rejected = manager.evaluate(
        [
            {
                "client_order_id": "o1",
                "symbol": "MSFT",
                "side": "buy",
                "qty": 1.0,
                "price": 50.0,
            }
        ],
        context,
    )

    assert approved == []
    assert len(rejected) == 1
    assert rejected[0]["rejection_reason"] == "max_gross_usd"


def test_max_gross_exposure_risk_manager_approves_sell_that_reduces_exposure() -> None:
    """Ensure exposure-reducing sells remain allowed when naive notional addition would fail."""
    # Gross exposure is already at 100 USD (1 AAPL @ 100). A sell that reduces it
    # should be approved even though the limit is 110 and a naive buy of equal size
    # would be rejected.
    context = _context(
        positions={"AAPL": Position(symbol="AAPL", qty=1.0, avg_price=100.0)},
        price_lookup={"AAPL": 100.0},
    )
    manager = MaxGrossExposureRiskManager(limit_usd=110.0)

    approved, rejected = manager.evaluate(
        [
            {
                "client_order_id": "o1",
                "symbol": "AAPL",
                "side": "sell",
                "qty": 0.5,
                "price": 100.0,
            }
        ],
        context,
    )

    assert len(approved) == 1
    assert rejected == []


def test_max_gross_exposure_risk_manager_approves_sell_when_already_at_limit() -> None:
    """Ensure a portfolio at its limit may still submit exposure-reducing sells."""
    # Gross exposure exactly at the limit; a sell order that reduces it should be
    # approved and must not be blocked as "exceeding" the limit.
    context = _context(
        positions={"AAPL": Position(symbol="AAPL", qty=2.0, avg_price=100.0)},
        price_lookup={"AAPL": 100.0},
    )
    manager = MaxGrossExposureRiskManager(limit_usd=200.0)

    approved, rejected = manager.evaluate(
        [
            {
                "client_order_id": "o1",
                "symbol": "AAPL",
                "side": "sell",
                "qty": 1.0,
                "price": 100.0,
            }
        ],
        context,
    )

    assert len(approved) == 1
    assert rejected == []


def test_max_position_usd_per_symbol_risk_manager_rejects_when_limit_exceeded() -> None:
    """Ensure a candidate exceeding its symbol-level position limit is rejected explicitly."""
    context = _context(
        positions={"AAPL": Position(symbol="AAPL", qty=1.0, avg_price=100.0)},
        price_lookup={"AAPL": 100.0},
    )
    manager = MaxPositionUsdPerSymbolRiskManager(limit_usd=150.0)

    approved, rejected = manager.evaluate(
        [
            {
                "client_order_id": "o1",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "price": 100.0,
            }
        ],
        context,
    )

    assert approved == []
    assert len(rejected) == 1
    assert rejected[0]["rejection_reason"] == "max_pos_usd_per_symbol"


def test_open_buy_order_limit_rejects_when_existing_open_buy() -> None:
    """Ensure an existing nonterminal buy prevents stacking another buy for that symbol."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    context = _context(
        open_orders=[
            {
                "client_order_id": "order_1",
                "run_id": "run1",
                "cycle_id": "cycle1",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "order_type": "market",
                "status": "submitted",
                "broker_order_id": "broker1",
                "created_at": now,
            }
        ]
    )
    manager = OpenBuyOrderLimitRiskManager(max_open_buy_orders_per_symbol=1)

    approved, rejected = manager.evaluate(
        [{"client_order_id": "order_new", "symbol": "AAPL", "side": "buy", "qty": 1.0}],
        context,
    )

    assert approved == []
    assert len(rejected) == 1
    assert rejected[0]["rejection_reason"] == "open_buy_order_exists"


def test_risk_pipeline_runs_sequentially_and_accumulates_rejections() -> None:
    """Ensure ordered maintained controls see prior approvals and retain every rejection reason."""
    context = _context(price_lookup={"AAPL": 100.0, "MSFT": 25.0})
    manager = RiskPipeline(
        [
            MaxOrdersPerRunRiskManager(limit=2),
            MaxPositionUsdPerSymbolRiskManager(limit_usd=50.0),
        ]
    )

    approved, rejected = manager.evaluate(
        [
            {
                "client_order_id": "o1",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "price": 100.0,
            },
            {
                "client_order_id": "o2",
                "symbol": "MSFT",
                "side": "buy",
                "qty": 1.0,
                "price": 25.0,
            },
            {
                "client_order_id": "o3",
                "symbol": "NVDA",
                "side": "buy",
                "qty": 1.0,
                "price": 10.0,
            },
        ],
        context,
    )

    assert [order["client_order_id"] for order in approved] == ["o2"]
    assert len(rejected) == 2
    assert {order["client_order_id"] for order in rejected} == {"o1", "o3"}
    reasons = {
        order["client_order_id"]: order["rejection_reason"] for order in rejected
    }
    assert reasons["o1"] == "max_pos_usd_per_symbol"
    assert reasons["o3"] == "max_orders_per_run"


def test_evaluate_risk_pipeline_returns_immutable_ordered_result() -> None:
    """Ensure pure pipeline evaluation returns ordered immutable approvals and accumulated rejections."""
    context = _context()

    result = evaluate_risk_pipeline(
        [
            _RejectBySymbolRiskManager("MSFT", "blocked_msft"),
            _RejectBySymbolRiskManager("AAPL", "blocked_aapl"),
        ],
        [
            {"client_order_id": "o1", "symbol": "AAPL", "side": "buy", "qty": 1.0},
            {"client_order_id": "o2", "symbol": "MSFT", "side": "buy", "qty": 1.0},
            {"client_order_id": "o3", "symbol": "NVDA", "side": "buy", "qty": 1.0},
        ],
        context,
    )

    assert [order["client_order_id"] for order in result.approved] == ["o3"]
    assert [order["client_order_id"] for order in result.rejected] == ["o2", "o1"]
    assert [order["rejection_reason"] for order in result.rejected] == [
        "blocked_msft",
        "blocked_aapl",
    ]
