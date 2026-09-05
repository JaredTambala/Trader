"""Typed public evidence for model-backed research coordination.

These contracts deliberately exclude prompts, hidden reasoning, raw model
messages, credentials, and complete tool transcripts. They preserve only the
operator-approved session boundary and bounded public decisions needed for
audit, recovery, and canonical handoff.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from trader_research.foundation import json_payload_hash, jsonable, stable_research_id
from trader_research.governance.handoffs import ArtifactReportRef, ResearchIssue


_SESSION_FIELDS = frozenset(
    {
        "artifact_type",
        "schema_version",
        "session_id",
        "session_digest",
        "objective",
        "success_definition",
        "operator_id",
        "approval_policy",
        "scope_envelope",
        "implementation_specification",
        "implementation_ref",
        "python_quality_guide",
        "model_profile_id",
        "agent_program_ids",
        "tool_catalog_id",
        "budget",
        "metadata",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "artifact_type",
        "schema_version",
        "receipt_id",
        "decision_digest",
        "session_id",
        "branch_id",
        "sequence",
        "actor",
        "program_id",
        "model_profile_id",
        "action",
        "status",
        "summary",
        "delegation_id",
        "attempt_id",
        "evidence_refs",
        "budget_used",
        "blockers",
        "next_actions",
        "metadata",
    }
)


class AgentDecisionStatus(str, Enum):
    """Lifecycle effect of one accepted public agent decision."""

    ACCEPTED = "accepted"
    AWAITING_OPERATOR = "awaiting_operator"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class AgentBudget:
    """Hard operating limits approved for one research session.

    Attributes:
        max_model_calls: Maximum model invocations across the session.
        max_tool_calls: Maximum MCP calls across all agents.
        max_tokens: Maximum aggregate model input and output tokens.
        max_duration_seconds: Maximum elapsed execution time.
        max_mutations: Maximum accepted mutating MCP calls.
        max_revisions: Maximum coordinator or candidate revision attempts.
        concurrency_limit: Maximum concurrent specialist/tool work items.
    """

    max_model_calls: int
    max_tool_calls: int
    max_tokens: int
    max_duration_seconds: int
    max_mutations: int
    max_revisions: int
    concurrency_limit: int

    def __post_init__(self) -> None:
        """Reject non-positive ceilings and unsupported concurrency."""
        positive = {
            "max_model_calls": self.max_model_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_tokens": self.max_tokens,
            "max_duration_seconds": self.max_duration_seconds,
            "concurrency_limit": self.concurrency_limit,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_mutations < 0 or self.max_revisions < 0:
            raise ValueError("mutation and revision limits cannot be negative")
        if self.concurrency_limit > 8:
            raise ValueError("concurrency_limit cannot exceed 8")

    def to_dict(self) -> dict[str, int]:
        """Return stable JSON-native budget limits."""
        return {
            "max_model_calls": self.max_model_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_tokens": self.max_tokens,
            "max_duration_seconds": self.max_duration_seconds,
            "max_mutations": self.max_mutations,
            "max_revisions": self.max_revisions,
            "concurrency_limit": self.concurrency_limit,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AgentBudget:
        """Parse strict JSON-compatible budget limits.

        Args:
            payload: Mapping containing every session budget ceiling.

        Returns:
            Validated immutable budget.
        """
        _reject_unknown_fields(payload, frozenset(cls.__dataclass_fields__), "agent budget")
        return cls(
            max_model_calls=_integer(payload, "max_model_calls"),
            max_tool_calls=_integer(payload, "max_tool_calls"),
            max_tokens=_integer(payload, "max_tokens"),
            max_duration_seconds=_integer(payload, "max_duration_seconds"),
            max_mutations=_integer(payload, "max_mutations"),
            max_revisions=_integer(payload, "max_revisions"),
            concurrency_limit=_integer(payload, "concurrency_limit"),
        )


@dataclass(frozen=True)
class AgentBudgetUsage:
    """Cumulative public resource use at one accepted decision boundary."""

    model_calls: int = 0
    tool_calls: int = 0
    tokens: int = 0
    duration_ms: int = 0
    mutations: int = 0
    revisions: int = 0

    def __post_init__(self) -> None:
        """Reject negative cumulative counters."""
        if any(value < 0 for value in self.to_dict().values()):
            raise ValueError("agent budget usage cannot be negative")

    def to_dict(self) -> dict[str, int]:
        """Return stable JSON-native cumulative counters."""
        return {
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "tokens": self.tokens,
            "duration_ms": self.duration_ms,
            "mutations": self.mutations,
            "revisions": self.revisions,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AgentBudgetUsage:
        """Parse strict cumulative usage counters."""
        _reject_unknown_fields(payload, frozenset(cls.__dataclass_fields__), "agent budget usage")
        return cls(
            model_calls=_integer(payload, "model_calls", default=0),
            tool_calls=_integer(payload, "tool_calls", default=0),
            tokens=_integer(payload, "tokens", default=0),
            duration_ms=_integer(payload, "duration_ms", default=0),
            mutations=_integer(payload, "mutations", default=0),
            revisions=_integer(payload, "revisions", default=0),
        )

    def validate_within(self, budget: AgentBudget) -> None:
        """Reject cumulative use that exceeds the approved session budget.

        Args:
            budget: Approved hard limits for the owning session.

        Raises:
            ValueError: If any public counter exceeds its corresponding limit.
        """
        checks = {
            "model_calls": (self.model_calls, budget.max_model_calls),
            "tool_calls": (self.tool_calls, budget.max_tool_calls),
            "tokens": (self.tokens, budget.max_tokens),
            "duration_ms": (self.duration_ms, budget.max_duration_seconds * 1000),
            "mutations": (self.mutations, budget.max_mutations),
            "revisions": (self.revisions, budget.max_revisions),
        }
        exceeded = [name for name, (used, limit) in checks.items() if used > limit]
        if exceeded:
            raise ValueError(f"agent budget exceeded: {', '.join(exceeded)}")


@dataclass(frozen=True)
class ResearchSession:
    """Immutable operator-approved boundary for one agentic research run.

    The natural-language objective and all external content are treated as data.
    Authority comes only from the structured policy, scope, build, model, tool,
    and budget fields captured here.
    """

    artifact_type: ClassVar[str] = "research_session"
    schema_version: ClassVar[str] = "1"

    session_id: str
    objective: str
    success_definition: str
    operator_id: str
    approval_policy: Mapping[str, Any]
    scope_envelope: Mapping[str, Any]
    implementation_specification: Mapping[str, Any] | None
    implementation_ref: str | None
    python_quality_guide: str
    model_profile_id: str
    agent_program_ids: tuple[str, ...]
    tool_catalog_id: str
    budget: AgentBudget
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate identity, authorities, model/tool pins, and build input."""
        for value, label in (
            (self.session_id, "session_id"),
            (self.objective, "objective"),
            (self.success_definition, "success_definition"),
            (self.operator_id, "operator_id"),
            (self.python_quality_guide, "python_quality_guide"),
            (self.model_profile_id, "model_profile_id"),
            (self.tool_catalog_id, "tool_catalog_id"),
        ):
            _required_text(value, label)
        if bool(self.implementation_specification) == bool(self.implementation_ref):
            raise ValueError(
                "exactly one implementation_specification or implementation_ref is required"
            )
        if not self.agent_program_ids:
            raise ValueError("agent_program_ids are required")
        if len(set(self.agent_program_ids)) != len(self.agent_program_ids):
            raise ValueError("agent_program_ids must be unique")
        for program_id in self.agent_program_ids:
            _required_text(program_id, "agent_program_id")
        _json_mapping(self.approval_policy, "approval_policy")
        _json_mapping(self.scope_envelope, "scope_envelope")
        if self.implementation_specification is not None:
            _json_mapping(
                self.implementation_specification,
                "implementation_specification",
            )
        _json_mapping(self.metadata, "metadata")

    @property
    def session_digest(self) -> str:
        """Return the full digest of the immutable session content."""
        return json_payload_hash(self._identity_payload())

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete canonical session payload."""
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            **self._identity_payload(),
            "session_digest": self.session_digest,
        }

    def _identity_payload(self) -> dict[str, Any]:
        """Return fields that determine immutable session identity."""
        return {
            "session_id": self.session_id,
            "objective": self.objective,
            "success_definition": self.success_definition,
            "operator_id": self.operator_id,
            "approval_policy": jsonable(self.approval_policy),
            "scope_envelope": jsonable(self.scope_envelope),
            "implementation_specification": jsonable(
                self.implementation_specification
            ),
            "implementation_ref": self.implementation_ref,
            "python_quality_guide": self.python_quality_guide,
            "model_profile_id": self.model_profile_id,
            "agent_program_ids": list(self.agent_program_ids),
            "tool_catalog_id": self.tool_catalog_id,
            "budget": self.budget.to_dict(),
            "metadata": jsonable(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResearchSession:
        """Parse and verify one canonical research-session payload.

        Args:
            payload: Strict JSON-compatible session mapping.

        Returns:
            Validated immutable session.
        """
        _reject_unknown_fields(payload, _SESSION_FIELDS, "research session")
        _expect_constant(payload, "artifact_type", cls.artifact_type)
        _expect_constant(payload, "schema_version", cls.schema_version)
        implementation = payload.get("implementation_specification")
        session = cls(
            session_id=str(payload.get("session_id") or ""),
            objective=str(payload.get("objective") or ""),
            success_definition=str(payload.get("success_definition") or ""),
            operator_id=str(payload.get("operator_id") or ""),
            approval_policy=_mapping(payload.get("approval_policy")),
            scope_envelope=_mapping(payload.get("scope_envelope")),
            implementation_specification=(
                _mapping(implementation) if implementation is not None else None
            ),
            implementation_ref=_optional_text(payload.get("implementation_ref")),
            python_quality_guide=str(payload.get("python_quality_guide") or ""),
            model_profile_id=str(payload.get("model_profile_id") or ""),
            agent_program_ids=_text_tuple(payload.get("agent_program_ids")),
            tool_catalog_id=str(payload.get("tool_catalog_id") or ""),
            budget=AgentBudget.from_dict(_mapping(payload.get("budget"))),
            metadata=_mapping(payload.get("metadata")),
        )
        supplied_digest = str(payload.get("session_digest") or "")
        if supplied_digest and supplied_digest != session.session_digest:
            raise ValueError("research session_digest does not match session content")
        return session


@dataclass(frozen=True)
class AgentDecisionReceipt:
    """Immutable public receipt for one accepted coordinator transition."""

    artifact_type: ClassVar[str] = "agent_decision_receipt"
    schema_version: ClassVar[str] = "1"

    receipt_id: str
    session_id: str
    branch_id: str
    sequence: int
    actor: str
    program_id: str
    model_profile_id: str
    action: str
    status: AgentDecisionStatus
    summary: str
    delegation_id: str | None = None
    attempt_id: str | None = None
    evidence_refs: tuple[ArtifactReportRef, ...] = ()
    budget_used: AgentBudgetUsage = field(default_factory=AgentBudgetUsage)
    blockers: tuple[ResearchIssue, ...] = ()
    next_actions: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate public decision identity, status, and bounded contents."""
        for value, label in (
            (self.receipt_id, "receipt_id"),
            (self.session_id, "session_id"),
            (self.branch_id, "branch_id"),
            (self.actor, "actor"),
            (self.program_id, "program_id"),
            (self.model_profile_id, "model_profile_id"),
            (self.action, "action"),
            (self.summary, "summary"),
        ):
            _required_text(value, label)
        if self.sequence <= 0:
            raise ValueError("decision sequence must be positive")
        if len(self.summary) > 4_000:
            raise ValueError("decision summary exceeds 4000 characters")
        if len(self.evidence_refs) > 32:
            raise ValueError("decision receipt supports at most 32 evidence refs")
        if len({item.uri for item in self.evidence_refs}) != len(self.evidence_refs):
            raise ValueError("decision evidence refs must be unique")
        if len(set(self.next_actions)) != len(self.next_actions):
            raise ValueError("decision next_actions must be unique")
        for action in self.next_actions:
            _required_text(action, "next_action")
        if self.status is AgentDecisionStatus.AWAITING_OPERATOR and not self.blockers:
            raise ValueError("awaiting_operator decisions require a structured blocker")
        if self.status in {
            AgentDecisionStatus.BLOCKED,
            AgentDecisionStatus.CANCELLED,
        } and not self.blockers:
            raise ValueError(
                "blocked or cancelled decisions require a structured blocker"
            )
        _json_mapping(self.metadata, "metadata")

    @property
    def decision_digest(self) -> str:
        """Return the full digest of the immutable public decision content."""
        return json_payload_hash(self._identity_payload())

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete canonical decision receipt."""
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            **self._identity_payload(),
            "decision_digest": self.decision_digest,
        }

    def _identity_payload(self) -> dict[str, Any]:
        """Return fields that determine immutable receipt identity."""
        return {
            "receipt_id": self.receipt_id,
            "session_id": self.session_id,
            "branch_id": self.branch_id,
            "sequence": self.sequence,
            "actor": self.actor,
            "program_id": self.program_id,
            "model_profile_id": self.model_profile_id,
            "action": self.action,
            "status": self.status.value,
            "summary": self.summary,
            "delegation_id": self.delegation_id,
            "attempt_id": self.attempt_id,
            "evidence_refs": [item.to_dict() for item in self.evidence_refs],
            "budget_used": self.budget_used.to_dict(),
            "blockers": [item.to_dict() for item in self.blockers],
            "next_actions": list(self.next_actions),
            "metadata": jsonable(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AgentDecisionReceipt:
        """Parse and verify one canonical public decision receipt."""
        _reject_unknown_fields(payload, _RECEIPT_FIELDS, "agent decision receipt")
        _expect_constant(payload, "artifact_type", cls.artifact_type)
        _expect_constant(payload, "schema_version", cls.schema_version)
        try:
            status = AgentDecisionStatus(str(payload.get("status") or ""))
        except ValueError as exc:
            raise ValueError("unsupported agent decision status") from exc
        receipt = cls(
            receipt_id=str(payload.get("receipt_id") or ""),
            session_id=str(payload.get("session_id") or ""),
            branch_id=str(payload.get("branch_id") or ""),
            sequence=_integer(payload, "sequence"),
            actor=str(payload.get("actor") or ""),
            program_id=str(payload.get("program_id") or ""),
            model_profile_id=str(payload.get("model_profile_id") or ""),
            action=str(payload.get("action") or ""),
            status=status,
            summary=str(payload.get("summary") or ""),
            delegation_id=_optional_text(payload.get("delegation_id")),
            attempt_id=_optional_text(payload.get("attempt_id")),
            evidence_refs=tuple(
                ArtifactReportRef.from_dict(item)
                for item in _mapping_sequence(payload.get("evidence_refs"))
            ),
            budget_used=AgentBudgetUsage.from_dict(
                _mapping(payload.get("budget_used"))
            ),
            blockers=tuple(
                ResearchIssue.from_dict(item)
                for item in _mapping_sequence(payload.get("blockers"))
            ),
            next_actions=_text_tuple(payload.get("next_actions")),
            metadata=_mapping(payload.get("metadata")),
        )
        supplied_digest = str(payload.get("decision_digest") or "")
        if supplied_digest and supplied_digest != receipt.decision_digest:
            raise ValueError("decision_digest does not match receipt content")
        expected_id = _receipt_id(receipt._identity_payload(), receipt_id=None)
        if receipt.receipt_id != expected_id:
            raise ValueError("receipt_id does not match decision content")
        return receipt


def build_agent_decision_receipt(
    *,
    session_id: str,
    branch_id: str,
    sequence: int,
    actor: str,
    program_id: str,
    model_profile_id: str,
    action: str,
    status: AgentDecisionStatus,
    summary: str,
    delegation_id: str | None = None,
    attempt_id: str | None = None,
    evidence_refs: Sequence[ArtifactReportRef] = (),
    budget_used: AgentBudgetUsage | None = None,
    blockers: Sequence[ResearchIssue] = (),
    next_actions: Sequence[str] = (),
    metadata: Mapping[str, Any] | None = None,
) -> AgentDecisionReceipt:
    """Build a content-addressed decision receipt from normalized fields.

    Args:
        session_id: Owning immutable research-session identity.
        branch_id: Exact research branch receiving the transition.
        sequence: Positive branch-local coordinator sequence.
        actor: Registered public actor responsible for the transition.
        program_id: Exact agent-program identity used for the decision.
        model_profile_id: Exact configured model-profile identity.
        action: Structured coordinator or specialist-return action.
        status: Public lifecycle effect of the action.
        summary: Bounded public rationale without hidden reasoning.
        delegation_id: Optional delegation identity affected by the decision.
        attempt_id: Optional immutable specialist/candidate attempt identity.
        evidence_refs: Canonical evidence cited by the decision.
        budget_used: Cumulative public resource counters.
        blockers: Structured blockers or operator questions.
        next_actions: Bounded advisory next-action identifiers.
        metadata: Optional public trace and lineage metadata.

    Returns:
        Validated content-addressed receipt.
    """
    provisional = AgentDecisionReceipt(
        receipt_id="pending",
        session_id=session_id,
        branch_id=branch_id,
        sequence=sequence,
        actor=actor,
        program_id=program_id,
        model_profile_id=model_profile_id,
        action=action,
        status=status,
        summary=summary,
        delegation_id=delegation_id,
        attempt_id=attempt_id,
        evidence_refs=tuple(evidence_refs),
        budget_used=budget_used or AgentBudgetUsage(),
        blockers=tuple(blockers),
        next_actions=tuple(next_actions),
        metadata=dict(metadata or {}),
    )
    receipt_id = _receipt_id(provisional._identity_payload(), receipt_id="pending")
    return AgentDecisionReceipt(
        receipt_id=receipt_id,
        session_id=provisional.session_id,
        branch_id=provisional.branch_id,
        sequence=provisional.sequence,
        actor=provisional.actor,
        program_id=provisional.program_id,
        model_profile_id=provisional.model_profile_id,
        action=provisional.action,
        status=provisional.status,
        summary=provisional.summary,
        delegation_id=provisional.delegation_id,
        attempt_id=provisional.attempt_id,
        evidence_refs=provisional.evidence_refs,
        budget_used=provisional.budget_used,
        blockers=provisional.blockers,
        next_actions=provisional.next_actions,
        metadata=provisional.metadata,
    )


def _receipt_id(payload: Mapping[str, Any], receipt_id: str | None) -> str:
    """Derive receipt identity after removing its provisional identifier."""
    identity = dict(payload)
    if receipt_id is None:
        identity.pop("receipt_id", None)
    elif identity.get("receipt_id") == receipt_id:
        identity.pop("receipt_id", None)
    return stable_research_id("agent_decision", identity)


def _required_text(value: object, label: str) -> str:
    """Normalize and require one bounded text field."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _optional_text(value: object) -> str | None:
    """Normalize optional text without inventing empty values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _integer(
    payload: Mapping[str, Any],
    key: str,
    *,
    default: int | None = None,
) -> int:
    """Parse an exact integer while rejecting booleans and floats."""
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    """Return an exact mapping or reject the boundary value."""
    if not isinstance(value, Mapping):
        raise ValueError("expected a JSON object")
    return dict(value)


def _mapping_sequence(value: object) -> tuple[Mapping[str, Any], ...]:
    """Parse a sequence containing only JSON object values."""
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("expected a sequence of JSON objects")
    if any(not isinstance(item, Mapping) for item in value):
        raise ValueError("expected a sequence of JSON objects")
    return tuple(dict(item) for item in value)


def _text_tuple(value: object) -> tuple[str, ...]:
    """Parse a sequence of non-empty text values."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("expected a sequence of text values")
    return tuple(_required_text(item, "sequence item") for item in value)


def _json_mapping(value: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    """Require a mapping that normalizes to a JSON object."""
    normalized = jsonable(value)
    if not isinstance(normalized, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return normalized


def _reject_unknown_fields(
    payload: Mapping[str, Any],
    allowed: frozenset[str],
    label: str,
) -> None:
    """Reject fields outside one explicit public schema."""
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _expect_constant(payload: Mapping[str, Any], key: str, expected: str) -> None:
    """Validate an optional serialized schema constant when present."""
    value = payload.get(key)
    if value is not None and value != expected:
        raise ValueError(f"{key} must be {expected}")
