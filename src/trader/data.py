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
        """Record a single event with a typed payload.

        Args:
            event_type: Name of the target table/event collection.
            payload: Mapping of column names to values.

        Raises:
            Exception: Implementations may raise on insert or validation errors.
        """

    def record_run_start(
        self,
        run_id: str,
        strategy_id: str,
        mode: str,
        decision_ts: object,
        started_at: object,
    ) -> None:
        """Record the start of a run.

        Args:
            run_id: Deterministic run identifier.
            strategy_id: Strategy identifier.
            mode: Execution mode.
            decision_ts: Timestamp used to derive run_id.
            started_at: Timestamp when the run started.

        Raises:
            Exception: Implementations may raise on insert errors.
        """
        self.record_event(
            "run_events",
            {
                "run_id": run_id,
                "strategy_id": strategy_id,
                "mode": mode,
                "decision_ts": decision_ts,
                "started_at": started_at,
                "finished_at": None,
                "status": "started",
                "error_message": None,
            },
        )

    def record_run_finish(
        self,
        run_id: str,
        strategy_id: str,
        mode: str,
        decision_ts: object,
        started_at: object,
        finished_at: object,
        status: str,
        error_message: str | None,
    ) -> None:
        """Record the final status of a run.

        Args:
            run_id: Deterministic run identifier.
            strategy_id: Strategy identifier.
            mode: Execution mode.
            decision_ts: Timestamp used to derive run_id.
            started_at: Timestamp when the run started.
            finished_at: Timestamp when the run finished.
            status: Terminal status string.
            error_message: Optional error message when failed.

        Raises:
            Exception: Implementations may raise on insert/update errors.
        """
        self.record_event(
            "run_events",
            {
                "run_id": run_id,
                "strategy_id": strategy_id,
                "mode": mode,
                "decision_ts": decision_ts,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "error_message": error_message,
            },
        )

    def close(self) -> None:
        """Release any resources held by the store.

        Raises:
            None.
        """
        return None

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Provide a transactional scope for event writes.

        Yields:
            None.

        Raises:
            Exception: Implementations may raise on commit/rollback errors.
        """
        yield


class NoOpEventStore(EventStore):
    """Event store used for a no-op cycle."""

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Discard events without persisting them.

        Args:
            event_type: Name of the event type.
            payload: Event payload.

        Raises:
            None.
        """
        return None


@dataclass(frozen=True)
class SchemaTable:
    """Container for named schema DDL."""
    name: str
    create_sql: str


class DuckDBEventStore(EventStore):
    """DuckDB-backed event store with Stage 0 schema enforcement."""

    def __init__(self, db_path: str) -> None:
        """Create a DuckDB event store and initialize the schema.

        Args:
            db_path: Path to the DuckDB file.

        Raises:
            duckdb.Error: If the database cannot be opened or schema fails.
        """
        self._connection = duckdb.connect(db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create schema tables and constraints if needed.

        Raises:
            duckdb.Error: On DDL execution failures.
        """
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
                name="stock_bar_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS stock_bar_events (
                    symbol TEXT,
                    timeframe TEXT,
                    ts TIMESTAMP,
                    ingested_at TIMESTAMP,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume DOUBLE,
                    trade_count DOUBLE,
                    vwap DOUBLE,
                    source TEXT
                )
                """,
            ),
            SchemaTable(
                name="crypto_bar_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS crypto_bar_events (
                    symbol TEXT,
                    timeframe TEXT,
                    ts TIMESTAMP,
                    ingested_at TIMESTAMP,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume DOUBLE,
                    trade_count DOUBLE,
                    vwap DOUBLE,
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
            ALTER TABLE stock_bar_events
            ADD COLUMN IF NOT EXISTS timeframe TEXT
            """
        )
        self._connection.execute(
            """
            UPDATE stock_bar_events
            SET timeframe = '1Min'
            WHERE timeframe IS NULL
            """
        )
        self._connection.execute("DROP INDEX IF EXISTS stock_bar_events_unique")
        self._connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS stock_bar_events_unique
            ON stock_bar_events(symbol, timeframe, ts, source)
            """
        )
        self._connection.execute(
            """
            ALTER TABLE crypto_bar_events
            ADD COLUMN IF NOT EXISTS timeframe TEXT
            """
        )
        self._connection.execute(
            """
            UPDATE crypto_bar_events
            SET timeframe = '1Min'
            WHERE timeframe IS NULL
            """
        )
        self._connection.execute("DROP INDEX IF EXISTS crypto_bar_events_unique")
        self._connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS crypto_bar_events_unique
            ON crypto_bar_events(symbol, timeframe, ts, source)
            """
        )

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Insert a payload into the requested event table.

        Args:
            event_type: Name of the target table.
            payload: Mapping of column names to values.

        Raises:
            ValueError: If event_type is unsupported.
            duckdb.Error: If the insert fails.
        """
        if event_type not in {
            "run_events",
            "stock_bar_events",
            "crypto_bar_events",
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

    def record_run_start(
        self,
        run_id: str,
        strategy_id: str,
        mode: str,
        decision_ts: object,
        started_at: object,
    ) -> None:
        """Insert a started run record if it does not already exist.

        Args:
            run_id: Deterministic run identifier.
            strategy_id: Strategy identifier.
            mode: Execution mode.
            decision_ts: Timestamp used to derive run_id.
            started_at: Timestamp when the run started.

        Raises:
            duckdb.Error: If the insert fails.
        """
        self._connection.execute(
            """
            INSERT INTO run_events (
                run_id,
                strategy_id,
                mode,
                decision_ts,
                started_at,
                finished_at,
                status,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, NULL, 'started', NULL)
            ON CONFLICT (run_id) DO NOTHING
            """,
            [run_id, strategy_id, mode, decision_ts, started_at],
        )

    def record_run_finish(
        self,
        run_id: str,
        strategy_id: str,
        mode: str,
        decision_ts: object,
        started_at: object,
        finished_at: object,
        status: str,
        error_message: str | None,
    ) -> None:
        """Upsert the final run status record.

        Args:
            run_id: Deterministic run identifier.
            strategy_id: Strategy identifier.
            mode: Execution mode.
            decision_ts: Timestamp used to derive run_id.
            started_at: Timestamp when the run started.
            finished_at: Timestamp when the run finished.
            status: Terminal status string.
            error_message: Optional error message when failed.

        Raises:
            duckdb.Error: If the insert/update fails.
        """
        self._connection.execute(
            """
            INSERT INTO run_events (
                run_id,
                strategy_id,
                mode,
                decision_ts,
                started_at,
                finished_at,
                status,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (run_id) DO UPDATE SET
                finished_at = excluded.finished_at,
                status = excluded.status,
                error_message = excluded.error_message
            """,
            [
                run_id,
                strategy_id,
                mode,
                decision_ts,
                started_at,
                finished_at,
                status,
                error_message,
            ],
        )

    def close(self) -> None:
        """Close the DuckDB connection.

        Raises:
            duckdb.Error: If closing the connection fails.
        """
        self._connection.close()

    def connection(self) -> duckdb.DuckDBPyConnection:
        """Expose the underlying DuckDB connection for advanced operations."""
        return self._connection

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Wrap operations in an explicit DuckDB transaction.

        Yields:
            None.

        Raises:
            duckdb.Error: If begin/commit/rollback fails.
        """
        self._connection.execute("BEGIN")
        try:
            yield
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
