"""Reusable deterministic fixtures for parameter-optimisation contract tests.

These package-owned builders create canonical experiment plans, supplied
implementations, trial executors, and tracking sinks without external services.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from trader_research.experiments import (
    TrialExecution,
    create_backtest_specification,
    create_parameter_optimization_plan,
    create_strategy_specification,
    register_optimization_objective,
    register_strategy_implementation,
    validate_backtest_specification,
    validate_optimization_objective,
    validate_strategy_implementation,
    validate_strategy_specification,
)
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore

STRATEGY_SOURCE = """
from trader.strategies import Strategy

class EmptyStrategy(Strategy):
    def __init__(self, period=2):
        self.period = period

    @property
    def strategy_id(self):
        return "empty"

    def generate_orders(self, **kwargs):
        return ()

def build_strategy(period=2, **kwargs):
    return EmptyStrategy(period=period)
"""

OBJECTIVE_SOURCE = """
def objective(observation):
    return {"value": observation["metrics"]["sharpe"], "diagnostics": {"metric": "sharpe"}}
"""


@dataclass
class FakeExecutor:
    """Deterministic trial executor independent of market-data runtime."""

    executor_kind: str = "test_fixture"

    def execute(
        self,
        *,
        plan: Mapping[str, Any],
        parameters: Mapping[str, Any],
        trial_id: str,
        optimization_run_id: str,
    ) -> TrialExecution:
        del plan, optimization_run_id
        period = int(parameters["/strategy/parameters/period"])
        return TrialExecution(
            status="passed",
            observation={
                "schema_version": "1.0",
                "status": "passed",
                "metrics": {
                    "sharpe": float(period),
                    "total_return": period / 100,
                    "max_drawdown": 0.1,
                },
                "counts": {"trade_count": period, "total_runs": 1, "failed_runs": 0},
                "costs": {"fees": 1.0, "slippage": 0.5},
                "exposure": {"final_concentration": 0.2},
                "risk": {"decisions": {}, "breaches": {}, "measures": {}},
                "quality": {"complete": True, "blockers": []},
                "constraints": {},
                "lineage": {"trial_id": trial_id, "fold": "selection"},
            },
            child_refs={
                "strategy_specification_id": f"strategy-{period}",
                "backtest_specification_id": f"backtest-{period}",
                "backtest_run_id": f"run-{period}",
            },
        )


class RecordingSink:
    """In-memory tracking sink used to prove derived idempotent projection."""

    def __init__(self) -> None:
        self.snapshots: list[Mapping[str, Any]] = []

    def profile(self) -> Mapping[str, Any]:
        return {"profile_name": "recording", "provider": "test", "version": "1"}

    def project(self, canonical_run: Mapping[str, Any]) -> Mapping[str, Any]:
        self.snapshots.append(canonical_run)
        return {"external_run_id": "projection-1"}


class FailingSink:
    """Configured sink that proves provider failure cannot damage canonical evidence."""

    def profile(self) -> Mapping[str, Any]:
        return {"profile_name": "failing", "provider": "test", "version": "1"}

    def project(self, canonical_run: Mapping[str, Any]) -> Mapping[str, Any]:
        del canonical_run
        raise RuntimeError("tracking provider unavailable")


class RetryExecutor(FakeExecutor):
    """Fail the first attempt for each trial and pass the retry."""

    executor_kind = "retry_fixture"

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def execute(
        self,
        *,
        plan: Mapping[str, Any],
        parameters: Mapping[str, Any],
        trial_id: str,
        optimization_run_id: str,
    ) -> TrialExecution:
        self.calls[trial_id] = self.calls.get(trial_id, 0) + 1
        if self.calls[trial_id] == 1:
            raise RuntimeError("transient fixture failure")
        return super().execute(
            plan=plan,
            parameters=parameters,
            trial_id=trial_id,
            optimization_run_id=optimization_run_id,
        )


class TieExecutor(FakeExecutor):
    """Return equal objective evidence so canonical tie-breaking is exercised."""

    executor_kind = "tie_fixture"

    def execute(
        self,
        *,
        plan: Mapping[str, Any],
        parameters: Mapping[str, Any],
        trial_id: str,
        optimization_run_id: str,
    ) -> TrialExecution:
        result = super().execute(
            plan=plan,
            parameters=parameters,
            trial_id=trial_id,
            optimization_run_id=optimization_run_id,
        )
        observation = deepcopy(dict(result.observation or {}))
        observation["metrics"]["sharpe"] = 1.0
        return TrialExecution(
            status=result.status,
            observation=observation,
            child_refs=result.child_refs,
            warnings=result.warnings,
            blockers=result.blockers,
        )


class HugeFailureExecutor(FakeExecutor):
    """Raise an oversized error to prove canonical failure evidence is bounded."""

    executor_kind = "huge_failure_fixture"

    def execute(
        self,
        *,
        plan: Mapping[str, Any],
        parameters: Mapping[str, Any],
        trial_id: str,
        optimization_run_id: str,
    ) -> TrialExecution:
        del plan, parameters, trial_id, optimization_run_id
        raise RuntimeError("x" * 10_000)


def _plan(
    store: InMemoryResearchArtifactStore,
    *,
    resource_limits: Mapping[str, Any] | None = None,
    max_trials: int = 2,
) -> Mapping[str, Any]:
    base_validation_id, objective_validation_id = _base_validations(store)
    created = create_parameter_optimization_plan(
        base_backtest_specification_validation_ref=base_validation_id,
        holdout_dataset_manifest=_manifest(
            "holdout", "2025-02-01T00:00:00+00:00", "2025-02-28T00:00:00+00:00"
        ),
        holdout_data_quality_report=_quality(
            "2025-02-01T00:00:00+00:00", "2025-02-28T00:00:00+00:00"
        ),
        objective_validation_ref=objective_validation_id,
        search_space=[
            {
                "path": "/strategy/parameters/period",
                "type": "integer",
                "low": 2,
                "high": 3,
            }
        ],
        max_trials=max_trials,
        resource_limits=resource_limits,
        artifact_store=store,
    )
    assert created.ok is True
    return created.data["parameter_optimization_plan"]


def _base_validations(store: InMemoryResearchArtifactStore) -> tuple[str, str]:
    strategy = register_strategy_implementation(
        name="empty",
        version="1",
        source_code=STRATEGY_SOURCE,
        factory_name="build_strategy",
        parameter_schema={
            "type": "object",
            "properties": {"period": {"type": "integer", "minimum": 1}},
            "required": ["period"],
        },
        artifact_store=store,
    )
    strategy_id = strategy.data["implementation_version"]["implementation_version_id"]
    strategy_validation = validate_strategy_implementation(
        implementation_version_id=strategy_id,
        fixture_parameters={"period": 2},
        artifact_store=store,
    )
    assert strategy_validation.ok is True
    strategy_spec = create_strategy_specification(
        implementation_validation_ref=strategy_validation.data[
            "implementation_validation_report"
        ]["validation_id"],
        parameters={"period": 2},
        tunable_fields=["/strategy/parameters/period"],
        artifact_store=store,
    )
    strategy_spec_validation = validate_strategy_specification(
        strategy_specification_id=strategy_spec.data["strategy_specification"][
            "strategy_specification_id"
        ],
        artifact_store=store,
    )
    backtest = create_backtest_specification(
        strategy_specification_validation_ref=strategy_spec_validation.data[
            "strategy_specification_validation_report"
        ]["validation_id"],
        dataset_manifest=_manifest(
            "selection", "2025-01-01T00:00:00+00:00", "2025-01-31T00:00:00+00:00"
        ),
        data_quality_report=_quality(
            "2025-01-01T00:00:00+00:00", "2025-01-31T00:00:00+00:00"
        ),
        artifact_store=store,
    )
    backtest_validation = validate_backtest_specification(
        backtest_specification_id=backtest.data["backtest_specification"][
            "backtest_specification_id"
        ],
        artifact_store=store,
    )

    objective = register_optimization_objective(
        name="sharpe",
        version="1",
        source_code=OBJECTIVE_SOURCE,
        factory_name="objective",
        artifact_store=store,
    )
    objective_validation = validate_optimization_objective(
        implementation_version_id=objective.data["implementation_version"][
            "implementation_version_id"
        ],
        artifact_store=store,
    )
    assert objective_validation.ok is True
    return (
        backtest_validation.data["backtest_specification_validation_report"][
            "validation_id"
        ],
        objective_validation.data["implementation_validation_report"]["validation_id"],
    )


def _manifest(dataset_id: str, start: str, end: str) -> dict[str, Any]:
    return {
        "artifact_type": "dataset_manifest",
        "dataset_id": dataset_id,
        "symbols": ["EURUSD"],
        "asset_class": "forex",
        "timeframe": "1Hour",
        "time_range": {"start": start, "end": end},
        "total_rows": 100,
        "complete": True,
    }


def _quality(start: str, end: str) -> dict[str, Any]:
    return {
        "artifact_type": "data_quality_report",
        "symbols": ["EURUSD"],
        "asset_class": "forex",
        "timeframe": "1Hour",
        "time_range": {"start": start, "end": end},
        "complete": True,
        "blockers": [],
    }
