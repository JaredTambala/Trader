"""Tests for raw portfolio order input normalization."""

from __future__ import annotations

import pytest

from trader.portfolio.order_inputs import PortfolioOrderInput, normalize_portfolio_order_inputs


def test_normalize_portfolio_order_inputs_applies_price_lookup_and_fees() -> None:
    """Ensure raw order mappings normalize into typed order inputs."""
    orders = normalize_portfolio_order_inputs(
        (
            {"symbol": " AAPL ", "side": " BUY ", "qty": "2", "fee_amount": "0.5"},
            {"symbol": "MSFT", "side": "sell", "qty": 1, "price": "250.25"},
        ),
        price_lookup={"AAPL": 100.0},
    )

    assert orders == (
        PortfolioOrderInput("AAPL", "buy", 2.0, 100.0, 0.5),
        PortfolioOrderInput("MSFT", "sell", 1.0, 250.25, 0.0),
    )


def test_normalize_portfolio_order_inputs_skips_blank_symbols_and_non_positive_qty() -> None:
    """Ensure ignored raw mappings preserve existing portfolio shell behavior."""
    orders = normalize_portfolio_order_inputs(
        (
            {"symbol": "", "side": "buy", "qty": 1},
            {"symbol": "AAPL", "side": "buy", "qty": 0},
            {"symbol": "MSFT", "side": "sell", "qty": -1},
        ),
        price_lookup={},
    )

    assert orders == ()


def test_normalize_portfolio_order_inputs_rejects_invalid_qty() -> None:
    """Ensure invalid quantities fail with the original order payload."""
    with pytest.raises(ValueError, match="Invalid qty for order: .*AAPL"):
        normalize_portfolio_order_inputs(
            ({"symbol": "AAPL", "side": "buy", "qty": "bad"},),
            price_lookup={},
        )


def test_normalize_portfolio_order_inputs_rejects_invalid_side() -> None:
    """Ensure invalid sides fail after symbol and quantity normalization."""
    with pytest.raises(ValueError, match="Invalid side for order: .*hold"):
        normalize_portfolio_order_inputs(
            ({"symbol": "AAPL", "side": "hold", "qty": 1},),
            price_lookup={},
        )
