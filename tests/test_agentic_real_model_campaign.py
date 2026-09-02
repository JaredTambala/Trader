"""Repeated real-model campaign for the frozen first agentic slice."""

from __future__ import annotations

import os

import anyio
import psycopg
from psycopg.rows import dict_row
import pytest

from tests.support.agentic_campaign import AgenticCampaignRunner
from tests.support.agentic_fixture import GuardedPostgresAgenticFixtureController
from tests.support.agentic_qualification import (
    evaluate_agentic_campaign,
    load_agentic_scenario_results,
    save_agentic_scenario_result,
)
from tests.support.postgres_verification import (
    AGENTIC_VERIFICATION_PROFILE,
    RETAIN_EVIDENCE_PHASE_ENV,
    VERIFICATION_PROFILE_ENV,
    load_qualification_profile,
    load_retained_evidence_phase,
    load_test_settings,
    resolve_freeze_revision,
)


_PHASE = "AGENTIC_REAL_MODEL"


@pytest.mark.postgres
def test_complete_repeated_real_model_campaign() -> None:
    """Run, persist, reload, and score every frozen scenario repetition."""
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
    controller = GuardedPostgresAgenticFixtureController(
        freeze_revision=freeze_revision,
        phase=_PHASE,
    )
    with psycopg.connect(
        settings.conninfo(),
        autocommit=True,
        row_factory=dict_row,
    ) as connection:
        runner = AgenticCampaignRunner(
            freeze_revision=freeze_revision,
            base_environment=environment,
            fixture_controller=controller,
            result_sink=lambda result: save_agentic_scenario_result(
                connection,
                qualification_profile=profile.name,
                freeze_revision=freeze_revision,
                result=result,
            ),
        )
        results = anyio.run(runner.run_all)
        reloaded = load_agentic_scenario_results(
            connection,
            qualification_profile=profile.name,
            freeze_revision=freeze_revision,
        )

    assert reloaded == results
    verdict = evaluate_agentic_campaign(reloaded)
    assert verdict["status"] == "passed", verdict["blockers"]
    assert verdict["result_count"] == 36
