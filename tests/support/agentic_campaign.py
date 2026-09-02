"""No-cherry-picking runner for repeated real-model agentic qualification."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Protocol

from trader_research.governance import ResearchSession

from tests.support.agentic_assessment import assess_agentic_scenario
from tests.support.agentic_faults import (
    AFTER_DATA_MUTATION,
    BEFORE_DATA_MUTATION,
    BEFORE_RETURN_RECONCILIATION,
    NO_FAULT,
)
from tests.support.agentic_observation import (
    LifecycleTrace,
    ScenarioTrajectoryEvidence,
    build_agentic_scenario_result,
    load_mlflow_lifecycle_traces,
    mutation_trace_identity,
    trajectory_evidence_refs,
)
from tests.support.agentic_qualification import (
    AgenticScenarioResult,
    load_agentic_evaluation_contract,
)
from tests.support.agentic_scenarios import (
    AgenticScenarioInput,
    build_agentic_scenario_sessions,
    load_agentic_scenario_inputs,
)
from tests.support.agentic_session_worker import (
    FAULT_EXIT_CODE,
    FAULT_RESULT_PREFIX,
    STATE_RESULT_PREFIX,
)
from trader_agents.runtime import runtime_from_environment


_RECOVERY_FAULT_PROFILE = "before_mutation_after_acceptance_and_return_reconciliation"
_SESSION_WORKER_MODULE = "tests.support.agentic_session_worker"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ScenarioFixtureController(Protocol):
    """Provision and independently inspect one deterministic scenario fixture."""

    async def prepare(
        self,
        scenario: AgenticScenarioInput,
        sessions: Sequence[ResearchSession],
        base_environment: Mapping[str, str],
    ) -> Mapping[str, str]:
        """Prepare exact external state and return runtime environment overrides."""

    async def resolve_evidence_refs(
        self,
        references: frozenset[str],
    ) -> frozenset[str]:
        """Resolve canonical refs independently of agent model output."""

    async def mutation_acceptance_counts(
        self,
        traces: Sequence[LifecycleTrace],
    ) -> Mapping[str, int]:
        """Return accepted provider mutation counts by exact call identity."""


class SessionExecutor(Protocol):
    """Execute one concrete session and return its redacted final checkpoint."""

    def __call__(
        self,
        session: ResearchSession,
        environment: Mapping[str, str],
        setup_checkpoint_schema: bool,
    ) -> Awaitable[Mapping[str, object]]:
        """Run one exact session without changing its immutable identity."""


TraceLoader = Callable[
    [str, str, Sequence[str]],
    tuple[LifecycleTrace, ...],
]
ResultSink = Callable[[AgenticScenarioResult], None]


@dataclass
class AgenticCampaignRunner:
    """Execute the complete frozen campaign in deterministic fixture order.

    Attributes:
        freeze_revision: Exact product Git revision under qualification.
        base_environment: Explicit controlled runtime configuration.
        fixture_controller: External-state provisioner and evidence verifier.
        session_executor: Runtime lifecycle executor, injectable for contract tests.
        trace_loader: MLflow public-trace loader, injectable for contract tests.
        result_sink: Optional immediate durable result writer.
        execution_namespace: Code-owned phase lane isolating mutable fixtures.
    """

    freeze_revision: str
    base_environment: Mapping[str, str]
    fixture_controller: ScenarioFixtureController
    session_executor: SessionExecutor = field(
        default=lambda session, environment, setup: _execute_production_session(
            session,
            environment,
            setup,
        )
    )
    trace_loader: TraceLoader = field(
        default=lambda uri, experiment, ids: load_mlflow_lifecycle_traces(
            tracking_uri=uri,
            experiment_name=experiment,
            session_ids=ids,
        )
    )
    result_sink: ResultSink | None = None
    execution_namespace: str = "campaign"
    _checkpoint_schema_initialized: bool = field(
        default=False,
        init=False,
        repr=False,
    )

    async def run_all(self) -> tuple[AgenticScenarioResult, ...]:
        """Run all scenario repetitions in charter order without selection.

        Returns:
            Every immediately assessed result in deterministic execution order.
        """
        contract = load_agentic_evaluation_contract()
        repetitions = int(
            contract["provisional_promotion_thresholds"]["repetitions_per_scenario"]
        )
        results = []
        for scenario in contract["scenarios"]:
            scenario_id = str(scenario["scenario_id"])
            for repetition in range(1, repetitions + 1):
                result = await self.run_repetition(scenario_id, repetition)
                if self.result_sink is not None:
                    self.result_sink(result)
                results.append(result)
        return tuple(results)

    async def run_repetition(
        self,
        scenario_id: str,
        repetition: int,
    ) -> AgenticScenarioResult:
        """Run and assess every concrete variant of one scenario repetition."""
        scenarios = load_agentic_scenario_inputs()
        try:
            scenario = scenarios[scenario_id]
        except KeyError as exc:
            raise ValueError(f"unknown agentic scenario: {scenario_id}") from exc
        sessions = build_agentic_scenario_sessions(
            scenario_id,
            repetition=repetition,
            freeze_revision=self.freeze_revision,
            execution_namespace=self.execution_namespace,
        )
        environment = dict(
            await self.fixture_controller.prepare(
                scenario,
                sessions,
                self.base_environment,
            )
        )
        tracking_uri = _required_environment(
            environment,
            "TRADER_AGENTS_MLFLOW_TRACKING_URI",
        )
        experiment = _required_environment(
            environment,
            "TRADER_AGENTS_MLFLOW_EXPERIMENT",
        )
        states = []
        for session in sessions:
            state = await self.session_executor(
                session,
                environment,
                not self._checkpoint_schema_initialized,
            )
            self._checkpoint_schema_initialized = True
            states.append(state)
        traces = self.trace_loader(
            tracking_uri,
            experiment,
            [session.session_id for session in sessions],
        )
        draft = ScenarioTrajectoryEvidence(
            scenario_id=scenario_id,
            repetition=repetition,
            sessions=sessions,
            public_states=tuple(states),
            traces=traces,
            resolved_evidence_refs=frozenset(),
            mutation_acceptance_counts={},
        )
        references = trajectory_evidence_refs(draft)
        resolved = await self.fixture_controller.resolve_evidence_refs(references)
        mutation_counts = await self.fixture_controller.mutation_acceptance_counts(
            traces
        )
        evidence = ScenarioTrajectoryEvidence(
            scenario_id=scenario_id,
            repetition=repetition,
            sessions=sessions,
            public_states=tuple(states),
            traces=traces,
            resolved_evidence_refs=resolved,
            mutation_acceptance_counts=mutation_counts,
        )
        return build_agentic_scenario_result(
            evidence,
            assess_agentic_scenario(evidence),
        )


async def _execute_production_session(
    session: ResearchSession,
    environment: Mapping[str, str],
    setup_checkpoint_schema: bool,
) -> Mapping[str, object]:
    """Run one production runtime lifecycle and inspect its public state."""
    scenario_id = str(session.metadata.get("qualification_scenario_id") or "").strip()
    scenario = load_agentic_scenario_inputs().get(scenario_id)
    if scenario is None:
        raise ValueError(f"unknown session qualification scenario: {scenario_id}")
    if scenario.environment.fault_profile == _RECOVERY_FAULT_PROFILE:
        return await _execute_recovery_session(
            session,
            environment,
            setup_checkpoint_schema=setup_checkpoint_schema,
        )
    if scenario.environment.fault_profile != NO_FAULT:
        raise ValueError(
            f"unsupported session fault profile: {scenario.environment.fault_profile}"
        )
    async with runtime_from_environment(
        environment,
        setup_checkpoint_schema=setup_checkpoint_schema,
    ) as runtime:
        await runtime.start(session)
        return await runtime.inspect(session)


async def _execute_recovery_session(
    session: ResearchSession,
    environment: Mapping[str, str],
    *,
    setup_checkpoint_schema: bool,
) -> Mapping[str, object]:
    """Recover one session across the three reviewed process fault boundaries.

    A separate process first stops before provider mutation, then after the
    provider accepted the same runtime-owned operation, and finally before the
    coordinator reconciles checkpointed specialist returns. A fourth clean
    process must finish from the same Postgres checkpoints.
    """
    return await execute_fresh_process_fault_sequence(
        session,
        environment,
        setup_checkpoint_schema,
        fault_modes=(
            BEFORE_DATA_MUTATION,
            AFTER_DATA_MUTATION,
            BEFORE_RETURN_RECONCILIATION,
        ),
    )


async def execute_fresh_process_fault_sequence(
    session: ResearchSession,
    environment: Mapping[str, str],
    setup_checkpoint_schema: bool,
    *,
    fault_modes: Sequence[str],
) -> Mapping[str, object]:
    """Recover one session across exact process-level MCP fault boundaries.

    Args:
        session: Immutable research session resumed by every fresh worker.
        environment: Complete controlled runtime environment.
        setup_checkpoint_schema: Whether the first worker owns schema setup.
        fault_modes: Ordered reviewed boundaries, each run in a new process.

    Returns:
        Final redacted public state from a clean completion process.

    Raises:
        RuntimeError: If a worker misses its fault or clean completion fails.
    """
    if not fault_modes:
        raise ValueError("fresh-process recovery requires at least one fault mode")
    timeout_seconds = max(
        60,
        min(session.budget.max_duration_seconds + 120, 1_800),
    )
    for index, fault_mode in enumerate(fault_modes):
        outcome = await _run_session_worker(
            session,
            environment,
            fault_mode=fault_mode,
            setup_checkpoint_schema=setup_checkpoint_schema and index == 0,
            timeout_seconds=timeout_seconds,
        )
        _require_expected_fault(outcome, fault_mode)
    final = await _run_session_worker(
        session,
        environment,
        fault_mode=NO_FAULT,
        setup_checkpoint_schema=False,
        timeout_seconds=timeout_seconds,
    )
    if final.returncode != 0:
        raise RuntimeError(_worker_failure("recovery completion", final))
    state = _worker_marker(final.stdout, STATE_RESULT_PREFIX)
    if str(state.get("session_id") or "") != session.session_id:
        raise RuntimeError("recovery worker returned another session's state")
    return state


async def execute_fresh_process_cancellation(
    session: ResearchSession,
    environment: Mapping[str, str],
    setup_checkpoint_schema: bool,
    *,
    fault_mode: str,
) -> Mapping[str, object]:
    """Interrupt a running session, cancel it elsewhere, and replay terminal state.

    Args:
        session: Immutable research session used by every worker.
        environment: Complete controlled runtime environment.
        setup_checkpoint_schema: Whether the initial worker owns schema setup.
        fault_mode: Reviewed boundary that leaves the initial run incomplete.

    Returns:
        Redacted terminal state read by a third clean process.

    Raises:
        RuntimeError: If fault, cancellation, or terminal replay fails.
    """
    timeout_seconds = max(
        60,
        min(session.budget.max_duration_seconds + 120, 1_800),
    )
    interrupted = await _run_session_worker(
        session,
        environment,
        fault_mode=fault_mode,
        setup_checkpoint_schema=setup_checkpoint_schema,
        timeout_seconds=timeout_seconds,
    )
    _require_expected_fault(interrupted, fault_mode)
    cancelled = await _run_session_worker(
        session,
        environment,
        fault_mode=NO_FAULT,
        setup_checkpoint_schema=False,
        timeout_seconds=timeout_seconds,
        action="cancel",
    )
    if cancelled.returncode != 0:
        raise RuntimeError(_worker_failure("fresh-process cancellation", cancelled))
    cancelled_state = _worker_marker(cancelled.stdout, STATE_RESULT_PREFIX)
    if cancelled_state.get("status") != "cancelled":
        raise RuntimeError("fresh-process cancellation was not terminal")
    replayed = await _run_session_worker(
        session,
        environment,
        fault_mode=NO_FAULT,
        setup_checkpoint_schema=False,
        timeout_seconds=timeout_seconds,
    )
    if replayed.returncode != 0:
        raise RuntimeError(_worker_failure("cancelled terminal replay", replayed))
    replayed_state = _worker_marker(replayed.stdout, STATE_RESULT_PREFIX)
    if replayed_state != cancelled_state:
        raise RuntimeError(
            "cancelled terminal state changed during fresh-process replay"
        )
    return replayed_state


@dataclass(frozen=True)
class _WorkerOutcome:
    """Bounded completed subprocess result for one lifecycle attempt."""

    returncode: int
    stdout: str
    stderr: str


async def _run_session_worker(
    session: ResearchSession,
    environment: Mapping[str, str],
    *,
    fault_mode: str,
    setup_checkpoint_schema: bool,
    timeout_seconds: int,
    action: str = "start",
) -> _WorkerOutcome:
    """Execute one isolated lifecycle worker with the controlled environment."""
    command = [
        sys.executable,
        "-m",
        _SESSION_WORKER_MODULE,
        "--fault-mode",
        fault_mode,
        "--action",
        action,
    ]
    if setup_checkpoint_schema:
        command.append("--setup-checkpoint-schema")
    worker_environment = dict(os.environ)
    worker_environment.update(
        {str(key): str(value) for key, value in environment.items()}
    )
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=_REPOSITORY_ROOT,
        env=worker_environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    request = json.dumps(
        {"session": session.to_dict()},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(request),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise RuntimeError(
            f"agentic session worker exceeded {timeout_seconds} seconds"
        ) from exc
    return _WorkerOutcome(
        returncode=int(process.returncode or 0),
        stdout=stdout_bytes.decode("utf-8", errors="replace")[-100_000:],
        stderr=stderr_bytes.decode("utf-8", errors="replace")[-100_000:],
    )


def _require_expected_fault(outcome: _WorkerOutcome, fault_mode: str) -> None:
    """Require one worker to stop only at its selected fault boundary."""
    if outcome.returncode != FAULT_EXIT_CODE:
        raise RuntimeError(_worker_failure(fault_mode, outcome))
    marker = _worker_marker(outcome.stdout, FAULT_RESULT_PREFIX)
    if marker.get("mode") != fault_mode:
        raise RuntimeError(
            f"recovery worker reported {marker.get('mode')!r}, expected {fault_mode!r}"
        )


def _worker_marker(output: str, prefix: str) -> dict[str, object]:
    """Parse exactly one bounded JSON worker marker from mixed process output."""
    values = [
        line.removeprefix(prefix)
        for line in output.splitlines()
        if line.startswith(prefix)
    ]
    if len(values) != 1:
        raise RuntimeError(f"worker output requires exactly one {prefix} marker")
    try:
        payload = json.loads(values[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError("worker marker is not valid JSON") from exc
    if not isinstance(payload, dict) or any(
        not isinstance(key, str) for key in payload
    ):
        raise RuntimeError("worker marker must be a JSON object")
    return payload


def _worker_failure(label: str, outcome: _WorkerOutcome) -> str:
    """Build a bounded source-free worker failure diagnostic."""
    return (
        f"agentic worker did not reach {label}; exit={outcome.returncode}; "
        f"stdout={_stream_fingerprint(outcome.stdout)}; "
        f"stderr={_stream_fingerprint(outcome.stderr)}"
    )


def _stream_fingerprint(value: str) -> str:
    """Return byte length and digest without reproducing process output."""
    encoded = value.encode("utf-8")
    return f"bytes:{len(encoded)},sha256:{sha256(encoded).hexdigest()}"


def successful_mutation_counts_from_traces(
    traces: Sequence[LifecycleTrace],
) -> dict[str, int]:
    """Count successful traced mutations when no deeper journal is required.

    This helper is suitable only for immutable control receipts whose MCP
    result itself is the accepted canonical identity. Provider-backed Data and
    Coding mutations must be replaced by operation-journal inspection in the
    controlled fixture controller.
    """
    successful_results = Counter(
        mutation_trace_identity(span)
        for trace in traces
        for span in trace.spans
        if span.name.startswith("agent.mcp_result.")
        and span.attributes.get("trader.result_ok") is True
    )
    counts: dict[str, int] = {}
    for call in (
        span
        for trace in traces
        for span in trace.spans
        if span.name.startswith("agent.mcp.")
        and not span.name.startswith("agent.mcp_result.")
        and span.attributes.get("trader.side_effect") != "read_only"
    ):
        identity = mutation_trace_identity(call)
        counts[identity] = successful_results[identity]
    return counts


def _required_environment(environment: Mapping[str, str], name: str) -> str:
    """Return one required non-empty controlled environment value."""
    value = str(environment.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required for the agentic campaign")
    return value
