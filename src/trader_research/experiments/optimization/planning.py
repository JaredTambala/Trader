"""Construct immutable, provider-neutral parameter optimization plans.

Planning seals the base specification, holdout Data evidence, objective,
search dimensions, constraints, seed, and resource limits. It validates this
closed decision surface before persisting an Experiments-owned plan artifact.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from trader_research.foundation import ApplicationResult, error_result, stable_research_id, success_result
from trader_research.foundation.artifacts import ResearchArtifactStore, ResearchArtifactStoreError, SCHEMA_VERSION
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    PARAMETER_OPTIMIZATION_PLAN,
)
from trader_research.experiments.implementations import load_passed_implementation
from trader_research.experiments.specifications import (
    load_passed_backtest_specification,
    load_passed_risk_stack_specification,
    load_passed_strategy_specification,
)
from trader_research.experiments.specifications.common import (
    artifact_snapshot,
    normalized_dataset_manifest,
    parse_datetime,
    validate_quality_report,
)

from .commands import RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN, RESEARCH_GET_OPTIMIZER_RUNTIME
from .engines import OptimizationEngineRegistry, dimension_values


def get_optimizer_runtime(*, engine_registry: OptimizationEngineRegistry | None = None) -> ApplicationResult:
    """Return deterministic non-secret profiles for configured optimizers.

    The registry is inspected without starting an engine session or creating
    provider storage. Unavailable profiles remain visible with their reason.
    """
    registry = engine_registry or OptimizationEngineRegistry()
    return success_result(
        command=RESEARCH_GET_OPTIMIZER_RUNTIME,
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
) -> ApplicationResult:
    """Create a provider-neutral plan over explicitly tunable parameters.

    The function requires passed base and objective validations, verifies that
    holdout Data is distinct and fit, restricts search dimensions to declared
    tunable paths, and normalizes direction, constraints, seed, budget, and
    resource limits. Every selection and holdout input is snapshotted into the
    content-derived plan identity.

    Returns:
        A result containing the persisted immutable plan and canonical reference,
        or a structured validation or persistence failure.
    """
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
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_PLAN],
            producer_tool=RESEARCH_CREATE_PARAMETER_OPTIMIZATION_PLAN,
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
    return success_result(
        command=command,
        data={"parameter_optimization_plan": payload},
        artifacts={"parameter_optimization_plan": record.reference().to_dict()},
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


def _error(command: str, code: str, message: str) -> ApplicationResult:
    return error_result(
        command=command,
        code=code,
        message=message,
    )
