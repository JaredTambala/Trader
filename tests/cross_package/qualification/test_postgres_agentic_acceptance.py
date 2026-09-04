"""Canonical acceptance record for the frozen first agentic research slice.

Subject: Final reconciliation and persistence of every mandatory Agent qualification phase.
Level: Cross-package controlled acceptance.
Collaborators: Guarded Postgres evidence, campaign results, scale results, and exact command manifests.
Guarantees: One credential-free reviewed verdict binds every phase to the same frozen revision.
Non-goals: Executing the preceding phases, repairing failed evidence, or changing agent behavior.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

from tests.trader_agents.application_runtime.support.agentic_qualification import (
    evaluate_agentic_campaign,
    load_agentic_scenario_results,
)
from tests.trader_agents.application_runtime.support.agentic_scale import (
    AGENTIC_SCALE_PROFILES,
    load_agentic_scale_results,
)
from tests.cross_package.qualification.support.postgres_verification import (
    AGENTIC_VERIFICATION_PROFILE,
    VERIFICATION_PROFILE_ENV,
    assert_connection_targets_verification_database,
    load_qualification_profile,
    resolve_freeze_revision,
    settings_from_mapping,
)


_MANDATORY_PHASES = (
    "AGENTIC_RUNTIME_ISOLATION",
    "AGENTIC_CORE_CHECKS",
    "AGENTIC_POSTGRES_E2E",
    "AGENTIC_RECOVERY",
    "AGENTIC_SECURITY",
    "AGENTIC_SANDBOX",
    "AGENTIC_REAL_MODEL",
    "AGENTIC_BOUNDED_SCALE",
)
_COMMANDS = {
    "AGENTIC_RUNTIME_ISOLATION": [
        "uv run pytest tests/cross_package/qualification/test_postgres_agentic_runtime_isolation.py -m postgres -q -W error",
    ],
    "AGENTIC_CORE_CHECKS": [
        "uv run ruff check src tests",
        "uv run mypy src/trader_agents src/trader_mcp src/trader_research tests/trader_agents tests/cross_package/qualification/test_agentic_sandbox_qualification.py tests/cross_package/qualification/test_postgres_agentic_acceptance.py tests/cross_package/qualification/test_postgres_agentic_bounded_scale.py tests/cross_package/qualification/test_postgres_agentic_end_to_end.py tests/cross_package/qualification/test_postgres_agentic_recovery.py tests/cross_package/qualification/test_postgres_agentic_runtime_isolation.py tests/cross_package/qualification/test_postgres_agentic_security.py",
        "uv run pytest -m 'not postgres' -q -W error",
    ],
    "AGENTIC_POSTGRES_E2E": [
        "uv run pytest tests/cross_package/qualification/test_postgres_agentic_end_to_end.py -m postgres -q -W error -s",
    ],
    "AGENTIC_RECOVERY": [
        "uv run pytest tests/cross_package/qualification/test_postgres_agentic_recovery.py -m postgres -q -W error -s",
    ],
    "AGENTIC_SECURITY": [
        "uv run pytest tests/trader_research/governance/test_agent_session_governance.py tests/trader_agents tests/cross_package/boundaries -m 'not postgres' -q -W error",
        "uv run pytest tests/cross_package/qualification/test_postgres_agentic_security.py -m postgres -q -W error -s",
    ],
    "AGENTIC_SANDBOX": [
        "uv run pytest tests/cross_package/qualification/test_agentic_sandbox_qualification.py -q -W error -s",
    ],
    "AGENTIC_REAL_MODEL": [
        "uv run pytest tests/cross_package/qualification/test_agentic_real_model_campaign.py -q -W error -s",
    ],
    "AGENTIC_BOUNDED_SCALE": [
        "uv run pytest tests/cross_package/qualification/test_postgres_agentic_bounded_scale.py -m postgres -q -W error -s",
    ],
    "AGENTIC_ACCEPTANCE": [
        "uv run pytest tests/cross_package/qualification/test_postgres_agentic_acceptance.py -m postgres -q -W error -s",
    ],
}


@pytest.mark.postgres
def test_frozen_agentic_research_acceptance_record(
    postgres_settings: dict[str, object],
) -> None:
    """Require every phase and persist one reviewed credential-free verdict."""
    profile = load_qualification_profile()
    if profile.name != AGENTIC_VERIFICATION_PROFILE:
        pytest.skip(f"set {VERIFICATION_PROFILE_ENV}={AGENTIC_VERIFICATION_PROFILE}")
    reviewer_id = _required_reviewer_id()
    settings = settings_from_mapping(postgres_settings)
    freeze_revision = resolve_freeze_revision(profile)
    with psycopg.connect(
        settings.conninfo(),
        autocommit=True,
        row_factory=dict_row,
    ) as connection:
        database_identity = assert_connection_targets_verification_database(
            connection,
            settings,
            freeze_revision=freeze_revision,
        )
        phases = _load_passed_phases(connection, freeze_revision=freeze_revision)
        agentic_identities = {
            str(row["manifest"]["agentic_identity"]["identity_digest"])
            for row in phases.values()
        }
        lock_hashes = {
            str(row["manifest"]["dependency_lock_sha256"]) for row in phases.values()
        }
        assert len(agentic_identities) == 1
        assert len(lock_hashes) == 1
        public_identity = next(iter(phases.values()))["manifest"]["agentic_identity"]

        results = load_agentic_scenario_results(
            connection,
            qualification_profile=AGENTIC_VERIFICATION_PROFILE,
            freeze_revision=freeze_revision,
        )
        campaign = evaluate_agentic_campaign(results)
        assert campaign["status"] == "passed", campaign["blockers"]
        assert campaign["result_count"] == 36
        scale_results = load_agentic_scale_results(
            connection,
            qualification_profile=AGENTIC_VERIFICATION_PROFILE,
            freeze_revision=freeze_revision,
        )
        assert {item.profile for item in scale_results} == AGENTIC_SCALE_PROFILES
        assert all(item.status == "passed" for item in scale_results)
        assert all(item.checkpoint_bytes > 0 for item in scale_results)
        assert all(item.database_bytes > 0 for item in scale_results)

        mandatory_phases = {
            phase: {
                "status": row["qualification_status"],
                "configuration_digest": row["manifest"]["configuration_digest"],
                "started_at": row["started_at"].isoformat(),
                "finished_at": row["finished_at"].isoformat(),
            }
            for phase, row in sorted(phases.items())
        }
        qualified_surface = {
            "coordinator": "model-backed Research Coordinator",
            "specialists": ["Data Research", "Strategy Engineering"],
            "terminal_boundary": (
                "coordinator-accepted Data readiness plus independently admitted "
                "strategy or risk implementation"
            ),
            "capability_boundary": "role-scoped MCP only",
            "approval_authority": "owning operator",
        }
        exclusions = [
            "Knowledge Research and Quantitative Methods",
            "Experiment Design, backtesting, optimization, robustness, and walk-forward analysis",
            "ML research and ML Agent behavior",
            "strategy-performance judgment and recommendation",
            "paper or live deployment and broker mutation",
        ]
        environment = {
            "reviewer_id": reviewer_id,
            "database": database_identity["database_name"],
            "product_role": database_identity["role_name"],
            "timezone": database_identity["timezone"],
            "locale": database_identity["lc_collate"],
            "dependency_lock_sha256": next(iter(lock_hashes)),
            "agentic_identity": public_identity,
            "operator_fingerprint": next(iter(phases.values()))[
                "operator_after_digest"
            ],
        }
        evidence_inventory = {
            "campaign": campaign,
            "bounded_scale": [
                {
                    "profile": item.profile,
                    "task_count": item.task_count,
                    "tool_call_count": item.tool_call_count,
                    "checkpoint_bytes": item.checkpoint_bytes,
                    "artifact_count": item.artifact_count,
                    "database_bytes": item.database_bytes,
                    "wall_seconds": item.wall_seconds,
                    "payload": dict(item.payload),
                }
                for item in scale_results
            ],
            "scenario_results": [
                {
                    "scenario_id": result.scenario_id,
                    "repetition": result.repetition,
                    "trace_ids": list(result.trace_ids),
                    "evidence_refs": list(result.evidence_refs),
                }
                for result in results
            ],
        }
        residual_risks = [
            "The accepted surface ends before experiment design or performance evidence.",
            "Bounded local measurements are not universal service-level objectives.",
            "Operational checkpoints are replaceable state rather than research evidence.",
        ]
        _save_acceptance_record(
            connection,
            freeze_revision=freeze_revision,
            qualified_surface=qualified_surface,
            exclusions=exclusions,
            mandatory_phases=mandatory_phases,
            environment=environment,
            evidence_inventory=evidence_inventory,
            residual_risks=residual_risks,
        )
        saved = connection.execute(
            """
            SELECT status, qualified_surface, exclusions, mandatory_phases,
                   environment, evidence_inventory, commands, residual_risks
            FROM verification_control.orchestration_acceptance_records
            WHERE qualification_profile = %s AND freeze_revision = %s
            """,
            [AGENTIC_VERIFICATION_PROFILE, freeze_revision],
        ).fetchone()
        assert saved is not None
        assert saved["status"] == "passed"
        assert saved["qualified_surface"] == qualified_surface
        assert saved["exclusions"] == exclusions
        assert saved["mandatory_phases"] == mandatory_phases
        assert saved["environment"] == environment
        assert saved["evidence_inventory"] == evidence_inventory
        assert saved["commands"] == _COMMANDS
        assert saved["residual_risks"] == residual_risks


def _load_passed_phases(
    connection: psycopg.Connection[Any],
    *,
    freeze_revision: str,
) -> dict[str, Mapping[str, Any]]:
    """Load and validate every mandatory phase for the exact freeze."""
    rows = connection.execute(
        """
        SELECT phase, freeze_revision, isolation_status, qualification_status,
               blockers, manifest, operator_before_digest,
               operator_after_digest, started_at, finished_at
        FROM verification_control.phase_runs
        WHERE phase = ANY(%s)
        """,
        [list(_MANDATORY_PHASES)],
    ).fetchall()
    by_phase = {str(row["phase"]): row for row in rows}
    assert set(by_phase) == set(_MANDATORY_PHASES)
    assert all(row["freeze_revision"] == freeze_revision for row in rows)
    assert all(row["isolation_status"] == "passed" for row in rows)
    assert all(row["qualification_status"] == "passed" for row in rows)
    assert all(row["blockers"] == [] for row in rows)
    assert all(row["finished_at"] is not None for row in rows)
    assert all(
        row["operator_before_digest"] == row["operator_after_digest"] for row in rows
    )
    assert all(
        row["manifest"]["qualification_profile"] == AGENTIC_VERIFICATION_PROFILE
        for row in rows
    )
    return by_phase


def _save_acceptance_record(
    connection: psycopg.Connection[Any],
    *,
    freeze_revision: str,
    qualified_surface: Mapping[str, Any],
    exclusions: list[str],
    mandatory_phases: Mapping[str, Any],
    environment: Mapping[str, Any],
    evidence_inventory: Mapping[str, Any],
    residual_risks: list[str],
) -> None:
    """Upsert the exact reviewed acceptance record."""
    connection.execute(
        """
        INSERT INTO verification_control.orchestration_acceptance_records (
            qualification_profile, freeze_revision, status, qualified_surface,
            exclusions, mandatory_phases, environment, evidence_inventory,
            commands, residual_risks
        ) VALUES (%s, %s, 'passed', %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (qualification_profile, freeze_revision) DO UPDATE SET
            status = 'passed',
            qualified_surface = EXCLUDED.qualified_surface,
            exclusions = EXCLUDED.exclusions,
            mandatory_phases = EXCLUDED.mandatory_phases,
            environment = EXCLUDED.environment,
            evidence_inventory = EXCLUDED.evidence_inventory,
            commands = EXCLUDED.commands,
            residual_risks = EXCLUDED.residual_risks,
            recorded_at = now()
        """,
        [
            AGENTIC_VERIFICATION_PROFILE,
            freeze_revision,
            Jsonb(qualified_surface),
            Jsonb(exclusions),
            Jsonb(mandatory_phases),
            Jsonb(environment),
            Jsonb(evidence_inventory),
            Jsonb(_COMMANDS),
            Jsonb(residual_risks),
        ],
    )


def _required_reviewer_id() -> str:
    """Return the explicit public reviewer identity for final acceptance."""
    value = str(os.environ.get("TRADER_AGENTIC_QUALIFICATION_REVIEWER") or "").strip()
    if not value or len(value.encode("utf-8")) > 200:
        raise ValueError(
            "TRADER_AGENTIC_QUALIFICATION_REVIEWER must contain 1 to 200 bytes"
        )
    return value
