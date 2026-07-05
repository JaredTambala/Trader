"""Lightweight event-store adapter implementations."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

from .base import EventStore


class NoOpEventStore(EventStore):
    """Event store implementation that intentionally discards every write.

    This store is useful for dry-run cycles and unit tests that need the
    `EventStore` contract but should not persist state. Read-oriented helpers
    return empty/default values through the base implementation.
    """

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
    """Wrapper that allows only selected event types through to an inner store.

    The cycle uses this to disable noisy event families while keeping lifecycle
    and safety events intact. Methods that represent lifecycle operations are
    delegated to the inner store so filtering stays centralized in
    `record_event`.
    """

    def __init__(self, inner: EventStore, *, allowed_event_types: set[str]) -> None:
        """Create a filtering facade around an existing event store.

        Args:
            inner: Store that receives allowed events and owns durable state.
            allowed_event_types: Event/table names that should be persisted.
        """
        self._inner = inner
        self._allowed = set(allowed_event_types)

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Persist an event only when its type is enabled.

        Disabled events are dropped silently by design because this wrapper is
        driven by config flags for optional observability streams. Required
        lifecycle methods delegate directly and are not filtered here.
        """
        if event_type not in self._allowed:
            return
        self._inner.record_event(event_type, payload)

    def connection(self) -> Any:
        """Expose the inner connection for read-only helper queries when available to callers."""
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
        """Delegate run-session start recording without applying optional event filters to lifecycle data."""
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
        """Delegate run-session completion recording without applying optional event filters to lifecycle data."""
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
        """Delegate cycle-start recording without applying optional event filters to lifecycle data."""
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
        """Delegate cycle completion recording without applying optional event filters to lifecycle data."""
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
        """Delegate experiment metadata upserts to the inner store without event filtering."""
        self._inner.upsert_experiment(
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
        """Delegate experiment-run start recording to the inner store without event filtering."""
        self._inner.record_experiment_run_start(
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
        """Delegate experiment-run completion recording to the inner store without event filtering."""
        self._inner.record_experiment_run_finish(
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
        """Return experiment runs from the inner store after any inner flushing."""
        return self._inner.list_experiment_runs(experiment_id, limit=limit)

    def flush(self) -> None:
        """Flush the wrapped store so callers see durable state after buffered writes."""
        return self._inner.flush()

    def close(self) -> None:
        """Close the wrapped store and release its resources through the inner implementation."""
        return self._inner.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Run a transaction scope owned by the wrapped store implementation for writes."""
        with self._inner.transaction():
            yield
