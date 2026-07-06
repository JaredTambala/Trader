"""Postgres-backed event-store implementation."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

from .base import EventStore
from .records import (
    PostgresEventInsertPlan,
    build_postgres_event_insert_plan,
    cycle_finish_parameters,
    cycle_start_parameters,
    experiment_run_finish_parameters,
    experiment_run_row_to_record,
    experiment_run_start_parameters,
    list_experiment_runs_query_plan,
    run_session_finish_parameters,
    run_session_start_parameters,
    trading_session_finish_parameters,
    trading_session_start_parameters,
    upsert_experiment_parameters,
)
from .schema import POSTGRES_SCHEMA_STATEMENTS
from .statements import (
    CYCLE_FINISH_SQL,
    CYCLE_START_SQL,
    EXPERIMENT_RUN_FINISH_SQL,
    EXPERIMENT_RUN_START_SQL,
    RUN_SESSION_FINISH_SQL,
    RUN_SESSION_START_SQL,
    TRADING_SESSION_FINISH_SQL,
    TRADING_SESSION_START_SQL,
    UPSERT_EXPERIMENT_SQL,
)

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover - optional dependency
    psycopg = None
    sql = None


def _event_insert_query(plan: PostgresEventInsertPlan) -> Any:
    """Build a psycopg SQL insert object from a validated event insert plan."""
    if sql is None:  # pragma: no cover - guarded by PostgresEventStore init
        raise ImportError("psycopg is required to build Postgres event insert queries")
    query = sql.SQL("INSERT INTO {table} ({fields}) VALUES ({values})").format(
        table=sql.Identifier(plan.event_type),
        fields=sql.SQL(", ").join(sql.Identifier(column) for column in plan.columns),
        values=sql.SQL(", ").join(sql.Placeholder() for _ in plan.columns),
    )
    if plan.ignore_bar_conflicts:
        query = query + sql.SQL(" ON CONFLICT (symbol, timeframe, ts, source) DO NOTHING")
    return query


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
        with self.transaction():
            for statement in POSTGRES_SCHEMA_STATEMENTS:
                self._connection.execute(statement)

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Insert one append-only event payload into a known table.

        Args:
            event_type: Whitelisted table/event name.
            payload: Column-to-value mapping to insert.

        Raises:
            ValueError: If `event_type` is not part of the event-store schema.
            Exception: If Postgres rejects the generated insert.
        """
        plan = build_postgres_event_insert_plan(event_type, payload)
        self._connection.execute(_event_insert_query(plan), list(plan.values))

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
        self._connection.execute(
            RUN_SESSION_START_SQL,
            run_session_start_parameters(
                run_id=run_id,
                run_type=run_type,
                started_at=started_at,
                status=status,
                config_snapshot=config_snapshot,
                mode=mode,
                symbols=symbols,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts=end_ts,
            ),
        )
        if run_type == "trading":
            self._connection.execute(
                TRADING_SESSION_START_SQL,
                trading_session_start_parameters(
                    run_id=run_id,
                    strategy_id=strategy_id,
                    started_at=started_at,
                    status=status,
                    config_snapshot=config_snapshot,
                    mode=mode,
                    symbols=symbols,
                    timeframe=timeframe,
                    start_ts=start_ts,
                    end_ts=end_ts,
                ),
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
        self._connection.execute(
            RUN_SESSION_FINISH_SQL,
            run_session_finish_parameters(
                run_id=run_id,
                run_type=run_type,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                error_message=error_message,
                config_snapshot=config_snapshot,
                mode=mode,
                symbols=symbols,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts=end_ts,
            ),
        )
        if run_type == "trading":
            self._connection.execute(
                TRADING_SESSION_FINISH_SQL,
                trading_session_finish_parameters(
                    run_id=run_id,
                    strategy_id=strategy_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    status=status,
                    error_message=error_message,
                    config_snapshot=config_snapshot,
                    mode=mode,
                    symbols=symbols,
                    timeframe=timeframe,
                    start_ts=start_ts,
                    end_ts=end_ts,
                ),
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
            CYCLE_START_SQL,
            cycle_start_parameters(
                run_id=run_id,
                cycle_id=cycle_id,
                strategy_id=strategy_id,
                mode=mode,
                decision_ts=decision_ts,
                started_at=started_at,
            ),
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
            CYCLE_FINISH_SQL,
            cycle_finish_parameters(
                run_id=run_id,
                cycle_id=cycle_id,
                strategy_id=strategy_id,
                mode=mode,
                decision_ts=decision_ts,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                error_message=error_message,
            ),
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
        self._connection.execute(
            UPSERT_EXPERIMENT_SQL,
            upsert_experiment_parameters(
                experiment_id=experiment_id,
                name=name,
                description=description,
                tags=tags,
                created_at=created_at,
                updated_at=updated_at,
                metadata=metadata,
            ),
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
            EXPERIMENT_RUN_START_SQL,
            experiment_run_start_parameters(
                experiment_run_id=experiment_run_id,
                experiment_id=experiment_id,
                run_id=run_id,
                status=status,
                created_at=created_at,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                strategy_version=strategy_version,
                symbols=symbols,
                asset_class=asset_class,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts=end_ts,
                parameters=parameters,
                assumptions=assumptions,
                provenance=provenance,
                data_quality=data_quality,
                artifact_dir=artifact_dir,
            ),
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
            EXPERIMENT_RUN_FINISH_SQL,
            experiment_run_finish_parameters(
                experiment_run_id=experiment_run_id,
                experiment_id=experiment_id,
                run_id=run_id,
                status=status,
                finished_at=finished_at,
                provenance=provenance,
                data_quality=data_quality,
                result_summary=result_summary,
                artifact_dir=artifact_dir,
                error_message=error_message,
            ),
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
        plan = list_experiment_runs_query_plan(experiment_id, limit=limit)
        with self._connection.cursor() as cursor:
            cursor.execute(plan.query, list(plan.parameters))
            rows = cursor.fetchall()
        return [experiment_run_row_to_record(row) for row in rows]

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
