"""Acceptance record over retained controlled orchestration evidence."""

from __future__ import annotations

from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

from trader_mcp.constants import (
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL,
    RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL,
    RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL,
)
from tests.support.postgres_verification import (
    ORCHESTRATION_VERIFICATION_PROFILE,
    assert_connection_targets_verification_database,
    resolve_freeze_revision,
    settings_from_mapping,
)


_MANDATORY_PHASES = (
    "ORCHESTRATION_RUNTIME",
    "ORCHESTRATION_CORE",
    "ORCHESTRATION_E2E",
    "ORCHESTRATION_RECOVERY",
    "ORCHESTRATION_POLICY",
    "ORCHESTRATION_SCALE",
)
_COMMANDS = {
    "ORCHESTRATION_RUNTIME": [
        "uv run pytest tests/test_postgres_orchestration_runtime.py -m postgres -q -W error",
    ],
    "ORCHESTRATION_CORE": [
        "uv run ruff check src tests",
        "python -m compileall -q src tests/support",
        "uv run mypy",
        "uv run pytest -m 'not postgres' -q -W error",
    ],
    "ORCHESTRATION_E2E": [
        "uv run pytest tests/test_postgres_orchestration_evidence_graph.py -m postgres -q -W error -s",
    ],
    "ORCHESTRATION_RECOVERY": [
        "uv run pytest tests/test_postgres_orchestration_recovery.py -m postgres -q -W error -s",
    ],
    "ORCHESTRATION_POLICY": [
        "uv run pytest tests/test_orchestration_policy_security.py tests/test_research_composition.py tests/test_experiment_design_specialist.py tests/test_package_boundaries.py -q -W error",
    ],
    "ORCHESTRATION_SCALE": [
        "uv run pytest tests/test_postgres_orchestration_bounded_scale.py -m postgres -q -W error -s",
    ],
}


@pytest.mark.postgres
def test_controlled_orchestration_acceptance_record(
    postgres_settings: dict[str, object],
) -> None:
    """Require all retained phases and write one credential-free verdict."""
    settings = settings_from_mapping(postgres_settings)
    freeze_revision = resolve_freeze_revision()
    with psycopg.connect(
        settings.conninfo(),
        autocommit=True,
        row_factory=dict_row,
    ) as connection:
        identity = assert_connection_targets_verification_database(
            connection,
            settings,
            freeze_revision=freeze_revision,
        )
        phases = connection.execute(
            "SELECT phase, freeze_revision, isolation_status, qualification_status, "
            "blockers, manifest, operator_before_digest, operator_after_digest, "
            "started_at, finished_at FROM verification_control.phase_runs "
            "WHERE phase = ANY(%s)",
            [list(_MANDATORY_PHASES)],
        ).fetchall()
        by_phase = {str(row["phase"]): row for row in phases}
        assert set(by_phase) == set(_MANDATORY_PHASES)
        assert all(row["freeze_revision"] == freeze_revision for row in phases)
        assert all(row["isolation_status"] == "passed" for row in phases)
        assert all(row["qualification_status"] == "passed" for row in phases)
        assert all(row["blockers"] == [] for row in phases)
        assert all(
            row["operator_before_digest"] == row["operator_after_digest"]
            for row in phases
        )
        assert all(
            row["manifest"]["qualification_profile"]
            == ORCHESTRATION_VERIFICATION_PROFILE
            for row in phases
        )
        lock_hashes = {
            str(row["manifest"]["dependency_lock_sha256"]) for row in phases
        }
        assert len(lock_hashes) == 1

        scale_rows = connection.execute(
            "SELECT profile, status, task_count, transition_count, "
            "tool_call_count, checkpoint_bytes, artifact_count, database_bytes, "
            "wall_seconds, payload FROM "
            "verification_control.orchestration_scale_results "
            "WHERE qualification_profile = %s AND freeze_revision = %s "
            "AND phase = 'ORCHESTRATION_SCALE' ORDER BY profile",
            [ORCHESTRATION_VERIFICATION_PROFILE, freeze_revision],
        ).fetchall()
        assert {row["profile"] for row in scale_rows} == {
            "eight_explicit_data_tasks",
            "three_symbol_1000_bar_baseline",
        }
        assert all(row["status"] == "passed" for row in scale_rows)
        assert all(row["checkpoint_bytes"] > 0 for row in scale_rows)
        assert all(row["database_bytes"] > 0 for row in scale_rows)

        call_expectations = _call_expectations(
            connection,
            freeze_revision=freeze_revision,
        )
        root_refs = _root_refs(connection)
        assert root_refs["protocol_proposals"]
        assert root_refs["workflow_outcomes"]
        _assert_root_refs_resolve(connection, root_refs)

        mandatory_phases = {
            phase: {
                "status": by_phase[phase]["qualification_status"],
                "configuration_digest": by_phase[phase]["manifest"][
                    "configuration_digest"
                ],
                "started_at": by_phase[phase]["started_at"].isoformat(),
                "finished_at": by_phase[phase]["finished_at"].isoformat(),
            }
            for phase in _MANDATORY_PHASES
        }
        qualified_surface = {
            "coordinator": "bounded deterministic research coordination",
            "specialists": ["Data Agent", "Experiment Design Agent"],
            "workflow": "supplied_implementation_to_evidence",
            "approval_authority": "operator",
        }
        exclusions = [
            "prose-to-task inference",
            "dynamic specialist-task binding",
            "Quantitative Methods, ML, general Robustness, and final Evaluation specialists",
            "optional external providers",
            "deployment, paper trading, and live trading",
        ]
        environment = {
            "database": identity["database_name"],
            "product_role": identity["role_name"],
            "timezone": identity["timezone"],
            "locale": identity["lc_collate"],
            "dependency_lock_sha256": next(iter(lock_hashes)),
            "operator_fingerprint": phases[0]["operator_after_digest"],
        }
        evidence_inventory = {
            "root_refs": root_refs,
            "call_expectations": call_expectations,
            "bounded_scale": [dict(row) for row in scale_rows],
        }
        residual_risks = [
            "Qualification covers only explicit caller-built Data and Experiment Design tasks.",
            "Optional optimisation and tracking providers remain unqualified and gated off.",
            "Scale rows are local bounded measurements, not universal service-level objectives.",
            "Operational checkpoints remain replaceable state rather than research evidence.",
        ]
        connection.execute(
            "INSERT INTO verification_control.orchestration_acceptance_records ("
            "qualification_profile, freeze_revision, status, qualified_surface, "
            "exclusions, mandatory_phases, environment, evidence_inventory, commands, "
            "residual_risks) VALUES (%s, %s, 'passed', %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (qualification_profile, freeze_revision) DO UPDATE SET "
            "status = 'passed', qualified_surface = EXCLUDED.qualified_surface, "
            "exclusions = EXCLUDED.exclusions, mandatory_phases = EXCLUDED.mandatory_phases, "
            "environment = EXCLUDED.environment, "
            "evidence_inventory = EXCLUDED.evidence_inventory, "
            "commands = EXCLUDED.commands, residual_risks = EXCLUDED.residual_risks, "
            "recorded_at = now()",
            [
                ORCHESTRATION_VERIFICATION_PROFILE,
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
        saved = connection.execute(
            "SELECT status, qualified_surface, exclusions, residual_risks "
            "FROM verification_control.orchestration_acceptance_records "
            "WHERE qualification_profile = %s AND freeze_revision = %s",
            [ORCHESTRATION_VERIFICATION_PROFILE, freeze_revision],
        ).fetchone()
        assert saved is not None
        assert saved["status"] == "passed"
        assert saved["qualified_surface"] == qualified_surface
        assert saved["exclusions"] == exclusions
        assert saved["residual_risks"] == residual_risks


def _call_expectations(
    connection: psycopg.Connection[Any],
    *,
    freeze_revision: str,
) -> Mapping[str, Any]:
    rows = connection.execute(
        "SELECT phase, command, retry_disposition, count(*) AS call_count "
        "FROM verification_control.orchestration_call_ledger "
        "WHERE qualification_profile = %s AND freeze_revision = %s "
        "GROUP BY phase, command, retry_disposition",
        [ORCHESTRATION_VERIFICATION_PROFILE, freeze_revision],
    ).fetchall()
    counts = {
        f"{row['phase']}:{row['command']}:{row['retry_disposition']}": int(
            row["call_count"]
        )
        for row in rows
    }
    assert counts[
        f"ORCHESTRATION_E2E:{RESEARCH_CREATE_EXPERIMENT_PROTOCOL_PROPOSAL_TOOL}:accepted"
    ] == 1
    assert counts[
        f"ORCHESTRATION_E2E:{RESEARCH_REGISTER_EXPERIMENT_WORKFLOW_TOOL}:accepted"
    ] == 1
    assert counts[
        f"ORCHESTRATION_E2E:{RESEARCH_RECORD_WORKFLOW_OUTCOME_TOOL}:accepted"
    ] == 1
    assert counts[
        f"ORCHESTRATION_E2E:{DATA_CREATE_RESEARCH_SNAPSHOT_TOOL}:accepted"
    ] == 4
    assert any(key.endswith(":response_lost") for key in counts)
    assert any(key.endswith(":identical_retry") for key in counts)
    return counts


def _root_refs(connection: psycopg.Connection[Any]) -> Mapping[str, list[str]]:
    proposals = connection.execute(
        "SELECT proposal_id FROM research_experiment_protocol_proposals "
        "ORDER BY proposal_id"
    ).fetchall()
    outcomes = connection.execute(
        "SELECT outcome_id FROM research_workflow_outcomes ORDER BY outcome_id"
    ).fetchall()
    return {
        "protocol_proposals": [
            f"research://postgres/experiment_protocol_proposal/{row['proposal_id']}"
            for row in proposals
        ],
        "workflow_outcomes": [
            f"research://postgres/workflow_outcome/{row['outcome_id']}"
            for row in outcomes
        ],
    }


def _assert_root_refs_resolve(
    connection: psycopg.Connection[Any],
    root_refs: Mapping[str, list[str]],
) -> None:
    for uri in (*root_refs["protocol_proposals"], *root_refs["workflow_outcomes"]):
        artifact_type, artifact_id = uri.removeprefix("research://postgres/").split(
            "/", 1
        )
        row = connection.execute(
            "SELECT 1 FROM research_artifacts WHERE artifact_type = %s "
            "AND artifact_id = %s",
            [artifact_type, artifact_id],
        ).fetchone()
        assert row is not None
