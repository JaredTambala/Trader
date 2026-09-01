"""Model/tool control loop for the first-slice Data Research specialist."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from trader_research.governance import AgentBudget, ResearchSession

from .catalogue import ToolCatalogue
from .contracts import (
    AgentPhase,
    AgentRole,
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
    ) -> SpecialistReturn:
        """Execute one bounded Data specialist invocation.

        Args:
            session: Immutable operator authority and global ceilings.
            delegation: Exact task, branch, side effects, and reservation.
            scope: Complete role-labelled approved Data requirement.
            program: Exact Data Research model program.
            profile: Exact admitted model profile.

        Returns:
            Trusted specialist return with measured usage and observed refs.
        """
        _validate_entry(session, delegation, scope, program, profile)
        ledger = BudgetLedger(_delegation_budget(session, delegation))
        runtime = RoleScopedMcpRuntime(
            client=self.mcp_client,
            catalogue=self.tool_catalogue,
            ledger=ledger,
            trace_sink=self.trace_sink,
        )
        phase = AgentPhase.INVESTIGATE
        observations: list[ToolObservation] = []
        observed_refs: dict[str, CanonicalEvidenceRef] = {}
        loop_fingerprints: dict[str, int] = {}
        successful_steps: list[tuple[str, Mapping[str, Any]]] = []
        correlation = TraceCorrelation(
            session_id=session.session_id,
            branch_id=delegation.branch_id,
            delegation_id=delegation.delegation_id,
            attempt_id=delegation.attempt_id,
            program_id=program.program_id,
            model_profile_id=profile.profile_id,
            tool_catalog_id=self.tool_catalogue.catalogue_id,
        )

        try:
            while ledger.usage.model_calls < delegation.reserved_model_calls:
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
                        "observations": [
                            item.model_dump(mode="json")
                            for item in observations[-12:]
                        ],
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
                    return build_specialist_return(
                        delegation=delegation,
                        role=AgentRole.DATA_RESEARCH.value,
                        program_id=program.program_id,
                        model_profile_id=profile.profile_id,
                        tool_catalog_id=self.tool_catalogue.catalogue_id,
                        conclusion=conclusion,
                        budget_used=ledger.usage,
                        available_evidence_refs=list(observed_refs.values()),
                    )
                if turn.action == "change_phase":
                    phase = _next_data_phase(phase, turn.next_phase)
                    continue
                proposal = turn.tool_call
                if proposal is None:
                    raise ValueError("call_tool turn is missing a tool proposal")
                result = await runtime.execute(
                    proposal,
                    context=context,
                    correlation=correlation,
                )
                fingerprint = result.authorized_call.fingerprint
                prior = loop_fingerprints.get(fingerprint, 0)
                if prior:
                    ledger.record_revision()
                loop_fingerprints[fingerprint] = prior + 1
                observations.append(result.observation)
                for reference in result.observation.evidence_refs:
                    observed_refs[reference.uri] = reference
                if result.observation.ok:
                    successful_steps.append(
                        (proposal.tool_name, dict(proposal.arguments))
                    )
            raise PolicyViolation(
                "delegation_model_budget_exhausted",
                "Data Research did not reach a conclusion inside its model reservation",
            )
        except (PolicyViolation, StructuredOutputError, RuntimeError, ValueError) as exc:
            return _failed_return(
                session=session,
                delegation=delegation,
                program=program,
                profile=profile,
                catalogue=self.tool_catalogue,
                ledger=ledger,
                observed_refs=list(observed_refs.values()),
                error=exc,
            )


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
    usage: Any,
    loop_fingerprints: Mapping[str, int],
    successful_steps: list[tuple[str, Mapping[str, Any]]],
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
    successful_steps: list[tuple[str, Mapping[str, Any]]],
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
        if not any(_arguments_cover_item(arguments, item) for arguments in snapshot_arguments)
    ]
    if missing:
        raise ValueError(
            "ready Data conclusion lacks exact snapshots for: "
            + ", ".join(missing)
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
