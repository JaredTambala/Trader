"""Pure reconstruction helpers for persisted portfolio snapshot rows."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .models import PortfolioState, Position


def position_from_snapshot_row(row: Sequence[object]) -> Position:
    """Return a position reconstructed from a snapshot query row.

    Args:
        row: Positional row containing `symbol`, `qty`, and `avg_price`.

    Returns:
        Position with normalized numeric fields.

    Raises:
        ValueError: If the row does not contain a usable symbol.
    """
    symbol = row[0]
    if symbol is None or str(symbol).strip() == "":
        raise ValueError("position snapshot row symbol is required")
    avg_price = row[2]
    return Position(
        symbol=str(symbol),
        qty=float(row[1]),
        avg_price=float(avg_price) if avg_price is not None else None,
    )


def positions_from_snapshot_rows(rows: Iterable[Sequence[object]]) -> list[Position]:
    """Return positions reconstructed from snapshot query rows."""
    return [position_from_snapshot_row(row) for row in rows]


def cash_balance_from_snapshot_row(row: Sequence[object] | None) -> float | None:
    """Return the cash balance from a latest-cash query row."""
    if row and row[0] is not None:
        return float(row[0])
    return None


def portfolio_state_from_loaded_values(
    *,
    positions: Iterable[Position],
    cash_balance: float | None,
) -> PortfolioState:
    """Return a portfolio state reconstructed from persisted values."""
    return PortfolioState(
        positions={position.symbol: position for position in positions},
        cash_balance=cash_balance if cash_balance is not None else 0.0,
    )


__all__ = [
    "cash_balance_from_snapshot_row",
    "portfolio_state_from_loaded_values",
    "position_from_snapshot_row",
    "positions_from_snapshot_rows",
]
