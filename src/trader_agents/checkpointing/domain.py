"""Bounded operational checkpoint state for model-backed research agents.

Checkpoint rows are resumable runtime state, not canonical research evidence.
They retain public decisions, exact identities, counters, and canonical refs but
never prompts, hidden reasoning, credentials, source code, or raw transcripts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any, TypedDict

from trader_research.foundation import json_payload_hash

from trader_agents.contracts.domain import (
    BudgetUsage,
    CanonicalEvidenceRef,
    CoordinatorAgenda,
    CoordinatorDecision,
    PublicIssue,
    SpecialistDelegation,
    SpecialistReturn,
)


MAX_CHECKPOINT_BYTES = 256_000
MAX_DELEGATIONS = 32
MAX_SPECIALIST_RETURNS = 32
MAX_EVIDENCE_REFS = 64
MAX_LOOP_FINGERPRINTS = 128
MAX_CHECKPOINT_ISSUES = 64

_FORBIDDEN_KEY_PARTS = (
    "api_key",
    "credential",
    "hidden_reasoning",
    "password",
    "prompt",
    "raw_message",
    "raw_tool",
    "scratchpad",
    "secret",
    "source_code",
    "tool_transcript",
)


class AgentCheckpointState(TypedDict, total=False):
    """JSON-native LangGraph state for one coordinator or specialist thread."""

    session_id: str
    session_digest: str
    branch_id: str
    status: str
    phase: str
    coordinator_program_id: str
    model_profile_id: str
    tool_catalog_id: str
    agenda: dict[str, Any]
    delegations: list[dict[str, Any]]
    active_delegations: list[dict[str, Any]]
    specialist_returns: list[dict[str, Any]]
    accepted_return_digests: dict[str, str]
    decision: dict[str, Any]
    evidence_refs: list[dict[str, Any]]
    pending_interrupt: dict[str, Any]
    budget_usage: dict[str, Any]
    loop_fingerprints: dict[str, int]
    warnings: list[dict[str, Any]]
    blockers: list[dict[str, Any]]
    terminal_result: dict[str, Any]
    completed_task_ids: list[str]
    task_attempts: dict[str, int]
    branch_by_task: dict[str, str]
    review_cursor: int
    decision_receipt_ref: dict[str, Any]
    operator_response: dict[str, Any]
    next_sequence: int


def build_agent_checkpoint_state(
    *,
    session_id: str,
    session_digest: str,
    branch_id: str,
    coordinator_program_id: str,
    model_profile_id: str,
    tool_catalog_id: str,
) -> AgentCheckpointState:
    """Build validated initial coordinator state.

    Args:
        session_id: Exact immutable research-session identity.
        session_digest: Digest of the complete canonical session payload.
        branch_id: Root research branch identity.
        coordinator_program_id: Exact versioned coordinator program.
        model_profile_id: Exact versioned model profile.
        tool_catalog_id: Exact code-owned tool catalogue identity.

    Returns:
        Bounded JSON-native state ready for LangGraph persistence.
    """
    state: AgentCheckpointState = {
        "session_id": _required_text(session_id, "session_id"),
        "session_digest": _required_text(session_digest, "session_digest"),
        "branch_id": _required_text(branch_id, "branch_id"),
        "status": "ready",
        "phase": "interpret",
        "coordinator_program_id": _required_text(
            coordinator_program_id,
            "coordinator_program_id",
        ),
        "model_profile_id": _required_text(model_profile_id, "model_profile_id"),
        "tool_catalog_id": _required_text(tool_catalog_id, "tool_catalog_id"),
        "agenda": {},
        "delegations": [],
        "active_delegations": [],
        "specialist_returns": [],
        "accepted_return_digests": {},
        "decision": {},
        "evidence_refs": [],
        "pending_interrupt": {},
        "budget_usage": BudgetUsage().model_dump(mode="json"),
        "loop_fingerprints": {},
        "warnings": [],
        "blockers": [],
        "terminal_result": {},
        "completed_task_ids": [],
        "task_attempts": {},
        "branch_by_task": {},
        "review_cursor": 0,
        "decision_receipt_ref": {},
        "operator_response": {},
        "next_sequence": 1,
    }
    validate_agent_checkpoint_state(state)
    return state


def validate_agent_checkpoint_state(state: Mapping[str, Any]) -> None:
    """Reject unsafe, inconsistent, or unbounded operational state.

    Args:
        state: Candidate JSON-native checkpoint mapping.

    Raises:
        ValueError: If the state contains forbidden content, invalid contracts,
            inconsistent identities, or exceeds a checkpoint bound.
    """
    allowed_fields = set(AgentCheckpointState.__annotations__)
    unknown_fields = set(state) - allowed_fields
    if unknown_fields:
        raise ValueError(
            "checkpoint has unknown fields: " + ", ".join(sorted(unknown_fields))
        )
    for key in (
        "session_id",
        "session_digest",
        "branch_id",
        "status",
        "phase",
        "coordinator_program_id",
        "model_profile_id",
        "tool_catalog_id",
    ):
        _required_text(state.get(key), key)
    next_sequence = state.get("next_sequence", 1)
    if isinstance(next_sequence, bool) or not isinstance(next_sequence, int):
        raise ValueError("next_sequence must be an integer")
    if next_sequence <= 0:
        raise ValueError("next_sequence must be positive")
    review_cursor = state.get("review_cursor", 0)
    if isinstance(review_cursor, bool) or not isinstance(review_cursor, int):
        raise ValueError("review_cursor must be an integer")
    if review_cursor < 0:
        raise ValueError("review_cursor cannot be negative")

    delegations = _mapping_sequence(state.get("delegations"), "delegations")
    active_delegations = _mapping_sequence(
        state.get("active_delegations"),
        "active_delegations",
    )
    returns = _mapping_sequence(
        state.get("specialist_returns"),
        "specialist_returns",
    )
    evidence = _mapping_sequence(state.get("evidence_refs"), "evidence_refs")
    if len(delegations) > MAX_DELEGATIONS:
        raise ValueError(f"checkpoint supports at most {MAX_DELEGATIONS} delegations")
    if len(active_delegations) > MAX_DELEGATIONS:
        raise ValueError(
            f"checkpoint supports at most {MAX_DELEGATIONS} active delegations"
        )
    if len(returns) > MAX_SPECIALIST_RETURNS:
        raise ValueError(
            f"checkpoint supports at most {MAX_SPECIALIST_RETURNS} specialist returns"
        )
    if len(evidence) > MAX_EVIDENCE_REFS:
        raise ValueError(
            f"checkpoint supports at most {MAX_EVIDENCE_REFS} evidence refs"
        )
    for payload in delegations:
        delegation = SpecialistDelegation.model_validate(payload)
        _require_session_identity(state, delegation.session_id, "delegation")
    known_delegation_ids = {
        SpecialistDelegation.model_validate(payload).delegation_id
        for payload in delegations
    }
    active_ids = set()
    for payload in active_delegations:
        delegation = SpecialistDelegation.model_validate(payload)
        _require_session_identity(state, delegation.session_id, "active delegation")
        if delegation.delegation_id not in known_delegation_ids:
            raise ValueError("active delegation is absent from delegation history")
        active_ids.add(delegation.delegation_id)
    if len(active_ids) != len(active_delegations):
        raise ValueError("active delegation identities must be unique")
    for payload in returns:
        specialist_return = SpecialistReturn.model_validate(payload)
        _require_session_identity(state, specialist_return.session_id, "return")
    for payload in evidence:
        CanonicalEvidenceRef.model_validate(payload)
    receipt_ref = _optional_mapping(
        state.get("decision_receipt_ref"),
        "decision_receipt_ref",
    )
    if receipt_ref:
        CanonicalEvidenceRef.model_validate(receipt_ref)

    agenda = _optional_mapping(state.get("agenda"), "agenda")
    if agenda:
        CoordinatorAgenda.model_validate(agenda)
    decision = _optional_mapping(state.get("decision"), "decision")
    if decision:
        CoordinatorDecision.model_validate(decision)
    pending_interrupt = _optional_mapping(
        state.get("pending_interrupt"),
        "pending_interrupt",
    )
    _validate_interrupt(pending_interrupt)
    _validate_operator_response(
        _optional_mapping(state.get("operator_response"), "operator_response")
    )
    BudgetUsage.model_validate(
        _optional_mapping(state.get("budget_usage"), "budget_usage")
    )

    fingerprints = _integer_mapping(
        state.get("loop_fingerprints"),
        "loop_fingerprints",
    )
    if len(fingerprints) > MAX_LOOP_FINGERPRINTS:
        raise ValueError(
            f"checkpoint supports at most {MAX_LOOP_FINGERPRINTS} loop fingerprints"
        )
    if any(value < 0 for value in fingerprints.values()):
        raise ValueError("loop fingerprint counts cannot be negative")
    attempts = _integer_mapping(state.get("task_attempts"), "task_attempts")
    if any(value < 0 for value in attempts.values()):
        raise ValueError("task attempt counts cannot be negative")
    completed = _text_sequence(
        state.get("completed_task_ids"),
        "completed_task_ids",
    )
    if len(set(completed)) != len(completed):
        raise ValueError("completed_task_ids must be unique")
    branches = _optional_mapping(state.get("branch_by_task"), "branch_by_task")
    if any(
        not str(key).strip() or not str(value).strip()
        for key, value in branches.items()
    ):
        raise ValueError("branch_by_task requires non-empty string identities")

    issue_count = 0
    for key in ("warnings", "blockers"):
        issues = _mapping_sequence(state.get(key), key)
        issue_count += len(issues)
        for issue in issues:
            PublicIssue.model_validate(issue)
    if issue_count > MAX_CHECKPOINT_ISSUES:
        raise ValueError(
            f"checkpoint supports at most {MAX_CHECKPOINT_ISSUES} public issues"
        )

    _reject_forbidden_keys(state)
    encoded = _json_bytes(state)
    if len(encoded) > MAX_CHECKPOINT_BYTES:
        raise ValueError(
            f"checkpoint is {len(encoded)} bytes; limit is {MAX_CHECKPOINT_BYTES}"
        )


def agent_checkpoint_digest(state: Mapping[str, Any]) -> str:
    """Return a stable digest after validating the complete state."""
    validate_agent_checkpoint_state(state)
    return json_payload_hash(dict(state))


def coordinator_thread_config(session_id: str) -> dict[str, Any]:
    """Build isolated LangGraph configuration for one coordinator thread."""
    identity = _required_text(session_id, "session_id")
    return {
        "configurable": {
            "thread_id": f"agent-session:{identity}:coordinator",
        }
    }


def specialist_thread_config(
    *,
    session_id: str,
    delegation_id: str,
) -> dict[str, Any]:
    """Build isolated LangGraph configuration for one specialist invocation."""
    session = _required_text(session_id, "session_id")
    delegation = _required_text(delegation_id, "delegation_id")
    return {
        "configurable": {
            "thread_id": (f"agent-session:{session}:specialist:{delegation}"),
        }
    }


def agent_public_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return the bounded operator-visible projection of checkpoint state."""
    validate_agent_checkpoint_state(state)
    return {
        key: state.get(key)
        for key in (
            "session_id",
            "branch_id",
            "status",
            "phase",
            "coordinator_program_id",
            "model_profile_id",
            "tool_catalog_id",
            "agenda",
            "delegations",
            "active_delegations",
            "specialist_returns",
            "decision",
            "evidence_refs",
            "pending_interrupt",
            "budget_usage",
            "warnings",
            "blockers",
            "terminal_result",
            "completed_task_ids",
            "task_attempts",
            "branch_by_task",
            "review_cursor",
            "decision_receipt_ref",
            "operator_response",
            "next_sequence",
        )
    }


def _validate_interrupt(payload: Mapping[str, Any]) -> None:
    """Validate the deliberately small operator-interrupt record."""
    if not payload:
        return
    allowed = {"kind", "question", "requested_action", "resume_schema"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(
            "pending_interrupt has unknown fields: " + ", ".join(sorted(unknown))
        )
    _required_text(payload.get("kind"), "interrupt kind")
    _required_text(payload.get("question"), "interrupt question")
    _required_text(payload.get("requested_action"), "interrupt requested_action")
    resume_schema = payload.get("resume_schema")
    if resume_schema is not None and not isinstance(resume_schema, Mapping):
        raise ValueError("interrupt resume_schema must be an object")


def _validate_operator_response(payload: Mapping[str, Any]) -> None:
    """Validate one bounded public response to an operator interrupt."""
    if not payload:
        return
    allowed = {"approved", "answer", "operator_id"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(
            "operator_response has unknown fields: " + ", ".join(sorted(unknown))
        )
    if not isinstance(payload.get("approved"), bool):
        raise ValueError("operator_response.approved must be a boolean")
    answer = _required_text(payload.get("answer"), "operator response answer")
    if len(answer) > 2_000:
        raise ValueError("operator response answer exceeds 2000 characters")
    _required_text(payload.get("operator_id"), "operator response operator_id")


def _require_session_identity(
    state: Mapping[str, Any],
    candidate: str,
    label: str,
) -> None:
    """Require nested values to belong to the checkpoint session."""
    if candidate != state.get("session_id"):
        raise ValueError(f"{label} belongs to another research session")


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
    """Normalize an optional string-to-non-boolean-integer mapping."""
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


def _text_sequence(value: object, label: str) -> tuple[str, ...]:
    """Normalize an optional sequence of non-empty text identities."""
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a list")
    normalized = tuple(str(item).strip() for item in value)
    if any(not item for item in normalized):
        raise ValueError(f"{label} contains an empty value")
    return normalized


def _reject_forbidden_keys(value: object, *, path: str = "state") -> None:
    """Recursively reject fields that could persist private/raw content."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower()
            if any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
                raise ValueError(f"checkpoint key is forbidden: {path}.{key}")
            _reject_forbidden_keys(item, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            _reject_forbidden_keys(item, path=f"{path}[{index}]")


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
        raise ValueError("checkpoint state must be JSON-native") from exc
