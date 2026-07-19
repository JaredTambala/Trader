"""Canonical optimization plan/run/trial loading and integrity validation."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from trader_research.foundation import stable_research_id
from trader_research.foundation.artifacts import ResearchArtifactStore, load_artifact_ref
from trader_research.governance.artifacts import (
    BACKTEST_RUN,
    PARAMETER_OPTIMIZATION_PLAN,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
)
from trader_research.experiments.implementations import evaluate_objective, load_passed_implementation
from trader_research.experiments.specifications import (
    load_passed_backtest_specification,
    load_passed_risk_stack_specification,
    load_passed_strategy_specification,
)
from trader_research.experiments.specifications.common import (
    artifact_snapshot,
    normalized_dataset_manifest,
    validate_quality_report,
)

from .engines import dimension_values
from .executor import backtest_optimization_observation
from .planning import (
    _allowed_tunable_paths,
    _plan_identity,
    _validate_constraints,
    _validate_holdout,
    _validate_resource_limits,
    _validate_search_space,
)
from .validation import constraint_blockers


def load_validated_parameter_optimization_plan(
    store: ResearchArtifactStore,
    plan_ref: str,
) -> tuple[Mapping[str, Any], Any, Mapping[str, Any]]:
    """Load a canonical plan and revalidate all sealed upstream evidence."""
    plan = load_artifact_ref(store, PARAMETER_OPTIMIZATION_PLAN, plan_ref)
    if plan.get("status") != "created" or plan.get("artifact_type") != PARAMETER_OPTIMIZATION_PLAN:
        raise ValueError("optimization plan must be a created parameter_optimization_plan")
    if stable_research_id("parameter_optimization_plan", _plan_identity(plan)) != plan.get(
        "optimization_plan_id"
    ):
        raise ValueError("optimization plan ID does not match its canonical content")
    base, base_validation = load_passed_backtest_specification(
        store, str(plan["base_backtest_specification_validation_id"])
    )
    if base.get("backtest_specification_id") != plan.get("base_backtest_specification_id"):
        raise ValueError("base backtest specification identity drifted after planning")
    if base_validation.get("validation_id") != plan.get("base_backtest_specification_validation_id"):
        raise ValueError("base backtest specification validation drifted after planning")
    if (base.get("dataset") or {}).get("sha256") != plan.get("selection_dataset_hash"):
        raise ValueError("selection dataset snapshot drifted after planning")

    holdout_snapshot = dict(plan.get("holdout_dataset") or {})
    holdout_quality_snapshot = dict(plan.get("holdout_data_quality") or {})
    holdout = normalized_dataset_manifest(dict(holdout_snapshot.get("payload") or {}))
    holdout_quality = validate_quality_report(
        dict(holdout_quality_snapshot.get("payload") or {}), holdout
    )
    if artifact_snapshot(holdout) != holdout_snapshot:
        raise ValueError("holdout dataset snapshot drifted after planning")
    if artifact_snapshot(holdout_quality) != holdout_quality_snapshot:
        raise ValueError("holdout data-quality snapshot drifted after planning")
    selection = normalized_dataset_manifest(dict(base["dataset"]["payload"]))
    _validate_holdout(selection, holdout)

    objective, objective_validation = load_passed_implementation(
        store,
        str(plan["objective_validation_id"]),
        expected_kind="optimization_objective",
    )
    if objective.implementation_version_id != plan.get("objective_implementation_version_id"):
        raise ValueError("optimization objective identity drifted after planning")
    if objective.source_hash != plan.get("objective_source_hash"):
        raise ValueError("optimization objective source hash drifted after planning")
    if objective_validation.get("validation_id") != plan.get("objective_validation_id"):
        raise ValueError("optimization objective validation drifted after planning")

    allowed_paths = _allowed_tunable_paths(store, base)
    if _validate_search_space(list(plan.get("search_space") or []), allowed_paths) != list(
        plan.get("search_space") or []
    ):
        raise ValueError("optimization search space is not canonical")
    if _validate_constraints(list(plan.get("constraints") or [])) != list(
        plan.get("constraints") or []
    ):
        raise ValueError("optimization constraints are not canonical")
    if _validate_resource_limits(dict(plan.get("resource_limits") or {})) != dict(
        plan.get("resource_limits") or {}
    ):
        raise ValueError("optimization resource limits are not canonical")
    return plan, objective, objective_validation


def load_validated_parameter_optimization_run(
    store: ResearchArtifactStore,
    run_ref: str,
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    """Load one run and independently recompute its complete trial ledger and selection."""
    run = load_artifact_ref(store, PARAMETER_OPTIMIZATION_RUN, run_ref)
    if run.get("artifact_type") != PARAMETER_OPTIMIZATION_RUN:
        raise ValueError("artifact_type must be parameter_optimization_run")
    plan, objective, objective_validation = load_validated_parameter_optimization_plan(
        store, str(run.get("optimization_plan_id") or "")
    )
    identity = {
        "optimization_plan_id": plan["optimization_plan_id"],
        "engine_profile": dict(run.get("engine_profile") or {}),
        "executor_kind": str(run.get("executor_kind") or ""),
    }
    run_id = str(run.get("optimization_run_id") or "")
    if stable_research_id("parameter_optimization_run", identity) != run_id:
        raise ValueError("optimization run ID does not match its canonical content")
    if run.get("seed") != plan.get("seed") or run.get("direction") != plan.get("direction"):
        raise ValueError("optimization run seed or direction drifted from its plan")
    if run.get("max_trials") != plan.get("max_trials"):
        raise ValueError("optimization run trial budget drifted from its plan")
    if run.get("holdout_dataset") != plan.get("holdout_dataset"):
        raise ValueError("optimization run holdout dataset drifted from its plan")
    if run.get("holdout_data_quality") != plan.get("holdout_data_quality"):
        raise ValueError("optimization run holdout quality drifted from its plan")
    if run.get("objective_validation_id") != objective_validation.get("validation_id"):
        raise ValueError("optimization run objective validation drifted from its plan")

    trials = _run_trials(store, run_id)
    _validate_trials(
        trials,
        store=store,
        run_id=run_id,
        plan=plan,
        objective=objective,
        executor_kind=str(run.get("executor_kind") or ""),
    )
    expected_trial_ids = [trial["trial_id"] for trial in trials]
    if list(run.get("trial_ids") or []) != expected_trial_ids:
        raise ValueError("optimization run trial ledger does not match trial_ids")
    if run.get("trial_count") != len(trials):
        raise ValueError("optimization run trial_count does not match its ledger")
    passed_count = sum(1 for trial in trials if trial.get("status") == "passed")
    if run.get("passed_trial_count") != passed_count:
        raise ValueError("optimization run passed_trial_count does not match its ledger")
    if run.get("failed_trial_count") != len(trials) - passed_count:
        raise ValueError("optimization run failed_trial_count does not match its ledger")

    selected = _select_trial(trials, str(plan["direction"]))
    expected_selection = {
        "selected_trial_id": selected.get("trial_id") if selected else None,
        "selected_parameters": dict(selected.get("parameters") or {}) if selected else None,
        "selected_objective_value": selected.get("objective_value") if selected else None,
        "selected_child_refs": dict(selected.get("child_refs") or {}) if selected else {},
    }
    for key, expected in expected_selection.items():
        if run.get(key) != expected:
            raise ValueError(f"optimization run {key} does not match deterministic selection")
    if run.get("selection_policy") != {
        "direction": plan["direction"],
        "tie_break": ["canonical_parameters", "trial_id"],
    }:
        raise ValueError("optimization run selection policy drifted")
    _validate_run_status(run, trials, selected)
    provider_state = dict(run.get("provider_state") or {})
    if provider_state.get("run_id") not in {None, run_id}:
        raise ValueError("optimization provider state belongs to a different run")
    return run, trials


def _validate_trials(
    trials: Sequence[Mapping[str, Any]],
    *,
    store: ResearchArtifactStore,
    run_id: str,
    plan: Mapping[str, Any],
    objective: Any,
    executor_kind: str,
) -> None:
    expected_paths = {str(item["path"]): item for item in plan.get("search_space") or []}
    for expected_sequence, trial in enumerate(trials):
        if trial.get("artifact_type") != PARAMETER_OPTIMIZATION_TRIAL:
            raise ValueError("optimization trial artifact_type drifted")
        if trial.get("optimization_run_id") != run_id:
            raise ValueError("optimization trial belongs to a different run")
        if trial.get("optimization_plan_id") != plan.get("optimization_plan_id"):
            raise ValueError("optimization trial belongs to a different plan")
        if trial.get("sequence") != expected_sequence:
            raise ValueError("optimization trial sequence is not contiguous")
        parameters = dict(trial.get("parameters") or {})
        if set(parameters) != set(expected_paths):
            raise ValueError("optimization trial parameters do not match the declared search space")
        for path, value in parameters.items():
            if value not in dimension_values(expected_paths[path]):
                raise ValueError(f"optimization trial parameter is outside its search space: {path}")
        trial_id = stable_research_id(
            "parameter_optimization_trial",
            {
                "optimization_run_id": run_id,
                "parameters": parameters,
                "sequence": expected_sequence,
            },
        )
        if trial.get("trial_id") != trial_id:
            raise ValueError("optimization trial ID does not match its canonical content")
        attempts = list(trial.get("attempts") or [])
        _validate_attempts(attempts, trial=trial, plan=plan)
        observation = dict(trial.get("observation") or {})
        status = str(trial.get("status") or "")
        if executor_kind == "backtest_specification":
            _validate_backtest_trial_lineage(
                store,
                trial=trial,
                observation=observation,
                plan=plan,
                run_id=run_id,
            )
        if status == "passed":
            if not observation:
                raise ValueError("passed optimization trial is missing its observation")
            lineage = dict(observation.get("lineage") or {})
            if lineage.get("trial_id") != trial_id or lineage.get("fold") != "selection":
                raise ValueError("optimization trial observation lineage drifted")
            value, diagnostics = evaluate_objective(objective, observation)
            if trial.get("objective_value") != value:
                raise ValueError("optimization trial objective value drifted from its observation")
            if dict(trial.get("objective_diagnostics") or {}) != dict(diagnostics):
                raise ValueError("optimization trial objective diagnostics drifted from its observation")
            blockers = constraint_blockers(plan.get("constraints") or [], observation)
            if blockers:
                raise ValueError("passed optimization trial violates a declared constraint")
        elif status not in {"blocked", "rejected"}:
            raise ValueError("optimization trial has an unsupported status")


def _validate_run_status(
    run: Mapping[str, Any],
    trials: Sequence[Mapping[str, Any]],
    selected: Mapping[str, Any] | None,
) -> None:
    status = str(run.get("status") or "")
    provider_state = dict(run.get("provider_state") or {})
    profile = dict(run.get("engine_profile") or {})
    built_in_exhausted = (
        profile.get("provider") == "trader"
        and profile.get("algorithm") in {"grid", "seeded_random"}
        and provider_state.get("remaining") == 0
    )
    exhausted = len(trials) >= int(run.get("max_trials") or 0) or built_in_exhausted
    if status == "completed" and (not exhausted or selected is None):
        raise ValueError("completed optimization run is not exhausted with a selection")
    if status == "partial" and exhausted:
        raise ValueError("partial optimization run has exhausted its trial budget")
    if status == "blocked" and (not exhausted or selected is not None):
        raise ValueError("blocked optimization run has inconsistent terminal evidence")
    if status not in {"completed", "partial", "blocked"}:
        raise ValueError("optimization run has an unsupported status")


def _validate_attempts(
    attempts: Sequence[Mapping[str, Any]],
    *,
    trial: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    max_attempts = int((plan.get("resource_limits") or {}).get("max_trial_attempts", 1))
    if not attempts or len(attempts) > max_attempts:
        raise ValueError("optimization trial attempt evidence is incomplete")
    if [item.get("attempt") for item in attempts] != list(range(1, len(attempts) + 1)):
        raise ValueError("optimization trial attempt sequence is not contiguous")
    required = {"attempt", "status", "child_refs", "warnings", "blockers", "exception"}
    for index, attempt in enumerate(attempts):
        if set(attempt) != required:
            raise ValueError("optimization trial attempt fields are not canonical")
        if attempt.get("status") not in {"passed", "blocked", "rejected"}:
            raise ValueError("optimization trial attempt has an unsupported status")
        if not isinstance(attempt.get("child_refs"), Mapping):
            raise ValueError("optimization trial attempt child_refs must be an object")
        if not isinstance(attempt.get("warnings"), list) or not isinstance(
            attempt.get("blockers"), list
        ):
            raise ValueError("optimization trial attempt warnings and blockers must be arrays")
        exception = attempt.get("exception")
        if exception is not None and (
            not isinstance(exception, str) or exception not in attempt.get("blockers", [])
        ):
            raise ValueError("optimization trial exception evidence is incomplete")
        if attempt.get("status") == "passed" and index != len(attempts) - 1:
            raise ValueError("optimization trial retried after a passed attempt")
    final = attempts[-1]
    if dict(final.get("child_refs") or {}) != dict(trial.get("child_refs") or {}):
        raise ValueError("optimization trial final attempt child refs drifted")
    if list(final.get("warnings") or []) != list(trial.get("warnings") or []):
        raise ValueError("optimization trial final attempt warnings drifted")
    final_status = str(final.get("status") or "")
    trial_status = str(trial.get("status") or "")
    allowed_final_statuses = {
        "passed": {"passed"},
        "rejected": {"passed", "rejected"},
        "blocked": {"passed", "blocked"},
    }
    if final_status not in allowed_final_statuses.get(trial_status, set()):
        raise ValueError("optimization trial status does not match its final attempt")


def _validate_backtest_trial_lineage(
    store: ResearchArtifactStore,
    *,
    trial: Mapping[str, Any],
    observation: Mapping[str, Any],
    plan: Mapping[str, Any],
    run_id: str,
) -> None:
    refs = dict(trial.get("child_refs") or {})
    if not refs:
        if observation or trial.get("status") != "blocked":
            raise ValueError("backtest optimization trial is missing child lineage")
        return
    required = (
        "strategy_specification_id",
        "strategy_specification_validation_id",
        "backtest_specification_id",
        "backtest_specification_validation_id",
        "backtest_run_id",
    )
    if any(not str(refs.get(key) or "") for key in required):
        raise ValueError("backtest optimization trial child lineage is incomplete")

    strategy, strategy_validation = load_passed_strategy_specification(
        store, str(refs["strategy_specification_validation_id"])
    )
    if strategy.get("strategy_specification_id") != refs["strategy_specification_id"]:
        raise ValueError("optimization trial strategy child lineage drifted")
    if strategy_validation.get("validation_id") != refs["strategy_specification_validation_id"]:
        raise ValueError("optimization trial strategy validation lineage drifted")

    risk = None
    risk_id = refs.get("risk_stack_specification_id")
    risk_validation_id = refs.get("risk_stack_specification_validation_id")
    if bool(risk_id) != bool(risk_validation_id):
        raise ValueError("optimization trial risk child lineage is incomplete")
    if risk_validation_id:
        risk, risk_validation = load_passed_risk_stack_specification(
            store, str(risk_validation_id)
        )
        if risk.get("risk_stack_specification_id") != risk_id:
            raise ValueError("optimization trial risk child lineage drifted")
        if risk_validation.get("validation_id") != risk_validation_id:
            raise ValueError("optimization trial risk validation lineage drifted")

    for path, expected in dict(trial.get("parameters") or {}).items():
        if _child_parameter_value(strategy, risk, str(path)) != expected:
            raise ValueError(f"optimization trial parameter was not materialized: {path}")

    backtest, backtest_validation = load_passed_backtest_specification(
        store, str(refs["backtest_specification_validation_id"])
    )
    if backtest.get("backtest_specification_id") != refs["backtest_specification_id"]:
        raise ValueError("optimization trial backtest child lineage drifted")
    if backtest_validation.get("validation_id") != refs["backtest_specification_validation_id"]:
        raise ValueError("optimization trial backtest validation lineage drifted")
    expected_backtest_fields = {
        "strategy_specification_id": refs["strategy_specification_id"],
        "strategy_specification_validation_id": refs["strategy_specification_validation_id"],
        "risk_stack_specification_id": risk_id,
        "risk_stack_specification_validation_id": risk_validation_id,
        "parent_specification_ref": plan["base_backtest_specification_id"],
        "selection_origin_ref": run_id,
    }
    for key, expected in expected_backtest_fields.items():
        if backtest.get(key) != expected:
            raise ValueError(f"optimization trial backtest {key} lineage drifted")
    if (backtest.get("dataset") or {}).get("sha256") != plan.get("selection_dataset_hash"):
        raise ValueError("optimization trial backtest used a non-selection dataset")

    backtest_run = load_artifact_ref(store, BACKTEST_RUN, str(refs["backtest_run_id"]))
    expected_run_fields = {
        "run_id": refs["backtest_run_id"],
        "backtest_specification_id": refs["backtest_specification_id"],
        "backtest_specification_validation_id": refs["backtest_specification_validation_id"],
        "dataset_hash": plan["selection_dataset_hash"],
        "selection_origin_ref": run_id,
    }
    for key, expected in expected_run_fields.items():
        if backtest_run.get(key) != expected:
            raise ValueError(f"optimization trial backtest run {key} lineage drifted")
    expected_observation = backtest_optimization_observation(
        backtest_run, str(trial["trial_id"])
    )
    if dict(observation) != expected_observation:
        raise ValueError("optimization trial observation drifted from its backtest run")


def _child_parameter_value(
    strategy: Mapping[str, Any],
    risk: Mapping[str, Any] | None,
    path: str,
) -> Any:
    parts = [part for part in path.split("/") if part]
    if len(parts) == 3 and parts[0] == "strategy" and parts[1] in {
        "parameters",
        "sizing",
    }:
        return (strategy.get(parts[1]) or {}).get(parts[2])
    if len(parts) == 4 and parts[0] == "risk" and parts[2] == "parameters" and risk:
        return (risk.get("risk_managers") or [])[int(parts[1])].get("parameters", {}).get(
            parts[3]
        )
    raise ValueError(f"unsupported trial parameter path: {path}")


def _run_trials(store: ResearchArtifactStore, run_id: str) -> list[Mapping[str, Any]]:
    trials: list[Mapping[str, Any]] = []
    for record in store.list_artifacts(artifact_type=PARAMETER_OPTIMIZATION_TRIAL):
        if record.payload.get("optimization_run_id") != run_id:
            continue
        if record.payload.get("trial_id") != record.artifact_id:
            raise ValueError("optimization trial payload identity drifted from its artifact key")
        trials.append(record.payload)
    return sorted(
        trials,
        key=lambda item: (int(item.get("sequence") or 0), str(item.get("trial_id") or "")),
    )


def _select_trial(trials: Sequence[Mapping[str, Any]], direction: str) -> Mapping[str, Any] | None:
    passed = [item for item in trials if item.get("status") == "passed" and isinstance(item.get("objective_value"), (int, float))]
    if not passed:
        return None
    if direction == "maximize":
        return min(
            passed,
            key=lambda item: (
                -float(item["objective_value"]),
                _canonical_parameters(item),
                str(item["trial_id"]),
            ),
        )
    return min(
        passed,
        key=lambda item: (
            float(item["objective_value"]),
            _canonical_parameters(item),
            str(item["trial_id"]),
        ),
    )


def _canonical_parameters(trial: Mapping[str, Any]) -> str:
    return json.dumps(trial.get("parameters") or {}, sort_keys=True, separators=(",", ":"), default=str)
