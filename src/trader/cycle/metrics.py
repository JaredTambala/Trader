"""Pure metrics snapshot builders for decision cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Mapping, Sequence

from ..market_data import MarketDataEvent
from ..portfolio import Position
from .market_data import _build_price_lookup


@dataclass(frozen=True)
class MetricsSnapshotPayload:
    """Computed portfolio metrics payload for a cycle snapshot."""

    equity: float
    cash: float
    net_exposure: float
    gross_exposure: float
    asset_class: str
    symbols: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        """Return the JSON-compatible metrics payload."""
        return {
            "equity": self.equity,
            "cash": self.cash,
            "net_exposure": self.net_exposure,
            "gross_exposure": self.gross_exposure,
            "asset_class": self.asset_class,
            "symbols": list(self.symbols),
        }


@dataclass(frozen=True)
class MetricsSnapshotEvent:
    """Event-store record for one computed metrics snapshot."""

    ts: datetime
    run_id: str
    session_id: str
    cycle_id: str | None
    payload: MetricsSnapshotPayload

    def to_record(self) -> dict[str, object]:
        """Return an event-store-compatible metrics snapshot record."""
        return {
            "ts": self.ts,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "cycle_id": self.cycle_id,
            "payload": json.dumps(self.payload.to_payload()),
        }


def build_metrics_snapshot_payload(
    *,
    positions: Mapping[str, Position],
    cash_balance: float,
    price_lookup: Mapping[str, float],
    asset_class: str,
    symbols: Sequence[str],
) -> MetricsSnapshotPayload:
    """Compute portfolio equity and exposure metrics without side effects.

    Args:
        positions: Current positions keyed by symbol.
        cash_balance: Current portfolio cash balance.
        price_lookup: Current prices keyed by symbol.
        asset_class: Configured asset class for the cycle.
        symbols: Configured trading symbols for the cycle.

    Returns:
        Immutable metrics payload. Positions without a current price are
        excluded from exposure and equity calculations.
    """
    equity = cash_balance
    net = 0.0
    gross = 0.0
    for position in positions.values():
        price = price_lookup.get(position.symbol)
        if price is None:
            continue
        notional = position.qty * price
        equity += notional
        net += notional
        gross += abs(notional)
    return MetricsSnapshotPayload(
        equity=equity,
        cash=cash_balance,
        net_exposure=net,
        gross_exposure=gross,
        asset_class=asset_class,
        symbols=tuple(symbols),
    )


def build_metrics_snapshot_event(
    *,
    positions: Mapping[str, Position],
    cash_balance: float,
    price_lookup: Mapping[str, float],
    asof_ts: datetime,
    run_id: str,
    cycle_id: str | None,
    asset_class: str,
    symbols: Sequence[str],
) -> MetricsSnapshotEvent:
    """Build a metrics snapshot event from explicit portfolio inputs."""
    return MetricsSnapshotEvent(
        ts=asof_ts,
        run_id=run_id,
        session_id=run_id,
        cycle_id=cycle_id,
        payload=build_metrics_snapshot_payload(
            positions=positions,
            cash_balance=cash_balance,
            price_lookup=price_lookup,
            asset_class=asset_class,
            symbols=symbols,
        ),
    )


def _resolve_metrics_price_lookup(
    *,
    price_lookup: Mapping[str, float],
    market_data_events: Sequence[MarketDataEvent],
) -> Mapping[str, float]:
    """Return the price lookup used for metrics snapshots."""
    if price_lookup:
        return price_lookup
    if market_data_events:
        return _build_price_lookup(market_data_events)
    return {}


__all__ = [
    "MetricsSnapshotEvent",
    "MetricsSnapshotPayload",
    "build_metrics_snapshot_event",
    "build_metrics_snapshot_payload",
]
