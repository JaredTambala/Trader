"""Model/tool control loop for first-slice Strategy Engineering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from trader_research.foundation import json_payload_hash, stable_research_id
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
    PublicIssue,
    SpecialistConclusion,
    SpecialistDelegation,
    SpecialistReturn,
    SpecialistStatus,
    StrategyAgentTurn,
    StrategyBuildContract,
    ToolCallProposal,
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
class StrategyEngineeringAgent:
    """Investigate, build, and independently admit one exact candidate.

    Attributes:
        model_runner: Strict model invocation boundary.
        mcp_client: Transport used only through the role-scoped MCP runtime.
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
        build_contract: StrategyBuildContract,
        program: AgentProgram,
        profile: ModelProfile,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> SpecialistReturn:
        """Execute or recover one catalogue/coding/admission invocation.

        Args:
            session: Immutable operator authority and global ceilings.
            delegation: Exact task, branch, side effects, and reservation.
            build_contract: Behaviorally complete approved implementation input.
            program: Exact Strategy Engineering model program.
            profile: Exact admitted model profile.
            checkpointer: Optional isolated operational checkpoint backend.

        Returns:
            Trusted specialist return with immutable evidence and measured use.
        """
        _validate_entry(session, delegation, build_contract, program, profile)
        graph = self._build_graph(
            session=session,
            delegation=delegation,
            build_contract=build_contract,
            program=program,
            profile=profile,
            checkpointer=checkpointer,
        )
        initial = build_specialist_checkpoint_state(
            session_id=session.session_id,
            session_digest=session.session_digest,
            delegation=delegation,
            role=AgentRole.STRATEGY_ENGINEERING,
            phase=AgentPhase.INVESTIGATE.value,
            program_id=program.program_id,
            model_profile_id=profile.profile_id,
            tool_catalog_id=self.tool_catalogue.catalogue_id,
            lifecycle=_initial_lifecycle_state(delegation),
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
            raise RuntimeError("Strategy specialist graph returned no terminal result")
        return terminal

    def _build_graph(
        self,
        *,
        session: ResearchSession,
        delegation: SpecialistDelegation,
        build_contract: StrategyBuildContract,
        program: AgentProgram,
        profile: ModelProfile,
        checkpointer: BaseCheckpointSaver[Any] | None,
    ) -> Any:
        """Compile one isolated checkpointed Strategy model/tool loop.

        Complete repository and candidate source stays transient. A recovered
        agent receives hashes and lifecycle facts and must re-read any source it
        still needs through the same role-scoped MCP boundary.
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
            checkpoint: SpecialistCheckpointState,
        ) -> SpecialistCheckpointState:
            """Run one model choice and at most one authorized MCP operation."""
            _validate_checkpoint_identity(
                checkpoint,
                session=session,
                delegation=delegation,
                program=program,
                profile=profile,
                catalogue=self.tool_catalogue,
            )
            ledger = BudgetLedger(
                _delegation_budget(session, delegation),
                usage=BudgetUsage.model_validate(checkpoint.get("budget_usage", {})),
            )
            runtime = RoleScopedMcpRuntime(
                client=self.mcp_client,
                catalogue=self.tool_catalogue,
                ledger=ledger,
                trace_sink=self.trace_sink,
            )
            phase = AgentPhase(str(checkpoint["phase"]))
            observations = [
                ToolObservation.model_validate(item)
                for item in checkpoint.get("observations", [])
            ]
            observed_refs = {
                reference.uri: reference
                for reference in (
                    CanonicalEvidenceRef.model_validate(item)
                    for item in checkpoint.get("evidence_refs", [])
                )
            }
            loop_fingerprints = dict(checkpoint.get("loop_fingerprints", {}))
            lifecycle = dict(checkpoint.get("lifecycle", {}))
            successful_steps = list(checkpoint.get("successful_steps", []))
            try:
                if ledger.usage.model_calls >= delegation.reserved_model_calls:
                    raise PolicyViolation(
                        "delegation_model_budget_exhausted",
                        "Strategy Engineering did not conclude inside its model reservation",
                    )
                context = _policy_context(
                    session=session,
                    delegation=delegation,
                    build_contract=build_contract,
                    program=program,
                    catalogue=self.tool_catalogue,
                    phase=phase,
                    usage=ledger.usage,
                    loop_fingerprints=loop_fingerprints,
                    state=lifecycle,
                    step_sequence=int(checkpoint["step_sequence"]),
                )
                tools = await runtime.available_tools(context)
                invocation = await self.model_runner.invoke(
                    program=program,
                    profile=profile,
                    output_type=StrategyAgentTurn,
                    instruction=(
                        "Choose exactly one next action. Search and compare before "
                        "choose_build. For adapt/author, use only the workspace, "
                        "package, registration, and admission tools. Return a "
                        "grounded conclusion only when lifecycle evidence permits."
                    ),
                    public_context={
                        "delegation": delegation.model_dump(mode="json"),
                        "build_contract": build_contract.model_dump(mode="json"),
                        "phase": phase.value,
                        "lifecycle": _public_lifecycle(lifecycle),
                        "available_tools": list(tools),
                        "observations": _model_observations(
                            observations,
                            transient_observations,
                        ),
                        "recovery_note": (
                            "Complete source and command output are not checkpointed. "
                            "Re-read an authorized repository, candidate, or catalogue "
                            "resource when a recovered summary is insufficient."
                        ),
                        "budget_used": ledger.usage.model_dump(mode="json"),
                    },
                    ledger=ledger,
                    correlation=correlation,
                )
                turn = invocation.output
                if turn.action == "return_result":
                    conclusion = _required_conclusion(turn)
                    _validate_strategy_conclusion(
                        conclusion,
                        state=lifecycle,
                    )
                    await _cleanup_workspace(
                        runtime=runtime,
                        session=session,
                        delegation=delegation,
                        build_contract=build_contract,
                        program=program,
                        phase=AgentPhase.TERMINAL,
                        ledger=ledger,
                        loop_fingerprints=loop_fingerprints,
                        state=lifecycle,
                        correlation=correlation,
                    )
                    specialist_result = build_specialist_return(
                        delegation=delegation,
                        role=AgentRole.STRATEGY_ENGINEERING.value,
                        program_id=program.program_id,
                        model_profile_id=profile.profile_id,
                        tool_catalog_id=self.tool_catalogue.catalogue_id,
                        conclusion=conclusion,
                        budget_used=ledger.usage,
                        available_evidence_refs=list(observed_refs.values()),
                    )
                    return _validated_update(
                        checkpoint,
                        {
                            "status": "completed",
                            "phase": AgentPhase.TERMINAL.value,
                            "lifecycle": lifecycle,
                            "budget_usage": ledger.usage.model_dump(mode="json"),
                            "terminal_return": specialist_result.model_dump(
                                mode="json"
                            ),
                            "step_sequence": int(checkpoint["step_sequence"]) + 1,
                        },
                    )
                if turn.action == "choose_build":
                    phase = _accept_build_decision(turn, lifecycle)
                    return _validated_update(
                        checkpoint,
                        {
                            "phase": phase.value,
                            "lifecycle": lifecycle,
                            "budget_usage": ledger.usage.model_dump(mode="json"),
                            "step_sequence": int(checkpoint["step_sequence"]) + 1,
                        },
                    )
                if turn.action == "change_phase":
                    phase = _next_strategy_phase(
                        phase,
                        turn.next_phase,
                        state=lifecycle,
                        contract=build_contract,
                        ledger=ledger,
                        delegation=delegation,
                    )
                    return _validated_update(
                        checkpoint,
                        {
                            "phase": phase.value,
                            "lifecycle": lifecycle,
                            "budget_usage": ledger.usage.model_dump(mode="json"),
                            "step_sequence": int(checkpoint["step_sequence"]) + 1,
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
                _update_lifecycle(
                    lifecycle,
                    proposal=proposal,
                    observation=execution.observation,
                )
                if (
                    proposal.tool_name.startswith("research_validate_")
                    and not execution.observation.ok
                ):
                    await _cleanup_workspace(
                        runtime=runtime,
                        session=session,
                        delegation=delegation,
                        build_contract=build_contract,
                        program=program,
                        phase=phase,
                        ledger=ledger,
                        loop_fingerprints=loop_fingerprints,
                        state=lifecycle,
                        correlation=correlation,
                    )
                if execution.observation.ok:
                    successful_steps.append(
                        checkpoint_step(
                            tool_name=proposal.tool_name,
                            arguments=proposal.arguments,
                        )
                    )
                if (
                    execution.observation.ok
                    and proposal.tool_name == "coding_package_candidate"
                ):
                    phase = AgentPhase.ADMIT
                return _validated_update(
                    checkpoint,
                    {
                        "phase": phase.value,
                        "observations": [
                            item.model_dump(mode="json") for item in observations
                        ],
                        "successful_steps": successful_steps[-32:],
                        "evidence_refs": [
                            item.model_dump(mode="json")
                            for item in observed_refs.values()
                        ],
                        "loop_fingerprints": loop_fingerprints,
                        "lifecycle": lifecycle,
                        "budget_usage": ledger.usage.model_dump(mode="json"),
                        "step_sequence": int(checkpoint["step_sequence"]) + 1,
                    },
                )
            except (
                PolicyViolation,
                StructuredOutputError,
                RuntimeError,
                ValueError,
            ) as exc:
                cleanup_error: Exception | None = None
                try:
                    await _cleanup_workspace(
                        runtime=runtime,
                        session=session,
                        delegation=delegation,
                        build_contract=build_contract,
                        program=program,
                        phase=AgentPhase.TERMINAL,
                        ledger=ledger,
                        loop_fingerprints=loop_fingerprints,
                        state=lifecycle,
                        correlation=correlation,
                    )
                except (PolicyViolation, RuntimeError, ValueError) as cleanup_exc:
                    cleanup_error = cleanup_exc
                specialist_result = _failed_return(
                    delegation=delegation,
                    program=program,
                    profile=profile,
                    catalogue=self.tool_catalogue,
                    ledger=ledger,
                    observed_refs=list(observed_refs.values()),
                    error=cleanup_error or exc,
                )
                return _validated_update(
                    checkpoint,
                    {
                        "status": "failed",
                        "phase": AgentPhase.TERMINAL.value,
                        "lifecycle": lifecycle,
                        "budget_usage": ledger.usage.model_dump(mode="json"),
                        "terminal_return": specialist_result.model_dump(mode="json"),
                        "step_sequence": int(checkpoint["step_sequence"]) + 1,
                    },
                )

        graph = StateGraph(SpecialistCheckpointState)
        graph.add_node("model_tool_step", cast(Any, step_node))
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
    contract: StrategyBuildContract,
    program: AgentProgram,
    profile: ModelProfile,
) -> None:
    """Validate exact role, session, program, profile, and contract pins."""
    if delegation.task.role != AgentRole.STRATEGY_ENGINEERING.value:
        raise ValueError("Strategy Engineering received another role's delegation")
    if delegation.session_id != session.session_id:
        raise ValueError("Strategy delegation belongs to another session")
    if contract.session_id != session.session_id:
        raise ValueError("build contract belongs to another session")
    if contract.branch_id != delegation.branch_id:
        raise ValueError("build contract belongs to another branch")
    if program.role is not AgentRole.STRATEGY_ENGINEERING:
        raise ValueError("Strategy Engineering requires the Strategy program")
    if program.program_id not in session.agent_program_ids:
        raise ValueError("Strategy program is not admitted by the session")
    if profile.profile_id != session.model_profile_id:
        raise ValueError("Strategy model profile does not match the session")


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
        "role": AgentRole.STRATEGY_ENGINEERING.value,
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
            "Strategy specialist checkpoint identity drift: " + ", ".join(mismatched)
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


def _delegation_budget(
    session: ResearchSession,
    delegation: SpecialistDelegation,
) -> AgentBudget:
    """Build hard local ceilings from a scheduler reservation."""
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


def _initial_lifecycle_state(
    delegation: SpecialistDelegation,
) -> dict[str, Any]:
    """Build public lifecycle facts without model text or source content."""
    return {
        "catalogue_searched": False,
        "catalogue_result_count": None,
        "comparison_completed": False,
        "direct_reuse_eligible": False,
        "build_decision": None,
        "repair_count": 0,
        "candidate_attempt_id": _candidate_attempt_id(delegation, 0),
        "workspace_id": None,
        "workspace_destroyed": False,
        "checks_passed": [],
        "package_id": None,
        "package_source_hash": None,
        "implementation_ref": None,
        "admission_passed": False,
        "admission_failed": False,
    }


def _candidate_attempt_id(
    delegation: SpecialistDelegation,
    repair_count: int,
) -> str:
    """Derive immutable candidate-attempt lineage from the delegation."""
    return stable_research_id(
        "candidate_attempt",
        {
            "delegation_id": delegation.delegation_id,
            "specialist_attempt_id": delegation.attempt_id,
            "repair_count": repair_count,
        },
    )


def _policy_context(
    *,
    session: ResearchSession,
    delegation: SpecialistDelegation,
    build_contract: StrategyBuildContract,
    program: AgentProgram,
    catalogue: ToolCatalogue,
    phase: AgentPhase,
    usage: BudgetUsage,
    loop_fingerprints: Mapping[str, int],
    state: Mapping[str, Any],
    step_sequence: int | None = None,
) -> PolicyContext:
    """Build fresh trusted policy context after every accepted transition."""
    return PolicyContext(
        session=session,
        role=AgentRole.STRATEGY_ENGINEERING,
        phase=phase,
        program_id=program.program_id,
        tool_catalogue=catalogue,
        usage=usage,
        runtime_state={
            **dict(state),
            **({"step_sequence": step_sequence} if step_sequence is not None else {}),
        },
        loop_fingerprints=loop_fingerprints,
        delegation=delegation,
        build_contract=build_contract,
    )


def _accept_build_decision(
    turn: StrategyAgentTurn,
    state: dict[str, Any],
) -> AgentPhase:
    """Validate catalogue evidence before accepting reuse/adapt/author."""
    decision = turn.build_decision
    if decision is None:
        raise ValueError("choose_build requires build_decision")
    if state.get("build_decision") is not None:
        raise PolicyViolation(
            "build_decision_already_recorded",
            "build approach cannot change without a new candidate attempt",
        )
    if not state.get("catalogue_searched"):
        raise PolicyViolation(
            "catalogue_search_required",
            "build approach requires prior implementation search",
        )
    result_count = state.get("catalogue_result_count")
    compared = bool(state.get("comparison_completed"))
    if decision in {"reuse", "adapt"} and not compared:
        raise PolicyViolation(
            "implementation_comparison_required",
            f"{decision} requires a field-level implementation comparison",
        )
    if decision == "author" and result_count != 0 and not compared:
        raise PolicyViolation(
            "implementation_comparison_required",
            "authorship requires comparison or evidence that search found no candidate",
        )
    if decision == "reuse" and not state.get("direct_reuse_eligible"):
        raise PolicyViolation(
            "direct_reuse_not_eligible",
            "reuse requires an admitted field-level compatible implementation",
        )
    state["build_decision"] = decision
    return AgentPhase.INVESTIGATE if decision == "reuse" else AgentPhase.CONSTRUCT


def _next_strategy_phase(
    current: AgentPhase,
    proposed: str | None,
    *,
    state: dict[str, Any],
    contract: StrategyBuildContract,
    ledger: BudgetLedger,
    delegation: SpecialistDelegation,
) -> AgentPhase:
    """Validate forward construction and bounded admission-repair transitions."""
    if proposed is None:
        raise ValueError("change_phase requires next_phase")
    target = AgentPhase(proposed)
    if current is AgentPhase.CONSTRUCT and target is AgentPhase.ADMIT:
        if not state.get("package_id"):
            raise PolicyViolation(
                "candidate_package_required",
                "admission phase requires an exact candidate package",
            )
        return target
    if current is AgentPhase.ADMIT and target is AgentPhase.CONSTRUCT:
        if not state.get("admission_failed"):
            raise PolicyViolation(
                "admission_failure_required",
                "repair requires actionable failed admission evidence",
            )
        if not state.get("workspace_destroyed"):
            raise PolicyViolation(
                "workspace_cleanup_required",
                "failed candidate workspace must be destroyed before repair",
            )
        repair_count = int(state.get("repair_count") or 0) + 1
        if repair_count > contract.max_repairs:
            raise PolicyViolation(
                "candidate_repair_exhausted",
                "candidate repair limit is exhausted",
            )
        ledger.record_revision()
        state.update(
            {
                "repair_count": repair_count,
                "candidate_attempt_id": _candidate_attempt_id(
                    delegation,
                    repair_count,
                ),
                "workspace_id": None,
                "workspace_destroyed": False,
                "checks_passed": [],
                "package_id": None,
                "package_source_hash": None,
                "implementation_ref": None,
                "admission_passed": False,
                "admission_failed": False,
            }
        )
        return target
    raise PolicyViolation(
        "invalid_strategy_phase_transition",
        f"Strategy phase cannot move from {current.value} to {target.value}",
    )


def _update_lifecycle(
    state: dict[str, Any],
    *,
    proposal: ToolCallProposal,
    observation: ToolObservation,
) -> None:
    """Project accepted MCP observations into bounded lifecycle facts."""
    name = proposal.tool_name
    summary = observation.summary
    if name == "research_search_implementations" and observation.ok:
        state["catalogue_searched"] = True
        state["catalogue_result_count"] = _optional_integer(summary.get("result_count"))
    elif name == "research_compare_implementation" and observation.ok:
        state["comparison_completed"] = True
        state["direct_reuse_eligible"] = bool(summary.get("direct_reuse_eligible"))
    elif name == "coding_create_workspace" and observation.ok:
        workspace = _mapping(summary.get("workspace"))
        state["workspace_id"] = str(workspace.get("workspace_id") or "")
        state["workspace_destroyed"] = False
    elif name == "coding_run_check" and observation.ok:
        check = _mapping(summary.get("check"))
        check_name = str(check.get("check_name") or "")
        if check_name:
            state["checks_passed"] = [
                *state.get("checks_passed", []),
                check_name,
            ]
    elif name == "coding_package_candidate" and observation.ok:
        package = _mapping(summary.get("candidate_package"))
        state["package_id"] = str(package.get("package_id") or "")
        state["package_source_hash"] = str(package.get("source_hash") or "")
    elif name.startswith("research_register_") and observation.ok:
        reference = _first_ref(observation, "implementation_version")
        state["implementation_ref"] = reference.uri if reference else None
    elif name.startswith("research_validate_"):
        state["admission_passed"] = observation.ok
        state["admission_failed"] = not observation.ok
    elif name == "coding_destroy_workspace" and observation.ok:
        state["workspace_destroyed"] = True


async def _cleanup_workspace(
    *,
    runtime: RoleScopedMcpRuntime,
    session: ResearchSession,
    delegation: SpecialistDelegation,
    build_contract: StrategyBuildContract,
    program: AgentProgram,
    phase: AgentPhase,
    ledger: BudgetLedger,
    loop_fingerprints: dict[str, int],
    state: dict[str, Any],
    correlation: TraceCorrelation,
) -> None:
    """Destroy an active workspace through the same policy/MCP boundary."""
    workspace_id = str(state.get("workspace_id") or "")
    if not workspace_id or state.get("workspace_destroyed"):
        return
    context = _policy_context(
        session=session,
        delegation=delegation,
        build_contract=build_contract,
        program=program,
        catalogue=runtime.catalogue,
        phase=phase,
        usage=ledger.usage,
        loop_fingerprints=loop_fingerprints,
        state=state,
    )
    proposal = ToolCallProposal(
        call_id=f"cleanup-{state['candidate_attempt_id']}",
        tool_name="coding_destroy_workspace",
        arguments={"workspace_id": workspace_id},
        purpose="Destroy the disposable candidate workspace after terminal use.",
        expected_evidence=["workspace destruction status"],
        mutation_reason="Required terminal cleanup of isolated candidate state.",
    )
    result = await runtime.execute(
        proposal,
        context=context,
        correlation=correlation,
    )
    if not result.observation.ok:
        raise RuntimeError("candidate workspace cleanup failed")
    state["workspace_destroyed"] = True


def _validate_strategy_conclusion(
    conclusion: SpecialistConclusion,
    *,
    state: Mapping[str, Any],
) -> None:
    """Require admitted exact evidence for a ready Strategy verdict."""
    if conclusion.status is not SpecialistStatus.READY:
        return
    decision = state.get("build_decision")
    if decision == "reuse":
        if not state.get("direct_reuse_eligible"):
            raise ValueError("ready reuse conclusion lacks direct-reuse evidence")
    elif decision in {"adapt", "author"}:
        if not state.get("admission_passed"):
            raise ValueError("ready built candidate lacks passed admission")
    else:
        raise ValueError("ready Strategy conclusion lacks a build decision")
    artifact_types = {item.artifact_type for item in conclusion.evidence_refs}
    required = {"implementation_version", "implementation_validation_report"}
    if not required.issubset(artifact_types):
        raise ValueError(
            "ready Strategy conclusion requires implementation and admission refs"
        )


def _required_conclusion(turn: StrategyAgentTurn) -> SpecialistConclusion:
    """Return the selected conclusion or reject an inconsistent turn."""
    if turn.final_conclusion is None:
        raise ValueError("return_result turn is missing final_conclusion")
    return turn.final_conclusion


def _failed_return(
    *,
    delegation: SpecialistDelegation,
    program: AgentProgram,
    profile: ModelProfile,
    catalogue: ToolCatalogue,
    ledger: BudgetLedger,
    observed_refs: list[CanonicalEvidenceRef],
    error: Exception,
) -> SpecialistReturn:
    """Build a bounded fail-closed return for runtime/policy failures."""
    code = error.code if isinstance(error, PolicyViolation) else "strategy_agent_failed"
    conclusion = SpecialistConclusion(
        status=SpecialistStatus.FAILED,
        unresolved_questions=[delegation.task.question],
        findings=["Strategy Engineering did not reach a validated admission verdict."],
        evidence_refs=observed_refs,
        blockers=[PublicIssue(code=code, message=str(error)[:1_000])],
        advisory_next_actions=["review the blocker before any new candidate attempt"],
    )
    return build_specialist_return(
        delegation=delegation,
        role=AgentRole.STRATEGY_ENGINEERING.value,
        program_id=program.program_id,
        model_profile_id=profile.profile_id,
        tool_catalog_id=catalogue.catalogue_id,
        conclusion=conclusion,
        budget_used=ledger.usage,
        available_evidence_refs=observed_refs,
    )


def _public_lifecycle(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return lifecycle facts safe for model context and tracing."""
    return {key: value for key, value in state.items() if key != "package_source_hash"}


def _first_ref(
    observation: ToolObservation,
    artifact_type: str,
) -> CanonicalEvidenceRef | None:
    """Return the first exact observed ref of one artifact type."""
    return next(
        (
            reference
            for reference in observation.evidence_refs
            if reference.artifact_type == artifact_type
        ),
        None,
    )


def _mapping(value: object) -> Mapping[str, Any]:
    """Normalize an optional mapping in one bounded observation."""
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_integer(value: object) -> int | None:
    """Return an exact non-boolean integer or no value."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
