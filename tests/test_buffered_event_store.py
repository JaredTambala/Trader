"""Tests for buffered event-store write planning helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

from trader.event_store import EventStore
from trader.event_store.buffered_events import (
    CYCLE_FINISH_EVENT,
    CYCLE_START_EVENT,
    RUN_SESSION_FINISH_EVENT,
    RUN_SESSION_START_EVENT,
    CycleFinishWrite,
    CycleStartWrite,
    RecordEventWrite,
    RunSessionFinishWrite,
    RunSessionStartWrite,
    build_cycle_finish_payload,
    build_cycle_start_payload,
    build_run_session_finish_payload,
    build_run_session_start_payload,
    plan_buffered_event_write,
    write_buffered_event,
)


class RecordingStore(EventStore):
    """In-memory event-store fake that records high-level method calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    def record_event(self, event_type: str, payload: Mapping[str, object]) -> None:
        """Record an ordinary event write."""
        self.calls.append(("record_event", {"event_type": event_type, "payload": dict(payload)}))

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
        """Record a run-session start call."""
        self.calls.append(
            (
                "record_run_session_start",
                {
                    "run_id": run_id,
                    "run_type": run_type,
                    "started_at": started_at,
                    "status": status,
                    "strategy_id": strategy_id,
                    "config_snapshot": config_snapshot,
                    "mode": mode,
                    "symbols": tuple(symbols) if symbols is not None else None,
                    "timeframe": timeframe,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                },
            )
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
        """Record a run-session finish call."""
        self.calls.append(
            (
                "record_run_session_finish",
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
                    "symbols": tuple(symbols) if symbols is not None else None,
                    "timeframe": timeframe,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                },
            )
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
        """Record a cycle-start call."""
        self.calls.append(
            (
                "record_cycle_start",
                {
                    "run_id": run_id,
                    "cycle_id": cycle_id,
                    "strategy_id": strategy_id,
                    "mode": mode,
                    "decision_ts": decision_ts,
                    "started_at": started_at,
                },
            )
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
        """Record a cycle-finish call."""
        self.calls.append(
            (
                "record_cycle_finish",
                {
                    "run_id": run_id,
                    "cycle_id": cycle_id,
                    "strategy_id": strategy_id,
                    "mode": mode,
                    "decision_ts": decision_ts,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "status": status,
                    "error_message": error_message,
                },
            )
        )


def test_plan_buffered_event_write_preserves_ordinary_events() -> None:
    """Ensure non-reserved events remain ordinary append-only writes."""
    payload = {"client_order_id": "order_1", "status": "submitted"}

    write = plan_buffered_event_write("order_events", payload)

    assert isinstance(write, RecordEventWrite)
    assert write.event_type == "order_events"
    assert write.payload == payload
    assert write.payload is not payload


def test_plan_buffered_event_write_maps_run_session_start() -> None:
    """Ensure queued run-session start payloads become high-level store calls."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    payload = build_run_session_start_payload(
        run_id="run_1",
        run_type="trading",
        started_at=timestamp,
        status="started",
        strategy_id="demo",
        config_snapshot={"mode": "once"},
        mode="once",
        symbols=("AAPL", "MSFT"),
        timeframe="1Min",
        start_ts=None,
        end_ts=None,
    )

    write = plan_buffered_event_write(RUN_SESSION_START_EVENT, payload)

    assert isinstance(write, RunSessionStartWrite)
    assert write.run_id == "run_1"
    assert write.symbols == ("AAPL", "MSFT")
    assert write.config_snapshot == {"mode": "once"}


def test_plan_buffered_event_write_maps_run_session_finish() -> None:
    """Ensure queued run-session finish payloads retain terminal status fields."""
    started_at = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 1, 21, 12, 1, tzinfo=timezone.utc)
    payload = build_run_session_finish_payload(
        run_id="run_1",
        run_type="trading",
        started_at=started_at,
        finished_at=finished_at,
        status="failed",
        error_message="boom",
        strategy_id="demo",
        config_snapshot=None,
        mode="loop",
        symbols=("AAPL",),
        timeframe="1Min",
        start_ts=None,
        end_ts=None,
    )

    write = plan_buffered_event_write(RUN_SESSION_FINISH_EVENT, payload)

    assert isinstance(write, RunSessionFinishWrite)
    assert write.finished_at == finished_at
    assert write.status == "failed"
    assert write.error_message == "boom"


def test_plan_buffered_event_write_maps_cycle_start_and_finish() -> None:
    """Ensure cycle lifecycle payloads become typed cycle write plans."""
    started_at = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 1, 21, 12, 1, tzinfo=timezone.utc)

    start = plan_buffered_event_write(
        CYCLE_START_EVENT,
        build_cycle_start_payload(
            run_id="run_1",
            cycle_id="cycle_1",
            strategy_id="demo",
            mode="once",
            decision_ts=started_at,
            started_at=started_at,
        ),
    )
    finish = plan_buffered_event_write(
        CYCLE_FINISH_EVENT,
        build_cycle_finish_payload(
            run_id="run_1",
            cycle_id="cycle_1",
            strategy_id="demo",
            mode="once",
            decision_ts=started_at,
            started_at=started_at,
            finished_at=finished_at,
            status="success",
            error_message=None,
        ),
    )

    assert isinstance(start, CycleStartWrite)
    assert start.cycle_id == "cycle_1"
    assert isinstance(finish, CycleFinishWrite)
    assert finish.finished_at == finished_at
    assert finish.status == "success"


def test_write_buffered_event_dispatches_high_level_store_methods() -> None:
    """Ensure write plans call lifecycle methods instead of generic events."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    store = RecordingStore()
    start_write = plan_buffered_event_write(
        RUN_SESSION_START_EVENT,
        build_run_session_start_payload(
            run_id="run_1",
            run_type="trading",
            started_at=timestamp,
            status="started",
            strategy_id="demo",
            config_snapshot=None,
            mode="once",
            symbols=("AAPL",),
            timeframe="1Min",
            start_ts=None,
            end_ts=None,
        ),
    )
    event_write = plan_buffered_event_write("signal_events", {"signal": 1})

    write_buffered_event(store, start_write)
    write_buffered_event(store, event_write)

    assert store.calls == [
        (
            "record_run_session_start",
            {
                "run_id": "run_1",
                "run_type": "trading",
                "started_at": timestamp,
                "status": "started",
                "strategy_id": "demo",
                "config_snapshot": None,
                "mode": "once",
                "symbols": ("AAPL",),
                "timeframe": "1Min",
                "start_ts": None,
                "end_ts": None,
            },
        ),
        ("record_event", {"event_type": "signal_events", "payload": {"signal": 1}}),
    ]
