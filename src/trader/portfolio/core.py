"""Portfolio primitives for tracking positions over time."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Iterable, Mapping, Sequence

from ..event_store import EventStore


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
        session_id = self.session_id or self.run_id
        if not self.positions:
            event_store.record_event(
                "position_snapshots",
                {
                    "asof_ts": self.asof_ts,
                    "symbol": None,
                    "qty": 0.0,
                    "avg_price": None,
                    "cash_balance": self.cash_balance,
                    "run_id": self.run_id,
                    "cycle_id": self.cycle_id,
                    "session_id": session_id,
                },
            )
            return
        for position in self.positions:
            event_store.record_event(
                "position_snapshots",
                {
                    "asof_ts": self.asof_ts,
                    "symbol": position.symbol,
                    "qty": position.qty,
                    "avg_price": position.avg_price,
                    "cash_balance": self.cash_balance,
                    "run_id": self.run_id,
                    "cycle_id": self.cycle_id,
                    "session_id": session_id,
                },
            )


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
        for order in orders_list:
            symbol = str(order.get("symbol", "")).strip()
            side = str(order.get("side", "")).lower().strip()
            qty = order.get("qty", 0.0)
            logger.debug("Applying order symbol=%s side=%s qty=%s", symbol, side, qty)
            if not symbol:
                continue
            try:
                qty_float = float(qty)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid qty for order: {order}") from exc
            if qty_float <= 0:
                continue
            if side not in {"buy", "sell"}:
                raise ValueError(f"Invalid side for order: {order}")
            price = order.get("price")
            if price is None:
                price = price_lookup.get(symbol)
            price_value = float(price) if price is not None else None
            fee_amount = order.get("fee_amount")
            fee_value = float(fee_amount) if fee_amount is not None else 0.0
            portfolio_order = PortfolioOrder(
                symbol=symbol,
                side=side,
                qty=qty_float,
                price=price_value,
                fee_amount=fee_value,
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
            if asof_ts is None:
                cursor.execute(
                    """
                    SELECT symbol, qty, avg_price
                    FROM (
                        SELECT
                            symbol,
                            qty,
                            avg_price,
                            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY asof_ts DESC) AS rn
                        FROM position_snapshots
                        WHERE symbol IS NOT NULL AND symbol <> ''
                    ) AS ranked
                    WHERE rn = 1
                    """
                )
            else:
                placeholder = _param_placeholder(connection)
                cursor.execute(
                    f"""
                    SELECT symbol, qty, avg_price
                    FROM (
                        SELECT
                            symbol,
                            qty,
                            avg_price,
                            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY asof_ts DESC) AS rn
                        FROM position_snapshots
                        WHERE asof_ts <= {placeholder} AND symbol IS NOT NULL AND symbol <> ''
                    ) AS ranked
                    WHERE rn = 1
                    """,
                    [asof_ts],
                )
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
            if asof_ts is None:
                cursor.execute(
                    """
                    SELECT cash_balance
                    FROM position_snapshots
                    ORDER BY asof_ts DESC
                    LIMIT 1
                    """
                )
            else:
                placeholder = _param_placeholder(connection)
                cursor.execute(
                    f"""
                    SELECT cash_balance
                    FROM position_snapshots
                    WHERE asof_ts <= {placeholder}
                    ORDER BY asof_ts DESC
                    LIMIT 1
                    """,
                    [asof_ts],
                )
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
    new_avg = _compute_avg_price(current, delta, new_qty, order.price)
    cash_balance = _cash_balance_after_order(state.cash_balance, order)

    if abs(new_qty) < 1e-12:
        positions.pop(order.symbol, None)
    else:
        positions[order.symbol] = Position(symbol=order.symbol, qty=new_qty, avg_price=new_avg)

    skipped = (order.symbol,) if order.price is None else ()
    return PortfolioOrderApplication(
        state=PortfolioState(positions=positions, cash_balance=cash_balance),
        cash_update_skipped_symbols=skipped,
    )


def _compute_avg_price(
    current: Position,
    delta: float,
    new_qty: float,
    price: float | None,
) -> float | None:
    """Compute average entry price after a position quantity change.

    Adding to an existing position recalculates weighted average cost. Reducing
    without crossing zero preserves the prior cost basis, closing returns
    `None`, and crossing sides starts the new position at the execution price.
    """
    if new_qty == 0:
        return None
    if price is None:
        return current.avg_price
    if current.qty == 0 or current.avg_price is None:
        return price

    adding_same_side = (current.qty > 0 and delta > 0) or (current.qty < 0 and delta < 0)
    if adding_same_side:
        return ((current.qty * current.avg_price) + (delta * price)) / new_qty

    reducing = abs(delta) < abs(current.qty)
    if reducing:
        return current.avg_price

    return price


def _cash_balance_after_order(cash_balance: float, order: PortfolioOrder) -> float:
    """Return cash balance after one order without mutating portfolio state."""
    if order.price is None:
        return cash_balance - order.fee_amount

    notional = order.qty * order.price
    if order.side == "buy":
        return cash_balance - notional - order.fee_amount
    return cash_balance + notional - order.fee_amount


def _param_placeholder(connection: object) -> str:
    """Return the SQL parameter placeholder for the active backend."""
    module = connection.__class__.__module__
    if module.startswith("duckdb"):
        return "?"
    return "%s"
