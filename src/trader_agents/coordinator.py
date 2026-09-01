"""LangGraph Research Coordinator for the first agentic implementation slice."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from trader_research.foundation import json_payload_hash, stable_research_id
from trader_research.governance import (
    AgentBudgetUsage,
    AgentDecisionStatus,
    ArtifactReportRef,
    ResearchIssue,
    ResearchSession,
    build_agent_decision_receipt,
)

from .catalogue import ToolCatalogue
from .checkpointing import AgentCheckpointState, validate_agent_checkpoint_state
from .contracts import (
    AgentPhase,
    AgentRole,
    AgenticSliceResult,
    BudgetUsage,
    CanonicalEvidenceRef,
    CoordinatorAction,
    CoordinatorAgenda,
    CoordinatorDecision,
    PublicIssue,
    SpecialistDelegation,
    SpecialistReturn,
    SpecialistStatus,
    ToolCallProposal,
    build_delegation,
)
from .data_research import DataResearchAgent
from .inputs import (
    composite_data_scope_from_session,
    strategy_build_contract_from_session,
)
from .mcp_runtime import RoleScopedMcpRuntime
from .policy import BudgetLedger, PolicyContext
from .profiles import AgentProgramRegistry, ModelProfileRegistry
from .scheduler import SchedulingError, compute_ready_set
from .strategy_engineering import StrategyEngineeringAgent
from .structured_model import StructuredModelRunner
from .tool_client import McpToolClient
from .tracing import NoOpTraceSink, TraceCorrelation, TraceSink


@dataclass
class ResearchCoordinator:
    """Build the single-writer coordinator graph over isolated specialists.

    Attributes:
        model_runner: Strict coordinator model invocation boundary.
        mcp_client: Coordinator-owned MCP transport.
        data_agent: Isolated Data Research specialist runtime.
        strategy_agent: Isolated Strategy Engineering specialist runtime.
        tool_catalogue: Exact code-owned MCP catalogue.
        programs: Exact versioned agent-program registry.
        model_profiles: Exact admitted model-profile registry.
        trace_sink: Optional redacted trace backend.
    """

    model_runner: StructuredModelRunner
    mcp_client: McpToolClient
    data_agent: DataResearchAgent
    strategy_agent: StrategyEngineeringAgent
    tool_catalogue: ToolCatalogue
    programs: AgentProgramRegistry
    model_profiles: ModelProfileRegistry
    trace_sink: TraceSink = NoOpTraceSink()

    def build_graph(
        self,
        *,
        session: ResearchSession,
        checkpointer: BaseCheckpointSaver[Any] | None,
    ) -> Any:
        """Compile the resumable first-slice LangGraph.

        Args:
            session: Immutable operator-approved research session.
            checkpointer: Operational saver. Production callers provide the
                dedicated Postgres saver; tests may inject an in-memory saver.

        Returns:
            Compiled graph with coordinator-only state writes and interrupts.
        """
        coordinator_program = self.programs.for_role(
            AgentRole.RESEARCH_COORDINATOR
        )
        profile = self.model_profiles.get(session.model_profile_id)

        async def ensure_session_node(
            state: AgentCheckpointState,
        ) -> AgentCheckpointState:
            """Idempotently persist the immutable session through MCP."""
            _validate_state_session(state, session)
            ledger = _ledger(session, state)
            runtime = self._coordinator_runtime(ledger)
            context = _coordinator_policy_context(
                session=session,
                state=state,
                catalogue=self.tool_catalogue,
                program_id=coordinator_program.program_id,
                phase=AgentPhase.INTERPRET,
                usage=ledger.usage,
            )
            proposal = ToolCallProposal(
                call_id=f"create-session-{session.session_id}",
                tool_name="research_create_agent_session",
                arguments={"session": session.to_dict()},
                purpose="Persist the exact operator-approved research boundary.",
                expected_evidence=["canonical research session ref"],
                mutation_reason="Create or idempotently confirm the immutable session.",
            )
            result = await runtime.execute(
                proposal,
                context=context,
                correlation=_correlation(
                    session=session,
                    branch_id=str(state["branch_id"]),
                    program_id=coordinator_program.program_id,
                    tool_catalog_id=self.tool_catalogue.catalogue_id,
                ),
            )
            if not result.observation.ok:
                raise RuntimeError("research session persistence failed")
            evidence = _merge_refs(
                _refs_from_state(state),
                result.observation.evidence_refs,
            )
            return {
                "status": "running",
                "phase": AgentPhase.INTERPRET.value,
                "budget_usage": ledger.usage.model_dump(mode="json"),
                "evidence_refs": _dump_refs(evidence),
            }

        async def interpret_node(
            state: AgentCheckpointState,
        ) -> AgentCheckpointState:
            """Ask the model for a visible bounded agenda."""
            _validate_state_session(state, session)
            ledger = _ledger(session, state)
            prior_agenda = dict(state.get("agenda", {}))
            operator_response = dict(state.get("operator_response", {}))
            invocation = await self.model_runner.invoke(
                program=coordinator_program,
                profile=profile,
                output_type=CoordinatorAgenda,
                instruction=(
                    "Interpret the operator objective into a visible first-slice "
                    "agenda. Declare material ambiguity instead of inventing "
                    "strategy semantics. Include Data Research and Strategy "
                    "Engineering tasks when the approved inputs are sufficient."
                ),
                public_context={
                    "session": _public_session(session),
                    "prior_agenda": prior_agenda,
                    "accepted_specialist_returns": list(
                        state.get("specialist_returns", [])
                    ),
                    "operator_response": operator_response,
                    "scope_contracts": {
                        "data_scope": composite_data_scope_from_session(
                            session
                        ).model_dump(mode="json"),
                        "implementation_specification_present": (
                            session.implementation_specification is not None
                        ),
                    },
                },
                ledger=ledger,
                correlation=_correlation(
                    session=session,
                    branch_id=str(state["branch_id"]),
                    program_id=coordinator_program.program_id,
                    tool_catalog_id=self.tool_catalogue.catalogue_id,
                ),
            )
            agenda = invocation.output
            _validate_first_slice_agenda(agenda)
            branch_by_task = {
                task.task_id: _branch_id(session.session_id, task.task_id)
                for task in agenda.tasks
            }
            existing_attempts = dict(state.get("task_attempts", {}))
            return {
                "agenda": agenda.model_dump(mode="json"),
                "branch_by_task": branch_by_task,
                "task_attempts": {
                    task.task_id: int(existing_attempts.get(task.task_id, 0))
                    for task in agenda.tasks
                },
                "completed_task_ids": [],
                "operator_response": {},
                "status": "running",
                "phase": AgentPhase.INTERPRET.value,
                "budget_usage": ledger.usage.model_dump(mode="json"),
            }

        async def dispatch_node(
            state: AgentCheckpointState,
        ) -> AgentCheckpointState:
            """Run only the scheduler's legal ready set and hard-join results."""
            _validate_state_session(state, session)
            agenda = CoordinatorAgenda.model_validate(state.get("agenda", {}))
            ledger = _ledger(session, state)
            mutation_keys = {
                task.task_id: (
                    f"data-scope:{composite_data_scope_from_session(session).scope_id}"
                    if task.role == AgentRole.DATA_RESEARCH.value
                    else f"candidate-branch:{state['branch_by_task'][task.task_id]}"
                ,)
                for task in agenda.tasks
            }
            ready = compute_ready_set(
                agenda,
                completed_task_ids=list(state.get("completed_task_ids", [])),
                mutation_keys_by_task=mutation_keys,
                budget=session.budget,
                usage=ledger.usage,
            )
            if not ready:
                if set(state.get("completed_task_ids", [])) == {
                    task.task_id for task in agenda.tasks
                }:
                    return {"phase": AgentPhase.REVIEW.value}
                raise SchedulingError("agenda has pending work but no legal ready task")
            attempts = dict(state.get("task_attempts", {}))
            branches = dict(state.get("branch_by_task", {}))
            delegations = []
            coroutines = []
            for scheduled in ready:
                task = scheduled.task
                attempt = int(attempts.get(task.task_id, 0)) + 1
                attempts[task.task_id] = attempt
                branch_id = str(branches[task.task_id])
                delegation = build_delegation(
                    session_id=session.session_id,
                    branch_id=branch_id,
                    task=task,
                    required_input_refs=_refs_from_state(state),
                    permitted_side_effects=["read_only", "local_mutating"],
                    reserved_model_calls=scheduled.reservation.model_calls,
                    reserved_tool_calls=scheduled.reservation.tool_calls,
                    reserved_tokens=scheduled.reservation.tokens,
                    attempt=attempt,
                )
                delegations.append(delegation)
                if task.role == AgentRole.DATA_RESEARCH.value:
                    data_program = self.programs.for_role(AgentRole.DATA_RESEARCH)
                    coroutines.append(
                        self.data_agent.run(
                            session=session,
                            delegation=delegation,
                            scope=composite_data_scope_from_session(session),
                            program=data_program,
                            profile=self.model_profiles.get(
                                data_program.model_profile_id
                            ),
                        )
                    )
                else:
                    strategy_program = self.programs.for_role(
                        AgentRole.STRATEGY_ENGINEERING
                    )
                    coroutines.append(
                        self.strategy_agent.run(
                            session=session,
                            delegation=delegation,
                            build_contract=strategy_build_contract_from_session(
                                session,
                                branch_id=branch_id,
                            ),
                            program=strategy_program,
                            profile=self.model_profiles.get(
                                strategy_program.model_profile_id
                            ),
                        )
                    )
            results = await asyncio.gather(*coroutines)
            accepted, digests = _accept_specialist_returns(
                state,
                delegations=delegations,
                results=results,
            )
            completed = list(state.get("completed_task_ids", []))
            for delegation, result in zip(delegations, results, strict=True):
                if result.delegation_id == delegation.delegation_id:
                    completed.append(delegation.task.task_id)
                    ledger.merge(result.budget_used)
            evidence = _merge_refs(
                _refs_from_state(state),
                *(result.evidence_refs for result in results),
            )
            return {
                "delegations": [
                    *state.get("delegations", []),
                    *(item.model_dump(mode="json") for item in delegations),
                ],
                "specialist_returns": [
                    *state.get("specialist_returns", []),
                    *(item.model_dump(mode="json") for item in accepted),
                ],
                "accepted_return_digests": digests,
                "completed_task_ids": list(dict.fromkeys(completed)),
                "task_attempts": attempts,
                "evidence_refs": _dump_refs(evidence),
                "budget_usage": ledger.usage.model_dump(mode="json"),
                "phase": AgentPhase.REVIEW.value,
                "status": "running",
            }

        async def review_node(
            state: AgentCheckpointState,
        ) -> AgentCheckpointState:
            """Verify every new return and ask the model for one public decision."""
            _validate_state_session(state, session)
            ledger = _ledger(session, state)
            returns = [
                SpecialistReturn.model_validate(item)
                for item in state.get("specialist_returns", [])
            ]
            cursor = int(state.get("review_cursor", 0))
            new_returns = returns[cursor:]
            verified = await self._verify_evidence(
                session=session,
                state=state,
                program_id=coordinator_program.program_id,
                ledger=ledger,
                references=_merge_refs(
                    (),
                    *(item.evidence_refs for item in new_returns),
                ),
            )
            agenda = CoordinatorAgenda.model_validate(state.get("agenda", {}))
            invocation = await self.model_runner.invoke(
                program=coordinator_program,
                profile=profile,
                output_type=CoordinatorDecision,
                instruction=(
                    "Review every supplied specialist return and verified exact "
                    "artifact. Choose advance, revise, revisit, fork, ask_operator, "
                    "conclude, or stop_fail_closed. Do not claim efficacy."
                ),
                public_context={
                    "session_objective": session.objective,
                    "success_definition": session.success_definition,
                    "agenda": agenda.model_dump(mode="json"),
                    "new_specialist_returns": [
                        item.model_dump(mode="json") for item in new_returns
                    ],
                    "all_specialist_returns": [
                        item.model_dump(mode="json") for item in returns
                    ],
                    "verified_artifacts": verified,
                    "operator_response": dict(state.get("operator_response", {})),
                    "budget_used": ledger.usage.model_dump(mode="json"),
                },
                ledger=ledger,
                correlation=_correlation(
                    session=session,
                    branch_id=str(state["branch_id"]),
                    program_id=coordinator_program.program_id,
                    tool_catalog_id=self.tool_catalogue.catalogue_id,
                ),
            )
            decision = invocation.output
            try:
                _validate_coordinator_decision(
                    decision,
                    agenda=agenda,
                    new_returns=new_returns,
                    all_returns=returns,
                    verified_refs=[item["reference"] for item in verified],
                    completed_task_ids=list(state.get("completed_task_ids", [])),
                )
            except ValueError as exc:
                decision = _fail_closed_decision(
                    code="invalid_coordinator_decision",
                    message=str(exc),
                    reviewed_delegation_ids=[
                        item.delegation_id for item in new_returns
                    ],
                )
            receipt_ref = await self._record_decision(
                session=session,
                state=state,
                decision=decision,
                program_id=coordinator_program.program_id,
                ledger=ledger,
            )
            updates = _apply_decision(
                state,
                session=session,
                decision=decision,
                returns=returns,
                receipt_ref=receipt_ref,
                budget=ledger.usage,
            )
            updates["review_cursor"] = len(returns)
            updates["decision"] = decision.model_dump(mode="json")
            updates["decision_receipt_ref"] = receipt_ref.model_dump(mode="json")
            updates["budget_usage"] = ledger.usage.model_dump(mode="json")
            updates["next_sequence"] = int(state.get("next_sequence", 1)) + 1
            return cast(AgentCheckpointState, updates)

        def operator_interrupt_node(
            state: AgentCheckpointState,
        ) -> AgentCheckpointState:
            """Suspend and accept one bounded public operator response."""
            pending = dict(state.get("pending_interrupt", {}))
            if not pending:
                raise ValueError("operator interrupt has no pending request")
            raw_response = interrupt(pending)
            if not isinstance(raw_response, Mapping):
                raise ValueError("operator resume value must be an object")
            response = {
                "approved": raw_response.get("approved"),
                "answer": str(raw_response.get("answer") or "").strip(),
                "operator_id": str(raw_response.get("operator_id") or "").strip(),
            }
            if response["operator_id"] != session.operator_id:
                raise ValueError("operator resume identity does not match the session")
            if not isinstance(response["approved"], bool):
                raise ValueError("operator resume approved must be a boolean")
            if not response["answer"] or len(str(response["answer"])) > 2_000:
                raise ValueError("operator resume answer must contain 1 to 2000 characters")
            return {
                "operator_response": response,
                "pending_interrupt": {},
                "status": "running",
                "phase": AgentPhase.INTERPRET.value,
            }

        graph = StateGraph(AgentCheckpointState)
        graph.add_node("ensure_session", ensure_session_node)
        graph.add_node("interpret_brief", interpret_node)
        graph.add_node("dispatch_ready_specialists", dispatch_node)
        graph.add_node("review_evidence", review_node)
        graph.add_node("await_operator", operator_interrupt_node)
        graph.add_edge(START, "ensure_session")
        graph.add_edge("ensure_session", "interpret_brief")
        graph.add_conditional_edges(
            "interpret_brief",
            _route_after_interpret,
            {
                "dispatch": "dispatch_ready_specialists",
                "review": "review_evidence",
            },
        )
        graph.add_edge("dispatch_ready_specialists", "review_evidence")
        graph.add_conditional_edges(
            "review_evidence",
            _route_after_review,
            {
                "dispatch": "dispatch_ready_specialists",
                "interrupt": "await_operator",
                "end": END,
            },
        )
        graph.add_edge("await_operator", "interpret_brief")
        return graph.compile(checkpointer=checkpointer)

    def _coordinator_runtime(self, ledger: BudgetLedger) -> RoleScopedMcpRuntime:
        """Build a coordinator-scoped MCP runtime over the shared transport."""
        return RoleScopedMcpRuntime(
            client=self.mcp_client,
            catalogue=self.tool_catalogue,
            ledger=ledger,
            trace_sink=self.trace_sink,
        )

    async def _verify_evidence(
        self,
        *,
        session: ResearchSession,
        state: AgentCheckpointState,
        program_id: str,
        ledger: BudgetLedger,
        references: Sequence[CanonicalEvidenceRef],
    ) -> list[dict[str, Any]]:
        """Dereference every material specialist ref through coordinator MCP."""
        runtime = self._coordinator_runtime(ledger)
        verified = []
        for reference in references:
            context = _coordinator_policy_context(
                session=session,
                state=state,
                catalogue=self.tool_catalogue,
                program_id=program_id,
                phase=AgentPhase.REVIEW,
                usage=ledger.usage,
            )
            proposal = ToolCallProposal(
                call_id=f"verify-{json_payload_hash(reference.model_dump(mode='json'))[:20]}",
                tool_name="research_read_artifact",
                arguments={
                    "artifact_ref": reference.uri,
                    "expected_artifact_type": reference.artifact_type,
                    "max_payload_bytes": 64_000,
                    "include_payload": False,
                },
                purpose="Independently verify specialist canonical evidence.",
                expected_evidence=["exact canonical identity and payload hash"],
            )
            result = await runtime.execute(
                proposal,
                context=context,
                correlation=_correlation(
                    session=session,
                    branch_id=str(state["branch_id"]),
                    program_id=program_id,
                    tool_catalog_id=self.tool_catalogue.catalogue_id,
                ),
            )
            if not result.observation.ok:
                raise RuntimeError(f"canonical evidence verification failed: {reference.uri}")
            returned = {item.uri: item for item in result.observation.evidence_refs}
            if reference.uri not in returned:
                raise RuntimeError("canonical read did not return the requested exact ref")
            record = result.observation.summary.get("record")
            if not isinstance(record, Mapping):
                raise RuntimeError("canonical read returned no bounded record metadata")
            if record.get("domain_owner") != reference.domain_owner:
                raise RuntimeError("canonical evidence owner does not match specialist ref")
            verified.append(
                {
                    "reference": reference.model_dump(mode="json"),
                    "status": record.get("status"),
                    "producer_tool": record.get("producer_tool"),
                    "payload_hash": record.get("payload_hash"),
                    "source_hash": record.get("source_hash"),
                }
            )
        return verified

    async def _record_decision(
        self,
        *,
        session: ResearchSession,
        state: AgentCheckpointState,
        decision: CoordinatorDecision,
        program_id: str,
        ledger: BudgetLedger,
    ) -> CanonicalEvidenceRef:
        """Persist one append-only public decision receipt through MCP."""
        status = _receipt_status(decision.action)
        receipt = build_agent_decision_receipt(
            session_id=session.session_id,
            branch_id=str(state["branch_id"]),
            sequence=int(state.get("next_sequence", 1)),
            actor="Research Coordinator",
            program_id=program_id,
            model_profile_id=session.model_profile_id,
            action=decision.action.value,
            status=status,
            summary=decision.summary,
            evidence_refs=tuple(_artifact_ref(item) for item in decision.cited_evidence_refs),
            budget_used=AgentBudgetUsage(
                model_calls=ledger.usage.model_calls,
                tool_calls=ledger.usage.tool_calls,
                tokens=ledger.usage.total_tokens,
                duration_ms=ledger.usage.duration_ms,
                mutations=ledger.usage.mutations,
                revisions=ledger.usage.revisions,
            ),
            blockers=_receipt_blockers(decision),
            next_actions=tuple(decision.permitted_next_actions),
            metadata={
                "tool_catalog_id": self.tool_catalogue.catalogue_id,
                "reviewed_delegation_ids": decision.reviewed_delegation_ids,
            },
        )
        runtime = self._coordinator_runtime(ledger)
        context = _coordinator_policy_context(
            session=session,
            state=state,
            catalogue=self.tool_catalogue,
            program_id=program_id,
            phase=(
                AgentPhase.AWAITING_OPERATOR
                if decision.action is CoordinatorAction.ASK_OPERATOR
                else AgentPhase.TERMINAL
                if decision.action in {
                    CoordinatorAction.CONCLUDE,
                    CoordinatorAction.STOP_FAIL_CLOSED,
                }
                else AgentPhase.REVIEW
            ),
            usage=ledger.usage,
        )
        proposal = ToolCallProposal(
            call_id=f"decision-{receipt.receipt_id}",
            tool_name="research_record_agent_decision",
            arguments={"receipt": receipt.to_dict()},
            purpose="Persist the accepted public coordinator transition.",
            expected_evidence=["canonical decision receipt"],
            mutation_reason="Append the coordinator's public evidence decision.",
        )
        result = await runtime.execute(
            proposal,
            context=context,
            correlation=_correlation(
                session=session,
                branch_id=str(state["branch_id"]),
                program_id=program_id,
                tool_catalog_id=self.tool_catalogue.catalogue_id,
            ),
        )
        if not result.observation.ok:
            raise RuntimeError("coordinator decision receipt persistence failed")
        reference = next(
            (
                item
                for item in result.observation.evidence_refs
                if item.artifact_type == "agent_decision_receipt"
            ),
            None,
        )
        if reference is None:
            raise RuntimeError("decision persistence returned no canonical receipt ref")
        return reference


def _validate_state_session(
    state: Mapping[str, Any],
    session: ResearchSession,
) -> None:
    """Require checkpoint and immutable session identities to match."""
    validate_agent_checkpoint_state(state)
    if state.get("session_id") != session.session_id:
        raise ValueError("checkpoint belongs to another research session")
    if state.get("session_digest") != session.session_digest:
        raise ValueError("checkpoint session digest has drifted")


def _ledger(
    session: ResearchSession,
    state: Mapping[str, Any],
) -> BudgetLedger:
    """Restore the cumulative public ledger from checkpoint state."""
    return BudgetLedger(
        session.budget,
        usage=BudgetUsage.model_validate(state.get("budget_usage", {})),
    )


def _coordinator_policy_context(
    *,
    session: ResearchSession,
    state: Mapping[str, Any],
    catalogue: ToolCatalogue,
    program_id: str,
    phase: AgentPhase,
    usage: BudgetUsage,
) -> PolicyContext:
    """Build fresh trusted policy state for coordinator lifecycle calls."""
    return PolicyContext(
        session=session,
        role=AgentRole.RESEARCH_COORDINATOR,
        phase=phase,
        program_id=program_id,
        tool_catalogue=catalogue,
        usage=usage,
        runtime_state={
            "branch_id": state.get("branch_id"),
            "next_sequence": state.get("next_sequence", 1),
        },
        loop_fingerprints=dict(state.get("loop_fingerprints", {})),
    )


def _validate_first_slice_agenda(agenda: CoordinatorAgenda) -> None:
    """Require both specialist responsibilities or explicit ambiguity."""
    if agenda.material_ambiguities:
        return
    roles = [task.role for task in agenda.tasks]
    required: set[Literal["data_research", "strategy_engineering"]] = {
        AgentRole.DATA_RESEARCH.value,
        AgentRole.STRATEGY_ENGINEERING.value,
    }
    if set(roles) != required:
        raise ValueError("first-slice agenda requires Data and Strategy tasks")
    if any(roles.count(role) != 1 for role in required):
        raise ValueError("first-slice agenda requires exactly one task per role")


def _accept_specialist_returns(
    state: Mapping[str, Any],
    *,
    delegations: Sequence[SpecialistDelegation],
    results: Sequence[SpecialistReturn],
) -> tuple[list[SpecialistReturn], dict[str, str]]:
    """Validate isolated returns and reject replay/conflicting identities."""
    if len(delegations) != len(results):
        raise ValueError("specialist result cardinality does not match dispatch")
    digests = dict(state.get("accepted_return_digests", {}))
    accepted = []
    for delegation, result in zip(delegations, results, strict=True):
        if result.delegation_id != delegation.delegation_id:
            raise ValueError("specialist return delegation identity mismatch")
        if result.attempt_id != delegation.attempt_id:
            raise ValueError("specialist return attempt identity mismatch")
        if result.session_id != delegation.session_id:
            raise ValueError("specialist return session identity mismatch")
        digest = json_payload_hash(result.model_dump(mode="json"))
        existing = digests.get(result.delegation_id)
        if existing is not None and existing != digest:
            raise ValueError("delegation return replayed with conflicting content")
        if existing is None:
            accepted.append(result)
            digests[result.delegation_id] = digest
    return accepted, digests


def _validate_coordinator_decision(
    decision: CoordinatorDecision,
    *,
    agenda: CoordinatorAgenda,
    new_returns: Sequence[SpecialistReturn],
    all_returns: Sequence[SpecialistReturn],
    verified_refs: Sequence[Mapping[str, Any]],
    completed_task_ids: Sequence[str],
) -> None:
    """Validate model-owned transition against verified public state."""
    expected_reviewed = {item.delegation_id for item in new_returns}
    if set(decision.reviewed_delegation_ids) != expected_reviewed:
        raise ValueError("coordinator must review every newly joined specialist return")
    verified_uris = {str(item.get("uri") or "") for item in verified_refs}
    cited_uris = {item.uri for item in decision.cited_evidence_refs}
    if not cited_uris.issubset(verified_uris):
        raise ValueError("coordinator cited evidence that was not independently verified")
    known_tasks = {task.task_id for task in agenda.tasks}
    if not set(decision.affected_task_ids).issubset(known_tasks):
        raise ValueError("coordinator decision affects an unknown agenda task")
    if decision.action in {
        CoordinatorAction.REVISE,
        CoordinatorAction.REVISIT,
        CoordinatorAction.FORK,
    } and not decision.affected_task_ids:
        raise ValueError("revision, revisit, or fork requires affected tasks")
    if decision.action is CoordinatorAction.CONCLUDE:
        latest_by_role = {item.role: item for item in all_returns}
        if set(latest_by_role) != {
            AgentRole.DATA_RESEARCH.value,
            AgentRole.STRATEGY_ENGINEERING.value,
        }:
            raise ValueError("conclusion requires both specialist returns")
        if any(
            item.status is not SpecialistStatus.READY
            for item in latest_by_role.values()
        ):
            raise ValueError("conclusion requires ready Data and Strategy returns")
        if set(completed_task_ids) != known_tasks:
            raise ValueError("conclusion requires every agenda task to be completed")


def _apply_decision(
    state: Mapping[str, Any],
    *,
    session: ResearchSession,
    decision: CoordinatorDecision,
    returns: Sequence[SpecialistReturn],
    receipt_ref: CanonicalEvidenceRef,
    budget: BudgetUsage,
) -> dict[str, Any]:
    """Apply one validated model decision as deterministic graph state."""
    updates: dict[str, Any] = {"phase": AgentPhase.REVIEW.value}
    if decision.action is CoordinatorAction.ASK_OPERATOR:
        updates.update(
            {
                "status": "awaiting_operator",
                "phase": AgentPhase.AWAITING_OPERATOR.value,
                "pending_interrupt": {
                    "kind": "operator_clarification_required",
                    "question": decision.operator_question,
                    "requested_action": "answer_or_decline",
                    "resume_schema": {
                        "type": "object",
                        "required": ["approved", "answer", "operator_id"],
                    },
                },
            }
        )
        return updates
    if decision.action in {
        CoordinatorAction.CONCLUDE,
        CoordinatorAction.STOP_FAIL_CLOSED,
    }:
        status: Literal["completed", "blocked"] = (
            "completed"
            if decision.action is CoordinatorAction.CONCLUDE
            else "blocked"
        )
        data_return = _latest_return(returns, AgentRole.DATA_RESEARCH.value)
        strategy_return = _latest_return(
            returns,
            AgentRole.STRATEGY_ENGINEERING.value,
        )
        result = AgenticSliceResult(
            session_id=session.session_id,
            branch_id=str(state["branch_id"]),
            status=status,
            summary=decision.summary,
            data_return=data_return,
            strategy_return=strategy_return,
            decision=decision,
            decision_receipt_ref=receipt_ref,
            budget_used=budget,
            permitted_next_actions=decision.permitted_next_actions,
        )
        updates.update(
            {
                "status": "completed" if status == "completed" else "blocked",
                "phase": AgentPhase.TERMINAL.value,
                "pending_interrupt": {},
                "terminal_result": result.model_dump(mode="json"),
            }
        )
        return updates
    completed = list(state.get("completed_task_ids", []))
    if decision.action in {
        CoordinatorAction.REVISE,
        CoordinatorAction.REVISIT,
        CoordinatorAction.FORK,
    }:
        affected = set(decision.affected_task_ids)
        completed = [task_id for task_id in completed if task_id not in affected]
        if decision.action is CoordinatorAction.FORK:
            branches = dict(state.get("branch_by_task", {}))
            for task_id in affected:
                branches[task_id] = stable_research_id(
                    "agent_fork_branch",
                    {
                        "session_id": session.session_id,
                        "task_id": task_id,
                        "prior_branch": branches[task_id],
                        "sequence": state.get("next_sequence", 1),
                    },
                )
            updates["branch_by_task"] = branches
    updates.update(
        {
            "status": "running",
            "completed_task_ids": completed,
            "pending_interrupt": {},
        }
    )
    return updates


def _fail_closed_decision(
    *,
    code: str,
    message: str,
    reviewed_delegation_ids: Sequence[str] = (),
) -> CoordinatorDecision:
    """Build a deterministic public stop when model output violates policy."""
    return CoordinatorDecision(
        action=CoordinatorAction.STOP_FAIL_CLOSED,
        summary="The coordinator stopped because its proposed transition failed policy validation.",
        reviewed_delegation_ids=list(reviewed_delegation_ids),
        criteria_applied=["deterministic coordinator transition policy"],
        blockers=[PublicIssue(code=code, message=message[:1_000])],
        permitted_next_actions=["inspect the blocker and start a corrected session"],
    )


def _route_after_interpret(
    state: AgentCheckpointState,
) -> Literal["dispatch", "review"]:
    """Route explicit ambiguities to review before specialist dispatch."""
    agenda = CoordinatorAgenda.model_validate(state.get("agenda", {}))
    return "review" if agenda.material_ambiguities else "dispatch"


def _route_after_review(
    state: AgentCheckpointState,
) -> Literal["dispatch", "interrupt", "end"]:
    """Route only from accepted public coordinator state."""
    status = str(state.get("status") or "")
    if status == "awaiting_operator":
        return "interrupt"
    if status in {"completed", "blocked", "failed"}:
        return "end"
    return "dispatch"


def _public_session(session: ResearchSession) -> dict[str, Any]:
    """Return authority and objective fields needed for agenda formation."""
    return {
        "session_id": session.session_id,
        "objective": session.objective,
        "success_definition": session.success_definition,
        "approval_policy": dict(session.approval_policy),
        "scope_envelope": dict(session.scope_envelope),
        "implementation_specification": session.implementation_specification,
        "python_quality_guide": session.python_quality_guide,
        "budget": session.budget.to_dict(),
    }


def _branch_id(session_id: str, task_id: str) -> str:
    """Derive one stable root specialist branch identity."""
    return stable_research_id(
        "agent_branch",
        {"session_id": session_id, "task_id": task_id},
    )


def _correlation(
    *,
    session: ResearchSession,
    branch_id: str,
    program_id: str,
    tool_catalog_id: str,
) -> TraceCorrelation:
    """Build the coordinator's stable redacted trace identities."""
    return TraceCorrelation(
        session_id=session.session_id,
        branch_id=branch_id,
        program_id=program_id,
        model_profile_id=session.model_profile_id,
        tool_catalog_id=tool_catalog_id,
    )


def _refs_from_state(state: Mapping[str, Any]) -> list[CanonicalEvidenceRef]:
    """Parse exact canonical refs from checkpoint state."""
    return [
        CanonicalEvidenceRef.model_validate(item)
        for item in state.get("evidence_refs", [])
    ]


def _merge_refs(
    first: Sequence[CanonicalEvidenceRef],
    *groups: Sequence[CanonicalEvidenceRef],
) -> list[CanonicalEvidenceRef]:
    """Merge exact refs in first-seen order by canonical URI."""
    merged: dict[str, CanonicalEvidenceRef] = {item.uri: item for item in first}
    for group in groups:
        for item in group:
            merged.setdefault(item.uri, item)
    return list(merged.values())


def _dump_refs(
    references: Sequence[CanonicalEvidenceRef],
) -> list[dict[str, Any]]:
    """Serialize exact refs for operational state."""
    return [item.model_dump(mode="json") for item in references]


def _artifact_ref(reference: CanonicalEvidenceRef) -> ArtifactReportRef:
    """Convert the strict agent ref to the canonical governance contract."""
    return ArtifactReportRef(
        artifact_id=reference.artifact_id,
        artifact_type=reference.artifact_type,
        domain_owner=reference.domain_owner,
        uri=reference.uri,
    )


def _receipt_status(action: CoordinatorAction) -> AgentDecisionStatus:
    """Map coordinator action to canonical receipt lifecycle."""
    if action is CoordinatorAction.ASK_OPERATOR:
        return AgentDecisionStatus.AWAITING_OPERATOR
    if action is CoordinatorAction.STOP_FAIL_CLOSED:
        return AgentDecisionStatus.BLOCKED
    if action is CoordinatorAction.CONCLUDE:
        return AgentDecisionStatus.TERMINAL
    return AgentDecisionStatus.ACCEPTED


def _receipt_blockers(
    decision: CoordinatorDecision,
) -> tuple[ResearchIssue, ...]:
    """Translate public blockers and operator questions to receipt issues."""
    blockers = tuple(
        ResearchIssue(
            code=item.code,
            message=item.message,
            details=item.details,
        )
        for item in decision.blockers
    )
    if blockers or decision.action is not CoordinatorAction.ASK_OPERATOR:
        return blockers
    return (
        ResearchIssue(
            code="operator_input_required",
            message=str(decision.operator_question or "Operator input is required."),
        ),
    )


def _latest_return(
    returns: Sequence[SpecialistReturn],
    role: str,
) -> SpecialistReturn | None:
    """Return the latest accepted specialist result for one role."""
    return next((item for item in reversed(returns) if item.role == role), None)
