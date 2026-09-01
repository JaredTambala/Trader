"""User-facing runtime lifecycle for first-slice agentic research sessions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass, field
import os
from pathlib import Path
import shlex
import sys
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from trader_research.foundation import stable_research_id
from trader_research.governance import ResearchSession

from .catalogue import ToolCatalogue, first_slice_tool_catalogue
from .checkpointing import (
    agent_public_state,
    build_agent_checkpoint_state,
    coordinator_thread_config,
    open_postgres_checkpointer,
)
from .contracts import (
    AgentRole,
    AgenticSliceResult,
    OperatorCancellation,
    OperatorInterrupt,
    OperatorResponse,
)
from .coordinator import ResearchCoordinator
from .data_research import DataResearchAgent
from .inputs import validate_runtime_pins
from .llm_client import RuntimeConfiguredLlmClient
from .profiles import (
    AgentProgramRegistry,
    ModelProfileRegistry,
    development_model_profiles,
    profile_environment,
)
from .programs import first_slice_programs
from .strategy_engineering import StrategyEngineeringAgent
from .structured_model import StructuredModelRunner
from .tool_client import PersistentStdioMcpToolClient
from .tracing import MlflowTraceSink, NoOpTraceSink, TraceSink


AgentRunOutcome = AgenticSliceResult | OperatorInterrupt
"""Public result of starting or resuming an agentic research session."""


@dataclass
class AgenticResearchRuntime:
    """Start, resume, and inspect one checkpoint-backed coordinator system.

    Attributes:
        coordinator: Fully wired coordinator and specialist system.
        checkpointer: Dedicated operational LangGraph checkpoint backend.
        tool_catalogue: Exact code-owned MCP catalogue.
        programs: Exact versioned agent programs.
        model_profiles: Exact admitted model profiles.
    """

    coordinator: ResearchCoordinator
    checkpointer: BaseCheckpointSaver[Any]
    tool_catalogue: ToolCatalogue
    programs: AgentProgramRegistry
    model_profiles: ModelProfileRegistry
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
            current = _outcome_if_available(session.session_id, snapshot.values)
            if current is not None:
                return current
            output = await graph.ainvoke(None, config)
            return _outcome(session.session_id, output)
        coordinator_program = self.programs.for_role(
            AgentRole.RESEARCH_COORDINATOR
        )
        initial = build_agent_checkpoint_state(
            session_id=session.session_id,
            session_digest=session.session_digest,
            branch_id=stable_research_id(
                "agent_root_branch",
                {"session_id": session.session_id},
            ),
            coordinator_program_id=coordinator_program.program_id,
            model_profile_id=session.model_profile_id,
            tool_catalog_id=self.tool_catalogue.catalogue_id,
        )
        output = await graph.ainvoke(initial, config)
        return _outcome(session.session_id, output)

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
        current = _outcome_if_available(session.session_id, snapshot.values)
        if current is not None:
            return current
        if not snapshot.interrupts:
            raise ValueError("research session is not awaiting operator input")
        output = await graph.ainvoke(
            Command(resume=response.model_dump(mode="json")),
            config,
        )
        return _outcome(session.session_id, output)

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
        return terminal

    async def inspect(self, session: ResearchSession) -> dict[str, Any]:
        """Return the redacted operator-visible checkpoint projection."""
        self._validate_session(session)
        graph = self.coordinator.build_graph(
            session=session,
            checkpointer=self.checkpointer,
        )
        snapshot = await graph.aget_state(
            coordinator_thread_config(session.session_id)
        )
        if not snapshot.values:
            raise ValueError("research session has no operational checkpoint")
        return agent_public_state(snapshot.values)

    def _validate_session(self, session: ResearchSession) -> None:
        """Validate all immutable runtime pins before touching checkpoints."""
        validate_runtime_pins(
            session,
            model_profiles=self.model_profiles,
            agent_programs=self.programs,
            tool_catalogue=self.tool_catalogue,
        )

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
) -> AsyncIterator[AgenticResearchRuntime]:
    """Open the production model, MCP, trace, and Postgres runtime.

    Three MCP stdio sessions isolate coordinator, Data, and Strategy transport
    state. All use the same server configuration but separate client sessions.

    Args:
        environ: Environment overrides; defaults to the process environment.
        setup_checkpoint_schema: Whether to run idempotent LangGraph checkpoint
            schema setup. Use true during initial environment setup.

    Yields:
        Ready user-facing runtime. Closing the context stops MCP subprocesses
        and releases the Postgres checkpointer connection.
    """
    values = dict(os.environ)
    if environ is not None:
        values.update(environ)
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    profiles = development_model_profiles()
    profile_id = values.get(
        "TRADER_AGENTS_MODEL_PROFILE_ID",
        "ollama-qwen35-9b-json-v1",
    )
    profile = profiles.get(profile_id)
    model_env = {**values, **profile_environment(profile)}
    llm_client = RuntimeConfiguredLlmClient(env=model_env)
    trace_sink = _trace_sink(values)
    server_command = values.get("TRADER_AGENTS_MCP_COMMAND", sys.executable)
    server_args = tuple(
        shlex.split(
            values.get(
                "TRADER_AGENTS_MCP_ARGS",
                "-m trader_mcp.server",
            )
        )
    )
    server_cwd = Path(
        values.get("TRADER_AGENTS_MCP_CWD", str(Path.cwd()))
    ).resolve()
    read_timeout = int(values.get("TRADER_AGENTS_MCP_TIMEOUT_SECONDS", "180"))

    async with AsyncExitStack() as stack:
        coordinator_client = await stack.enter_async_context(
            _mcp_client(
                command=server_command,
                args=server_args,
                cwd=server_cwd,
                environ=values,
                timeout_seconds=read_timeout,
            )
        )
        data_client = await stack.enter_async_context(
            _mcp_client(
                command=server_command,
                args=server_args,
                cwd=server_cwd,
                environ=values,
                timeout_seconds=read_timeout,
            )
        )
        strategy_client = await stack.enter_async_context(
            _mcp_client(
                command=server_command,
                args=server_args,
                cwd=server_cwd,
                environ=values,
                timeout_seconds=read_timeout,
            )
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
            ),
            mcp_client=coordinator_client,
            data_agent=DataResearchAgent(
                model_runner=StructuredModelRunner(
                    llm_client,
                    trace_sink=trace_sink,
                ),
                mcp_client=data_client,
                tool_catalogue=catalogue,
                trace_sink=trace_sink,
            ),
            strategy_agent=StrategyEngineeringAgent(
                model_runner=StructuredModelRunner(
                    llm_client,
                    trace_sink=trace_sink,
                ),
                mcp_client=strategy_client,
                tool_catalogue=catalogue,
                trace_sink=trace_sink,
            ),
            tool_catalogue=catalogue,
            programs=programs,
            model_profiles=profiles,
            trace_sink=trace_sink,
        )
        yield AgenticResearchRuntime(
            coordinator=coordinator,
            checkpointer=checkpointer,
            tool_catalogue=catalogue,
            programs=programs,
            model_profiles=profiles,
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
    command: str,
    args: tuple[str, ...],
    cwd: Path,
    environ: Mapping[str, str],
    timeout_seconds: int,
) -> PersistentStdioMcpToolClient:
    """Build one isolated persistent MCP transport client."""
    return PersistentStdioMcpToolClient(
        command=command,
        args=args,
        cwd=cwd,
        env=environ,
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
    tracking_uri = str(
        environ.get("TRADER_AGENTS_MLFLOW_TRACKING_URI") or ""
    ).strip()
    if not tracking_uri:
        return NoOpTraceSink()
    experiment = str(
        environ.get("TRADER_AGENTS_MLFLOW_EXPERIMENT")
        or "trader-agentic-research"
    ).strip()
    return MlflowTraceSink(
        tracking_uri=tracking_uri,
        experiment_name=experiment,
    )
