"""Portfolio primitives for tracking positions over time."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Iterable, Mapping, Sequence

from .data import EventStore


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Position:
    """Single-symbol position snapshot."""

    symbol: str
    qty: float
    avg_price: float | None


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Portfolio state at a point in time."""

    asof_ts: datetime
    positions: Sequence[Position]
    cash_balance: float
    run_id: str | None = None
    cycle_id: str | None = None

    def persist(self, event_store: EventStore) -> None:
        """Persist the snapshot to the event store."""
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
                },
            )


@dataclass
class Portfolio:
    """In-memory portfolio state derived from persisted snapshots."""

    positions: dict[str, Position] = field(default_factory=dict)
    cash_balance: float = 0.0

    @classmethod
    def empty(cls, *, cash_balance: float = 0.0) -> Portfolio:
        """Create an empty portfolio."""
        return cls(positions={}, cash_balance=cash_balance)

    @classmethod
    def from_event_store(cls, event_store: EventStore, *, asof_ts: datetime | None = None) -> Portfolio:
        """Load the latest positions per symbol from the event store."""
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

            delta = qty_float if side == "buy" else -qty_float
            price = order.get("price")
            if price is None:
                price = price_lookup.get(symbol)
            price_value = float(price) if price is not None else None

            current = self.positions.get(symbol, Position(symbol=symbol, qty=0.0, avg_price=None))
            new_qty = current.qty + delta
            new_avg = _compute_avg_price(current, delta, new_qty, price_value)

            if price_value is None:
                logger.warning("Cash update skipped; missing price for order symbol=%s", symbol)
            else:
                notional = qty_float * price_value
                if side == "buy":
                    self.cash_balance -= notional
                else:
                    self.cash_balance += notional

            if abs(new_qty) < 1e-12:
                self.positions.pop(symbol, None)
                continue

            self.positions[symbol] = Position(symbol=symbol, qty=new_qty, avg_price=new_avg)

    def snapshot(
        self,
        *,
        asof_ts: datetime | None = None,
        run_id: str | None = None,
        cycle_id: str | None = None,
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
        )


def load_latest_positions(event_store: EventStore, *, asof_ts: datetime | None = None) -> list[Position]:
    """Load the latest position per symbol from the event store."""
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
    """Load the latest cash balance from the event store."""
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
    """Create a snapshot using the current UTC time."""
    return PortfolioSnapshot(
        asof_ts=datetime.now(timezone.utc),
        positions=tuple(positions),
        cash_balance=0.0,
    )


def _compute_avg_price(
    current: Position,
    delta: float,
    new_qty: float,
    price: float | None,
) -> float | None:
    """Compute the new average price after applying a trade delta."""
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


def _param_placeholder(connection: object) -> str:
    """Return the SQL parameter placeholder for the active backend."""
    module = connection.__class__.__module__
    if module.startswith("duckdb"):
        return "?"
    return "%s"
