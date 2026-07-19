"""Provider-neutral optimization, projection, Evaluation, and audit evidence tests."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from typing import Any, Mapping

import pytest

from trader_research.adversarial import (
    create_parameter_optimization_audit_plan,
    generate_parameter_optimization_audit,
)
from trader_research.artifact_store import InMemoryResearchArtifactStore
from trader_research.domain import (
    BACKTEST_RUN,
    BACKTEST_SPECIFICATION,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
)
from trader_research.evaluation import generate_parameter_optimization_report
from trader_research.implementations import (
    register_optimization_objective,
    register_strategy_implementation,
    validate_optimization_objective,
    validate_strategy_implementation,
)
from trader_research.optimization import (
    OptimizationObservation,
    OptunaOptimizationEngine,
    RandomOptimizationEngine,
    TrialExecution,
    create_parameter_optimization_plan,
    get_parameter_optimization_results,
    run_parameter_optimization,
)
from trader_research.specifications import (
    create_backtest_specification,
    create_strategy_specification,
    validate_backtest_specification,
    validate_strategy_specification,
)
from trader_research.tracking import ExperimentTrackingSinkRegistry, project_experiment_tracking


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
                "metrics": {"sharpe": float(period), "total_return": period / 100, "max_drawdown": 0.1},
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


def test_grid_resume_selection_projection_evaluation_and_audit_are_separate() -> None:
    store = InMemoryResearchArtifactStore()
    plan = _plan(store)

    partial = run_parameter_optimization(
        optimization_plan_ref=plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=FakeExecutor(),
        artifact_store=store,
        max_new_trials=1,
    )
    assert partial.ok is True
    assert partial.data["parameter_optimization_run"]["status"] == "partial"

    completed = run_parameter_optimization(
        optimization_plan_ref=plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=FakeExecutor(),
        artifact_store=store,
    )
    assert completed.ok is True
    run = completed.data["parameter_optimization_run"]
    assert run["status"] == "completed"
    assert run["selected_parameters"] == {"/strategy/parameters/period": 3}
    assert run["trial_count"] == 2

    results = get_parameter_optimization_results(
        optimization_run_ref=run["optimization_run_id"], artifact_store=store
    )
    assert results.ok is True
    assert [trial["sequence"] for trial in results.data["trials"]] == [0, 1]

    sink = RecordingSink()
    registry = ExperimentTrackingSinkRegistry([sink])
    first_projection = project_experiment_tracking(
        canonical_run_ref=run["optimization_run_id"],
        tracking_profile="recording",
        artifact_store=store,
        sink_registry=registry,
    )
    second_projection = project_experiment_tracking(
        canonical_run_ref=run["optimization_run_id"],
        tracking_profile="recording",
        artifact_store=store,
        sink_registry=registry,
    )
    assert first_projection.ok is second_projection.ok is True
    assert (
        first_projection.data["experiment_tracking_projection_report"]["projection_id"]
        == second_projection.data["experiment_tracking_projection_report"]["projection_id"]
    )
    assert len(sink.snapshots) == 1
    assert sink.snapshots[-1]["parameter_optimization_run"]["optimization_run_id"] == run["optimization_run_id"]

    failed_projection = project_experiment_tracking(
        canonical_run_ref=run["optimization_run_id"],
        tracking_profile="failing",
        artifact_store=store,
        sink_registry=ExperimentTrackingSinkRegistry([FailingSink()]),
    )
    assert failed_projection.ok is False
    assert failed_projection.data["experiment_tracking_projection_report"]["status"] == "blocked"
    assert store.load_artifact(PARAMETER_OPTIMIZATION_RUN, run["optimization_run_id"])["status"] == "completed"

    holdout = {
        "artifact_type": BACKTEST_RUN,
        "run_id": "holdout-run",
        "status": "passed",
        "selection_origin_ref": run["optimization_run_id"],
        "dataset_hash": run["holdout_dataset"]["sha256"],
        "strategy_specification_id": run["selected_child_refs"]["strategy_specification_id"],
        "summary": {"sharpe": 0.8},
        "bundle": {
            "exposure_summary": {"final_concentration": 0.2},
            "risk_decisions": {},
            "risk_limit_breaches": {},
            "risk_measure_summary": {"missing_required_telemetry": []},
        },
        "warnings": [],
        "blockers": [],
    }
    store.save_artifact(
        artifact_type=BACKTEST_RUN,
        artifact_id="holdout-run",
        payload=holdout,
        status="passed",
    )
    evaluation = generate_parameter_optimization_report(
        optimization_run_ref=run["optimization_run_id"],
        holdout_backtest_run_ref="holdout-run",
        artifact_store=store,
    )
    assert evaluation.ok is True

    audit_plan = create_parameter_optimization_audit_plan(
        optimization_run_ref=run["optimization_run_id"],
        attacks=[{"attack_type": "concentration"}, {"attack_type": "multiple_testing"}],
        artifact_store=store,
    )
    audit = generate_parameter_optimization_audit(
        audit_plan_ref=audit_plan.data["parameter_optimization_audit_plan"]["audit_plan_id"],
        artifact_store=store,
    )
    assert audit.ok is True
    unchanged = store.load_artifact(PARAMETER_OPTIMIZATION_RUN, run["optimization_run_id"])
    assert unchanged["selected_trial_id"] == run["selected_trial_id"]


def test_closed_observation_and_plan_reject_undeclared_inputs() -> None:
    with pytest.raises(ValueError, match="undeclared fields"):
        OptimizationObservation.from_mapping(
            {
                "schema_version": "1.0",
                "status": "passed",
                "metrics": {},
                "counts": {},
                "costs": {},
                "exposure": {},
                "risk": {},
                "quality": {},
                "constraints": {},
                "lineage": {},
                "raw_events": [],
            }
        )

    store = InMemoryResearchArtifactStore()
    base_validation_id, objective_validation_id = _base_validations(store)
    rejected = create_parameter_optimization_plan(
        base_backtest_specification_validation_ref=base_validation_id,
        holdout_dataset_manifest=_manifest("holdout", "2025-02-01T00:00:00+00:00", "2025-02-28T00:00:00+00:00"),
        holdout_data_quality_report=_quality("2025-02-01T00:00:00+00:00", "2025-02-28T00:00:00+00:00"),
        objective_validation_ref=objective_validation_id,
        search_space=[{"path": "/dataset/time_range/end", "type": "integer", "low": 1, "high": 2}],
        artifact_store=store,
    )
    assert rejected.ok is False
    assert "not explicitly tunable" in rejected.errors[0]["message"]


def test_objective_validation_rejects_filesystem_and_indirect_builtin_access() -> None:
    store = InMemoryResearchArtifactStore()
    unsafe = register_optimization_objective(
        name="unsafe",
        version="1",
        source_code='''
def objective(observation):
    opener = open
    return opener("/tmp/objective-output", "w")
''',
        factory_name="objective",
        artifact_store=store,
    )
    validation = validate_optimization_objective(
        implementation_version_id=unsafe.data["implementation_version"]["implementation_version_id"],
        artifact_store=store,
    )
    assert validation.ok is False
    report = validation.data["implementation_validation_report"]
    assert any("unsafe objective name is not allowed: open" in blocker for blocker in report["blockers"])

    top_level = register_optimization_objective(
        name="top-level",
        version="1",
        source_code="value = 1\n\ndef objective(observation):\n    return value\n",
        factory_name="objective",
        artifact_store=store,
    )
    top_level_validation = validate_optimization_objective(
        implementation_version_id=top_level.data["implementation_version"]["implementation_version_id"],
        artifact_store=store,
    )
    assert top_level_validation.ok is False
    assert "executable top-level statement" in top_level_validation.errors[0]["message"]

    non_finite = register_optimization_objective(
        name="non-finite",
        version="1",
        source_code="def objective(observation):\n    return float('nan')\n",
        factory_name="objective",
        artifact_store=store,
    )
    non_finite_validation = validate_optimization_objective(
        implementation_version_id=non_finite.data["implementation_version"]["implementation_version_id"],
        artifact_store=store,
    )
    assert non_finite_validation.ok is False
    assert "finite numeric value" in non_finite_validation.errors[0]["message"]


def test_seeded_random_retry_evidence_and_base_snapshot_drift_are_deterministic() -> None:
    search_space = [{"path": "/strategy/parameters/period", "type": "integer", "low": 1, "high": 5}]

    def _suggestions(seed: int) -> list[Mapping[str, Any]]:
        session = RandomOptimizationEngine().start(
            run_id="random-run",
            search_space=search_space,
            seed=seed,
            max_trials=5,
            prior_trials=[],
            direction="maximize",
        )
        values: list[Mapping[str, Any]] = []
        while suggestion := session.ask():
            values.append(dict(suggestion.parameters))
        return values

    assert _suggestions(17) == _suggestions(17)
    assert _suggestions(17) != _suggestions(18)

    store = InMemoryResearchArtifactStore()
    plan = _plan(store, resource_limits={"max_trial_attempts": 2})
    retry = RetryExecutor()
    partial = run_parameter_optimization(
        optimization_plan_ref=plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=retry,
        artifact_store=store,
        max_new_trials=1,
    )
    assert partial.ok is True
    trial = partial.data["new_trials"][0]
    assert [attempt["status"] for attempt in trial["attempts"]] == ["blocked", "passed"]
    assert "transient fixture failure" in trial["attempts"][0]["exception"]
    retry_results = get_parameter_optimization_results(
        optimization_run_ref=partial.data["parameter_optimization_run"][
            "optimization_run_id"
        ],
        artifact_store=store,
    )
    assert retry_results.ok is True

    drift_store = InMemoryResearchArtifactStore()
    drift_plan = _plan(drift_store)
    base_id = drift_plan["base_backtest_specification_id"]
    changed = deepcopy(drift_store.load_artifact(BACKTEST_SPECIFICATION, base_id))
    changed["dataset"]["payload"]["dataset_id"] = "silently-replaced-selection"
    drift_store.save_artifact(
        artifact_type=BACKTEST_SPECIFICATION,
        artifact_id=base_id,
        payload=changed,
        status="created",
    )
    drifted = run_parameter_optimization(
        optimization_plan_ref=drift_plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=FakeExecutor(),
        artifact_store=drift_store,
    )
    assert drifted.ok is False
    assert "canonical content" in drifted.errors[0]["message"]


def test_equal_objectives_use_canonical_parameter_tie_break() -> None:
    store = InMemoryResearchArtifactStore()
    plan = _plan(store)
    completed = run_parameter_optimization(
        optimization_plan_ref=plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=TieExecutor(),
        artifact_store=store,
    )

    assert completed.ok is True
    run = completed.data["parameter_optimization_run"]
    assert run["selected_objective_value"] == 1.0
    assert run["selected_parameters"] == {"/strategy/parameters/period": 2}


def test_random_run_can_exhaust_finite_space_before_trial_budget() -> None:
    store = InMemoryResearchArtifactStore()
    plan = _plan(store, max_trials=5)
    completed = run_parameter_optimization(
        optimization_plan_ref=plan["optimization_plan_id"],
        optimizer_profile="builtin_random",
        trial_executor=FakeExecutor(),
        artifact_store=store,
    )
    assert completed.ok is True
    run = completed.data["parameter_optimization_run"]
    assert run["status"] == "completed"
    assert run["trial_count"] == 2
    results = get_parameter_optimization_results(
        optimization_run_ref=run["optimization_run_id"], artifact_store=store
    )
    assert results.ok is True
    assert run["selection_policy"]["tie_break"] == [
        "canonical_parameters",
        "trial_id",
    ]


@pytest.mark.parametrize("target", ["run", "trial"])
def test_results_fail_closed_on_canonical_selection_evidence_tamper(target: str) -> None:
    store = InMemoryResearchArtifactStore()
    plan = _plan(store)
    completed = run_parameter_optimization(
        optimization_plan_ref=plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=FakeExecutor(),
        artifact_store=store,
    )
    assert completed.ok is True
    run = completed.data["parameter_optimization_run"]

    if target == "run":
        changed = deepcopy(run)
        changed["selected_trial_id"] = "parameter_optimization_trial_tampered"
        store.save_artifact(
            artifact_type=PARAMETER_OPTIMIZATION_RUN,
            artifact_id=run["optimization_run_id"],
            payload=changed,
            status=changed["status"],
        )
    else:
        trial_id = run["selected_trial_id"]
        changed = deepcopy(store.load_artifact(PARAMETER_OPTIMIZATION_TRIAL, trial_id))
        changed["objective_value"] = float(changed["objective_value"]) + 100.0
        store.save_artifact(
            artifact_type=PARAMETER_OPTIMIZATION_TRIAL,
            artifact_id=trial_id,
            payload=changed,
            status=changed["status"],
        )

    result = get_parameter_optimization_results(
        optimization_run_ref=run["optimization_run_id"], artifact_store=store
    )
    assert result.ok is False
    assert result.errors[0]["code"] == "parameter_optimization_lookup_failed"


def test_optuna_adapter_requires_isolated_postgres_and_reconciles_canonical_trials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "trader_research.optimization.optuna_adapter.metadata.version",
        lambda package: "4.2.0" if package == "optuna" else "unknown",
    )
    configured = OptunaOptimizationEngine(
        storage_url="postgresql://trader_optuna_writer:secret@db-a:5432/optuna",
        schema_name="trader_optuna",
        role_name="trader_optuna_writer",
    ).profile()
    same_identity_new_secret = OptunaOptimizationEngine(
        storage_url="postgresql://trader_optuna_writer:changed@db-a:5432/optuna",
        schema_name="trader_optuna",
        role_name="trader_optuna_writer",
    ).profile()
    different_database = OptunaOptimizationEngine(
        storage_url="postgresql://trader_optuna_writer:secret@db-b:5432/optuna",
        schema_name="trader_optuna",
        role_name="trader_optuna_writer",
    ).profile()
    wrong_role = OptunaOptimizationEngine(
        storage_url="postgresql://trader_app:secret@db-a:5432/optuna",
        role_name="trader_optuna_writer",
    ).profile()
    public_schema = OptunaOptimizationEngine(
        storage_url="postgresql://trader_optuna_writer:secret@db-a:5432/optuna",
        schema_name="public",
        role_name="trader_optuna_writer",
    ).profile()
    non_postgres = OptunaOptimizationEngine(
        storage_url="sqlite:///optuna.db",
        schema_name="trader_optuna",
        role_name="trader_optuna_writer",
    ).profile()

    assert configured.available is True
    assert configured.configuration_digest == same_identity_new_secret.configuration_digest
    assert configured.configuration_digest != different_database.configuration_digest
    assert "dedicated writer role" in str(wrong_role.reason)
    assert "dedicated non-public schema" in str(public_schema.reason)
    assert "PostgreSQL" in str(non_postgres.reason)

    from trader_research.optimization.optuna_adapter import _OptunaSession

    class _State:
        name = "COMPLETE"

    class _Trial:
        state = _State()

    class _Study:
        trials = [_Trial()]

    with pytest.raises(ValueError, match="operational state has 1 terminal trials but Trader has 0"):
        _OptunaSession(_Study(), [], 1, [])


def _plan(
    store: InMemoryResearchArtifactStore,
    *,
    resource_limits: Mapping[str, Any] | None = None,
    max_trials: int = 2,
) -> Mapping[str, Any]:
    base_validation_id, objective_validation_id = _base_validations(store)
    created = create_parameter_optimization_plan(
        base_backtest_specification_validation_ref=base_validation_id,
        holdout_dataset_manifest=_manifest("holdout", "2025-02-01T00:00:00+00:00", "2025-02-28T00:00:00+00:00"),
        holdout_data_quality_report=_quality("2025-02-01T00:00:00+00:00", "2025-02-28T00:00:00+00:00"),
        objective_validation_ref=objective_validation_id,
        search_space=[{"path": "/strategy/parameters/period", "type": "integer", "low": 2, "high": 3}],
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
        implementation_validation_ref=strategy_validation.data["implementation_validation_report"]["validation_id"],
        parameters={"period": 2},
        tunable_fields=["/strategy/parameters/period"],
        artifact_store=store,
    )
    strategy_spec_validation = validate_strategy_specification(
        strategy_specification_id=strategy_spec.data["strategy_specification"]["strategy_specification_id"],
        artifact_store=store,
    )
    backtest = create_backtest_specification(
        strategy_specification_validation_ref=strategy_spec_validation.data[
            "strategy_specification_validation_report"
        ]["validation_id"],
        dataset_manifest=_manifest("selection", "2025-01-01T00:00:00+00:00", "2025-01-31T00:00:00+00:00"),
        data_quality_report=_quality("2025-01-01T00:00:00+00:00", "2025-01-31T00:00:00+00:00"),
        artifact_store=store,
    )
    backtest_validation = validate_backtest_specification(
        backtest_specification_id=backtest.data["backtest_specification"]["backtest_specification_id"],
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
        implementation_version_id=objective.data["implementation_version"]["implementation_version_id"],
        artifact_store=store,
    )
    assert objective_validation.ok is True
    return (
        backtest_validation.data["backtest_specification_validation_report"]["validation_id"],
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
