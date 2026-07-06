"""Tests for immutable portfolio value objects."""

from __future__ import annotations

import pytest

from trader.portfolio import PortfolioOrder
from trader.portfolio.core import PortfolioSnapshot as CorePortfolioSnapshot
from trader.portfolio.core import Position as CorePosition
from trader.portfolio.core import apply_portfolio_order as core_apply_portfolio_order
from trader.portfolio.models import Position
from trader.portfolio.snapshots import PortfolioSnapshot
from trader.portfolio.transitions import apply_portfolio_order


def test_position_remains_available_from_core_import_surface() -> None:
    """Direct core imports continue to resolve after model extraction."""
    assert CorePosition is Position


def test_portfolio_snapshot_remains_available_from_core_import_surface() -> None:
    """Direct core imports continue to resolve after snapshot extraction."""
    assert CorePortfolioSnapshot is PortfolioSnapshot


def test_transition_functions_remain_available_from_core_import_surface() -> None:
    """Direct core imports continue to resolve after transition extraction."""
    assert core_apply_portfolio_order is apply_portfolio_order


def test_portfolio_order_validates_required_fields() -> None:
    """Invalid normalized portfolio orders fail before transition logic runs."""
    with pytest.raises(ValueError, match="symbol is required"):
        PortfolioOrder(symbol=" ", side="buy", qty=1.0)

    with pytest.raises(ValueError, match="side must be buy or sell"):
        PortfolioOrder(symbol="AAPL", side="hold", qty=1.0)

    with pytest.raises(ValueError, match="qty must be positive"):
        PortfolioOrder(symbol="AAPL", side="buy", qty=0.0)


def test_portfolio_order_signed_qty_delta() -> None:
    """Order side determines the signed quantity delta."""
    assert PortfolioOrder(symbol="AAPL", side="buy", qty=2.0).signed_qty_delta == 2.0
    assert PortfolioOrder(symbol="AAPL", side="sell", qty=2.0).signed_qty_delta == -2.0
