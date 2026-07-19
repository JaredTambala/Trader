"""Typed Data Agent LLM policy decisions and deterministic routing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal
import json

from trader_mcp.constants import (
    DATA_DISCOVER_SYMBOLS_TOOL,
    DATA_ENSURE_LOADED_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
)

from .llm_client import LlmClient, LlmConfigurationError, LlmJsonRequest, LlmMessage, LlmRequestError
from .state import DataAgentState, graph_error, mapping_or_empty


DataAgentPolicyAction = Literal[
    "discover_symbols",
    "inspect_inventory",
    "summarize_quality",
    "ensure_loaded",
    "retry_with_changes",
    "block",
    "finish",
]


DATA_AGENT_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["action", "reason"],
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "discover_symbols",
                "inspect_inventory",
                "summarize_quality",
                "ensure_loaded",
                "retry_with_changes",
                "block",
                "finish",
            ],
        },
        "tool_name": {
            "type": "string",
            "enum": [
                DATA_DISCOVER_SYMBOLS_TOOL,
                DATA_GET_INVENTORY_TOOL,
                DATA_SUMMARIZE_QUALITY_TOOL,
                DATA_ENSURE_LOADED_TOOL,
            ],
        },
        "arguments": {"type": "object"},
        "updates": {"type": "object"},
        "reason": {"type": "string"},
        "blocker": {"type": "object"},
    },
    "additionalProperties": False,
}

_ACTION_TO_TOOL: dict[str, str] = {
    "discover_symbols": DATA_DISCOVER_SYMBOLS_TOOL,
    "inspect_inventory": DATA_GET_INVENTORY_TOOL,
    "summarize_quality": DATA_SUMMARIZE_QUALITY_TOOL,
    "ensure_loaded": DATA_ENSURE_LOADED_TOOL,
}

_ACTION_TO_REQUEST_KEY: dict[str, str] = {
    "discover_symbols": "symbol_discovery_request",
    "inspect_inventory": "inventory_request",
    "summarize_quality": "quality_request",
    "ensure_loaded": "ensure_request",
}

_TOOL_ROUTE: dict[str, str] = {
    DATA_DISCOVER_SYMBOLS_TOOL: "data_discover_symbols",
    DATA_GET_INVENTORY_TOOL: "data_get_inventory",
    DATA_SUMMARIZE_QUALITY_TOOL: "data_summarize_quality",
    DATA_ENSURE_LOADED_TOOL: "data_ensure_loaded",
}

_REQUEST_KEYS = frozenset(_ACTION_TO_REQUEST_KEY.values())


async def call_data_agent_policy(
    *,
    state: DataAgentState,
    llm_client: LlmClient,
    max_decisions: int = 8,
) -> DataAgentState:
    """Call the LLM policy and validate its typed decision.

    Args:
        state: Current Data Agent state.
        llm_client: Provider-neutral LLM client used by the policy node.
        max_decisions: Maximum policy decisions allowed in one graph run.

    Returns:
        State update containing either the next safe route or a closed failure.
    """
    decisions = list(state.get("llm_decisions", []))
    if len(decisions) >= max_decisions:
        return _blocked_state(
            code="llm_loop_limit_exceeded",
            message="Data Agent LLM policy exceeded its loop budget.",
            state=state,
            decisions=decisions,
        )

    try:
        raw_decision = dict(await llm_client.complete_json(_build_policy_request(state)))
    except LlmConfigurationError as exc:
        return _blocked_state(
            code="llm_not_configured",
            message=str(exc),
            state=state,
            decisions=decisions,
        )
    except LlmRequestError as exc:
        return _blocked_state(
            code="llm_request_failed",
            message=str(exc),
            state=state,
            decisions=decisions,
        )

    sanitized = _sanitize_decision(raw_decision)
    decisions.append(sanitized)
    validation_error = _validate_decision_shape(sanitized)
    if validation_error is not None:
        return _failed_state(validation_error[0], validation_error[1], state=state, decisions=decisions)

    action = sanitized["action"]
    if action == "block":
        blocker = mapping_or_empty(sanitized.get("blocker"))
        return _blocked_state(
            code=str(blocker.get("code") or "llm_policy_blocked"),
            message=str(blocker.get("message") or sanitized.get("reason") or "Data Agent LLM policy blocked."),
            state=state,
            decisions=decisions,
            details=mapping_or_empty(blocker.get("details")),
        )
    if action == "finish":
        return {
            "status": "completed",
            "next_policy_route": "done",
            "llm_decisions": decisions,
            "blockers": [],
            "errors": [],
            "called_tools": list(state.get("called_tools", [])),
            "warnings": list(state.get("warnings", [])),
        }
    if action == "retry_with_changes":
        return _apply_retry_updates(state=state, decision=sanitized, decisions=decisions)
    return _route_tool_action(state=state, decision=sanitized, decisions=decisions)


def route_after_data_agent_policy(state: DataAgentState) -> str:
    """Return the route selected by the validated Data Agent policy decision."""
    if state.get("status") in {"failed", "blocked", "completed"}:
        return "done"
    route = state.get("next_policy_route") or "done"
    return route if route in {"data_discover_symbols", "data_get_inventory", "data_summarize_quality", "data_ensure_loaded", "data_agent_policy"} else "done"


def _build_policy_request(state: DataAgentState) -> LlmJsonRequest:
    """Build the LLM request from public graph state only."""
    public_state = {
        "user_request": state.get("user_request", ""),
        "identity": mapping_or_empty(state.get("identity")),
        "tool_allowlist": list(state.get("tool_allowlist", [])),
        "policy": mapping_or_empty(state.get("policy")),
        "requests": {
            "symbol_discovery_request": mapping_or_empty(state.get("symbol_discovery_request")),
            "inventory_request": mapping_or_empty(state.get("inventory_request")),
            "quality_request": mapping_or_empty(state.get("quality_request")),
            "ensure_request": mapping_or_empty(state.get("ensure_request")),
        },
        "latest_artifacts": {
            "symbol_discovery_report": mapping_or_empty(state.get("symbol_discovery_report")),
            "dataset_manifest": mapping_or_empty(state.get("dataset_manifest")),
            "quality_report": mapping_or_empty(state.get("quality_report")),
            "load_result": mapping_or_empty(state.get("load_result")),
        },
        "called_tools": list(state.get("called_tools", [])),
        "warnings": list(state.get("warnings", [])),
        "blockers": list(state.get("blockers", [])),
        "errors": list(state.get("errors", [])),
    }
    instructions = {
        "role": "Data Agent policy controller",
        "allowed_actions": DATA_AGENT_DECISION_SCHEMA["properties"]["action"]["enum"],
        "rules": [
            "Use only Data Agent MCP tools.",
            "Call data_discover_symbols before inventory, quality, or loading.",
            "Do not call SQL, broker, strategy, backtest, supervisor, or non-Data-Agent tools.",
            "Use ensure_loaded only when policy.allow_data_loading is true.",
            "Return a single JSON object matching the provided decision schema.",
        ],
        "decision_schema": DATA_AGENT_DECISION_SCHEMA,
        "public_state": public_state,
    }
    return LlmJsonRequest(
        messages=(
            LlmMessage(
                role="system",
                content="You are the Data Agent control policy. Emit one typed JSON decision only.",
            ),
            LlmMessage(role="user", content=json.dumps(instructions, sort_keys=True)),
        ),
        response_schema=DATA_AGENT_DECISION_SCHEMA,
    )


def _sanitize_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only public typed decision fields; never persist prompts or scratchpads."""
    sanitized: dict[str, Any] = {}
    for key in ("action", "tool_name", "arguments", "updates", "reason", "blocker"):
        if key in decision:
            value = decision[key]
            if isinstance(value, Mapping):
                sanitized[key] = dict(value)
            else:
                sanitized[key] = value
    return sanitized


def _validate_decision_shape(decision: Mapping[str, Any]) -> tuple[str, str] | None:
    """Validate the shallow decision contract before route-specific checks."""
    action = decision.get("action")
    if not isinstance(action, str) or action not in DATA_AGENT_DECISION_SCHEMA["properties"]["action"]["enum"]:
        return ("invalid_llm_decision", "Data Agent LLM decision did not include a supported action.")
    reason = decision.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return ("invalid_llm_decision", "Data Agent LLM decision did not include a non-empty reason.")
    for key in ("arguments", "updates", "blocker"):
        if key in decision and not isinstance(decision[key], Mapping):
            return ("invalid_llm_decision", f"Data Agent LLM decision field {key!r} must be an object.")
    return None


def _route_tool_action(
    *,
    state: DataAgentState,
    decision: Mapping[str, Any],
    decisions: list[dict[str, Any]],
) -> DataAgentState:
    """Validate a tool action and select its graph route."""
    action = str(decision["action"])
    expected_tool = _ACTION_TO_TOOL[action]
    requested_tool = decision.get("tool_name")
    if requested_tool is not None and requested_tool != expected_tool:
        return _failed_state(
            "invalid_llm_tool",
            f"Data Agent LLM action {action!r} cannot call {requested_tool!r}.",
            state=state,
            decisions=decisions,
        )
    if expected_tool not in set(state.get("tool_allowlist", [])):
        return _failed_state(
            "tool_not_allowlisted",
            f"{expected_tool} is not allowlisted for this Data Agent identity.",
            state=state,
            decisions=decisions,
        )
    if action != "discover_symbols" and not _has_successful_symbol_discovery(state):
        return _failed_state(
            "symbol_discovery_required",
            "Data Agent LLM cannot call downstream data tools before successful symbol discovery.",
            state=state,
            decisions=decisions,
        )
    if action == "ensure_loaded" and mapping_or_empty(state.get("policy")).get("allow_data_loading") is not True:
        return _failed_state(
            "data_loading_not_allowed",
            "Data Agent LLM cannot call data_ensure_loaded unless policy allows data loading.",
            state=state,
            decisions=decisions,
        )

    request_key = _ACTION_TO_REQUEST_KEY[action]
    request_payload = dict(mapping_or_empty(decision.get("arguments")) or mapping_or_empty(state.get(request_key)))
    validation_error = _validate_tool_request(action=action, request=request_payload)
    if validation_error is not None:
        return _failed_state(validation_error[0], validation_error[1], state=state, decisions=decisions)
    if action != "discover_symbols":
        context_error = _validate_request_matches_discovery(request_payload, mapping_or_empty(state.get("symbol_discovery_report")))
        if context_error is not None:
            return _failed_state(context_error[0], context_error[1], state=state, decisions=decisions)
        request_payload = _with_resolved_provider_context(request_payload, mapping_or_empty(state.get("symbol_discovery_report")))

    update: DataAgentState = {
        "next_policy_route": _TOOL_ROUTE[expected_tool],
        "status": "ready",
        "llm_decisions": decisions,
        "blockers": [],
        "errors": [],
        "warnings": list(state.get("warnings", [])),
        "called_tools": list(state.get("called_tools", [])),
    }
    _set_request_payload(update, request_key, request_payload)
    return update


def _apply_retry_updates(
    *,
    state: DataAgentState,
    decision: Mapping[str, Any],
    decisions: list[dict[str, Any]],
) -> DataAgentState:
    """Apply bounded request updates and route back to the policy node."""
    updates = mapping_or_empty(decision.get("updates")) or mapping_or_empty(decision.get("arguments"))
    if not updates:
        return _failed_state(
            "invalid_retry_updates",
            "Data Agent LLM retry_with_changes did not include request updates.",
            state=state,
            decisions=decisions,
        )
    invalid_keys = sorted(set(updates) - _REQUEST_KEYS)
    if invalid_keys:
        return _failed_state(
            "invalid_retry_updates",
            f"Data Agent LLM retry updates included unsupported keys: {', '.join(invalid_keys)}.",
            state=state,
            decisions=decisions,
        )
    update: DataAgentState = {
        "next_policy_route": "data_agent_policy",
        "status": "ready",
        "llm_decisions": decisions,
        "blockers": [],
        "errors": [],
        "warnings": list(state.get("warnings", [])),
        "called_tools": list(state.get("called_tools", [])),
    }
    for key, value in updates.items():
        request = mapping_or_empty(value)
        if not request:
            return _failed_state(
                "invalid_retry_updates",
                f"Data Agent LLM retry update for {key!r} must be a non-empty object.",
                state=state,
                decisions=decisions,
            )
        _set_request_payload(update, key, request)
    return update


def _set_request_payload(
    state: DataAgentState,
    key: str,
    request: Mapping[str, Any],
) -> None:
    """Assign a validated request through one of the declared state keys."""
    payload = dict(request)
    if key == "symbol_discovery_request":
        state["symbol_discovery_request"] = payload
    elif key == "inventory_request":
        state["inventory_request"] = payload
    elif key == "quality_request":
        state["quality_request"] = payload
    elif key == "ensure_request":
        state["ensure_request"] = payload
    else:  # pragma: no cover - callers validate against _REQUEST_KEYS first
        raise ValueError(f"unsupported Data Agent request key: {key}")


def _validate_tool_request(*, action: str, request: Mapping[str, Any]) -> tuple[str, str] | None:
    """Validate required bounded fields before a tool can be called."""
    if not request:
        return ("missing_tool_request", f"Data Agent LLM action {action!r} did not provide tool arguments.")
    if action == "discover_symbols":
        symbols = request.get("symbols")
        query = request.get("query")
        if not _non_empty_sequence(symbols) and not _non_empty_string(query):
            return ("unbounded_symbol_discovery", "Symbol discovery requires requested symbols or a bounded query.")
        if not _non_empty_string(request.get("timeframe")):
            return ("unbounded_symbol_discovery", "Symbol discovery requires a timeframe.")
        return None
    if not _non_empty_sequence(request.get("symbols")):
        return ("unbounded_data_request", f"Data Agent LLM action {action!r} requires non-empty symbols.")
    for key in ("asset_class", "timeframe", "start", "end"):
        if not _non_empty_string(request.get(key)):
            return ("unbounded_data_request", f"Data Agent LLM action {action!r} requires {key}.")
    if action == "ensure_loaded" and not _non_empty_string(request.get("mode")):
        return ("unbounded_data_request", "Data Agent LLM action 'ensure_loaded' requires an explicit mode.")
    return None


def _validate_request_matches_discovery(
    request: Mapping[str, Any],
    report: Mapping[str, Any],
) -> tuple[str, str] | None:
    """Ensure downstream tool arguments do not contradict symbol discovery."""
    comparisons = (
        ("provider", "resolved_provider"),
        ("instrument_type", "instrument_type"),
        ("bar_type", "bar_type"),
    )
    for request_key, report_key in comparisons:
        request_value = request.get(request_key)
        report_value = report.get(report_key)
        if request_value is not None and report_value is not None and str(request_value) != str(report_value):
            return (
                "provider_context_mismatch",
                f"Data Agent LLM request {request_key}={request_value!r} does not match discovered {report_key}={report_value!r}.",
            )
    requested_symbols = {str(symbol) for symbol in request.get("symbols") or []}
    missing_symbols = {str(symbol) for symbol in report.get("missing_symbols") or []}
    if requested_symbols & missing_symbols:
        return ("symbols_not_available", "Data Agent LLM request includes symbols that discovery marked unavailable.")
    return None


def _with_resolved_provider_context(request: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    """Inject the resolved provider context into downstream tool arguments."""
    updated = dict(request)
    for target_key, report_key in (
        ("provider", "resolved_provider"),
        ("instrument_type", "instrument_type"),
        ("bar_type", "bar_type"),
        ("asset_class", "legacy_asset_class"),
    ):
        value = report.get(report_key)
        if value is not None:
            updated[target_key] = value
    return updated


def _has_successful_symbol_discovery(state: DataAgentState) -> bool:
    """Return whether current state has a successful exact symbol-discovery report."""
    report = mapping_or_empty(state.get("symbol_discovery_report"))
    return report.get("all_requested_symbols_exist") is True


def _failed_state(
    code: str,
    message: str,
    *,
    state: DataAgentState,
    decisions: list[dict[str, Any]],
) -> DataAgentState:
    """Build a fail-closed policy state update."""
    return {
        "status": "failed",
        "next_policy_route": "done",
        "llm_decisions": decisions,
        "warnings": list(state.get("warnings", [])),
        "blockers": [],
        "errors": [graph_error(code, message)],
        "called_tools": list(state.get("called_tools", [])),
    }


def _blocked_state(
    *,
    code: str,
    message: str,
    state: DataAgentState,
    decisions: list[dict[str, Any]],
    details: Mapping[str, Any] | None = None,
) -> DataAgentState:
    """Build a structured policy blocker state update."""
    blocker: dict[str, Any] = {"code": code, "message": message}
    if details:
        blocker["details"] = dict(details)
    return {
        "status": "blocked",
        "next_policy_route": "done",
        "llm_decisions": decisions,
        "warnings": list(state.get("warnings", [])),
        "blockers": [blocker],
        "errors": [],
        "called_tools": list(state.get("called_tools", [])),
    }


def _non_empty_string(value: object) -> bool:
    """Return True when value is a non-empty string."""
    return isinstance(value, str) and bool(value.strip())


def _non_empty_sequence(value: object) -> bool:
    """Return True when value is a non-empty non-string sequence."""
    return isinstance(value, list | tuple) and len(value) > 0
