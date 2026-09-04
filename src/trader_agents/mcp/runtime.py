"""Role-scoped MCP execution and envelope normalization for agent loops."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
import time
from typing import Any, Literal

from trader_research.foundation import json_payload_hash, stable_research_id

from .catalogue import ToolCatalogue, ToolDefinition
from trader_agents.contracts.domain import (
    CanonicalEvidenceRef,
    PublicIssue,
    StrategyBuildContract,
    ToolCallProposal,
    ToolObservation,
)
from trader_agents.observability.events import (
    AgentErrorCategory,
    AgentEventError,
    AgentEventName,
)
from trader_agents.observability.emitter import AgentEventEmitter
from trader_agents.observability.projections import (
    project_budget_usage,
    project_policy_result,
    project_tool_call_proposal,
    project_tool_observation,
)
from .policy import (
    AuthorizedToolCall,
    BudgetLedger,
    PolicyContext,
    PolicyViolation,
    ToolPolicy,
)
from .client import McpToolClient, McpToolDescription
from trader_agents.observability.tracing import (
    NoOpTraceSink,
    TraceCorrelation,
    TraceSink,
    correlated_attributes,
)


_STRATEGY_ATTRIBUTED_MUTATIONS = frozenset(
    {
        "research_register_strategy_implementation",
        "research_validate_strategy_implementation",
        "research_register_risk_manager_implementation",
        "research_validate_risk_manager_implementation",
    }
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
        event_emitter: Process-scoped semantic event stream.
        max_observation_bytes: Maximum public data returned to a model.
    """

    client: McpToolClient
    catalogue: ToolCatalogue
    ledger: BudgetLedger
    policy: ToolPolicy = ToolPolicy()
    trace_sink: TraceSink = NoOpTraceSink()
    event_emitter: AgentEventEmitter = field(default_factory=AgentEventEmitter)
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
        try:
            authorized = self.policy.authorize(proposal, context)
        except PolicyViolation as exc:
            self.event_emitter.emit(
                name=AgentEventName.TOOL_POLICY_DENIED,
                correlation=correlation,
                role=context.role.value,
                call_id=proposal.call_id,
                fields=project_policy_result(
                    proposal,
                    authorized=False,
                    denial_code=exc.code,
                    denial_message=str(exc),
                ),
                error=AgentEventError(
                    code=exc.code,
                    category=AgentErrorCategory.POLICY,
                    message=str(exc),
                ),
            )
            raise
        self.event_emitter.emit(
            name=AgentEventName.TOOL_POLICY_AUTHORIZED,
            correlation=correlation,
            role=context.role.value,
            call_id=proposal.call_id,
            fields=project_policy_result(
                proposal,
                authorized=True,
                side_effect=authorized.definition.side_effect.value,
                fingerprint=authorized.fingerprint,
            ),
        )
        transport_tool = self._transport_tools.get(proposal.tool_name)
        if transport_tool is None:
            raise RuntimeError(
                f"MCP tool disappeared after catalogue refresh: {proposal.tool_name}"
            )
        self.event_emitter.emit(
            name=AgentEventName.TOOL_EXECUTION_STARTED,
            correlation=correlation,
            role=context.role.value,
            call_id=proposal.call_id,
            fields={
                **project_tool_call_proposal(proposal),
                "side_effect": authorized.definition.side_effect.value,
            },
        )
        started = time.perf_counter()
        stage = "arguments"
        try:
            _validate_shallow_arguments(proposal.arguments, transport_tool.input_schema)
            stage = "transport"
            with self.trace_sink.span(
                f"agent.mcp.{proposal.tool_name}",
                span_type="TOOL",
                attributes=correlated_attributes(
                    correlation,
                    **{
                        "trader.tool_name": proposal.tool_name,
                        "trader.call_id": proposal.call_id,
                        "trader.side_effect": (authorized.definition.side_effect.value),
                        **_trace_identity_attributes(proposal.arguments),
                    },
                ),
            ):
                response = await self.client.call_tool(
                    proposal.tool_name,
                    proposal.arguments,
                )
            stage = "envelope"
            observation = _normalize_response(
                response,
                proposal=proposal,
                definition=authorized.definition,
                max_observation_bytes=self.max_observation_bytes,
            )
        except BaseException:
            _trace_result(
                self.trace_sink,
                correlation=correlation,
                proposal=proposal,
                observation=None,
            )
            is_transport_failure = stage == "transport"
            self.event_emitter.emit(
                name=AgentEventName.TOOL_EXECUTION_FAILED,
                correlation=correlation,
                role=context.role.value,
                call_id=proposal.call_id,
                fields={
                    **project_tool_call_proposal(proposal),
                    "side_effect": authorized.definition.side_effect.value,
                },
                error=AgentEventError(
                    code=(
                        "mcp_transport_interrupted"
                        if is_transport_failure
                        else "mcp_envelope_invalid"
                    ),
                    category=(
                        AgentErrorCategory.MCP_TRANSPORT
                        if is_transport_failure
                        else AgentErrorCategory.MCP_APPLICATION
                    ),
                    message=(
                        "The MCP transport did not return a usable response."
                        if is_transport_failure
                        else "The MCP request or response violated its public contract."
                    ),
                    retryable=is_transport_failure,
                ),
            )
            raise
        finally:
            duration_ms = max(
                0,
                round((time.perf_counter() - started) * 1_000),
            )
            self.ledger.record_tool_call(
                side_effect=authorized.definition.side_effect,
                duration_ms=duration_ms,
            )
            self.event_emitter.emit(
                name=AgentEventName.BUDGET_UPDATED,
                correlation=correlation,
                role=context.role.value,
                call_id=proposal.call_id,
                fields=project_budget_usage(self.ledger.usage),
            )
        _trace_result(
            self.trace_sink,
            correlation=correlation,
            proposal=proposal,
            observation=observation,
        )
        if observation.ok:
            self.event_emitter.emit(
                name=AgentEventName.TOOL_EXECUTION_COMPLETED,
                correlation=correlation,
                role=context.role.value,
                call_id=proposal.call_id,
                fields={
                    **project_tool_observation(observation),
                    "duration_ms": duration_ms,
                },
            )
        else:
            self.event_emitter.emit(
                name=AgentEventName.TOOL_EXECUTION_FAILED,
                correlation=correlation,
                role=context.role.value,
                call_id=proposal.call_id,
                fields={
                    **project_tool_observation(observation),
                    "duration_ms": duration_ms,
                },
                error=AgentEventError(
                    code="mcp_application_failed",
                    category=AgentErrorCategory.MCP_APPLICATION,
                    message="The MCP tool returned a failed public envelope.",
                ),
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
    """Bind trusted contract and mutation identities before authorization.

    The model chooses which implementation to compare and whether and what to
    mutate. Runtime code supplies the exact approved comparison requirements
    and operation identity, so the model cannot weaken the build contract or
    choose replay identity.
    """
    bound_arguments = dict(proposal.arguments)
    changed = False
    if proposal.tool_name == "research_compare_implementation":
        contract = context.build_contract
        if contract is None:
            raise ValueError("implementation comparison requires a build contract")
        bound_arguments["build_contract"] = _comparison_contract(contract)
        changed = True
    if proposal.tool_name in _STRATEGY_ATTRIBUTED_MUTATIONS:
        bound_arguments.update(
            {
                "requested_by": context.session.session_id,
                "actor": "Strategy Engineering Agent",
            }
        )
        changed = True
    if _requires_runtime_operation(proposal):
        delegation = context.delegation
        if delegation is None:
            raise ValueError("runtime-bound operation requires a delegation")
        sequence = context.runtime_state.get("step_sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
            raise ValueError(
                "runtime-bound operation requires a positive step sequence"
            )
        bound_arguments["operation_id"] = stable_research_id(
            "agent_tool_operation",
            {
                "session_id": context.session.session_id,
                "delegation_id": delegation.delegation_id,
                "attempt_id": delegation.attempt_id,
                "step_sequence": sequence,
                "tool_name": proposal.tool_name,
            },
        )
        if proposal.tool_name == "data_ensure_loaded":
            bound_arguments.update(
                {
                    "requested_by": context.session.session_id,
                    "actor": "Data Research Agent",
                }
            )
        changed = True
    if not changed:
        return proposal
    return proposal.model_copy(update={"arguments": bound_arguments})


def _comparison_contract(contract: StrategyBuildContract) -> dict[str, Any]:
    """Project exact approved requirements into the catalogue comparison shape."""
    parameters = {
        item.name: {
            "type": item.value_type,
            "default": item.default,
            **({"minimum": item.minimum} if item.minimum is not None else {}),
            **({"maximum": item.maximum} if item.maximum is not None else {}),
        }
        for item in contract.parameters
    }
    return {
        "implementation_kind": contract.implementation_kind,
        "runtime_contract": contract.runtime_interface,
        "portfolio_mode": contract.portfolio_mode,
        "required_capabilities": list(contract.required_capabilities),
        "parameters": parameters,
    }


def _requires_runtime_operation(proposal: ToolCallProposal) -> bool:
    """Return whether one proposal performs a runtime-bound local mutation."""
    if proposal.tool_name == "coding_write_candidate_file":
        return True
    if proposal.tool_name != "data_ensure_loaded":
        return False
    mode = str(proposal.arguments.get("mode") or "").strip().lower()
    dry_run = proposal.arguments.get("dry_run", True)
    return mode == "sample" or (mode == "backfill" and dry_run is False)


def _trace_identity_attributes(
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    """Project only allowlisted public lineage values into trace attributes."""
    allowed = (
        "acquisition_plan_id",
        "artifact_ref",
        "attempt_id",
        "build_contract_id",
        "candidate_attempt_id",
        "candidate_package_id",
        "implementation_ref",
        "operation_id",
        "workspace_id",
    )
    projected = {
        f"trader.argument.{key}": arguments[key]
        for key in allowed
        if isinstance(arguments.get(key), (str, int, float, bool))
    }
    receipt = arguments.get("receipt")
    if isinstance(receipt, Mapping):
        receipt_id = receipt.get("receipt_id")
        if isinstance(receipt_id, str) and receipt_id:
            projected["trader.argument.receipt_id"] = receipt_id
    scope_keys = (
        "asset_class",
        "build_contract_id",
        "end",
        "fields",
        "implementation_kinds",
        "query",
        "start",
        "symbols",
        "timeframe",
    )
    scope = {key: arguments[key] for key in scope_keys if key in arguments}
    if scope:
        projected["trader.argument.scope_digest"] = json_payload_hash(scope)
    return projected


def _trace_result(
    trace_sink: TraceSink,
    *,
    correlation: TraceCorrelation,
    proposal: ToolCallProposal,
    observation: ToolObservation | None,
) -> None:
    """Emit one terminal result span for every authorized MCP dispatch.

    A missing observation means execution ended at the transport boundary. The
    span records only a fixed public error class; canonical journals remain the
    authority for whether a provider mutation was accepted before its response
    was lost.
    """
    evidence_refs = observation.evidence_refs if observation is not None else ()
    error_codes = (
        sorted(item.code for item in observation.errors)
        if observation is not None
        else ["mcp_transport_interrupted"]
    )
    with trace_sink.span(
        f"agent.mcp_result.{proposal.tool_name}",
        span_type="CHAIN",
        attributes=correlated_attributes(
            correlation,
            **{
                "trader.tool_name": proposal.tool_name,
                "trader.call_id": proposal.call_id,
                "trader.result_ok": (
                    observation.ok if observation is not None else False
                ),
                "trader.evidence_count": len(evidence_refs),
                "trader.evidence_types": sorted(
                    item.artifact_type for item in evidence_refs
                ),
                "trader.evidence_refs": sorted(item.uri for item in evidence_refs),
                "trader.error_codes": error_codes,
                **_trace_identity_attributes(proposal.arguments),
            },
        ),
    ):
        pass


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
    """Normalize canonical refs from the public MCP artifact contract.

    Canonical application results use ``ArtifactReference`` values: type and
    URI are top-level, while identity and domain authority are bounded
    metadata. Keeping that conversion at the MCP boundary prevents model code
    from depending on persistence-specific record layouts.

    Args:
        value: Labelled artifact mapping from one structured MCP envelope.

    Returns:
        Strict canonical evidence references for Postgres-backed artifacts.

    Raises:
        RuntimeError: If a canonical URI lacks its required public identity or
            ownership metadata.
    """
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
            artifact_type = str(candidate.get("artifact_type") or "").strip()
            artifact_id = str(metadata_mapping.get("id") or "").strip()
            domain_owner = str(metadata_mapping.get("domain_owner") or "").strip()
            if not artifact_type or not artifact_id or not domain_owner:
                raise RuntimeError(
                    "canonical MCP artifact reference is missing type, ID, or owner"
                )
            references.append(
                CanonicalEvidenceRef(
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    domain_owner=domain_owner,
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
