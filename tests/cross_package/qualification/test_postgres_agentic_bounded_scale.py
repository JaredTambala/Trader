"""Controlled bounded-scale qualification for the first agentic slice.

Subject: Resource, storage, concurrency, and timing ceilings across production-shaped Agent profiles.
Level: Cross-package controlled qualification.
Collaborators: Real local model, MCP, MLflow traces, guarded Postgres, and fresh processes.
Guarantees: Composite, joined, recovered, and concurrent sessions stay within declared ceilings.
Non-goals: Load testing beyond bounded profiles, capacity planning, or live trading.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
import os
import time
from typing import Any

import anyio
import psycopg
from psycopg.rows import dict_row
import pytest

from tests.trader_agents.application_runtime.support.agentic_campaign import AgenticCampaignRunner
from tests.trader_agents.application_runtime.support.agentic_fixture import GuardedPostgresAgenticFixtureController
from tests.trader_agents.observability.support.agentic_observation import load_mlflow_lifecycle_traces
from tests.trader_agents.application_runtime.support.agentic_qualification import AgenticScenarioResult
from tests.trader_agents.application_runtime.support.agentic_scale import (
    AGENTIC_SCALE_PROFILES,
    build_agentic_scale_result,
    load_agentic_scale_results,
    measure_agentic_storage,
    save_agentic_scale_result,
)
from tests.trader_agents.contracts_state.support.agentic_scenarios import build_agentic_scenario_sessions
from tests.cross_package.qualification.support.postgres_verification import (
    AGENTIC_VERIFICATION_PROFILE,
    DEFAULT_CHECKPOINT_SCHEMA,
    RETAIN_EVIDENCE_PHASE_ENV,
    VERIFICATION_PROFILE_ENV,
    load_qualification_profile,
    load_retained_evidence_phase,
    load_test_settings,
    resolve_freeze_revision,
)


pytestmark = pytest.mark.postgres
_PHASE = "AGENTIC_BOUNDED_SCALE"
_PROFILE_CEILINGS: Mapping[str, Mapping[str, int | float]] = {
    "single_composite_session": {
        "session_count": 1,
        "model_calls": 40,
        "tool_calls": 40,
        "total_tokens": 120_000,
        "duration_seconds": 600,
        "revisions": 2,
        "peak_concurrency": 2,
        "trace_count": 4,
        "span_count": 256,
        "wall_seconds": 600,
    },
    "parallel_specialist_join": {
        "session_count": 1,
        "model_calls": 40,
        "tool_calls": 40,
        "total_tokens": 120_000,
        "duration_seconds": 600,
        "revisions": 2,
        "peak_concurrency": 2,
        "trace_count": 4,
        "span_count": 256,
        "wall_seconds": 600,
    },
    "fresh_process_recovery": {
        "session_count": 1,
        "model_calls": 40,
        "tool_calls": 40,
        "total_tokens": 120_000,
        "duration_seconds": 600,
        "revisions": 2,
        "peak_concurrency": 2,
        "trace_count": 8,
        "span_count": 512,
        "wall_seconds": 1_800,
    },
    "concurrent_multi_session": {
        "session_count": 2,
        "model_calls": 80,
        "tool_calls": 80,
        "total_tokens": 240_000,
        "duration_seconds": 1_200,
        "revisions": 4,
        "peak_concurrency": 2,
        "trace_count": 8,
        "span_count": 512,
        "wall_seconds": 900,
    },
}


def test_agentic_runtime_stays_within_all_bounded_scale_profiles() -> None:
    """Measure composite, joined, recovery, and concurrent real-model paths."""
    profile = load_qualification_profile()
    if profile.name != AGENTIC_VERIFICATION_PROFILE:
        pytest.skip(f"set {VERIFICATION_PROFILE_ENV}={AGENTIC_VERIFICATION_PROFILE}")
    if load_retained_evidence_phase() != _PHASE:
        raise RuntimeError(f"{RETAIN_EVIDENCE_PHASE_ENV} must be {_PHASE}")
    freeze_revision = resolve_freeze_revision(profile)
    settings = load_test_settings(required=True)
    if settings is None:  # pragma: no cover - required=True raises first
        raise RuntimeError("PG_TEST settings are required")
    environment = dict(os.environ)

    executions = anyio.run(
        _run_profiles,
        freeze_revision,
        environment,
    )
    with psycopg.connect(
        settings.conninfo(),
        autocommit=True,
        row_factory=dict_row,
    ) as connection:
        for execution in executions:
            storage = measure_agentic_storage(
                connection,
                checkpoint_schema=os.environ.get(
                    "TRADER_CHECKPOINT_SCHEMA",
                    DEFAULT_CHECKPOINT_SCHEMA,
                ),
            )
            result = build_agentic_scale_result(
                profile=execution["profile"],
                results=execution["results"],
                task_count=sum(
                    len(item.delegated_roles) for item in execution["results"]
                ),
                span_count=_span_count(
                    environment,
                    freeze_revision=freeze_revision,
                    namespace=execution["namespace"],
                    scenarios=execution["scenarios"],
                ),
                wall_seconds=execution["wall_seconds"],
                observed_peak_concurrency=execution["peak_concurrency"],
                ceilings=_PROFILE_CEILINGS[execution["profile"]],
                **storage,
            )
            save_agentic_scale_result(
                connection,
                qualification_profile=profile.name,
                freeze_revision=freeze_revision,
                result=result,
            )
            assert result.status == "passed", result.payload["breached_ceilings"]

        reloaded = load_agentic_scale_results(
            connection,
            qualification_profile=profile.name,
            freeze_revision=freeze_revision,
        )

    assert {result.profile for result in reloaded} == AGENTIC_SCALE_PROFILES
    assert all(result.status == "passed" for result in reloaded)
    assert all(result.checkpoint_bytes > 0 for result in reloaded)
    assert all(result.database_bytes > 0 for result in reloaded)
    by_profile = {result.profile: result for result in reloaded}
    assert by_profile["parallel_specialist_join"].payload["peak_concurrency"] == 2
    assert by_profile["fresh_process_recovery"].payload["trace_count"] >= 4
    assert by_profile["concurrent_multi_session"].payload["session_count"] == 2
    assert by_profile["concurrent_multi_session"].payload["peak_concurrency"] == 2


async def _run_profiles(
    freeze_revision: str,
    environment: Mapping[str, str],
) -> tuple[Mapping[str, Any], ...]:
    """Execute the four code-owned profiles and retain host measurements."""
    serial = _runner(
        freeze_revision,
        environment,
        namespace="bounded_scale_serial",
    )
    parallel = _runner(
        freeze_revision,
        environment,
        namespace="bounded_scale_parallel",
    )
    recovery = _runner(
        freeze_revision,
        environment,
        namespace="bounded_scale_recovery",
    )
    executions = [
        await _timed_profile(
            "single_composite_session",
            serial,
            ("bounded_backfill_and_adaptation",),
        ),
        await _timed_profile(
            "parallel_specialist_join",
            parallel,
            ("exact_reuse",),
        ),
        await _timed_profile(
            "fresh_process_recovery",
            recovery,
            ("crash_and_lost_response",),
        ),
    ]
    executions.append(
        await _timed_profile(
            "concurrent_multi_session",
            parallel,
            ("new_authorship_and_repair", "out_of_envelope_acquisition"),
            concurrent=True,
        )
    )
    return tuple(executions)


def _runner(
    freeze_revision: str,
    environment: Mapping[str, str],
    *,
    namespace: str,
) -> AgenticCampaignRunner:
    """Build one production-MCP runner for a bounded-scale namespace."""
    return AgenticCampaignRunner(
        freeze_revision=freeze_revision,
        base_environment=environment,
        fixture_controller=GuardedPostgresAgenticFixtureController(
            freeze_revision=freeze_revision,
            phase=_PHASE,
        ),
        execution_namespace=namespace,
    )


async def _timed_profile(
    profile: str,
    runner: AgenticCampaignRunner,
    scenarios: Sequence[str],
    *,
    concurrent: bool = False,
) -> Mapping[str, Any]:
    """Time one profile and measure concurrent top-level session ownership."""
    started = time.perf_counter()
    peak = 0
    active = 0

    async def _run(scenario: str) -> AgenticScenarioResult:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            return await runner.run_repetition(scenario, 1)
        finally:
            active -= 1

    if concurrent:
        results = tuple(await asyncio.gather(*(_run(item) for item in scenarios)))
    else:
        results = tuple([await _run(item) for item in scenarios])
    namespace = runner.execution_namespace
    return {
        "profile": profile,
        "namespace": namespace,
        "scenarios": tuple(scenarios),
        "results": results,
        "wall_seconds": time.perf_counter() - started,
        "peak_concurrency": peak,
    }


def _span_count(
    environment: Mapping[str, str],
    *,
    freeze_revision: str,
    namespace: str,
    scenarios: Sequence[str],
) -> int:
    """Count redacted MLflow spans for every exact profile session."""
    session_ids = [
        session.session_id
        for scenario in scenarios
        for session in build_agentic_scenario_sessions(
            scenario,
            repetition=1,
            freeze_revision=freeze_revision,
            execution_namespace=namespace,
        )
    ]
    traces = load_mlflow_lifecycle_traces(
        tracking_uri=_required_environment(
            environment,
            "TRADER_AGENTS_MLFLOW_TRACKING_URI",
        ),
        experiment_name=_required_environment(
            environment,
            "TRADER_AGENTS_MLFLOW_EXPERIMENT",
        ),
        session_ids=session_ids,
    )
    return sum(len(trace.spans) for trace in traces)


def _required_environment(environment: Mapping[str, str], name: str) -> str:
    """Return one required non-empty controlled environment value."""
    value = str(environment.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for bounded-scale qualification")
    return value
