"""Shared setup for cross-package optimization recovery and scale qualification.

The builder prepares one realistic canonical plan across core data and research
services so qualification modules exercise identical bounded inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from trader.config import Config
from trader.event_store import EventStore
from trader_research.experiments import (
    create_backtest_specification,
    create_parameter_optimization_plan,
    create_risk_stack_specification,
    create_strategy_specification,
    register_optimization_objective,
    register_risk_manager_implementation,
    register_strategy_implementation,
    validate_backtest_specification,
    validate_optimization_objective,
    validate_risk_manager_implementation,
    validate_risk_stack_specification,
    validate_strategy_implementation,
    validate_strategy_specification,
)
from trader_research.foundation import ApplicationResult
from trader_research.foundation.artifacts import ResearchArtifactStore
from tests.cross_package.qualification.support.realistic_optimization_fixture import (
    BACKTEST_ASSUMPTIONS,
    BASE_STRATEGY_PARAMETERS,
    INITIAL_CASH,
    OBJECTIVE_SOURCE,
    RISK_PARAMETERS,
    RISK_PARAMETER_SCHEMA,
    RISK_SOURCE,
    SEARCH_LOOKBACKS,
    SEED,
    STRATEGY_PARAMETER_SCHEMA,
    STRATEGY_SOURCE,
    build_backtest_config,
    build_realistic_optimization_fixture,
    data_evidence,
    seed_fixture,
)


@dataclass(frozen=True)
class PreparedOptimizationQualification:
    """Canonical plan and dependencies prepared from the realistic fixture."""

    optimization_plan_id: str
    base_backtest_validation_id: str
    strategy_validation_id: str
    risk_validation_id: str
    config: Config
    selection_manifest: Mapping[str, Any]
    selection_quality: Mapping[str, Any]
    holdout_manifest: Mapping[str, Any]
    holdout_quality: Mapping[str, Any]


def prepare_optimization_qualification(
    *,
    event_store: EventStore,
    artifact_store: ResearchArtifactStore,
    postgres_settings: Mapping[str, object],
    search_values: Sequence[int] = SEARCH_LOOKBACKS,
    seed: int = SEED,
    max_trial_attempts: int = 1,
    per_trial_timeout_seconds: float | None = None,
    search_space: Sequence[Mapping[str, Any]] | None = None,
    tunable_fields: Sequence[str] | None = None,
    max_trials: int | None = None,
) -> PreparedOptimizationQualification:
    """Persist one complete strategy/risk/backtest/optimization plan fixture."""
    values = tuple(int(value) for value in search_values)
    if not values:
        raise ValueError("search_values must not be empty")
    resolved_search_space = [
        dict(dimension)
        for dimension in (
            search_space
            or [
                {
                    "path": "/strategy/parameters/lookback_bars",
                    "type": "categorical",
                    "values": list(values),
                }
            ]
        )
    ]
    resolved_tunable_fields = list(
        tunable_fields
        or [str(dimension["path"]) for dimension in resolved_search_space]
    )
    resolved_max_trials = max_trials or _categorical_cardinality(
        resolved_search_space
    )
    fixture = build_realistic_optimization_fixture()
    seed_fixture(event_store, fixture)
    selection_manifest, selection_quality = data_evidence(event_store, fixture.selection)
    holdout_manifest, holdout_quality = data_evidence(event_store, fixture.holdout)

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
            artifact_store=artifact_store,
        ),
        "implementation_version",
    )
    strategy_validation = _data(
        validate_strategy_implementation(
            implementation_version_id=strategy["implementation_version_id"],
            fixture_parameters=BASE_STRATEGY_PARAMETERS,
            artifact_store=artifact_store,
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
            artifact_store=artifact_store,
        ),
        "implementation_version",
    )
    risk_validation = _data(
        validate_risk_manager_implementation(
            implementation_version_id=risk["implementation_version_id"],
            fixture_parameters=RISK_PARAMETERS,
            artifact_store=artifact_store,
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
            artifact_store=artifact_store,
        ),
        "implementation_version",
    )
    objective_validation = _data(
        validate_optimization_objective(
            implementation_version_id=objective["implementation_version_id"],
            artifact_store=artifact_store,
        ),
        "implementation_validation_report",
    )

    strategy_specification = _data(
        create_strategy_specification(
            implementation_validation_ref=strategy_validation["validation_id"],
            parameters=BASE_STRATEGY_PARAMETERS,
            portfolio_mode="multi_asset",
            required_runtime_context={
                "event_store_bars": True,
                "portfolio_positions": True,
            },
            execution_assumptions={
                "broker_mutation_allowed": False,
                "live_trading_allowed": False,
                "raw_sql_allowed": False,
            },
            tunable_fields=resolved_tunable_fields,
            artifact_store=artifact_store,
        ),
        "strategy_specification",
    )
    strategy_specification_validation = _data(
        validate_strategy_specification(
            strategy_specification_id=strategy_specification[
                "strategy_specification_id"
            ],
            artifact_store=artifact_store,
        ),
        "strategy_specification_validation_report",
    )
    risk_specification = _data(
        create_risk_stack_specification(
            risk_managers=[
                {
                    "implementation_validation_ref": risk_validation["validation_id"],
                    "parameters": RISK_PARAMETERS,
                }
            ],
            execution_assumptions={
                "broker_mutation_allowed": False,
                "live_trading_allowed": False,
                "raw_sql_allowed": False,
            },
            artifact_store=artifact_store,
        ),
        "risk_stack_specification",
    )
    risk_specification_validation = _data(
        validate_risk_stack_specification(
            risk_stack_specification_id=risk_specification[
                "risk_stack_specification_id"
            ],
            artifact_store=artifact_store,
        ),
        "risk_stack_specification_validation_report",
    )
    backtest_specification = _data(
        create_backtest_specification(
            strategy_specification_validation_ref=(
                strategy_specification_validation["validation_id"]
            ),
            risk_stack_specification_validation_ref=(
                risk_specification_validation["validation_id"]
            ),
            dataset_manifest=selection_manifest,
            data_quality_report=selection_quality,
            assumptions=BACKTEST_ASSUMPTIONS,
            initial_cash=INITIAL_CASH,
            deterministic_seed=seed,
            max_runs=None,
            log_cycle_details=False,
            runtime_limits={"fixture": "57O-R", "bounded": True},
            artifact_store=artifact_store,
        ),
        "backtest_specification",
    )
    backtest_validation = _data(
        validate_backtest_specification(
            backtest_specification_id=backtest_specification[
                "backtest_specification_id"
            ],
            artifact_store=artifact_store,
        ),
        "backtest_specification_validation_report",
    )
    resource_limits: dict[str, Any] = {
        "max_trial_attempts": max_trial_attempts,
        "max_concurrent_trials": 1,
    }
    if per_trial_timeout_seconds is not None:
        resource_limits["per_trial_timeout_seconds"] = per_trial_timeout_seconds
    plan = _data(
        create_parameter_optimization_plan(
            base_backtest_specification_validation_ref=backtest_validation[
                "validation_id"
            ],
            holdout_dataset_manifest=holdout_manifest,
            holdout_data_quality_report=holdout_quality,
            objective_validation_ref=objective_validation["validation_id"],
            search_space=resolved_search_space,
            direction="maximize",
            seed=seed,
            max_trials=resolved_max_trials,
            resource_limits=resource_limits,
            artifact_store=artifact_store,
        ),
        "parameter_optimization_plan",
    )
    return PreparedOptimizationQualification(
        optimization_plan_id=str(plan["optimization_plan_id"]),
        base_backtest_validation_id=str(backtest_validation["validation_id"]),
        strategy_validation_id=str(strategy_specification_validation["validation_id"]),
        risk_validation_id=str(risk_specification_validation["validation_id"]),
        config=build_backtest_config(postgres_settings),
        selection_manifest=selection_manifest,
        selection_quality=selection_quality,
        holdout_manifest=holdout_manifest,
        holdout_quality=holdout_quality,
    )


def _categorical_cardinality(search_space: Sequence[Mapping[str, Any]]) -> int:
    cardinality = 1
    for dimension in search_space:
        values = dimension.get("values")
        if dimension.get("type") != "categorical" or not isinstance(values, Sequence):
            raise ValueError("max_trials is required for non-categorical qualification spaces")
        cardinality *= len(values)
    return cardinality


def _data(result: ApplicationResult, key: str) -> Mapping[str, Any]:
    if not result.ok:
        raise AssertionError(result.errors)
    value = result.data.get(key)
    if not isinstance(value, Mapping):
        raise AssertionError(f"missing mapping result {key!r}: {result.data}")
    return value
