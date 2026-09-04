"""User-facing runtime lifecycle for first-slice agentic research sessions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass, field
import os
from pathlib import Path
import shlex
import sys
from typing import Any, overload
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from trader_research.foundation import stable_research_id
from trader_research.governance import ResearchSession

from trader_agents.mcp.catalogue import ToolCatalogue, first_slice_tool_catalogue
from trader_agents.checkpointing import (
    AgentCheckpointState,
    agent_checkpoint_digest,
    agent_public_state,
    build_agent_checkpoint_state,
    coordinator_thread_config,
    open_postgres_checkpointer,
)
from trader_agents.contracts.domain import (
    AgentPhase,
    AgentRole,
    AgenticSliceResult,
    OperatorCancellation,
    OperatorInterrupt,
    OperatorResponse,
)
from trader_agents.coordination.coordinator import ResearchCoordinator
from trader_agents.specialists.data_research import DataResearchAgent
from trader_agents.contracts.inputs import validate_runtime_pins
from trader_agents.model_runtime.client import RuntimeConfiguredLlmClient
from trader_agents.observability.events import (
    AgentErrorCategory,
    AgentEventError,
    AgentEventName,
)
from trader_agents.observability.console import (
    AgentConsoleConfig,
    ConsoleObservabilityEventSink,
    agent_console_config,
)
from trader_agents.observability.emitter import AgentEventEmitter
from trader_agents.observability.projections import (
    project_checkpoint,
    project_terminal_result,
)
from trader_agents.model_runtime.profiles import (
    DEVELOPMENT_MODEL_PROFILE_ID,
    AgentProgramRegistry,
    ModelProfileRegistry,
    development_model_profiles,
    profile_environment,
)
from trader_agents.model_runtime.programs import first_slice_programs
from trader_agents.specialists.strategy_engineering import StrategyEngineeringAgent
from trader_agents.model_runtime.structured import StructuredModelRunner
from trader_agents.mcp.client import McpToolClient, PersistentStdioMcpToolClient
from trader_agents.observability.tracing import (
    MlflowTraceSink,
    NoOpTraceSink,
    TraceCorrelation,
    TraceSink,
    correlated_attributes,
)


_PROCESS_INSTANCE_ID = uuid4().hex
"""Public random process identity used only for recovery trace correlation."""


AgentRunOutcome = AgenticSliceResult | OperatorInterrupt
"""Public result of starting or resuming an agentic research session."""

McpClientDecorator = Callable[[AgentRole, McpToolClient], McpToolClient]
"""Compose a role-labelled client without changing transport ownership."""


@dataclass
class AgenticResearchRuntime:
    """Start, resume, and inspect one checkpoint-backed coordinator system.

    Attributes:
        coordinator: Fully wired coordinator and specialist system.
        checkpointer: Dedicated operational LangGraph checkpoint backend.
        tool_catalogue: Exact code-owned MCP catalogue.
        programs: Exact versioned agent programs.
        model_profiles: Exact admitted model profiles.
        trace_sink: Redacted lifecycle root-span sink shared with all runtime
            components.
        event_emitter: Process-scoped public event stream shared with all runtime
            components.
    """

    coordinator: ResearchCoordinator
    checkpointer: BaseCheckpointSaver[Any]
    tool_catalogue: ToolCatalogue
    programs: AgentProgramRegistry
    model_profiles: ModelProfileRegistry
    trace_sink: TraceSink = field(default_factory=NoOpTraceSink)
    event_emitter: AgentEventEmitter = field(default_factory=AgentEventEmitter)
    _active_tasks: dict[str, asyncio.Task[Any]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    async def start(self, session: ResearchSession) -> AgentRunOutcome:
        """Start, recover, or return the current exact research session.

        Args:
            session: Complete immutable operator-approved session.

        Returns:
            Terminal grounded result or bounded operator interrupt.
        """
        self._validate_session(session)
        with self._trace_operation(session, "start"):
            async with self._active_session(session.session_id):
                return await self._start_unlocked(session)

    async def _start_unlocked(
        self,
        session: ResearchSession,
    ) -> AgentRunOutcome:
        """Run start/recovery while this runtime owns the session task."""
        graph = self.coordinator.build_graph(
            session=session,
            checkpointer=self.checkpointer,
        )
        config = coordinator_thread_config(session.session_id)
        snapshot = await graph.aget_state(config)
        if snapshot.values:
            self._emit_checkpoint(AgentEventName.CHECKPOINT_RECOVERED, snapshot.values)
            self.event_emitter.emit(
                name=AgentEventName.SESSION_RESUMED,
                correlation=self._event_correlation(session),
                role=AgentRole.RESEARCH_COORDINATOR.value,
                fields={"lifecycle_operation": "start", "recovered": True},
            )
            current = _outcome_if_available(session.session_id, snapshot.values)
            if current is not None:
                return self._emit_outcome(session, current)
            output = await graph.ainvoke(None, config)
            self._emit_checkpoint(AgentEventName.CHECKPOINT_SAVED, output)
            return self._emit_outcome(
                session,
                _outcome(session.session_id, output),
            )
        coordinator_program = self.programs.for_role(AgentRole.RESEARCH_COORDINATOR)
        initial = build_agent_checkpoint_state(
            session_id=session.session_id,
            session_digest=session.session_digest,
            branch_id=_root_branch_id(session.session_id),
            coordinator_program_id=coordinator_program.program_id,
            model_profile_id=session.model_profile_id,
            tool_catalog_id=self.tool_catalogue.catalogue_id,
        )
        self.event_emitter.emit(
            name=AgentEventName.SESSION_STARTED,
            correlation=self._event_correlation(session),
            role=AgentRole.RESEARCH_COORDINATOR.value,
            fields={"lifecycle_operation": "start", "recovered": False},
        )
        output = await graph.ainvoke(initial, config)
        self._emit_checkpoint(AgentEventName.CHECKPOINT_SAVED, output)
        return self._emit_outcome(session, _outcome(session.session_id, output))

    async def resume(
        self,
        session: ResearchSession,
        response: OperatorResponse,
    ) -> AgentRunOutcome:
        """Resume one exact interrupted coordinator thread.

        Args:
            session: Same immutable session used to start the thread.
            response: Bounded operator identity, approval, and public answer.

        Returns:
            Terminal grounded result or a later bounded interrupt.
        """
        self._validate_session(session)
        if response.operator_id != session.operator_id:
            raise ValueError("operator response identity does not match the session")
        with self._trace_operation(session, "resume"):
            async with self._active_session(session.session_id):
                return await self._resume_unlocked(session, response)

    async def _resume_unlocked(
        self,
        session: ResearchSession,
        response: OperatorResponse,
    ) -> AgentRunOutcome:
        """Resume while this runtime owns the session task."""
        graph = self.coordinator.build_graph(
            session=session,
            checkpointer=self.checkpointer,
        )
        config = coordinator_thread_config(session.session_id)
        snapshot = await graph.aget_state(config)
        if not snapshot.values:
            raise ValueError("research session has no operational checkpoint")
        self._emit_checkpoint(AgentEventName.CHECKPOINT_RECOVERED, snapshot.values)
        self.event_emitter.emit(
            name=AgentEventName.SESSION_RESUMED,
            correlation=self._event_correlation(session),
            role=AgentRole.RESEARCH_COORDINATOR.value,
            fields={"lifecycle_operation": "resume", "recovered": True},
        )
        current = _outcome_if_available(session.session_id, snapshot.values)
        if current is not None:
            return self._emit_outcome(session, current)
        if not snapshot.interrupts:
            raise ValueError("research session is not awaiting operator input")
        output = await graph.ainvoke(
            Command(resume=response.model_dump(mode="json")),
            config,
        )
        self._emit_checkpoint(AgentEventName.CHECKPOINT_SAVED, output)
        return self._emit_outcome(session, _outcome(session.session_id, output))

    async def cancel(
        self,
        session: ResearchSession,
        cancellation: OperatorCancellation,
    ) -> AgenticSliceResult:
        """Cancel one checkpointed session and persist the public transition.

        An in-flight invocation owned by this runtime is cancelled first. The
        last completed checkpoint is then advanced to an explicit terminal
        state with a canonical cancelled decision receipt. Provider mutations
        interrupted at that boundary remain protected by their operation
        journals and are not blindly replayed.

        Args:
            session: Exact immutable research session to terminate.
            cancellation: Owning operator identity and bounded public reason.

        Returns:
            Terminal cancelled result retained in the coordinator checkpoint.
        """
        self._validate_session(session)
        if cancellation.operator_id != session.operator_id:
            raise ValueError("operator cancellation identity does not match session")
        with self._trace_operation(session, "cancel"):
            return await self._cancel_unlocked(session, cancellation)

    async def _cancel_unlocked(
        self,
        session: ResearchSession,
        cancellation: OperatorCancellation,
    ) -> AgenticSliceResult:
        """Apply cancellation inside one correlated lifecycle trace."""
        current_task = asyncio.current_task()
        active_task = self._active_tasks.get(session.session_id)
        if (
            active_task is not None
            and active_task is not current_task
            and not active_task.done()
        ):
            active_task.cancel()
            with suppress(asyncio.CancelledError):
                await active_task
        graph = self.coordinator.build_graph(
            session=session,
            checkpointer=self.checkpointer,
        )
        config = coordinator_thread_config(session.session_id)
        snapshot = await graph.aget_state(config)
        if not snapshot.values:
            raise ValueError("research session has no operational checkpoint")
        current = _outcome_if_available(session.session_id, snapshot.values)
        if isinstance(current, AgenticSliceResult):
            if current.status == "cancelled":
                return current
            raise ValueError("a terminal research session cannot be cancelled")
        updates = await self.coordinator.cancel_state(
            session=session,
            state=snapshot.values,
            cancellation=cancellation,
        )
        await graph.aupdate_state(config, updates, as_node="commit_decision")
        terminal_snapshot = await graph.aget_state(config)
        terminal = _outcome_if_available(
            session.session_id,
            terminal_snapshot.values,
        )
        if not isinstance(terminal, AgenticSliceResult):
            raise RuntimeError("cancellation did not produce a terminal result")
        self._emit_checkpoint(
            AgentEventName.CHECKPOINT_SAVED,
            terminal_snapshot.values,
        )
        return self._emit_outcome(session, terminal)

    async def inspect(self, session: ResearchSession) -> dict[str, Any]:
        """Return the redacted operator-visible checkpoint projection."""
        self._validate_session(session)
        with self._trace_operation(session, "inspect"):
            graph = self.coordinator.build_graph(
                session=session,
                checkpointer=self.checkpointer,
            )
            snapshot = await graph.aget_state(
                coordinator_thread_config(session.session_id)
            )
            if not snapshot.values:
                raise ValueError("research session has no operational checkpoint")
            public_state = agent_public_state(snapshot.values)
            self.event_emitter.emit(
                name=AgentEventName.SESSION_INSPECTED,
                correlation=self._event_correlation(session),
                role=AgentRole.RESEARCH_COORDINATOR.value,
                fields={
                    "status": str(public_state.get("status") or "unknown"),
                    "phase": str(public_state.get("phase") or "unknown"),
                    "next_sequence": int(public_state.get("next_sequence") or 1),
                },
            )
            return public_state

    def _validate_session(self, session: ResearchSession) -> None:
        """Validate all immutable runtime pins before touching checkpoints."""
        validate_runtime_pins(
            session,
            model_profiles=self.model_profiles,
            agent_programs=self.programs,
            tool_catalogue=self.tool_catalogue,
        )

    def _trace_operation(self, session: ResearchSession, operation: str) -> Any:
        """Return one root span joining a public lifecycle trajectory."""
        program = self.programs.for_role(AgentRole.RESEARCH_COORDINATOR)
        correlation = TraceCorrelation(
            session_id=session.session_id,
            branch_id=_root_branch_id(session.session_id),
            program_id=program.program_id,
            model_profile_id=session.model_profile_id,
            tool_catalog_id=self.tool_catalogue.catalogue_id,
        )
        return self.trace_sink.span(
            f"agent.session.{operation}",
            span_type="CHAIN",
            attributes=correlated_attributes(
                correlation,
                **{
                    "trader.lifecycle_operation": operation,
                    "trader.process_instance_id": _PROCESS_INSTANCE_ID,
                },
            ),
        )

    def _event_correlation(self, session: ResearchSession) -> TraceCorrelation:
        """Return the stable coordinator correlation for console events."""
        program = self.programs.for_role(AgentRole.RESEARCH_COORDINATOR)
        return TraceCorrelation(
            session_id=session.session_id,
            branch_id=_root_branch_id(session.session_id),
            program_id=program.program_id,
            model_profile_id=session.model_profile_id,
            tool_catalog_id=self.tool_catalogue.catalogue_id,
        )

    def _emit_checkpoint(
        self,
        name: AgentEventName,
        state: Mapping[str, Any],
    ) -> None:
        """Emit one coordinator checkpoint identity without its state payload."""
        checkpoint_state = {
            key: value
            for key, value in state.items()
            if key in AgentCheckpointState.__annotations__
        }
        session_id = str(checkpoint_state.get("session_id") or "")
        if not session_id:
            raise ValueError("checkpoint event requires session_id")
        sequence = _checkpoint_sequence(state)
        correlation = TraceCorrelation(
            session_id=session_id,
            branch_id=str(
                checkpoint_state.get("branch_id") or _root_branch_id(session_id)
            ),
            program_id=str(
                checkpoint_state.get("coordinator_program_id") or "unknown-program"
            ),
            model_profile_id=str(
                checkpoint_state.get("model_profile_id") or "unknown-profile"
            ),
            tool_catalog_id=str(
                checkpoint_state.get("tool_catalog_id") or "unknown-catalogue"
            ),
        )
        self.event_emitter.emit(
            name=name,
            correlation=correlation,
            role=AgentRole.RESEARCH_COORDINATOR.value,
            transition_sequence=sequence,
            fields=project_checkpoint(
                checkpoint_digest=agent_checkpoint_digest(checkpoint_state),
                transition_sequence=sequence,
                status=str(checkpoint_state.get("status") or "running"),
                phase=str(checkpoint_state.get("phase") or AgentPhase.INTERPRET.value),
            ),
        )

    @overload
    def _emit_outcome(
        self,
        session: ResearchSession,
        outcome: AgenticSliceResult,
    ) -> AgenticSliceResult: ...

    @overload
    def _emit_outcome(
        self,
        session: ResearchSession,
        outcome: OperatorInterrupt,
    ) -> OperatorInterrupt: ...

    def _emit_outcome(
        self,
        session: ResearchSession,
        outcome: AgentRunOutcome,
    ) -> AgentRunOutcome:
        """Emit the public result or operator interrupt returned by the runtime."""
        correlation = self._event_correlation(session)
        if isinstance(outcome, OperatorInterrupt):
            self.event_emitter.emit(
                name=AgentEventName.SESSION_INTERRUPTED,
                correlation=correlation,
                role=AgentRole.RESEARCH_COORDINATOR.value,
                fields={
                    "kind": outcome.kind,
                    "question": outcome.question,
                    "requested_action": outcome.requested_action,
                },
            )
            return outcome
        if outcome.status in {"failed", "blocked"}:
            self.event_emitter.emit(
                name=AgentEventName.SESSION_FAILED,
                correlation=correlation,
                role=AgentRole.RESEARCH_COORDINATOR.value,
                fields=project_terminal_result(outcome),
                error=AgentEventError(
                    code=(
                        "research_session_blocked"
                        if outcome.status == "blocked"
                        else "research_session_failed"
                    ),
                    category=(
                        AgentErrorCategory.DOMAIN_VALIDATION
                        if outcome.status == "blocked"
                        else AgentErrorCategory.INTERNAL
                    ),
                    message=(
                        "The research session reached a fail-closed blocker."
                        if outcome.status == "blocked"
                        else "The research session failed before a usable conclusion."
                    ),
                ),
            )
        elif outcome.status == "awaiting_operator":
            self.event_emitter.emit(
                name=AgentEventName.SESSION_INTERRUPTED,
                correlation=correlation,
                role=AgentRole.RESEARCH_COORDINATOR.value,
                fields=project_terminal_result(outcome),
            )
        else:
            name = (
                AgentEventName.SESSION_CANCELLED
                if outcome.status == "cancelled"
                else AgentEventName.SESSION_COMPLETED
            )
            self.event_emitter.emit(
                name=name,
                correlation=correlation,
                role=AgentRole.RESEARCH_COORDINATOR.value,
                fields=project_terminal_result(outcome),
            )
        return outcome

    @asynccontextmanager
    async def _active_session(
        self,
        session_id: str,
    ) -> AsyncIterator[None]:
        """Enforce one in-process writer task for a research session."""
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("agent runtime requires an active asyncio task")
        existing = self._active_tasks.get(session_id)
        if existing is not None and existing is not task and not existing.done():
            raise RuntimeError("research session already has an active runtime task")
        self._active_tasks[session_id] = task
        try:
            yield
        finally:
            if self._active_tasks.get(session_id) is task:
                self._active_tasks.pop(session_id, None)


@asynccontextmanager
async def runtime_from_environment(
    environ: Mapping[str, str] | None = None,
    *,
    setup_checkpoint_schema: bool = False,
    mcp_client_decorator: McpClientDecorator | None = None,
    console_config: AgentConsoleConfig | None = None,
) -> AsyncIterator[AgenticResearchRuntime]:
    """Open the production model, MCP, trace, and Postgres runtime.

    Three MCP stdio sessions isolate coordinator, Data, and Strategy transport
    state. All use the same server configuration but separate client sessions.

    Args:
        environ: Environment overrides; defaults to the process environment.
        setup_checkpoint_schema: Whether to run idempotent LangGraph checkpoint
            schema setup. Use true during initial environment setup.
        mcp_client_decorator: Optional trusted composition boundary applied to
            each role-labelled client after its persistent transport opens.
            Normal production callers omit it; controlled recovery tests may
            use it to inject a process-ending transport fault.
        console_config: Optional already-validated console override. Normal CLI
            composition supplies this after applying command-line precedence.

    Yields:
        Ready user-facing runtime. Closing the context stops MCP subprocesses
        and releases the Postgres checkpointer connection.
    """
    values = dict(os.environ)
    if environ is not None:
        values.update(environ)
    resolved_console_config = console_config or agent_console_config(values)
    values["TRADER_MCP_LOG_LEVEL"] = resolved_console_config.level.value
    values["TRADER_MCP_LOG_FORMAT"] = resolved_console_config.format.value
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    profiles = development_model_profiles()
    profile_id = values.get(
        "TRADER_AGENTS_MODEL_PROFILE_ID",
        DEVELOPMENT_MODEL_PROFILE_ID,
    )
    profile = profiles.get(profile_id)
    model_env = {**values, **profile_environment(profile)}
    llm_client = RuntimeConfiguredLlmClient(env=model_env)
    trace_sink = _trace_sink(values)
    event_emitter = AgentEventEmitter(
        sink=ConsoleObservabilityEventSink(config=resolved_console_config),
        process_instance_id=_PROCESS_INSTANCE_ID,
    )
    server_command = values.get("TRADER_AGENTS_MCP_COMMAND", sys.executable)
    server_args = tuple(
        shlex.split(
            values.get(
                "TRADER_AGENTS_MCP_ARGS",
                "-m trader_mcp.runtime.server",
            )
        )
    )
    server_cwd = Path(values.get("TRADER_AGENTS_MCP_CWD", str(Path.cwd()))).resolve()
    read_timeout = int(values.get("TRADER_AGENTS_MCP_TIMEOUT_SECONDS", "180"))

    async with AsyncExitStack() as stack:
        coordinator_transport = await stack.enter_async_context(
            _mcp_client(
                role=AgentRole.RESEARCH_COORDINATOR,
                command=server_command,
                args=server_args,
                cwd=server_cwd,
                environ=values,
                timeout_seconds=read_timeout,
            )
        )
        data_transport = await stack.enter_async_context(
            _mcp_client(
                role=AgentRole.DATA_RESEARCH,
                command=server_command,
                args=server_args,
                cwd=server_cwd,
                environ=values,
                timeout_seconds=read_timeout,
            )
        )
        strategy_transport = await stack.enter_async_context(
            _mcp_client(
                role=AgentRole.STRATEGY_ENGINEERING,
                command=server_command,
                args=server_args,
                cwd=server_cwd,
                environ=values,
                timeout_seconds=read_timeout,
            )
        )
        coordinator_client: McpToolClient = coordinator_transport
        data_client: McpToolClient = data_transport
        strategy_client: McpToolClient = strategy_transport
        if mcp_client_decorator is not None:
            coordinator_client = mcp_client_decorator(
                AgentRole.RESEARCH_COORDINATOR,
                coordinator_transport,
            )
            data_client = mcp_client_decorator(
                AgentRole.DATA_RESEARCH,
                data_transport,
            )
            strategy_client = mcp_client_decorator(
                AgentRole.STRATEGY_ENGINEERING,
                strategy_transport,
            )
        checkpointer = await stack.enter_async_context(
            open_postgres_checkpointer(
                environ=values,
                setup=setup_checkpoint_schema,
            )
        )
        coordinator = ResearchCoordinator(
            model_runner=StructuredModelRunner(
                llm_client,
                trace_sink=trace_sink,
                event_emitter=event_emitter,
            ),
            mcp_client=coordinator_client,
            data_agent=DataResearchAgent(
                model_runner=StructuredModelRunner(
                    llm_client,
                    trace_sink=trace_sink,
                    event_emitter=event_emitter,
                ),
                mcp_client=data_client,
                tool_catalogue=catalogue,
                trace_sink=trace_sink,
                event_emitter=event_emitter,
            ),
            strategy_agent=StrategyEngineeringAgent(
                model_runner=StructuredModelRunner(
                    llm_client,
                    trace_sink=trace_sink,
                    event_emitter=event_emitter,
                ),
                mcp_client=strategy_client,
                tool_catalogue=catalogue,
                trace_sink=trace_sink,
                event_emitter=event_emitter,
            ),
            tool_catalogue=catalogue,
            programs=programs,
            model_profiles=profiles,
            trace_sink=trace_sink,
            event_emitter=event_emitter,
        )
        yield AgenticResearchRuntime(
            coordinator=coordinator,
            checkpointer=checkpointer,
            tool_catalogue=catalogue,
            programs=programs,
            model_profiles=profiles,
            trace_sink=trace_sink,
            event_emitter=event_emitter,
        )


def runtime_manifest() -> dict[str, Any]:
    """Return exact credential-free program, model, and tool identities."""
    catalogue = first_slice_tool_catalogue()
    return {
        "model_profiles": development_model_profiles().public_manifest(),
        "agent_programs": first_slice_programs().public_manifest(),
        "tool_catalogue": {
            "catalogue_id": catalogue.catalogue_id,
            **catalogue.public_manifest(),
        },
    }


def _mcp_client(
    *,
    role: AgentRole,
    command: str,
    args: tuple[str, ...],
    cwd: Path,
    environ: Mapping[str, str],
    timeout_seconds: int,
) -> PersistentStdioMcpToolClient:
    """Build one isolated persistent MCP transport client."""
    client_environment = dict(environ)
    client_environment["TRADER_MCP_SERVER_ROLE"] = role.value
    return PersistentStdioMcpToolClient(
        command=command,
        args=args,
        cwd=cwd,
        env=client_environment,
        read_timeout_seconds=timeout_seconds,
    )


def _outcome(
    session_id: str,
    output: Mapping[str, Any],
) -> AgentRunOutcome:
    """Normalize raw LangGraph output into one strict public result."""
    outcome = _outcome_if_available(session_id, output)
    if outcome is not None:
        return outcome
    raise RuntimeError("agent graph returned neither terminal result nor interrupt")


def _outcome_if_available(
    session_id: str,
    state: Mapping[str, Any],
) -> AgentRunOutcome | None:
    """Return a strict public result when state is terminal or interrupted."""
    terminal = state.get("terminal_result")
    if isinstance(terminal, Mapping) and terminal:
        return AgenticSliceResult.model_validate(terminal)
    pending = state.get("pending_interrupt")
    if isinstance(pending, Mapping) and pending:
        resume_schema = pending.get("resume_schema")
        return OperatorInterrupt(
            session_id=session_id,
            kind=str(pending.get("kind") or ""),
            question=str(pending.get("question") or ""),
            requested_action=str(pending.get("requested_action") or ""),
            resume_schema=(
                dict(resume_schema) if isinstance(resume_schema, Mapping) else {}
            ),
        )
    return None


def _trace_sink(environ: Mapping[str, str]) -> TraceSink:
    """Build optional MLflow tracing only from explicit configuration."""
    tracking_uri = str(environ.get("TRADER_AGENTS_MLFLOW_TRACKING_URI") or "").strip()
    if not tracking_uri:
        return NoOpTraceSink()
    experiment = str(
        environ.get("TRADER_AGENTS_MLFLOW_EXPERIMENT") or "trader-agentic-research"
    ).strip()
    return MlflowTraceSink(
        tracking_uri=tracking_uri,
        experiment_name=experiment,
    )


def _root_branch_id(session_id: str) -> str:
    """Return the deterministic coordinator root-branch identity."""
    return stable_research_id(
        "agent_root_branch",
        {"session_id": session_id},
    )


def _checkpoint_sequence(state: Mapping[str, Any]) -> int:
    """Return the positive coordinator transition represented by a checkpoint."""
    value = state.get("next_sequence", 1)
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else 1
    )
