"""Pure lifecycle event-record builders for event-store implementations.

The base `EventStore` contract exposes high-level lifecycle methods, while
concrete stores persist append-only event rows or SQL upserts. This module keeps
the default append-only record shapes in one deterministic place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

__all__ = [
    "EventRecord",
    "build_cycle_finish_payload",
    "build_cycle_finish_record",
    "build_cycle_start_payload",
    "build_cycle_start_record",
    "build_experiment_record",
    "build_experiment_run_finish_record",
    "build_experiment_run_start_record",
    "build_run_session_finish_payload",
    "build_run_session_finish_records",
    "build_run_session_start_payload",
    "build_run_session_start_records",
]


@dataclass(frozen=True)
class EventRecord:
    """Append-only event-store record prepared for `record_event`.

    Attributes:
        event_type: Target event collection or table name.
        payload: Stable payload mapping for the event type.
    """

    event_type: str
    payload: Mapping[str, object]


def build_run_session_start_payload(
    *,
    run_id: str,
    run_type: str,
    started_at: object,
    status: str,
    strategy_id: str | None,
    config_snapshot: object | None,
    mode: str | None,
    symbols: Sequence[str] | None,
    timeframe: str | None,
    start_ts: object | None,
    end_ts: object | None,
) -> dict[str, object]:
    """Return normalized call payload for a run-session start."""
    return {
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
    }


def build_run_session_start_records(
    *,
    run_id: str,
    run_type: str,
    started_at: object,
    status: str,
    strategy_id: str | None,
    config_snapshot: object | None,
    mode: str | None,
    symbols: Sequence[str] | None,
    timeframe: str | None,
    start_ts: object | None,
    end_ts: object | None,
) -> tuple[EventRecord, ...]:
    """Return append-only records for a run-session start.

    Trading runs also emit a `trading_sessions` record keyed by the run ID so
    runtime status and operator tooling can query session state directly.
    """
    payload = build_run_session_start_payload(
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
    run_payload = {key: value for key, value in payload.items() if key != "strategy_id"}
    records = [EventRecord("runs", run_payload)]
    if run_type == "trading":
        records.append(
            EventRecord(
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
                    "symbols": payload["symbols"],
                    "timeframe": timeframe,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                },
            )
        )
    return tuple(records)


def build_run_session_finish_payload(
    *,
    run_id: str,
    run_type: str,
    started_at: object,
    finished_at: object,
    status: str,
    error_message: str | None,
    strategy_id: str | None,
    config_snapshot: object | None,
    mode: str | None,
    symbols: Sequence[str] | None,
    timeframe: str | None,
    start_ts: object | None,
    end_ts: object | None,
) -> dict[str, object]:
    """Return normalized call payload for a run-session finish."""
    return {
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
    }


def build_run_session_finish_records(
    *,
    run_id: str,
    run_type: str,
    started_at: object,
    finished_at: object,
    status: str,
    error_message: str | None,
    strategy_id: str | None,
    config_snapshot: object | None,
    mode: str | None,
    symbols: Sequence[str] | None,
    timeframe: str | None,
    start_ts: object | None,
    end_ts: object | None,
) -> tuple[EventRecord, ...]:
    """Return append-only records for a run-session finish."""
    payload = build_run_session_finish_payload(
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
    run_payload = {key: value for key, value in payload.items() if key != "strategy_id"}
    records = [EventRecord("runs", run_payload)]
    if run_type == "trading":
        records.append(
            EventRecord(
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
                    "symbols": payload["symbols"],
                    "timeframe": timeframe,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                },
            )
        )
    return tuple(records)


def build_experiment_record(
    *,
    experiment_id: str,
    name: str,
    description: str | None,
    tags: Sequence[str] | None,
    created_at: object | None,
    updated_at: object | None,
    metadata: Mapping[str, object] | None,
) -> EventRecord:
    """Return the default append-only experiment metadata record."""
    return EventRecord(
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


def build_experiment_run_start_record(
    *,
    experiment_run_id: str,
    experiment_id: str,
    run_id: str,
    created_at: object,
    status: str,
    strategy_id: str | None,
    strategy_name: str | None,
    strategy_version: str | None,
    symbols: Sequence[str] | None,
    asset_class: str | None,
    timeframe: str | None,
    start_ts: object | None,
    end_ts: object | None,
    parameters: Mapping[str, object] | None,
    assumptions: Mapping[str, object] | None,
    provenance: Mapping[str, object] | None,
    data_quality: Mapping[str, object] | None,
    artifact_dir: str | None,
) -> EventRecord:
    """Return the default append-only experiment-run start record."""
    return EventRecord(
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


def build_experiment_run_finish_record(
    *,
    experiment_run_id: str,
    experiment_id: str,
    run_id: str,
    status: str,
    finished_at: object,
    result_summary: Mapping[str, object] | None,
    provenance: Mapping[str, object] | None,
    data_quality: Mapping[str, object] | None,
    artifact_dir: str | None,
    error_message: str | None,
) -> EventRecord:
    """Return the default append-only experiment-run finish record."""
    return EventRecord(
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


def build_cycle_start_payload(
    *,
    run_id: str,
    cycle_id: str,
    strategy_id: str,
    mode: str,
    decision_ts: object,
    started_at: object,
) -> dict[str, object]:
    """Return normalized payload for a cycle-start lifecycle record."""
    return {
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
    }


def build_cycle_start_record(
    *,
    run_id: str,
    cycle_id: str,
    strategy_id: str,
    mode: str,
    decision_ts: object,
    started_at: object,
) -> EventRecord:
    """Return the append-only record for a cycle start."""
    return EventRecord(
        "run_events",
        build_cycle_start_payload(
            run_id=run_id,
            cycle_id=cycle_id,
            strategy_id=strategy_id,
            mode=mode,
            decision_ts=decision_ts,
            started_at=started_at,
        ),
    )


def build_cycle_finish_payload(
    *,
    run_id: str,
    cycle_id: str,
    strategy_id: str,
    mode: str,
    decision_ts: object,
    started_at: object,
    finished_at: object,
    status: str,
    error_message: str | None,
) -> dict[str, object]:
    """Return normalized payload for a cycle-finish lifecycle record."""
    return {
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
    }


def build_cycle_finish_record(
    *,
    run_id: str,
    cycle_id: str,
    strategy_id: str,
    mode: str,
    decision_ts: object,
    started_at: object,
    finished_at: object,
    status: str,
    error_message: str | None,
) -> EventRecord:
    """Return the append-only record for a cycle finish."""
    return EventRecord(
        "run_events",
        build_cycle_finish_payload(
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
