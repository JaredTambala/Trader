"""Model/tool control loop for the first-slice Data Research specialist."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from trader_research.foundation import json_payload_hash
from trader_research.governance import AgentBudget, ResearchSession

from .catalogue import ToolCatalogue
from .checkpointing import (
    SpecialistCheckpointState,
    build_specialist_checkpoint_state,
    checkpoint_safe_observation,
    checkpoint_step,
    specialist_thread_config,
    validate_specialist_checkpoint_state,
)
from .contracts import (
    AgentPhase,
    AgentRole,
    BudgetUsage,
    CanonicalEvidenceRef,
    CompositeDataScope,
    DataAgentTurn,
    PublicIssue,
    SpecialistConclusion,
    SpecialistDelegation,
    SpecialistReturn,
    SpecialistStatus,
    ToolObservation,
    build_specialist_return,
)
from .mcp_runtime import RoleScopedMcpRuntime
from .policy import BudgetLedger, PolicyContext, PolicyViolation
from .profiles import AgentProgram, ModelProfile
from .structured_model import StructuredModelRunner, StructuredOutputError
from .tool_client import McpToolClient
from .tracing import NoOpTraceSink, TraceCorrelation, TraceSink


@dataclass
class DataResearchAgent:
    """Run evidence-responsive Data investigation over role-scoped MCP.

    Attributes:
        model_runner: Strict model invocation boundary.
        mcp_client: Transport used only through ``RoleScopedMcpRuntime``.
        tool_catalogue: Code-owned first-slice operation catalogue.
        trace_sink: Optional redacted trace backend.
    """

    model_runner: StructuredModelRunner
    mcp_client: McpToolClient
    tool_catalogue: ToolCatalogue
    trace_sink: TraceSink = NoOpTraceSink()

    async def run(
        self,
        *,
        session: ResearchSession,
        delegation: SpecialistDelegation,
        scope: CompositeDataScope,
        program: AgentProgram,
        profile: ModelProfile,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> SpecialistReturn:
        """Execute or recover one bounded Data specialist invocation.

        Args:
            session: Immutable operator authority and global ceilings.
            delegation: Exact task, branch, side effects, and reservation.
            scope: Complete role-labelled approved Data requirement.
            program: Exact Data Research model program.
            profile: Exact admitted model profile.
            checkpointer: Optional isolated operational checkpoint backend.

        Returns:
            Trusted specialist return with measured usage and observed refs.
        """
        _validate_entry(session, delegation, scope, program, profile)
        graph = self._build_graph(
            session=session,
            delegation=delegation,
            scope=scope,
            program=program,
            profile=profile,
            checkpointer=checkpointer,
        )
        initial = build_specialist_checkpoint_state(
            session_id=session.session_id,
            session_digest=session.session_digest,
            delegation=delegation,
            role=AgentRole.DATA_RESEARCH,
            phase=AgentPhase.INVESTIGATE.value,
            program_id=program.program_id,
            model_profile_id=profile.profile_id,
            tool_catalog_id=self.tool_catalogue.catalogue_id,
        )
        if checkpointer is None:
            output = await graph.ainvoke(initial)
        else:
            config = specialist_thread_config(
                session_id=session.session_id,
                delegation_id=delegation.delegation_id,
            )
            snapshot = await graph.aget_state(config)
            if snapshot.values:
                _validate_checkpoint_identity(
                    snapshot.values,
                    session=session,
                    delegation=delegation,
                    program=program,
                    profile=profile,
                    catalogue=self.tool_catalogue,
                )
                terminal = _terminal_return(snapshot.values)
                if terminal is not None:
                    return terminal
                output = await graph.ainvoke(None, config)
            else:
                output = await graph.ainvoke(initial, config)
        terminal = _terminal_return(output)
        if terminal is None:
            raise RuntimeError("Data specialist graph returned no terminal result")
        return terminal

    def _build_graph(
        self,
        *,
        session: ResearchSession,
        delegation: SpecialistDelegation,
        scope: CompositeDataScope,
        program: AgentProgram,
        profile: ModelProfile,
        checkpointer: BaseCheckpointSaver[Any] | None,
    ) -> Any:
        """Compile one isolated checkpointed Data model/tool loop.

        Raw MCP observations are held only in the current process. The durable
        state receives a redacted projection, so a recovered model may need to
        re-read source-like content through MCP before making its next choice.
        """
        transient_observations: dict[str, ToolObservation] = {}
        correlation = TraceCorrelation(
            session_id=session.session_id,
            branch_id=delegation.branch_id,
            delegation_id=delegation.delegation_id,
            attempt_id=delegation.attempt_id,
            program_id=program.program_id,
            model_profile_id=profile.profile_id,
            tool_catalog_id=self.tool_catalogue.catalogue_id,
        )

        async def step_node(
            state: SpecialistCheckpointState,
        ) -> SpecialistCheckpointState:
            """Run one model choice and at most one authorized MCP operation."""
            _validate_checkpoint_identity(
                state,
                session=session,
                delegation=delegation,
                program=program,
                profile=profile,
                catalogue=self.tool_catalogue,
            )
            ledger = BudgetLedger(
                _delegation_budget(session, delegation),
                usage=BudgetUsage.model_validate(state.get("budget_usage", {})),
            )
            observations = [
                ToolObservation.model_validate(item)
                for item in state.get("observations", [])
            ]
            observed_refs = {
                reference.uri: reference
                for reference in (
                    CanonicalEvidenceRef.model_validate(item)
                    for item in state.get("evidence_refs", [])
                )
            }
            loop_fingerprints = dict(state.get("loop_fingerprints", {}))
            successful_step_records = list(state.get("successful_steps", []))
            successful_steps: list[tuple[str, Mapping[str, Any]]] = [
                (str(item["tool_name"]), dict(item["arguments"]))
                for item in successful_step_records
            ]
            phase = AgentPhase(str(state["phase"]))
            runtime = RoleScopedMcpRuntime(
                client=self.mcp_client,
                catalogue=self.tool_catalogue,
                ledger=ledger,
                trace_sink=self.trace_sink,
            )
            try:
                if ledger.usage.model_calls >= delegation.reserved_model_calls:
                    raise PolicyViolation(
                        "delegation_model_budget_exhausted",
                        "Data Research did not reach a conclusion inside its model reservation",
                    )
                context = _policy_context(
                    session=session,
                    delegation=delegation,
                    scope=scope,
                    program=program,
                    catalogue=self.tool_catalogue,
                    phase=phase,
                    usage=ledger.usage,
                    loop_fingerprints=loop_fingerprints,
                    successful_steps=successful_steps,
                )
                tools = await runtime.available_tools(context)
                invocation = await self.model_runner.invoke(
                    program=program,
                    profile=profile,
                    output_type=DataAgentTurn,
                    instruction=(
                        "Choose one next action. Use call_tool for one currently "
                        "listed operation, change_phase when evidence justifies "
                        "remediation/review, or return_result with a grounded "
                        "conclusion. Never cite a ref absent from observations."
                    ),
                    public_context={
                        "delegation": delegation.model_dump(mode="json"),
                        "composite_data_scope": scope.model_dump(mode="json"),
                        "phase": phase.value,
                        "available_tools": list(tools),
                        "observations": _model_observations(
                            observations,
                            transient_observations,
                        ),
                        "recovery_note": (
                            "Source-like payloads are not checkpointed. Re-read "
                            "an authorized resource when a recovered summary is insufficient."
                        ),
                        "successful_tool_sequence": [
                            name for name, _ in successful_steps
                        ],
                        "budget_used": ledger.usage.model_dump(mode="json"),
                    },
                    ledger=ledger,
                    correlation=correlation,
                )
                turn = invocation.output
                if turn.action == "return_result":
                    conclusion = _required_conclusion(turn)
                    _validate_data_conclusion(
                        conclusion,
                        scope=scope,
                        successful_steps=successful_steps,
                    )
                    specialist_result = build_specialist_return(
                        delegation=delegation,
                        role=AgentRole.DATA_RESEARCH.value,
                        program_id=program.program_id,
                        model_profile_id=profile.profile_id,
                        tool_catalog_id=self.tool_catalogue.catalogue_id,
                        conclusion=conclusion,
                        budget_used=ledger.usage,
                        available_evidence_refs=list(observed_refs.values()),
                    )
                    return _validated_update(
                        state,
                        {
                            "status": "completed",
                            "phase": AgentPhase.TERMINAL.value,
                            "budget_usage": ledger.usage.model_dump(mode="json"),
                            "terminal_return": specialist_result.model_dump(
                                mode="json"
                            ),
                            "step_sequence": int(state["step_sequence"]) + 1,
                        },
                    )
                if turn.action == "change_phase":
                    phase = _next_data_phase(phase, turn.next_phase)
                    return _validated_update(
                        state,
                        {
                            "phase": phase.value,
                            "budget_usage": ledger.usage.model_dump(mode="json"),
                            "step_sequence": int(state["step_sequence"]) + 1,
                        },
                    )
                proposal = turn.tool_call
                if proposal is None:
                    raise ValueError("call_tool turn is missing a tool proposal")
                execution = await runtime.execute(
                    proposal,
                    context=context,
                    correlation=correlation,
                )
                fingerprint = execution.authorized_call.fingerprint
                prior = loop_fingerprints.get(fingerprint, 0)
                if prior:
                    ledger.record_revision()
                loop_fingerprints[fingerprint] = prior + 1
                transient_observations[execution.observation.call_id] = (
                    execution.observation
                )
                observations.append(checkpoint_safe_observation(execution.observation))
                observations = observations[-24:]
                for reference in execution.observation.evidence_refs:
                    observed_refs[reference.uri] = reference
                if execution.observation.ok:
                    successful_step_records.append(
                        checkpoint_step(
                            tool_name=proposal.tool_name,
                            arguments=proposal.arguments,
                        )
                    )
                return _validated_update(
                    state,
                    {
                        "observations": [
                            item.model_dump(mode="json") for item in observations
                        ],
                        "successful_steps": successful_step_records[-32:],
                        "evidence_refs": [
                            item.model_dump(mode="json")
                            for item in observed_refs.values()
                        ],
                        "loop_fingerprints": loop_fingerprints,
                        "budget_usage": ledger.usage.model_dump(mode="json"),
                        "step_sequence": int(state["step_sequence"]) + 1,
                    },
                )
            except (
                PolicyViolation,
                StructuredOutputError,
                RuntimeError,
                ValueError,
            ) as exc:
                specialist_result = _failed_return(
                    session=session,
                    delegation=delegation,
                    program=program,
                    profile=profile,
                    catalogue=self.tool_catalogue,
                    ledger=ledger,
                    observed_refs=list(observed_refs.values()),
                    error=exc,
                )
                return _validated_update(
                    state,
                    {
                        "status": "failed",
                        "phase": AgentPhase.TERMINAL.value,
                        "budget_usage": ledger.usage.model_dump(mode="json"),
                        "terminal_return": specialist_result.model_dump(mode="json"),
                        "step_sequence": int(state["step_sequence"]) + 1,
                    },
                )

        graph = StateGraph(SpecialistCheckpointState)
        graph.add_node("model_tool_step", step_node)
        graph.add_edge(START, "model_tool_step")
        graph.add_conditional_edges(
            "model_tool_step",
            _route_specialist_step,
            {"continue": "model_tool_step", "end": END},
        )
        return graph.compile(checkpointer=checkpointer)


def _validate_entry(
    session: ResearchSession,
    delegation: SpecialistDelegation,
    scope: CompositeDataScope,
    program: AgentProgram,
    profile: ModelProfile,
) -> None:
    """Validate exact role, session, program, profile, and scope pins."""
    if delegation.task.role != AgentRole.DATA_RESEARCH.value:
        raise ValueError("Data Research received a delegation for another role")
    if delegation.session_id != session.session_id:
        raise ValueError("Data delegation belongs to another session")
    if scope.session_id != session.session_id:
        raise ValueError("composite Data scope belongs to another session")
    if program.role is not AgentRole.DATA_RESEARCH:
        raise ValueError("Data Research requires the Data program")
    if program.program_id not in session.agent_program_ids:
        raise ValueError("Data program is not admitted by the session")
    if profile.profile_id != session.model_profile_id:
        raise ValueError("Data model profile does not match the session")


def _delegation_budget(
    session: ResearchSession,
    delegation: SpecialistDelegation,
) -> AgentBudget:
    """Build hard local ceilings from a prior scheduler reservation."""
    return AgentBudget(
        max_model_calls=delegation.reserved_model_calls,
        max_tool_calls=delegation.reserved_tool_calls,
        max_tokens=delegation.reserved_tokens,
        max_duration_seconds=session.budget.max_duration_seconds,
        max_mutations=min(
            session.budget.max_mutations,
            delegation.reserved_tool_calls,
        ),
        max_revisions=session.budget.max_revisions,
        concurrency_limit=1,
    )


def _policy_context(
    *,
    session: ResearchSession,
    delegation: SpecialistDelegation,
    scope: CompositeDataScope,
    program: AgentProgram,
    catalogue: ToolCatalogue,
    phase: AgentPhase,
    usage: BudgetUsage,
    loop_fingerprints: Mapping[str, int],
    successful_steps: Sequence[tuple[str, Mapping[str, Any]]],
) -> PolicyContext:
    """Build fresh trusted policy context after every accepted transition."""
    return PolicyContext(
        session=session,
        role=AgentRole.DATA_RESEARCH,
        phase=phase,
        program_id=program.program_id,
        tool_catalogue=catalogue,
        usage=usage,
        runtime_state={
            "successful_tool_sequence": [name for name, _ in successful_steps],
        },
        loop_fingerprints=loop_fingerprints,
        delegation=delegation,
        data_scope=scope,
    )


def _validate_checkpoint_identity(
    state: Mapping[str, Any],
    *,
    session: ResearchSession,
    delegation: SpecialistDelegation,
    program: AgentProgram,
    profile: ModelProfile,
    catalogue: ToolCatalogue,
) -> None:
    """Require recovered state to match every immutable invocation pin."""
    validate_specialist_checkpoint_state(state)
    expected = {
        "session_id": session.session_id,
        "session_digest": session.session_digest,
        "delegation_id": delegation.delegation_id,
        "delegation_digest": json_payload_hash(delegation.model_dump(mode="json")),
        "branch_id": delegation.branch_id,
        "attempt_id": delegation.attempt_id,
        "role": AgentRole.DATA_RESEARCH.value,
        "program_id": program.program_id,
        "model_profile_id": profile.profile_id,
        "tool_catalog_id": catalogue.catalogue_id,
    }
    mismatched = [
        key
        for key, expected_value in expected.items()
        if state.get(key) != expected_value
    ]
    if mismatched:
        raise ValueError(
            "Data specialist checkpoint identity drift: " + ", ".join(mismatched)
        )


def _validated_update(
    state: Mapping[str, Any],
    update: Mapping[str, Any],
) -> SpecialistCheckpointState:
    """Validate the complete next state before returning a graph update."""
    candidate = {**dict(state), **dict(update)}
    validate_specialist_checkpoint_state(candidate)
    return cast(SpecialistCheckpointState, dict(update))


def _route_specialist_step(
    state: SpecialistCheckpointState,
) -> str:
    """Continue until a strict terminal specialist return is checkpointed."""
    return "end" if state.get("terminal_return") else "continue"


def _terminal_return(
    state: Mapping[str, Any],
) -> SpecialistReturn | None:
    """Parse a checkpointed terminal return when one is present."""
    payload = state.get("terminal_return")
    if not isinstance(payload, Mapping) or not payload:
        return None
    return SpecialistReturn.model_validate(payload)


def _model_observations(
    observations: list[ToolObservation],
    transient: Mapping[str, ToolObservation],
) -> list[dict[str, Any]]:
    """Overlay transient raw observations onto persisted safe projections."""
    projected = []
    for observation in observations[-12:]:
        selected = transient.get(observation.call_id, observation)
        projected.append(selected.model_dump(mode="json"))
    return projected


def _next_data_phase(
    current: AgentPhase,
    proposed: str | None,
) -> AgentPhase:
    """Validate forward-only model-owned Data phase transitions."""
    if proposed is None:
        raise ValueError("change_phase requires next_phase")
    target = AgentPhase(proposed)
    allowed = {
        AgentPhase.INVESTIGATE: {AgentPhase.REMEDIATE, AgentPhase.REVIEW},
        AgentPhase.REMEDIATE: {AgentPhase.REVIEW},
        AgentPhase.REVIEW: set(),
    }
    if target not in allowed.get(current, set()):
        raise PolicyViolation(
            "invalid_data_phase_transition",
            f"Data phase cannot move from {current.value} to {target.value}",
        )
    return target


def _required_conclusion(turn: DataAgentTurn) -> SpecialistConclusion:
    """Return the selected conclusion or reject an inconsistent turn."""
    if turn.final_conclusion is None:
        raise ValueError("return_result turn is missing final_conclusion")
    return turn.final_conclusion


def _validate_data_conclusion(
    conclusion: SpecialistConclusion,
    *,
    scope: CompositeDataScope,
    successful_steps: Sequence[tuple[str, Mapping[str, Any]]],
) -> None:
    """Require exact post-remediation snapshots for ready Data verdicts."""
    if conclusion.status is not SpecialistStatus.READY:
        return
    snapshot_arguments = [
        arguments
        for name, arguments in successful_steps
        if name == "data_create_research_snapshot"
    ]
    missing = [
        item.item_id
        for item in scope.items
        if not any(
            _arguments_cover_item(arguments, item) for arguments in snapshot_arguments
        )
    ]
    if missing:
        raise ValueError(
            "ready Data conclusion lacks exact snapshots for: " + ", ".join(missing)
        )
    for index, (name, arguments) in enumerate(successful_steps):
        if name != "data_ensure_loaded" or arguments.get("dry_run") is not False:
            continue
        later_names = [step_name for step_name, _ in successful_steps[index + 1 :]]
        required = {
            "data_get_inventory",
            "data_summarize_quality",
            "data_create_research_snapshot",
        }
        if not required.issubset(later_names):
            raise ValueError(
                "ready Data conclusion requires post-load inventory, quality, and snapshot"
            )


def _arguments_cover_item(arguments: Mapping[str, Any], item: Any) -> bool:
    """Return whether exact snapshot arguments cover one fixed scope item."""
    if not item.symbols:
        return False
    return (
        set(arguments.get("symbols") or ()) == set(item.symbols)
        and str(arguments.get("asset_class") or "") == item.asset_class
        and str(arguments.get("timeframe") or "") == item.timeframe
        and str(arguments.get("start") or "") == item.start
        and str(arguments.get("end") or "") == item.end
    )


def _failed_return(
    *,
    session: ResearchSession,
    delegation: SpecialistDelegation,
    program: AgentProgram,
    profile: ModelProfile,
    catalogue: ToolCatalogue,
    ledger: BudgetLedger,
    observed_refs: list[CanonicalEvidenceRef],
    error: Exception,
) -> SpecialistReturn:
    """Build a bounded fail-closed return for runtime/policy failures."""
    code = error.code if isinstance(error, PolicyViolation) else "data_agent_failed"
    conclusion = SpecialistConclusion(
        status=SpecialistStatus.FAILED,
        unresolved_questions=[delegation.task.question],
        findings=["Data investigation did not reach a validated readiness verdict."],
        evidence_refs=observed_refs,
        blockers=[PublicIssue(code=code, message=str(error)[:1_000])],
        advisory_next_actions=["review the blocker before any new delegation"],
    )
    return build_specialist_return(
        delegation=delegation,
        role=AgentRole.DATA_RESEARCH.value,
        program_id=program.program_id,
        model_profile_id=profile.profile_id,
        tool_catalog_id=catalogue.catalogue_id,
        conclusion=conclusion,
        budget_used=ledger.usage,
        available_evidence_refs=observed_refs,
    )
