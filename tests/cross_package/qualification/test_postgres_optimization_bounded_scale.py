"""Bounded multi-symbol optimization scale and projection qualification.

Subject: Resource-bounded grid and random optimization over a realistic multi-symbol dataset.
Level: Cross-package controlled qualification.
Collaborators: Core events, research experiment services, Postgres artifacts, and projection tables.
Guarantees: Declared scale ceilings hold while canonical and typed projections remain reconciled.
Non-goals: Unbounded performance benchmarking, provider comparison, or production capacity planning.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

import pytest

from trader.event_store import PostgresEventStore
from trader_research.experiments import (
    BacktestOptimizationTrialExecutor,
    create_backtest_specification,
    get_parameter_optimization_results,
    run_backtest_specification,
    run_parameter_optimization,
    validate_backtest_specification,
)
from trader_research.governance.artifacts import (
    BACKTEST_RUN,
    BACKTEST_SPECIFICATION,
    BACKTEST_SPECIFICATION_VALIDATION_REPORT,
    IMPLEMENTATION_VALIDATION_REPORT,
    IMPLEMENTATION_VERSION,
    PARAMETER_OPTIMIZATION_PLAN,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
    RISK_STACK_SPECIFICATION,
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT,
    STRATEGY_SPECIFICATION,
    STRATEGY_SPECIFICATION_VALIDATION_REPORT,
)
from trader_research.infrastructure.postgres import PostgresResearchArtifactStore
from tests.cross_package.qualification.support.optimization_qualification import prepare_optimization_qualification
from tests.cross_package.qualification.support.postgres_57r import (
    clear_57r_control_evidence,
    save_57r_scale_result,
)
from tests.cross_package.qualification.support.realistic_optimization_fixture import (
    BACKTEST_ASSUMPTIONS,
    INITIAL_CASH,
    SYMBOLS,
    build_bounded_scale_region,
    data_evidence,
)


_MAX_PROFILE_SECONDS = 900.0
_TUNABLE_FIELDS = (
    "/strategy/parameters/lookback_bars",
    "/strategy/parameters/entry_threshold_bps",
    "/strategy/parameters/exit_threshold_bps",
)
_GRID_SPACE = (
    {
        "path": "/strategy/parameters/lookback_bars",
        "type": "categorical",
        "values": [2, 3, 4, 5],
    },
    {
        "path": "/strategy/parameters/entry_threshold_bps",
        "type": "categorical",
        "values": [10.0, 15.0, 20.0, 25.0],
    },
    {
        "path": "/strategy/parameters/exit_threshold_bps",
        "type": "categorical",
        "values": [2.5, 5.0, 7.5, 10.0],
    },
)
_RANDOM_SPACE = (
    _GRID_SPACE[0],
    {
        "path": "/strategy/parameters/entry_threshold_bps",
        "type": "categorical",
        "values": [10.0, 12.5, 15.0, 20.0, 25.0],
    },
    {
        "path": "/strategy/parameters/exit_threshold_bps",
        "type": "categorical",
        "values": [2.5, 5.0, 7.5, 10.0, 12.5],
    },
)
_PROJECTIONS = {
    IMPLEMENTATION_VERSION: (
        "research_implementation_versions",
        "implementation_version_id",
    ),
    IMPLEMENTATION_VALIDATION_REPORT: (
        "research_implementation_validations",
        "validation_id",
    ),
    STRATEGY_SPECIFICATION: (
        "research_strategy_specifications",
        "strategy_specification_id",
    ),
    STRATEGY_SPECIFICATION_VALIDATION_REPORT: (
        "research_strategy_specification_validations",
        "validation_id",
    ),
    RISK_STACK_SPECIFICATION: (
        "research_risk_stack_specifications",
        "risk_stack_specification_id",
    ),
    RISK_STACK_SPECIFICATION_VALIDATION_REPORT: (
        "research_risk_stack_specification_validations",
        "validation_id",
    ),
    BACKTEST_SPECIFICATION: (
        "research_backtest_specifications",
        "backtest_specification_id",
    ),
    BACKTEST_SPECIFICATION_VALIDATION_REPORT: (
        "research_backtest_specification_validations",
        "validation_id",
    ),
    BACKTEST_RUN: ("research_backtest_runs", "run_id"),
    PARAMETER_OPTIMIZATION_PLAN: (
        "research_parameter_optimization_plans",
        "optimization_plan_id",
    ),
    PARAMETER_OPTIMIZATION_RUN: (
        "research_parameter_optimization_runs",
        "optimization_run_id",
    ),
    PARAMETER_OPTIMIZATION_TRIAL: (
        "research_parameter_optimization_trials",
        "trial_id",
    ),
}


@pytest.mark.postgres
def test_postgres_bounded_scale_and_projection_reconciliation(
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
    postgres_settings: dict[str, object],
) -> None:
    """Prove bounded optimization scale and exact Postgres projection reconciliation."""
    connection = postgres_research_artifact_store.connection()
    clear_57r_control_evidence(connection)
    initial_database_bytes = _database_size(connection)

    grid_prepared = prepare_optimization_qualification(
        event_store=postgres_event_store,
        artifact_store=postgres_research_artifact_store,
        postgres_settings=postgres_settings,
        search_space=_GRID_SPACE,
        tunable_fields=_TUNABLE_FIELDS,
        max_trials=64,
    )
    grid_seconds, grid_run = _run_profile(
        "builtin_grid",
        grid_prepared.optimization_plan_id,
        event_store=postgres_event_store,
        artifact_store=postgres_research_artifact_store,
        config=grid_prepared.config,
    )
    assert grid_run["trial_count"] == 64
    assert grid_seconds < _MAX_PROFILE_SECONDS

    random_prepared = prepare_optimization_qualification(
        event_store=postgres_event_store,
        artifact_store=postgres_research_artifact_store,
        postgres_settings=postgres_settings,
        search_space=_RANDOM_SPACE,
        tunable_fields=_TUNABLE_FIELDS,
        max_trials=100,
    )
    random_seconds, random_run = _run_profile(
        "builtin_random",
        random_prepared.optimization_plan_id,
        event_store=postgres_event_store,
        artifact_store=postgres_research_artifact_store,
        config=random_prepared.config,
    )
    assert random_run["trial_count"] == 100
    assert random_seconds < _MAX_PROFILE_SECONDS

    scale_region = build_bounded_scale_region(bar_count=1_000)
    for row in scale_region.rows():
        postgres_event_store.record_event("stock_bar_events", row)
    scale_manifest, scale_quality = data_evidence(postgres_event_store, scale_region)
    scale_specification = _data(
        create_backtest_specification(
            strategy_specification_validation_ref=(
                grid_prepared.strategy_validation_id
            ),
            risk_stack_specification_validation_ref=grid_prepared.risk_validation_id,
            dataset_manifest=scale_manifest,
            data_quality_report=scale_quality,
            assumptions=BACKTEST_ASSUMPTIONS,
            initial_cash=INITIAL_CASH,
            deterministic_seed=5701,
            runtime_limits={
                "fixture": "57R",
                "bounded": True,
                "bars_per_symbol": 1_000,
            },
            artifact_store=postgres_research_artifact_store,
        ),
        "backtest_specification",
    )
    scale_validation = _data(
        validate_backtest_specification(
            backtest_specification_id=scale_specification[
                "backtest_specification_id"
            ],
            artifact_store=postgres_research_artifact_store,
        ),
        "backtest_specification_validation_report",
    )
    started = time.perf_counter()
    scale_run = _data(
        run_backtest_specification(
            event_store=postgres_event_store,
            config=grid_prepared.config,
            backtest_specification_validation_ref=scale_validation["validation_id"],
            artifact_store=postgres_research_artifact_store,
        ),
        "backtest_run",
    )
    scale_seconds = time.perf_counter() - started
    assert scale_seconds < _MAX_PROFILE_SECONDS
    assert scale_run["status"] == "passed"
    assert scale_run["dataset_id"] == scale_manifest["dataset_id"]
    assert scale_manifest["total_rows"] == 1_000 * len(SYMBOLS)

    grid_query_seconds = _query_seconds(
        postgres_research_artifact_store,
        str(grid_run["optimization_run_id"]),
    )
    random_query_seconds = _query_seconds(
        postgres_research_artifact_store,
        str(random_run["optimization_run_id"]),
    )
    query_plan = _optimization_trial_query_plan(
        connection,
        str(random_run["optimization_run_id"]),
    )
    assert "research_optimization_trials_run_sequence_idx" in str(query_plan)
    _assert_projection_reconciliation(postgres_research_artifact_store)

    final_database_bytes = _database_size(connection)
    assert final_database_bytes >= initial_database_bytes
    artifact_count = len(postgres_research_artifact_store.list_artifacts())
    common = {
        "symbols": len(SYMBOLS),
        "bars_per_symbol": 48,
        "database_bytes": final_database_bytes,
        "artifact_count": artifact_count,
        "query_plan": query_plan,
    }
    save_57r_scale_result(
        connection,
        profile="builtin_grid_64",
        trial_count=64,
        wall_seconds=grid_seconds,
        result_query_seconds=grid_query_seconds,
        payload={"optimization_run_id": grid_run["optimization_run_id"]},
        **common,
    )
    save_57r_scale_result(
        connection,
        profile="builtin_random_100",
        trial_count=100,
        wall_seconds=random_seconds,
        result_query_seconds=random_query_seconds,
        payload={"optimization_run_id": random_run["optimization_run_id"]},
        **common,
    )
    save_57r_scale_result(
        connection,
        profile="portfolio_backtest_1000_bars",
        symbols=len(SYMBOLS),
        bars_per_symbol=1_000,
        trial_count=0,
        wall_seconds=scale_seconds,
        result_query_seconds=None,
        database_bytes=final_database_bytes,
        artifact_count=artifact_count,
        query_plan={},
        payload={"backtest_run_id": scale_run["run_id"]},
    )


def _run_profile(
    profile: str,
    plan_ref: str,
    *,
    event_store: PostgresEventStore,
    artifact_store: PostgresResearchArtifactStore,
    config: Any,
) -> tuple[float, Mapping[str, Any]]:
    started = time.perf_counter()
    result = run_parameter_optimization(
        optimization_plan_ref=plan_ref,
        optimizer_profile=profile,
        trial_executor=BacktestOptimizationTrialExecutor(
            event_store=event_store,
            config=config,
            artifact_store=artifact_store,
        ),
        artifact_store=artifact_store,
    )
    elapsed = time.perf_counter() - started
    assert result.ok is True, result.errors
    return elapsed, result.data["parameter_optimization_run"]


def _query_seconds(store: PostgresResearchArtifactStore, run_id: str) -> float:
    started = time.perf_counter()
    result = get_parameter_optimization_results(
        optimization_run_ref=run_id,
        artifact_store=store,
    )
    elapsed = time.perf_counter() - started
    assert result.ok is True, result.errors
    return elapsed


def _optimization_trial_query_plan(
    connection: Any,
    run_id: str,
) -> Mapping[str, Any]:
    connection.execute("SET enable_seqscan TO off")
    try:
        row = connection.execute(
            "EXPLAIN (FORMAT JSON) "
            "SELECT trial_id, sequence FROM research_parameter_optimization_trials "
            "WHERE optimization_run_id = %s ORDER BY sequence",
            [run_id],
        ).fetchone()
    finally:
        connection.execute("RESET enable_seqscan")
    return row["QUERY PLAN"][0]


def _assert_projection_reconciliation(
    store: PostgresResearchArtifactStore,
) -> None:
    for record in store.list_artifacts():
        table, id_column = _PROJECTIONS[record.artifact_type]
        projection = store.connection().execute(
            f"SELECT payload FROM {table} WHERE {id_column} = %s",
            [record.artifact_id],
        ).fetchone()
        assert projection == {"payload": record.payload}


def _database_size(connection: Any) -> int:
    row = connection.execute(
        "SELECT pg_database_size(current_database()) AS database_bytes"
    ).fetchone()
    return int(row["database_bytes"])


def _data(result: Any, key: str) -> Mapping[str, Any]:
    assert result.ok is True, result.errors
    value = result.data.get(key)
    assert isinstance(value, Mapping)
    return value
