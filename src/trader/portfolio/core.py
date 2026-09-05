"""Mutable portfolio shell for applying orders and creating snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Iterable, Mapping

from ..event_store import EventStore
from .models import PortfolioOrder, PortfolioOrderApplication, PortfolioState, Position
from .persistence import load_latest_cash, load_latest_portfolio_state, load_latest_positions
from .snapshots import (
    PortfolioSnapshot,
    PortfolioSnapshotState,
    build_cash_neutral_snapshot,
    build_portfolio_snapshot,
)
from .transitions import apply_portfolio_order, apply_portfolio_order_mappings, apply_portfolio_orders


logger = logging.getLogger(__name__)


__all__ = [
    "Portfolio",
    "PortfolioOrder",
    "PortfolioOrderApplication",
    "PortfolioSnapshot",
    "PortfolioState",
    "Position",
    "apply_portfolio_order",
    "apply_portfolio_orders",
    "load_latest_cash",
    "load_latest_portfolio_state",
    "load_latest_positions",
    "snapshot_now",
]


@dataclass
class Portfolio:
    """Mutable in-memory portfolio used during one cycle or backtest replay.

    The object tracks the current position map and cash balance. Callers mutate
    it with executed order/fill evidence, then persist immutable snapshots for
    audit and later reconstruction.
    """

    positions: dict[str, Position] = field(default_factory=dict)
    cash_balance: float = 0.0

    @classmethod
    def empty(cls, *, cash_balance: float = 0.0) -> Portfolio:
        """Create a portfolio with no positions and the requested cash balance."""
        return cls(positions={}, cash_balance=cash_balance)

    @classmethod
    def from_event_store(cls, event_store: EventStore, *, asof_ts: datetime | None = None) -> Portfolio:
        """Reconstruct current or historical portfolio state from snapshots.

        Args:
            event_store: Store exposing position snapshot rows.
            asof_ts: Optional upper timestamp bound for backtest-safe reads.

        Returns:
            Portfolio containing the latest position per symbol and latest cash
            balance at or before `asof_ts`.
        """
        state = load_latest_portfolio_state(event_store, asof_ts=asof_ts)
        return cls(positions=dict(state.positions), cash_balance=state.cash_balance)

    def apply_orders(
        self,
        orders: Iterable[Mapping[str, object]],
        *,
        price_lookup: Mapping[str, float] | None = None,
    ) -> None:
        """Apply order intents to the portfolio state.

        Args:
            orders: Iterable of order mappings (symbol, side, qty).
            price_lookup: Optional mapping of symbol to reference price.

        Raises:
            ValueError: If an order contains an invalid side or quantity.
        """
        price_lookup = price_lookup or {}
        orders_list = list(orders)
        if not orders_list:
            logger.info("Portfolio apply skipped; no orders provided")
            return
        logger.info("Applying portfolio orders count=%s", len(orders_list))
        order_application = apply_portfolio_order_mappings(
            PortfolioState(positions=self.positions, cash_balance=self.cash_balance),
            tuple(orders_list),
            price_lookup=price_lookup,
        )
        for portfolio_order in order_application.orders:
            logger.debug(
                "Applying order symbol=%s side=%s qty=%s",
                portfolio_order.symbol,
                portfolio_order.side,
                portfolio_order.qty,
            )
        result = order_application.application
        self.positions = dict(result.state.positions)
        self.cash_balance = result.state.cash_balance
        for skipped_symbol in result.cash_update_skipped_symbols:
            logger.warning("Cash update skipped; missing price for order symbol=%s", skipped_symbol)

    def snapshot(
        self,
        *,
        asof_ts: datetime | None = None,
        run_id: str | None = None,
        cycle_id: str | None = None,
        session_id: str | None = None,
    ) -> PortfolioSnapshot:
        """Create a snapshot of the current portfolio state.

        Args:
            asof_ts: Timestamp for the snapshot; defaults to now (UTC).

        Returns:
            PortfolioSnapshot with positions sorted by symbol.
        """
        return build_portfolio_snapshot(
            state=PortfolioSnapshotState(
                positions=self.positions,
                cash_balance=self.cash_balance,
            ),
            asof_ts=asof_ts or datetime.now(timezone.utc),
            run_id=run_id,
            cycle_id=cycle_id,
            session_id=session_id,
        )


def snapshot_now(positions: Iterable[Position]) -> PortfolioSnapshot:
    """Create a cash-neutral snapshot for legacy callers with explicit positions.

    Newer runtime paths prefer `Portfolio.snapshot()` because it preserves cash
    and run/cycle correlation IDs.
    """
    return build_cash_neutral_snapshot(
        asof_ts=datetime.now(timezone.utc),
        positions=tuple(positions),
    )
