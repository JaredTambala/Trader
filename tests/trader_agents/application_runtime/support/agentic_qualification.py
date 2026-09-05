"""Contracts and persistence helpers for Agent application qualification.

The module normalizes public scenario results, fixture identities, and retained
acceptance evidence without granting authority to the evaluated model.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from trader_agents.model_runtime.profiles import DEVELOPMENT_MODEL_PROFILE_ID
from trader_agents.application.runtime import runtime_manifest
from trader_research.coding.domain import validate_pinned_container_image
from trader_research.foundation import json_payload_hash


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
AGENTIC_EVALUATION_FIXTURE = (
    REPOSITORY_ROOT
    / "tests"
    / "trader_agents"
    / "contracts_state"
    / "fixtures"
    / "agentic_slice_scenarios.json"
)
AGENTIC_SESSION_INPUT_FIXTURE = (
    REPOSITORY_ROOT
    / "tests"
    / "trader_agents"
    / "contracts_state"
    / "fixtures"
    / "agentic_slice_session_inputs.json"
)
_MAX_PUBLIC_ITEMS = 64
_MAX_PUBLIC_TEXT = 500
_TRACE_ID_PATTERN = re.compile(r"tr-[0-9a-f]{32}")
_RESULT_FIELDS = frozenset(
    {
        "scenario_id",
        "repetition",
        "status",
        "terminal_actions",
        "delegated_roles",
        "evidence_types",
        "evidence_refs",
        "mutations",
        "trajectory_assertions",
        "deterministic_invariants",
        "schema_valid",
        "grounded_decision",
        "required_role_coverage",
        "forbidden_tool_calls",
        "unapproved_mutations",
        "lost_canonical_receipts",
        "replayed_accepted_mutations",
        "model_calls",
        "tool_calls",
        "total_tokens",
        "duration_seconds",
        "revisions",
        "peak_concurrency",
        "trace_ids",
        "blockers",
    }
)


@dataclass(frozen=True)
class AgenticScenarioResult:
    """Bounded public evidence for one real-model scenario repetition.

    The record deliberately excludes prompts, model messages, source code,
    hidden reasoning, credentials, and complete tool payloads. Canonical refs
    and an external trace identity preserve auditability without making the
    qualification database a second product-evidence store.

    Attributes:
        scenario_id: Exact scenario identity from the frozen fixture.
        repetition: One-based repetition number.
        status: Qualification verdict for this repetition.
        terminal_actions: Coordinator terminal or interrupt action for every
            concrete session variant in this repetition.
        delegated_roles: Specialist roles actually invoked.
        evidence_types: Public evidence types returned by the trajectory.
        evidence_refs: Exact canonical evidence references.
        mutations: Named mutation classes actually attempted.
        trajectory_assertions: Fixture assertions and their audited verdicts.
        deterministic_invariants: Code-owned safety checks and verdicts.
        schema_valid: Whether all model outputs satisfied their strict schema.
        grounded_decision: Whether the terminal decision cites sufficient
            canonical evidence for the scenario.
        required_role_coverage: Fraction of required specialist roles covered.
        forbidden_tool_calls: Count of forbidden calls reaching MCP dispatch.
        unapproved_mutations: Count of mutations outside approved authority.
        lost_canonical_receipts: Count of accepted receipts missing at end.
        replayed_accepted_mutations: Count of duplicate accepted mutations.
        model_calls: Total provider calls.
        tool_calls: Total MCP calls crossing the policy boundary.
        total_tokens: Provider-reported input plus output tokens.
        duration_seconds: End-to-end wall duration.
        revisions: Coordinator and candidate revisions consumed.
        peak_concurrency: Maximum simultaneously active specialist work.
        trace_ids: Queryable redacted MLflow trace identities for all lifecycle
            invocations in this scenario repetition.
        blockers: Bounded public blockers for a failed repetition.
    """

    scenario_id: str
    repetition: int
    status: str
    terminal_actions: tuple[str, ...]
    delegated_roles: tuple[str, ...]
    evidence_types: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    mutations: tuple[str, ...]
    trajectory_assertions: Mapping[str, bool]
    deterministic_invariants: Mapping[str, bool]
    schema_valid: bool
    grounded_decision: bool
    required_role_coverage: float
    forbidden_tool_calls: int
    unapproved_mutations: int
    lost_canonical_receipts: int
    replayed_accepted_mutations: int
    model_calls: int
    tool_calls: int
    total_tokens: int
    duration_seconds: float
    revisions: int
    peak_concurrency: int
    trace_ids: tuple[str, ...]
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Reject inconsistent, unsafe, or unbounded public evidence."""
        _bounded_text(self.scenario_id, "scenario_id", limit=120)
        if self.repetition <= 0:
            raise ValueError("repetition must be positive")
        if self.status not in {"passed", "blocked"}:
            raise ValueError("status must be passed or blocked")
        _bounded_ordered_text_sequence(self.terminal_actions, "terminal_actions")
        if not self.terminal_actions:
            raise ValueError("terminal_actions must contain every session variant")
        _bounded_text_sequence(self.trace_ids, "trace_ids")
        if not self.trace_ids:
            raise ValueError("trace_ids must contain at least one lifecycle trace")
        if any(
            _TRACE_ID_PATTERN.fullmatch(trace_id) is None for trace_id in self.trace_ids
        ):
            raise ValueError("trace_ids must be public MLflow trace identities")
        for values, label in (
            (self.delegated_roles, "delegated_roles"),
            (self.evidence_types, "evidence_types"),
            (self.evidence_refs, "evidence_refs"),
            (self.mutations, "mutations"),
            (self.blockers, "blockers"),
        ):
            _bounded_text_sequence(values, label)
        _bounded_verdicts(self.trajectory_assertions, "trajectory_assertions")
        _bounded_verdicts(
            self.deterministic_invariants,
            "deterministic_invariants",
        )
        if not 0.0 <= self.required_role_coverage <= 1.0:
            raise ValueError("required_role_coverage must be between zero and one")
        for value, label in (
            (self.forbidden_tool_calls, "forbidden_tool_calls"),
            (self.unapproved_mutations, "unapproved_mutations"),
            (self.lost_canonical_receipts, "lost_canonical_receipts"),
            (self.replayed_accepted_mutations, "replayed_accepted_mutations"),
            (self.model_calls, "model_calls"),
            (self.tool_calls, "tool_calls"),
            (self.total_tokens, "total_tokens"),
            (self.revisions, "revisions"),
            (self.peak_concurrency, "peak_concurrency"),
        ):
            if value < 0:
                raise ValueError(f"{label} cannot be negative")
        if self.duration_seconds < 0.0:
            raise ValueError("duration_seconds cannot be negative")
        if self.status == "passed" and self.blockers:
            raise ValueError("a passed scenario result cannot contain blockers")
        if self.status == "blocked" and not self.blockers:
            raise ValueError("a blocked scenario result must contain blockers")

    def to_dict(self) -> dict[str, Any]:
        """Return the credential-free JSON-native result."""
        return {
            "scenario_id": self.scenario_id,
            "repetition": self.repetition,
            "status": self.status,
            "terminal_actions": list(self.terminal_actions),
            "delegated_roles": list(self.delegated_roles),
            "evidence_types": list(self.evidence_types),
            "evidence_refs": list(self.evidence_refs),
            "mutations": list(self.mutations),
            "trajectory_assertions": dict(self.trajectory_assertions),
            "deterministic_invariants": dict(self.deterministic_invariants),
            "schema_valid": self.schema_valid,
            "grounded_decision": self.grounded_decision,
            "required_role_coverage": self.required_role_coverage,
            "forbidden_tool_calls": self.forbidden_tool_calls,
            "unapproved_mutations": self.unapproved_mutations,
            "lost_canonical_receipts": self.lost_canonical_receipts,
            "replayed_accepted_mutations": self.replayed_accepted_mutations,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "total_tokens": self.total_tokens,
            "duration_seconds": self.duration_seconds,
            "revisions": self.revisions,
            "peak_concurrency": self.peak_concurrency,
            "trace_ids": list(self.trace_ids),
            "blockers": list(self.blockers),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AgenticScenarioResult":
        """Normalize one persisted JSON result into the strict contract."""
        unknown = set(payload) - _RESULT_FIELDS
        missing = _RESULT_FIELDS - set(payload)
        if unknown or missing:
            raise ValueError(
                "scenario result fields do not match the closed contract: "
                f"missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
        return cls(
            scenario_id=_required_string(payload["scenario_id"], "scenario_id"),
            repetition=_required_int(payload["repetition"], "repetition"),
            status=_required_string(payload["status"], "status"),
            terminal_actions=_string_tuple(payload["terminal_actions"]),
            delegated_roles=_string_tuple(payload.get("delegated_roles")),
            evidence_types=_string_tuple(payload.get("evidence_types")),
            evidence_refs=_string_tuple(payload.get("evidence_refs")),
            mutations=_string_tuple(payload.get("mutations")),
            trajectory_assertions=_bool_mapping(payload.get("trajectory_assertions")),
            deterministic_invariants=_bool_mapping(
                payload.get("deterministic_invariants")
            ),
            schema_valid=_required_bool(payload["schema_valid"], "schema_valid"),
            grounded_decision=_required_bool(
                payload["grounded_decision"],
                "grounded_decision",
            ),
            required_role_coverage=_required_float(
                payload["required_role_coverage"],
                "required_role_coverage",
            ),
            forbidden_tool_calls=_required_int(
                payload["forbidden_tool_calls"],
                "forbidden_tool_calls",
            ),
            unapproved_mutations=_required_int(
                payload["unapproved_mutations"],
                "unapproved_mutations",
            ),
            lost_canonical_receipts=_required_int(
                payload["lost_canonical_receipts"],
                "lost_canonical_receipts",
            ),
            replayed_accepted_mutations=_required_int(
                payload["replayed_accepted_mutations"],
                "replayed_accepted_mutations",
            ),
            model_calls=_required_int(payload["model_calls"], "model_calls"),
            tool_calls=_required_int(payload["tool_calls"], "tool_calls"),
            total_tokens=_required_int(payload["total_tokens"], "total_tokens"),
            duration_seconds=_required_float(
                payload["duration_seconds"],
                "duration_seconds",
            ),
            revisions=_required_int(payload["revisions"], "revisions"),
            peak_concurrency=_required_int(
                payload["peak_concurrency"],
                "peak_concurrency",
            ),
            trace_ids=_string_tuple(payload.get("trace_ids")),
            blockers=_string_tuple(payload.get("blockers")),
        )


def load_agentic_evaluation_contract() -> dict[str, Any]:
    """Load and minimally validate the frozen scenario contract."""
    payload = json.loads(AGENTIC_EVALUATION_FIXTURE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("agentic evaluation fixture must contain one object")
    scenarios = payload.get("scenarios")
    thresholds = payload.get("provisional_promotion_thresholds")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("agentic evaluation fixture requires scenarios")
    if not isinstance(thresholds, dict):
        raise ValueError("agentic evaluation fixture requires thresholds")
    input_fixture_id = payload.get("input_fixture_id")
    if not isinstance(input_fixture_id, str) or not input_fixture_id:
        raise ValueError("agentic evaluation fixture requires input_fixture_id")
    required_invariants = payload.get("required_deterministic_invariants")
    if not isinstance(required_invariants, list) or not required_invariants:
        raise ValueError("agentic evaluation fixture requires deterministic invariants")
    if any(not isinstance(item, str) or not item for item in required_invariants):
        raise ValueError("agentic deterministic invariants must be named strings")
    if len(set(required_invariants)) != len(required_invariants):
        raise ValueError("agentic deterministic invariants must be unique")
    scenario_ids = [str(item.get("scenario_id") or "") for item in scenarios]
    if any(not value for value in scenario_ids) or len(set(scenario_ids)) != len(
        scenario_ids
    ):
        raise ValueError("agentic scenario IDs must be non-empty and unique")
    for scenario in scenarios:
        legal_roles = _scenario_role_set(scenario, "legal_delegations")
        required_roles = _scenario_role_set(scenario, "required_delegations")
        if not required_roles.issubset(legal_roles):
            raise ValueError(
                "agentic required delegations must be a subset of legal delegations"
            )
    return payload


def load_agentic_session_input_contract() -> dict[str, Any]:
    """Load and cross-check the frozen concrete session inputs."""
    payload = json.loads(AGENTIC_SESSION_INPUT_FIXTURE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("agentic session input fixture must contain one object")
    charter = load_agentic_evaluation_contract()
    if payload.get("fixture_id") != charter["input_fixture_id"]:
        raise ValueError(
            "agentic session input fixture identity does not match charter"
        )
    if payload.get("scenario_dataset_id") != charter["dataset_id"]:
        raise ValueError("agentic session inputs belong to another scenario dataset")
    if payload.get("schema_version") != "1":
        raise ValueError("agentic session input schema_version must be 1")
    template = payload.get("session_template")
    if not isinstance(template, dict) or not template:
        raise ValueError("agentic session inputs require a session_template")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, dict):
        raise ValueError("agentic session inputs require a scenarios object")
    charter_ids = {str(item["scenario_id"]) for item in charter["scenarios"]}
    if set(scenarios) != charter_ids:
        raise ValueError("agentic session inputs must exactly cover charter scenarios")
    return payload


def agentic_evaluation_component_digests() -> dict[str, str]:
    """Return exact byte digests for both frozen evaluation components."""
    load_agentic_evaluation_contract()
    load_agentic_session_input_contract()
    return {
        "charter_sha256": hashlib.sha256(
            AGENTIC_EVALUATION_FIXTURE.read_bytes()
        ).hexdigest(),
        "session_inputs_sha256": hashlib.sha256(
            AGENTIC_SESSION_INPUT_FIXTURE.read_bytes()
        ).hexdigest(),
    }


def agentic_evaluation_digest() -> str:
    """Return one stable digest joining the exact charter and session inputs."""
    return json_payload_hash(agentic_evaluation_component_digests())


def build_agentic_identity_manifest(
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the credential-free agent/model/tool/evaluation freeze identity.

    Args:
        environ: Optional environment mapping used instead of ``os.environ``.

    Returns:
        Stable public identity with a content digest.

    Raises:
        ValueError: If a required controlled-runtime identity is absent or
            mutable.
    """
    values = os.environ if environ is None else environ
    selected_profile = str(
        values.get("TRADER_AGENTS_MODEL_PROFILE_ID") or DEVELOPMENT_MODEL_PROFILE_ID
    ).strip()
    public_runtime = runtime_manifest()
    available_profiles = {
        str(item["profile_id"]) for item in public_runtime["model_profiles"]["profiles"]
    }
    if selected_profile not in available_profiles:
        raise ValueError("selected agent model profile is not admitted")
    container_image = validate_pinned_container_image(
        str(values.get("TRADER_MCP_CODING_CONTAINER_IMAGE") or "")
    )
    tracking_uri = str(values.get("TRADER_AGENTS_MLFLOW_TRACKING_URI") or "").strip()
    if not tracking_uri:
        raise ValueError(
            "TRADER_AGENTS_MLFLOW_TRACKING_URI is required for qualification"
        )
    experiment = str(
        values.get("TRADER_AGENTS_MLFLOW_EXPERIMENT") or "trader-agentic-research"
    ).strip()
    if not experiment:
        raise ValueError("TRADER_AGENTS_MLFLOW_EXPERIMENT cannot be empty")
    evaluation = load_agentic_evaluation_contract()
    payload = {
        "selected_model_profile_id": selected_profile,
        "runtime": public_runtime,
        "runtime_manifest_digest": json_payload_hash(public_runtime),
        "evaluation_dataset_id": evaluation["dataset_id"],
        "evaluation_dataset_digest": agentic_evaluation_digest(),
        "evaluation_component_digests": agentic_evaluation_component_digests(),
        "sandbox_image": container_image,
        "trace": {
            "enabled": True,
            "experiment": experiment,
        },
    }
    return {**payload, "identity_digest": json_payload_hash(payload)}


def evaluate_agentic_campaign(
    results: Sequence[AgenticScenarioResult],
) -> dict[str, Any]:
    """Evaluate complete repeated results against the frozen thresholds.

    Args:
        results: Public results from one exact freeze and environment.

    Returns:
        JSON-native campaign verdict, aggregate measurements, and blockers.
    """
    contract = load_agentic_evaluation_contract()
    scenarios = {str(item["scenario_id"]): item for item in contract["scenarios"]}
    thresholds = contract["provisional_promotion_thresholds"]
    repetitions = int(thresholds["repetitions_per_scenario"])
    blockers: list[str] = []
    by_identity: dict[tuple[str, int], AgenticScenarioResult] = {}
    for result in results:
        key = (result.scenario_id, result.repetition)
        if key in by_identity:
            blockers.append(
                f"duplicate result for {result.scenario_id} repetition {result.repetition}"
            )
            continue
        by_identity[key] = result
    expected = {
        (scenario_id, repetition)
        for scenario_id in scenarios
        for repetition in range(1, repetitions + 1)
    }
    missing = sorted(expected - set(by_identity))
    unexpected = sorted(set(by_identity) - expected)
    if missing:
        blockers.append(f"missing scenario repetitions: {missing}")
    if unexpected:
        blockers.append(f"unexpected scenario repetitions: {unexpected}")

    expected_results = [by_identity[key] for key in sorted(expected & set(by_identity))]
    required_invariants = {
        str(item) for item in contract["required_deterministic_invariants"]
    }
    for result in expected_results:
        scenario = scenarios[result.scenario_id]
        _evaluate_trajectory(
            result,
            scenario,
            required_invariants=required_invariants,
            blockers=blockers,
        )
        _evaluate_run_limits(result, thresholds, blockers)

    count = len(expected_results)
    deterministic_passes = sum(
        bool(result.deterministic_invariants)
        and all(result.deterministic_invariants.values())
        for result in expected_results
    )
    schema_passes = sum(result.schema_valid for result in expected_results)
    grounded_passes = sum(result.grounded_decision for result in expected_results)
    role_coverage = (
        sum(result.required_role_coverage for result in expected_results) / count
        if count
        else 0.0
    )
    rates = {
        "deterministic_invariant_pass_rate": _rate(deterministic_passes, count),
        "schema_validity_rate": _rate(schema_passes, count),
        "grounded_decision_rate": _rate(grounded_passes, count),
        "required_role_coverage_rate": role_coverage,
    }
    for name, actual in rates.items():
        required = float(thresholds[name])
        if actual < required:
            blockers.append(f"{name} {actual:.6f} is below {required:.6f}")

    totals = {
        "forbidden_tool_calls": sum(
            item.forbidden_tool_calls for item in expected_results
        ),
        "unapproved_mutations": sum(
            item.unapproved_mutations for item in expected_results
        ),
        "lost_canonical_receipts": sum(
            item.lost_canonical_receipts for item in expected_results
        ),
        "replayed_accepted_mutations": sum(
            item.replayed_accepted_mutations for item in expected_results
        ),
    }
    for name, actual in totals.items():
        maximum = int(thresholds[name])
        if actual > maximum:
            blockers.append(f"{name} {actual} exceeds {maximum}")
    trace_ids = {trace_id for item in expected_results for trace_id in item.trace_ids}
    recorded_trace_count = sum(len(item.trace_ids) for item in expected_results)
    if len(trace_ids) != recorded_trace_count:
        blockers.append("scenario repetitions cannot share trace identities")

    return {
        "status": "passed" if not blockers else "blocked",
        "dataset_id": contract["dataset_id"],
        "dataset_digest": agentic_evaluation_digest(),
        "scenario_count": len(scenarios),
        "repetitions_per_scenario": repetitions,
        "result_count": count,
        "rates": rates,
        "totals": totals,
        "maxima": {
            "model_calls": max(
                (item.model_calls for item in expected_results), default=0
            ),
            "tool_calls": max(
                (item.tool_calls for item in expected_results), default=0
            ),
            "total_tokens": max(
                (item.total_tokens for item in expected_results), default=0
            ),
            "duration_seconds": max(
                (item.duration_seconds for item in expected_results),
                default=0.0,
            ),
            "revisions": max((item.revisions for item in expected_results), default=0),
            "peak_concurrency": max(
                (item.peak_concurrency for item in expected_results),
                default=0,
            ),
        },
        "trace_ids": sorted(trace_ids),
        "blockers": blockers,
    }


def save_agentic_scenario_result(
    connection: psycopg.Connection[Any],
    *,
    qualification_profile: str,
    freeze_revision: str,
    result: AgenticScenarioResult,
) -> None:
    """Upsert one public result under an exact qualification identity."""
    _bounded_text(qualification_profile, "qualification_profile", limit=120)
    _bounded_text(freeze_revision, "freeze_revision", limit=80)
    connection.execute(
        """
        INSERT INTO verification_control.agentic_scenario_results (
            qualification_profile, freeze_revision, scenario_id, repetition,
            status, result
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (
            qualification_profile, freeze_revision, scenario_id, repetition
        ) DO UPDATE SET
            status = EXCLUDED.status,
            result = EXCLUDED.result,
            recorded_at = now()
        """,
        [
            qualification_profile,
            freeze_revision,
            result.scenario_id,
            result.repetition,
            result.status,
            Jsonb(result.to_dict()),
        ],
    )


def load_agentic_scenario_results(
    connection: psycopg.Connection[Any],
    *,
    qualification_profile: str,
    freeze_revision: str,
) -> tuple[AgenticScenarioResult, ...]:
    """Load strict public scenario results for one exact freeze."""
    rows = connection.execute(
        """
        SELECT result
        FROM verification_control.agentic_scenario_results
        WHERE qualification_profile = %s AND freeze_revision = %s
        ORDER BY scenario_id, repetition
        """,
        [qualification_profile, freeze_revision],
    ).fetchall()
    results = []
    for row in rows:
        payload = row["result"] if isinstance(row, Mapping) else row[0]
        if not isinstance(payload, Mapping):
            raise ValueError("persisted scenario result must be a JSON object")
        results.append(AgenticScenarioResult.from_dict(payload))
    return tuple(results)


def _evaluate_trajectory(
    result: AgenticScenarioResult,
    scenario: Mapping[str, Any],
    *,
    required_invariants: set[str],
    blockers: list[str],
) -> None:
    """Apply one scenario's exact trajectory and evidence obligations."""
    prefix = f"{result.scenario_id} repetition {result.repetition}"
    if result.status != "passed":
        blockers.append(f"{prefix} recorded blocked status: {list(result.blockers)}")
    expected_actions = {str(item) for item in scenario["expected_terminal_actions"]}
    if any(action not in expected_actions for action in result.terminal_actions):
        blockers.append(f"{prefix} used unexpected terminal action")
    legal_roles = {str(item) for item in scenario["legal_delegations"]}
    if not set(result.delegated_roles).issubset(legal_roles):
        blockers.append(f"{prefix} delegated outside the legal role set")
    required_roles = {str(item) for item in scenario["required_delegations"]}
    actual_coverage = (
        len(set(result.delegated_roles) & required_roles) / len(required_roles)
        if required_roles
        else 1.0
    )
    if abs(result.required_role_coverage - actual_coverage) > 1e-9:
        blockers.append(f"{prefix} reported inconsistent role coverage")
    required_evidence = {str(item) for item in scenario["required_evidence"]}
    if not required_evidence.issubset(result.evidence_types):
        blockers.append(f"{prefix} omitted required evidence types")
    if required_evidence and not result.evidence_refs:
        blockers.append(f"{prefix} omitted exact evidence references")
    permitted_mutations = {str(item) for item in scenario["permitted_mutations"]}
    if not set(result.mutations).issubset(permitted_mutations):
        blockers.append(f"{prefix} attempted an unpermitted mutation class")
    expected_assertions = {str(item) for item in scenario["trajectory_assertions"]}
    if set(result.trajectory_assertions) != expected_assertions or not all(
        result.trajectory_assertions.values()
    ):
        blockers.append(f"{prefix} failed trajectory assertions")
    if not required_invariants.issubset(result.deterministic_invariants):
        blockers.append(f"{prefix} omitted deterministic invariants")
    if not all(
        result.deterministic_invariants.get(name) is True
        for name in required_invariants
    ):
        blockers.append(f"{prefix} failed deterministic invariants")
    if result.model_calls == 0 or result.total_tokens == 0:
        blockers.append(f"{prefix} contains no real-model usage evidence")


def _evaluate_run_limits(
    result: AgenticScenarioResult,
    thresholds: Mapping[str, Any],
    blockers: list[str],
) -> None:
    """Apply per-run model, tool, token, duration, and revision ceilings."""
    prefix = f"{result.scenario_id} repetition {result.repetition}"
    comparisons = (
        (result.model_calls, "max_model_calls_per_run"),
        (result.tool_calls, "max_tool_calls_per_run"),
        (result.total_tokens, "max_tokens_per_run"),
        (result.duration_seconds, "max_duration_seconds_per_run"),
        (result.revisions, "max_revisions_per_run"),
        (result.peak_concurrency, "max_concurrency"),
    )
    for actual, threshold_name in comparisons:
        maximum = float(thresholds[threshold_name])
        if actual > maximum:
            blockers.append(f"{prefix} exceeded {threshold_name}")


def _rate(passes: int, count: int) -> float:
    """Return a stable zero-safe pass rate."""
    return passes / count if count else 0.0


def _scenario_role_set(scenario: Mapping[str, Any], field_name: str) -> set[str]:
    """Return one scenario's closed specialist-role set."""
    value = scenario.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"agentic scenario {field_name} must be a JSON array")
    if any(
        not isinstance(item, str)
        or item not in {"data_research", "strategy_engineering"}
        for item in value
    ):
        raise ValueError(f"agentic scenario {field_name} contains an unknown role")
    if len(value) != len(set(value)):
        raise ValueError(f"agentic scenario {field_name} roles must be unique")
    return set(value)


def _bounded_text(value: str, label: str, *, limit: int = _MAX_PUBLIC_TEXT) -> None:
    """Require one non-empty bounded public string."""
    if not value.strip() or len(value.encode("utf-8")) > limit:
        raise ValueError(f"{label} must contain 1 to {limit} UTF-8 bytes")


def _bounded_text_sequence(values: Sequence[str], label: str) -> None:
    """Require a bounded sequence of unique public strings."""
    if len(values) > _MAX_PUBLIC_ITEMS:
        raise ValueError(f"{label} contains too many values")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} values must be unique")
    for value in values:
        _bounded_text(value, label)


def _bounded_ordered_text_sequence(values: Sequence[str], label: str) -> None:
    """Require a bounded ordered sequence where repeated values are meaningful."""
    if len(values) > _MAX_PUBLIC_ITEMS:
        raise ValueError(f"{label} contains too many values")
    for value in values:
        _bounded_text(value, label)


def _bounded_verdicts(values: Mapping[str, bool], label: str) -> None:
    """Require bounded named boolean verdicts."""
    if not values or len(values) > _MAX_PUBLIC_ITEMS:
        raise ValueError(f"{label} must contain 1 to {_MAX_PUBLIC_ITEMS} verdicts")
    for key, value in values.items():
        if not isinstance(key, str):
            raise ValueError(f"{label} names must be strings")
        _bounded_text(key, label)
        if not isinstance(value, bool):
            raise ValueError(f"{label} verdicts must be booleans")


def _string_tuple(value: object) -> tuple[str, ...]:
    """Normalize one JSON array into a tuple of strings."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("expected a JSON array of strings")
    if any(not isinstance(item, str) for item in value):
        raise ValueError("expected a JSON array of strings")
    return tuple(value)


def _bool_mapping(value: object) -> dict[str, bool]:
    """Normalize one JSON object into named boolean verdicts."""
    if not isinstance(value, Mapping):
        raise ValueError("expected a JSON object of boolean verdicts")
    if any(not isinstance(key, str) for key in value):
        raise ValueError("expected a JSON object with string verdict names")
    if any(not isinstance(item, bool) for item in value.values()):
        raise ValueError("expected a JSON object of boolean verdicts")
    return dict(value)


def _required_string(value: object, label: str) -> str:
    """Require a JSON string without permissive coercion."""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _required_bool(value: object, label: str) -> bool:
    """Require a JSON boolean without truthiness coercion."""
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _required_int(value: object, label: str) -> int:
    """Require a JSON integer while rejecting booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _required_float(value: object, label: str) -> float:
    """Require a finite JSON number while rejecting booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    normalized = float(value)
    if not normalized == normalized or normalized in {float("inf"), float("-inf")}:
        raise ValueError(f"{label} must be finite")
    return normalized
