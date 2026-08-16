"""Execute immutable optimization variants requested by Adversarial review.

Variant services load an approved audit plan, derive only its declared child
plans, and run them through the normal optimizer. They preserve the baseline
selection and return canonical variant refs for independent judgment.
"""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result, success_result

from typing import Any, Mapping

from trader_research.foundation.artifacts import ResearchArtifactStore, ResearchArtifactStoreError, load_artifact_ref
from trader_research.governance.artifacts import (
    PARAMETER_OPTIMIZATION_AUDIT_PLAN,
    PARAMETER_OPTIMIZATION_RUN,
)

from .contracts import OptimizationTrialExecutor
from .commands import RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS
from .engines import OptimizationEngineRegistry
from .ledger import (
    load_validated_parameter_optimization_plan,
    load_validated_parameter_optimization_run,
)
from .orchestration import run_parameter_optimization
from .planning import create_parameter_optimization_plan


def required_optimizer_profiles_for_variants(
    *,
    audit_plan_ref: str,
    artifact_store: ResearchArtifactStore,
) -> tuple[str, ...]:
    """Resolve optimizer profiles required by an Adversarial audit plan.

    Only attacks whose evidence kind is ``optimization_variant`` contribute a
    profile. Each may override the baseline run's profile; duplicate names are
    removed and the result is sorted for deterministic provider setup.

    Returns:
        The exact non-empty or empty profile set requested by executable variants.
    """
    audit = load_artifact_ref(artifact_store, PARAMETER_OPTIMIZATION_AUDIT_PLAN, audit_plan_ref)
    baseline_run = load_artifact_ref(
        artifact_store,
        PARAMETER_OPTIMIZATION_RUN,
        str(audit["baseline_optimization_run_id"]),
    )
    baseline_profile = str((baseline_run.get("engine_profile") or {}).get("profile_name") or "builtin_random")
    profiles: set[str] = set()
    for attack in audit.get("attacks", []):
        if attack.get("evidence_kind") != "optimization_variant":
            continue
        configuration = dict(attack.get("configuration") or {})
        profiles.add(str(configuration.get("optimizer_profile") or baseline_profile))
    return tuple(sorted(profiles))


def run_parameter_optimization_variants(
    *,
    audit_plan_ref: str,
    trial_executor: OptimizationTrialExecutor,
    artifact_store: ResearchArtifactStore | None,
    engine_registry: OptimizationEngineRegistry | None = None,
) -> ApplicationResult:
    """Execute optimization variants declared by an Adversarial audit plan.

    Baseline run and plan evidence are revalidated first. Each executable attack
    derives a child plan that changes only its declared seed, budget, search
    space, objective, or provider, then uses the ordinary optimization service.
    Other evidence kinds are reported as skipped for separate execution.

    Returns:
        A result containing canonical variant runs and skipped attacks, or a
        structured failure if the plan, variant configuration, execution, or
        persistence cannot be validated.
    """
    command = RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS
    if artifact_store is None:
        return _error("research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        audit = load_artifact_ref(artifact_store, PARAMETER_OPTIMIZATION_AUDIT_PLAN, audit_plan_ref)
        baseline_run, _ = load_validated_parameter_optimization_run(
            artifact_store, str(audit["baseline_optimization_run_id"])
        )
        baseline_plan, _, _ = load_validated_parameter_optimization_plan(
            artifact_store, str(audit["baseline_optimization_plan_id"])
        )
        registry = engine_registry or OptimizationEngineRegistry()
        baseline_profile = str((baseline_run.get("engine_profile") or {}).get("profile_name") or "builtin_random")
        variants: list[Mapping[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for attack in audit.get("attacks", []):
            if attack.get("evidence_kind") != "optimization_variant":
                skipped.append({"attack_type": attack.get("attack_type"), "reason": "requires separate evidence kind"})
                continue
            attack_type = str(attack["attack_type"])
            configuration = dict(attack.get("configuration") or {})
            seed, max_trials, search_space, objective_ref, profile = _variant_configuration(
                attack_type,
                configuration,
                baseline_plan,
                baseline_profile,
            )
            created = create_parameter_optimization_plan(
                base_backtest_specification_validation_ref=str(
                    baseline_plan["base_backtest_specification_validation_id"]
                ),
                holdout_dataset_manifest=dict(baseline_plan["holdout_dataset"]["payload"]),
                holdout_data_quality_report=dict(baseline_plan["holdout_data_quality"]["payload"]),
                objective_validation_ref=objective_ref,
                search_space=search_space,
                direction=str(baseline_plan["direction"]),
                constraints=list(baseline_plan.get("constraints") or []),
                seed=seed,
                max_trials=max_trials,
                resource_limits=dict(baseline_plan.get("resource_limits") or {}),
                parent_plan_ref=str(baseline_plan["optimization_plan_id"]),
                variant_reason=attack_type,
                artifact_store=artifact_store,
            )
            child_plan = _result_data(created, "parameter_optimization_plan")
            run = run_parameter_optimization(
                optimization_plan_ref=str(child_plan["optimization_plan_id"]),
                optimizer_profile=profile,
                trial_executor=trial_executor,
                artifact_store=artifact_store,
                engine_registry=registry,
            )
            variants.append(_result_data(run, "parameter_optimization_run"))
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error("parameter_optimization_variants_failed", str(exc))
    return success_result(
        command=command,
        data={"variant_optimization_runs": variants, "skipped_attacks": skipped},
        artifacts={
            "variant_optimization_runs": [
                {
                    "artifact_type": PARAMETER_OPTIMIZATION_RUN,
                    "uri": f"research://postgres/{PARAMETER_OPTIMIZATION_RUN}/{item['optimization_run_id']}",
                    "metadata": {"status": item.get("status")},
                }
                for item in variants
            ]
        },
    )


def _variant_configuration(
    attack_type: str,
    configuration: Mapping[str, Any],
    baseline_plan: Mapping[str, Any],
    baseline_profile: str,
) -> tuple[int, int, list[Mapping[str, Any]], str, str]:
    seed = int(configuration.get("seed", baseline_plan["seed"]))
    max_trials = int(configuration.get("max_trials", baseline_plan["max_trials"]))
    search_space = list(configuration.get("search_space") or baseline_plan["search_space"])
    objective_ref = str(configuration.get("objective_validation_ref") or baseline_plan["objective_validation_id"])
    profile = str(configuration.get("optimizer_profile") or baseline_profile)
    if attack_type == "seed_sensitivity" and "seed" not in configuration:
        seed += 1
    elif attack_type == "budget_sensitivity" and "max_trials" not in configuration:
        max_trials = max(1, max_trials // 2)
    elif attack_type == "provider_sensitivity" and "optimizer_profile" not in configuration:
        raise ValueError("provider_sensitivity requires configuration.optimizer_profile")
    elif attack_type in {"search_boundary_sensitivity", "neighbor_parameter_sensitivity"} and "search_space" not in configuration:
        raise ValueError(f"{attack_type} requires configuration.search_space")
    elif attack_type == "objective_sensitivity" and "objective_validation_ref" not in configuration:
        raise ValueError("objective_sensitivity requires configuration.objective_validation_ref")
    return seed, max_trials, search_space, objective_ref, profile


def _result_data(result: ApplicationResult, key: str) -> Mapping[str, Any]:
    if not result.ok:
        message = result.errors[0]["message"] if result.errors else f"{result.operation} failed"
        raise ValueError(str(message))
    value = result.data.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{result.operation} did not return {key}")
    return value


def _error(code: str, message: str) -> ApplicationResult:
    return error_result(
        command=RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS,
        code=code,
        message=message,
    )
