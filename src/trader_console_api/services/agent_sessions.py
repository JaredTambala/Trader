"""Application service for the redacted Console agent-session workspace."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from trader.runtime.operator_control import is_human_operator_principal

from ..contracts import (
    AgentSessionBudgetLimits,
    AgentSessionBudgetUsage,
    AgentSessionCommandRecord,
    AgentSessionCommandName,
    AgentSessionCommandRequest,
    AgentSessionCommandsResponse,
    AgentSessionDelegation,
    AgentSessionEvidenceReference,
    AgentSessionEvent,
    AgentSessionHandoff,
    AgentSessionInterrupt,
    AgentSessionProjection,
    AgentSessionStatus,
    AgentSessionSpecialistStatus,
    AgentSessionTerminalDecision,
    PageInfo,
    TraderPrincipal,
)
from ..repositories.agent_sessions import (
    AgentSessionCommandConflict,
    AgentSessionNotFound,
    AgentSessionRepository,
    AgentSessionSource,
)
from ..repositories.agent_sessions_schema import AgentSessionStorageUnavailable
from ..repositories.database import ConsoleDatabaseUnavailable


class AgentSessionAuthorityError(RuntimeError):
    """The authenticated principal cannot inspect or command this session."""


AgentSessionDatabaseUnavailable = ConsoleDatabaseUnavailable
"""The configured database cannot provide the session projection."""


def _text(value: object, label: str, *, maximum: int = 4_000) -> str:
    """Normalize one bounded public text value."""
    result = str(value or "").strip()
    if not result:
        raise AgentSessionStorageUnavailable(f"agent session {label} is missing")
    if len(result) > maximum:
        raise AgentSessionStorageUnavailable(f"agent session {label} is too long")
    return result


def _status(value: object) -> AgentSessionStatus:
    """Map a producer lifecycle value to the closed Console vocabulary."""
    candidate = str(value or "")
    allowed = {
        "active",
        "ready",
        "running",
        "accepted",
        "awaiting_operator",
        "blocked",
        "cancelled",
        "failed",
        "terminal",
        "completed",
    }
    if candidate not in allowed:
        raise AgentSessionStorageUnavailable("agent session status is incompatible")
    return candidate  # type: ignore[return-value]


def _available_commands(
    status: AgentSessionStatus,
    *,
    has_runtime_state: bool,
    pending_interrupt: AgentSessionInterrupt | None,
) -> tuple[AgentSessionCommandName, ...]:
    """Expose only lifecycle intents admitted by the inspected public state."""
    if not has_runtime_state:
        return ("inspect",)
    if status == "awaiting_operator" and pending_interrupt is not None:
        return ("inspect", "resume", "cancel")
    if status in {"active", "ready", "running", "accepted"} and pending_interrupt is None:
        return ("inspect", "interrupt", "cancel")
    return ("inspect",)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    """Require one JSON object at the persistence boundary."""
    if not isinstance(value, Mapping):
        raise AgentSessionStorageUnavailable(f"agent session {label} must be an object")
    return value


def _budget_limits(payload: Mapping[str, Any]) -> AgentSessionBudgetLimits:
    """Normalize immutable session ceilings without exposing extra metadata."""
    try:
        return AgentSessionBudgetLimits.model_validate(dict(payload))
    except Exception as exc:
        raise AgentSessionStorageUnavailable("agent session budget is incompatible") from exc


def _budget_usage(payload: Mapping[str, Any] | None) -> AgentSessionBudgetUsage:
    """Normalize cumulative receipt counters to the public contract."""
    try:
        return AgentSessionBudgetUsage.model_validate(
            {
                "model_calls": int((payload or {}).get("model_calls", 0)),
                "tool_calls": int((payload or {}).get("tool_calls", 0)),
                "tokens": int((payload or {}).get("tokens", 0)),
                "duration_ms": int((payload or {}).get("duration_ms", 0)),
                "mutations": int((payload or {}).get("mutations", 0)),
                "revisions": int((payload or {}).get("revisions", 0)),
            }
        )
    except (TypeError, ValueError) as exc:
        raise AgentSessionStorageUnavailable("agent session budget usage is incompatible") from exc


def _counter(value: object, label: str) -> int:
    """Normalize one runtime counter or fail closed at the persistence boundary."""
    if isinstance(value, bool) or not isinstance(value, (int, str, float)):
        raise AgentSessionStorageUnavailable(f"agent session {label} is incompatible")
    try:
        result = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise AgentSessionStorageUnavailable(f"agent session {label} is incompatible") from exc
    if result < 0:
        raise AgentSessionStorageUnavailable(f"agent session {label} is negative")
    return result


def _reference(value: object) -> AgentSessionEvidenceReference:
    """Project a canonical reference while dropping arbitrary metadata."""
    raw = _mapping(value, "evidence reference")
    metadata = raw.get("metadata")
    metadata_mapping = metadata if isinstance(metadata, Mapping) else {}
    source_hash = metadata_mapping.get("source_hash")
    revision_value = metadata_mapping.get("revision", metadata_mapping.get("evidence_revision"))
    revision: int | None = None
    if revision_value is not None:
        try:
            revision = int(revision_value)
        except (TypeError, ValueError) as exc:
            raise AgentSessionStorageUnavailable("agent evidence revision is incompatible") from exc
    raw_status = str(raw.get("status") or metadata_mapping.get("status") or "available")
    if raw_status not in {"available", "stale", "missing", "unavailable", "incompatible"}:
        raise AgentSessionStorageUnavailable("agent evidence status is incompatible")
    try:
        return AgentSessionEvidenceReference(
            artifact_type=_text(raw.get("artifact_type"), "evidence artifact_type", maximum=100),
            artifact_id=_text(raw.get("artifact_id"), "evidence artifact_id", maximum=200),
            domain_owner=_text(raw.get("domain_owner"), "evidence domain_owner", maximum=100),
            uri=_text(raw.get("uri"), "evidence uri", maximum=500),
            revision=revision,
            status=cast(
                Literal["available", "stale", "missing", "unavailable", "incompatible"],
                raw_status,
            ),
            source_hash=str(source_hash) if source_hash is not None else None,
        )
    except Exception as exc:
        raise AgentSessionStorageUnavailable("agent evidence reference is incompatible") from exc


def _references(values: object) -> tuple[AgentSessionEvidenceReference, ...]:
    """Project a bounded sequence of canonical references with stable order."""
    if values is None:
        return ()
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise AgentSessionStorageUnavailable("agent evidence references must be a list")
    result: list[AgentSessionEvidenceReference] = []
    seen: set[str] = set()
    for value in values:
        reference = _reference(value)
        if reference.uri in seen:
            continue
        seen.add(reference.uri)
        result.append(reference)
    return tuple(result)


def _specialist_status(value: object) -> AgentSessionSpecialistStatus:
    """Normalize specialist outcomes while preserving partial and stale states."""
    candidate = str(value or "running")
    if candidate in {"completed", "complete", "ready"}:
        return "complete"
    if candidate in {"partial", "failed", "blocked", "stale", "unavailable", "running"}:
        return candidate  # type: ignore[return-value]
    raise AgentSessionStorageUnavailable("agent specialist status is incompatible")


def _scope_summary(value: object) -> dict[str, Any]:
    """Allowlist human-useful scope facts and reject unsafe fields."""
    scope = _mapping(value, "scope envelope")
    data_scope = scope.get("data_scope")
    source = data_scope if isinstance(data_scope, Mapping) else scope
    allowed = {
        "scope_id",
        "session_id",
        "asset_class",
        "symbols",
        "timeframe",
        "start",
        "end",
        "interval",
        "bar_type",
        "loading_approved",
        "max_loading_cost",
    }
    result: dict[str, Any] = {}
    for key in allowed:
        if key not in source:
            continue
        candidate = source[key]
        if isinstance(candidate, (str, int, float, bool)) or candidate is None:
            result[key] = candidate
        elif isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
            scalar_items = [item for item in candidate if isinstance(item, (str, int, float, bool))]
            if len(scalar_items) == len(candidate):
                result[key] = scalar_items[:64]
    items = source.get("items")
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        result["item_count"] = len(items)
        item_summaries: list[dict[str, Any]] = []
        for item in items[:64]:
            if not isinstance(item, Mapping):
                continue
            item_summary = {
                name: item[name]
                for name in ("item_id", "data_role", "asset_class", "data_type", "timeframe", "start", "end")
                if name in item and isinstance(item[name], (str, int, float, bool))
            }
            symbols = item.get("symbols")
            if isinstance(symbols, Sequence) and not isinstance(symbols, (str, bytes)):
                item_summary["symbols"] = [symbol for symbol in symbols[:64] if isinstance(symbol, str)]
            if item_summary:
                item_summaries.append(item_summary)
        if item_summaries:
            result["items"] = item_summaries
    return result


def _blocker_messages(value: object) -> tuple[str, ...]:
    """Project blocker messages only; issue details remain private."""
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AgentSessionStorageUnavailable("agent blockers must be a list")
    messages: list[str] = []
    for item in value:
        raw = item if isinstance(item, Mapping) else {}
        message = str(raw.get("message") or "").strip()
        if message:
            messages.append(message[:1_000])
    return tuple(messages[:16])


def _public_state(source: AgentSessionSource, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Validate one runtime inspection snapshot before using its public fields."""
    row = source.public_state
    if row is None:
        return None
    expected_digest = _text(payload.get("session_digest"), "session_digest", maximum=64)
    if (
        row.get("session_id") != payload.get("session_id")
        or row.get("session_digest") != expected_digest
        or row.get("operator_id") != payload.get("operator_id")
    ):
        raise AgentSessionStorageUnavailable("agent public state identity does not match the session")
    return _mapping(row.get("public_state"), "public state")


def _public_state_delegations(
    value: object,
    *,
    sequence: int,
) -> tuple[AgentSessionDelegation, ...]:
    """Project runtime delegation identities without task prompts or payloads."""
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AgentSessionStorageUnavailable("agent public delegations must be a list")
    result: list[AgentSessionDelegation] = []
    for raw in value[:32]:
        delegation = _mapping(raw, "public delegation")
        task = delegation.get("task")
        task_mapping = task if isinstance(task, Mapping) else {}
        role = str(task_mapping.get("role") or delegation.get("role") or "research_coordinator")
        if role not in {"data_research", "strategy_engineering", "research_coordinator"}:
            role = "research_coordinator"
        branch_id = _text(delegation.get("branch_id"), "delegation branch_id", maximum=200)
        delegation_id = _text(delegation.get("delegation_id"), "delegation_id", maximum=200)
        attempt_id = _text(delegation.get("attempt_id"), "attempt_id", maximum=200)
        question = task_mapping.get("question") or task_mapping.get("expected_information_gain")
        summary = _text(question, "delegation question", maximum=1200)
        result.append(
            AgentSessionDelegation(
                branch_id=branch_id,
                delegation_id=delegation_id,
                attempt_id=attempt_id,
                role=role,  # type: ignore[arg-type]
                status="running",
                sequence=sequence,
                summary=summary,
            )
        )
    return tuple(result)


def _build_projection(source: AgentSessionSource) -> AgentSessionProjection:
    """Build one redacted typed projection from canonical producer rows."""
    payload = _mapping(source.session.get("payload"), "payload")
    if source.session.get("session_id") != payload.get("session_id") or source.session.get("operator_id") != payload.get("operator_id"):
        raise AgentSessionStorageUnavailable("agent session row identity does not match the payload")
    digest = _text(payload.get("session_digest"), "session_digest", maximum=64)
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise AgentSessionStorageUnavailable("agent session digest is incompatible")
    budget = _budget_limits(_mapping(payload.get("budget"), "budget"))
    runtime_state = _public_state(source, payload)
    program_ids = payload.get("agent_program_ids")
    if not isinstance(program_ids, (list, tuple)) or not program_ids or any(not isinstance(item, str) or not item for item in program_ids):
        raise AgentSessionStorageUnavailable("agent session programs are incompatible")
    events: list[AgentSessionEvent] = []
    delegations: list[AgentSessionDelegation] = []
    evidence_refs: list[AgentSessionEvidenceReference] = []
    terminal: AgentSessionTerminalDecision | None = None
    pending_interrupt: AgentSessionInterrupt | None = None
    latest_by_branch: dict[str, Mapping[str, Any]] = {}
    for raw_receipt in source.receipts:
        receipt = _mapping(raw_receipt.get("payload"), "receipt payload")
        if (
            receipt.get("session_id") != payload.get("session_id")
            or receipt.get("program_id") not in program_ids
            or receipt.get("model_profile_id") != payload.get("model_profile_id")
        ):
            raise AgentSessionStorageUnavailable("agent receipt identity does not match the session")
        branch_id = _text(receipt.get("branch_id"), "receipt branch_id", maximum=200)
        sequence = int(receipt.get("sequence") or 0)
        if sequence <= 0:
            raise AgentSessionStorageUnavailable("agent receipt sequence is invalid")
        refs = _references(receipt.get("evidence_refs"))
        evidence_refs.extend(ref for ref in refs if ref.uri not in {item.uri for item in evidence_refs})
        metadata = _mapping(receipt.get("metadata"), "receipt metadata")
        raw_specialist_status = receipt.get("specialist_status") or metadata.get("specialist_status")
        if raw_specialist_status is None and receipt.get("status") in {
            "partial", "failed", "blocked", "stale", "unavailable", "completed", "complete", "ready"
        }:
            raw_specialist_status = receipt.get("status")
        specialist_status = _specialist_status(raw_specialist_status or "running")
        status = _status(
            "blocked"
            if specialist_status in {"partial", "failed", "blocked", "stale", "unavailable"}
            else receipt.get("status")
        )
        blockers = _blocker_messages(receipt.get("blockers"))
        next_actions = tuple(
            str(item).strip()[:200]
            for item in (receipt.get("next_actions") or ())
            if str(item).strip()
        )[:12]
        event = AgentSessionEvent(
            event_id=_text(receipt.get("receipt_id"), "receipt_id", maximum=200),
            session_id=_text(receipt.get("session_id"), "receipt session_id", maximum=200),
            branch_id=branch_id,
            sequence=sequence,
            event_type=_text(receipt.get("action"), "receipt action", maximum=100),
            status=status,
            summary=_text(receipt.get("summary"), "receipt summary"),
            delegation_id=(str(receipt["delegation_id"]) if receipt.get("delegation_id") else None),
            attempt_id=(str(receipt["attempt_id"]) if receipt.get("attempt_id") else None),
            evidence_refs=refs,
            budget_used=_budget_usage(receipt.get("budget_used")),
            blockers=blockers,
            next_actions=next_actions,
            recorded_at=(raw_receipt.get("created_at") if isinstance(raw_receipt.get("created_at"), datetime) else None),
        )
        events.append(event)
        latest = latest_by_branch.get(branch_id)
        if latest is None or int(latest.get("sequence") or 0) < sequence:
            latest_by_branch[branch_id] = receipt
        role = str(metadata.get("role") or "research_coordinator")
        if role not in {"data_research", "strategy_engineering", "research_coordinator"}:
            role = "research_coordinator"
        handoff: AgentSessionHandoff | None = None
        if receipt.get("delegation_id") and receipt.get("attempt_id"):
            digest_value = metadata.get("handoff_digest") or metadata.get("return_digest")
            if digest_value is not None and (
                not isinstance(digest_value, str) or len(digest_value) != 64
            ):
                raise AgentSessionStorageUnavailable("agent handoff digest is incompatible")
            handoff = AgentSessionHandoff(
                branch_id=branch_id,
                delegation_id=str(receipt["delegation_id"]),
                attempt_id=str(receipt["attempt_id"]),
                owner=str(metadata.get("owner") or role),
                status=specialist_status,
                digest=digest_value,
                artifact_refs=refs,
                blockers=blockers,
            )
        delegations.append(
            AgentSessionDelegation(
                branch_id=branch_id,
                delegation_id=(str(receipt["delegation_id"]) if receipt.get("delegation_id") else None),
                attempt_id=(str(receipt["attempt_id"]) if receipt.get("attempt_id") else None),
                role=role,  # type: ignore[arg-type]
                status=status,
                sequence=sequence,
                summary=_text(receipt.get("summary"), "delegation summary"),
                evidence_refs=refs,
                blockers=blockers,
                next_actions=next_actions,
                specialist_status=specialist_status,
                handoff=handoff,
            )
        )
        if status == "awaiting_operator" and blockers:
            pending_interrupt = AgentSessionInterrupt(
                kind="operator_input",
                question=blockers[0],
                requested_action=next_actions[0] if next_actions else "resume",
            )
        if status in {"terminal", "cancelled", "blocked", "failed", "completed"} and receipt.get("actor") == "Research Coordinator":
            terminal = AgentSessionTerminalDecision(
                branch_id=branch_id,
                sequence=sequence,
                status=status,
                action=_text(receipt.get("action"), "terminal action", maximum=100),
                summary=_text(receipt.get("summary"), "terminal summary"),
                evidence_refs=refs,
                blockers=blockers,
            )
    latest_events = sorted(events, key=lambda item: (item.branch_id, item.sequence))
    latest_usage = latest_events[-1].budget_used if latest_events else _budget_usage(None)
    latest_status: AgentSessionStatus = _status(source.session.get("status"))
    if latest_events:
        statuses = {event.status for event in latest_events}
        if terminal is not None:
            latest_status = terminal.status
        elif "awaiting_operator" in statuses:
            latest_status = "awaiting_operator"
        elif "accepted" in statuses:
            latest_status = "running"
    if terminal is not None:
        pending_interrupt = None
    delegations_projection = tuple(delegations)
    agenda = payload.get("metadata")
    metadata = agenda if isinstance(agenda, Mapping) else {}
    agenda_summary = metadata.get("agenda_summary")
    checkpoint_sequence = max((event.sequence for event in latest_events), default=0) or None
    pending_from_runtime: AgentSessionInterrupt | None = None
    if runtime_state is not None:
        runtime_status = runtime_state.get("status")
        latest_status = _status(runtime_status)
        runtime_budget = runtime_state.get("budget_usage")
        if isinstance(runtime_budget, Mapping):
            latest_usage = _budget_usage(
                {
                    "model_calls": _counter(runtime_budget.get("model_calls"), "model_calls"),
                    "tool_calls": _counter(runtime_budget.get("tool_calls"), "tool_calls"),
                    "tokens": _counter(runtime_budget.get("input_tokens"), "input_tokens")
                    + _counter(runtime_budget.get("output_tokens"), "output_tokens"),
                    "duration_ms": _counter(runtime_budget.get("duration_ms"), "duration_ms"),
                    "mutations": _counter(runtime_budget.get("mutations"), "mutations"),
                    "revisions": _counter(runtime_budget.get("revisions"), "revisions"),
                }
            )
        agenda_value = runtime_state.get("agenda")
        if isinstance(agenda_value, Mapping):
            agenda_summary = agenda_value.get("objective_summary") or agenda_summary
        pending_value = runtime_state.get("pending_interrupt")
        pending_interrupt = None
        if isinstance(pending_value, Mapping) and pending_value:
            try:
                pending_from_runtime = AgentSessionInterrupt(
                    kind=_text(pending_value.get("kind"), "interrupt kind", maximum=100),
                    question=_text(pending_value.get("question"), "interrupt question", maximum=800),
                    requested_action=_text(pending_value.get("requested_action"), "interrupt action", maximum=200),
                )
            except Exception as exc:
                raise AgentSessionStorageUnavailable("agent public interrupt is incompatible") from exc
        runtime_sequence = runtime_state.get("next_sequence")
        if isinstance(runtime_sequence, int) and runtime_sequence > 1:
            checkpoint_sequence = runtime_sequence - 1
        runtime_delegations = _public_state_delegations(
            runtime_state.get("delegations"),
            sequence=checkpoint_sequence or 1,
        )
        if runtime_delegations:
            delegations_projection = runtime_delegations
        if pending_from_runtime is not None:
            pending_interrupt = pending_from_runtime
        if terminal is not None:
            latest_status = terminal.status
            pending_interrupt = None
    return AgentSessionProjection(
        session_id=_text(payload.get("session_id"), "session_id", maximum=200),
        session_digest=digest,
        operator_id=_text(payload.get("operator_id"), "operator_id", maximum=200),
        objective=_text(payload.get("objective"), "objective", maximum=1200),
        success_definition=_text(payload.get("success_definition"), "success_definition", maximum=1200),
        status=latest_status,
        model_profile_id=_text(payload.get("model_profile_id"), "model_profile_id", maximum=200),
        agent_program_ids=tuple(program_ids[:16]),
        tool_catalog_id=_text(payload.get("tool_catalog_id"), "tool_catalog_id", maximum=200),
        scope_summary=_scope_summary(payload.get("scope_envelope")),
        budget_limits=budget,
        budget_used=latest_usage,
        agenda_summary=str(agenda_summary)[:1200] if agenda_summary else None,
        delegations=delegations_projection,
        events=tuple(latest_events),
        evidence_refs=tuple(evidence_refs),
        pending_interrupt=pending_interrupt,
        terminal_decision=terminal,
        checkpoint_sequence=checkpoint_sequence,
        available_commands=_available_commands(
            latest_status,
            has_runtime_state=runtime_state is not None,
            pending_interrupt=pending_interrupt,
        ),
        command_ids=tuple(item.command_id for item in source.commands),
    )


class AgentSessionService:
    """Expose agent-session reads and human command intents to Console."""

    def __init__(self, repository: AgentSessionRepository) -> None:
        """Bind one scope-owned agent-session repository."""
        self._repository = repository

    async def get(self, session_id: str, principal: TraderPrincipal) -> AgentSessionProjection:
        """Return one exact redacted session projection to its human owner."""
        self._require_human(principal)
        async with self._repository.session() as session:
            await session.require_storage()
            source = await session.get(session_id)
        if source is None:
            raise AgentSessionNotFound("agent session not found")
        projection = _build_projection(source)
        self._require_owner(projection, principal)
        return projection

    async def command(
        self,
        session_id: str,
        request: AgentSessionCommandRequest,
        principal: TraderPrincipal,
    ) -> AgentSessionCommandRecord:
        """Persist one human-owned command intent for runtime consumption."""
        self._require_human(principal)
        projection = await self.get(session_id, principal)
        if request.command not in projection.available_commands:
            raise AgentSessionCommandConflict(
                f"{request.command} is not available in the inspected agent session state"
            )
        async with self._repository.session(write=True) as session:
            await session.require_storage()
            return await session.create_command(
                session_id,
                request,
                requested_by=principal.principal_id,
            )

    async def get_command(
        self,
        session_id: str,
        command_id: UUID,
        principal: TraderPrincipal,
    ) -> AgentSessionCommandRecord:
        """Return one command receipt after rechecking session ownership."""
        self._require_human(principal)
        await self.get(session_id, principal)
        async with self._repository.session() as session:
            await session.require_storage()
            result = await session.get_command(command_id)
        if result is None or result.session_id != session_id:
            raise AgentSessionNotFound("agent session command not found")
        return result

    async def list_commands(
        self,
        session_id: str,
        *,
        limit: int,
        offset: int,
        principal: TraderPrincipal,
    ) -> AgentSessionCommandsResponse:
        """Return bounded command audit history after owner authorization."""
        self._require_human(principal)
        await self.get(session_id, principal)
        async with self._repository.session() as session:
            await session.require_storage()
            rows, total = await session.list_commands(session_id, limit, offset)
        return AgentSessionCommandsResponse(
            items=tuple(rows),
            page=PageInfo(limit=limit, offset=offset, total=total, has_more=offset + limit < total),
        )

    @staticmethod
    def _require_human(principal: TraderPrincipal) -> None:
        """Reject MCP and agent identities at the human control boundary."""
        if not is_human_operator_principal(principal.principal_id):
            raise AgentSessionAuthorityError("A human operator principal is required")

    @staticmethod
    def _require_owner(projection: AgentSessionProjection, principal: TraderPrincipal) -> None:
        """Require the authenticated human to own the immutable session."""
        if projection.operator_id != principal.principal_id:
            raise AgentSessionAuthorityError("The authenticated operator does not own this session")


__all__ = [
    "AgentSessionAuthorityError",
    "AgentSessionCommandConflict",
    "AgentSessionDatabaseUnavailable",
    "AgentSessionService",
    "AgentSessionStorageUnavailable",
]
