"""Event store interface for persisting trading system events."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
import json
from queue import Queue, Full, Empty
from threading import Event, Lock, Thread
from typing import Any, Iterator, Mapping, Sequence

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover - optional dependency
    psycopg = None
    sql = None


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
        """Record the start of a run session.

        Args:
            run_id: Stable identifier for the run session.
            run_type: Run type (backtest/trading).
            started_at: Timestamp when the run started.
            status: Initial run status.
            config_snapshot: Optional configuration snapshot payload.
            mode: Runtime mode for trading runs.
            symbols: Optional symbol universe.
            timeframe: Optional timeframe label.
            start_ts: Optional backtest start timestamp.
            end_ts: Optional backtest end timestamp.

        Raises:
            Exception: Implementations may raise on insert errors.
        """
        self.record_event(
            "runs",
            {
                "run_id": run_id,
                "run_type": run_type,
                "started_at": started_at,
                "finished_at": None,
                "status": status,
                "error_message": None,
                "config_snapshot": config_snapshot,
                "mode": mode,
                "symbols": list(symbols) if symbols is not None else None,
                "timeframe": timeframe,
                "start_ts": start_ts,
                "end_ts": end_ts,
            },
        )
        if run_type == "trading":
            self.record_event(
                "trading_sessions",
                {
                    "session_id": run_id,
                    "strategy_id": strategy_id,
                    "started_at": started_at,
                    "finished_at": None,
                    "status": status,
                    "error_message": None,
                    "config_snapshot": config_snapshot,
                    "mode": mode,
                    "symbols": list(symbols) if symbols is not None else None,
                    "timeframe": timeframe,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                },
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
        """Record the final status of a run session.

        Args:
            run_id: Stable identifier for the run session.
            run_type: Run type (backtest/trading).
            started_at: Timestamp when the run started.
            finished_at: Timestamp when the run finished.
            status: Terminal status string.
            error_message: Optional error message when failed.
            config_snapshot: Optional configuration snapshot payload.
            mode: Runtime mode for trading runs.
            symbols: Optional symbol universe.
            timeframe: Optional timeframe label.
            start_ts: Optional backtest start timestamp.
            end_ts: Optional backtest end timestamp.

        Raises:
            Exception: Implementations may raise on insert/update errors.
        """
        self.record_event(
            "runs",
            {
                "run_id": run_id,
                "run_type": run_type,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "error_message": error_message,
                "config_snapshot": config_snapshot,
                "mode": mode,
                "symbols": list(symbols) if symbols is not None else None,
                "timeframe": timeframe,
                "start_ts": start_ts,
                "end_ts": end_ts,
            },
        )
        if run_type == "trading":
            self.record_event(
                "trading_sessions",
                {
                    "session_id": run_id,
                    "strategy_id": strategy_id,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "status": status,
                    "error_message": error_message,
                    "config_snapshot": config_snapshot,
                    "mode": mode,
                    "symbols": list(symbols) if symbols is not None else None,
                    "timeframe": timeframe,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                },
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
        """Record the start of a decision cycle."""
        self.record_event(
            "run_events",
            {
                "cycle_id": cycle_id,
                "run_id": run_id,
                "session_id": run_id,
                "strategy_id": strategy_id,
                "mode": mode,
                "decision_ts": decision_ts,
                "started_at": started_at,
                "finished_at": None,
                "status": "started",
                "error_message": None,
            },
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
        """Record the final status of a decision cycle."""
        self.record_event(
            "run_events",
            {
                "cycle_id": cycle_id,
                "run_id": run_id,
                "session_id": run_id,
                "strategy_id": strategy_id,
                "mode": mode,
                "decision_ts": decision_ts,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "error_message": error_message,
            },
        )

    def record_run_start(
        self,
        run_id: str,
        strategy_id: str,
        mode: str,
        decision_ts: object,
        started_at: object,
    ) -> None:
        """Backward-compatible alias for cycle start recording."""
        self.record_cycle_start(
            run_id=run_id,
            cycle_id=run_id,
            strategy_id=strategy_id,
            mode=mode,
            decision_ts=decision_ts,
            started_at=started_at,
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
        """Backward-compatible alias for cycle finish recording."""
        self.record_cycle_finish(
            run_id=run_id,
            cycle_id=run_id,
            strategy_id=strategy_id,
            mode=mode,
            decision_ts=decision_ts,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            error_message=error_message,
        )

    def close(self) -> None:
        """Release any resources held by the store.

        Raises:
            None.
        """
        return None

    def flush(self) -> None:
        """Flush any buffered events to the underlying store."""
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


class FilteredEventStore(EventStore):
    """Event store wrapper that filters selected event types."""

    def __init__(self, inner: EventStore, *, allowed_event_types: set[str]) -> None:
        """Initialize the instance."""
        self._inner = inner
        self._allowed = set(allowed_event_types)

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Handle record event."""
        if event_type not in self._allowed:
            return
        self._inner.record_event(event_type, payload)

    def connection(self) -> Any:
        """Expose the inner connection for read-only queries."""
        connector = getattr(self._inner, "connection", None)
        if connector is None:
            return None
        return connector()

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
        """Handle record run session start."""
        self._inner.record_run_session_start(
            run_id=run_id,
            run_type=run_type,
            started_at=started_at,
            status=status,
            strategy_id=strategy_id,
            config_snapshot=config_snapshot,
            mode=mode,
            symbols=symbols,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts=end_ts,
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
        """Handle record run session finish."""
        self._inner.record_run_session_finish(
            run_id=run_id,
            run_type=run_type,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            error_message=error_message,
            strategy_id=strategy_id,
            config_snapshot=config_snapshot,
            mode=mode,
            symbols=symbols,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts=end_ts,
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
        """Handle record cycle start."""
        self._inner.record_cycle_start(
            run_id=run_id,
            cycle_id=cycle_id,
            strategy_id=strategy_id,
            mode=mode,
            decision_ts=decision_ts,
            started_at=started_at,
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
        """Handle record cycle finish."""
        self._inner.record_cycle_finish(
            run_id=run_id,
            cycle_id=cycle_id,
            strategy_id=strategy_id,
            mode=mode,
            decision_ts=decision_ts,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            error_message=error_message,
        )

    def flush(self) -> None:
        """Handle flush."""
        return self._inner.flush()

    def close(self) -> None:
        """Handle close."""
        return self._inner.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Handle transaction."""
        with self._inner.transaction():
            yield


def build_event_store(config: object) -> EventStore:
    """Create the configured event store."""
    event_store = getattr(config, "event_store", "postgres").lower()
    if event_store in {"noop", "none"}:
        return NoOpEventStore()
    if event_store == "postgres":
        store = PostgresEventStore(
            dsn=getattr(config, "pg_dsn", None) or None,
            host=getattr(config, "pg_host", None) or None,
            port=getattr(config, "pg_port", None) or None,
            dbname=getattr(config, "pg_db", None) or None,
            user=getattr(config, "pg_user", None) or None,
            password=getattr(config, "pg_password", None) or None,
        )
        if getattr(config, "buffered_event_store", False):
            write_store = PostgresEventStore(
                dsn=getattr(config, "pg_dsn", None) or None,
                host=getattr(config, "pg_host", None) or None,
                port=getattr(config, "pg_port", None) or None,
                dbname=getattr(config, "pg_db", None) or None,
                user=getattr(config, "pg_user", None) or None,
                password=getattr(config, "pg_password", None) or None,
            )
            store = BufferedEventStore(
                store,
                write_store=write_store,
                flush_interval_ms=getattr(config, "buffer_flush_interval_ms", 250),
                max_batch_size=getattr(config, "buffer_max_batch_size", 500),
                max_queue_size=getattr(config, "buffer_max_queue_size", 10000),
                block_on_full=getattr(config, "buffer_block_on_full", True),
            )
        return store
    raise ValueError(f"Unsupported event store: {event_store}")


@dataclass(frozen=True)
class BufferedEventStoreSettings:
    flush_interval_ms: int
    max_batch_size: int
    max_queue_size: int
    block_on_full: bool


class BufferedEventStore(EventStore):
    """Buffered wrapper that flushes events asynchronously."""

    _RUN_SESSION_START_EVENT = "__run_session_start__"
    _RUN_SESSION_FINISH_EVENT = "__run_session_finish__"
    _CYCLE_START_EVENT = "__cycle_start__"
    _CYCLE_FINISH_EVENT = "__cycle_finish__"
    def __init__(
        self,
        inner: EventStore,
        *,
        write_store: EventStore | None = None,
        flush_interval_ms: int = 250,
        max_batch_size: int = 500,
        max_queue_size: int = 10000,
        block_on_full: bool = True,
    ) -> None:
        """Initialize the instance."""
        if flush_interval_ms <= 0:
            raise ValueError("flush_interval_ms must be positive")
        if max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")
        self._inner = inner
        self._write_store = write_store or inner
        self._settings = BufferedEventStoreSettings(
            flush_interval_ms=flush_interval_ms,
            max_batch_size=max_batch_size,
            max_queue_size=max_queue_size,
            block_on_full=block_on_full,
        )
        self._queue: Queue[tuple[str, Mapping[str, object]]] = Queue(maxsize=max_queue_size)
        self._stop = Event()
        self._write_lock = Lock()
        self._worker = Thread(target=self._run, name="event-store-flush", daemon=True)
        self._worker.start()

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Handle record event."""
        try:
            if self._settings.block_on_full:
                self._queue.put((event_type, dict(payload)))
            else:
                self._queue.put_nowait((event_type, dict(payload)))
        except Full as exc:
            raise RuntimeError("Buffered event queue is full") from exc

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
        """Enqueue a run session start event."""
        self.record_event(
            self._RUN_SESSION_START_EVENT,
            {
                "run_id": run_id,
                "run_type": run_type,
                "started_at": started_at,
                "finished_at": None,
                "status": status,
                "error_message": None,
                "strategy_id": strategy_id,
                "config_snapshot": config_snapshot,
                "mode": mode,
                "symbols": list(symbols) if symbols is not None else None,
                "timeframe": timeframe,
                "start_ts": start_ts,
                "end_ts": end_ts,
            },
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
        """Enqueue a run session finish event."""
        self.record_event(
            self._RUN_SESSION_FINISH_EVENT,
            {
                "run_id": run_id,
                "run_type": run_type,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "error_message": error_message,
                "strategy_id": strategy_id,
                "config_snapshot": config_snapshot,
                "mode": mode,
                "symbols": list(symbols) if symbols is not None else None,
                "timeframe": timeframe,
                "start_ts": start_ts,
                "end_ts": end_ts,
            },
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
        """Enqueue a cycle start event."""
        self.record_event(
            self._CYCLE_START_EVENT,
            {
                "run_id": run_id,
                "cycle_id": cycle_id,
                "session_id": run_id,
                "strategy_id": strategy_id,
                "mode": mode,
                "decision_ts": decision_ts,
                "started_at": started_at,
                "finished_at": None,
                "status": "started",
                "error_message": None,
            },
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
        """Enqueue a cycle finish event."""
        self.record_event(
            self._CYCLE_FINISH_EVENT,
            {
                "run_id": run_id,
                "cycle_id": cycle_id,
                "session_id": run_id,
                "strategy_id": strategy_id,
                "mode": mode,
                "decision_ts": decision_ts,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "error_message": error_message,
            },
        )

    def flush(self) -> None:
        """Flush all queued events synchronously."""
        batch: list[tuple[str, Mapping[str, object]]] = []
        while True:
            try:
                batch.append(self._queue.get_nowait())
            except Empty:
                break
        if batch:
            with self._write_lock:
                with self._write_store.transaction():
                    for event_type, payload in batch:
                        self._flush_event(event_type, payload)

    def close(self) -> None:
        """Flush and stop the background worker."""
        self._stop.set()
        self._worker.join(timeout=5.0)
        self.flush()
        self._inner.close()
        if self._write_store is not self._inner:
            self._write_store.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Let callers enqueue events without blocking on DB flush."""
        yield

    def connection(self) -> Any:
        """Expose the underlying connection if supported."""
        return getattr(self._inner, "connection", lambda: None)()

    def _run(self) -> None:
        """Handle run."""
        interval = self._settings.flush_interval_ms / 1000.0
        while not self._stop.is_set():
            self._flush_batch()
            self._stop.wait(interval)

    def _flush_batch(self) -> None:
        """Handle flush batch."""
        batch: list[tuple[str, Mapping[str, object]]] = []
        while len(batch) < self._settings.max_batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except Empty:
                break
        if not batch:
            return
        with self._write_lock:
            with self._write_store.transaction():
                for event_type, payload in batch:
                    self._flush_event(event_type, payload)

    def _flush_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Handle flush event."""
        if event_type == self._RUN_SESSION_START_EVENT:
            self._write_store.record_run_session_start(
                run_id=str(payload["run_id"]),
                run_type=str(payload["run_type"]),
                started_at=payload["started_at"],
                status=str(payload["status"]),
                strategy_id=payload.get("strategy_id"),
                config_snapshot=payload.get("config_snapshot"),
                mode=payload.get("mode"),
                symbols=payload.get("symbols"),
                timeframe=payload.get("timeframe"),
                start_ts=payload.get("start_ts"),
                end_ts=payload.get("end_ts"),
            )
            return
        if event_type == self._RUN_SESSION_FINISH_EVENT:
            self._write_store.record_run_session_finish(
                run_id=str(payload["run_id"]),
                run_type=str(payload["run_type"]),
                started_at=payload["started_at"],
                finished_at=payload["finished_at"],
                status=str(payload["status"]),
                error_message=payload.get("error_message"),
                strategy_id=payload.get("strategy_id"),
                config_snapshot=payload.get("config_snapshot"),
                mode=payload.get("mode"),
                symbols=payload.get("symbols"),
                timeframe=payload.get("timeframe"),
                start_ts=payload.get("start_ts"),
                end_ts=payload.get("end_ts"),
            )
            return
        if event_type == self._CYCLE_START_EVENT:
            self._write_store.record_cycle_start(
                run_id=str(payload["run_id"]),
                cycle_id=str(payload["cycle_id"]),
                strategy_id=str(payload["strategy_id"]),
                mode=str(payload["mode"]),
                decision_ts=payload["decision_ts"],
                started_at=payload["started_at"],
            )
            return
        if event_type == self._CYCLE_FINISH_EVENT:
            self._write_store.record_cycle_finish(
                run_id=str(payload["run_id"]),
                cycle_id=str(payload["cycle_id"]),
                strategy_id=str(payload["strategy_id"]),
                mode=str(payload["mode"]),
                decision_ts=payload["decision_ts"],
                started_at=payload["started_at"],
                finished_at=payload["finished_at"],
                status=str(payload["status"]),
                error_message=payload.get("error_message"),
            )
            return
        self._write_store.record_event(event_type, payload)


class PostgresEventStore(EventStore):
    """Postgres-backed event store for concurrent workloads."""

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
        """Create a Postgres event store and initialize the schema."""
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
        """Handle ensure schema."""
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
                bar_ts TIMESTAMPTZ
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
                fill_price DOUBLE PRECISION
            )
            """,
            """
            ALTER TABLE fill_events
            ADD COLUMN IF NOT EXISTS session_id TEXT
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
        ]
        with self.transaction():
            for stmt in statements:
                self._connection.execute(stmt)

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Insert a payload into the requested event table."""
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
        """Insert a started run session record if it does not already exist."""
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
        """Upsert the final run session status record."""
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
        """Insert a started cycle record if it does not already exist."""
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
        """Upsert the final cycle status record."""
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

    def close(self) -> None:
        """Close the Postgres connection."""
        self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Wrap operations in an explicit Postgres transaction."""
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
        """Expose the underlying Postgres connection for advanced operations."""
        return self._connection
