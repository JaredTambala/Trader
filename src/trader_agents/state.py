"""State schemas for deterministic research-agent graphs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypedDict

from trader_research.foundation import stable_research_id
from trader_research.governance import (
    BoundedResearchRequest,
    DataRequirement,
    FEATURE_MANIFEST,
    MODEL_CARD,
    PREDICTION_ARTIFACT,
    DRIFT_REPORT,
)

from .identities import AgentIdentity, build_agent_identity


AgentStatus = Literal["ready", "completed", "failed", "blocked"]
"""Lifecycle status values used by initial agent graphs."""


class QuantResearchSupervisorState(TypedDict, total=False):
    """State held by the initial Quant Research Supervisor graph.

    Attributes:
        identity: JSON-safe supervisor identity metadata.
        tool_allowlist: Tool names the supervisor may call in future slices.
        research_request: Bounded research request payload.
        incoming_handoffs: Specialist handoffs supplied to the supervisor.
        handoff_ledger: Accepted specialist handoffs.
        artifact_slots: Required and optional specialist artifact slots.
        data_manifest: Accepted Data Agent dataset manifest summary.
        data_quality_report: Accepted Data Agent quality summary.
        status: Current graph status.
        public_status: Human-readable public status.
        warnings: Structured warnings from handoffs or validation.
        blockers: Structured blockers preventing progression.
        errors: Structured graph errors.
        called_tools: Tool names requested by the supervisor graph.
    """

    identity: dict[str, Any]
    tool_allowlist: list[str]
    research_request: dict[str, Any]
    incoming_handoffs: list[dict[str, Any]]
    handoff_ledger: list[dict[str, Any]]
    artifact_slots: dict[str, dict[str, Any]]
    data_manifest: dict[str, Any]
    data_quality_report: dict[str, Any]
    status: AgentStatus
    public_status: str
    warnings: list[dict[str, Any]]
    blockers: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    called_tools: list[str]


def build_quant_research_supervisor_initial_state(
    *,
    objective: str,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: str,
    end: str,
    source: str | None = None,
    incoming_handoffs: Sequence[Mapping[str, Any]] | None = None,
    require_ml: bool = True,
) -> QuantResearchSupervisorState:
    """Build initial state for a deterministic supervisor graph run.

    Args:
        objective: Human-supplied research objective, stored as data.
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        source: Optional source filter.
        incoming_handoffs: Specialist handoff records available at graph start.
        require_ml: Whether ML artifacts are required blockers for this request.

    Returns:
        Initial Quant Research Supervisor state.
    """
    identity = build_agent_identity("quant_research_supervisor")
    data_requirement = DataRequirement(
        symbols=tuple(str(symbol) for symbol in symbols),
        asset_class=asset_class,
        timeframe=timeframe,
        start=start,
        end=end,
        source=source,
    )
    optional_artifacts = (
        ()
        if require_ml
        else (FEATURE_MANIFEST, MODEL_CARD, PREDICTION_ARTIFACT, DRIFT_REPORT)
    )
    required_artifacts = (
        BoundedResearchRequest.required_artifacts
        if not require_ml
        else (
            *BoundedResearchRequest.required_artifacts,
            FEATURE_MANIFEST,
            MODEL_CARD,
            PREDICTION_ARTIFACT,
            DRIFT_REPORT,
        )
    )
    request_payload = {
        "objective": objective,
        "data_requirement": data_requirement.to_dict(),
        "required_artifacts": list(required_artifacts),
        "optional_artifacts": list(optional_artifacts),
    }
    request = BoundedResearchRequest(
        request_id=stable_research_id("research_request", request_payload),
        objective=objective,
        data_requirement=data_requirement,
        required_artifacts=tuple(required_artifacts),
        optional_artifacts=tuple(optional_artifacts),
    )
    return {
        "identity": _identity_payload(identity),
        "tool_allowlist": list(identity.tool_allowlist),
        "research_request": request.to_dict(),
        "incoming_handoffs": [dict(handoff) for handoff in incoming_handoffs or ()],
        "handoff_ledger": [],
        "artifact_slots": {},
        "status": "ready",
        "public_status": "ready",
        "warnings": [],
        "blockers": [],
        "errors": [],
        "called_tools": [],
    }


def _identity_payload(identity: AgentIdentity) -> dict[str, Any]:
    """Convert an agent identity into JSON-safe state.

    Args:
        identity: Agent identity metadata.

    Returns:
        JSON-safe identity mapping.
    """
    return {
        "agent_key": identity.agent_key,
        "display_name": identity.display_name,
        "role_policy": identity.role_policy,
        "tool_allowlist": list(identity.tool_allowlist),
        "output_artifacts": list(identity.output_artifacts),
    }


def graph_error(code: str, message: str) -> dict[str, Any]:
    """Build a structured graph error.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable error message.

    Returns:
        JSON-safe error mapping.
    """
    return {"code": code, "message": message}


def mapping_or_empty(value: object) -> dict[str, Any]:
    """Return a mapping as a mutable dictionary.

    Args:
        value: Candidate mapping value.

    Returns:
        Dictionary copy when value is a mapping, otherwise an empty dictionary.
    """
    if isinstance(value, Mapping):
        return dict(value)
    return {}
