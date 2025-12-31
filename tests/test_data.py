from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

from trader.data import DuckDBEventStore


def test_duckdb_event_store_initializes_schema(tmp_path: Path) -> None:
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
        "run_events",
        "market_data_events",
        "signal_events",
        "order_events",
        "fill_events",
        "position_snapshots",
        "config_kv",
    }
    assert expected.issubset(tables)


def test_duplicate_client_order_id_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "events.duckdb"
    store = DuckDBEventStore(str(db_path))

    payload = {
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
    with pytest.raises(duckdb.ConstraintException):
        store.record_event("order_events", payload)


def test_high_frequency_market_data_inserts(tmp_path: Path) -> None:
    db_path = tmp_path / "events.duckdb"
    store = DuckDBEventStore(str(db_path))

    base_ts = datetime.now(timezone.utc)
    for index in range(200):
        store.record_event(
            "market_data_events",
            {
                "symbol": "AAPL",
                "ts": base_ts + timedelta(milliseconds=index),
                "ingested_at": datetime.now(timezone.utc),
                "price": 100.0 + index,
                "volume": 10.0,
                "source": "test",
            },
        )

    conn = duckdb.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM market_data_events").fetchone()[0]
    assert count == 200
