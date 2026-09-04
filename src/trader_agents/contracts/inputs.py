"""Boundary normalization for first-slice research-session inputs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from trader_research.foundation import stable_research_id
from trader_research.governance import ResearchSession

from trader_agents.mcp.catalogue import ToolCatalogue
from .domain import AgentRole, CompositeDataScope, StrategyBuildContract
from trader_agents.model_runtime.profiles import (
    AgentProgramRegistry,
    ModelProfileRegistry,
)


class SessionInputError(ValueError):
    """Raised when an approved session cannot enter the first-slice runtime."""


def scope_timestamps_equal(left: object, right: object) -> bool:
    """Return whether two timezone-aware scope boundaries name one instant.

    Args:
        left: Candidate RFC 3339/ISO 8601 boundary value.
        right: Approved RFC 3339/ISO 8601 boundary value.

    Returns:
        ``True`` only when both values are timezone-aware and normalize to the
        same UTC instant.
    """
    try:
        parsed = [
            datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            for value in (left, right)
        ]
    except ValueError:
        return False
    if any(value.tzinfo is None for value in parsed):
        return False
    return parsed[0].astimezone(timezone.utc) == parsed[1].astimezone(timezone.utc)


def composite_data_scope_from_session(
    session: ResearchSession,
) -> CompositeDataScope:
    """Parse the exact role-labelled Data scope from a research session.

    Args:
        session: Immutable operator-approved session.

    Returns:
        Strict composite scope with the owning session identity.

    Raises:
        SessionInputError: If the session has no strict ``data_scope`` object
            or its identity does not match the session.
    """
    raw_scope = session.scope_envelope.get("data_scope")
    if not isinstance(raw_scope, Mapping):
        raise SessionInputError(
            "scope_envelope.data_scope must be a structured composite scope"
        )
    payload = dict(raw_scope)
    payload.setdefault("session_id", session.session_id)
    if not payload.get("scope_id"):
        identity = {key: value for key, value in payload.items() if key != "scope_id"}
        payload["scope_id"] = stable_research_id("composite_data_scope", identity)
    try:
        scope = CompositeDataScope.model_validate(payload)
    except ValueError as exc:
        raise SessionInputError(f"invalid composite Data scope: {exc}") from exc
    if scope.session_id != session.session_id:
        raise SessionInputError("composite Data scope belongs to another session")
    return scope


def strategy_build_contract_from_session(
    session: ResearchSession,
    *,
    branch_id: str,
) -> StrategyBuildContract:
    """Normalize the operator specification into a strict build contract.

    This first slice intentionally supports only the operator-specified route.
    Missing behaviorally material fields are rejected rather than inferred.

    Args:
        session: Immutable operator-approved session.
        branch_id: Exact strategy research branch.

    Returns:
        Strict build contract pinned to the session and branch.

    Raises:
        SessionInputError: If the route or contract is invalid.
    """
    if session.implementation_specification is None:
        raise SessionInputError(
            "the first slice requires implementation_specification; "
            "implementation_ref is not yet an accepted entry route"
        )
    payload: dict[str, Any] = dict(session.implementation_specification)
    payload.setdefault("session_id", session.session_id)
    payload.setdefault("branch_id", branch_id)
    payload.setdefault("provenance", "operator_specified")
    if not payload.get("contract_id"):
        identity = {
            key: value for key, value in payload.items() if key != "contract_id"
        }
        payload["contract_id"] = stable_research_id(
            "strategy_build_contract",
            identity,
        )
    try:
        contract = StrategyBuildContract.model_validate(payload)
    except ValueError as exc:
        raise SessionInputError(f"invalid strategy build contract: {exc}") from exc
    if contract.session_id != session.session_id:
        raise SessionInputError("strategy build contract belongs to another session")
    if contract.branch_id != branch_id:
        raise SessionInputError("strategy build contract belongs to another branch")
    return contract


def validate_runtime_pins(
    session: ResearchSession,
    *,
    model_profiles: ModelProfileRegistry,
    agent_programs: AgentProgramRegistry,
    tool_catalogue: ToolCatalogue,
) -> None:
    """Validate exact model, program, and tool identities before execution.

    Args:
        session: Immutable approved session.
        model_profiles: Code-owned admitted model profiles.
        agent_programs: Code-owned admitted agent programs.
        tool_catalogue: Code-owned role catalogue.

    Raises:
        SessionInputError: If any session pin is missing or has drifted.
    """
    try:
        model_profiles.get(session.model_profile_id)
    except KeyError as exc:
        raise SessionInputError(str(exc)) from exc
    admitted = set(session.agent_program_ids)
    required = {agent_programs.for_role(role).program_id for role in AgentRole}
    if admitted != required:
        raise SessionInputError(
            "session agent_program_ids must exactly match the first-slice programs"
        )
    if session.tool_catalog_id != tool_catalogue.catalogue_id:
        raise SessionInputError("session tool_catalog_id does not match runtime")
