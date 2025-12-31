"""Event store interface for persisting trading system events."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Mapping

import duckdb


class EventStore(ABC):
    """Persists append-only events for traceability."""

    @abstractmethod
    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Record a single event with a typed payload."""

    def close(self) -> None:
        """Release any resources held by the store."""
        return None

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Provide a transactional scope for event writes."""
        yield


class NoOpEventStore(EventStore):
    """Event store used for a no-op cycle."""

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        return None


@dataclass(frozen=True)
class SchemaTable:
    name: str
    create_sql: str


class DuckDBEventStore(EventStore):
    """DuckDB-backed event store with Stage 0 schema enforcement."""

    def __init__(self, db_path: str) -> None:
        self._connection = duckdb.connect(db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        tables = (
            SchemaTable(
                name="run_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT PRIMARY KEY,
                    strategy_id TEXT,
                    mode TEXT,
                    decision_ts TIMESTAMP,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    status TEXT,
                    error_message TEXT
                )
                """,
            ),
            SchemaTable(
                name="market_data_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS market_data_events (
                    symbol TEXT,
                    ts TIMESTAMP,
                    ingested_at TIMESTAMP,
                    price DOUBLE,
                    volume DOUBLE,
                    source TEXT
                )
                """,
            ),
            SchemaTable(
                name="signal_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS signal_events (
                    run_id TEXT,
                    symbol TEXT,
                    signal_value DOUBLE,
                    target_qty DOUBLE,
                    generated_at TIMESTAMP
                )
                """,
            ),
            SchemaTable(
                name="order_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS order_events (
                    client_order_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    symbol TEXT,
                    side TEXT,
                    qty DOUBLE,
                    order_type TEXT,
                    status TEXT,
                    broker_order_id TEXT,
                    created_at TIMESTAMP
                )
                """,
            ),
            SchemaTable(
                name="fill_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS fill_events (
                    client_order_id TEXT,
                    fill_ts TIMESTAMP,
                    fill_qty DOUBLE,
                    fill_price DOUBLE
                )
                """,
            ),
            SchemaTable(
                name="position_snapshots",
                create_sql="""
                CREATE TABLE IF NOT EXISTS position_snapshots (
                    asof_ts TIMESTAMP,
                    symbol TEXT,
                    qty DOUBLE,
                    avg_price DOUBLE
                )
                """,
            ),
            SchemaTable(
                name="config_kv",
                create_sql="""
                CREATE TABLE IF NOT EXISTS config_kv (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """,
            ),
        )

        for table in tables:
            self._connection.execute(table.create_sql)

        self._connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS market_data_events_unique
            ON market_data_events(symbol, ts, source)
            """
        )

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        if event_type not in {
            "run_events",
            "market_data_events",
            "signal_events",
            "order_events",
            "fill_events",
            "position_snapshots",
            "config_kv",
        }:
            raise ValueError(f"Unknown event type: {event_type}")

        columns = ", ".join(payload.keys())
        placeholders = ", ".join(["?"] * len(payload))
        sql = f"INSERT INTO {event_type} ({columns}) VALUES ({placeholders})"
        self._connection.execute(sql, list(payload.values()))

    def close(self) -> None:
        self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self._connection.execute("BEGIN")
        try:
            yield
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
