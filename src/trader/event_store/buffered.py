"""Buffered event-store wrapper."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Any, Iterator, Mapping, Sequence

from .base import EventStore


@dataclass(frozen=True)
class BufferedEventStoreSettings:
    """Runtime limits that control asynchronous event-store flushing.

    Attributes:
        flush_interval_ms: Worker wake-up interval for draining queued events.
        max_batch_size: Maximum number of events written in one transaction.
        max_queue_size: Maximum pending events retained in memory.
        block_on_full: Whether producers wait when the queue is full or fail
            immediately with `RuntimeError`.
    """

    flush_interval_ms: int
    max_batch_size: int
    max_queue_size: int
    block_on_full: bool


class BufferedEventStore(EventStore):
    """Asynchronous write-through wrapper for event-store append operations.

    Ordinary runtime events are queued in memory and flushed by a background
    worker in bounded batches. Operations that must be visible immediately for
    research metadata or reads call `flush()` first and then write synchronously
    against the configured write store.
    """

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
        """Start a background flusher around an existing event store.

        Args:
            inner: Store used for reads and default writes.
            write_store: Optional separate store/connection used by the worker
                to avoid sharing a connection with readers.
            flush_interval_ms: Worker wake-up interval.
            max_batch_size: Maximum queued events written per transaction.
            max_queue_size: Maximum number of pending in-memory events.
            block_on_full: Whether producers block or fail when the queue is
                full.

        Raises:
            ValueError: If any positive queue or timing limit is invalid.
        """
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
        """Queue one event for asynchronous persistence.

        Payloads are copied before enqueueing so caller-owned mappings can be
        mutated after the call without changing the queued write.

        Raises:
            RuntimeError: If `block_on_full` is false and the queue has reached
                `max_queue_size`.
        """
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
        """Queue a run-session start record using a reserved internal event type.

        The reserved type lets the flusher call the concrete store's lifecycle
        method later instead of flattening the operation into backend-specific
        table writes in this wrapper.
        """
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
        """Queue run-session completion for the background writer.

        The payload preserves lifecycle fields exactly as the synchronous store
        expects, but durability occurs later through the worker or an explicit
        `flush()`. This keeps producer latency low while maintaining one writer
        transaction boundary for batched lifecycle events.
        """
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
        """Queue a cycle-start event without blocking on the write store.

        The method keeps the normal lifecycle API available to callers while the
        buffered store serializes the actual write on its worker thread.
        """
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
        """Queue a cycle-finish event with terminal status and error context.

        Finish records are enqueued in the same shape as synchronous stores use,
        then flushed later under the writer lock so start and finish batches do not
        interleave with synchronous research writes.
        """
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
        """Drain the pending queue and write all events before returning.

        The method takes the same write lock as the worker so explicit flushes,
        synchronous research writes, and background batches cannot interleave in
        the middle of a transaction.
        """
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
        """Stop the worker, persist pending events, and close owned stores.

        Closing sets the stop flag, waits briefly for the worker, drains any
        remaining queue items through `flush()`, then closes the read and write
        stores without double-closing when both references point to the same store.
        """
        self._stop.set()
        self._worker.join(timeout=5.0)
        self.flush()
        self._inner.close()
        if self._write_store is not self._inner:
            self._write_store.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Provide a no-op transaction scope for buffered producers.

        Callers may group enqueue calls syntactically, but durability still
        occurs later in the worker or explicit `flush()`.
        """
        yield

    def connection(self) -> Any:
        """Return the wrapped read-side connection without forcing a write flush.

        Read-heavy query helpers use this connection for local inspection. The
        method delegates to the inner store when present and returns `None` for
        stores that do not expose raw connections.
        """
        return getattr(self._inner, "connection", lambda: None)()

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
        """Flush queued lifecycle events before synchronously writing experiment metadata.

        Research metadata must be visible immediately to subsequent comparison
        queries, so this method drains asynchronous events and writes under the
        same lock used by the worker.
        """
        self.flush()
        with self._write_lock:
            self._write_store.upsert_experiment(
                experiment_id=experiment_id,
                name=name,
                description=description,
                tags=tags,
                created_at=created_at,
                updated_at=updated_at,
                metadata=metadata,
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
        """Flush queued lifecycle events before synchronously recording run start.

        Experiment-run rows participate in later comparison queries, so the write
        bypasses background buffering after pending events have been drained.
        """
        self.flush()
        with self._write_lock:
            self._write_store.record_experiment_run_start(
                experiment_run_id=experiment_run_id,
                experiment_id=experiment_id,
                run_id=run_id,
                created_at=created_at,
                status=status,
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
        """Flush queued lifecycle events before synchronously recording run completion.

        Completion metadata includes result summaries and artifact paths needed by
        recommendation tools, so the write is serialized under the worker lock
        rather than being delayed in the background queue.
        """
        self.flush()
        with self._write_lock:
            self._write_store.record_experiment_run_finish(
                experiment_run_id=experiment_run_id,
                experiment_id=experiment_id,
                run_id=run_id,
                status=status,
                finished_at=finished_at,
                result_summary=result_summary,
                provenance=provenance,
                data_quality=data_quality,
                artifact_dir=artifact_dir,
                error_message=error_message,
            )

    def list_experiment_runs(
        self,
        experiment_id: str,
        *,
        limit: int | None = None,
    ) -> list[Mapping[str, object]]:
        """Flush queued writes, then read experiment runs from the inner store."""
        self.flush()
        return self._inner.list_experiment_runs(experiment_id, limit=limit)

    def _run(self) -> None:
        """Background worker loop that periodically drains queued events."""
        interval = self._settings.flush_interval_ms / 1000.0
        while not self._stop.is_set():
            self._flush_batch()
            self._stop.wait(interval)

    def _flush_batch(self) -> None:
        """Write at most one configured batch of queued events."""
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
        """Dispatch a queued event to the matching concrete store method.

        Reserved lifecycle event types are expanded back into high-level store
        calls. All other event types are written through as ordinary append-only
        events.
        """
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
