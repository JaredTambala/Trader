"""Run or resume sequential single-objective optimization studies.

The orchestrator reconciles an engine session with canonical trial artifacts,
executes a bounded number of new suggestions, and persists every accepted
observation before advancing. Existing ledger content is authoritative on
resume; conflicts, drift, or incomplete trial evidence fail closed.
"""

from __future__ import annotations

from typing import Any, Mapping

from trader_research.foundation import ApplicationResult, error_result, stable_research_id, success_result
from trader_research.foundation.artifacts import ResearchArtifactStore, ResearchArtifactStoreError, SCHEMA_VERSION
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
)
from trader_research.experiments.implementations import evaluate_objective

from .commands import RESEARCH_RUN_PARAMETER_OPTIMIZATION
from .contracts import OptimizationOutcome, OptimizationTrialExecutor, TrialExecution
from .engines import OptimizationEngineRegistry
from .ledger import (
    _run_trials,
    _select_trial,
    _validate_trials,
    load_validated_parameter_optimization_plan,
)
from .validation import constraint_blockers


def run_parameter_optimization(
    *,
    optimization_plan_ref: str,
    optimizer_profile: str,
    trial_executor: OptimizationTrialExecutor,
    artifact_store: ResearchArtifactStore | None,
    engine_registry: OptimizationEngineRegistry | None = None,
    max_new_trials: int | None = None,
) -> ApplicationResult:
    """Run or resume one canonical sequential single-objective study.

    The plan is revalidated before the selected engine starts. Existing canonical
    trials are replayed into the ask/tell session in ledger order; only missing
    suggestions are executed, and each trial is persisted before its outcome is
    told to the engine. ``max_new_trials`` may bound work for one invocation but
    never changes the plan's total trial budget.

    Returns:
        A result containing the reconciled run and trial ledger. Provider,
        executor, ledger, or persistence conflicts are returned as structured
        failures without accepting partial in-memory state as evidence.
    """
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
                timeout_seconds=(plan.get("resource_limits") or {}).get(
                    "per_trial_timeout_seconds"
                ),
            )
            value = None
            diagnostics: Mapping[str, Any] = {}
            blockers = list(execution.blockers)
            status = execution.status
            if status == "passed" and execution.observation is not None:
                blockers.extend(
                    constraint_blockers(
                        plan.get("constraints") or [], execution.observation
                    )
                )
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
                domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_TRIAL],
                producer_tool=RESEARCH_RUN_PARAMETER_OPTIMIZATION,
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
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_RUN],
            producer_tool=RESEARCH_RUN_PARAMETER_OPTIMIZATION,
            artifact_type=PARAMETER_OPTIMIZATION_RUN,
            artifact_id=run_id,
            payload=payload,
            status=status,
            metadata={"optimization_plan_id": plan["optimization_plan_id"], "engine_profile": profile.profile_name},
        )
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error(command, "parameter_optimization_run_failed", str(exc))
    result = success_result(
        command=command,
        data={"parameter_optimization_run": payload, "new_trials": new_trials},
        artifacts={"parameter_optimization_run": record.reference().to_dict()},
    )
    if status != "blocked":
        return result
    return ApplicationResult(
        ok=False,
        operation=command,
        data=result.data,
        artifacts=result.artifacts,
        errors=({"code": "parameter_optimization_blocked", "message": payload["blockers"][0]},),
    )


def _execute_trial(
    executor: OptimizationTrialExecutor,
    *,
    plan: Mapping[str, Any],
    parameters: Mapping[str, Any],
    trial_id: str,
    optimization_run_id: str,
    max_attempts: int,
    timeout_seconds: float | None,
) -> tuple[TrialExecution, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    execution = TrialExecution(status="blocked", observation=None, blockers=("trial was not executed",))
    for attempt in range(1, max_attempts + 1):
        exception: str | None = None
        try:
            if timeout_seconds is None:
                execution = executor.execute(
                    plan=plan,
                    parameters=parameters,
                    trial_id=trial_id,
                    optimization_run_id=optimization_run_id,
                )
            else:
                execute_with_timeout = getattr(executor, "execute_with_timeout", None)
                if not callable(execute_with_timeout):
                    execution = TrialExecution(
                        status="blocked",
                        observation=None,
                        blockers=(
                            "trial executor cannot enforce per_trial_timeout_seconds",
                        ),
                    )
                else:
                    execution = execute_with_timeout(
                        plan=plan,
                        parameters=parameters,
                        trial_id=trial_id,
                        optimization_run_id=optimization_run_id,
                        timeout_seconds=float(timeout_seconds),
                    )
        except Exception as exc:
            exception = _bounded_text(f"{type(exc).__name__}: {exc}")
            execution = TrialExecution(status="blocked", observation=None, blockers=(exception,))
        execution = TrialExecution(
            status=execution.status,
            observation=execution.observation,
            child_refs=execution.child_refs,
            warnings=_bounded_messages(execution.warnings),
            blockers=_bounded_messages(execution.blockers),
        )
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


def _bounded_messages(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_bounded_text(str(value)) for value in values[:25])


def _bounded_text(value: str, *, limit: int = 2_000) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - len("...[truncated]")] + "...[truncated]"


def _positive(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("max_new_trials must be a positive integer")
    return value


def _error(command: str, code: str, message: str) -> ApplicationResult:
    return error_result(
        command=command,
        code=code,
        message=message,
    )
