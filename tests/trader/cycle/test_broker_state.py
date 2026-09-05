"""Cycle broker-state and internal-fill application contracts.

Subject: Broker portfolio normalization, response decisions, and fill-driven portfolio application.
Level: Deterministic unit and fail-closed boundary contracts.
Collaborators: Real broker-state helpers, package-owned configuration, and provider-shaped in-memory payloads.
Guarantees: Broker truth is normalized, out-of-scope positions fail closed, and valid fills become explicit actions.
Non-goals: Provider calls, persistence, order lifecycle records, or full-cycle orchestration.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.trader.cycle.factories import build_cycle_config as _base_config
from trader.cycle.broker_state import (
    _build_cycle_broker_response_plan,
    _build_portfolio_from_broker_payload,
    _build_processed_order_from_broker_response,
    _broker_position_views_to_positions,
    _coerce_broker_cash,
    _resolve_broker_response_status,
    _should_sync_portfolio_for_broker_response,
)
from trader.cycle.portfolio_updates import build_internal_fill_portfolio_application
from trader.portfolio import Position
from trader.symbols import BrokerPositionView


def test_broker_portfolio_payload_helpers_build_runtime_portfolio() -> None:
    """Normalize broker cash and position views into the runtime portfolio model."""
    config = _base_config(":memory:")
    views = [
        BrokerPositionView(
            symbol="AAPL",
            asset_class="stocks",
            qty=2.0,
            avg_entry_price=95.0,
            side="long",
            raw_symbol="AAPL",
            raw_asset_class="us_equity",
        )
    ]

    positions = _broker_position_views_to_positions(views)
    portfolio = _build_portfolio_from_broker_payload(
        account={"cash": "1234.50"},
        positions_raw=[
            {
                "symbol": "AAPL",
                "asset_class": "us_equity",
                "qty": "2",
                "avg_entry_price": "95",
                "side": "long",
            }
        ],
        config=config,
    )

    assert _coerce_broker_cash({"cash": "1234.50"}) == 1234.5
    assert _coerce_broker_cash({}) == 0.0
    assert _coerce_broker_cash(object()) == 0.0
    assert positions == {"AAPL": Position(symbol="AAPL", qty=2.0, avg_price=95.0)}
    assert portfolio.cash_balance == 1234.5
    assert portfolio.positions == positions


def test_broker_portfolio_payload_rejects_positions_outside_configured_universe() -> (
    None
):
    """Fail closed when broker truth contains a position outside configured scope."""
    config = _base_config(":memory:")

    with pytest.raises(ValueError, match="Broker portfolio mismatch"):
        _build_portfolio_from_broker_payload(
            account={"cash": "0"},
            positions_raw=[
                {
                    "symbol": "MSFT",
                    "asset_class": "us_equity",
                    "qty": "1",
                    "avg_entry_price": "100",
                    "side": "long",
                }
            ],
            config=config,
        )


def test_broker_response_helpers_normalize_status_sync_and_processed_order() -> None:
    """Derive canonical status, synchronization, and filled-order actions from responses."""
    order = {"symbol": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0}
    fallback_fill_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    filled_response = {
        "status": "filled",
        "fill_qty": "0.5",
        "fill_price": "101.25",
    }

    assert _resolve_broker_response_status({}) == "submitted"
    assert _resolve_broker_response_status(filled_response) == "filled"
    assert (
        _should_sync_portfolio_for_broker_response(
            status="filled",
            sync_portfolio_on_fill=True,
        )
        is True
    )
    assert (
        _should_sync_portfolio_for_broker_response(
            status="submitted",
            sync_portfolio_on_fill=True,
        )
        is False
    )
    assert _build_processed_order_from_broker_response(order, filled_response) == {
        **order,
        "qty": 0.5,
        "price": 101.25,
    }
    assert (
        _build_processed_order_from_broker_response(
            order,
            {"status": "rejected", "rejection_reason": "broker_reject"},
        )
        is None
    )
    plan = _build_cycle_broker_response_plan(
        order,
        filled_response,
        sync_portfolio_on_fill=True,
        fallback_fill_ts=fallback_fill_ts,
    )
    assert plan.status == "filled"
    assert plan.processed_order == {**order, "qty": 0.5, "price": 101.25}
    assert plan.should_sync_portfolio is True
    assert plan.fill_ts == fallback_fill_ts
    rejected_plan = _build_cycle_broker_response_plan(
        order,
        {"status": "rejected", "rejection_reason": "broker_reject"},
        sync_portfolio_on_fill=True,
        fallback_fill_ts=fallback_fill_ts,
    )
    assert rejected_plan.processed_order is None
    assert rejected_plan.should_sync_portfolio is False


def test_build_internal_fill_portfolio_application_normalizes_fill_response() -> None:
    """Convert a valid internal fill into one normalized portfolio application."""
    order = {"symbol": " AAPL ", "side": " BUY ", "qty": "2", "price": "99.0"}
    response = {"fill_qty": "1.5", "fill_price": "101.25", "fee_amount": "0.25"}

    application = build_internal_fill_portfolio_application(
        order=order, response=response
    )

    assert application is not None
    assert application.order == {
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.5,
        "price": "101.25",
        "fee_amount": "0.25",
    }
    assert application.price_lookup == {"AAPL": 101.25}


def test_build_internal_fill_portfolio_application_skips_invalid_fill_inputs() -> None:
    """Suppress portfolio mutation for invalid symbols, sides, or quantities."""
    assert (
        build_internal_fill_portfolio_application(
            order={"symbol": "", "side": "buy", "qty": 1.0},
            response={},
        )
        is None
    )
    assert (
        build_internal_fill_portfolio_application(
            order={"symbol": "AAPL", "side": "hold", "qty": 1.0},
            response={},
        )
        is None
    )
    assert (
        build_internal_fill_portfolio_application(
            order={"symbol": "AAPL", "side": "buy", "qty": "bad"},
            response={},
        )
        is None
    )
