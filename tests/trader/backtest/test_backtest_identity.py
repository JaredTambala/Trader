"""Protect persisted replay evidence from collisions across runs and symbols.

Subject: Backtest cycle, order and fill identity at the production cycle boundary.
Level: In-process integration with persistent SQL event storage.
Collaborators: Real runner, internal broker, deterministic strategy and DuckDB.
Guarantees: Independent replays retain complete, separate evidence in one store.
Non-goals: Live broker retry policy, strategy profitability or database throughput.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from trader.backtest import BacktestRunner, BacktestSpec
from trader.config import build_config
from trader.event_store import EventStore
from trader.strategies import Strategy
from trader_standard.risk import NoOpRiskManager
from tests.support.duckdb_store import DuckDBEventStore


class BuyEachSymbol(Strategy):
    """Emit a deterministic buy to exercise every lifecycle identity."""

    @property
    def strategy_id(self) -> str:
        return "identity-contract"

    def generate_orders(self, **kwargs):
        """Emit one order per symbol; the cycle applies its symbol filter."""
        return [
            {"symbol": symbol, "side": "buy", "qty": 1.0, "order_type": "market"}
            for symbol in ("AAA", "BBB")
        ]


def _run_twice(store: EventStore) -> None:
    """Reconcile two identical replays without clearing the first run's rows."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(3):
        timestamp = start + timedelta(minutes=index)
        for symbol in ("AAA", "BBB"):
            store.record_event("stock_bar_events", {
                "symbol": symbol, "timeframe": "1Min", "ts": timestamp,
                "ingested_at": timestamp, "open": 100.0, "high": 101.0,
                "low": 99.0, "close": 100.0, "volume": 10.0, "source": "test",
            })
    config = build_config({
        "runtime": {"mode": "backtest"},
        "market_data": {"asset_class": "stocks", "symbols": ["AAA", "BBB"]},
        "broker": {"type": "internal"},
    })
    conn = store.connection()
    placeholder = "?" if isinstance(store, DuckDBEventStore) else "%s"
    previous_rows = None
    for run_id in ("replay-first", "replay-second"):
        result = BacktestRunner(
            config, BacktestSpec(start=start, end=start + timedelta(minutes=2), timeframe="1Min"),
            strategy=BuyEachSymbol(), risk_manager=NoOpRiskManager(),
            event_store=store, run_id=run_id, initial_cash=10000.0,
        ).run()
        assert result.total_runs == result.success_runs == 6
        assert len(result.trades) == 6
        rows = conn.execute(
            f"SELECT cycle_id, run_id, decision_ts, finished_at FROM run_events WHERE run_id={placeholder} ORDER BY cycle_id",
            ("replay-first",),
        ).fetchall()
        if previous_rows is not None:
            assert rows == previous_rows
        previous_rows = rows
    for table, identity, expected in (
        ("run_events", "cycle_id", 6),
        ("order_events", "client_order_id", 6),
        ("fill_events", "fill_event_id", 6),
    ):
        rows = conn.execute(
            f"SELECT run_id, COUNT(DISTINCT {identity}) FROM {table} GROUP BY run_id ORDER BY run_id"
        ).fetchall()
        assert rows == [("replay-first", expected), ("replay-second", expected)]
        shared = conn.execute(
            f"SELECT {identity} FROM {table} GROUP BY {identity} HAVING COUNT(DISTINCT run_id) > 1"
        ).fetchall()
        assert shared == []
    composition_rows = conn.execute(
        "SELECT run_id, COUNT(*) FROM risk_compositions GROUP BY run_id ORDER BY run_id"
    ).fetchall()
    assert composition_rows == [("replay-first", 1), ("replay-second", 1)]
    decision_rows = conn.execute(
        "SELECT run_id, COUNT(*) FROM risk_decisions GROUP BY run_id ORDER BY run_id"
    ).fetchall()
    assert decision_rows == [("replay-first", 6), ("replay-second", 6)]


def test_replays_preserve_run_and_symbol_evidence(tmp_path: Path) -> None:
    """Keep every cycle and fill separate when replay windows overlap exactly."""
    store = DuckDBEventStore(str(tmp_path / "replays.duckdb"))
    try:
        _run_twice(store)
    finally:
        store.close()
