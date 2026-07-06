"""Tests for pure portfolio snapshot row reconstruction."""

from __future__ import annotations

import pytest

from trader.portfolio import Position
from trader.portfolio.reconstruction import (
    cash_balance_from_snapshot_row,
    portfolio_state_from_loaded_values,
    position_from_snapshot_row,
    positions_from_snapshot_rows,
)


def test_position_from_snapshot_row_normalizes_numeric_fields() -> None:
    """Database rows reconstruct typed position values without a cursor."""
    assert position_from_snapshot_row(("AAPL", "2", "100.5")) == Position("AAPL", 2.0, 100.5)
    assert position_from_snapshot_row(("MSFT", 1, None)) == Position("MSFT", 1.0, None)


def test_position_from_snapshot_row_rejects_missing_symbol() -> None:
    """Invalid rows fail with actionable context before constructing a position."""
    with pytest.raises(ValueError, match="symbol is required"):
        position_from_snapshot_row((None, 1, 100))


def test_positions_from_snapshot_rows_preserves_row_order() -> None:
    """Row reconstruction keeps the database ordering intact."""
    positions = positions_from_snapshot_rows(
        (
            ("AAPL", 2, 100),
            ("MSFT", -1, 250),
        )
    )

    assert positions == [
        Position("AAPL", 2.0, 100.0),
        Position("MSFT", -1.0, 250.0),
    ]


def test_cash_balance_from_snapshot_row_handles_empty_rows() -> None:
    """Cash reconstruction mirrors latest-cash query semantics."""
    assert cash_balance_from_snapshot_row(("1000.25",)) == 1000.25
    assert cash_balance_from_snapshot_row((None,)) is None
    assert cash_balance_from_snapshot_row(None) is None


def test_portfolio_state_from_loaded_values_defaults_missing_cash() -> None:
    """Persisted positions and optional cash reconstruct immutable portfolio state."""
    state = portfolio_state_from_loaded_values(
        positions=(Position("AAPL", 2.0, 100.0),),
        cash_balance=None,
    )

    assert state.positions == {"AAPL": Position("AAPL", 2.0, 100.0)}
    assert state.cash_balance == 0.0
