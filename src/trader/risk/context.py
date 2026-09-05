"""Typed context supplied to risk managers during order validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

from ..portfolio import Position


@dataclass(frozen=True)
class RiskContext:
    """Immutable market, portfolio, and runtime facts supplied to risk checks.

    Attributes:
        positions: Current positions keyed by symbol.
        open_orders: Latest local order lifecycle records still relevant to risk.
        price_lookup: Latest close/fill prices keyed by symbol.
        run_id: Run/session identifier for audit-aware risk decisions.
        cycle_id: Decision-cycle identifier for emitted rejection reasons.
        decision_ts: Timestamp of the decision being evaluated.
        halted: Whether the operator global halt flag is active.
    """

    positions: Mapping[str, Position]
    open_orders: Sequence[Mapping[str, object]]
    price_lookup: Mapping[str, float]
    run_id: str
    cycle_id: str
    decision_ts: datetime
    halted: bool = False
