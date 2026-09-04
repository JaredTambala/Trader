"""Guarded end-to-end qualification for the first model-backed Agent slice.

Subject: Complete Coordinator-to-Data-and-Strategy execution under the approved mutable scope.
Level: Cross-package controlled qualification.
Collaborators: Real local model, stdio MCP, guarded Postgres, and isolated coding workspace.
Guarantees: Loading, adaptation, admission, synthesis, and safety evidence complete together.
Non-goals: Broad scenario coverage, bounded scale, recovery, or live trading.
"""

from __future__ import annotations

import os

import anyio
import pytest

from tests.trader_agents.application_runtime.support.agentic_campaign import AgenticCampaignRunner
from tests.trader_agents.application_runtime.support.agentic_fixture import GuardedPostgresAgenticFixtureController
from tests.cross_package.qualification.support.postgres_verification import (
    AGENTIC_VERIFICATION_PROFILE,
    RETAIN_EVIDENCE_PHASE_ENV,
    VERIFICATION_PROFILE_ENV,
    load_qualification_profile,
    load_retained_evidence_phase,
    resolve_freeze_revision,
)


pytestmark = pytest.mark.postgres
_PHASE = "AGENTIC_POSTGRES_E2E"
_SCENARIO = "bounded_backfill_and_adaptation"


def test_real_model_completes_guarded_data_and_strategy_path() -> None:
    """Exercise Data loading, isolated adaptation, admission, and synthesis."""
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
        execution_namespace="postgres_e2e",
    )

    result = anyio.run(runner.run_repetition, _SCENARIO, 1)

    assert result.status == "passed", result.blockers
    assert set(result.delegated_roles) == {
        "data_research",
        "strategy_engineering",
    }
    assert {
        "data_load_evidence",
        "candidate_package",
        "passed_admission_report",
    }.issubset(result.evidence_types)
    assert result.forbidden_tool_calls == 0
    assert result.unapproved_mutations == 0
    assert result.replayed_accepted_mutations == 0
