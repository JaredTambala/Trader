"""Postgres-only qualification of the realistic task 57L evidence fixture."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

import pytest

from tests.support.realistic_optimization_fixture import (
    BACKTEST_ASSUMPTIONS,
    BASE_STRATEGY_PARAMETERS,
    HOLDOUT_CONTENT_SHA256,
    HOLDOUT_DATASET_ID,
    HOLDOUT_MANIFEST_SHA256,
    HOLDOUT_QUALITY_SHA256,
    INITIAL_CASH,
    OBJECTIVE_SOURCE_SHA256,
    OBJECTIVE_SOURCE,
    RISK_PARAMETERS,
    RISK_PARAMETER_SCHEMA,
    RISK_SOURCE_SHA256,
    RISK_SOURCE,
    SEARCH_LOOKBACKS,
    SEED,
    SELECTION_CONTENT_SHA256,
    SELECTION_DATASET_ID,
    SELECTION_MANIFEST_SHA256,
    SELECTION_QUALITY_SHA256,
    STRATEGY_PARAMETER_SCHEMA,
    STRATEGY_SOURCE_SHA256,
    STRATEGY_SOURCE,
    SYMBOLS,
    build_backtest_config,
    build_realistic_optimization_fixture,
    data_evidence,
    postgres_region_content_sha256,
    seed_fixture,
)
from trader.event_store import PostgresEventStore
from trader_research.artifact_store import json_payload_hash, source_hash
from trader_research.backtests import run_backtest_specification
from trader_research.domain import BACKTEST_RUN, PARAMETER_OPTIMIZATION_TRIAL
from trader_research.implementations import (
    register_optimization_objective,
    register_risk_manager_implementation,
    register_strategy_implementation,
    validate_optimization_objective,
    validate_risk_manager_implementation,
    validate_strategy_implementation,
)
from trader_research.optimization import (
    BacktestOptimizationTrialExecutor,
    create_parameter_optimization_plan,
    run_parameter_optimization,
)
from trader_research.postgres_artifact_store import PostgresResearchArtifactStore
from trader_research.specifications import (
    create_backtest_specification,
    create_risk_stack_specification,
    create_strategy_specification,
    validate_backtest_specification,
    validate_risk_stack_specification,
    validate_strategy_specification,
)


def test_realistic_optimization_fixture_is_bounded_and_deterministic() -> None:
    first = build_realistic_optimization_fixture()
    second = build_realistic_optimization_fixture()

    assert first == second
    assert first.selection.rows() == second.selection.rows()
    assert first.holdout.rows() == second.holdout.rows()
    assert len(first.selection.rows()) == 48 * len(SYMBOLS)
    assert len(first.holdout.rows()) == 32 * len(SYMBOLS)
    assert first.selection.content_sha256 == SELECTION_CONTENT_SHA256
    assert first.holdout.content_sha256 == HOLDOUT_CONTENT_SHA256
    assert first.selection.content_sha256 != first.holdout.content_sha256
    assert first.selection.end < first.holdout.start
    assert first.holdout.start - first.selection.end > _hours(max(SEARCH_LOOKBACKS))
    assert source_hash(STRATEGY_SOURCE) == STRATEGY_SOURCE_SHA256
    assert source_hash(RISK_SOURCE) == RISK_SOURCE_SHA256
    assert source_hash(OBJECTIVE_SOURCE) == OBJECTIVE_SOURCE_SHA256


@pytest.mark.postgres
def test_postgres_realistic_strategy_risk_backtest_and_optimization_evidence(
    postgres_event_store: PostgresEventStore,
    postgres_research_artifact_store: PostgresResearchArtifactStore,
    postgres_settings: dict[str, object],
) -> None:
    fixture = build_realistic_optimization_fixture()
    seed_fixture(postgres_event_store, fixture)

    selection_manifest, selection_quality = data_evidence(postgres_event_store, fixture.selection)
    holdout_manifest, holdout_quality = data_evidence(postgres_event_store, fixture.holdout)
    _assert_data_agent_snapshot(
        selection_manifest,
        selection_quality,
        dataset_id=SELECTION_DATASET_ID,
        manifest_sha256=SELECTION_MANIFEST_SHA256,
        quality_sha256=SELECTION_QUALITY_SHA256,
        total_rows=48 * len(SYMBOLS),
    )
    _assert_data_agent_snapshot(
        holdout_manifest,
        holdout_quality,
        dataset_id=HOLDOUT_DATASET_ID,
        manifest_sha256=HOLDOUT_MANIFEST_SHA256,
        quality_sha256=HOLDOUT_QUALITY_SHA256,
        total_rows=32 * len(SYMBOLS),
    )
    assert selection_manifest["dataset_id"] != holdout_manifest["dataset_id"]
    assert postgres_region_content_sha256(postgres_event_store, fixture.selection) == (
        SELECTION_CONTENT_SHA256
    )
    assert postgres_region_content_sha256(postgres_event_store, fixture.holdout) == (
        HOLDOUT_CONTENT_SHA256
    )

    store = postgres_research_artifact_store
    admitted = _admit_implementations(store)
    configured = _create_configured_behavior(store, admitted)
    selection_backtest = _create_validated_backtest(
        store,
        strategy_validation_id=configured["strategy_validation_id"],
        risk_validation_id=configured["risk_validation_id"],
        manifest=selection_manifest,
        quality=selection_quality,
    )
    config = build_backtest_config(postgres_settings)
    base_run = _data(
        run_backtest_specification(
            event_store=postgres_event_store,
            config=config,
            backtest_specification_validation_ref=selection_backtest["validation_id"],
            artifact_store=store,
        ),
        "backtest_run",
    )
    _assert_meaningful_backtest(base_run)

    plan = _data(
        create_parameter_optimization_plan(
            base_backtest_specification_validation_ref=selection_backtest["validation_id"],
            holdout_dataset_manifest=holdout_manifest,
            holdout_data_quality_report=holdout_quality,
            objective_validation_ref=admitted["objective_validation_id"],
            search_space=[
                {
                    "path": "/strategy/parameters/lookback_bars",
                    "type": "integer",
                    "low": min(SEARCH_LOOKBACKS),
                    "high": max(SEARCH_LOOKBACKS),
                }
            ],
            direction="maximize",
            seed=SEED,
            max_trials=len(SEARCH_LOOKBACKS),
            resource_limits={"max_trial_attempts": 1, "max_concurrent_trials": 1},
            artifact_store=store,
        ),
        "parameter_optimization_plan",
    )
    optimization = _data(
        run_parameter_optimization(
            optimization_plan_ref=plan["optimization_plan_id"],
            optimizer_profile="builtin_grid",
            trial_executor=BacktestOptimizationTrialExecutor(
                event_store=postgres_event_store,
                config=config,
                artifact_store=store,
            ),
            artifact_store=store,
        ),
        "parameter_optimization_run",
    )
    trials = [
        dict(record.payload)
        for record in store.list_artifacts(artifact_type=PARAMETER_OPTIMIZATION_TRIAL)
        if record.payload.get("optimization_run_id") == optimization["optimization_run_id"]
    ]
    trials.sort(key=lambda item: int(item["sequence"]))
    _assert_parameter_sensitive_optimization(optimization, trials)

    selection_hash = selection_backtest["dataset_hash"]
    selection_runs = store.list_artifacts(artifact_type=BACKTEST_RUN)
    assert len(selection_runs) == 1 + len(SEARCH_LOOKBACKS)
    assert {record.payload["dataset_hash"] for record in selection_runs} == {selection_hash}

    selected_refs = optimization["selected_child_refs"]
    holdout_backtest = _create_validated_backtest(
        store,
        strategy_validation_id=str(selected_refs["strategy_specification_validation_id"]),
        risk_validation_id=str(selected_refs["risk_stack_specification_validation_id"]),
        manifest=holdout_manifest,
        quality=holdout_quality,
        selection_origin_ref=optimization["optimization_run_id"],
    )
    holdout_run = _data(
        run_backtest_specification(
            event_store=postgres_event_store,
            config=config,
            backtest_specification_validation_ref=holdout_backtest["validation_id"],
            artifact_store=store,
        ),
        "backtest_run",
    )
    _assert_meaningful_backtest(holdout_run)
    assert holdout_run["dataset_hash"] != selection_hash
    assert holdout_run["selection_origin_ref"] == optimization["optimization_run_id"]
    reloaded_optimization = store.load_artifact(
        "parameter_optimization_run", optimization["optimization_run_id"]
    )
    assert reloaded_optimization["selected_trial_id"] == optimization["selected_trial_id"]
    assert reloaded_optimization["selected_child_refs"] == selected_refs

    assert postgres_region_content_sha256(postgres_event_store, fixture.selection) == (
        SELECTION_CONTENT_SHA256
    )
    assert postgres_region_content_sha256(postgres_event_store, fixture.holdout) == (
        HOLDOUT_CONTENT_SHA256
    )
    _assert_postgres_projections(store, optimization, trials, holdout_run)


def _admit_implementations(store: PostgresResearchArtifactStore) -> dict[str, str]:
    strategy = _data(
        register_strategy_implementation(
            name="verification-trailing-return-transition",
            version="1",
            source_code=STRATEGY_SOURCE,
            factory_name="build_strategy",
            class_name="TrailingReturnTransitionStrategy",
            parameter_schema=STRATEGY_PARAMETER_SCHEMA,
            authoring_origin="handwritten_test_fixture",
            capabilities=["multi_asset", "long_flat", "event_store_bars"],
            artifact_store=store,
        ),
        "implementation_version",
    )
    assert strategy["source_hash"] == source_hash(STRATEGY_SOURCE)
    strategy_validation = _data(
        validate_strategy_implementation(
            implementation_version_id=strategy["implementation_version_id"],
            fixture_parameters=BASE_STRATEGY_PARAMETERS,
            artifact_store=store,
        ),
        "implementation_validation_report",
    )

    risk = _data(
        register_risk_manager_implementation(
            name="verification-entry-quantity-limit",
            version="1",
            source_code=RISK_SOURCE,
            factory_name="build_risk_manager",
            class_name="EntryQuantityLimitRiskManager",
            parameter_schema=RISK_PARAMETER_SCHEMA,
            authoring_origin="handwritten_test_fixture",
            capabilities=["entry_quantity_limit", "risk_reducing_exit"],
            artifact_store=store,
        ),
        "implementation_version",
    )
    assert risk["source_hash"] == source_hash(RISK_SOURCE)
    risk_validation = _data(
        validate_risk_manager_implementation(
            implementation_version_id=risk["implementation_version_id"],
            fixture_parameters=RISK_PARAMETERS,
            artifact_store=store,
        ),
        "implementation_validation_report",
    )

    objective = _data(
        register_optimization_objective(
            name="verification-risk-adjusted-return",
            version="1",
            source_code=OBJECTIVE_SOURCE,
            factory_name="objective",
            authoring_origin="handwritten_test_fixture",
            artifact_store=store,
        ),
        "implementation_version",
    )
    assert objective["source_hash"] == source_hash(OBJECTIVE_SOURCE)
    objective_validation = _data(
        validate_optimization_objective(
            implementation_version_id=objective["implementation_version_id"],
            artifact_store=store,
        ),
        "implementation_validation_report",
    )

    return {
        "strategy_validation_id": strategy_validation["validation_id"],
        "risk_validation_id": risk_validation["validation_id"],
        "objective_validation_id": objective_validation["validation_id"],
    }


def _create_configured_behavior(
    store: PostgresResearchArtifactStore,
    admitted: Mapping[str, str],
) -> dict[str, str]:
    strategy = _data(
        create_strategy_specification(
            implementation_validation_ref=admitted["strategy_validation_id"],
            parameters=BASE_STRATEGY_PARAMETERS,
            portfolio_mode="multi_asset",
            required_runtime_context={"event_store_bars": True, "portfolio_positions": True},
            execution_assumptions={
                "broker_mutation_allowed": False,
                "live_trading_allowed": False,
                "raw_sql_allowed": False,
            },
            tunable_fields=["/strategy/parameters/lookback_bars"],
            artifact_store=store,
        ),
        "strategy_specification",
    )
    assert not set(strategy["parameters"]).intersection(
        {"symbols", "asset_class", "timeframe", "start", "end", "source_filter"}
    )
    strategy_validation = _data(
        validate_strategy_specification(
            strategy_specification_id=strategy["strategy_specification_id"],
            artifact_store=store,
        ),
        "strategy_specification_validation_report",
    )

    risk = _data(
        create_risk_stack_specification(
            risk_managers=[
                {
                    "implementation_validation_ref": admitted["risk_validation_id"],
                    "parameters": RISK_PARAMETERS,
                }
            ],
            execution_assumptions={
                "broker_mutation_allowed": False,
                "live_trading_allowed": False,
                "raw_sql_allowed": False,
            },
            artifact_store=store,
        ),
        "risk_stack_specification",
    )
    risk_validation = _data(
        validate_risk_stack_specification(
            risk_stack_specification_id=risk["risk_stack_specification_id"],
            artifact_store=store,
        ),
        "risk_stack_specification_validation_report",
    )
    return {
        "strategy_validation_id": strategy_validation["validation_id"],
        "risk_validation_id": risk_validation["validation_id"],
    }


def _create_validated_backtest(
    store: PostgresResearchArtifactStore,
    *,
    strategy_validation_id: str,
    risk_validation_id: str,
    manifest: Mapping[str, Any],
    quality: Mapping[str, Any],
    selection_origin_ref: str | None = None,
) -> Mapping[str, Any]:
    specification = _data(
        create_backtest_specification(
            strategy_specification_validation_ref=strategy_validation_id,
            risk_stack_specification_validation_ref=risk_validation_id,
            dataset_manifest=manifest,
            data_quality_report=quality,
            assumptions=BACKTEST_ASSUMPTIONS,
            initial_cash=INITIAL_CASH,
            deterministic_seed=SEED,
            max_runs=None,
            log_cycle_details=False,
            runtime_limits={"fixture": "57L", "bounded": True},
            selection_origin_ref=selection_origin_ref,
            artifact_store=store,
        ),
        "backtest_specification",
    )
    return _data(
        validate_backtest_specification(
            backtest_specification_id=specification["backtest_specification_id"],
            artifact_store=store,
        ),
        "backtest_specification_validation_report",
    )


def _assert_meaningful_backtest(run: Mapping[str, Any]) -> None:
    assert run["status"] == "passed"
    assert run["backtest_kind"] == "portfolio"
    summary = run["summary"]
    bundle = run["bundle"]
    trades = bundle["trades"]
    assert summary["trade_count"] >= 6
    assert {trade["side"] for trade in trades} == {"buy", "sell"}
    assert len({trade["symbol"] for trade in trades}) >= 2
    assert summary["fees"] > 0.0
    assert summary["slippage"] > 0.0
    exposure = bundle["exposure_summary"]
    assert exposure["avg_gross_exposure"] > 0.0
    assert exposure["final_gross_notional"] > 0.0
    risk = bundle["risk_decisions"]
    decisions = risk["decisions"]
    assert sum(int(item["approved_count"]) for item in decisions) > 0
    assert risk["rejected_order_count"] > 0
    breaches = bundle["risk_limit_breaches"]
    assert breaches["breach_count"] == risk["rejected_order_count"]
    assert any(
        item["symbol"] == "GAMMA" and item["rejection_reason"] == "entry_quantity_limit"
        for item in breaches["breaches"]
    )


def _assert_data_agent_snapshot(
    manifest: Mapping[str, Any],
    quality: Mapping[str, Any],
    *,
    dataset_id: str,
    manifest_sha256: str,
    quality_sha256: str,
    total_rows: int,
) -> None:
    assert manifest["dataset_id"] == dataset_id
    assert manifest["complete"] is True
    assert manifest["symbols"] == list(SYMBOLS)
    assert manifest["total_rows"] == total_rows
    assert manifest["source_filter"] is None
    assert json_payload_hash(manifest) == manifest_sha256
    assert quality["report_id"] == f"data_quality_{dataset_id.removeprefix('dataset_')}"
    assert quality["complete"] is True
    assert quality["total_bars"] == total_rows
    assert quality["missing_gap_count"] == 0
    assert quality["missing_bar_count"] == 0
    assert quality["source_filter"] is None
    assert json_payload_hash(quality) == quality_sha256


def _assert_parameter_sensitive_optimization(
    optimization: Mapping[str, Any],
    trials: list[Mapping[str, Any]],
) -> None:
    assert optimization["status"] == "completed"
    assert optimization["trial_count"] == len(SEARCH_LOOKBACKS)
    assert optimization["passed_trial_count"] == len(SEARCH_LOOKBACKS)
    assert optimization["failed_trial_count"] == 0
    assert [trial["sequence"] for trial in trials] == list(range(len(SEARCH_LOOKBACKS)))
    assert [
        trial["parameters"]["/strategy/parameters/lookback_bars"] for trial in trials
    ] == list(SEARCH_LOOKBACKS)
    assert all(trial["status"] == "passed" for trial in trials)
    assert all(trial["child_refs"].get("strategy_specification_id") for trial in trials)
    assert all(trial["child_refs"].get("risk_stack_specification_id") for trial in trials)
    assert all(trial["child_refs"].get("backtest_specification_id") for trial in trials)
    assert all(trial["child_refs"].get("backtest_run_id") for trial in trials)
    objective_values = [float(trial["objective_value"]) for trial in trials]
    total_returns = [float(trial["observation"]["metrics"]["total_return"]) for trial in trials]
    trade_counts = [int(trial["observation"]["counts"]["trade_count"]) for trial in trials]
    assert max(objective_values) - min(objective_values) > 1e-6
    assert len({round(value, 12) for value in total_returns}) > 1
    assert len(set(trade_counts)) > 1
    best_value = max(objective_values)
    assert sum(abs(value - best_value) <= 1e-12 for value in objective_values) == 1
    selected = trials[objective_values.index(best_value)]
    assert optimization["selected_trial_id"] == selected["trial_id"]
    assert optimization["selected_parameters"] == selected["parameters"]
    assert optimization["selected_child_refs"] == selected["child_refs"]


def _assert_postgres_projections(
    store: PostgresResearchArtifactStore,
    optimization: Mapping[str, Any],
    trials: list[Mapping[str, Any]],
    holdout_run: Mapping[str, Any],
) -> None:
    connection = store.connection()
    implementation_counts = connection.execute(
        "SELECT implementation_kind, COUNT(*) AS count "
        "FROM research_implementation_versions GROUP BY implementation_kind"
    ).fetchall()
    assert {row["implementation_kind"]: row["count"] for row in implementation_counts} == {
        "optimization_objective": 1,
        "risk_manager": 1,
        "strategy": 1,
    }
    run_projection = connection.execute(
        "SELECT optimization_plan_id, status, selected_trial_id, "
        "selected_backtest_specification_id FROM research_parameter_optimization_runs "
        "WHERE optimization_run_id = %s",
        [optimization["optimization_run_id"]],
    ).fetchone()
    assert run_projection["optimization_plan_id"] == optimization["optimization_plan_id"]
    assert run_projection["status"] == "completed"
    assert run_projection["selected_trial_id"] == optimization["selected_trial_id"]
    assert run_projection["selected_backtest_specification_id"] == (
        optimization["selected_child_refs"]["backtest_specification_id"]
    )
    trial_rows = connection.execute(
        "SELECT trial_id, sequence, status, objective_value, child_backtest_run_id "
        "FROM research_parameter_optimization_trials WHERE optimization_run_id = %s "
        "ORDER BY sequence",
        [optimization["optimization_run_id"]],
    ).fetchall()
    assert [row["trial_id"] for row in trial_rows] == [trial["trial_id"] for trial in trials]
    assert all(row["status"] == "passed" and row["child_backtest_run_id"] for row in trial_rows)
    holdout_projection = connection.execute(
        "SELECT run_id, dataset_id, status, selection_origin_ref "
        "FROM research_backtest_runs WHERE run_id = %s",
        [holdout_run["run_id"]],
    ).fetchone()
    assert holdout_projection == {
        "run_id": holdout_run["run_id"],
        "dataset_id": holdout_run["dataset_id"],
        "status": "passed",
        "selection_origin_ref": optimization["optimization_run_id"],
    }
    canonical = connection.execute(
        "SELECT payload FROM research_artifacts WHERE artifact_type = %s AND artifact_id = %s",
        ["backtest_run", holdout_run["run_id"]],
    ).fetchone()
    assert canonical["payload"]["run_id"] == holdout_run["run_id"]
    assert canonical["payload"]["summary"] == holdout_run["summary"]


def _data(envelope: Any, key: str) -> Mapping[str, Any]:
    assert envelope.ok is True, envelope.errors
    value = envelope.data.get(key)
    assert isinstance(value, Mapping), envelope.data
    reference = envelope.artifacts.get(key)
    if reference is not None:
        assert str(reference["uri"]).startswith(f"research://postgres/{reference['artifact_type']}/")
    return value


def _hours(value: int) -> timedelta:
    return timedelta(hours=value)
