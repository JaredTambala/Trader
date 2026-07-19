"""Supervisor execution of immutable Adversarial optimization variants."""

from __future__ import annotations

from typing import Any, Mapping

from trader_research.artifact_store import ResearchArtifactStore, ResearchArtifactStoreError, load_artifact_ref
from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import (
    PARAMETER_OPTIMIZATION_AUDIT_PLAN,
    PARAMETER_OPTIMIZATION_RUN,
)

from .contracts import OptimizationTrialExecutor
from .engines import OptimizationEngineRegistry
from .services import (
    RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS,
    create_parameter_optimization_plan,
    load_validated_parameter_optimization_plan,
    load_validated_parameter_optimization_run,
    run_parameter_optimization,
)


def required_optimizer_profiles_for_variants(
    *,
    audit_plan_ref: str,
    artifact_store: ResearchArtifactStore,
) -> tuple[str, ...]:
    """Return the distinct optimizer profiles an audit plan asks the Supervisor to execute."""
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
) -> ToolEnvelope:
    """Execute only optimization-variant requests declared by an Adversarial audit plan."""
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
            child_plan = _envelope_data(created, "parameter_optimization_plan")
            run = run_parameter_optimization(
                optimization_plan_ref=str(child_plan["optimization_plan_id"]),
                optimizer_profile=profile,
                trial_executor=trial_executor,
                artifact_store=artifact_store,
                engine_registry=registry,
            )
            variants.append(_envelope_data(run, "parameter_optimization_run"))
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error("parameter_optimization_variants_failed", str(exc))
    return success_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
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


def _envelope_data(envelope: ToolEnvelope, key: str) -> Mapping[str, Any]:
    if not envelope.ok:
        message = envelope.errors[0]["message"] if envelope.errors else f"{envelope.command} failed"
        raise ValueError(str(message))
    value = envelope.data.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{envelope.command} did not return {key}")
    return value


def _error(code: str, message: str) -> ToolEnvelope:
    return error_envelope(
        command=RESEARCH_RUN_PARAMETER_OPTIMIZATION_VARIANTS,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
    )
