"""Bounded checkpoint contracts for isolated specialist model/tool loops.

Specialist checkpoints are operational recovery state, not research evidence or
conversation storage. They retain enough public state to resume a delegation,
while source text, prompts, model rationale, command output, and raw MCP payloads
remain transient and must be re-read through an authorized MCP capability after
a fresh-process restart.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any, TypedDict

from trader_research.foundation import json_payload_hash

from ..contracts import (
    AgentRole,
    BudgetUsage,
    CanonicalEvidenceRef,
    SpecialistDelegation,
    SpecialistReturn,
    ToolObservation,
)


MAX_SPECIALIST_CHECKPOINT_BYTES = 192_000
MAX_SPECIALIST_OBSERVATIONS = 24
MAX_SPECIALIST_STEPS = 32
MAX_SPECIALIST_EVIDENCE_REFS = 32
MAX_SPECIALIST_LOOP_FINGERPRINTS = 96

_SENSITIVE_EXACT_KEYS = frozenset(
    {
        "content",
        "excerpt",
        "hidden_reasoning",
        "prompt",
        "public_rationale",
        "raw_message",
        "raw_tool_payload",
        "source_code",
        "stderr",
        "stdout",
        "tool_transcript",
    }
)
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "credential",
    "password",
    "scratchpad",
    "secret",
)


class SpecialistCheckpointState(TypedDict, total=False):
    """JSON-native state persisted for one isolated specialist delegation."""

    session_id: str
    session_digest: str
    delegation_id: str
    delegation_digest: str
    branch_id: str
    attempt_id: str
    role: str
    status: str
    phase: str
    program_id: str
    model_profile_id: str
    tool_catalog_id: str
    observations: list[dict[str, Any]]
    successful_steps: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]
    loop_fingerprints: dict[str, int]
    lifecycle: dict[str, Any]
    budget_usage: dict[str, Any]
    step_sequence: int
    terminal_return: dict[str, Any]


def build_specialist_checkpoint_state(
    *,
    session_id: str,
    session_digest: str,
    delegation: SpecialistDelegation,
    role: AgentRole,
    phase: str,
    program_id: str,
    model_profile_id: str,
    tool_catalog_id: str,
    lifecycle: Mapping[str, Any] | None = None,
) -> SpecialistCheckpointState:
    """Build validated initial state for one specialist invocation.

    Args:
        session_id: Exact immutable research-session identity.
        session_digest: Digest of the complete research-session payload.
        delegation: Deterministically admitted specialist delegation.
        role: Specialist role that owns the invocation.
        phase: Initial policy-relevant phase.
        program_id: Exact versioned specialist program identity.
        model_profile_id: Exact admitted model-profile identity.
        tool_catalog_id: Exact code-owned tool-catalogue identity.
        lifecycle: Optional role-specific public lifecycle facts.

    Returns:
        Bounded JSON-native state ready for LangGraph persistence.
    """
    delegation_payload = delegation.model_dump(mode="json")
    state: SpecialistCheckpointState = {
        "session_id": _required_text(session_id, "session_id"),
        "session_digest": _required_text(session_digest, "session_digest"),
        "delegation_id": delegation.delegation_id,
        "delegation_digest": json_payload_hash(delegation_payload),
        "branch_id": delegation.branch_id,
        "attempt_id": delegation.attempt_id,
        "role": role.value,
        "status": "running",
        "phase": _required_text(phase, "phase"),
        "program_id": _required_text(program_id, "program_id"),
        "model_profile_id": _required_text(
            model_profile_id,
            "model_profile_id",
        ),
        "tool_catalog_id": _required_text(tool_catalog_id, "tool_catalog_id"),
        "observations": [],
        "successful_steps": [],
        "evidence_refs": [],
        "loop_fingerprints": {},
        "lifecycle": dict(lifecycle or {}),
        "budget_usage": BudgetUsage().model_dump(mode="json"),
        "step_sequence": 1,
        "terminal_return": {},
    }
    validate_specialist_checkpoint_state(state)
    return state


def validate_specialist_checkpoint_state(
    state: Mapping[str, Any],
) -> None:
    """Reject unsafe, inconsistent, or unbounded specialist state.

    Args:
        state: Candidate JSON-native specialist checkpoint mapping.

    Raises:
        ValueError: If state is unbounded, contains sensitive fields, or has
            inconsistent public identities or contracts.
    """
    allowed_fields = set(SpecialistCheckpointState.__annotations__)
    unknown_fields = set(state) - allowed_fields
    if unknown_fields:
        raise ValueError(
            "specialist checkpoint has unknown fields: "
            + ", ".join(sorted(unknown_fields))
        )
    for key in (
        "session_id",
        "session_digest",
        "delegation_id",
        "delegation_digest",
        "branch_id",
        "attempt_id",
        "role",
        "status",
        "phase",
        "program_id",
        "model_profile_id",
        "tool_catalog_id",
    ):
        _required_text(state.get(key), key)
    try:
        AgentRole(str(state["role"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("specialist checkpoint role is unsupported") from exc
    if state.get("role") == AgentRole.RESEARCH_COORDINATOR.value:
        raise ValueError("coordinator state cannot use a specialist checkpoint")

    sequence = state.get("step_sequence", 1)
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValueError("step_sequence must be a positive integer")
    BudgetUsage.model_validate(
        _optional_mapping(state.get("budget_usage"), "budget_usage")
    )

    observations = _mapping_sequence(state.get("observations"), "observations")
    if len(observations) > MAX_SPECIALIST_OBSERVATIONS:
        raise ValueError(
            "specialist checkpoint supports at most "
            f"{MAX_SPECIALIST_OBSERVATIONS} observations"
        )
    for observation in observations:
        ToolObservation.model_validate(observation)

    steps = _mapping_sequence(state.get("successful_steps"), "successful_steps")
    if len(steps) > MAX_SPECIALIST_STEPS:
        raise ValueError(
            f"specialist checkpoint supports at most {MAX_SPECIALIST_STEPS} steps"
        )
    for step in steps:
        if set(step) != {"tool_name", "arguments", "argument_hash"}:
            raise ValueError("specialist step has an invalid checkpoint shape")
        _required_text(step.get("tool_name"), "step tool_name")
        _required_text(step.get("argument_hash"), "step argument_hash")
        _optional_mapping(step.get("arguments"), "step arguments")

    references = _mapping_sequence(state.get("evidence_refs"), "evidence_refs")
    if len(references) > MAX_SPECIALIST_EVIDENCE_REFS:
        raise ValueError(
            "specialist checkpoint supports at most "
            f"{MAX_SPECIALIST_EVIDENCE_REFS} evidence refs"
        )
    for reference in references:
        CanonicalEvidenceRef.model_validate(reference)

    fingerprints = _integer_mapping(
        state.get("loop_fingerprints"),
        "loop_fingerprints",
    )
    if len(fingerprints) > MAX_SPECIALIST_LOOP_FINGERPRINTS:
        raise ValueError(
            "specialist checkpoint supports at most "
            f"{MAX_SPECIALIST_LOOP_FINGERPRINTS} loop fingerprints"
        )
    if any(value < 0 for value in fingerprints.values()):
        raise ValueError("loop fingerprint counts cannot be negative")

    _optional_mapping(state.get("lifecycle"), "lifecycle")
    terminal = _optional_mapping(state.get("terminal_return"), "terminal_return")
    if terminal:
        result = SpecialistReturn.model_validate(terminal)
        if result.session_id != state.get("session_id"):
            raise ValueError("specialist return belongs to another session")
        if result.delegation_id != state.get("delegation_id"):
            raise ValueError("specialist return belongs to another delegation")
        if result.attempt_id != state.get("attempt_id"):
            raise ValueError("specialist return belongs to another attempt")
        if result.role != state.get("role"):
            raise ValueError("specialist return role does not match checkpoint")

    _reject_sensitive_keys(state)
    encoded = _json_bytes(state)
    if len(encoded) > MAX_SPECIALIST_CHECKPOINT_BYTES:
        raise ValueError(
            f"specialist checkpoint is {len(encoded)} bytes; "
            f"limit is {MAX_SPECIALIST_CHECKPOINT_BYTES}"
        )


def checkpoint_safe_observation(
    observation: ToolObservation,
) -> ToolObservation:
    """Return a persistence-safe projection of one model-visible observation.

    Complete source, repository excerpts, candidate file content, and command
    output are deliberately removed. Their hashes, identities, errors, and
    canonical evidence refs remain available for recovery and audit.
    """
    return observation.model_copy(
        update={"summary": _redact_sensitive_values(observation.summary)}
    )


def checkpoint_step(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a safe successful-step record with an exact argument digest."""
    normalized = dict(arguments)
    return {
        "tool_name": _required_text(tool_name, "tool_name"),
        "arguments": _redact_sensitive_values(normalized),
        "argument_hash": json_payload_hash(normalized),
    }


def specialist_checkpoint_digest(state: Mapping[str, Any]) -> str:
    """Return a stable digest after complete specialist-state validation."""
    validate_specialist_checkpoint_state(state)
    return json_payload_hash(dict(state))


def _redact_sensitive_values(value: object) -> Any:
    """Recursively remove sensitive payload fields without hiding structure."""
    if isinstance(value, Mapping):
        projected: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = key.casefold()
            if normalized in _SENSITIVE_EXACT_KEYS or any(
                part in normalized for part in _SENSITIVE_KEY_PARTS
            ):
                continue
            projected[key] = _redact_sensitive_values(item)
        return projected
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_redact_sensitive_values(item) for item in value]
    return value


def _reject_sensitive_keys(value: object, *, path: str = "state") -> None:
    """Reject sensitive fields that bypassed the explicit projection."""
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = key.casefold()
            if normalized in _SENSITIVE_EXACT_KEYS or any(
                part in normalized for part in _SENSITIVE_KEY_PARTS
            ):
                raise ValueError(
                    f"specialist checkpoint key is forbidden: {path}.{key}"
                )
            _reject_sensitive_keys(item, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            _reject_sensitive_keys(item, path=f"{path}[{index}]")


def _required_text(value: object, label: str) -> str:
    """Normalize and require one text identity."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _optional_mapping(value: object, label: str) -> Mapping[str, Any]:
    """Normalize an optional JSON object."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _mapping_sequence(
    value: object,
    label: str,
) -> tuple[Mapping[str, Any], ...]:
    """Normalize an optional sequence of JSON objects."""
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a list")
    if any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must contain only objects")
    return tuple(dict(item) for item in value)


def _integer_mapping(value: object, label: str) -> dict[str, int]:
    """Normalize an optional string-to-integer mapping."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"{label} values must be integers")
        result[str(key)] = item
    return result


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    """Serialize exact JSON-native state without permissive coercion."""
    try:
        return json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("specialist checkpoint state must be JSON-native") from exc
