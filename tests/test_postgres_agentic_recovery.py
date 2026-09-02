"""Fresh-process recovery qualification for the model-backed first slice."""

from __future__ import annotations

from functools import partial
import os

import anyio
import pytest

from tests.support.agentic_campaign import (
    AgenticCampaignRunner,
    execute_fresh_process_cancellation,
    execute_fresh_process_fault_sequence,
)
from tests.support.agentic_faults import (
    AFTER_STRATEGY_ADMISSION_FAILURE,
    AFTER_STRATEGY_ADMISSION_SUCCESS,
    AFTER_STRATEGY_PACKAGE,
    AFTER_STRATEGY_REGISTRATION,
    BEFORE_STRATEGY_ADMISSION,
    BEFORE_STRATEGY_PACKAGE,
    BEFORE_STRATEGY_REGISTRATION,
    BEFORE_STRATEGY_REPAIR_WRITE,
    BEFORE_DATA_MUTATION,
)
from tests.support.agentic_fixture import GuardedPostgresAgenticFixtureController
from tests.support.agentic_observation import load_mlflow_lifecycle_traces
from tests.support.agentic_scenarios import (
    build_agentic_scenario_sessions,
    load_agentic_scenario_inputs,
)
from tests.support.postgres_verification import (
    AGENTIC_VERIFICATION_PROFILE,
    RETAIN_EVIDENCE_PHASE_ENV,
    VERIFICATION_PROFILE_ENV,
    load_qualification_profile,
    load_retained_evidence_phase,
    resolve_freeze_revision,
)


pytestmark = pytest.mark.postgres
_PHASE = "AGENTIC_RECOVERY"
_SCENARIO = "crash_and_lost_response"
_STRATEGY_FAULT_CASES = (
    ("strategy_recovery_a", 1, BEFORE_STRATEGY_PACKAGE),
    ("strategy_recovery_a", 2, AFTER_STRATEGY_PACKAGE),
    ("strategy_recovery_a", 3, BEFORE_STRATEGY_REGISTRATION),
    ("strategy_recovery_b", 1, AFTER_STRATEGY_REGISTRATION),
    ("strategy_recovery_b", 2, BEFORE_STRATEGY_ADMISSION),
    ("strategy_recovery_b", 3, AFTER_STRATEGY_ADMISSION_FAILURE),
    ("strategy_recovery_c", 1, BEFORE_STRATEGY_REPAIR_WRITE),
    ("strategy_recovery_c", 2, AFTER_STRATEGY_ADMISSION_SUCCESS),
)


def test_agentic_session_recovers_across_four_fresh_processes() -> None:
    """Prove pre-mutation, lost-response, and return-reconciliation recovery."""
    profile = load_qualification_profile()
    if profile.name != AGENTIC_VERIFICATION_PROFILE:
        pytest.skip(f"set {VERIFICATION_PROFILE_ENV}={AGENTIC_VERIFICATION_PROFILE}")
    if load_retained_evidence_phase() != _PHASE:
        raise RuntimeError(f"{RETAIN_EVIDENCE_PHASE_ENV} must be {_PHASE}")
    freeze_revision = resolve_freeze_revision(profile)
    runner = AgenticCampaignRunner(
        freeze_revision=freeze_revision,
        base_environment=dict(os.environ),
        fixture_controller=GuardedPostgresAgenticFixtureController(
            freeze_revision=freeze_revision,
            phase=_PHASE,
        ),
        execution_namespace="postgres_recovery",
    )

    result = anyio.run(runner.run_repetition, _SCENARIO, 1)

    assert result.status == "passed", result.blockers
    assert len(result.trace_ids) >= 4
    assert result.deterministic_invariants["no_lost_canonical_receipt"] is True
    assert result.deterministic_invariants["no_replayed_accepted_mutation"] is True
    assert result.deterministic_invariants["budgets_within_limits"] is True
    assert result.replayed_accepted_mutations == 0


def test_strategy_path_recovers_at_every_package_and_admission_boundary() -> None:
    """Prove fresh-process recovery through initial and repaired candidates."""
    profile = load_qualification_profile()
    if profile.name != AGENTIC_VERIFICATION_PROFILE:
        pytest.skip(f"set {VERIFICATION_PROFILE_ENV}={AGENTIC_VERIFICATION_PROFILE}")
    if load_retained_evidence_phase() != _PHASE:
        raise RuntimeError(f"{RETAIN_EVIDENCE_PHASE_ENV} must be {_PHASE}")
    freeze_revision = resolve_freeze_revision(profile)
    environment = dict(os.environ)

    async def _run_all() -> None:
        for namespace, repetition, fault_mode in _STRATEGY_FAULT_CASES:
            runner = AgenticCampaignRunner(
                freeze_revision=freeze_revision,
                base_environment=environment,
                fixture_controller=GuardedPostgresAgenticFixtureController(
                    freeze_revision=freeze_revision,
                    phase=_PHASE,
                ),
                session_executor=partial(
                    execute_fresh_process_fault_sequence,
                    fault_modes=(fault_mode,),
                ),
                execution_namespace=namespace,
            )
            result = await runner.run_repetition(
                "new_authorship_and_repair",
                repetition,
            )
            assert result.status == "passed", (fault_mode, result.blockers)
            assert len(result.trace_ids) >= 2
            assert result.replayed_accepted_mutations == 0
            assert result.deterministic_invariants["no_lost_canonical_receipt"] is True

    anyio.run(_run_all)


def test_operator_cancellation_is_terminal_across_fresh_processes() -> None:
    """Interrupt, cancel, and replay one session in three separate processes."""
    profile = load_qualification_profile()
    if profile.name != AGENTIC_VERIFICATION_PROFILE:
        pytest.skip(f"set {VERIFICATION_PROFILE_ENV}={AGENTIC_VERIFICATION_PROFILE}")
    if load_retained_evidence_phase() != _PHASE:
        raise RuntimeError(f"{RETAIN_EVIDENCE_PHASE_ENV} must be {_PHASE}")
    freeze_revision = resolve_freeze_revision(profile)
    scenario_id = "bounded_backfill_and_adaptation"
    sessions = build_agentic_scenario_sessions(
        scenario_id,
        repetition=3,
        freeze_revision=freeze_revision,
        execution_namespace="strategy_recovery_c",
    )
    session = sessions[0]
    controller = GuardedPostgresAgenticFixtureController(
        freeze_revision=freeze_revision,
        phase=_PHASE,
    )

    async def _run() -> tuple[dict[str, object], dict[str, str], frozenset[str]]:
        environment = dict(
            await controller.prepare(
                load_agentic_scenario_inputs()[scenario_id],
                sessions,
                dict(os.environ),
            )
        )
        state = dict(
            await execute_fresh_process_cancellation(
                session,
                environment,
                True,
                fault_mode=BEFORE_DATA_MUTATION,
            )
        )
        decision_ref = str(state.get("decision_receipt_ref") or "")
        resolved = await controller.resolve_evidence_refs(frozenset({decision_ref}))
        return state, environment, resolved

    state, environment, resolved = anyio.run(_run)
    decision_ref = str(state["decision_receipt_ref"])
    traces = load_mlflow_lifecycle_traces(
        tracking_uri=environment["TRADER_AGENTS_MLFLOW_TRACKING_URI"],
        experiment_name=environment["TRADER_AGENTS_MLFLOW_EXPERIMENT"],
        session_ids=[session.session_id],
    )
    root_spans = [
        span
        for trace in traces
        for span in trace.spans
        if span.name.startswith("agent.session.")
    ]

    assert state["status"] == "cancelled"
    assert state["pending_interrupt"] == {}
    assert decision_ref in resolved
    assert {trace.operation for trace in traces} >= {"start", "cancel", "inspect"}
    assert (
        len({str(span.attributes["trader.process_instance_id"]) for span in root_spans})
        >= 3
    )
