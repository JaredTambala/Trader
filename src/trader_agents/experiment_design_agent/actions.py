"""Execute Experiment Design proposal persistence through validated MCP.

The handler converts the strict task request into one registered tool call,
validates transport metadata, reloads the canonical proposal, and returns only a
URI-and-digest handoff. Complete proposal payloads never enter graph state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from trader_mcp.constants import (
    RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL,
)
from trader_research.foundation import (
    EXPERIMENTS_DOMAIN_OWNER,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    json_payload_hash,
    parse_research_artifact_uri,
    stable_research_id,
)
from trader_research.governance import (
    EXPERIMENT_DESIGN_AGENT_OWNER,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    CapabilitySideEffect,
    ExperimentDesignRequest,
    ExperimentProtocolProposal,
    ResearchIssue,
    SpecialistHandoff,
    agent_owner_for_tool,
    build_experiment_protocol_proposal,
    replace_experiment_design_refs,
)

from trader_agents.specialists import (
    SpecialistActionExecutionError,
    SpecialistActionOutcome,
    SpecialistActionStatus,
    SpecialistDecision,
    SpecialistPolicyContext,
)
from trader_agents.tool_client import McpToolClient

from .domain import experiment_design_request_from_task
from .policy import (
    CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_ACTION,
    EXPERIMENT_DESIGN_ACTION_VERSION,
)


@dataclass(frozen=True)
class _DesignToolEnvelope:
    """Normalized bounded MCP response used during one handler invocation."""

    ok: bool
    data: Mapping[str, Any]
    artifacts: Mapping[str, Any]
    warnings: tuple[ResearchIssue, ...]
    errors: tuple[ResearchIssue, ...]


class CreateExperimentProtocolProposalHandler:
    """Persist and independently verify one canonical protocol proposal."""

    def __init__(
        self,
        *,
        tool_client: McpToolClient,
        artifact_store: ResearchArtifactStore,
    ) -> None:
        """Retain injected transport and canonical-store dependencies."""
        self._tool_client = tool_client
        self._artifact_store = artifact_store

    async def run(
        self,
        *,
        context: SpecialistPolicyContext,
        decision: SpecialistDecision,
    ) -> SpecialistActionOutcome:
        """Return one digest-pinned proposal handoff after canonical validation."""
        del decision
        request = experiment_design_request_from_task(context.task)
        actor = agent_owner_for_tool(
            RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL
        )
        envelope = await _call_proposal_tool(
            tool_client=self._tool_client,
            arguments={
                "objective": context.task.objective.to_dict(),
                "design_request": request.to_dict(),
                "task_id": context.task.task_id,
                "requested_by": context.task.requested_by,
                "actor": actor,
            },
        )
        if not envelope.ok:
            errors = envelope.errors or (
                ResearchIssue(
                    code="experiment_protocol_proposal_failed",
                    message="Protocol proposal operation returned an error.",
                ),
            )
            return SpecialistActionOutcome(
                action_id=CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_ACTION,
                action_version=EXPERIMENT_DESIGN_ACTION_VERSION,
                status=SpecialistActionStatus.FAILED,
                warnings=envelope.warnings,
                errors=errors,
            )
        try:
            uri = _proposal_uri(envelope.artifacts)
            record, proposal = _load_verified_proposal(
                store=self._artifact_store,
                uri=uri,
                context=context,
                request=request,
            )
        except (ResearchArtifactStoreError, ValueError) as exc:
            raise SpecialistActionExecutionError(
                "invalid_canonical_protocol_proposal",
                str(exc),
            ) from exc
        digest = json_payload_hash(record.payload)
        handoff = SpecialistHandoff(
            handoff_id=stable_research_id(
                "experiment_design_handoff",
                {
                    "task_id": context.task.task_id,
                    "artifact_uri": record.uri,
                    "payload_sha256": digest,
                },
            ),
            domain_owner=record.domain_owner,
            producer_tool=record.producer_tool,
            requested_by=context.task.requested_by,
            actor=EXPERIMENT_DESIGN_AGENT_OWNER,
            artifact_type=record.artifact_type,
            artifact_uri=record.uri,
            source_request={
                "task_id": context.task.task_id,
                "objective_id": context.task.objective.objective_id,
            },
            provenance_refs={
                "payload_sha256": digest,
                "protocol_id": proposal.protocol.protocol_id,
                "design_digest": proposal.design_digest,
            },
        )
        return SpecialistActionOutcome(
            action_id=CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_ACTION,
            action_version=EXPERIMENT_DESIGN_ACTION_VERSION,
            status=SpecialistActionStatus.SUCCEEDED,
            outputs={"proposal": (handoff,)},
            warnings=envelope.warnings,
        )


async def _call_proposal_tool(
    *,
    tool_client: McpToolClient,
    arguments: Mapping[str, Any],
) -> _DesignToolEnvelope:
    tool_name = RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL
    try:
        raw_result = await tool_client.call_tool(tool_name, arguments)
    except Exception as exc:
        raise SpecialistActionExecutionError(
            "experiment_design_tool_transport_error",
            f"{tool_name} transport failed: {exc}",
        ) from exc
    envelope = _mapping(raw_result.get("structuredContent"), "MCP structuredContent")
    expected = {
        "command": tool_name,
        "agent_owner": agent_owner_for_tool(tool_name),
        "side_effect": CapabilitySideEffect.LOCAL_MUTATING.value,
    }
    for key, value in expected.items():
        if envelope.get(key) != value:
            raise SpecialistActionExecutionError(
                "invalid_experiment_design_tool_envelope",
                f"{tool_name} returned the wrong {key}.",
            )
    ok = envelope.get("ok")
    if not isinstance(ok, bool):
        raise SpecialistActionExecutionError(
            "invalid_experiment_design_tool_envelope",
            f"{tool_name} did not return a boolean success value.",
        )
    is_error = raw_result.get("isError")
    if is_error is not None and bool(is_error) is ok:
        raise SpecialistActionExecutionError(
            "invalid_experiment_design_tool_envelope",
            f"{tool_name} returned inconsistent MCP error metadata.",
        )
    return _DesignToolEnvelope(
        ok=ok,
        data=_mapping_or_empty(envelope.get("data")),
        artifacts=_mapping_or_empty(envelope.get("artifacts")),
        warnings=tuple(
            _issue(item, "experiment_design_tool_warning")
            for item in _sequence(envelope.get("warnings"))
        ),
        errors=tuple(
            _issue(item, "experiment_design_tool_error")
            for item in _sequence(envelope.get("errors"))
        ),
    )


def _proposal_uri(artifacts: Mapping[str, Any]) -> str:
    if set(artifacts) != {"experiment_protocol_proposal"}:
        raise ValueError("proposal tool must return exactly one proposal ref")
    raw_ref = _mapping(
        artifacts.get("experiment_protocol_proposal"),
        "proposal artifact reference",
    )
    uri = str(raw_ref.get("uri") or "")
    artifact_type, _ = parse_research_artifact_uri(uri)
    if (
        raw_ref.get("artifact_type") != EXPERIMENT_PROTOCOL_PROPOSAL
        or artifact_type != EXPERIMENT_PROTOCOL_PROPOSAL
    ):
        raise ValueError("proposal tool returned the wrong artifact type")
    return uri


def _load_verified_proposal(
    *,
    store: ResearchArtifactStore,
    uri: str,
    context: SpecialistPolicyContext,
    request: ExperimentDesignRequest,
) -> tuple[ResearchArtifactRecord, ExperimentProtocolProposal]:
    artifact_type, artifact_id = parse_research_artifact_uri(uri)
    record = store.load_artifact_record(artifact_type, artifact_id)
    expected_producer = RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL
    if record.uri != uri or record.artifact_type != EXPERIMENT_PROTOCOL_PROPOSAL:
        raise ValueError("canonical proposal identity mismatch")
    if record.domain_owner != EXPERIMENTS_DOMAIN_OWNER:
        raise ValueError("canonical proposal has the wrong domain owner")
    if record.producer_tool != expected_producer:
        raise ValueError("canonical proposal has the wrong producer")
    if record.requested_by != context.task.requested_by:
        raise ValueError("canonical proposal has the wrong requester")
    if record.actor != EXPERIMENT_DESIGN_AGENT_OWNER:
        raise ValueError("canonical proposal has the wrong actor")
    if record.status != "proposed":
        raise ValueError("canonical proposal is not proposed")
    proposal = ExperimentProtocolProposal.from_dict(record.payload)
    if proposal.task_id != context.task.task_id:
        raise ValueError("canonical proposal task identity drift")
    if proposal.objective_id != context.task.objective.objective_id:
        raise ValueError("canonical proposal objective identity drift")
    if proposal.objective_digest != json_payload_hash(
        context.task.objective.to_dict()
    ):
        raise ValueError("canonical proposal objective content drift")
    if {item.uri for item in proposal.input_refs} != {
        item.uri for item in context.task.input_refs
    }:
        raise ValueError("canonical proposal input refs drift")
    pinned_refs = {item.uri: item for item in proposal.input_refs}
    expected = build_experiment_protocol_proposal(
        objective=context.task.objective,
        design=replace_experiment_design_refs(request, pinned_refs),
        task_id=context.task.task_id,
        requested_by=context.task.requested_by,
        proposed_by=EXPERIMENT_DESIGN_AGENT_OWNER,
        input_refs=proposal.input_refs,
    )
    if proposal.to_dict() != expected.to_dict():
        raise ValueError("canonical proposal content drift")
    return record, proposal


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SpecialistActionExecutionError(
            "invalid_experiment_design_tool_envelope",
            f"{label} must be a mapping.",
        )
    return value


def _mapping_or_empty(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _issue(value: object, default_code: str) -> ResearchIssue:
    if isinstance(value, Mapping):
        return ResearchIssue(
            code=str(value.get("code") or default_code),
            message=str(value.get("message") or "Experiment Design tool issue."),
            details=_mapping_or_empty(value.get("details")),
        )
    return ResearchIssue(code=default_code, message=str(value))
