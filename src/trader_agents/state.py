"""State schemas for deterministic research-agent graphs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypedDict

from .identities import AgentIdentity, build_agent_identity


AgentStatus = Literal["ready", "completed", "failed"]
"""Lifecycle status values used by initial agent graphs."""


class DataAgentState(TypedDict, total=False):
    """State held by the first deterministic Data Agent graph.

    Attributes:
        identity: JSON-safe Data Agent identity metadata.
        tool_allowlist: Tool names the Data Agent may call.
        inventory_request: JSON-native request passed to `data_get_inventory`.
        mcp_result: Raw MCP result mapping returned by the client wrapper.
        tool_envelope: Structured research tool envelope returned by MCP.
        dataset_manifest: Dataset manifest payload from a successful envelope.
        status: Current graph status.
        warnings: Non-fatal warnings from the tool envelope.
        errors: Structured graph or tool errors.
        called_tools: Tool names successfully requested by the graph.
    """

    identity: dict[str, Any]
    tool_allowlist: list[str]
    inventory_request: dict[str, Any]
    mcp_result: dict[str, Any]
    tool_envelope: dict[str, Any]
    dataset_manifest: dict[str, Any]
    status: AgentStatus
    warnings: list[str]
    errors: list[dict[str, Any]]
    called_tools: list[str]


def build_data_agent_initial_state(
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: str,
    end: str,
    source: str | None = None,
) -> DataAgentState:
    """Build initial state for a Data Agent inventory graph run.

    Args:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        source: Optional source filter.

    Returns:
        Initial Data Agent state with identity, allowlist, and inventory request.
    """
    identity = build_agent_identity("data_agent")
    request: dict[str, Any] = {
        "symbols": [str(symbol) for symbol in symbols],
        "asset_class": asset_class,
        "timeframe": timeframe,
        "start": start,
        "end": end,
    }
    if source is not None:
        request["source"] = source
    return {
        "identity": _identity_payload(identity),
        "tool_allowlist": list(identity.tool_allowlist),
        "inventory_request": request,
        "status": "ready",
        "warnings": [],
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
