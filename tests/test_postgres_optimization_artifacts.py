"""Postgres projections for canonical optimization evidence."""

from __future__ import annotations

from trader_research.governance.artifacts import DOMAIN_OWNER_BY_ARTIFACT_TYPE

import pytest

from trader_research.governance.artifacts import (
    PARAMETER_OPTIMIZATION_PLAN,
    PARAMETER_OPTIMIZATION_RUN,
    PARAMETER_OPTIMIZATION_TRIAL,
)
from trader_research.infrastructure.postgres import (
    RESEARCH_ARTIFACT_SCHEMA_STATEMENTS,
    PostgresResearchArtifactStore,
)


def test_research_schema_has_canonical_optimization_tables_without_retired_projections() -> None:
    schema = "\n".join(RESEARCH_ARTIFACT_SCHEMA_STATEMENTS)
    assert "domain_owner TEXT NOT NULL" in schema
    assert "producer_tool TEXT NOT NULL" in schema
    assert "requested_by TEXT" in schema
    assert "actor TEXT" in schema
    assert "agent_owner TEXT" not in schema
    assert "legacy research_artifacts schema detected" in schema
    for table in (
        "research_parameter_optimization_plans",
        "research_parameter_optimization_runs",
        "research_parameter_optimization_trials",
        "research_experiment_tracking_projections",
        "research_parameter_optimization_evaluations",
        "research_parameter_optimization_audit_plans",
        "research_parameter_optimization_robustness_reports",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
    for retired in (
        "research_strategy_candidates",
        "research_strategy_validations",
        "research_risk_manager_candidates",
        "research_risk_manager_validations",
        "research_strategy_risk_stacks",
        "research_stack_validations",
        "research_backtest_sidecars",
        "research_evaluation_reports",
    ):
        assert retired not in schema


@pytest.mark.postgres
def test_optimization_artifacts_have_typed_pgadmin_visible_projections(
    postgres_research_artifact_store: PostgresResearchArtifactStore,
) -> None:
    store = postgres_research_artifact_store
    store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_PLAN],
        producer_tool="test_postgres_optimization_fixture",
        artifact_type=PARAMETER_OPTIMIZATION_PLAN,
        artifact_id="plan-1",
        payload={
            "artifact_type": PARAMETER_OPTIMIZATION_PLAN,
            "optimization_plan_id": "plan-1",
            "base_backtest_specification_id": "backtest-spec-1",
            "objective_implementation_version_id": "objective-1",
            "direction": "maximize",
            "seed": 7,
            "max_trials": 2,
            "status": "created",
        },
        status="created",
    )
    store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_RUN],
        producer_tool="test_postgres_optimization_fixture",
        artifact_type=PARAMETER_OPTIMIZATION_RUN,
        artifact_id="run-1",
        payload={
            "artifact_type": PARAMETER_OPTIMIZATION_RUN,
            "optimization_run_id": "run-1",
            "optimization_plan_id": "plan-1",
            "engine_profile": {
                "profile_name": "builtin_grid",
                "provider_version": "1",
                "configuration_digest": "digest-1",
            },
            "seed": 7,
            "status": "completed",
            "selected_trial_id": "trial-1",
            "selected_child_refs": {"backtest_specification_id": "child-spec-1"},
        },
        status="completed",
    )
    store.save_artifact(
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[PARAMETER_OPTIMIZATION_TRIAL],
        producer_tool="test_postgres_optimization_fixture",
        artifact_type=PARAMETER_OPTIMIZATION_TRIAL,
        artifact_id="trial-1",
        payload={
            "artifact_type": PARAMETER_OPTIMIZATION_TRIAL,
            "trial_id": "trial-1",
            "optimization_run_id": "run-1",
            "optimization_plan_id": "plan-1",
            "sequence": 0,
            "status": "passed",
            "objective_value": 1.25,
            "parameters": {"/strategy/parameters/period": 10},
            "child_refs": {
                "backtest_specification_id": "child-spec-1",
                "backtest_run_id": "child-run-1",
            },
        },
        status="passed",
    )

    run = store.connection().execute(
        """
        SELECT optimization_plan_id, engine_name, engine_version,
               engine_configuration_digest, selected_trial_id
        FROM research_parameter_optimization_runs
        WHERE optimization_run_id = %s
        """,
        ["run-1"],
    ).fetchone()
    trial = store.connection().execute(
        """
        SELECT sequence, status, objective_value, parameters
        FROM research_parameter_optimization_trials
        WHERE trial_id = %s
        """,
        ["trial-1"],
    ).fetchone()
    authority = store.connection().execute(
        """
        SELECT domain_owner, producer_tool, requested_by, actor
        FROM research_artifacts
        WHERE artifact_type = %s AND artifact_id = %s
        """,
        [PARAMETER_OPTIMIZATION_RUN, "run-1"],
    ).fetchone()

    assert run == {
        "optimization_plan_id": "plan-1",
        "engine_name": "builtin_grid",
        "engine_version": "1",
        "engine_configuration_digest": "digest-1",
        "selected_trial_id": "trial-1",
    }
    assert trial["sequence"] == 0
    assert trial["status"] == "passed"
    assert trial["objective_value"] == 1.25
    assert trial["parameters"] == {"/strategy/parameters/period": 10}
    assert authority == {
        "domain_owner": "Experiments",
        "producer_tool": "test_postgres_optimization_fixture",
        "requested_by": None,
        "actor": None,
    }
