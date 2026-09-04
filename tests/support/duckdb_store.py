"""Shared in-process implementation of the core event-store contract for tests.

Subject: Deterministic event, runtime, portfolio, and experiment persistence without an external database.
Level: Shared test infrastructure.
Collaborators: The core ``EventStore`` interface and DuckDB's in-process connection.
Guarantees: Multiple package owners exercise the same SQL-shaped persistence behavior in isolated files.
Non-goals: Postgres compatibility qualification, concurrency guarantees, migration testing, or production use.
Cohesion rationale: The implementation is intentionally one complete ``EventStore`` test double; splitting its
schema and methods would obscure the interface-wide state transitions that its cross-package consumers depend on.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from typing import Iterator, Mapping, Sequence

import duckdb

from trader.event_store import EventStore


@dataclass(frozen=True)
class SchemaTable:
    name: str
    create_sql: str


class DuckDBEventStore(EventStore):
    """DuckDB event store used in tests."""

    def __init__(self, db_path: str) -> None:
        self._connection = duckdb.connect(db_path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        tables = (
            SchemaTable(
                name="runs",
                create_sql="""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    run_type TEXT,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    status TEXT,
                    error_message TEXT,
                    config_snapshot TEXT,
                    mode TEXT,
                    symbols TEXT[],
                    timeframe TEXT,
                    start_ts TIMESTAMP,
                    end_ts TIMESTAMP
                )
                """,
            ),
            SchemaTable(
                name="trading_sessions",
                create_sql="""
                CREATE TABLE IF NOT EXISTS trading_sessions (
                    session_id TEXT PRIMARY KEY,
                    strategy_id TEXT,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    status TEXT,
                    error_message TEXT,
                    config_snapshot TEXT,
                    mode TEXT,
                    symbols TEXT[],
                    timeframe TEXT,
                    start_ts TIMESTAMP,
                    end_ts TIMESTAMP
                )
                """,
            ),
            SchemaTable(
                name="experiments",
                create_sql="""
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    name TEXT UNIQUE,
                    description TEXT,
                    tags TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    metadata TEXT
                )
                """,
            ),
            SchemaTable(
                name="experiment_runs",
                create_sql="""
                CREATE TABLE IF NOT EXISTS experiment_runs (
                    experiment_run_id TEXT PRIMARY KEY,
                    experiment_id TEXT,
                    run_id TEXT,
                    status TEXT,
                    created_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    strategy_id TEXT,
                    strategy_name TEXT,
                    strategy_version TEXT,
                    symbols TEXT,
                    asset_class TEXT,
                    timeframe TEXT,
                    start_ts TIMESTAMP,
                    end_ts TIMESTAMP,
                    parameters TEXT,
                    assumptions TEXT,
                    provenance TEXT,
                    data_quality TEXT,
                    result_summary TEXT,
                    artifact_dir TEXT,
                    error_message TEXT
                )
                """,
            ),
            SchemaTable(
                name="run_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS run_events (
                    cycle_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    session_id TEXT,
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
                    session_id TEXT,
                    cycle_id TEXT,
                    symbol TEXT,
                    signal_name TEXT,
                    signal_value DOUBLE,
                    target_qty DOUBLE,
                    generated_at TIMESTAMP,
                    prediction_event_refs TEXT,
                    mapper_id TEXT,
                    payload TEXT
                )
                """,
            ),
            SchemaTable(
                name="indicator_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS indicator_events (
                    run_id TEXT,
                    session_id TEXT,
                    cycle_id TEXT,
                    symbol TEXT,
                    indicator_name TEXT,
                    value DOUBLE,
                    bar_ts TIMESTAMP,
                    payload TEXT
                )
                """,
            ),
            SchemaTable(
                name="prediction_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS prediction_events (
                    prediction_event_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    session_id TEXT,
                    cycle_id TEXT,
                    deployment_id TEXT,
                    deployment_validation_id TEXT,
                    model_version_id TEXT,
                    feature_set_id TEXT,
                    feature_batch_hash TEXT,
                    decision_ts TIMESTAMP,
                    symbol TEXT,
                    output_name TEXT,
                    semantics TEXT,
                    horizon TEXT,
                    value_payload TEXT,
                    latency_ms DOUBLE,
                    status TEXT,
                    error_message TEXT,
                    payload TEXT
                )
                """,
            ),
            SchemaTable(
                name="order_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS order_events (
                    order_event_id TEXT PRIMARY KEY,
                    client_order_id TEXT,
                    run_id TEXT,
                    session_id TEXT,
                    cycle_id TEXT,
                    symbol TEXT,
                    side TEXT,
                    qty DOUBLE,
                    order_type TEXT,
                    status TEXT,
                    broker_order_id TEXT,
                    rejection_reason TEXT,
                    decision_evidence TEXT,
                    created_at TIMESTAMP
                )
                """,
            ),
            SchemaTable(
                name="fill_events",
                create_sql="""
                CREATE TABLE IF NOT EXISTS fill_events (
                    client_order_id TEXT,
                    run_id TEXT,
                    session_id TEXT,
                    cycle_id TEXT,
                    fill_ts TIMESTAMP,
                    fill_qty DOUBLE,
                    raw_fill_price DOUBLE,
                    slippage_amount DOUBLE,
                    fee_amount DOUBLE,
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
                    avg_price DOUBLE,
                    cash_balance DOUBLE,
                    run_id TEXT,
                    session_id TEXT,
                    cycle_id TEXT
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
            SchemaTable(
                name="metrics_snapshots",
                create_sql="""
                CREATE TABLE IF NOT EXISTS metrics_snapshots (
                    ts TIMESTAMP,
                    run_id TEXT,
                    session_id TEXT,
                    cycle_id TEXT,
                    payload TEXT
                )
                """,
            ),
        )

        for table in tables:
            self._connection.execute(table.create_sql)

        self._connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS stock_bar_events_unique
            ON stock_bar_events(symbol, timeframe, ts, source)
            """
        )
        self._connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS crypto_bar_events_unique
            ON crypto_bar_events(symbol, timeframe, ts, source)
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_experiment_id_idx
            ON experiment_runs(experiment_id)
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_run_id_idx
            ON experiment_runs(run_id)
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_status_idx
            ON experiment_runs(status)
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_created_at_idx
            ON experiment_runs(created_at)
            """
        )

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        if event_type not in {
            "runs",
            "run_events",
            "stock_bar_events",
            "crypto_bar_events",
            "signal_events",
            "indicator_events",
            "prediction_events",
            "order_events",
            "fill_events",
            "position_snapshots",
            "config_kv",
            "metrics_snapshots",
            "trading_sessions",
            "experiments",
            "experiment_runs",
        }:
            raise ValueError(f"Unknown event type: {event_type}")

        columns = ", ".join(payload.keys())
        placeholders = ", ".join(["?"] * len(payload))
        insert = "INSERT OR IGNORE" if event_type in {"stock_bar_events", "crypto_bar_events"} else "INSERT"
        sql = f"{insert} INTO {event_type} ({columns}) VALUES ({placeholders})"
        self._connection.execute(sql, list(payload.values()))

    def record_run_session_start(
        self,
        run_id: str,
        run_type: str,
        started_at: object,
        *,
        status: str = "started",
        strategy_id: str | None = None,
        config_snapshot: object | None = None,
        mode: str | None = None,
        symbols: Sequence[str] | None = None,
        timeframe: str | None = None,
        start_ts: object | None = None,
        end_ts: object | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO runs (
                run_id,
                run_type,
                started_at,
                finished_at,
                status,
                error_message,
                config_snapshot,
                mode,
                symbols,
                timeframe,
                start_ts,
                end_ts
            )
            VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (run_id) DO NOTHING
            """,
            [
                run_id,
                run_type,
                started_at,
                status,
                config_snapshot,
                mode,
                list(symbols) if symbols is not None else None,
                timeframe,
                start_ts,
                end_ts,
            ],
        )
        if run_type == "trading":
            self._connection.execute(
                """
                INSERT INTO trading_sessions (
                    session_id,
                    strategy_id,
                    started_at,
                    finished_at,
                    status,
                    error_message,
                    config_snapshot,
                    mode,
                    symbols,
                    timeframe,
                    start_ts,
                    end_ts
                )
                VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (session_id) DO NOTHING
                """,
                [
                    run_id,
                    strategy_id,
                    started_at,
                    status,
                    config_snapshot,
                    mode,
                    list(symbols) if symbols is not None else None,
                    timeframe,
                    start_ts,
                    end_ts,
                ],
            )

    def record_run_session_finish(
        self,
        run_id: str,
        run_type: str,
        started_at: object,
        finished_at: object,
        status: str,
        error_message: str | None,
        *,
        strategy_id: str | None = None,
        config_snapshot: object | None = None,
        mode: str | None = None,
        symbols: Sequence[str] | None = None,
        timeframe: str | None = None,
        start_ts: object | None = None,
        end_ts: object | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO runs (
                run_id,
                run_type,
                started_at,
                finished_at,
                status,
                error_message,
                config_snapshot,
                mode,
                symbols,
                timeframe,
                start_ts,
                end_ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (run_id) DO UPDATE SET
                finished_at = excluded.finished_at,
                status = excluded.status,
                error_message = excluded.error_message
            """,
            [
                run_id,
                run_type,
                started_at,
                finished_at,
                status,
                error_message,
                config_snapshot,
                mode,
                list(symbols) if symbols is not None else None,
                timeframe,
                start_ts,
                end_ts,
            ],
        )
        if run_type == "trading":
            self._connection.execute(
                """
                INSERT INTO trading_sessions (
                    session_id,
                    strategy_id,
                    started_at,
                    finished_at,
                    status,
                    error_message,
                    config_snapshot,
                    mode,
                    symbols,
                    timeframe,
                    start_ts,
                    end_ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (session_id) DO UPDATE SET
                    finished_at = excluded.finished_at,
                    status = excluded.status,
                    error_message = excluded.error_message
                """,
                [
                    run_id,
                    strategy_id,
                    started_at,
                    finished_at,
                    status,
                    error_message,
                    config_snapshot,
                    mode,
                    list(symbols) if symbols is not None else None,
                    timeframe,
                    start_ts,
                    end_ts,
                ],
            )

    def record_cycle_start(
        self,
        run_id: str,
        cycle_id: str,
        strategy_id: str,
        mode: str,
        decision_ts: object,
        started_at: object,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO run_events (
                cycle_id,
                run_id,
                strategy_id,
                mode,
                decision_ts,
                started_at,
                finished_at,
                status,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, 'started', NULL)
            ON CONFLICT (cycle_id) DO NOTHING
            """,
            [cycle_id, run_id, strategy_id, mode, decision_ts, started_at],
        )

    def record_cycle_finish(
        self,
        run_id: str,
        cycle_id: str,
        strategy_id: str,
        mode: str,
        decision_ts: object,
        started_at: object,
        finished_at: object,
        status: str,
        error_message: str | None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO run_events (
                cycle_id,
                run_id,
                strategy_id,
                mode,
                decision_ts,
                started_at,
                finished_at,
                status,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (cycle_id) DO UPDATE SET
                finished_at = excluded.finished_at,
                status = excluded.status,
                error_message = excluded.error_message
            """,
            [
                cycle_id,
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

    def upsert_experiment(
        self,
        *,
        experiment_id: str,
        name: str,
        description: str | None = None,
        tags: Sequence[str] | None = None,
        created_at: object | None = None,
        updated_at: object | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO experiments (
                experiment_id,
                name,
                description,
                tags,
                created_at,
                updated_at,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (experiment_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                tags = excluded.tags,
                updated_at = excluded.updated_at,
                metadata = excluded.metadata
            """,
            [
                experiment_id,
                name,
                description,
                json.dumps(list(tags or ()), default=str),
                created_at,
                updated_at,
                json.dumps(metadata or {}, default=str),
            ],
        )

    def record_experiment_run_start(
        self,
        *,
        experiment_run_id: str,
        experiment_id: str,
        run_id: str,
        created_at: object,
        status: str = "started",
        strategy_id: str | None = None,
        strategy_name: str | None = None,
        strategy_version: str | None = None,
        symbols: Sequence[str] | None = None,
        asset_class: str | None = None,
        timeframe: str | None = None,
        start_ts: object | None = None,
        end_ts: object | None = None,
        parameters: Mapping[str, object] | None = None,
        assumptions: Mapping[str, object] | None = None,
        provenance: Mapping[str, object] | None = None,
        data_quality: Mapping[str, object] | None = None,
        artifact_dir: str | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO experiment_runs (
                experiment_run_id,
                experiment_id,
                run_id,
                status,
                created_at,
                finished_at,
                strategy_id,
                strategy_name,
                strategy_version,
                symbols,
                asset_class,
                timeframe,
                start_ts,
                end_ts,
                parameters,
                assumptions,
                provenance,
                data_quality,
                result_summary,
                artifact_dir,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL)
            ON CONFLICT (experiment_run_id) DO UPDATE SET
                status = excluded.status,
                strategy_id = excluded.strategy_id,
                strategy_name = excluded.strategy_name,
                strategy_version = excluded.strategy_version,
                symbols = excluded.symbols,
                asset_class = excluded.asset_class,
                timeframe = excluded.timeframe,
                start_ts = excluded.start_ts,
                end_ts = excluded.end_ts,
                parameters = excluded.parameters,
                assumptions = excluded.assumptions,
                provenance = excluded.provenance,
                data_quality = excluded.data_quality,
                artifact_dir = excluded.artifact_dir,
                error_message = NULL
            """,
            [
                experiment_run_id,
                experiment_id,
                run_id,
                status,
                created_at,
                strategy_id,
                strategy_name,
                strategy_version,
                json.dumps(list(symbols) if symbols is not None else None, default=str),
                asset_class,
                timeframe,
                start_ts,
                end_ts,
                json.dumps(parameters or {}, default=str),
                json.dumps(assumptions or {}, default=str),
                json.dumps(provenance or {}, default=str),
                json.dumps(data_quality or {}, default=str),
                artifact_dir,
            ],
        )

    def record_experiment_run_finish(
        self,
        *,
        experiment_run_id: str,
        experiment_id: str,
        run_id: str,
        status: str,
        finished_at: object,
        result_summary: Mapping[str, object] | None = None,
        provenance: Mapping[str, object] | None = None,
        data_quality: Mapping[str, object] | None = None,
        artifact_dir: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO experiment_runs (
                experiment_run_id,
                experiment_id,
                run_id,
                status,
                created_at,
                finished_at,
                provenance,
                data_quality,
                result_summary,
                artifact_dir,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (experiment_run_id) DO UPDATE SET
                status = excluded.status,
                finished_at = excluded.finished_at,
                provenance = excluded.provenance,
                data_quality = excluded.data_quality,
                result_summary = excluded.result_summary,
                artifact_dir = excluded.artifact_dir,
                error_message = excluded.error_message
            """,
            [
                experiment_run_id,
                experiment_id,
                run_id,
                status,
                finished_at,
                finished_at,
                json.dumps(provenance or {}, default=str),
                json.dumps(data_quality or {}, default=str),
                json.dumps(result_summary or {}, default=str),
                artifact_dir,
                error_message,
            ],
        )

    def list_experiment_runs(
        self,
        experiment_id: str,
        *,
        limit: int | None = None,
    ) -> list[Mapping[str, object]]:
        query = """
            SELECT
                experiment_run_id,
                experiment_id,
                run_id,
                status,
                created_at,
                finished_at,
                strategy_id,
                strategy_name,
                strategy_version,
                symbols,
                asset_class,
                timeframe,
                start_ts,
                end_ts,
                parameters,
                assumptions,
                provenance,
                data_quality,
                result_summary,
                artifact_dir,
                error_message
            FROM experiment_runs
            WHERE experiment_id = ?
            ORDER BY created_at DESC, experiment_run_id DESC
        """
        params: list[object] = [experiment_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = self._connection.execute(query, params).fetchall()
        fields = [
            "experiment_run_id",
            "experiment_id",
            "run_id",
            "status",
            "created_at",
            "finished_at",
            "strategy_id",
            "strategy_name",
            "strategy_version",
            "symbols",
            "asset_class",
            "timeframe",
            "start_ts",
            "end_ts",
            "parameters",
            "assumptions",
            "provenance",
            "data_quality",
            "result_summary",
            "artifact_dir",
            "error_message",
        ]
        parsed_rows: list[Mapping[str, object]] = []
        for row in rows:
            item = dict(zip(fields, row))
            for key in {"symbols", "parameters", "assumptions", "provenance", "data_quality", "result_summary"}:
                value = item.get(key)
                if isinstance(value, str):
                    item[key] = json.loads(value)
            parsed_rows.append(item)
        return parsed_rows

    def close(self) -> None:
        self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield

    def connection(self) -> "DuckDBConnectionAdapter":
        return DuckDBConnectionAdapter(self._connection)


class DuckDBConnectionAdapter:
    """Adapter to provide Postgres-style cursor semantics for DuckDB."""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection

    def cursor(self) -> "DuckDBCursorAdapter":
        return DuckDBCursorAdapter(self._connection)

    def execute(self, query: str, params: list[object] | None = None) -> duckdb.DuckDBPyConnection:
        translated = _translate_placeholders(query)
        return self._connection.execute(translated, params or [])

    def close(self) -> None:
        self._connection.close()


class DuckDBCursorAdapter:
    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection
        self._result: duckdb.DuckDBPyConnection | None = None

    def execute(self, query: str, params: list[object] | None = None) -> None:
        translated = _translate_placeholders(query)
        self._result = self._connection.execute(translated, params or [])

    def fetchone(self) -> object | None:
        if self._result is None:
            return None
        return self._result.fetchone()

    def fetchall(self) -> list[object]:
        if self._result is None:
            return []
        return self._result.fetchall()

    def __enter__(self) -> "DuckDBCursorAdapter":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _translate_placeholders(query: str) -> str:
    return query.replace("%s", "?")


def merge_events(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    events: list[Mapping[str, object]],
) -> None:
    """Merge events into DuckDB with deduplication (test helper)."""
    if not events:
        return
    columns = list(events[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    values = [list(event.values()) for event in events]
    staging_table = f"staging_{table_name}"
    connection.execute(
        f"CREATE TEMP TABLE {staging_table} AS SELECT {', '.join(columns)} FROM {table_name} WHERE 1=0"
    )
    connection.executemany(
        f"INSERT INTO {staging_table} ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )
    insert_columns = ", ".join(columns)
    source_columns = ", ".join([f"source.{col}" for col in columns])
    connection.execute(
        f"""
        MERGE INTO {table_name} AS target
        USING {staging_table} AS source
        ON target.symbol = source.symbol
            AND target.timeframe = source.timeframe
            AND target.ts = source.ts
            AND target.source = source.source
        WHEN NOT MATCHED THEN
            INSERT ({insert_columns}) VALUES ({source_columns})
        """
    )
    connection.execute(f"DROP TABLE {staging_table}")
