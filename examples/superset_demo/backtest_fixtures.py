"""Generate Superset backtest fixtures through Trader's production replay path.

The market bars in this module are deterministic replay inputs. All run rows,
orders, fills, positions, lifecycle state, and metrics snapshots are generated
by :class:`trader.backtest.BacktestRunner` and the event-store persistence
contracts. The command is restricted to the dedicated Superset demo database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from typing import Callable, Sequence

import psycopg

from trader.backtest import (
    BacktestAssumptions,
    BacktestRunner,
    BacktestSpec,
    DataAssumptions,
    serialize_backtest_result,
)
from trader.backtest.persistence_payloads import build_backtest_metrics_snapshot_payload
from trader.config import build_config
from trader.event_store import PostgresEventStore
from trader.event_store.console_read_contract import install_console_read_contract
from trader.event_store.schema import POSTGRES_SCHEMA_STATEMENTS
from trader.strategies import Strategy
from trader_standard.risk import NoOpRiskManager
from trader_standard.strategies import NoOpStrategy, ToggleUnitStrategy

from .database import DATABASE, OWNER
from .runtime import DemoStack


FIXTURE_SOURCE = "superset-backtest-fixture"
FIXTURE_PREFIX = "superset_fixture_"
BASE_TS = datetime(2026, 1, 20, 14, 30, tzinfo=UTC)


@dataclass(frozen=True)
class FixtureCase:
    """Describe one backtest scenario generated for dashboard review."""

    name: str
    symbols: tuple[str, ...]
    prices: dict[str, tuple[float, ...]]
    strategy_factory: Callable[[], Strategy]
    max_runs: int | None = None
    allow_price_carry_forward: bool = True
    initial_cash: float = 10_000.0
    expect_failure: bool = False


class _UniverseNoOpStrategy(NoOpStrategy):
    """Run the no-op strategy on synchronized symbols to expose missing bars."""

    @property
    def decision_scope(self) -> str:
        """Require complete symbol alignment at each replay timestamp."""
        return "universe_snapshot"

    @property
    def strategy_id(self) -> str:
        """Return a stable fixture-specific strategy identifier."""
        return "fixture_universe_noop"


class _FailingStrategy(NoOpStrategy):
    """Raise inside the production cycle to preserve a failed-run example."""

    def __init__(self) -> None:
        self._calls = 0

    @property
    def strategy_id(self) -> str:
        """Return a stable fixture-specific strategy identifier."""
        return "fixture_failure"

    def generate_orders(self, **kwargs: object) -> Sequence[dict[str, object]]:
        """Fail after the first production strategy invocation."""
        del kwargs
        self._calls += 1
        if self._calls > 1:
            raise RuntimeError("intentional Superset fixture failure")
        return []


def fixture_cases() -> tuple[FixtureCase, ...]:
    """Return deterministic cases covering the dashboard review states."""
    return (
        FixtureCase(
            "complete_drawdown",
            ("FIX_COMPLETE",),
            {"FIX_COMPLETE": (100.0, 104.0, 108.0, 95.0, 92.0, 98.0)},
            lambda: ToggleUnitStrategy(symbols=("FIX_COMPLETE",), order_qty=2.0),
        ),
        FixtureCase(
            "zero_trade",
            ("FIX_ZERO",),
            {"FIX_ZERO": (100.0, 101.0, 100.5, 101.5)},
            NoOpStrategy,
        ),
        FixtureCase(
            "multi_symbol",
            ("FIX_MULTI_A", "FIX_MULTI_B"),
            {
                "FIX_MULTI_A": (100.0, 102.0, 101.0, 104.0),
                "FIX_MULTI_B": (50.0, 49.0, 51.0, 48.0),
            },
            lambda: ToggleUnitStrategy(symbols=("FIX_MULTI_A", "FIX_MULTI_B"), order_qty=1.0),
        ),
        FixtureCase(
            "partial_run",
            ("FIX_PARTIAL",),
            {"FIX_PARTIAL": (100.0, 101.0, 99.0, 98.0, 100.0)},
            lambda: ToggleUnitStrategy(symbols=("FIX_PARTIAL",), order_qty=1.0),
            max_runs=2,
        ),
        FixtureCase(
            "missing_mark",
            ("FIX_MISSING_A", "FIX_MISSING_B"),
            {
                "FIX_MISSING_A": (100.0, 101.0, 102.0, 103.0, 104.0),
                "FIX_MISSING_B": (50.0, 51.0, 53.0),
            },
            _UniverseNoOpStrategy,
            allow_price_carry_forward=False,
        ),
        FixtureCase(
            "failed_run",
            ("FIX_FAILED",),
            {"FIX_FAILED": (100.0, 101.0, 102.0)},
            _FailingStrategy,
            expect_failure=True,
        ),
    )


def generate_fixtures(stack: DemoStack) -> dict[str, int]:
    """Generate all review cases in the dedicated demo database.

    Existing rows from this fixture namespace are removed first so reruns are
    deterministic. No rows outside ``FIXTURE_SOURCE`` or ``FIXTURE_PREFIX``
    are changed.
    """
    _bootstrap_database(stack)
    cases = fixture_cases()
    with psycopg.connect(stack.dsn()) as connection:
        _clear_fixture_rows(connection)
        _insert_input_bars(connection, cases)
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.name] = _run_case(stack, case)
    return counts


def _bootstrap_database(stack: DemoStack) -> None:
    """Ensure the dedicated database has the core and Console schemas."""
    with psycopg.connect(stack.dsn()) as connection:
        identity = connection.execute("SELECT current_database(), session_user").fetchone()
        if identity != (DATABASE, OWNER):
            raise RuntimeError("Refusing to generate fixtures outside the Superset demo database")
        for statement in POSTGRES_SCHEMA_STATEMENTS:
            connection.execute(statement)
        install_console_read_contract(connection)


def _clear_fixture_rows(connection: psycopg.Connection) -> None:
    """Delete only rows owned by this fixture namespace."""
    for table in (
        "metrics_snapshots", "fill_events", "order_events", "position_snapshots",
        "signal_events", "indicator_events", "run_events", "runs", "experiment_runs",
    ):
        connection.execute(
            f"DELETE FROM {table} WHERE run_id LIKE %s",
            (f"{FIXTURE_PREFIX}%",),
        )
    for table in ("stock_bar_events", "crypto_bar_events"):
        connection.execute(f"DELETE FROM {table} WHERE source = %s", (FIXTURE_SOURCE,))


def _insert_input_bars(connection: psycopg.Connection, cases: Sequence[FixtureCase]) -> None:
    """Insert replay inputs with idempotent conflict checks in the demo database."""
    for case in cases:
        for symbol, prices in case.prices.items():
            for index, price in enumerate(prices):
                ts = BASE_TS + timedelta(minutes=index)
                connection.execute(
                    """
                    INSERT INTO crypto_bar_events
                        (symbol, timeframe, ts, ingested_at, open, high, low, close, volume, source)
                    SELECT %s, '1Min', %s, %s, %s, %s, %s, %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM crypto_bar_events
                        WHERE symbol = %s AND timeframe = '1Min' AND ts = %s AND source = %s
                    )
                    """,
                    (
                        symbol, ts, ts, price, price + 1.0, price - 1.0, price,
                        1000.0 + index * 100.0, FIXTURE_SOURCE,
                        symbol, ts, FIXTURE_SOURCE,
                    ),
                )


def _run_case(stack: DemoStack, case: FixtureCase) -> int:
    """Run one case through BacktestRunner and persist its canonical evidence."""
    run_id = f"{FIXTURE_PREFIX}{case.name}"
    experiment_id = "superset_backtest_review"
    experiment_run_id = f"{run_id}_experiment"
    config_data = _config_data(stack, case)
    config = build_config(config_data)
    assumptions = BacktestAssumptions(
        fill_model="full_fill",
        latency_ms=0.0,
        data=DataAssumptions(
            allow_latest_prior_bar=True,
            allow_price_carry_forward=case.allow_price_carry_forward,
        ),
    )
    store = PostgresEventStore(dsn=stack.dsn())
    started_at = BASE_TS - timedelta(minutes=1)
    store.upsert_experiment(
        experiment_id=experiment_id,
        name="Superset backtest review fixtures",
        description="Generated by Trader BacktestRunner for local Superset review.",
        tags=("superset", "fixture", "backtest"),
        created_at=started_at,
        updated_at=started_at,
    )
    store.record_experiment_run_start(
        experiment_run_id=experiment_run_id,
        experiment_id=experiment_id,
        run_id=run_id,
        created_at=started_at,
        strategy_id=case.strategy_factory().strategy_id,
        strategy_name=case.name,
        strategy_version="fixture",
        symbols=case.symbols,
        asset_class="crypto",
        timeframe="1Min",
        start_ts=BASE_TS,
        end_ts=BASE_TS + timedelta(minutes=5),
        assumptions={"allow_price_carry_forward": case.allow_price_carry_forward},
        provenance={"generator": "trader.backtest.BacktestRunner", "fixture_case": case.name},
        data_quality={"source": FIXTURE_SOURCE},
    )
    try:
        result = BacktestRunner(
            config=config,
            spec=BacktestSpec(
                start=BASE_TS,
                end=BASE_TS + timedelta(minutes=5),
                timeframe="1Min",
                max_runs=case.max_runs,
            ),
            symbols=case.symbols,
            asset_class="crypto",
            event_store=store,
            initial_cash=case.initial_cash,
            strategy=case.strategy_factory(),
            risk_manager=NoOpRiskManager(),
            assumptions=assumptions,
            config_snapshot={"fixture_case": case.name, "source": FIXTURE_SOURCE},
            run_id=run_id,
            started_at=started_at,
        ).run()
    except Exception as exc:
        if not case.expect_failure:
            store.close()
            raise
        store.record_experiment_run_finish(
            experiment_run_id=experiment_run_id,
            experiment_id=experiment_id,
            run_id=run_id,
            status="failed",
            finished_at=datetime.now(UTC),
            error_message=str(exc),
            provenance={"generator": "trader.backtest.BacktestRunner", "fixture_case": case.name},
        )
        store.close()
        return 0
    payload = serialize_backtest_result(result)
    store.record_experiment_run_finish(
        experiment_run_id=experiment_run_id,
        experiment_id=experiment_id,
        run_id=run_id,
        status="partial" if case.max_runs is not None else "completed",
        finished_at=result.finished_at,
        result_summary=payload,
        provenance={"generator": "trader.backtest.BacktestRunner", "fixture_case": case.name},
    )
    store.record_event(
        "metrics_snapshots",
        build_backtest_metrics_snapshot_payload(run_id=run_id, result=result, ts=result.finished_at),
    )
    store.close()
    return int(result.total_runs)


def _config_data(stack: DemoStack, case: FixtureCase) -> dict[str, object]:
    """Build explicit local config for the injected production runner."""
    return {
        "runtime": {"mode": "once"},
        "logging": {"persist": {"signals": True, "indicators": True, "orders": True, "fills": True, "positions": True}},
        "strategy": {"id": case.name, "timeframe": "1Min"},
        "broker": {"type": "internal", "time_in_force": "day"},
        "market_data": {"source": "event_store", "asset_class": "crypto", "symbols": list(case.symbols)},
        "alpaca": {},
        "database": {
            "event_store": "postgres",
            "pg": {"host": "127.0.0.1", "port": stack.database_port, "db": DATABASE, "user": OWNER, "password": ""},
        },
        "metrics": {"enable_snapshots": False, "interval_seconds": 0},
    }


def fixture_summary(stack: DemoStack) -> list[dict[str, object]]:
    """Return generated rows for human and test verification."""
    with psycopg.connect(stack.dsn()) as connection:
        rows = connection.execute(
            """
            SELECT experiment_run_id, run_id, status, symbols, timeframe, result_summary
            FROM experiment_runs
            WHERE experiment_id = %s
            ORDER BY experiment_run_id
            """,
            ("superset_backtest_review",),
        ).fetchall()
    return [
        {
            "experiment_run_id": row[0],
            "run_id": row[1],
            "status": row[2],
            "symbols": row[3],
            "timeframe": row[4],
            "result_summary": row[5] if isinstance(row[5], dict) else json.loads(row[5]) if row[5] else None,
        }
        for row in rows
    ]
