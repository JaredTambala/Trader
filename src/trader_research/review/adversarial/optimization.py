"""Plan and judge attacks on parameter-optimization procedures.

Audit plans pin a canonical baseline and declare immutable variant requests.
Judgment consumes only the supplied canonical variant and stress evidence,
reports sensitivity, and never changes the baseline selection or reruns trials.
"""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result, success_result
from trader_research.foundation.artifacts import SCHEMA_VERSION

from typing import Any, Mapping, Sequence

from trader_research.foundation.artifacts import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    load_artifact_ref,
)
from trader_research.foundation import json_payload_hash
from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    PARAMETER_OPTIMIZATION_AUDIT_PLAN,
    PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
)
from trader_research.experiments.reads import (
    ExperimentEvidenceReader,
    StoreBackedExperimentEvidenceReader,
)


ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN = "adversarial_create_parameter_optimization_audit_plan"
ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT = "adversarial_generate_parameter_optimization_audit"

_ATTACK_EVIDENCE_KIND = {
    "seed_sensitivity": "optimization_variant",
    "provider_sensitivity": "optimization_variant",
    "budget_sensitivity": "optimization_variant",
    "search_boundary_sensitivity": "optimization_variant",
    "objective_sensitivity": "optimization_variant",
    "neighbor_parameter_sensitivity": "optimization_variant",
    "cost_sensitivity": "backtest_stress",
    "data_window_sensitivity": "backtest_stress",
    "concentration": "ledger_analysis",
    "multiple_testing": "ledger_analysis",
}


def create_parameter_optimization_audit_plan(
    *,
    optimization_run_ref: str,
    attacks: Sequence[Mapping[str, Any]] | None = None,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Declare immutable attacks against one validated optimization baseline.

    The baseline run and plan are revalidated, attack types and configurations are
    normalized, and each request is classified by the separate evidence it needs.
    The content-addressed Review-owned plan references but never changes baseline
    trials, selected parameters, data, costs, or objective.

    Returns:
        A result containing the persisted audit plan and canonical reference, or
        a structured baseline, attack-contract, or persistence failure.
    """
    command = ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        evidence_reader = StoreBackedExperimentEvidenceReader(artifact_store)
        baseline, _ = evidence_reader.load_parameter_optimization_run(
            optimization_run_ref
        )
        if baseline.get("status") != "completed" or not baseline.get("selected_trial_id"):
            raise ValueError("baseline optimization run must be completed with a selected trial")
        normalized = _normalize_attacks(attacks)
        plan_id = stable_research_id(
            "parameter_optimization_audit_plan",
            {
                "baseline_optimization_run_id": baseline["optimization_run_id"],
                "baseline_digest": json_payload_hash(baseline),
                "attacks": normalized,
            },
        )
        payload = {
            "artifact_type": PARAMETER_OPTIMIZATION_AUDIT_PLAN,
            "schema_version": SCHEMA_VERSION,
            "audit_plan_id": plan_id,
            "baseline_optimization_run_id": baseline["optimization_run_id"],
            "baseline_optimization_plan_id": baseline["optimization_plan_id"],
            "baseline_digest": json_payload_hash(baseline),
            "selected_trial_id": baseline["selected_trial_id"],
            "selected_parameters": baseline["selected_parameters"],
            "attacks": normalized,
            "status": "created",
        }
        record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_AUDIT_PLAN],
            producer_tool=ADVERSARIAL_CREATE_PARAMETER_OPTIMIZATION_AUDIT_PLAN,
            artifact_type=PARAMETER_OPTIMIZATION_AUDIT_PLAN,
            artifact_id=plan_id,
            payload=payload,
            status="created",
            metadata={"baseline_optimization_run_id": baseline["optimization_run_id"]},
        )
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error(command, "parameter_optimization_audit_plan_failed", str(exc))
    return success_result(
        command=command,
        data={"parameter_optimization_audit_plan": payload},
        artifacts={"parameter_optimization_audit_plan": record.reference().to_dict()},
    )


def generate_parameter_optimization_audit(
    *,
    audit_plan_ref: str,
    variant_optimization_run_refs: Sequence[str] | None = None,
    stress_backtest_run_refs: Sequence[str] | None = None,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Judge supplied variant evidence against an immutable baseline selection.

    The audit plan and baseline are revalidated, every supplied optimization or
    stress run must match a declared attack and required lineage, and sensitivity
    findings are derived without executing new work. Missing required evidence is
    retained as a blocker in the Review-owned robustness report.

    Returns:
        A result containing the canonical robustness report and reference.
        ``ok`` is false when the review is blocked or evidence cannot be resolved
        or persisted.
    """
    command = ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        evidence_reader = StoreBackedExperimentEvidenceReader(artifact_store)
        plan = load_artifact_ref(artifact_store, PARAMETER_OPTIMIZATION_AUDIT_PLAN, audit_plan_ref)
        baseline, baseline_trials = evidence_reader.load_parameter_optimization_run(
            str(plan["baseline_optimization_run_id"])
        )
        if json_payload_hash(baseline) != plan.get("baseline_digest"):
            raise ValueError("baseline optimization run changed after the audit plan was created")
        variants = [
            evidence_reader.load_parameter_optimization_run(ref)[0]
            for ref in (variant_optimization_run_refs or ())
        ]
        stresses = [
            evidence_reader.load_backtest_run(ref)
            for ref in (stress_backtest_run_refs or ())
        ]
        coverage, findings, blockers, warnings = _audit_evidence(
            evidence_reader,
            plan,
            baseline,
            baseline_trials,
            variants,
            stresses,
        )
        status = "passed" if not blockers else "blocked"
        identity = {
            "audit_plan_id": plan["audit_plan_id"],
            "baseline_optimization_run_id": baseline["optimization_run_id"],
            "variant_run_ids": sorted(str(item["optimization_run_id"]) for item in variants),
            "stress_run_ids": sorted(str(item["run_id"]) for item in stresses),
            "blockers": blockers,
        }
        report_id = stable_research_id("parameter_optimization_robustness", identity)
        report = {
            "artifact_type": PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
            "schema_version": SCHEMA_VERSION,
            "report_id": report_id,
            **identity,
            "status": status,
            "valid": not blockers,
            "baseline_selected_trial_id": baseline["selected_trial_id"],
            "baseline_selected_parameters": baseline["selected_parameters"],
            "coverage": coverage,
            "findings": findings,
            "warnings": warnings,
        }
        record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT],
            producer_tool=ADVERSARIAL_GENERATE_PARAMETER_OPTIMIZATION_AUDIT,
            artifact_type=PARAMETER_OPTIMIZATION_ROBUSTNESS_REPORT,
            artifact_id=report_id,
            payload=report,
            status=status,
            metadata={"baseline_optimization_run_id": baseline["optimization_run_id"]},
        )
    except (ValueError, KeyError, ResearchArtifactStoreError) as exc:
        return _error(command, "parameter_optimization_audit_failed", str(exc))
    result = success_result(
        command=command,
        data={"parameter_optimization_robustness_report": report},
        artifacts={"parameter_optimization_robustness_report": record.reference().to_dict()},
        warnings=tuple(warnings),
    )
    if status == "passed":
        return result
    return ApplicationResult(
        ok=False,
        operation=command,
        data=result.data,
        artifacts=result.artifacts,
        warnings=result.warnings,
        errors=({"code": "parameter_optimization_audit_blocked", "message": blockers[0]},),
    )


def _normalize_attacks(attacks: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    values = attacks or tuple({"attack_type": name} for name in _ATTACK_EVIDENCE_KIND)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        attack_type = str(value.get("attack_type") or "").strip()
        if attack_type not in _ATTACK_EVIDENCE_KIND:
            raise ValueError(f"unsupported optimization attack_type: {attack_type}")
        if attack_type in seen:
            raise ValueError(f"duplicate optimization attack_type: {attack_type}")
        seen.add(attack_type)
        normalized.append(
            {
                "attack_type": attack_type,
                "evidence_kind": _ATTACK_EVIDENCE_KIND[attack_type],
                "configuration": dict(value.get("configuration") or {}),
            }
        )
    if not normalized:
        raise ValueError("attacks must contain at least one attack")
    return sorted(normalized, key=lambda item: item["attack_type"])


def _audit_evidence(
    evidence_reader: ExperimentEvidenceReader,
    plan: Mapping[str, Any],
    baseline: Mapping[str, Any],
    baseline_trials: Sequence[Mapping[str, Any]],
    variants: Sequence[Mapping[str, Any]],
    stresses: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    coverage: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    variant_by_reason: dict[str, list[Mapping[str, Any]]] = {}
    for variant in variants:
        child_plan = evidence_reader.load_parameter_optimization_plan(
            str(variant["optimization_plan_id"])
        )
        if child_plan.get("parent_plan_ref") != baseline.get("optimization_plan_id"):
            raise ValueError("optimization variant does not descend from the baseline plan")
        variant_by_reason.setdefault(str(child_plan.get("variant_reason") or ""), []).append(variant)
    stresses_by_reason: dict[str, list[Mapping[str, Any]]] = {}
    for stress in stresses:
        stresses_by_reason.setdefault(str(stress.get("variant_reason") or ""), []).append(stress)

    for attack in plan["attacks"]:
        attack_type = str(attack["attack_type"])
        evidence_kind = str(attack["evidence_kind"])
        if evidence_kind == "optimization_variant":
            evidence = variant_by_reason.get(attack_type, [])
            covered = bool(evidence)
            if covered:
                unstable = [
                    item["optimization_run_id"]
                    for item in evidence
                    if item.get("status") != "completed"
                    or item.get("selected_parameters") != baseline.get("selected_parameters")
                ]
                findings.append(
                    {
                        "attack_type": attack_type,
                        "variant_run_ids": [item["optimization_run_id"] for item in evidence],
                        "selection_instability_run_ids": unstable,
                    }
                )
                if unstable:
                    blockers.append(f"{attack_type} changed or failed to reproduce the selected configuration")
            else:
                blockers.append(f"missing required optimization variant evidence: {attack_type}")
        elif evidence_kind == "backtest_stress":
            evidence = stresses_by_reason.get(attack_type, [])
            covered = bool(evidence)
            if covered:
                failed = [item["run_id"] for item in evidence if item.get("status") != "passed"]
                findings.append({"attack_type": attack_type, "stress_run_ids": [item["run_id"] for item in evidence], "failed_run_ids": failed})
                if failed:
                    blockers.append(f"{attack_type} contains blocked stress runs")
            else:
                blockers.append(f"missing required backtest stress evidence: {attack_type}")
        else:
            covered = True
            if attack_type == "multiple_testing":
                trial_count = int(baseline.get("trial_count") or 0)
                findings.append({"attack_type": attack_type, "trial_count": trial_count, "selection_count": 1})
                if trial_count > 100:
                    warnings.append("More than 100 candidates were searched; multiple-testing evidence should be strengthened.")
            elif attack_type == "concentration":
                trial_id = str(baseline["selected_trial_id"])
                selected_trial = next(
                    (
                        trial
                        for trial in baseline_trials
                        if str(trial.get("trial_id")) == trial_id
                    ),
                    None,
                )
                if selected_trial is None:
                    raise ValueError("selected optimization trial is absent from its ledger")
                concentration = (selected_trial.get("observation") or {}).get("exposure", {}).get("final_concentration")
                findings.append({"attack_type": attack_type, "final_concentration": concentration})
                if isinstance(concentration, (int, float)) and concentration > 0.5:
                    blockers.append("selected trial final concentration exceeds 50 percent")
        coverage.append({"attack_type": attack_type, "evidence_kind": evidence_kind, "covered": covered})
    return coverage, findings, blockers, warnings


def _error(command: str, code: str, message: str) -> ApplicationResult:
    return error_result(command=command, code=code, message=message)
