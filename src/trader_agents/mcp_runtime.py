"""Role-scoped MCP execution and envelope normalization for agent loops."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import time
from typing import Any, Literal

from trader_research.foundation import stable_research_id

from .catalogue import ToolCatalogue, ToolDefinition
from .contracts import (
    CanonicalEvidenceRef,
    PublicIssue,
    ToolCallProposal,
    ToolObservation,
)
from .policy import AuthorizedToolCall, BudgetLedger, PolicyContext, ToolPolicy
from .tool_client import McpToolClient, McpToolDescription
from .tracing import (
    NoOpTraceSink,
    TraceCorrelation,
    TraceSink,
    correlated_attributes,
)


@dataclass(frozen=True)
class McpExecutionResult:
    """Authorized call metadata plus its normalized bounded observation."""

    authorized_call: AuthorizedToolCall
    observation: ToolObservation
    duration_ms: int


@dataclass
class RoleScopedMcpRuntime:
    """Execute model proposals only through a narrowed verified MCP catalogue.

    Attributes:
        client: MCP transport client.
        catalogue: Code-owned role, phase, side-effect, and owner catalogue.
        ledger: Mutable session resource ledger.
        policy: Deterministic proposal authorizer.
        trace_sink: Optional redacted trace backend.
        max_observation_bytes: Maximum public data returned to a model.
    """

    client: McpToolClient
    catalogue: ToolCatalogue
    ledger: BudgetLedger
    policy: ToolPolicy = ToolPolicy()
    trace_sink: TraceSink = NoOpTraceSink()
    max_observation_bytes: int = 32_000

    def __post_init__(self) -> None:
        """Initialize the transport-schema cache and validate bounds."""
        if not 1_000 <= self.max_observation_bytes <= 128_000:
            raise ValueError("max_observation_bytes must be between 1000 and 128000")
        self._transport_tools: dict[str, McpToolDescription] = {}

    async def available_tools(
        self,
        context: PolicyContext,
    ) -> tuple[dict[str, Any], ...]:
        """Return the current model-facing role/phase-narrowed tool schemas.

        Args:
            context: Trusted active policy context.

        Returns:
            Sorted descriptions whose code-owned and transport identities agree.
        """
        await self._ensure_transport_catalogue()
        definitions = self.catalogue.available(
            role=context.role,
            phase=context.phase,
            approval_policy=context.session.approval_policy,
        )
        model_tools = []
        for definition in definitions:
            transport = self._transport_tools.get(definition.name)
            if transport is None:
                raise RuntimeError(
                    f"required MCP tool is not registered: {definition.name}"
                )
            model_tools.append(
                {
                    "name": definition.name,
                    "description": definition.description,
                    "side_effect": definition.side_effect.value,
                    "input_schema": dict(transport.input_schema),
                }
            )
        return tuple(model_tools)

    async def execute(
        self,
        proposal: ToolCallProposal,
        *,
        context: PolicyContext,
        correlation: TraceCorrelation,
    ) -> McpExecutionResult:
        """Authorize, execute, validate, normalize, and meter one MCP call.

        Args:
            proposal: Strict model-produced tool proposal.
            context: Trusted role/session/lifecycle policy state.
            correlation: Redacted session/delegation trace identities.

        Returns:
            Authorized call plus a bounded public observation.
        """
        await self._ensure_transport_catalogue()
        proposal = _bind_runtime_operation(proposal, context)
        authorized = self.policy.authorize(proposal, context)
        transport_tool = self._transport_tools.get(proposal.tool_name)
        if transport_tool is None:
            raise RuntimeError(
                f"MCP tool disappeared after catalogue refresh: {proposal.tool_name}"
            )
        _validate_shallow_arguments(proposal.arguments, transport_tool.input_schema)
        started = time.perf_counter()
        with self.trace_sink.span(
            f"agent.mcp.{proposal.tool_name}",
            span_type="TOOL",
            attributes=correlated_attributes(
                correlation,
                **{
                    "trader.tool_name": proposal.tool_name,
                    "trader.call_id": proposal.call_id,
                    "trader.side_effect": authorized.definition.side_effect.value,
                },
            ),
        ):
            response = await self.client.call_tool(
                proposal.tool_name,
                proposal.arguments,
            )
        duration_ms = max(0, round((time.perf_counter() - started) * 1_000))
        self.ledger.record_tool_call(
            side_effect=authorized.definition.side_effect,
            duration_ms=duration_ms,
        )
        observation = _normalize_response(
            response,
            proposal=proposal,
            definition=authorized.definition,
            max_observation_bytes=self.max_observation_bytes,
        )
        return McpExecutionResult(
            authorized_call=authorized,
            observation=observation,
            duration_ms=duration_ms,
        )

    async def refresh_transport_catalogue(self) -> None:
        """Reload and validate exact MCP transport schemas."""
        descriptions = tuple(await self.client.list_tools())
        indexed = {item.name: item for item in descriptions}
        if len(indexed) != len(descriptions):
            raise RuntimeError("MCP server returned duplicate tool names")
        self._transport_tools = indexed

    async def _ensure_transport_catalogue(self) -> None:
        """Load MCP schemas lazily before first exposure or execution."""
        if not self._transport_tools:
            await self.refresh_transport_catalogue()


def _bind_runtime_operation(
    proposal: ToolCallProposal,
    context: PolicyContext,
) -> ToolCallProposal:
    """Bind model-proposed mutations to one deterministic transition.

    The model chooses whether and what to mutate. Runtime code supplies the
    operation identity for candidate writes and actual Data loading, so the
    model cannot select replay identity and every accepted attempt has stable
    lineage across checkpoint recovery.
    """
    if not _requires_runtime_operation(proposal):
        return proposal
    delegation = context.delegation
    if delegation is None:
        raise ValueError("runtime-bound operation requires a delegation")
    sequence = context.runtime_state.get("step_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValueError("runtime-bound operation requires a positive step sequence")
    operation_id = stable_research_id(
        "agent_tool_operation",
        {
            "session_id": context.session.session_id,
            "delegation_id": delegation.delegation_id,
            "attempt_id": delegation.attempt_id,
            "step_sequence": sequence,
            "tool_name": proposal.tool_name,
        },
    )
    bound_arguments = {
        **proposal.arguments,
        "operation_id": operation_id,
    }
    if proposal.tool_name == "data_ensure_loaded":
        bound_arguments.update(
            {
                "requested_by": context.session.session_id,
                "actor": "Data Research Agent",
            }
        )
    return proposal.model_copy(
        update={"arguments": bound_arguments}
    )


def _requires_runtime_operation(proposal: ToolCallProposal) -> bool:
    """Return whether one proposal performs a runtime-bound local mutation."""
    if proposal.tool_name == "coding_write_candidate_file":
        return True
    if proposal.tool_name != "data_ensure_loaded":
        return False
    mode = str(proposal.arguments.get("mode") or "").strip().lower()
    dry_run = proposal.arguments.get("dry_run", True)
    return mode == "sample" or (mode == "backfill" and dry_run is False)


def _normalize_response(
    response: Mapping[str, Any],
    *,
    proposal: ToolCallProposal,
    definition: ToolDefinition,
    max_observation_bytes: int,
) -> ToolObservation:
    """Validate one MCP envelope and project bounded model-visible evidence."""
    structured = response.get("structuredContent")
    if not isinstance(structured, Mapping):
        raise RuntimeError(f"{proposal.tool_name} returned no structured MCP envelope")
    command = str(structured.get("command") or "")
    owner = str(structured.get("agent_owner") or "")
    side_effect = str(structured.get("side_effect") or "")
    if command != proposal.tool_name:
        raise RuntimeError("MCP envelope command does not match authorized tool")
    if owner != definition.expected_owner:
        raise RuntimeError("MCP envelope agent_owner does not match role catalogue")
    if side_effect != definition.side_effect.value:
        raise RuntimeError("MCP envelope side_effect does not match role catalogue")
    transport_error = bool(response.get("isError"))
    ok = structured.get("ok") is True and not transport_error
    errors = _issues(structured.get("errors"), default_code="mcp_tool_failed")
    if not ok and not errors:
        errors = (
            PublicIssue(
                code="mcp_tool_failed",
                message=f"{proposal.tool_name} returned a failed MCP envelope",
            ),
        )
    data = structured.get("data")
    summary = dict(data) if isinstance(data, Mapping) else {}
    _validate_observation_size(summary, max_observation_bytes)
    return ToolObservation(
        call_id=proposal.call_id,
        tool_name=proposal.tool_name,
        ok=ok,
        command=command,
        agent_owner=owner,
        side_effect=_research_side_effect(definition),
        summary=summary,
        evidence_refs=list(_evidence_refs(structured.get("artifacts"))),
        warnings=list(_issues(structured.get("warnings"), default_code="mcp_warning")),
        errors=list(errors),
    )


def _evidence_refs(value: object) -> tuple[CanonicalEvidenceRef, ...]:
    """Normalize canonical refs from a labelled MCP artifact mapping."""
    if not isinstance(value, Mapping):
        return ()
    references = []
    for raw in value.values():
        candidates: Sequence[object]
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, Mapping)):
            candidates = raw
        else:
            candidates = (raw,)
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            uri = str(candidate.get("uri") or "")
            if not uri.startswith("research://postgres/"):
                continue
            metadata = candidate.get("metadata")
            metadata_mapping = metadata if isinstance(metadata, Mapping) else {}
            references.append(
                CanonicalEvidenceRef(
                    artifact_type=str(candidate.get("artifact_type") or ""),
                    artifact_id=str(candidate.get("artifact_id") or ""),
                    domain_owner=str(candidate.get("domain_owner") or ""),
                    uri=uri,
                    source_hash=(
                        str(metadata_mapping["source_hash"])
                        if metadata_mapping.get("source_hash")
                        else None
                    ),
                )
            )
    return tuple(references)


def _issues(value: object, *, default_code: str) -> tuple[PublicIssue, ...]:
    """Normalize string or mapping issues at the MCP boundary."""
    if value is None:
        return ()
    raw_items: Sequence[object]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, Mapping)):
        raw_items = value
    else:
        raw_items = (value,)
    issues = []
    for item in raw_items[:16]:
        if isinstance(item, Mapping):
            details = item.get("details")
            issues.append(
                PublicIssue(
                    code=str(item.get("code") or default_code),
                    message=str(item.get("message") or "MCP operation issue"),
                    details=dict(details) if isinstance(details, Mapping) else {},
                )
            )
        else:
            issues.append(PublicIssue(code=default_code, message=str(item)))
    return tuple(issues)


def _validate_observation_size(
    summary: Mapping[str, Any],
    max_observation_bytes: int,
) -> None:
    """Reject unbounded model context rather than silently truncating evidence."""
    try:
        encoded = json.dumps(
            dict(summary),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("MCP data must be JSON-native") from exc
    if len(encoded) > max_observation_bytes:
        raise RuntimeError(
            f"MCP observation is {len(encoded)} bytes; limit is {max_observation_bytes}"
        )


def _validate_shallow_arguments(
    arguments: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> None:
    """Validate required/unknown top-level fields before MCP transport."""
    if schema.get("type") not in {None, "object"}:
        raise RuntimeError("MCP input schema is not an object")
    required = schema.get("required")
    if isinstance(required, Sequence) and not isinstance(required, (str, bytes)):
        missing = [str(key) for key in required if key not in arguments]
        if missing:
            raise ValueError("missing required MCP arguments: " + ", ".join(missing))
    properties = schema.get("properties")
    if schema.get("additionalProperties") is False and isinstance(properties, Mapping):
        unknown = set(arguments) - set(properties)
        if unknown:
            raise ValueError("unknown MCP arguments: " + ", ".join(sorted(unknown)))
    try:
        encoded = json.dumps(
            dict(arguments),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("MCP arguments must be JSON-native") from exc
    if len(encoded) > 64_000:
        raise ValueError("MCP arguments exceed the 64000-byte limit")


def _research_side_effect(
    definition: ToolDefinition,
) -> Literal["read_only", "local_mutating", "external_research_mutating"]:
    """Narrow code-owned side effects to the public research-only contract."""
    value = definition.side_effect.value
    if value == "read_only":
        return "read_only"
    if value == "local_mutating":
        return "local_mutating"
    if value == "external_research_mutating":
        return "external_research_mutating"
    raise RuntimeError(f"unsafe side effect entered the agent catalogue: {value}")
