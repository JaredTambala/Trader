"""Cycle stream-state and universe-barrier contracts.

Subject: Per-event stream decisions, latest prices, and synchronized universe strategy invocation.
Level: In-process asynchronous stream contract tests.
Collaborators: Real stream planners, in-memory queues, temporary DuckDB, and deterministic strategy/broker fakes.
Guarantees: Freshness policy and universe alignment control exactly when normalized orders reach the queue.
Non-goals: Provider streaming, concurrent workers, broker execution, recovery, or long-running service behavior.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone

from tests.support.duckdb_store import DuckDBEventStore
from tests.trader.cycle.factories import (
    build_cycle_config as _base_config,
    stock_event as _stock_event,
)
from trader.cycle.stream import (
    CycleStreamRuntime,
    _build_cycle_stream_state,
    _latest_stream_prices,
    _plan_cycle_stream_market_event,
)
from trader.cycle.stream_pipeline import _generate_universe_snapshot_orders
from trader.market_data import StockBarEvent
from trader.portfolio import Portfolio
from trader.strategies import Strategy
from trader_standard.risk import NoOpRiskManager


class UniverseOrderStrategy(Strategy):
    """Record synchronized callbacks and emit one order per configured symbol."""

    def __init__(self) -> None:
        self.calls: list[datetime] = []

    @property
    def strategy_id(self) -> str:
        return "universe_order"

    @property
    def decision_scope(self) -> str:
        return "universe_snapshot"

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store,
        portfolio,
    ):
        del run_id, cycle_id, event_store, portfolio
        self.calls.append(decision_ts)
        return [
            {"symbol": symbol, "side": "buy", "qty": 1.0, "order_type": "market"}
            for symbol in ("AAPL", "MSFT")
        ]


class _UnusedBroker:
    def submit_orders(self, orders):
        del orders
        return ()


def test_cycle_stream_state_starts_empty_and_exposes_latest_prices() -> None:
    """Initialize empty stream counters and project stored latest prices without timestamps."""
    ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    state = _build_cycle_stream_state()

    assert state.processed_orders == []
    assert state.latest_prices == {}
    assert state.counters.orders_emitted == 0

    state.latest_prices["AAPL"] = (ts, 101.25)
    state.latest_prices["MSFT"] = (ts, 250.5)

    assert _latest_stream_prices(state) == {"AAPL": 101.25, "MSFT": 250.5}


def test_plan_cycle_stream_market_event_normalizes_fresh_event() -> None:
    """Normalize a fresh stream event into an executable per-symbol decision plan."""
    event_ts = datetime(2026, 1, 20, 12, 0)
    event = _stock_event(ts=event_ts, close=101.25)

    plan = _plan_cycle_stream_market_event(
        event,
        enforce_staleness=True,
        now=datetime(2026, 1, 20, 12, 0, 30, tzinfo=timezone.utc),
        max_age_seconds=60,
    )

    assert plan.symbol == "AAPL"
    assert plan.decision_ts == event_ts.replace(tzinfo=timezone.utc)
    assert plan.close_price == 101.25
    assert plan.should_skip is False
    assert plan.freshness.age_seconds == 30.0


def test_plan_cycle_stream_market_event_skips_stale_event_only_when_enforced() -> None:
    """Expose staleness consistently while skipping only when enforcement is enabled."""
    event = _stock_event(ts=datetime(2026, 1, 20, 11, 58, tzinfo=timezone.utc))
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)

    enforced = _plan_cycle_stream_market_event(
        event,
        enforce_staleness=True,
        now=now,
        max_age_seconds=60,
    )
    unenforced = _plan_cycle_stream_market_event(
        event,
        enforce_staleness=False,
        now=now,
        max_age_seconds=60,
    )

    assert enforced.freshness.is_stale is True
    assert enforced.should_skip is True
    assert unenforced.freshness.is_stale is True
    assert unenforced.should_skip is False


def test_stream_universe_barrier_invokes_strategy_once_for_aligned_symbols(
    tmp_path,
) -> None:
    """Release one universe decision only after aligned events for every symbol arrive."""
    store = DuckDBEventStore(str(tmp_path / "universe-stream.duckdb"))
    strategy = UniverseOrderStrategy()
    config = replace(
        _base_config(str(tmp_path / "universe-stream.duckdb")),
        market_data_symbols=("AAPL", "MSFT"),
    )
    decision_ts = datetime.now(timezone.utc)
    events = [
        StockBarEvent(
            symbol=symbol,
            timeframe="1Min",
            ts=decision_ts,
            ingested_at=decision_ts,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1.0,
            trade_count=None,
            vwap=None,
            source="test",
        )
        for symbol, price in (("AAPL", 100.0), ("MSFT", 200.0))
    ]

    async def _run() -> list[object]:
        event_queue = asyncio.Queue()
        order_queue = asyncio.Queue()
        for event in events:
            await event_queue.put(event)
        await event_queue.put(None)
        await _generate_universe_snapshot_orders(
            runtime=CycleStreamRuntime(
                event_store=store,
                strategy=strategy,
                broker=_UnusedBroker(),
                portfolio=Portfolio.empty(cash_balance=100_000.0),
                run_id="run_1",
                cycle_id="cycle_1",
                max_age_seconds=300,
                enforce_staleness=True,
                asset_class="stocks",
                time_in_force="day",
                sync_portfolio_on_fill=False,
                broker_type="noop",
                config=config,
                risk_manager=NoOpRiskManager(),
            ),
            state=_build_cycle_stream_state(),
            event_queue=event_queue,
            order_queue=order_queue,
        )
        return [
            await order_queue.get(),
            await order_queue.get(),
            await order_queue.get(),
        ]

    orders = asyncio.run(_run())

    assert strategy.calls == [decision_ts]
    assert [order["symbol"] for order in orders[:-1]] == ["AAPL", "MSFT"]
    assert orders[-1] is None
