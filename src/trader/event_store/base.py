"""Event-store contracts and lightweight wrappers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator, Mapping, Sequence


class EventStore(ABC):
    """Contract for append-only runtime, market-data, and research events.

    Implementations own physical persistence and conflict handling, while
    callers use stable event names and payload mappings. Convenience methods in
    this base class translate higher-level lifecycle operations into append-only
    records so runtime orchestration does not need backend-specific SQL.
    """

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
        """Record experiment metadata in stores that support research grouping.

        The base implementation emits a generic `experiments` event so simple
        stores can still preserve the payload, while database-backed stores can
        override this method to perform an actual upsert keyed by `experiment_id`.
        """
        self.record_event(
            "experiments",
            {
                "experiment_id": experiment_id,
                "name": name,
                "description": description,
                "tags": list(tags or ()),
                "created_at": created_at,
                "updated_at": updated_at,
                "metadata": dict(metadata or {}),
            },
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
        """Record initial metadata for a research experiment run.

        The base implementation emits a complete `experiment_runs` event with run
        identity, strategy metadata, universe, parameters, assumptions, provenance,
        data-quality context, and artifact location. Finish-specific fields are
        initialized to empty values for stores that model starts and finishes as
        append-only events.
        """
        self.record_event(
            "experiment_runs",
            {
                "experiment_run_id": experiment_run_id,
                "experiment_id": experiment_id,
                "run_id": run_id,
                "status": status,
                "created_at": created_at,
                "finished_at": None,
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "strategy_version": strategy_version,
                "symbols": list(symbols) if symbols is not None else None,
                "asset_class": asset_class,
                "timeframe": timeframe,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "parameters": dict(parameters or {}),
                "assumptions": dict(assumptions or {}),
                "provenance": dict(provenance or {}),
                "data_quality": dict(data_quality or {}),
                "result_summary": None,
                "artifact_dir": artifact_dir,
                "error_message": None,
            },
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
        """Record terminal metadata for a research experiment run.

        The base implementation emits a second `experiment_runs` event containing
        terminal status, finish time, result summary, updated provenance,
        data-quality context, artifact location, and optional error text. Concrete
        stores may merge this with the start row instead of appending.
        """
        self.record_event(
            "experiment_runs",
            {
                "experiment_run_id": experiment_run_id,
                "experiment_id": experiment_id,
                "run_id": run_id,
                "status": status,
                "created_at": finished_at,
                "finished_at": finished_at,
                "strategy_id": None,
                "strategy_name": None,
                "strategy_version": None,
                "symbols": None,
                "asset_class": None,
                "timeframe": None,
                "start_ts": None,
                "end_ts": None,
                "parameters": None,
                "assumptions": None,
                "provenance": dict(provenance or {}),
                "data_quality": dict(data_quality or {}),
                "result_summary": dict(result_summary or {}),
                "artifact_dir": artifact_dir,
                "error_message": error_message,
            },
        )

    def list_experiment_runs(
        self,
        experiment_id: str,
        *,
        limit: int | None = None,
    ) -> list[Mapping[str, object]]:
        """Return experiment-run rows for stores that support comparison queries.

        Append-only or in-memory stores that cannot query historical research runs
        return an empty list by default. Persistent stores override this to provide
        newest-first rows consumed by research comparison and recommendation tools.
        """
        return []

    def record_cycle_start(
        self,
        run_id: str,
        cycle_id: str,
        strategy_id: str,
        mode: str,
        decision_ts: object,
        started_at: object,
    ) -> None:
        """Record the start of a trading decision cycle.

        The event includes run/session identity, cycle ID, strategy, mode, decision
        timestamp, start time, and an initial `started` status so observability
        tools can correlate later orders, fills, and finish records with the same
        cycle.
        """
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
        """Record completion metadata for a trading decision cycle.

        The event repeats the cycle identity fields from start, adds finish time,
        terminal status, and optional error text, allowing append-only stores and
        database stores to expose the same lifecycle semantics.
        """
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
        """Record a legacy run-start event by mapping the run ID to a cycle ID.

        Older callers used run-level lifecycle methods before explicit cycle IDs
        existed. The alias preserves that API by using `run_id` for both the run
        and cycle identifiers, then delegating to `record_cycle_start`.
        """
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
        """Record a legacy run-finish event by delegating to cycle completion.

        The alias keeps older integrations working while storing lifecycle data in
        the newer cycle-oriented shape, using `run_id` as the cycle identifier.
        """
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
        """Release any resources held by the store implementation after use.

        Raises:
            None.
        """
        return None

    def flush(self) -> None:
        """Flush any buffered events to the underlying store before reads continue."""
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


def __getattr__(name: str) -> object:
    """Lazily expose adapter classes formerly defined in this module."""
    if name in {"FilteredEventStore", "NoOpEventStore"}:
        from .adapters import FilteredEventStore, NoOpEventStore

        return {
            "FilteredEventStore": FilteredEventStore,
            "NoOpEventStore": NoOpEventStore,
        }[name]
    raise AttributeError(name)
