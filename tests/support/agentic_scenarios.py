"""Strict concrete session fixtures for first-slice agentic qualification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any

from trader_research.foundation import stable_research_id
from trader_research.governance import AgentBudget, ResearchSession

from tests.support.agentic_qualification import (
    load_agentic_evaluation_contract,
    load_agentic_session_input_contract,
)
from trader_agents.catalogue import first_slice_tool_catalogue
from trader_agents.contracts import AgentRole
from trader_agents.inputs import (
    SessionInputError,
    composite_data_scope_from_session,
    strategy_build_contract_from_session,
    validate_runtime_pins,
)
from trader_agents.profiles import (
    DEVELOPMENT_MODEL_PROFILE_ID,
    development_model_profiles,
)
from trader_agents.programs import first_slice_programs


_FREEZE_REVISION_PATTERN = re.compile(r"[0-9a-f]{40,64}")
_EXECUTION_NAMESPACE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
_EXECUTION_NAMESPACE_ORDINALS = {
    "campaign": 0,
    "postgres_e2e": 1,
    "postgres_recovery": 2,
    "bounded_scale_serial": 3,
    "bounded_scale_parallel": 4,
    "security": 5,
    "bounded_scale_recovery": 6,
    "strategy_recovery_a": 7,
    "strategy_recovery_b": 8,
    "strategy_recovery_c": 9,
}
_INPUT_CONTRACT_FIELDS = frozenset(
    {
        "fixture_id",
        "schema_version",
        "scenario_dataset_id",
        "session_template",
        "scenarios",
    }
)
_SCENARIO_FIELDS = frozenset(
    {
        "isolation_ordinal",
        "build_contract_expected",
        "environment_fixture",
        "session_variants",
    }
)
_ENVIRONMENT_FIELDS = frozenset(
    {
        "data_state",
        "implementation_state",
        "admission_sequence",
        "fault_profile",
        "untrusted_content_profile",
    }
)
_VARIANT_FIELDS = frozenset({"variant_id", "patch"})
_SESSION_TEMPLATE_FIELDS = frozenset(
    {
        "objective",
        "success_definition",
        "operator_id",
        "approval_policy",
        "scope_envelope",
        "implementation_specification",
        "python_quality_guide",
        "budget",
    }
)
_BUILD_EXPECTATIONS = frozenset({"valid", "materially_incomplete"})
_ADMISSION_OUTCOMES = frozenset(
    {
        "passed",
        "actionable_non_semantic_failure",
        "actionable_failure",
        "equivalent_failure",
    }
)
_FAULT_PROFILES = frozenset(
    {
        "none",
        "before_mutation_after_acceptance_and_return_reconciliation",
    }
)
_UNTRUSTED_CONTENT_PROFILES = frozenset(
    {
        "none",
        "provider_and_repository_prompt_injection",
    }
)


@dataclass(frozen=True)
class ScenarioEnvironmentFixture:
    """Exact external-state behavior required by one scenario.

    Attributes:
        data_state: Named deterministic market-data fixture state.
        implementation_state: Named deterministic catalogue fixture state.
        admission_sequence: Ordered independent admission outcomes.
        fault_profile: Named process-fault injection behavior.
        untrusted_content_profile: Named embedded-content attack fixture.
    """

    data_state: str
    implementation_state: str
    admission_sequence: tuple[str, ...]
    fault_profile: str
    untrusted_content_profile: str


@dataclass(frozen=True)
class AgenticSessionVariant:
    """One named concrete brief variant represented as a JSON merge patch."""

    variant_id: str
    patch: Mapping[str, Any]


@dataclass(frozen=True)
class AgenticScenarioInput:
    """Frozen session and environment inputs for one evaluated scenario.

    Attributes:
        scenario_id: Stable scenario identity from the evaluation charter.
        isolation_ordinal: Unique zero-based slot used to isolate mutable Data
            and implementation state across the complete campaign.
        build_contract_expected: Whether the merged operator specification is
            expected to form a complete Strategy build contract.
        environment: Exact named external-state fixture behavior.
        variants: One or more concrete brief variants for each repetition.
    """

    scenario_id: str
    isolation_ordinal: int
    build_contract_expected: str
    environment: ScenarioEnvironmentFixture
    variants: tuple[AgenticSessionVariant, ...]


def load_agentic_scenario_inputs() -> dict[str, AgenticScenarioInput]:
    """Normalize the complete frozen input fixture into strict value objects.

    Returns:
        Scenario inputs keyed by the exact charter scenario identity.

    Raises:
        ValueError: If any fixture field, variant, or environment value is
            missing, unknown, unbounded, or internally inconsistent.
    """
    payload = load_agentic_session_input_contract()
    _require_exact_fields(payload, _INPUT_CONTRACT_FIELDS, "input fixture")
    raw_scenarios = _required_mapping(payload.get("scenarios"), "scenarios")
    normalized: dict[str, AgenticScenarioInput] = {}
    for scenario_id, raw_scenario in raw_scenarios.items():
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError("scenario input identities must be non-empty strings")
        scenario = _required_mapping(raw_scenario, scenario_id)
        _require_exact_fields(scenario, _SCENARIO_FIELDS, scenario_id)
        isolation_ordinal = _required_ordinal(
            scenario.get("isolation_ordinal"),
            f"{scenario_id}.isolation_ordinal",
        )
        expectation = _required_text(
            scenario.get("build_contract_expected"),
            f"{scenario_id}.build_contract_expected",
        )
        if expectation not in _BUILD_EXPECTATIONS:
            raise ValueError(f"{scenario_id} has an unknown build expectation")
        environment = _environment_fixture(
            scenario_id,
            scenario.get("environment_fixture"),
        )
        variants = _session_variants(scenario_id, scenario.get("session_variants"))
        normalized[scenario_id] = AgenticScenarioInput(
            scenario_id=scenario_id,
            isolation_ordinal=isolation_ordinal,
            build_contract_expected=expectation,
            environment=environment,
            variants=variants,
        )
    _validate_isolation_ordinals(normalized)
    return normalized


def build_agentic_scenario_sessions(
    scenario_id: str,
    *,
    repetition: int,
    freeze_revision: str,
    execution_namespace: str = "campaign",
) -> tuple[ResearchSession, ...]:
    """Build every exact research session required by one scenario repetition.

    Args:
        scenario_id: Exact scenario identity from the evaluation charter.
        repetition: One-based repetition within the frozen campaign.
        freeze_revision: Exact lowercase Git revision under qualification.
        execution_namespace: Code-owned qualification lane used to isolate
            phase-specific sessions, Data windows, and implementation names.

    Returns:
        One session for ordinary scenarios or the complete paired sessions for
        a multi-brief scenario.

    Raises:
        ValueError: If identity, repetition, or normalized session inputs are
            invalid or contradict their declared build expectation.
    """
    if _FREEZE_REVISION_PATTERN.fullmatch(freeze_revision) is None:
        raise ValueError("freeze_revision must be a full lowercase Git revision")
    namespace = _normalized_execution_namespace(execution_namespace)
    charter = load_agentic_evaluation_contract()
    maximum_repetitions = int(
        charter["provisional_promotion_thresholds"]["repetitions_per_scenario"]
    )
    if not 1 <= repetition <= maximum_repetitions:
        raise ValueError(f"repetition must be between 1 and {maximum_repetitions}")
    inputs = load_agentic_scenario_inputs()
    try:
        scenario = inputs[scenario_id]
    except KeyError as exc:
        raise ValueError(f"unknown agentic scenario: {scenario_id}") from exc
    contract = load_agentic_session_input_contract()
    template = _required_mapping(contract["session_template"], "session_template")
    _require_exact_fields(template, _SESSION_TEMPLATE_FIELDS, "session_template")
    return tuple(
        _build_session(
            scenario,
            variant,
            template=template,
            repetition=repetition,
            freeze_revision=freeze_revision,
            execution_namespace=namespace,
        )
        for variant in scenario.variants
    )


def _build_session(
    scenario: AgenticScenarioInput,
    variant: AgenticSessionVariant,
    *,
    template: Mapping[str, Any],
    repetition: int,
    freeze_revision: str,
    execution_namespace: str,
) -> ResearchSession:
    """Apply one frozen patch and validate the resulting session boundary."""
    payload = _json_merge_patch(template, variant.patch)
    _require_exact_fields(payload, _SESSION_TEMPLATE_FIELDS, "merged session")
    session_id = stable_research_id(
        "agentic_qualification_session",
        {
            "scenario_id": scenario.scenario_id,
            "variant_id": variant.variant_id,
            "repetition": repetition,
            "freeze_revision": freeze_revision,
            "execution_namespace": execution_namespace,
        },
    )
    scope_envelope = _required_mapping(payload["scope_envelope"], "scope_envelope")
    scope_envelope = _json_clone(scope_envelope)
    raw_scope = _required_mapping(scope_envelope.get("data_scope"), "data_scope")
    namespace_ordinal = _EXECUTION_NAMESPACE_ORDINALS[execution_namespace]
    isolation_offset_days = (
        scenario.isolation_ordinal * 14
        + (repetition - 1) * 400
        + namespace_ordinal * 10_000
    )
    scope = _isolate_data_scope(
        raw_scope,
        offset_days=isolation_offset_days,
    )
    scope["session_id"] = session_id
    scope["scope_id"] = stable_research_id(
        "agentic_qualification_scope",
        {
            "session_id": session_id,
            "items": scope.get("items"),
            "loading_approved": scope.get("loading_approved"),
            "max_loading_cost": scope.get("max_loading_cost"),
        },
    )
    scope_envelope["data_scope"] = scope
    implementation = _required_mapping(
        payload["implementation_specification"],
        "implementation_specification",
    )
    implementation = _isolate_implementation_specification(
        implementation,
        isolation_ordinal=scenario.isolation_ordinal + namespace_ordinal * 100,
        repetition=repetition,
        variant_id=variant.variant_id,
    )
    implementation["repository_revision"] = freeze_revision
    programs = first_slice_programs()
    catalogue = first_slice_tool_catalogue()
    session = ResearchSession(
        session_id=session_id,
        objective=_required_text(payload["objective"], "objective"),
        success_definition=_required_text(
            payload["success_definition"],
            "success_definition",
        ),
        operator_id=_required_text(payload["operator_id"], "operator_id"),
        approval_policy=_required_mapping(
            payload["approval_policy"],
            "approval_policy",
        ),
        scope_envelope=scope_envelope,
        implementation_specification=implementation,
        implementation_ref=None,
        python_quality_guide=_required_text(
            payload["python_quality_guide"],
            "python_quality_guide",
        ),
        model_profile_id=DEVELOPMENT_MODEL_PROFILE_ID,
        agent_program_ids=tuple(
            programs.for_role(role).program_id for role in AgentRole
        ),
        tool_catalog_id=catalogue.catalogue_id,
        budget=AgentBudget.from_dict(_required_mapping(payload["budget"], "budget")),
        metadata={
            "qualification_dataset_id": load_agentic_evaluation_contract()[
                "dataset_id"
            ],
            "qualification_scenario_id": scenario.scenario_id,
            "qualification_variant_id": variant.variant_id,
            "qualification_repetition": repetition,
            "qualification_execution_namespace": execution_namespace,
            "qualification_isolation_ordinal": scenario.isolation_ordinal,
            "qualification_time_offset_days": isolation_offset_days,
            "freeze_revision": freeze_revision,
        },
    )
    validate_runtime_pins(
        session,
        model_profiles=development_model_profiles(),
        agent_programs=programs,
        tool_catalogue=catalogue,
    )
    composite_data_scope_from_session(session)
    branch_id = stable_research_id(
        "agent_branch",
        {"session_id": session.session_id, "task_id": "strategy"},
    )
    try:
        strategy_build_contract_from_session(session, branch_id=branch_id)
    except SessionInputError:
        if scenario.build_contract_expected != "materially_incomplete":
            raise
    else:
        if scenario.build_contract_expected != "valid":
            raise ValueError(
                f"{scenario.scenario_id} unexpectedly has a complete build contract"
            )
    return session


def _normalized_execution_namespace(value: str) -> str:
    """Return one admitted qualification execution namespace."""
    normalized = str(value).strip().lower()
    if (
        _EXECUTION_NAMESPACE_PATTERN.fullmatch(normalized) is None
        or normalized not in _EXECUTION_NAMESPACE_ORDINALS
    ):
        raise ValueError(
            "execution_namespace must be one of "
            f"{sorted(_EXECUTION_NAMESPACE_ORDINALS)}"
        )
    return normalized


def _isolate_data_scope(
    raw_scope: Mapping[str, Any],
    *,
    offset_days: int,
) -> dict[str, Any]:
    """Shift every requested window into a campaign-unique Data partition.

    Repeated qualification runs must not inherit bars loaded by an earlier
    scenario or repetition. The frozen ordinal plus a 400-day repetition stride
    yields disjoint windows while preserving each brief's exact duration,
    symbols, timeframe, and authority envelope.

    Args:
        raw_scope: Merged operator-approved Data scope.
        offset_days: Deterministic scenario/repetition offset.

    Returns:
        Deep-copied scope with shifted ISO-8601 item boundaries.

    Raises:
        ValueError: If scope items or timestamp boundaries are malformed.
    """
    scope = _json_clone(raw_scope)
    items = scope.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("data_scope.items must be a non-empty array")
    isolated_items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(items):
        item = _required_mapping(raw_item, f"data_scope.items[{index}]")
        for field_name in ("start", "end"):
            timestamp = _parse_utc_timestamp(
                item.get(field_name),
                f"data_scope.items[{index}].{field_name}",
            )
            item[field_name] = _utc_text(timestamp + timedelta(days=offset_days))
        isolated_items.append(item)
    scope["items"] = isolated_items
    return scope


def _isolate_implementation_specification(
    raw_specification: Mapping[str, Any],
    *,
    isolation_ordinal: int,
    repetition: int,
    variant_id: str,
) -> dict[str, Any]:
    """Give one campaign session a catalogue-unique implementation name.

    Args:
        raw_specification: Merged operator-approved implementation input.
        isolation_ordinal: Unique scenario slot.
        repetition: One-based campaign repetition.
        variant_id: Frozen brief-variant identity.

    Returns:
        Deep-copied specification with an isolated implementation name.

    Raises:
        ValueError: If the required name is missing or the isolated name would
            exceed the public build-contract boundary.
    """
    specification = _json_clone(raw_specification)
    base_name = _required_text(specification.get("name"), "implementation name")
    variant_token = re.sub(r"[^a-z0-9]+", "_", variant_id.lower()).strip("_")
    isolated_name = (
        f"{base_name}__q{isolation_ordinal:02d}r{repetition}_{variant_token}"
    )
    if len(isolated_name) > 200:
        raise ValueError("isolated implementation name exceeds 200 characters")
    specification["name"] = isolated_name
    return specification


def _parse_utc_timestamp(value: object, label: str) -> datetime:
    """Parse one timezone-aware ISO timestamp and normalize it to UTC."""
    text = _required_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    """Return a canonical UTC ISO-8601 fixture timestamp."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _environment_fixture(
    scenario_id: str,
    value: object,
) -> ScenarioEnvironmentFixture:
    """Normalize one closed environment-fixture declaration."""
    payload = _required_mapping(value, f"{scenario_id}.environment_fixture")
    _require_exact_fields(payload, _ENVIRONMENT_FIELDS, "environment_fixture")
    admission = payload.get("admission_sequence")
    if not isinstance(admission, list) or any(
        not isinstance(item, str) or not item for item in admission
    ):
        raise ValueError("admission_sequence must be an array of strings")
    if len(admission) > 2:
        raise ValueError("admission_sequence cannot exceed two candidate attempts")
    unknown_outcomes = set(admission).difference(_ADMISSION_OUTCOMES)
    if unknown_outcomes:
        raise ValueError(
            f"unknown admission_sequence outcomes: {sorted(unknown_outcomes)}"
        )
    fault_profile = _required_text(payload["fault_profile"], "fault_profile")
    if fault_profile not in _FAULT_PROFILES:
        raise ValueError(f"unknown qualification fault profile: {fault_profile}")
    untrusted_content_profile = _required_text(
        payload["untrusted_content_profile"],
        "untrusted_content_profile",
    )
    if untrusted_content_profile not in _UNTRUSTED_CONTENT_PROFILES:
        raise ValueError(
            "unknown qualification untrusted-content profile: "
            f"{untrusted_content_profile}"
        )
    return ScenarioEnvironmentFixture(
        data_state=_required_text(payload["data_state"], "data_state"),
        implementation_state=_required_text(
            payload["implementation_state"],
            "implementation_state",
        ),
        admission_sequence=tuple(admission),
        fault_profile=fault_profile,
        untrusted_content_profile=untrusted_content_profile,
    )


def _session_variants(
    scenario_id: str,
    value: object,
) -> tuple[AgenticSessionVariant, ...]:
    """Normalize a bounded non-empty list of unique session variants."""
    if not isinstance(value, list) or not value or len(value) > 4:
        raise ValueError(f"{scenario_id}.session_variants must contain 1 to 4 items")
    variants: list[AgenticSessionVariant] = []
    for raw_variant in value:
        payload = _required_mapping(raw_variant, "session variant")
        _require_exact_fields(payload, _VARIANT_FIELDS, "session variant")
        variant_id = _required_text(payload["variant_id"], "variant_id")
        patch = _required_mapping(payload["patch"], "session patch")
        if not set(patch).issubset(_SESSION_TEMPLATE_FIELDS):
            raise ValueError("session patch attempts to set a runtime-owned field")
        variants.append(AgenticSessionVariant(variant_id=variant_id, patch=patch))
    if len({item.variant_id for item in variants}) != len(variants):
        raise ValueError(f"{scenario_id} session variant IDs must be unique")
    return tuple(variants)


def _json_merge_patch(
    target: Mapping[str, Any],
    patch: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply RFC 7396 object merge-patch semantics to JSON-native mappings."""
    result = _json_clone(target)
    for key, value in patch.items():
        if not isinstance(key, str):
            raise ValueError("JSON merge-patch keys must be strings")
        if value is None:
            result.pop(key, None)
        elif isinstance(value, Mapping):
            current = result.get(key)
            base = current if isinstance(current, Mapping) else {}
            result[key] = _json_merge_patch(base, value)
        else:
            result[key] = _json_clone(value)
    return result


def _json_clone(value: Any) -> Any:
    """Copy one JSON-native value while rejecting non-JSON objects and NaN."""
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("agentic session inputs must be JSON-native") from exc


def _required_mapping(value: object, label: str) -> dict[str, Any]:
    """Require a JSON object with string keys."""
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return dict(value)


def _required_text(value: object, label: str) -> str:
    """Require a bounded non-empty public fixture string."""
    if not isinstance(value, str) or not value.strip() or len(value) > 2_000:
        raise ValueError(f"{label} must contain 1 to 2000 characters")
    return value


def _required_ordinal(value: object, label: str) -> int:
    """Require a non-negative integer campaign-isolation ordinal."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _validate_isolation_ordinals(
    scenarios: Mapping[str, AgenticScenarioInput],
) -> None:
    """Require one contiguous isolation slot for every charter scenario."""
    ordinals = sorted(item.isolation_ordinal for item in scenarios.values())
    expected = list(range(len(scenarios)))
    if ordinals != expected:
        raise ValueError(
            "scenario isolation ordinals must be unique and contiguous from zero"
        )


def _require_exact_fields(
    payload: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    """Reject missing and forward-unknown fixture fields."""
    missing = expected - set(payload)
    unknown = set(payload) - expected
    if missing or unknown:
        raise ValueError(
            f"{label} fields do not match the closed contract: "
            f"missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
