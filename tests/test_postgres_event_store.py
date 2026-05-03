from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trader.data import PostgresEventStore


pytestmark = pytest.mark.postgres


def test_postgres_event_store_initializes_runtime_schema(
    postgres_event_store: PostgresEventStore,
) -> None:
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
    }
    assert expected.issubset(tables)


def test_postgres_bar_events_are_idempotent_on_symbol_timeframe_ts_source(
    postgres_event_store: PostgresEventStore,
) -> None:
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

    count = postgres_event_store.connection().execute(
        "SELECT COUNT(*) FROM stock_bar_events WHERE symbol = %s",
        ["AAPL"],
    ).fetchone()[0]
    assert count == 1


def test_postgres_run_and_cycle_lifecycle_upserts_status(
    postgres_event_store: PostgresEventStore,
) -> None:
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

    run_row = postgres_event_store.connection().execute(
        "SELECT status, finished_at FROM runs WHERE run_id = %s",
        ["run_postgres"],
    ).fetchone()
    cycle_row = postgres_event_store.connection().execute(
        "SELECT status, finished_at FROM run_events WHERE cycle_id = %s",
        ["cycle_postgres"],
    ).fetchone()
    session_row = postgres_event_store.connection().execute(
        "SELECT status, finished_at FROM trading_sessions WHERE session_id = %s",
        ["run_postgres"],
    ).fetchone()

    assert run_row == ("success", finished_at)
    assert cycle_row == ("success", finished_at)
    assert session_row == ("success", finished_at)


def test_postgres_order_events_remain_append_only_and_preserve_session_id(
    postgres_event_store: PostgresEventStore,
) -> None:
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

    rows = postgres_event_store.connection().execute(
        """
        SELECT status, session_id
        FROM order_events
        WHERE client_order_id = %s
        ORDER BY created_at
        """,
        ["order_1"],
    ).fetchall()
    assert rows == [("created", "run_1"), ("validated", "run_1"), ("submitted", "run_1")]


def test_postgres_metrics_snapshots_persist_run_cycle_and_session_ids(
    postgres_event_store: PostgresEventStore,
) -> None:
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

    row = postgres_event_store.connection().execute(
        """
        SELECT run_id, session_id, cycle_id, payload
        FROM metrics_snapshots
        WHERE run_id = %s
        """,
        ["run_metrics"],
    ).fetchone()
    assert row == ("run_metrics", "run_metrics", "cycle_metrics", '{"equity": 1000.0}')
