"""Tests for event-store record normalization helpers."""

from datetime import datetime, timezone

import pytest

from trader.event_store.records import (
    EXPERIMENT_RUN_FIELDS,
    build_postgres_event_insert_plan,
    cycle_finish_parameters,
    cycle_start_parameters,
    experiment_run_finish_parameters,
    experiment_run_row_to_record,
    experiment_run_start_parameters,
    json_payload_or_empty,
    json_payload_or_none,
    list_experiment_runs_query_plan,
    postgres_text_array_or_empty,
    postgres_text_array_or_none,
    run_session_finish_parameters,
    run_session_start_parameters,
    trading_session_finish_parameters,
    trading_session_start_parameters,
    upsert_experiment_parameters,
)


def test_postgres_event_insert_plan_preserves_payload_order() -> None:
    """Ensure generic inserts keep column and value order aligned."""
    payload = {
        "order_event_id": "order_evt_1",
        "client_order_id": "order_1",
        "status": "submitted",
    }

    plan = build_postgres_event_insert_plan("order_events", payload)

    assert plan.event_type == "order_events"
    assert plan.columns == ("order_event_id", "client_order_id", "status")
    assert plan.values == ("order_evt_1", "order_1", "submitted")
    assert plan.ignore_bar_conflicts is False


def test_postgres_event_insert_plan_marks_bar_tables_idempotent() -> None:
    """Ensure bar event inserts carry the Postgres conflict policy."""
    plan = build_postgres_event_insert_plan(
        "stock_bar_events",
        {"symbol": "AAPL", "timeframe": "1Min", "ts": "now", "source": "test"},
    )

    assert plan.ignore_bar_conflicts is True


def test_postgres_event_insert_plan_rejects_unknown_event_types() -> None:
    """Ensure unsupported tables fail before SQL construction."""
    with pytest.raises(ValueError, match="Unknown event type: unknown_events"):
        build_postgres_event_insert_plan("unknown_events", {"id": "1"})


def test_json_payload_helpers_serialize_optional_payloads() -> None:
    """Ensure event-store JSON normalization handles absent and datetime values."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)

    assert json_payload_or_none(None) is None
    assert json_payload_or_none({"ts": timestamp}) == '{"ts": "2026-01-21 12:00:00+00:00"}'
    assert json_payload_or_empty(None) == "{}"
    assert json_payload_or_empty({"ts": timestamp}) == '{"ts": "2026-01-21 12:00:00+00:00"}'


def test_postgres_text_array_helpers_preserve_null_semantics() -> None:
    """Ensure optional and non-null text-array normalization remain distinct."""
    assert postgres_text_array_or_none(None) is None
    assert postgres_text_array_or_none(("AAPL", "MSFT")) == ["AAPL", "MSFT"]
    assert postgres_text_array_or_empty(None) == []
    assert postgres_text_array_or_empty(("sample",)) == ["sample"]


def test_experiment_run_row_mapping_uses_stable_field_order() -> None:
    """Ensure experiment-run query rows map into the public dictionary shape."""
    row = tuple(range(len(EXPERIMENT_RUN_FIELDS)))

    record = experiment_run_row_to_record(row)

    assert tuple(record) == EXPERIMENT_RUN_FIELDS
    assert record["experiment_run_id"] == 0
    assert record["error_message"] == len(EXPERIMENT_RUN_FIELDS) - 1


def test_list_experiment_runs_query_plan_adds_optional_limit() -> None:
    """Ensure experiment-run list queries keep params aligned to placeholders."""
    unbounded = list_experiment_runs_query_plan("exp_1")
    bounded = list_experiment_runs_query_plan("exp_1", limit=5)

    assert unbounded.query.count("%s") == 1
    assert unbounded.parameters == ("exp_1",)
    assert bounded.query.endswith(" LIMIT %s")
    assert bounded.query.count("%s") == 2
    assert bounded.parameters == ("exp_1", 5)


def test_run_session_sql_parameters_normalize_config_and_symbols() -> None:
    """Ensure run-session SQL parameters preserve statement order."""
    started_at = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 1, 21, 12, 5, tzinfo=timezone.utc)

    start_params = run_session_start_parameters(
        run_id="run_1",
        run_type="trading",
        started_at=started_at,
        status="started",
        config_snapshot={"mode": "once"},
        mode="once",
        symbols=("AAPL", "MSFT"),
        timeframe="1Min",
        start_ts=None,
        end_ts=None,
    )
    finish_params = run_session_finish_parameters(
        run_id="run_1",
        run_type="trading",
        started_at=started_at,
        finished_at=finished_at,
        status="success",
        error_message=None,
        config_snapshot={"mode": "once"},
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
        start_ts=started_at,
        end_ts=finished_at,
    )

    assert start_params == [
        "run_1",
        "trading",
        started_at,
        "started",
        None,
        '{"mode": "once"}',
        "once",
        ["AAPL", "MSFT"],
        "1Min",
        None,
        None,
    ]
    assert len(finish_params) == 12
    assert finish_params[3:8] == [finished_at, "success", None, '{"mode": "once"}', "once"]


def test_trading_session_sql_parameters_include_strategy_id() -> None:
    """Ensure trading-session parameter builders mirror run-session ordering."""
    started_at = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2026, 1, 21, 12, 5, tzinfo=timezone.utc)

    start_params = trading_session_start_parameters(
        run_id="run_1",
        strategy_id="demo",
        started_at=started_at,
        status="started",
        config_snapshot=None,
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
        start_ts=None,
        end_ts=None,
    )
    finish_params = trading_session_finish_parameters(
        run_id="run_1",
        strategy_id="demo",
        started_at=started_at,
        finished_at=finished_at,
        status="failed",
        error_message="boom",
        config_snapshot=None,
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
        start_ts=None,
        end_ts=None,
    )

    assert start_params[:5] == ["run_1", "demo", started_at, "started", None]
    assert finish_params[:7] == ["run_1", "demo", started_at, finished_at, "failed", "boom", None]


def test_cycle_sql_parameters_include_session_id_alias() -> None:
    """Ensure cycle parameter builders use run ID as session identity."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)

    start_params = cycle_start_parameters(
        run_id="run_1",
        cycle_id="cycle_1",
        strategy_id="demo",
        mode="once",
        decision_ts=timestamp,
        started_at=timestamp,
    )
    finish_params = cycle_finish_parameters(
        run_id="run_1",
        cycle_id="cycle_1",
        strategy_id="demo",
        mode="once",
        decision_ts=timestamp,
        started_at=timestamp,
        finished_at=timestamp,
        status="success",
        error_message=None,
    )

    assert start_params == ["cycle_1", "run_1", "run_1", "demo", "once", timestamp, timestamp]
    assert finish_params[:3] == ["cycle_1", "run_1", "run_1"]
    assert len(finish_params) == 10


def test_experiment_sql_parameters_normalize_json_payloads() -> None:
    """Ensure experiment parameter builders match statement JSON semantics."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)

    experiment_params = upsert_experiment_parameters(
        experiment_id="exp_1",
        name="Demo",
        description=None,
        tags=("baseline",),
        created_at=timestamp,
        updated_at=timestamp,
        metadata={"owner": "test"},
    )
    start_params = experiment_run_start_parameters(
        experiment_run_id="exp_run_1",
        experiment_id="exp_1",
        run_id="run_1",
        status="started",
        created_at=timestamp,
        strategy_id="demo",
        strategy_name="Demo",
        strategy_version="1",
        symbols=("AAPL",),
        asset_class="stocks",
        timeframe="1Min",
        start_ts=timestamp,
        end_ts=timestamp,
        parameters={"fast": 2},
        assumptions=None,
        provenance={"source": "test"},
        data_quality={"report_id": "dq_1"},
        artifact_dir="artifacts/run_1",
    )
    finish_params = experiment_run_finish_parameters(
        experiment_run_id="exp_run_1",
        experiment_id="exp_1",
        run_id="run_1",
        status="success",
        finished_at=timestamp,
        provenance={"source": "test"},
        data_quality={"report_id": "dq_1"},
        result_summary={"total_return": 0.1},
        artifact_dir="artifacts/run_1",
        error_message=None,
    )

    assert experiment_params == [
        "exp_1",
        "Demo",
        None,
        ["baseline"],
        timestamp,
        timestamp,
        '{"owner": "test"}',
    ]
    assert start_params[13:17] == [
        '{"fast": 2}',
        "{}",
        '{"source": "test"}',
        '{"report_id": "dq_1"}',
    ]
    assert finish_params[6:9] == [
        '{"source": "test"}',
        '{"report_id": "dq_1"}',
        '{"total_return": 0.1}',
    ]
