"""Contracts for deterministic parameter-optimisation workflow and selection.

Subject: Trial generation, resume, projection, evaluation separation, selection, and evidence integrity.
Level: Offline application workflow contract.
Collaborators: In-memory artifacts, deterministic trial executors, tracking sinks, and Review services.
Guarantees: Resumed runs match uninterrupted runs and canonical selection evidence rejects tampering.
Non-goals: Objective sandbox policy, real backtests, Postgres projections, or Optuna storage.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

import pytest

from tests.trader_research.experiments.optimization_fixtures import (
    FailingSink,
    FakeExecutor,
    RecordingSink,
    RetryExecutor,
    TieExecutor,
    _plan,
)
from trader_research.experiments import (
    ExperimentTrackingSinkRegistry,
    RandomOptimizationEngine,
    get_parameter_optimization_results,
    project_experiment_tracking,
    run_parameter_optimization,
)
from trader_research.foundation.artifacts import InMemoryResearchArtifactStore
from trader_research.governance.artifacts import (
    BACKTEST_RUN,
    BACKTEST_SPECIFICATION,
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
)
from trader_research.review import (
    create_parameter_optimization_audit_plan,
    generate_parameter_optimization_audit,
    generate_parameter_optimization_report,
)


def test_grid_resume_selection_projection_evaluation_and_audit_are_separate() -> None:
    """Optimisation resume, selection, tracking, evaluation, and audit remain distinct evidence stages."""
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
        == second_projection.data["experiment_tracking_projection_report"][
            "projection_id"
        ]
    )
    assert len(sink.snapshots) == 1
    assert (
        sink.snapshots[-1]["parameter_optimization_run"]["optimization_run_id"]
        == run["optimization_run_id"]
    )

    failed_projection = project_experiment_tracking(
        canonical_run_ref=run["optimization_run_id"],
        tracking_profile="failing",
        artifact_store=store,
        sink_registry=ExperimentTrackingSinkRegistry([FailingSink()]),
    )
    assert failed_projection.ok is False
    assert (
        failed_projection.data["experiment_tracking_projection_report"]["status"]
        == "blocked"
    )
    assert (
        store.load_artifact(PARAMETER_OPTIMIZATION_RUN, run["optimization_run_id"])[
            "status"
        ]
        == "completed"
    )

    holdout = {
        "artifact_type": BACKTEST_RUN,
        "run_id": "holdout-run",
        "status": "passed",
        "selection_origin_ref": run["optimization_run_id"],
        "dataset_hash": run["holdout_dataset"]["sha256"],
        "strategy_specification_id": run["selected_child_refs"][
            "strategy_specification_id"
        ],
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
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[BACKTEST_RUN],
        producer_tool="test_parameter_optimization_fixture",
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
        audit_plan_ref=audit_plan.data["parameter_optimization_audit_plan"][
            "audit_plan_id"
        ],
        artifact_store=store,
    )
    assert audit.ok is True
    unchanged = store.load_artifact(
        PARAMETER_OPTIMIZATION_RUN, run["optimization_run_id"]
    )
    assert unchanged["selected_trial_id"] == run["selected_trial_id"]


def test_builtin_grid_resume_matches_uninterrupted_provider_evidence() -> None:
    """A resumed built-in grid run exactly matches uninterrupted canonical provider evidence."""
    uninterrupted_store = InMemoryResearchArtifactStore()
    uninterrupted_plan = _plan(uninterrupted_store)
    uninterrupted = run_parameter_optimization(
        optimization_plan_ref=uninterrupted_plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=FakeExecutor(),
        artifact_store=uninterrupted_store,
    )
    assert uninterrupted.ok is True

    resumed_store = InMemoryResearchArtifactStore()
    resumed_plan = _plan(resumed_store)
    partial = run_parameter_optimization(
        optimization_plan_ref=resumed_plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=FakeExecutor(),
        artifact_store=resumed_store,
        max_new_trials=1,
    )
    assert partial.ok is True
    resumed = run_parameter_optimization(
        optimization_plan_ref=resumed_plan["optimization_plan_id"],
        optimizer_profile="builtin_grid",
        trial_executor=FakeExecutor(),
        artifact_store=resumed_store,
    )
    assert resumed.ok is True

    uninterrupted_run = uninterrupted.data["parameter_optimization_run"]
    resumed_run = resumed.data["parameter_optimization_run"]
    uninterrupted_trials = get_parameter_optimization_results(
        optimization_run_ref=uninterrupted_run["optimization_run_id"],
        artifact_store=uninterrupted_store,
    ).data["trials"]
    resumed_trials = get_parameter_optimization_results(
        optimization_run_ref=resumed_run["optimization_run_id"],
        artifact_store=resumed_store,
    ).data["trials"]

    assert resumed_run == uninterrupted_run
    assert resumed_trials == uninterrupted_trials
    engine_trial_ids = [trial["engine_trial_id"] for trial in resumed_trials]
    assert engine_trial_ids[0].startswith("grid-000000-")
    assert engine_trial_ids[1].startswith("grid-000001-")


def test_seeded_random_retry_evidence_and_base_snapshot_drift_are_deterministic() -> (
    None
):
    """Seeded suggestions, retry records, and canonical snapshot drift behave deterministically."""
    search_space = [
        {"path": "/strategy/parameters/period", "type": "integer", "low": 1, "high": 5}
    ]

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
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[BACKTEST_SPECIFICATION],
        producer_tool="test_parameter_optimization_fixture",
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
    """Equal objective values resolve through the declared canonical parameter tie-break."""
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
    """Random optimisation completes when finite unique suggestions end before its budget."""
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
def test_results_fail_closed_on_canonical_selection_evidence_tamper(
    target: str,
) -> None:
    """Result lookup rejects tampering in selected run or trial evidence."""
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
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_RUN],
            producer_tool="test_parameter_optimization_fixture",
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
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_TRIAL],
            producer_tool="test_parameter_optimization_fixture",
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
