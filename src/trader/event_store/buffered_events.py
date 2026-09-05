"""Typed write plans for buffered event-store lifecycle events.

The buffered event store queues plain event payloads in producer threads, then
turns reserved lifecycle event types back into high-level `EventStore` method
calls on the writer thread. This module owns that deterministic translation so
the queue and transaction wrapper can stay focused on side effects.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Mapping, TypeAlias

from .base import EventStore
from .lifecycle import (
    build_cycle_finish_payload,
    build_cycle_start_payload,
    build_run_session_finish_payload,
    build_run_session_start_payload,
)

__all__ = [
    "CYCLE_FINISH_EVENT",
    "CYCLE_START_EVENT",
    "RUN_SESSION_FINISH_EVENT",
    "RUN_SESSION_START_EVENT",
    "BufferedEventWrite",
    "CycleFinishWrite",
    "CycleStartWrite",
    "RecordEventWrite",
    "RunSessionFinishWrite",
    "RunSessionStartWrite",
    "build_cycle_finish_payload",
    "build_cycle_start_payload",
    "build_run_session_finish_payload",
    "build_run_session_start_payload",
    "plan_buffered_event_write",
    "write_buffered_event",
]

RUN_SESSION_START_EVENT = "__run_session_start__"
RUN_SESSION_FINISH_EVENT = "__run_session_finish__"
CYCLE_START_EVENT = "__cycle_start__"
CYCLE_FINISH_EVENT = "__cycle_finish__"


@dataclass(frozen=True)
class RecordEventWrite:
    """Ordinary append-only event write prepared for the concrete store.

    Attributes:
        event_type: Target event/table name.
        payload: Event payload copied from the queued mapping.
    """

    event_type: str
    payload: Mapping[str, object]


@dataclass(frozen=True)
class RunSessionStartWrite:
    """Run-session start call prepared from a reserved buffered event."""

    run_id: str
    run_type: str
    started_at: object
    status: str
    strategy_id: str | None
    config_snapshot: object | None
    mode: str | None
    symbols: tuple[str, ...] | None
    timeframe: str | None
    start_ts: object | None
    end_ts: object | None


@dataclass(frozen=True)
class RunSessionFinishWrite:
    """Run-session finish call prepared from a reserved buffered event."""

    run_id: str
    run_type: str
    started_at: object
    finished_at: object
    status: str
    error_message: str | None
    strategy_id: str | None
    config_snapshot: object | None
    mode: str | None
    symbols: tuple[str, ...] | None
    timeframe: str | None
    start_ts: object | None
    end_ts: object | None


@dataclass(frozen=True)
class CycleStartWrite:
    """Cycle-start call prepared from a reserved buffered event."""

    run_id: str
    cycle_id: str
    strategy_id: str
    mode: str
    decision_ts: object
    started_at: object


@dataclass(frozen=True)
class CycleFinishWrite:
    """Cycle-finish call prepared from a reserved buffered event."""

    run_id: str
    cycle_id: str
    strategy_id: str
    mode: str
    decision_ts: object
    started_at: object
    finished_at: object
    status: str
    error_message: str | None


BufferedEventWrite: TypeAlias = (
    RecordEventWrite
    | RunSessionStartWrite
    | RunSessionFinishWrite
    | CycleStartWrite
    | CycleFinishWrite
)


def plan_buffered_event_write(event_type: str, payload: Mapping[str, object]) -> BufferedEventWrite:
    """Return the concrete store write represented by one queued event.

    Args:
        event_type: Queued event type. Reserved lifecycle names are expanded into
            high-level event-store operations; all other names remain ordinary
            append-only event writes.
        payload: Queued event payload.

    Returns:
        A typed write plan consumed by `write_buffered_event`.

    Raises:
        KeyError: If a reserved lifecycle payload is missing a required field.
    """
    if event_type == RUN_SESSION_START_EVENT:
        return RunSessionStartWrite(
            run_id=str(payload["run_id"]),
            run_type=str(payload["run_type"]),
            started_at=payload["started_at"],
            status=str(payload["status"]),
            strategy_id=_optional_text(payload.get("strategy_id")),
            config_snapshot=payload.get("config_snapshot"),
            mode=_optional_text(payload.get("mode")),
            symbols=_optional_symbols(payload.get("symbols")),
            timeframe=_optional_text(payload.get("timeframe")),
            start_ts=payload.get("start_ts"),
            end_ts=payload.get("end_ts"),
        )
    if event_type == RUN_SESSION_FINISH_EVENT:
        return RunSessionFinishWrite(
            run_id=str(payload["run_id"]),
            run_type=str(payload["run_type"]),
            started_at=payload["started_at"],
            finished_at=payload["finished_at"],
            status=str(payload["status"]),
            error_message=_optional_text(payload.get("error_message")),
            strategy_id=_optional_text(payload.get("strategy_id")),
            config_snapshot=payload.get("config_snapshot"),
            mode=_optional_text(payload.get("mode")),
            symbols=_optional_symbols(payload.get("symbols")),
            timeframe=_optional_text(payload.get("timeframe")),
            start_ts=payload.get("start_ts"),
            end_ts=payload.get("end_ts"),
        )
    if event_type == CYCLE_START_EVENT:
        return CycleStartWrite(
            run_id=str(payload["run_id"]),
            cycle_id=str(payload["cycle_id"]),
            strategy_id=str(payload["strategy_id"]),
            mode=str(payload["mode"]),
            decision_ts=payload["decision_ts"],
            started_at=payload["started_at"],
        )
    if event_type == CYCLE_FINISH_EVENT:
        return CycleFinishWrite(
            run_id=str(payload["run_id"]),
            cycle_id=str(payload["cycle_id"]),
            strategy_id=str(payload["strategy_id"]),
            mode=str(payload["mode"]),
            decision_ts=payload["decision_ts"],
            started_at=payload["started_at"],
            finished_at=payload["finished_at"],
            status=str(payload["status"]),
            error_message=_optional_text(payload.get("error_message")),
        )
    return RecordEventWrite(event_type=event_type, payload=dict(payload))


def write_buffered_event(store: EventStore, write: BufferedEventWrite) -> None:
    """Apply one buffered event write plan to a concrete event store."""
    if isinstance(write, RecordEventWrite):
        store.record_event(write.event_type, write.payload)
        return
    if isinstance(write, RunSessionStartWrite):
        store.record_run_session_start(
            run_id=write.run_id,
            run_type=write.run_type,
            started_at=write.started_at,
            status=write.status,
            strategy_id=write.strategy_id,
            config_snapshot=write.config_snapshot,
            mode=write.mode,
            symbols=write.symbols,
            timeframe=write.timeframe,
            start_ts=write.start_ts,
            end_ts=write.end_ts,
        )
        return
    if isinstance(write, RunSessionFinishWrite):
        store.record_run_session_finish(
            run_id=write.run_id,
            run_type=write.run_type,
            started_at=write.started_at,
            finished_at=write.finished_at,
            status=write.status,
            error_message=write.error_message,
            strategy_id=write.strategy_id,
            config_snapshot=write.config_snapshot,
            mode=write.mode,
            symbols=write.symbols,
            timeframe=write.timeframe,
            start_ts=write.start_ts,
            end_ts=write.end_ts,
        )
        return
    if isinstance(write, CycleStartWrite):
        store.record_cycle_start(
            run_id=write.run_id,
            cycle_id=write.cycle_id,
            strategy_id=write.strategy_id,
            mode=write.mode,
            decision_ts=write.decision_ts,
            started_at=write.started_at,
        )
        return
    store.record_cycle_finish(
        run_id=write.run_id,
        cycle_id=write.cycle_id,
        strategy_id=write.strategy_id,
        mode=write.mode,
        decision_ts=write.decision_ts,
        started_at=write.started_at,
        finished_at=write.finished_at,
        status=write.status,
        error_message=write.error_message,
    )


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_symbols(value: object | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, Sequence):
        return (str(value),)
    return tuple(str(item) for item in value)
