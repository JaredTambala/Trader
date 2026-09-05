"""Guarded integration contracts for the Postgres event-store adapter.

Subject: Schema bootstrap, lifecycle persistence, idempotent bars, append-only events, and status queries.
Level: Real-Postgres adapter integration contracts.
Collaborators: PostgresEventStore, runtime status helpers, isolated fixtures, and the guarded test database.
Guarantees: Public persistence behavior round-trips canonical records while preserving identity and history.
Non-goals: Migration from production schemas, concurrent writers, failure recovery, or performance qualification.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trader.config import Config
from trader.event_store import PostgresEventStore
from trader.runtime.status import runtime_status, set_halt_state


pytestmark = pytest.mark.postgres


def test_postgres_event_store_initializes_runtime_schema(
    postgres_event_store: PostgresEventStore,
) -> None:
    """Ensure adapter initialization creates every required runtime table."""
    connection = postgres_event_store.connection()
    tables = {
        row[0]
        for row in connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        ).fetchall()
    }
    expected = {
        "runs",
        "trading_sessions",
        "run_events",
        "stock_bar_events",
        "crypto_bar_events",
        "signal_events",
        "indicator_events",
        "order_events",
        "fill_events",
        "position_snapshots",
        "metrics_snapshots",
        "config_kv",
        "experiments",
        "experiment_runs",
    }
    assert expected.issubset(tables)
    fill_columns = {
        row[0]
        for row in connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'fill_events'
            """
        ).fetchall()
    }
    assert {"raw_fill_price", "slippage_amount", "fee_amount"}.issubset(fill_columns)


def test_postgres_experiment_run_lifecycle(
    postgres_event_store: PostgresEventStore,
) -> None:
    """Ensure experiment definitions and run transitions round-trip through Postgres."""
    now = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    postgres_event_store.upsert_experiment(
        experiment_id="exp_demo",
        name="demo",
        description="Demo experiment",
        tags=("sample",),
        created_at=now,
        updated_at=now,
        metadata={"owner": "test"},
    )
    postgres_event_store.record_experiment_run_start(
        experiment_run_id="exp_run_1",
        experiment_id="exp_demo",
        run_id="run_1",
        created_at=now,
        strategy_id="trend_following",
        strategy_name="Trend",
        strategy_version="1",
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start_ts=now,
        end_ts=now,
        parameters={"fast": 2},
        assumptions={"slippage_bps": 10},
        provenance={"config_hash": "abc"},
        data_quality={"report_id": "dq_1"},
        artifact_dir="artifacts/demo/run_1",
    )
    postgres_event_store.record_experiment_run_finish(
        experiment_run_id="exp_run_1",
        experiment_id="exp_demo",
        run_id="run_1",
        status="success",
        finished_at=now,
        result_summary={"total_return": 0.1},
        provenance={"config_hash": "abc"},
        data_quality={"report_id": "dq_1"},
        artifact_dir="artifacts/demo/run_1",
    )

    rows = postgres_event_store.list_experiment_runs("exp_demo")
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    assert rows[0]["parameters"] == {"fast": 2}
    assert rows[0]["result_summary"] == {"total_return": 0.1}


def test_postgres_bar_events_are_idempotent_on_symbol_timeframe_ts_source(
    postgres_event_store: PostgresEventStore,
) -> None:
    """Ensure repeated bars with one natural identity produce one stored event."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    payload = {
        "symbol": "AAPL",
        "timeframe": "1Min",
        "ts": timestamp,
        "ingested_at": timestamp,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 10.0,
        "trade_count": None,
        "vwap": None,
        "source": "test",
    }

    postgres_event_store.record_event("stock_bar_events", payload)
    postgres_event_store.record_event("stock_bar_events", payload)

    count = (
        postgres_event_store.connection()
        .execute(
            "SELECT COUNT(*) FROM stock_bar_events WHERE symbol = %s",
            ["AAPL"],
        )
        .fetchone()[0]
    )
    assert count == 1


def test_postgres_run_and_cycle_lifecycle_upserts_status(
    postgres_event_store: PostgresEventStore,
) -> None:
    """Ensure terminal run and cycle writes update their persisted lifecycle rows."""
    started_at = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    finished_at = started_at + timedelta(seconds=3)
    decision_ts = started_at

    postgres_event_store.record_run_session_start(
        run_id="run_postgres",
        run_type="trading",
        started_at=started_at,
        strategy_id="demo",
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )
    postgres_event_store.record_cycle_start(
        run_id="run_postgres",
        cycle_id="cycle_postgres",
        strategy_id="demo",
        mode="once",
        decision_ts=decision_ts,
        started_at=started_at,
    )
    postgres_event_store.record_cycle_finish(
        run_id="run_postgres",
        cycle_id="cycle_postgres",
        strategy_id="demo",
        mode="once",
        decision_ts=decision_ts,
        started_at=started_at,
        finished_at=finished_at,
        status="success",
        error_message=None,
    )
    postgres_event_store.record_run_session_finish(
        run_id="run_postgres",
        run_type="trading",
        started_at=started_at,
        finished_at=finished_at,
        status="success",
        error_message=None,
        strategy_id="demo",
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )

    run_row = (
        postgres_event_store.connection()
        .execute(
            "SELECT status, finished_at FROM runs WHERE run_id = %s",
            ["run_postgres"],
        )
        .fetchone()
    )
    cycle_row = (
        postgres_event_store.connection()
        .execute(
            "SELECT status, finished_at FROM run_events WHERE cycle_id = %s",
            ["cycle_postgres"],
        )
        .fetchone()
    )
    session_row = (
        postgres_event_store.connection()
        .execute(
            "SELECT status, finished_at FROM trading_sessions WHERE session_id = %s",
            ["run_postgres"],
        )
        .fetchone()
    )

    assert run_row == ("success", finished_at)
    assert cycle_row == ("success", finished_at)
    assert session_row == ("success", finished_at)


def test_postgres_order_events_remain_append_only_and_preserve_session_id(
    postgres_event_store: PostgresEventStore,
) -> None:
    """Ensure order transitions append distinct rows with stable session lineage."""
    created_at = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    for index, status in enumerate(("created", "validated", "submitted"), start=1):
        postgres_event_store.record_event(
            "order_events",
            {
                "order_event_id": f"order_evt_{index}",
                "client_order_id": "order_1",
                "run_id": "run_1",
                "session_id": "run_1",
                "cycle_id": "cycle_1",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 1.0,
                "order_type": "market",
                "status": status,
                "broker_order_id": None,
                "rejection_reason": None,
                "created_at": created_at + timedelta(seconds=index),
            },
        )

    rows = (
        postgres_event_store.connection()
        .execute(
            """
        SELECT status, session_id
        FROM order_events
        WHERE client_order_id = %s
        ORDER BY created_at
        """,
            ["order_1"],
        )
        .fetchall()
    )
    assert rows == [
        ("created", "run_1"),
        ("validated", "run_1"),
        ("submitted", "run_1"),
    ]


def test_postgres_metrics_snapshots_persist_run_cycle_and_session_ids(
    postgres_event_store: PostgresEventStore,
) -> None:
    """Ensure metric snapshots retain all runtime lineage identifiers."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    postgres_event_store.record_event(
        "metrics_snapshots",
        {
            "ts": timestamp,
            "run_id": "run_metrics",
            "session_id": "run_metrics",
            "cycle_id": "cycle_metrics",
            "payload": '{"equity": 1000.0}',
        },
    )

    row = (
        postgres_event_store.connection()
        .execute(
            """
        SELECT run_id, session_id, cycle_id, payload
        FROM metrics_snapshots
        WHERE run_id = %s
        """,
            ["run_metrics"],
        )
        .fetchone()
    )
    assert row == ("run_metrics", "run_metrics", "cycle_metrics", '{"equity": 1000.0}')


def test_postgres_fill_events_support_null_cost_fields_for_old_rows(
    postgres_event_store: PostgresEventStore,
) -> None:
    """Ensure historical fill shapes without cost fields remain writable and readable."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    postgres_event_store.record_event(
        "fill_events",
        {
            "client_order_id": "legacy_fill",
            "run_id": "run_legacy",
            "session_id": "run_legacy",
            "cycle_id": "cycle_legacy",
            "fill_ts": timestamp,
            "fill_qty": 1.0,
            "fill_price": 100.0,
        },
    )

    row = (
        postgres_event_store.connection()
        .execute(
            """
        SELECT raw_fill_price, slippage_amount, fee_amount
        FROM fill_events
        WHERE client_order_id = %s
        """,
            ["legacy_fill"],
        )
        .fetchone()
    )
    assert row == (None, None, None)


def test_postgres_halt_state_round_trip(
    postgres_event_store: PostgresEventStore,
) -> None:
    """Ensure the operator halt flag and reason round-trip through configuration storage."""
    now = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)

    state = set_halt_state(
        postgres_event_store, halted=True, reason="operator test", now=now
    )

    assert state == {
        "halted": True,
        "reason": "operator test",
        "updated_at": now.isoformat(),
    }
    row = (
        postgres_event_store.connection()
        .execute(
            "SELECT value FROM config_kv WHERE key = %s",
            ["halt"],
        )
        .fetchone()
    )
    assert row == ("true",)


def test_postgres_runtime_status_queries_latest_cycle_and_open_orders(
    postgres_event_store: PostgresEventStore,
) -> None:
    """Ensure runtime status selects the latest cycle and currently open orders."""
    now = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    postgres_event_store.record_run_session_start(
        "run_status", "trading", now, strategy_id="demo"
    )
    postgres_event_store.record_cycle_start(
        "run_status", "cycle_status", "demo", "loop", now, now
    )
    postgres_event_store.record_cycle_finish(
        "run_status",
        "cycle_status",
        "demo",
        "loop",
        now,
        now,
        now,
        "success",
        None,
    )
    postgres_event_store.record_run_session_finish(
        "run_status",
        "trading",
        now,
        now,
        "success",
        None,
        strategy_id="demo",
    )
    postgres_event_store.record_event(
        "stock_bar_events",
        {
            "symbol": "AAPL",
            "timeframe": "1Min",
            "ts": now,
            "ingested_at": now,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "trade_count": None,
            "vwap": None,
            "source": "test",
        },
    )
    postgres_event_store.record_event(
        "order_events",
        {
            "order_event_id": "order_evt_pg_status",
            "client_order_id": "cid_pg_status",
            "run_id": "run_status",
            "session_id": "run_status",
            "cycle_id": "cycle_status",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 1.0,
            "order_type": "market",
            "status": "submitted",
            "broker_order_id": "broker_pg_status",
            "rejection_reason": None,
            "created_at": now,
        },
    )

    status = runtime_status(postgres_event_store, _status_config(), now=now)

    assert status["latest_cycle"]["cycle_id"] == "cycle_status"
    assert status["open_orders"]["count"] == 1
    assert status["market_data"]["stale_count"] == 0


def _status_config() -> Config:
    return Config(
        mode="loop",
        strategy_type="demo",
        strategy_id="demo",
        strategy_timeframe="1Min",
        sma_short_window=2,
        sma_long_window=3,
        db_path="",
        event_store="postgres",
        market_data_source="noop",
        market_data_asset_class="stocks",
        market_data_stock_feed="iex",
        market_data_symbols=("AAPL",),
        market_data_max_age_seconds=60,
        alpaca_api_key="",
        alpaca_secret_key="",
        alpaca_data_base_url="https://data.alpaca.markets",
        alpaca_base_url="https://paper-api.alpaca.markets",
        pg_dsn="",
        pg_host="",
        pg_port=5432,
        pg_db="",
        pg_user="",
        pg_password="",
        buffered_event_store=False,
        buffer_flush_interval_ms=250,
        buffer_max_batch_size=500,
        buffer_max_queue_size=10000,
        buffer_block_on_full=True,
        log_signal_events=True,
        log_indicator_events=True,
        log_order_events=True,
        log_fill_events=True,
        log_position_snapshots=True,
        broker_type="noop",
    )
