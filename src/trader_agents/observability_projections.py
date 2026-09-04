"""Safe field projections for public agent observability events.

Each projector accepts one strict public agent contract and emits only the
bounded facts needed to understand that contract at INFO or DEBUG detail.
Arbitrary model and MCP payloads are represented by identities, counts, and
deterministic digests rather than copied into observability data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

from trader_research.foundation import json_payload_hash

from .contracts import (
    AgentPhase,
    AgenticSliceResult,
    BudgetUsage,
    CanonicalEvidenceRef,
    CoordinatorAgenda,
    CoordinatorDecision,
    DataAgentTurn,
    PublicIssue,
    SpecialistConclusion,
    SpecialistReturn,
    StrategyAgentTurn,
    ToolCallProposal,
    ToolObservation,
)
from .observability import (
    ProjectionDetail,
    _field_is_forbidden,
    _json_bytes,
    validate_observability_fields,
)


_SAFE_ARGUMENT_IDENTITIES = frozenset(
    {
        "acquisition_plan_id",
        "artifact_ref",
        "attempt_id",
        "build_contract_id",
        "candidate_attempt_id",
        "candidate_package_id",
        "implementation_ref",
        "operation_id",
        "workspace_id",
    }
)
_SCOPE_ARGUMENTS = frozenset(
    {
        "asset_class",
        "build_contract_id",
        "end",
        "fields",
        "implementation_kinds",
        "query",
        "start",
        "symbols",
        "timeframe",
    }
)
_SAFE_OBSERVATION_SCALARS = frozenset(
    {
        "bar_count",
        "complete",
        "count",
        "coverage",
        "missing_rows",
        "passed",
        "result_count",
        "row_count",
        "status",
        "valid",
    }
)
_SIDE_EFFECTS = frozenset({"read_only", "local_mutating", "external_research_mutating"})


def project_coordinator_agenda(
    agenda: CoordinatorAgenda,
    *,
    detail: ProjectionDetail = ProjectionDetail.INFO,
) -> dict[str, Any]:
    """Project a coordinator agenda without copying the input brief.

    Args:
        agenda: Schema-valid agenda accepted at the coordinator boundary.
        detail: INFO summary or additional bounded DEBUG diagnostics.

    Returns:
        JSON-native fields safe to attach to an agenda event.
    """
    info = {
        "objective_summary": agenda.objective_summary,
        "material_ambiguity_count": len(agenda.material_ambiguities),
        "task_count": len(agenda.tasks),
        "tasks": [
            {
                "task_id": task.task_id,
                "role": task.role,
                "work_kind": task.work_kind,
                "join_mode": task.join_mode,
            }
            for task in agenda.tasks
        ],
    }
    debug = {
        "agenda_digest": _json_hash(agenda.model_dump(mode="json")),
        "task_diagnostics": [
            {
                "task_id": task.task_id,
                "dependencies": list(task.dependencies),
                "scope_item_count": len(task.scope_item_ids),
                "required_evidence_count": len(task.required_evidence),
                "mutation_requested": task.mutation_requested,
                "question_digest": _json_hash(task.question),
                "information_gain_digest": _json_hash(task.expected_information_gain),
            }
            for task in agenda.tasks
        ],
    }
    if agenda.material_ambiguities:
        debug["material_ambiguities_digest"] = _json_hash(agenda.material_ambiguities)
    return _projection(info, debug, detail)


def project_agent_turn(
    turn: DataAgentTurn | StrategyAgentTurn,
    *,
    detail: ProjectionDetail = ProjectionDetail.INFO,
) -> dict[str, Any]:
    """Project one schema-valid specialist action without hidden reasoning.

    Args:
        turn: Accepted Data or Strategy specialist action.
        detail: INFO summary or additional bounded DEBUG diagnostics.

    Returns:
        JSON-native fields safe to attach to an action event.
    """
    info: dict[str, Any] = {
        "action": turn.action,
        "public_rationale": turn.public_rationale,
    }
    debug: dict[str, Any] = {}
    if turn.tool_call is not None:
        info["tool_call"] = project_tool_call_proposal(turn.tool_call)
        debug["tool_call"] = project_tool_call_proposal(
            turn.tool_call,
            detail=ProjectionDetail.DEBUG,
        )
    if turn.next_phase is not None:
        info["next_phase"] = turn.next_phase
    if isinstance(turn, StrategyAgentTurn) and turn.build_decision is not None:
        info["build_decision"] = turn.build_decision
    if turn.final_conclusion is not None:
        info["conclusion"] = _project_specialist_conclusion(
            turn.final_conclusion,
            detail=ProjectionDetail.INFO,
        )
        debug["conclusion"] = _project_specialist_conclusion(
            turn.final_conclusion,
            detail=ProjectionDetail.DEBUG,
        )
    return _projection(info, debug, detail)


def project_tool_call_proposal(
    proposal: ToolCallProposal,
    *,
    detail: ProjectionDetail = ProjectionDetail.INFO,
) -> dict[str, Any]:
    """Project a tool proposal without exposing arbitrary argument values.

    Args:
        proposal: Schema-valid MCP tool call proposed by a model.
        detail: INFO summary or additional bounded DEBUG diagnostics.

    Returns:
        JSON-native fields safe to attach to policy and execution events.
    """
    info = {
        "call_id": proposal.call_id,
        "tool_name": proposal.tool_name,
        "purpose": proposal.purpose,
        "expected_evidence": _bounded_texts(proposal.expected_evidence),
        "mutation_requested": proposal.mutation_reason is not None,
    }
    if proposal.mutation_reason is not None:
        info["mutation_reason"] = proposal.mutation_reason
    safe_argument_names = sorted(
        key for key in proposal.arguments if not _field_is_forbidden(key)
    )
    debug: dict[str, Any] = {
        "argument_count": len(proposal.arguments),
        "argument_names": safe_argument_names,
        "argument_digest": json_payload_hash(proposal.arguments),
        "argument_identities": _selected_scalars(
            proposal.arguments,
            allowed=_SAFE_ARGUMENT_IDENTITIES,
        ),
    }
    scope = {
        key: proposal.arguments[key]
        for key in sorted(_SCOPE_ARGUMENTS)
        if key in proposal.arguments
    }
    if scope:
        debug["scope_digest"] = json_payload_hash(scope)
    return _projection(info, debug, detail)


def project_tool_observation(
    observation: ToolObservation,
    *,
    detail: ProjectionDetail = ProjectionDetail.INFO,
) -> dict[str, Any]:
    """Project a normalized MCP result without copying arbitrary result data.

    Args:
        observation: Bounded observation normalized from an MCP envelope.
        detail: INFO summary or additional bounded DEBUG diagnostics.

    Returns:
        JSON-native fields safe to attach to an execution outcome event.
    """
    info = {
        "call_id": observation.call_id,
        "tool_name": observation.tool_name,
        "ok": observation.ok,
        "command": observation.command,
        "agent_owner": observation.agent_owner,
        "side_effect": observation.side_effect,
        **_evidence_fields(observation.evidence_refs),
        "warning_codes": [item.code for item in observation.warnings],
        "error_codes": [item.code for item in observation.errors],
    }
    debug = {
        "summary_digest": json_payload_hash(observation.summary),
        "summary_field_count": len(observation.summary),
        "summary_fields": sorted(
            key for key in observation.summary if not _field_is_forbidden(key)
        ),
        "summary_values": _selected_scalars(
            observation.summary,
            allowed=_SAFE_OBSERVATION_SCALARS,
        ),
        "warnings": _issue_fields(observation.warnings),
        "errors": _issue_fields(observation.errors),
    }
    return _projection(info, debug, detail)


def project_specialist_return(
    result: SpecialistReturn,
    *,
    detail: ProjectionDetail = ProjectionDetail.INFO,
) -> dict[str, Any]:
    """Project a bounded specialist return and its canonical evidence.

    Args:
        result: Specialist return accepted by its isolated graph.
        detail: INFO summary or additional bounded DEBUG diagnostics.

    Returns:
        JSON-native fields safe to attach to a specialist-return event.
    """
    info = {
        "delegation_id": result.delegation_id,
        "attempt_id": result.attempt_id,
        "role": result.role,
        "status": result.status.value,
        "finding_count": len(result.findings),
        "unresolved_question_count": len(result.unresolved_questions),
        "blocker_codes": [item.code for item in result.blockers],
        **_evidence_fields(result.evidence_refs),
        "budget": project_budget_usage(result.budget_used),
    }
    debug = {
        "answered_questions": _bounded_texts(result.answered_questions, limit=4),
        "unresolved_questions": _bounded_texts(
            result.unresolved_questions,
            limit=4,
        ),
        "findings": _bounded_texts(result.findings, limit=4),
        "assumptions": _bounded_texts(result.assumptions, limit=4),
        "uncertainty": _bounded_texts(result.uncertainty, limit=4),
        "blockers": _issue_fields(result.blockers),
        "advisory_next_actions": _bounded_texts(
            result.advisory_next_actions,
            limit=8,
        ),
    }
    return _projection(info, debug, detail)


def project_coordinator_decision(
    decision: CoordinatorDecision,
    *,
    detail: ProjectionDetail = ProjectionDetail.INFO,
) -> dict[str, Any]:
    """Project one public coordinator decision and its cited evidence.

    Args:
        decision: Schema-valid decision produced after evidence review.
        detail: INFO summary or additional bounded DEBUG diagnostics.

    Returns:
        JSON-native fields safe to attach to a decision event.
    """
    info = {
        "action": decision.action.value,
        "summary": decision.summary,
        "reviewed_delegation_ids": _bounded_texts(
            decision.reviewed_delegation_ids,
            limit=16,
        ),
        "affected_task_ids": _bounded_texts(
            decision.affected_task_ids,
            limit=16,
        ),
        "blocker_codes": [item.code for item in decision.blockers],
        **_evidence_fields(decision.cited_evidence_refs),
    }
    debug: dict[str, Any] = {
        "criteria_applied": _bounded_texts(decision.criteria_applied, limit=8),
        "blockers": _issue_fields(decision.blockers),
        "permitted_next_actions": _bounded_texts(
            decision.permitted_next_actions,
            limit=8,
        ),
    }
    if decision.expected_information_gain is not None:
        debug["expected_information_gain"] = decision.expected_information_gain
    if decision.operator_question is not None:
        debug["operator_question"] = decision.operator_question
    return _projection(info, debug, detail)


def project_policy_result(
    proposal: ToolCallProposal,
    *,
    authorized: bool,
    detail: ProjectionDetail = ProjectionDetail.INFO,
    side_effect: str | None = None,
    fingerprint: str | None = None,
    denial_code: str | None = None,
    denial_message: str | None = None,
) -> dict[str, Any]:
    """Project deterministic tool-policy admission or denial.

    Denials require a stable public code and message. Authorized projections
    reject denial fields so one event cannot describe contradictory policy state.

    Args:
        proposal: Schema-valid MCP proposal evaluated by policy.
        authorized: Whether deterministic policy admitted the proposal.
        detail: INFO summary or additional bounded DEBUG diagnostics.
        side_effect: Catalogue side-effect class when known.
        fingerprint: Deterministic action fingerprint when computed.
        denial_code: Stable public failure code for a denied proposal.
        denial_message: Bounded public explanation for a denied proposal.

    Returns:
        JSON-native fields safe to attach to a policy event.

    Raises:
        ValueError: If admission state and denial fields contradict each other.
    """
    if authorized and (denial_code is not None or denial_message is not None):
        raise ValueError("authorized policy results cannot carry denial fields")
    if not authorized and (not denial_code or not denial_message):
        raise ValueError("denied policy results require a code and message")
    if fingerprint is not None and not _is_sha256(fingerprint):
        raise ValueError("policy fingerprint must be a lowercase SHA-256 value")
    if side_effect is not None and side_effect not in _SIDE_EFFECTS:
        raise ValueError("policy side_effect is not recognized")
    if denial_code is not None and (
        len(denial_code) > 100
        or not denial_code[0].isalpha()
        or not all(
            character.islower() or character.isdigit() or character == "_"
            for character in denial_code
        )
    ):
        raise ValueError("policy denial code must be a stable snake-case value")
    if denial_message is not None and len(denial_message) > 1_000:
        raise ValueError("policy denial message exceeds 1000 characters")
    info: dict[str, Any] = {
        "authorized": authorized,
        "call_id": proposal.call_id,
        "tool_name": proposal.tool_name,
    }
    if denial_code is not None:
        info["denial_code"] = denial_code
        info["denial_message"] = denial_message
    debug: dict[str, Any] = {
        "proposal": project_tool_call_proposal(
            proposal,
            detail=ProjectionDetail.DEBUG,
        )
    }
    if side_effect is not None:
        debug["side_effect"] = side_effect
    if fingerprint is not None:
        debug["fingerprint"] = fingerprint
    return _projection(info, debug, detail)


def project_budget_usage(usage: BudgetUsage) -> dict[str, int]:
    """Project the complete bounded public resource counters.

    Args:
        usage: Counters accepted at a runtime transition.

    Returns:
        JSON-native model, tool, token, duration, mutation, and revision counts.
    """
    return {
        "model_calls": usage.model_calls,
        "tool_calls": usage.tool_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "duration_ms": usage.duration_ms,
        "mutations": usage.mutations,
        "revisions": usage.revisions,
    }


def project_checkpoint(
    *,
    checkpoint_digest: str,
    transition_sequence: int,
    status: str,
    phase: AgentPhase | str,
) -> dict[str, Any]:
    """Project checkpoint identity without copying recoverable state.

    Args:
        checkpoint_digest: Lowercase SHA-256 digest of the public checkpoint.
        transition_sequence: Accepted transition represented by the checkpoint.
        status: Bounded public lifecycle status.
        phase: Bounded public agent phase.

    Returns:
        JSON-native checkpoint identity fields.

    Raises:
        ValueError: If identity or bounded lifecycle values are invalid.
    """
    if not _is_sha256(checkpoint_digest):
        raise ValueError("checkpoint_digest must be a lowercase SHA-256 value")
    if transition_sequence <= 0:
        raise ValueError("checkpoint transition_sequence must be positive")
    normalized_status = str(status).strip()
    normalized_phase = phase.value if isinstance(phase, AgentPhase) else str(phase)
    if not normalized_status:
        raise ValueError("checkpoint status is required")
    if not normalized_phase.strip():
        raise ValueError("checkpoint phase is required")
    if len(normalized_status) > 100 or len(normalized_phase) > 100:
        raise ValueError("checkpoint status and phase must not exceed 100 characters")
    fields = {
        "checkpoint_digest": checkpoint_digest,
        "transition_sequence": transition_sequence,
        "status": normalized_status,
        "phase": normalized_phase,
    }
    validate_observability_fields(fields)
    return fields


def project_terminal_result(
    result: AgenticSliceResult,
    *,
    detail: ProjectionDetail = ProjectionDetail.INFO,
) -> dict[str, Any]:
    """Project the terminal result without duplicating canonical artifacts.

    Args:
        result: Grounded terminal or interrupted result returned to an operator.
        detail: INFO summary or additional bounded DEBUG diagnostics.

    Returns:
        JSON-native fields safe to attach to a terminal event.
    """
    info: dict[str, Any] = {
        "status": result.status,
        "summary": result.summary,
        "decision_action": result.decision.action.value,
        "budget": project_budget_usage(result.budget_used),
        "permitted_next_actions": _bounded_texts(
            result.permitted_next_actions,
            limit=8,
        ),
    }
    if result.decision_receipt_ref is not None:
        info["decision_receipt_ref"] = result.decision_receipt_ref.uri
    debug = {
        "decision": project_coordinator_decision(
            result.decision,
            detail=ProjectionDetail.DEBUG,
        ),
        "specialist_statuses": {
            key: value.status.value
            for key, value in (
                ("data_research", result.data_return),
                ("strategy_engineering", result.strategy_return),
            )
            if value is not None
        },
    }
    return _projection(info, debug, detail)


def _project_specialist_conclusion(
    conclusion: SpecialistConclusion,
    *,
    detail: ProjectionDetail,
) -> dict[str, Any]:
    info = {
        "status": conclusion.status.value,
        "finding_count": len(conclusion.findings),
        "unresolved_question_count": len(conclusion.unresolved_questions),
        "blocker_codes": [item.code for item in conclusion.blockers],
        **_evidence_fields(conclusion.evidence_refs),
    }
    debug = {
        "findings": _bounded_texts(conclusion.findings, limit=4),
        "unresolved_questions": _bounded_texts(
            conclusion.unresolved_questions,
            limit=4,
        ),
        "assumptions": _bounded_texts(conclusion.assumptions, limit=4),
        "uncertainty": _bounded_texts(conclusion.uncertainty, limit=4),
        "blockers": _issue_fields(conclusion.blockers),
        "advisory_next_actions": _bounded_texts(
            conclusion.advisory_next_actions,
            limit=8,
        ),
    }
    return _projection(info, debug, detail)


def _projection(
    info: Mapping[str, Any],
    debug: Mapping[str, Any],
    detail: ProjectionDetail,
) -> dict[str, Any]:
    if not isinstance(detail, ProjectionDetail):
        raise TypeError("projection detail must be a ProjectionDetail")
    fields = dict(info)
    if detail is ProjectionDetail.DEBUG:
        fields.update(debug)
    validate_observability_fields(fields)
    return fields


def _evidence_fields(
    references: Sequence[CanonicalEvidenceRef],
) -> dict[str, Any]:
    uris = [str(reference.uri) for reference in references]
    visible = uris[:8]
    return {
        "evidence_count": len(uris),
        "evidence_types": sorted({str(item.artifact_type) for item in references}),
        "evidence_refs": visible,
        "evidence_ref_omitted_count": len(uris) - len(visible),
    }


def _issue_fields(issues: Sequence[PublicIssue]) -> list[dict[str, str]]:
    return [
        {
            "code": issue.code,
            "message": _bounded_text(issue.message, limit=500),
        }
        for issue in issues[:8]
    ]


def _bounded_texts(
    values: Sequence[str],
    *,
    limit: int = 8,
) -> list[str]:
    return [_bounded_text(value, limit=500) for value in values[:limit]]


def _bounded_text(value: str, *, limit: int) -> str:
    normalized = str(value).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"


def _selected_scalars(
    values: Mapping[str, Any],
    *,
    allowed: frozenset[str],
) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for key in sorted(allowed):
        value = values.get(key)
        if isinstance(value, bool) or isinstance(value, (int, float)):
            selected[key] = value
        elif isinstance(value, str) and len(value) <= 500:
            selected[key] = value
    return selected


def _json_hash(value: object) -> str:
    return sha256(_json_bytes(value, "projected value")).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
