"""Portfolio primitives for tracking positions over time."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Iterable, Mapping, Sequence

from ..event_store import EventStore
from .order_inputs import normalize_portfolio_order_inputs
from .order_math import cash_balance_after_order, compute_avg_price
from .snapshots import (
    build_position_snapshot_events,
    latest_cash_query_plan,
    latest_positions_query_plan,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Position:
    """Position quantity and cost basis for one symbol.

    Attributes:
        symbol: Canonical symbol spelling used by runtime config and brokers.
        qty: Signed position quantity; negative values represent shorts.
        avg_price: Average entry price for the open position when known.
    """

    symbol: str
    qty: float
    avg_price: float | None


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Portfolio state persisted as one row per position at a timestamp.

    An empty portfolio is represented by a single row with `symbol=None` so cash
    can still be reconstructed from the event store.
    """

    asof_ts: datetime
    positions: Sequence[Position]
    cash_balance: float
    run_id: str | None = None
    cycle_id: str | None = None
    session_id: str | None = None

    def persist(self, event_store: EventStore) -> None:
        """Append this snapshot to the event store.

        Each position becomes one `position_snapshots` event with the same cash
        balance and correlation IDs. When no positions exist, a sentinel row is
        written so cash-only state is not lost.
        """
        for event in build_position_snapshot_events(
            asof_ts=self.asof_ts,
            positions=self.positions,
            cash_balance=self.cash_balance,
            run_id=self.run_id,
            cycle_id=self.cycle_id,
            session_id=self.session_id,
        ):
            event_store.record_event(event.event_type, event.payload)


@dataclass(frozen=True)
class PortfolioState:
    """Immutable portfolio state used by pure position/cash calculations.

    Attributes:
        positions: Current positions keyed by symbol. Callers may pass any
            mapping; calculation helpers copy before updating.
        cash_balance: Cash balance before applying portfolio decisions.
    """

    positions: Mapping[str, Position]
    cash_balance: float


@dataclass(frozen=True)
class PortfolioOrder:
    """Validated order input for pure portfolio state transitions.

    Attributes:
        symbol: Canonical symbol being traded.
        side: Normalized order side, either `buy` or `sell`.
        qty: Positive order quantity.
        price: Optional execution/reference price used for cash and cost basis.
        fee_amount: Fee charged for the order.
    """

    symbol: str
    side: str
    qty: float
    price: float | None = None
    fee_amount: float = 0.0

    def __post_init__(self) -> None:
        """Validate the normalized order before state transitions use it."""
        if not self.symbol.strip():
            raise ValueError("portfolio order symbol is required")
        if self.side not in {"buy", "sell"}:
            raise ValueError(f"portfolio order side must be buy or sell: {self.side}")
        if self.qty <= 0:
            raise ValueError("portfolio order qty must be positive")

    @property
    def signed_qty_delta(self) -> float:
        """Return the signed position quantity delta represented by the order."""
        return self.qty if self.side == "buy" else -self.qty


@dataclass(frozen=True)
class PortfolioOrderApplication:
    """Result of applying one or more orders to immutable portfolio state.

    Attributes:
        state: Updated portfolio state.
        cash_update_skipped_symbols: Symbols whose cash update was skipped
            because no execution/reference price was available.
    """

    state: PortfolioState
    cash_update_skipped_symbols: tuple[str, ...] = ()


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
        positions = {
            position.symbol: position for position in load_latest_positions(event_store, asof_ts=asof_ts)
        }
        cash_balance = load_latest_cash(event_store, asof_ts=asof_ts)
        if cash_balance is None:
            cash_balance = 0.0
        return cls(positions=positions, cash_balance=cash_balance)

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
        portfolio_orders = normalize_portfolio_order_inputs(
            tuple(orders_list),
            price_lookup=price_lookup,
        )
        for order_input in portfolio_orders:
            logger.debug(
                "Applying order symbol=%s side=%s qty=%s",
                order_input.symbol,
                order_input.side,
                order_input.qty,
            )
            portfolio_order = PortfolioOrder(
                symbol=order_input.symbol,
                side=order_input.side,
                qty=order_input.qty,
                price=order_input.price,
                fee_amount=order_input.fee_amount,
            )
            result = apply_portfolio_order(
                PortfolioState(positions=self.positions, cash_balance=self.cash_balance),
                portfolio_order,
            )
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
        timestamp = asof_ts or datetime.now(timezone.utc)
        positions = tuple(self.positions[symbol] for symbol in sorted(self.positions))
        return PortfolioSnapshot(
            asof_ts=timestamp,
            positions=positions,
            cash_balance=self.cash_balance,
            run_id=run_id,
            cycle_id=cycle_id,
            session_id=session_id or run_id,
        )


def load_latest_positions(event_store: EventStore, *, asof_ts: datetime | None = None) -> list[Position]:
    """Load one latest non-empty position snapshot per symbol.

    Args:
        event_store: Store with a SQL connection.
        asof_ts: Optional upper timestamp bound; used by backtests to avoid
            reading future snapshots.

    Returns:
        Position objects reconstructed from the latest row for each symbol. An
        empty list is returned when the store has no readable connection.
    """
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Portfolio load skipped; event store has no connection")
        return []

    if hasattr(connection, "cursor"):
        with connection.cursor() as cursor:
            plan = latest_positions_query_plan(connection, asof_ts=asof_ts)
            _execute_query_plan(cursor, plan.query, plan.parameters)
            rows = cursor.fetchall()
            positions = [
                Position(
                    symbol=row[0],
                    qty=float(row[1]),
                    avg_price=float(row[2]) if row[2] is not None else None,
                )
                for row in rows
            ]
            logger.info("Loaded portfolio positions count=%s", len(positions))
            return positions

    return []


def load_latest_cash(event_store: EventStore, *, asof_ts: datetime | None = None) -> float | None:
    """Load the latest recorded cash balance from position snapshots.

    Args:
        event_store: Store with a SQL connection.
        asof_ts: Optional upper timestamp bound for historical reconstruction.

    Returns:
        Latest cash balance, or `None` when no snapshot is available.
    """
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None:
        logger.warning("Cash load skipped; event store has no connection")
        return None

    if hasattr(connection, "cursor"):
        with connection.cursor() as cursor:
            plan = latest_cash_query_plan(connection, asof_ts=asof_ts)
            _execute_query_plan(cursor, plan.query, plan.parameters)
            row = cursor.fetchone()
            if row and row[0] is not None:
                return float(row[0])
    return None


def snapshot_now(positions: Iterable[Position]) -> PortfolioSnapshot:
    """Create a cash-neutral snapshot for legacy callers with explicit positions.

    Newer runtime paths prefer `Portfolio.snapshot()` because it preserves cash
    and run/cycle correlation IDs.
    """
    return PortfolioSnapshot(
        asof_ts=datetime.now(timezone.utc),
        positions=tuple(positions),
        cash_balance=0.0,
    )


def apply_portfolio_orders(
    state: PortfolioState,
    orders: Iterable[PortfolioOrder],
) -> PortfolioOrderApplication:
    """Apply validated orders to portfolio state without mutating inputs.

    Args:
        state: Starting portfolio positions and cash balance.
        orders: Validated orders in execution order.

    Returns:
        Updated state plus cash-update caveats for the imperative shell to log.
    """
    current_state = PortfolioState(positions=dict(state.positions), cash_balance=state.cash_balance)
    skipped_symbols: list[str] = []
    for order in orders:
        result = apply_portfolio_order(current_state, order)
        current_state = result.state
        skipped_symbols.extend(result.cash_update_skipped_symbols)
    return PortfolioOrderApplication(
        state=current_state,
        cash_update_skipped_symbols=tuple(skipped_symbols),
    )


def apply_portfolio_order(
    state: PortfolioState,
    order: PortfolioOrder,
) -> PortfolioOrderApplication:
    """Apply one validated order to portfolio state without side effects.

    The calculation updates quantity, average price, and cash deterministically.
    Missing prices still update positions and fees, but report a skipped cash
    update so callers can decide how to log or surface the caveat.

    Args:
        state: Starting portfolio positions and cash balance.
        order: Validated order to apply.

    Returns:
        Updated portfolio state and any cash-update skipped symbol.
    """
    positions = dict(state.positions)
    current = positions.get(order.symbol, Position(symbol=order.symbol, qty=0.0, avg_price=None))
    delta = order.signed_qty_delta
    new_qty = current.qty + delta
    new_avg = compute_avg_price(
        current_qty=current.qty,
        current_avg_price=current.avg_price,
        delta=delta,
        new_qty=new_qty,
        price=order.price,
    )
    cash_balance = cash_balance_after_order(
        cash_balance=state.cash_balance,
        side=order.side,
        qty=order.qty,
        price=order.price,
        fee_amount=order.fee_amount,
    )

    if abs(new_qty) < 1e-12:
        positions.pop(order.symbol, None)
    else:
        positions[order.symbol] = Position(symbol=order.symbol, qty=new_qty, avg_price=new_avg)

    skipped = (order.symbol,) if order.price is None else ()
    return PortfolioOrderApplication(
        state=PortfolioState(positions=positions, cash_balance=cash_balance),
        cash_update_skipped_symbols=skipped,
    )


def _execute_query_plan(cursor: object, query: str, parameters: Sequence[object]) -> None:
    """Execute a query plan with DB-API-compatible optional parameters."""
    if parameters:
        cursor.execute(query, list(parameters))
        return
    cursor.execute(query)
