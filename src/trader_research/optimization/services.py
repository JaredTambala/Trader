"""Canonical parameter-optimization plans, runs, trials, and result lookup."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from trader_research.artifact_store import ResearchArtifactStore, ResearchArtifactStoreError, load_artifact_ref
from trader_research.contracts import ArtifactReference, SCHEMA_VERSION, SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import (
    BACKTEST_RUN,
    PARAMETER_OPTIMIZATION_PLAN,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
    stable_research_id,
)
from trader_research.implementations import evaluate_objective, load_passed_implementation
from trader_research.specifications import (
    load_passed_backtest_specification,
    load_passed_risk_stack_specification,
    load_passed_strategy_specification,
)
from trader_research.specifications.common import (
    artifact_snapshot,
    normalized_dataset_manifest,
    parse_datetime,
    validate_quality_report,
)

from .contracts import OptimizationOutcome, OptimizationTrialExecutor, TrialExecution
from .engines import OptimizationEngineRegistry, dimension_values
from .executor import backtest_optimization_observation


RESEARCH_GET_OPTIMIZER_RUNTIME = "research_get_optimizer_runtime"
RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN = "research_create_parameter_optimization_plan"
RESEARCH_RUN_PARAMETER_OPTIMIZATION = "research_run_parameter_optimization"
RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS = "research_get_parameter_optimization_results"
RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS = "research_run_parameter_optimization_variants"


def get_optimizer_runtime(*, engine_registry: OptimizationEngineRegistry | None = None) -> ToolEnvelope:
    """Return configured optimizer profiles without initializing provider state."""
    registry = engine_registry or OptimizationEngineRegistry()
    return success_envelope(
        command=RESEARCH_GET_OPTIMIZER_RUNTIME,
        side_effect=SideEffect.READ_ONLY,
        data={"profiles": [profile.to_dict() for profile in registry.profiles()]},
    )


def create_parameter_optimization_plan(
    *,
    base_backtest_specification_validation_ref: str,
    holdout_dataset_manifest: Mapping[str, Any],
    holdout_data_quality_report: Mapping[str, Any],
    objective_validation_ref: str,
    search_space: Sequence[Mapping[str, Any]],
    direction: str = "maximize",
    constraints: Sequence[Mapping[str, Any]] | None = None,
    seed: int = 0,
    max_trials: int = 25,
    resource_limits: Mapping[str, Any] | None = None,
    parent_plan_ref: str | None = None,
    variant_reason: str | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Create a provider-neutral study plan over explicitly tunable decision parameters."""
    command = RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        base, base_validation = load_passed_backtest_specification(
            artifact_store, base_backtest_specification_validation_ref
        )
        objective, objective_validation = load_passed_implementation(
            artifact_store, objective_validation_ref, expected_kind="optimization_objective"
        )
        selection_manifest = normalized_dataset_manifest(dict(base["dataset"]["payload"]))
        holdout_manifest = normalized_dataset_manifest(holdout_dataset_manifest)
        holdout_quality = validate_quality_report(holdout_data_quality_report, holdout_manifest)
        _validate_holdout(selection_manifest, holdout_manifest)
        allowed_paths = _allowed_tunable_paths(artifact_store, base)
        normalized_space = _validate_search_space(search_space, allowed_paths)
        if direction not in {"maximize", "minimize"}:
            raise ValueError("direction must be maximize or minimize")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        if isinstance(max_trials, bool) or not isinstance(max_trials, int) or not 1 <= max_trials <= 1000:
            raise ValueError("max_trials must be between 1 and 1000")
        normalized_constraints = _validate_constraints(constraints or ())
        identity = {
            "base_backtest_specification_id": base["backtest_specification_id"],
            "base_backtest_specification_validation_id": base_validation["validation_id"],
            "selection_dataset_hash": base["dataset"]["sha256"],
            "holdout_dataset": artifact_snapshot(holdout_manifest),
            "holdout_data_quality": artifact_snapshot(holdout_quality),
            "objective_implementation_version_id": objective.implementation_version_id,
            "objective_validation_id": objective_validation["validation_id"],
            "objective_source_hash": objective.source_hash,
            "search_space": normalized_space,
            "direction": direction,
            "constraints": normalized_constraints,
            "seed": seed,
            "max_trials": max_trials,
            "resource_limits": _validate_resource_limits(resource_limits or {}),
            "parent_plan_ref": parent_plan_ref,
            "variant_reason": variant_reason,
        }
        plan_id = stable_research_id("parameter_optimization_plan", identity)
        payload = {
            "artifact_type": PARAMETER_OPTIMIZATION_PLAN,
            "schema_version": SCHEMA_VERSION,
            "optimization_plan_id": plan_id,
            **identity,
            "status": "created",
        }
        record = artifact_store.save_artifact(
            artifact_type=PARAMETER_OPTIMIZATION_PLAN,
            artifact_id=plan_id,
            payload=payload,
            status="created",
            metadata={
                "base_backtest_specification_id": base["backtest_specification_id"],
                "max_trials": max_trials,
            },
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return _error(command, "parameter_optimization_plan_creation_failed", str(exc))
    return success_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"parameter_optimization_plan": payload},
        artifacts={"parameter_optimization_plan": record.reference().to_dict()},
    )


def run_parameter_optimization(
    *,
    optimization_plan_ref: str,
    optimizer_profile: str,
    trial_executor: OptimizationTrialExecutor,
    artifact_store: ResearchArtifactStore | None,
    engine_registry: OptimizationEngineRegistry | None = None,
    max_new_trials: int | None = None,
) -> ToolEnvelope:
    """Run or resume one canonical sequential single-objective study."""
    command = RESEARCH_RUN_PARAMETER_OPTIMIZATION
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        plan, objective, objective_validation = load_validated_parameter_optimization_plan(
            artifact_store, optimization_plan_ref
        )
        registry = engine_registry or OptimizationEngineRegistry()
        engine = registry.get(optimizer_profile)
        profile = engine.profile()
        run_id = stable_research_id(
            "parameter_optimization_run",
            {
                "optimization_plan_id": plan["optimization_plan_id"],
                "engine_profile": profile.to_dict(),
                "executor_kind": trial_executor.executor_kind,
            },
        )
        prior_trials = _run_trials(artifact_store, run_id)
        _validate_trials(
            prior_trials,
            store=artifact_store,
            run_id=run_id,
            plan=plan,
            objective=objective,
            executor_kind=trial_executor.executor_kind,
        )
        session = engine.start(
            run_id=run_id,
            search_space=list(plan["search_space"]),
            seed=int(plan["seed"]),
            max_trials=int(plan["max_trials"]),
            prior_trials=prior_trials,
            direction=str(plan["direction"]),
        )
        remaining_budget = int(plan["max_trials"]) - len(prior_trials)
        call_budget = remaining_budget if max_new_trials is None else min(remaining_budget, _positive(max_new_trials))
        new_trials: list[Mapping[str, Any]] = []
        engine_exhausted = False
        for _ in range(call_budget):
            suggestion = session.ask()
            if suggestion is None:
                engine_exhausted = True
                break
            trial_id = stable_research_id(
                "parameter_optimization_trial",
                {
                    "optimization_run_id": run_id,
                    "parameters": suggestion.parameters,
                    "sequence": len(prior_trials) + len(new_trials),
                },
            )
            execution, attempts = _execute_trial(
                trial_executor,
                plan=plan,
                parameters=suggestion.parameters,
                trial_id=trial_id,
                optimization_run_id=run_id,
                max_attempts=int((plan.get("resource_limits") or {}).get("max_trial_attempts", 1)),
            )
            value = None
            diagnostics: Mapping[str, Any] = {}
            blockers = list(execution.blockers)
            status = execution.status
            if status == "passed" and execution.observation is not None:
                constraint_blockers = _constraint_blockers(plan.get("constraints") or [], execution.observation)
                blockers.extend(constraint_blockers)
                if blockers:
                    status = "rejected"
                else:
                    try:
                        value, diagnostics = evaluate_objective(objective, execution.observation)
                    except Exception as exc:
                        status = "blocked"
                        blockers.append(f"objective evaluation failed: {exc}")
            trial_payload = {
                "artifact_type": PARAMETER_OPTIMIZATION_TRIAL,
                "schema_version": SCHEMA_VERSION,
                "trial_id": trial_id,
                "optimization_run_id": run_id,
                "optimization_plan_id": plan["optimization_plan_id"],
                "sequence": len(prior_trials) + len(new_trials),
                "engine_trial_id": suggestion.engine_trial_id,
                "parameters": dict(suggestion.parameters),
                "status": status,
                "objective_value": value,
                "objective_diagnostics": dict(diagnostics),
                "observation": dict(execution.observation or {}),
                "child_refs": dict(execution.child_refs),
                "warnings": list(execution.warnings),
                "blockers": blockers,
                "attempts": attempts,
            }
            artifact_store.save_artifact(
                artifact_type=PARAMETER_OPTIMIZATION_TRIAL,
                artifact_id=trial_id,
                payload=trial_payload,
                status=status,
                metadata={"optimization_run_id": run_id, "sequence": trial_payload["sequence"]},
            )
            session.tell(
                suggestion,
                OptimizationOutcome(
                    status=status,
                    value=value,
                    reason=blockers[0] if blockers else None,
                ),
            )
            new_trials.append(trial_payload)
        trials = sorted([*prior_trials, *new_trials], key=lambda item: (int(item["sequence"]), str(item["trial_id"])))
        selected = _select_trial(trials, str(plan["direction"]))
        exhausted = len(trials) >= int(plan["max_trials"]) or engine_exhausted
        status = "completed" if exhausted else "partial"
        if selected is None and exhausted:
            status = "blocked"
        payload = {
            "artifact_type": PARAMETER_OPTIMIZATION_RUN,
            "schema_version": SCHEMA_VERSION,
            "optimization_run_id": run_id,
            "optimization_plan_id": plan["optimization_plan_id"],
            "status": status,
            "engine_profile": profile.to_dict(),
            "executor_kind": trial_executor.executor_kind,
            "seed": plan["seed"],
            "direction": plan["direction"],
            "max_trials": plan["max_trials"],
            "trial_count": len(trials),
            "passed_trial_count": sum(1 for item in trials if item.get("status") == "passed"),
            "failed_trial_count": sum(1 for item in trials if item.get("status") != "passed"),
            "trial_ids": [item["trial_id"] for item in trials],
            "selected_trial_id": selected.get("trial_id") if selected else None,
            "selected_parameters": dict(selected.get("parameters") or {}) if selected else None,
            "selected_objective_value": selected.get("objective_value") if selected else None,
            "selected_child_refs": dict(selected.get("child_refs") or {}) if selected else {},
            "selection_policy": {
                "direction": plan["direction"],
                "tie_break": ["canonical_parameters", "trial_id"],
            },
            "holdout_dataset": plan["holdout_dataset"],
            "holdout_data_quality": plan["holdout_data_quality"],
            "objective_validation_id": objective_validation["validation_id"],
            "provider_state": dict(session.snapshot()),
            "promotion_readiness": "requires_holdout_evaluation_and_adversarial_audit",
            "warnings": [],
            "blockers": ["no passed optimization trial"] if selected is None and exhausted else [],
        }
        record = artifact_store.save_artifact(
            artifact_type=PARAMETER_OPTIMIZATION_RUN,
            artifact_id=run_id,
            payload=payload,
            status=status,
            metadata={"optimization_plan_id": plan["optimization_plan_id"], "engine_profile": profile.profile_name},
        )
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error(command, "parameter_optimization_run_failed", str(exc))
    envelope = success_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"parameter_optimization_run": payload, "new_trials": new_trials},
        artifacts={"parameter_optimization_run": record.reference().to_dict()},
    )
    if status != "blocked":
        return envelope
    return ToolEnvelope(
        ok=False,
        command=command,
        agent_owner=envelope.agent_owner,
        side_effect=envelope.side_effect,
        data=envelope.data,
        artifacts=envelope.artifacts,
        errors=({"code": "parameter_optimization_blocked", "message": payload["blockers"][0]},),
    )


def get_parameter_optimization_results(
    *,
    optimization_run_ref: str,
    artifact_store: ResearchArtifactStore | None,
) -> ToolEnvelope:
    """Read canonical run and complete trial ledger independently of provider availability."""
    command = RESEARCH_GET_PARAMETER_OPTIMIZATION_RESULTS
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.", read_only=True)
    try:
        run, trials = load_validated_parameter_optimization_run(
            artifact_store, optimization_run_ref
        )
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error(command, "parameter_optimization_lookup_failed", str(exc), read_only=True)
    return success_envelope(
        command=command,
        side_effect=SideEffect.READ_ONLY,
        data={"parameter_optimization_run": run, "trials": trials},
        artifacts={
            "parameter_optimization_run": ArtifactReference(
                artifact_type=PARAMETER_OPTIMIZATION_RUN,
                uri=f"research://postgres/{PARAMETER_OPTIMIZATION_RUN}/{run['optimization_run_id']}",
                metadata={"status": run.get("status"), "trial_count": len(trials)},
            ).to_dict()
        },
    )


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
            blockers = _constraint_blockers(plan.get("constraints") or [], observation)
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


def _allowed_tunable_paths(store: ResearchArtifactStore, base: Mapping[str, Any]) -> set[str]:
    strategy, _ = load_passed_strategy_specification(store, str(base["strategy_specification_validation_id"]))
    paths = set(str(item) for item in strategy.get("tunable_fields", []))
    if base.get("risk_stack_specification_validation_id"):
        risk, _ = load_passed_risk_stack_specification(
            store, str(base["risk_stack_specification_validation_id"])
        )
        for row in risk.get("risk_managers", []):
            paths.update(str(item) for item in row.get("tunable_fields", []))
    return paths


def _plan_identity(plan: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "base_backtest_specification_id",
        "base_backtest_specification_validation_id",
        "selection_dataset_hash",
        "holdout_dataset",
        "holdout_data_quality",
        "objective_implementation_version_id",
        "objective_validation_id",
        "objective_source_hash",
        "search_space",
        "direction",
        "constraints",
        "seed",
        "max_trials",
        "resource_limits",
        "parent_plan_ref",
        "variant_reason",
    )
    return {key: plan.get(key) for key in keys}


def _validate_search_space(
    search_space: Sequence[Mapping[str, Any]],
    allowed_paths: set[str],
) -> list[dict[str, Any]]:
    if not search_space:
        raise ValueError("search_space must contain at least one explicitly tunable dimension")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dimension in search_space:
        row = dict(dimension)
        path = str(row.get("path") or "").strip()
        if path in seen:
            raise ValueError(f"duplicate search-space path: {path}")
        if path not in allowed_paths:
            raise ValueError(f"search-space path is not explicitly tunable: {path}")
        if path.startswith("/assumptions/") or any(token in path for token in ("dataset", "holdout", "implementation")):
            raise ValueError(f"experimental assumption cannot be optimized: {path}")
        dimension_values(row)
        seen.add(path)
        normalized.append(row)
    return sorted(normalized, key=lambda item: str(item["path"]))


def _validate_holdout(selection: Mapping[str, Any], holdout: Mapping[str, Any]) -> None:
    for key in ("symbols", "asset_class", "timeframe"):
        if selection[key] != holdout[key]:
            raise ValueError(f"holdout dataset {key} must match selection dataset")
    selection_end = parse_datetime(selection["time_range"]["end"], "selection.end")
    holdout_start = parse_datetime(holdout["time_range"]["start"], "holdout.start")
    if holdout_start <= selection_end:
        raise ValueError("holdout dataset must begin strictly after the selection dataset ends")


def _validate_constraints(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for value in values:
        row = dict(value)
        if str(row.get("metric") or "").strip() == "":
            raise ValueError("constraint.metric is required")
        if row.get("operator") not in {"lt", "lte", "gt", "gte", "eq"}:
            raise ValueError("constraint.operator must be lt, lte, gt, gte, or eq")
        if isinstance(row.get("value"), bool) or not isinstance(row.get("value"), (int, float)):
            raise ValueError("constraint.value must be numeric")
        normalized.append(row)
    return normalized


def _validate_resource_limits(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"max_trial_attempts", "per_trial_timeout_seconds", "max_concurrent_trials"}
    unknown = sorted(set(value).difference(allowed))
    if unknown:
        raise ValueError(f"unsupported optimization resource limits: {unknown}")
    attempts = value.get("max_trial_attempts", 1)
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 3:
        raise ValueError("resource_limits.max_trial_attempts must be between 1 and 3")
    concurrency = value.get("max_concurrent_trials", 1)
    if concurrency != 1:
        raise ValueError("v1 optimization execution requires max_concurrent_trials=1")
    timeout = value.get("per_trial_timeout_seconds")
    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0):
        raise ValueError("resource_limits.per_trial_timeout_seconds must be positive")
    return {
        "max_trial_attempts": attempts,
        "max_concurrent_trials": 1,
        "per_trial_timeout_seconds": float(timeout) if timeout is not None else None,
    }


def _execute_trial(
    executor: OptimizationTrialExecutor,
    *,
    plan: Mapping[str, Any],
    parameters: Mapping[str, Any],
    trial_id: str,
    optimization_run_id: str,
    max_attempts: int,
) -> tuple[TrialExecution, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    execution = TrialExecution(status="blocked", observation=None, blockers=("trial was not executed",))
    for attempt in range(1, max_attempts + 1):
        exception: str | None = None
        try:
            execution = executor.execute(
                plan=plan,
                parameters=parameters,
                trial_id=trial_id,
                optimization_run_id=optimization_run_id,
            )
        except Exception as exc:
            exception = f"{type(exc).__name__}: {exc}"
            execution = TrialExecution(status="blocked", observation=None, blockers=(exception,))
        attempts.append(
            {
                "attempt": attempt,
                "status": execution.status,
                "child_refs": dict(execution.child_refs),
                "warnings": list(execution.warnings),
                "blockers": list(execution.blockers),
                "exception": exception,
            }
        )
        if execution.status == "passed":
            break
    return execution, attempts


def _constraint_blockers(constraints: Sequence[Mapping[str, Any]], observation: Mapping[str, Any]) -> list[str]:
    metrics = dict(observation.get("metrics") or {})
    blockers: list[str] = []
    operations = {
        "lt": lambda actual, expected: actual < expected,
        "lte": lambda actual, expected: actual <= expected,
        "gt": lambda actual, expected: actual > expected,
        "gte": lambda actual, expected: actual >= expected,
        "eq": lambda actual, expected: actual == expected,
    }
    for constraint in constraints:
        name = str(constraint["metric"])
        actual = metrics.get(name)
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            blockers.append(f"constraint metric is unavailable: {name}")
            continue
        if not operations[str(constraint["operator"])](float(actual), float(constraint["value"])):
            blockers.append(f"constraint failed: {name} {constraint['operator']} {constraint['value']}")
    return blockers


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


def _positive(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("max_new_trials must be a positive integer")
    return value


def _error(command: str, code: str, message: str, *, read_only: bool = False) -> ToolEnvelope:
    return error_envelope(
        command=command,
        side_effect=SideEffect.READ_ONLY if read_only else SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
    )
