"""Cycle event-persistence integration contracts.

Subject: Indicator, order-lifecycle, and fill records emitted by a complete isolated cycle.
Level: DuckDB-backed in-process integration contracts.
Collaborators: Real cycle pipeline and standard signal components with temporary DuckDB and static bars.
Guarantees: Enabled indicators and internal fills leave the required append-only audit evidence.
Non-goals: Postgres behavior, live brokers, provider data, recovery, or statistical strategy quality.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from tests.support.duckdb_store import DuckDBEventStore
from tests.trader.cycle.factories import build_cycle_config as _base_config
from trader.cycle import run_cycle
from trader.market_data import StaticMarketDataSource, StockBarEvent
from trader.portfolio import Portfolio
from trader.signals import Bar
from trader.strategies import Strategy
from trader_standard.indicators import SmaIndicator
from trader_standard.risk import NoOpRiskManager
from trader_standard.signal_generators import InMemoryBarsSignalGenerator
from trader_standard.signals import SmaCrossoverSignal
from trader_standard.strategies import SimpleStrategy


class SingleOrderStrategy(Strategy):
    """Strategy that always emits a single buy order."""

    @property
    def strategy_id(self) -> str:
        return "single_order"

    def generate_orders(
        self,
        *,
        run_id: str,
        cycle_id: str,
        decision_ts: datetime,
        event_store,
        portfolio,
    ):
        return [
            {
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "order_type": "market",
            }
        ]


def test_indicator_events_persisted(tmp_path) -> None:
    """Persist indicator calculations when cycle diagnostic logging is explicitly enabled."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    base_ts = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    bars = [
        Bar(
            ts=base_ts - timedelta(minutes=3),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
            vwap=None,
            trade_count=None,
        ),
        Bar(
            ts=base_ts - timedelta(minutes=2),
            open=101,
            high=102,
            low=100,
            close=101,
            volume=1,
            vwap=None,
            trade_count=None,
        ),
        Bar(
            ts=base_ts - timedelta(minutes=1),
            open=102,
            high=103,
            low=101,
            close=102,
            volume=1,
            vwap=None,
            trade_count=None,
        ),
        Bar(
            ts=base_ts,
            open=103,
            high=104,
            low=102,
            close=103,
            volume=1,
            vwap=None,
            trade_count=None,
        ),
    ]
    signal = SmaCrossoverSignal(SmaIndicator(period=2), SmaIndicator(period=3))
    generator = InMemoryBarsSignalGenerator(
        bars_by_symbol={"AAPL": bars},
        signals=[signal],
        symbols=["AAPL"],
        timeframe="1Min",
        event_store=store,
    )
    strategy = SimpleStrategy(signal_generator=generator, primary_signal=signal.name)

    event = StockBarEvent(
        symbol="AAPL",
        timeframe="1Min",
        ts=base_ts,
        ingested_at=base_ts,
        open=103,
        high=104,
        low=102,
        close=103,
        volume=10,
        trade_count=None,
        vwap=None,
        source="test",
    )

    config = replace(_base_config(str(tmp_path / "events.duckdb")), mode="backtest")
    run_cycle(
        event_store=store,
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        market_data_source=StaticMarketDataSource([event]),
        config=config,
        decision_ts=base_ts,
        ingest_market_data=False,
        portfolio=Portfolio.from_event_store(store, asof_ts=base_ts),
    )

    count = (
        store.connection()
        .execute("SELECT COUNT(*) FROM indicator_events")
        .fetchone()[0]
    )
    assert count > 0


def test_order_lifecycle_and_fill_events(tmp_path) -> None:
    """Persist every internal order transition and exactly one resulting fill event."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    event = StockBarEvent(
        symbol="AAPL",
        timeframe="1Min",
        ts=now,
        ingested_at=now,
        open=100,
        high=101,
        low=99,
        close=100.5,
        volume=10,
        trade_count=None,
        vwap=None,
        source="test",
    )

    config = replace(
        _base_config(str(tmp_path / "events.duckdb")),
        broker_type="internal",
        mode="backtest",
    )

    strategy = SingleOrderStrategy()
    run_cycle(
        event_store=store,
        strategy=strategy,
        risk_manager=NoOpRiskManager(),
        market_data_source=StaticMarketDataSource([event]),
        config=config,
        decision_ts=now,
        ingest_market_data=False,
        portfolio=Portfolio.from_event_store(store, asof_ts=now),
    )

    statuses = {
        row[0]
        for row in store.connection()
        .execute("SELECT status FROM order_events")
        .fetchall()
    }
    assert {"created", "validated", "submitted", "filled"}.issubset(statuses)

    fill_count = (
        store.connection().execute("SELECT COUNT(*) FROM fill_events").fetchone()[0]
    )
    assert fill_count == 1
