"""Tests for DuckDB event store schema and constraints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from tests.support.duckdb_store import DuckDBEventStore


def test_duckdb_event_store_initializes_schema(tmp_path: Path) -> None:
    """Verify schema initialization creates required tables.

    Args:
        tmp_path: Pytest temporary path fixture.

    Raises:
        AssertionError: If expected tables are missing.
    """
    db_path = tmp_path / "events.duckdb"
    DuckDBEventStore(str(db_path))

    conn = duckdb.connect(str(db_path))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }

    expected = {
        "runs",
        "run_events",
        "stock_bar_events",
        "crypto_bar_events",
        "signal_events",
        "indicator_events",
        "order_events",
        "fill_events",
        "position_snapshots",
        "config_kv",
    }
    assert expected.issubset(tables)


def test_duplicate_client_order_id_allowed(tmp_path: Path) -> None:
    """Ensure duplicate client_order_id inserts are allowed.

    Args:
        tmp_path: Pytest temporary path fixture.

    Raises:
        AssertionError: If append-only inserts are not persisted.
    """
    db_path = tmp_path / "events.duckdb"
    store = DuckDBEventStore(str(db_path))

    payload = {
        "order_event_id": "order_evt_1",
        "client_order_id": "order-1",
        "run_id": "run-1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "order_type": "market",
        "status": "created",
        "broker_order_id": None,
        "created_at": datetime.now(timezone.utc),
    }

    store.record_event("order_events", payload)
    payload["order_event_id"] = "order_evt_2"
    store.record_event("order_events", payload)

    conn = duckdb.connect(str(db_path))
    count = conn.execute(
        "SELECT COUNT(*) FROM order_events WHERE client_order_id = 'order-1'"
    ).fetchone()[0]
    assert count == 2


def test_high_frequency_market_data_inserts(tmp_path: Path) -> None:
    """Insert many stock bar events to validate append performance.

    Args:
        tmp_path: Pytest temporary path fixture.

    Raises:
        AssertionError: If the insert count is incorrect.
    """
    db_path = tmp_path / "events.duckdb"
    store = DuckDBEventStore(str(db_path))

    base_ts = datetime.now(timezone.utc)
    for index in range(200):
        store.record_event(
            "stock_bar_events",
            {
                "symbol": "AAPL",
                "timeframe": "1Min",
                "ts": base_ts + timedelta(milliseconds=index),
                "ingested_at": datetime.now(timezone.utc),
                "open": 100.0 + index,
                "high": 101.0 + index,
                "low": 99.0 + index,
                "close": 100.5 + index,
                "volume": 10.0,
                "trade_count": None,
                "vwap": None,
                "source": "test",
            },
        )

    conn = duckdb.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM stock_bar_events").fetchone()[0]
    assert count == 200


def test_run_lifecycle_updates_status(tmp_path: Path) -> None:
    """Verify run session + cycle lifecycle upserts update status fields.

    Args:
        tmp_path: Pytest temporary path fixture.

    Raises:
        AssertionError: If the run status or timestamps are missing.
    """
    db_path = tmp_path / "events.duckdb"
    store = DuckDBEventStore(str(db_path))

    decision_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    started_at = decision_ts
    finished_at = decision_ts + timedelta(seconds=1)

    store.record_run_session_start(
        run_id="run-123",
        run_type="trading",
        started_at=started_at,
        mode="once",
    )
    store.record_cycle_start(
        run_id="run-123",
        cycle_id="cycle-123",
        strategy_id="demo",
        mode="once",
        decision_ts=decision_ts,
        started_at=started_at,
    )
    store.record_cycle_finish(
        run_id="run-123",
        cycle_id="cycle-123",
        strategy_id="demo",
        mode="once",
        decision_ts=decision_ts,
        started_at=started_at,
        finished_at=finished_at,
        status="success",
        error_message=None,
    )
    store.record_run_session_finish(
        run_id="run-123",
        run_type="trading",
        started_at=started_at,
        finished_at=finished_at,
        status="success",
        error_message=None,
        mode="once",
    )

    conn = duckdb.connect(str(db_path))
    run_status, run_started, run_finished, run_error = conn.execute(
        "SELECT status, started_at, finished_at, error_message FROM runs WHERE run_id = ?",
        ["run-123"],
    ).fetchone()
    assert run_status == "success"
    assert run_started is not None
    assert run_finished is not None
    assert run_error is None

    cycle_status, cycle_started, cycle_finished, cycle_error = conn.execute(
        "SELECT status, started_at, finished_at, error_message FROM run_events WHERE cycle_id = ?",
        ["cycle-123"],
    ).fetchone()
    assert cycle_status == "success"
    assert cycle_started is not None
    assert cycle_finished is not None
    assert cycle_error is None
