"""Deterministic Quant Research Supervisor LangGraph skeleton."""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.graph import END, START, StateGraph

from trader_research.governance import (
    BoundedResearchRequest,
    DATA_QUALITY_REPORT,
    DATASET_MANIFEST,
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    ResearchIssue,
    SpecialistArtifactSlot,
    SpecialistHandoff,
)

from .state import (
    AgentStatus,
    QuantResearchSupervisorState,
    graph_error,
    mapping_or_empty,
)


SUPERVISOR_OWNER = "Quant Research Supervisor Agent"
"""Display name required for the Quant Research Supervisor identity."""


def build_quant_research_supervisor_graph() -> Any:
    """Build the deterministic Quant Research Supervisor skeleton graph.

    Returns:
        Compiled graph that records a bounded request, accepts specialist
        handoff records, and reports missing evidence blockers without calling
        MCP tools or specialist graphs.
    """

    async def supervise(
        state: QuantResearchSupervisorState,
    ) -> QuantResearchSupervisorState:
        """Run one deterministic supervisor state update.

        Args:
            state: Current Quant Research Supervisor state.

        Returns:
            Supervisor state update with handoff ledger, slots, blockers, and
            public status.
        """
        return _supervise(state)

    graph = StateGraph(QuantResearchSupervisorState)
    graph.add_node("quant_research_supervisor", supervise)
    graph.add_edge(START, "quant_research_supervisor")
    graph.add_edge("quant_research_supervisor", END)
    return graph.compile()


def _supervise(state: QuantResearchSupervisorState) -> QuantResearchSupervisorState:
    """Record request and consume supplied handoffs."""
    identity = mapping_or_empty(state.get("identity"))
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = list(state.get("warnings", []))
    blockers: list[dict[str, Any]] = list(state.get("blockers", []))
    if identity.get("display_name") != SUPERVISOR_OWNER:
        errors.append(
            graph_error(
                "unexpected_agent_identity",
                "State identity is not Quant Research Supervisor Agent.",
            )
        )

    try:
        request = BoundedResearchRequest.from_dict(
            mapping_or_empty(state.get("research_request"))
        )
    except ValueError as exc:
        return {
            "status": "failed",
            "public_status": "failed_validation",
            "errors": [*errors, graph_error("invalid_research_request", str(exc))],
            "warnings": warnings,
            "blockers": blockers,
            "called_tools": list(state.get("called_tools", [])),
        }

    slots = _initial_slots(request)
    handoff_ledger: list[dict[str, Any]] = list(state.get("handoff_ledger", []))
    accepted_manifest: dict[str, Any] = {}
    accepted_quality: dict[str, Any] = {}

    for raw_handoff in state.get("incoming_handoffs", []):
        try:
            handoff = SpecialistHandoff.from_dict(mapping_or_empty(raw_handoff))
            _validate_data_handoff_window(handoff, request)
        except ValueError as exc:
            errors.append(graph_error("invalid_handoff", str(exc)))
            continue
        if handoff.artifact_type not in slots:
            errors.append(
                graph_error(
                    "unsupported_handoff_artifact",
                    f"Unsupported handoff artifact: {handoff.artifact_type}",
                )
            )
            continue
        slot = slots[handoff.artifact_type]
        slots[handoff.artifact_type] = SpecialistArtifactSlot(
            slot_key=slot.slot_key,
            artifact_type=slot.artifact_type,
            domain_owner=slot.domain_owner,
            required=slot.required,
            status="accepted",
            handoff=handoff,
        )
        handoff_ledger.append(handoff.to_dict())
        warnings.extend(warning.to_dict() for warning in handoff.warnings)
        blockers.extend(blocker.to_dict() for blocker in handoff.blockers)
        if handoff.artifact_type == DATASET_MANIFEST:
            accepted_manifest = dict(handoff.payload)
        if handoff.artifact_type == DATA_QUALITY_REPORT:
            accepted_quality = dict(handoff.payload)

    blockers.extend(_payload_blockers(accepted_manifest, accepted_quality))
    for artifact_type, slot in list(slots.items()):
        if slot.status == "accepted":
            continue
        if slot.required:
            blocker = ResearchIssue(
                code=f"missing_{artifact_type}",
                message=f"Missing required {artifact_type} artifact from the {slot.domain_owner} domain.",
            )
            blockers.append(blocker.to_dict())
            slots[artifact_type] = SpecialistArtifactSlot(
                slot_key=slot.slot_key,
                artifact_type=slot.artifact_type,
                domain_owner=slot.domain_owner,
                required=slot.required,
                status="blocked",
                blockers=(blocker,),
            )
        else:
            slots[artifact_type] = SpecialistArtifactSlot(
                slot_key=slot.slot_key,
                artifact_type=slot.artifact_type,
                domain_owner=slot.domain_owner,
                required=slot.required,
                status="optional_missing",
            )

    status: AgentStatus = "failed" if errors else "blocked" if blockers else "completed"
    public_status = (
        "failed_validation"
        if errors
        else "blocked_missing_evidence"
        if blockers
        else "ready_for_next_stage"
    )
    return {
        "research_request": request.to_dict(),
        "handoff_ledger": handoff_ledger,
        "artifact_slots": {
            artifact_type: slot.to_dict() for artifact_type, slot in slots.items()
        },
        "data_manifest": accepted_manifest,
        "data_quality_report": accepted_quality,
        "status": status,
        "public_status": public_status,
        "warnings": warnings,
        "blockers": blockers,
        "errors": errors,
        "called_tools": list(state.get("called_tools", [])),
    }


def _initial_slots(
    request: BoundedResearchRequest,
) -> dict[str, SpecialistArtifactSlot]:
    """Create required and optional artifact slots for a request."""
    slots: dict[str, SpecialistArtifactSlot] = {}
    for artifact_type in request.required_artifacts:
        slots[artifact_type] = SpecialistArtifactSlot(
            slot_key=_slot_key(artifact_type),
            artifact_type=artifact_type,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
            required=True,
        )
    for artifact_type in request.optional_artifacts:
        slots.setdefault(
            artifact_type,
            SpecialistArtifactSlot(
                slot_key=_slot_key(artifact_type),
                artifact_type=artifact_type,
                domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
                required=False,
            ),
        )
    return slots


def _validate_data_handoff_window(
    handoff: SpecialistHandoff, request: BoundedResearchRequest
) -> None:
    """Validate that Data Agent handoffs match the bounded request."""
    if handoff.artifact_type not in {DATASET_MANIFEST, DATA_QUALITY_REPORT}:
        return
    if handoff.domain_owner != DOMAIN_OWNER_BY_ARTIFACT_TYPE[handoff.artifact_type]:
        raise ValueError("Data handoffs must carry Data domain authority")
    data_requirement = request.data_requirement.to_dict()
    source_request = dict(handoff.source_request)
    payload_request = _request_from_payload(handoff.payload)
    for key in ("asset_class", "timeframe", "start", "end"):
        expected = data_requirement.get(key)
        observed = source_request.get(key) or payload_request.get(key)
        if observed is not None and str(observed) != str(expected):
            raise ValueError(
                f"{handoff.artifact_type} {key} does not match research request"
            )
    expected_symbols = [str(symbol) for symbol in data_requirement.get("symbols", [])]
    observed_symbols = source_request.get("symbols") or payload_request.get("symbols")
    if (
        observed_symbols is not None
        and [str(symbol) for symbol in observed_symbols] != expected_symbols
    ):
        raise ValueError(
            f"{handoff.artifact_type} symbols do not match research request"
        )


def _request_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Extract request-like fields from a Data Agent payload."""
    request: dict[str, Any] = {}
    for key in ("symbols", "asset_class", "timeframe"):
        if payload.get(key) is not None:
            request[key] = payload[key]
    window = mapping_or_empty(payload.get("requested_window"))
    if window.get("start") is not None:
        request["start"] = window["start"]
    if window.get("end") is not None:
        request["end"] = window["end"]
    if payload.get("source_filter") is not None:
        request["source"] = payload["source_filter"]
    return request


def _payload_blockers(
    manifest: Mapping[str, Any], quality: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Create blockers for incomplete Data Agent payloads."""
    blockers: list[dict[str, Any]] = []
    if manifest and manifest.get("complete") is not True:
        blockers.append(
            ResearchIssue(
                code="dataset_manifest_incomplete",
                message="Data Agent dataset manifest is incomplete.",
            ).to_dict()
        )
    if quality and quality.get("complete") is not True:
        blockers.append(
            ResearchIssue(
                code="data_quality_incomplete",
                message="Data Agent quality report is incomplete.",
            ).to_dict()
        )
    return blockers


def _slot_key(artifact_type: str) -> str:
    """Convert an artifact type into a supervisor slot key."""
    return artifact_type
