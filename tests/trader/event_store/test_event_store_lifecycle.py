"""Contracts for constructing event-store lifecycle records.

Subject: Run, trading-session, cycle, experiment, and experiment-run lifecycle record construction.
Level: Pure domain unit contracts.
Collaborators: Real lifecycle builders with fixed identifiers, timestamps, statuses, and configuration values.
Guarantees: Each lifecycle transition yields complete, mode-aware records with stable event types and payloads.
Non-goals: Recording events, SQL statements, state-transition authorization, or orchestration execution.
"""

from __future__ import annotations

from datetime import datetime, timezone

from trader.event_store.lifecycle import (
    build_cycle_finish_record,
    build_cycle_start_record,
    build_experiment_record,
    build_experiment_run_finish_record,
    build_experiment_run_start_record,
    build_run_session_finish_records,
    build_run_session_start_records,
)


def test_run_session_start_records_include_trading_session_for_trading_runs() -> None:
    """Ensure trading run starts emit both run and trading-session records."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)

    records = build_run_session_start_records(
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

    assert [record.event_type for record in records] == ["runs", "trading_sessions"]
    assert records[0].payload == {
        "run_id": "run_1",
        "run_type": "trading",
        "started_at": timestamp,
        "finished_at": None,
        "status": "started",
        "error_message": None,
        "config_snapshot": {"mode": "once"},
        "mode": "once",
        "symbols": ["AAPL", "MSFT"],
        "timeframe": "1Min",
        "start_ts": None,
        "end_ts": None,
    }
    assert records[1].payload["session_id"] == "run_1"
    assert records[1].payload["strategy_id"] == "demo"


def test_run_session_finish_records_backtest_runs_skip_trading_session() -> None:
    """Ensure non-trading runs only produce the generic run record."""
    started_at = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 1, 21, 12, 5, tzinfo=timezone.utc)

    records = build_run_session_finish_records(
        run_id="run_1",
        run_type="backtest",
        started_at=started_at,
        finished_at=finished_at,
        status="success",
        error_message=None,
        strategy_id="demo",
        config_snapshot=None,
        mode=None,
        symbols=("AAPL",),
        timeframe="1Min",
        start_ts=started_at,
        end_ts=finished_at,
    )

    assert len(records) == 1
    assert records[0].event_type == "runs"
    assert records[0].payload["status"] == "success"
    assert records[0].payload["symbols"] == ["AAPL"]


def test_experiment_records_normalize_optional_sequences_and_mappings() -> None:
    """Ensure experiment builders copy mutable collection payloads at boundaries."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    tags = ["baseline"]
    metadata = {"owner": "test"}
    record = build_experiment_record(
        experiment_id="exp_1",
        name="Baseline",
        description=None,
        tags=tags,
        created_at=timestamp,
        updated_at=timestamp,
        metadata=metadata,
    )

    tags.append("mutated")
    metadata["owner"] = "changed"

    assert record.event_type == "experiments"
    assert record.payload["tags"] == ["baseline"]
    assert record.payload["metadata"] == {"owner": "test"}


def test_experiment_run_records_preserve_start_and_finish_shapes() -> None:
    """Ensure experiment-run start and finish records keep stable field semantics."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)

    start = build_experiment_run_start_record(
        experiment_run_id="exp_run_1",
        experiment_id="exp_1",
        run_id="run_1",
        created_at=timestamp,
        status="started",
        strategy_id="demo",
        strategy_name="Demo",
        strategy_version="1",
        symbols=("AAPL",),
        asset_class="stocks",
        timeframe="1Min",
        start_ts=timestamp,
        end_ts=timestamp,
        parameters={"fast": 2},
        assumptions={"fees": 0},
        provenance={"source": "test"},
        data_quality={"report_id": "dq_1"},
        artifact_dir="artifacts/run_1",
    )
    finish = build_experiment_run_finish_record(
        experiment_run_id="exp_run_1",
        experiment_id="exp_1",
        run_id="run_1",
        status="success",
        finished_at=timestamp,
        result_summary={"total_return": 0.1},
        provenance={"source": "test"},
        data_quality={"report_id": "dq_1"},
        artifact_dir="artifacts/run_1",
        error_message=None,
    )

    assert start.event_type == "experiment_runs"
    assert start.payload["finished_at"] is None
    assert start.payload["parameters"] == {"fast": 2}
    assert finish.event_type == "experiment_runs"
    assert finish.payload["created_at"] == timestamp
    assert finish.payload["finished_at"] == timestamp
    assert finish.payload["result_summary"] == {"total_return": 0.1}


def test_cycle_lifecycle_records_include_session_identity() -> None:
    """Ensure cycle records retain run/session identity for runtime correlation."""
    started_at = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 1, 21, 12, 1, tzinfo=timezone.utc)

    start = build_cycle_start_record(
        run_id="run_1",
        cycle_id="cycle_1",
        strategy_id="demo",
        mode="once",
        decision_ts=started_at,
        started_at=started_at,
    )
    finish = build_cycle_finish_record(
        run_id="run_1",
        cycle_id="cycle_1",
        strategy_id="demo",
        mode="once",
        decision_ts=started_at,
        started_at=started_at,
        finished_at=finished_at,
        status="success",
        error_message=None,
    )

    assert start.event_type == "run_events"
    assert start.payload["session_id"] == "run_1"
    assert start.payload["status"] == "started"
    assert finish.event_type == "run_events"
    assert finish.payload["session_id"] == "run_1"
    assert finish.payload["status"] == "success"
