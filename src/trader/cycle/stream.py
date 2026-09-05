"""Market-stream runtime value objects for decision cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from ..broker import Broker
from ..config import Config
from ..event_store import EventStore
from ..market_data import MarketDataEvent
from ..portfolio import Portfolio
from ..risk import RiskManager
from ..strategies import Strategy
from .readiness import MarketDataEventFreshness, assess_market_data_event_freshness


@dataclass(frozen=True)
class CycleStreamRuntime:
    """Immutable dependencies shared by market-stream pipeline stages."""

    event_store: EventStore
    strategy: Strategy
    broker: Broker
    portfolio: Portfolio
    run_id: str
    cycle_id: str
    max_age_seconds: int
    enforce_staleness: bool
    asset_class: str
    time_in_force: str
    sync_portfolio_on_fill: bool
    broker_type: str
    config: Config
    risk_manager: RiskManager


@dataclass
class CycleStreamCounters:
    """Mutable counters for one market-stream pipeline execution."""

    orders_emitted: int = 0
    orders_rejected_locally: int = 0
    orders_validated: int = 0
    orders_submitted: int = 0
    broker_responses: int = 0


@dataclass
class CycleStreamState:
    """Mutable state accumulated while market-stream pipeline stages run."""

    processed_orders: list[Mapping[str, object]]
    latest_prices: dict[str, tuple[datetime, float]]
    counters: CycleStreamCounters


@dataclass(frozen=True)
class CycleStreamMarketEventPlan:
    """Pure per-event plan consumed by the streaming order generator."""

    symbol: str
    decision_ts: datetime
    close_price: float
    should_skip: bool
    freshness: MarketDataEventFreshness


def _build_cycle_stream_state() -> CycleStreamState:
    """Create empty mutable state for one market-stream pipeline run."""
    return CycleStreamState(
        processed_orders=[],
        latest_prices={},
        counters=CycleStreamCounters(),
    )


def _latest_stream_prices(state: CycleStreamState) -> Mapping[str, float]:
    """Return latest stream prices in the legacy mapping shape."""
    return {symbol: price for symbol, (_, price) in state.latest_prices.items()}


def _plan_cycle_stream_market_event(
    event: MarketDataEvent,
    *,
    enforce_staleness: bool,
    now: datetime,
    max_age_seconds: int,
) -> CycleStreamMarketEventPlan:
    """Plan stream event handling without logging, mutation, or queue effects."""
    freshness = assess_market_data_event_freshness(
        event,
        now=now,
        max_age_seconds=max_age_seconds,
    )
    return CycleStreamMarketEventPlan(
        symbol=event.symbol,
        decision_ts=freshness.ts,
        close_price=float(event.close),
        should_skip=enforce_staleness and freshness.is_stale,
        freshness=freshness,
    )


__all__ = [
    "CycleStreamCounters",
    "CycleStreamMarketEventPlan",
    "CycleStreamRuntime",
    "CycleStreamState",
    "_plan_cycle_stream_market_event",
]
