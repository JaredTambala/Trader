"""Canonical parameter-optimization plans, runs, trials, and result lookup."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from trader_research.artifact_store import ResearchArtifactStore, ResearchArtifactStoreError, load_artifact_ref
from trader_research.contracts import ArtifactReference, SCHEMA_VERSION, SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import (
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
        plan = load_artifact_ref(artifact_store, PARAMETER_OPTIMIZATION_PLAN, optimization_plan_ref)
        if plan.get("status") != "created" or plan.get("artifact_type") != PARAMETER_OPTIMIZATION_PLAN:
            raise ValueError("optimization plan must be a created parameter_optimization_plan")
        if stable_research_id("parameter_optimization_plan", _plan_identity(plan)) != plan.get(
            "optimization_plan_id"
        ):
            raise ValueError("optimization plan ID does not match its canonical content")
        base, base_validation = load_passed_backtest_specification(
            artifact_store, str(plan["base_backtest_specification_validation_id"])
        )
        if base.get("backtest_specification_id") != plan.get("base_backtest_specification_id"):
            raise ValueError("base backtest specification identity drifted after planning")
        if base_validation.get("validation_id") != plan.get("base_backtest_specification_validation_id"):
            raise ValueError("base backtest specification validation drifted after planning")
        if (base.get("dataset") or {}).get("sha256") != plan.get("selection_dataset_hash"):
            raise ValueError("selection dataset snapshot drifted after planning")
        objective, objective_validation = load_passed_implementation(
            artifact_store, str(plan["objective_validation_id"]), expected_kind="optimization_objective"
        )
        if objective.source_hash != plan.get("objective_source_hash"):
            raise ValueError("optimization objective source hash drifted after planning")
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
        run = load_artifact_ref(artifact_store, PARAMETER_OPTIMIZATION_RUN, optimization_run_ref)
        trials = _run_trials(artifact_store, str(run["optimization_run_id"]))
    except (KeyError, ResearchArtifactStoreError) as exc:
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
    return sorted(
        [
            record.payload
            for record in store.list_artifacts(artifact_type=PARAMETER_OPTIMIZATION_TRIAL)
            if record.payload.get("optimization_run_id") == run_id
        ],
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
