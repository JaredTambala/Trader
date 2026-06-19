"""Postgres-backed event-store implementation."""

from __future__ import annotations

from contextlib import contextmanager
import json
from typing import Any, Iterator, Mapping, Sequence

from .base import EventStore

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover - optional dependency
    psycopg = None
    sql = None


class PostgresEventStore(EventStore):
    """Durable event store backed by PostgreSQL tables.

    The store owns schema initialization, append-only event insertion, and
    idempotent lifecycle upserts for runs, cycles, and research experiments. It
    uses JSONB for variable payloads and keeps timestamps in Postgres
    `TIMESTAMPTZ` columns so runtime status queries can reason about recency.
    """

    def __init__(
        self,
        *,
        dsn: str | None = None,
        host: str | None = None,
        port: int | None = None,
        dbname: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        """Open a Postgres connection and ensure required tables exist.

        Args:
            dsn: Optional complete Postgres connection string. When supplied it
                takes precedence over the individual connection fields.
            host: Postgres host used when `dsn` is absent.
            port: Postgres port used when `dsn` is absent.
            dbname: Database name used when `dsn` is absent.
            user: Database user used when `dsn` is absent.
            password: Database password used when `dsn` is absent.

        Raises:
            ImportError: If psycopg is not installed.
            Exception: If connection establishment or schema creation fails.
        """
        if psycopg is None:
            raise ImportError("psycopg is required to use PostgresEventStore")
        if dsn:
            self._connection = psycopg.connect(dsn)
        else:
            self._connection = psycopg.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
            )
        self._connection.autocommit = True
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create and migrate the tables required by current runtime code.

        Schema setup is deliberately idempotent so every process can construct a
        store safely. The method also creates indexes used by status, recovery,
        and experiment queries.
        """
        statements = [
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                run_type TEXT,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                status TEXT,
                error_message TEXT,
                config_snapshot JSONB,
                mode TEXT,
                symbols TEXT[],
                timeframe TEXT,
                start_ts TIMESTAMPTZ,
                end_ts TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trading_sessions (
                session_id TEXT PRIMARY KEY,
                strategy_id TEXT,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                status TEXT,
                error_message TEXT,
                config_snapshot JSONB,
                mode TEXT,
                symbols TEXT[],
                timeframe TEXT,
                start_ts TIMESTAMPTZ,
                end_ts TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                description TEXT,
                tags TEXT[],
                created_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ,
                metadata JSONB
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS experiment_runs (
                experiment_run_id TEXT PRIMARY KEY,
                experiment_id TEXT,
                run_id TEXT,
                status TEXT,
                created_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                strategy_id TEXT,
                strategy_name TEXT,
                strategy_version TEXT,
                symbols TEXT[],
                asset_class TEXT,
                timeframe TEXT,
                start_ts TIMESTAMPTZ,
                end_ts TIMESTAMPTZ,
                parameters JSONB,
                assumptions JSONB,
                provenance JSONB,
                data_quality JSONB,
                result_summary JSONB,
                artifact_dir TEXT,
                error_message TEXT
            )
            """,
            """
            ALTER TABLE IF EXISTS run_events
            DROP CONSTRAINT IF EXISTS run_events_pkey
            """,
            """
            CREATE TABLE IF NOT EXISTS run_events (
                cycle_id TEXT PRIMARY KEY,
                run_id TEXT,
                session_id TEXT,
                strategy_id TEXT,
                mode TEXT,
                decision_ts TIMESTAMPTZ,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                status TEXT,
                error_message TEXT
            )
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS cycle_id TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS run_id TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS strategy_id TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS mode TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS decision_ts TIMESTAMPTZ
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS status TEXT
            """,
            """
            ALTER TABLE IF EXISTS run_events
            ADD COLUMN IF NOT EXISTS error_message TEXT
            """,
            """
            CREATE TABLE IF NOT EXISTS stock_bar_events (
                symbol TEXT,
                timeframe TEXT,
                ts TIMESTAMPTZ,
                ingested_at TIMESTAMPTZ,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume DOUBLE PRECISION,
                trade_count DOUBLE PRECISION,
                vwap DOUBLE PRECISION,
                source TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS crypto_bar_events (
                symbol TEXT,
                timeframe TEXT,
                ts TIMESTAMPTZ,
                ingested_at TIMESTAMPTZ,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume DOUBLE PRECISION,
                trade_count DOUBLE PRECISION,
                vwap DOUBLE PRECISION,
                source TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS signal_events (
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                symbol TEXT,
                signal_value DOUBLE PRECISION,
                target_qty DOUBLE PRECISION,
                generated_at TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS indicator_events (
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                symbol TEXT,
                indicator_name TEXT,
                value DOUBLE PRECISION,
                bar_ts TIMESTAMPTZ,
                payload TEXT
            )
            """,
            """
            ALTER TABLE signal_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE indicator_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE indicator_events
            ADD COLUMN IF NOT EXISTS payload TEXT
            """,
            """
            CREATE TABLE IF NOT EXISTS order_events (
                order_event_id TEXT PRIMARY KEY,
                client_order_id TEXT,
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                symbol TEXT,
                side TEXT,
                qty DOUBLE PRECISION,
                order_type TEXT,
                status TEXT,
                broker_order_id TEXT,
                rejection_reason TEXT,
                created_at TIMESTAMPTZ
            )
            """,
            """
            ALTER TABLE order_events
            ADD COLUMN IF NOT EXISTS rejection_reason TEXT
            """,
            """
            ALTER TABLE order_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE order_events
            DROP CONSTRAINT IF EXISTS order_events_pkey
            """,
            """
            ALTER TABLE order_events
            ADD COLUMN IF NOT EXISTS order_event_id TEXT
            """,
            """
            UPDATE order_events
            SET order_event_id = CONCAT('order_evt_', md5(random()::text || clock_timestamp()::text))
            WHERE order_event_id IS NULL
            """,
            """
            ALTER TABLE order_events
            ALTER COLUMN order_event_id SET NOT NULL
            """,
            """
            ALTER TABLE order_events
            ADD PRIMARY KEY (order_event_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS fill_events (
                client_order_id TEXT,
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                fill_ts TIMESTAMPTZ,
                fill_qty DOUBLE PRECISION,
                raw_fill_price DOUBLE PRECISION,
                slippage_amount DOUBLE PRECISION,
                fee_amount DOUBLE PRECISION,
                fill_price DOUBLE PRECISION
            )
            """,
            """
            ALTER TABLE fill_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE fill_events
            ADD COLUMN IF NOT EXISTS raw_fill_price DOUBLE PRECISION
            """,
            """
            ALTER TABLE fill_events
            ADD COLUMN IF NOT EXISTS slippage_amount DOUBLE PRECISION
            """,
            """
            ALTER TABLE fill_events
            ADD COLUMN IF NOT EXISTS fee_amount DOUBLE PRECISION
            """,
            """
            CREATE TABLE IF NOT EXISTS position_snapshots (
                asof_ts TIMESTAMPTZ,
                symbol TEXT,
                qty DOUBLE PRECISION,
                avg_price DOUBLE PRECISION,
                cash_balance DOUBLE PRECISION,
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS config_kv (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """,
            """
            ALTER TABLE position_snapshots
            ADD COLUMN IF NOT EXISTS cash_balance DOUBLE PRECISION
            """,
            """
            ALTER TABLE position_snapshots
            ADD COLUMN IF NOT EXISTS run_id TEXT
            """,
            """
            ALTER TABLE position_snapshots
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            ALTER TABLE position_snapshots
            ADD COLUMN IF NOT EXISTS cycle_id TEXT
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS stock_bar_events_unique
            ON stock_bar_events(symbol, timeframe, ts, source)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS crypto_bar_events_unique
            ON crypto_bar_events(symbol, timeframe, ts, source)
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS run_events_cycle_unique
            ON run_events(cycle_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS run_events_run_id_idx
            ON run_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS run_events_session_id_idx
            ON run_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS signal_events_run_id_idx
            ON signal_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS signal_events_session_id_idx
            ON signal_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS indicator_events_run_id_idx
            ON indicator_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS indicator_events_session_id_idx
            ON indicator_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS order_events_run_id_idx
            ON order_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS order_events_session_id_idx
            ON order_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS order_events_client_order_id_idx
            ON order_events(client_order_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS fill_events_run_id_idx
            ON fill_events(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS fill_events_session_id_idx
            ON fill_events(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS position_snapshots_run_id_idx
            ON position_snapshots(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS position_snapshots_session_id_idx
            ON position_snapshots(session_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS metrics_snapshots (
                ts TIMESTAMPTZ,
                run_id TEXT,
                session_id TEXT,
                cycle_id TEXT,
                payload TEXT
            )
            """,
            """
            ALTER TABLE metrics_snapshots
            ADD COLUMN IF NOT EXISTS session_id TEXT
            """,
            """
            CREATE INDEX IF NOT EXISTS metrics_snapshots_run_id_idx
            ON metrics_snapshots(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS metrics_snapshots_session_id_idx
            ON metrics_snapshots(session_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_experiment_id_idx
            ON experiment_runs(experiment_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_run_id_idx
            ON experiment_runs(run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_status_idx
            ON experiment_runs(status)
            """,
            """
            CREATE INDEX IF NOT EXISTS experiment_runs_created_at_idx
            ON experiment_runs(created_at)
            """,
        ]
        with self.transaction():
            for stmt in statements:
                self._connection.execute(stmt)

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Insert one append-only event payload into a known table.

        Args:
            event_type: Whitelisted table/event name.
            payload: Column-to-value mapping to insert.

        Raises:
            ValueError: If `event_type` is not part of the event-store schema.
            Exception: If Postgres rejects the generated insert.
        """
        if event_type not in {
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
            "config_kv",
            "metrics_snapshots",
            "experiments",
            "experiment_runs",
        }:
            raise ValueError(f"Unknown event type: {event_type}")

        columns = list(payload.keys())
        query = sql.SQL("INSERT INTO {table} ({fields}) VALUES ({values})").format(
            table=sql.Identifier(event_type),
            fields=sql.SQL(", ").join(sql.Identifier(col) for col in columns),
            values=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        if event_type in {"stock_bar_events", "crypto_bar_events"}:
            query = query + sql.SQL(" ON CONFLICT (symbol, timeframe, ts, source) DO NOTHING")
        self._connection.execute(query, list(payload.values()))

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
        """Insert the initial run-session row without overwriting existing data.

        Backtests and live trading sessions share the `runs` table. Trading runs
        also get a `trading_sessions` row keyed by the same run ID so operator
        status queries can distinguish live service state.
        """
        # config_snapshot may contain datetimes (e.g. UI-submitted payloads).
        snapshot_json = json.dumps(config_snapshot, default=str) if config_snapshot is not None else None
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
            VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO NOTHING
            """,
            [
                run_id,
                run_type,
                started_at,
                status,
                None,
                snapshot_json,
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
                VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (session_id) DO NOTHING
                """,
                [
                    run_id,
                    strategy_id,
                    started_at,
                    status,
                    None,
                    snapshot_json,
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
        """Upsert final run-session status and mirror trading-session state.

        The row is updated on conflict so late completion writes can attach
        finish timestamps and errors to a start row created earlier by the same
        process or a buffered writer.
        """
        # config_snapshot may contain datetimes (e.g. UI-submitted payloads).
        snapshot_json = json.dumps(config_snapshot, default=str) if config_snapshot is not None else None
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                snapshot_json,
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    snapshot_json,
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
        """Insert the start row for one decision cycle.

        Cycle IDs are deterministic for a strategy and decision timestamp, so an
        existing row means the cycle start was already recorded and should not be
        duplicated.
        """
        self._connection.execute(
            """
            INSERT INTO run_events (
                cycle_id,
                run_id,
                session_id,
                strategy_id,
                mode,
                decision_ts,
                started_at,
                finished_at,
                status,
                error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, 'started', NULL)
            ON CONFLICT (cycle_id) DO NOTHING
            """,
            [cycle_id, run_id, run_id, strategy_id, mode, decision_ts, started_at],
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
        """Record terminal status for a decision cycle.

        The upsert preserves the cycle identity while allowing the finish event
        to fill in status, error text, and finish timestamp after the start row
        has already been inserted.
        """
        self._connection.execute(
            """
            INSERT INTO run_events (
                cycle_id,
                run_id,
                session_id,
                strategy_id,
                mode,
                decision_ts,
                started_at,
                finished_at,
                status,
                error_message
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (cycle_id) DO UPDATE SET
                finished_at = excluded.finished_at,
                status = excluded.status,
                error_message = excluded.error_message
            """,
            [
                cycle_id,
                run_id,
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
        """Insert or update reusable experiment metadata.

        Experiment names are unique and may be reused by research workflows; the
        row is updated with the latest description, tags, timestamps, and JSON
        metadata instead of creating duplicate experiment groups.
        """
        metadata_json = json.dumps(metadata or {}, default=str)
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
            VALUES (%s, %s, %s, %s, %s, %s, %s)
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
                list(tags or ()),
                created_at,
                updated_at,
                metadata_json,
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
        """Insert or refresh the metadata captured when an experiment run starts.

        The write records strategy identity, symbol universe, parameters,
        assumptions, provenance, data quality, and artifact location. Conflicts
        update the row so retried orchestration can repair incomplete metadata.
        """
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
            VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, NULL)
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
                list(symbols) if symbols is not None else None,
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
        """Insert or update the terminal row data for an experiment run.

        The statement preserves existing start metadata where possible while
        updating terminal status, finish timestamp, result summary, artifact path,
        provenance, data-quality payload, and error message. This gives research
        comparison queries a single row per `experiment_run_id`.
        """
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (experiment_run_id) DO UPDATE SET
                status = excluded.status,
                finished_at = excluded.finished_at,
                provenance = COALESCE(excluded.provenance, experiment_runs.provenance),
                data_quality = COALESCE(excluded.data_quality, experiment_runs.data_quality),
                result_summary = excluded.result_summary,
                artifact_dir = COALESCE(excluded.artifact_dir, experiment_runs.artifact_dir),
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
        """Return experiment runs for one experiment in newest-first order.

        Args:
            experiment_id: Experiment grouping to read.
            limit: Optional maximum number of rows to return.

        Returns:
            JSON-friendly mappings containing run metadata, result summaries,
            provenance, data-quality details, and artifact locations.
        """
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
            WHERE experiment_id = %s
            ORDER BY created_at DESC, experiment_run_id DESC
        """
        params: list[object] = [experiment_id]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
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
        return [dict(zip(fields, row)) for row in rows]

    def close(self) -> None:
        """Close the Postgres connection owned by this event store instance after use."""
        self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run enclosed operations in one explicit Postgres transaction.

        The store normally uses autocommit for single-event writes. This context
        temporarily disables autocommit, commits on success, rolls back on any
        exception, and restores the previous connection setting before returning.
        """
        previous_autocommit = self._connection.autocommit
        self._connection.autocommit = False
        try:
            yield
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            self._connection.autocommit = previous_autocommit

    def connection(self) -> Any:
        """Expose the raw Postgres connection for bounded read/query helpers.

        The store keeps ownership of transaction behavior; callers use the
        connection for existing helper queries that need direct SQL access rather
        than for ad hoc lifecycle writes.
        """
        return self._connection
