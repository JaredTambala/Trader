"""Task 57S acceptance record over controlled Postgres qualification evidence."""

from __future__ import annotations

from typing import Any, Mapping

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest
import psycopg

from tests.support.postgres_verification import (
    assert_connection_targets_verification_database,
    load_test_settings,
    resolve_freeze_revision,
)


_MANDATORY_PHASES = tuple(f"57{letter}" for letter in "JKLMNOPQR")
_COMMANDS = {
    "57J": [
        "uv run pytest tests/test_postgres_verification_runtime.py -m postgres -q -W error",
    ],
    "57K": [
        "uv run ruff check src/trader_research src/trader_mcp src/trader_agents src/trader_standard src/trader tests",
        "python -m compileall -q src/trader_research src/trader_mcp src/trader_agents src/trader_standard src/trader",
        "uv run mypy",
        "uv run pytest -m 'not postgres' -q -W error",
        "uv run pytest tests/test_mcp_tools.py tests/test_mcp_data_workflow.py tests/test_mcp_quant_methods_tools.py tests/test_mcp_optimization_tools.py tests/test_agent_identities.py tests/test_research_agent_docs.py tests/test_research_domain.py tests/test_package_boundaries.py -q -W error",
        "git diff --check verification-57i-freeze-v6^ verification-57i-freeze-v6",
    ],
    "57L": [
        "uv run pytest tests/test_postgres_realistic_optimization_fixture.py -m postgres -q -W error",
    ],
    "57M": [
        "uv run pytest tests/test_postgres_optimization_evidence_graph.py -m postgres -q -W error -s",
    ],
    "57N": [
        "uv run pytest tests/test_postgres_optimization_determinism_integrity.py -m postgres -q -W error -s",
    ],
    "57O": [
        "uv run pytest tests/test_postgres_optimization_recovery.py -m postgres -q -W error",
    ],
    "57P": [
        "uv run pytest tests/test_postgres_optimization_provider_independence.py -m postgres -q -W error",
    ],
    "57Q": [
        "uv run pytest tests/test_parameter_optimization.py tests/test_mcp_optimization_tools.py tests/test_implementation_templates.py tests/test_package_boundaries.py -q -W error",
    ],
    "57R": [
        "uv run pytest tests/test_postgres_optimization_bounded_scale.py tests/test_postgres_optimization_evidence_graph.py -m postgres -q -W error -s",
    ],
}


@pytest.mark.postgres
def test_controlled_optimization_acceptance_record() -> None:
    settings = load_test_settings(required=True)
    assert settings is not None
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
            "WHERE phase = ANY(%s) ORDER BY phase",
            [list(_MANDATORY_PHASES)],
        ).fetchall()
        assert [row["phase"] for row in phases] == list(_MANDATORY_PHASES)
        assert all(row["freeze_revision"] == freeze_revision for row in phases)
        assert all(row["isolation_status"] == "passed" for row in phases)
        assert all(row["qualification_status"] == "passed" for row in phases)
        assert all(row["blockers"] == [] for row in phases)
        assert all(
            row["operator_before_digest"] == row["operator_after_digest"]
            for row in phases
        )

        scale_rows = connection.execute(
            "SELECT profile, status, symbols, bars_per_symbol, trial_count, "
            "wall_seconds, result_query_seconds, database_bytes, artifact_count, payload "
            "FROM verification_control.bounded_scale_results "
            "WHERE phase = '57R' ORDER BY profile"
        ).fetchall()
        assert {row["profile"] for row in scale_rows} == {
            "builtin_grid_64",
            "builtin_random_100",
            "portfolio_backtest_1000_bars",
        }
        assert all(row["status"] == "passed" for row in scale_rows)

        artifact_counts = _mapping_rows(
            connection.execute(
                "SELECT artifact_type, count(*) AS row_count FROM research_artifacts "
                "GROUP BY artifact_type ORDER BY artifact_type"
            ).fetchall(),
            key="artifact_type",
        )
        assert int(artifact_counts.get("parameter_optimization_evaluation_report", 0)) >= 1
        assert int(artifact_counts.get("parameter_optimization_robustness_report", 0)) >= 1
        assert int(artifact_counts.get("parameter_optimization_trial", 0)) >= 4

        root_refs = {
            "optimization_runs": _ids(
                connection,
                "SELECT optimization_run_id AS id FROM research_parameter_optimization_runs ORDER BY id",
            ),
            "evaluations": _ids(
                connection,
                "SELECT report_id AS id FROM research_parameter_optimization_evaluations ORDER BY id",
            ),
            "adversarial_reports": _ids(
                connection,
                "SELECT report_id AS id FROM research_parameter_optimization_robustness_reports ORDER BY id",
            ),
        }
        assert all(root_refs.values())

        provider_profiles = {
            "builtin_grid": {
                "status": "qualified",
                "external_provider_writes": False,
            },
            "builtin_random": {
                "status": "qualified",
                "external_provider_writes": False,
            },
            "optuna_tpe": {
                "status": "not_qualified",
                "write_gate": "TRADER_MCP_ALLOW_OPTUNA_WRITES",
                "writes_enabled": False,
            },
            "mlflow_tracking": {
                "status": "not_qualified",
                "write_gate": "TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES",
                "writes_enabled": False,
            },
        }
        mandatory_phases = {
            row["phase"]: {
                "status": row["qualification_status"],
                "configuration_digest": row["manifest"]["configuration_digest"],
                "started_at": row["started_at"].isoformat(),
                "finished_at": row["finished_at"].isoformat(),
            }
            for row in phases
        }
        lock_hashes = {
            str(row["manifest"]["dependency_lock_sha256"]) for row in phases
        }
        assert len(lock_hashes) == 1
        environment = {
            "database": identity["database_name"],
            "role": identity["role_name"],
            "timezone": identity["timezone"],
            "locale": identity["lc_collate"],
            "dependency_lock_sha256": next(iter(lock_hashes)),
            "operator_fingerprint": phases[0]["operator_after_digest"],
        }
        evidence_inventory = {
            "artifact_counts": artifact_counts,
            "root_refs": root_refs,
            "bounded_scale": [dict(row) for row in scale_rows],
        }
        residual_risks = [
            "Optuna adapter is not qualified and must remain gated off.",
            "MLflow tracking projection is not qualified and must remain gated off.",
            "Source admission is a bounded validation policy, not an OS security sandbox.",
            "Scale results are local bounded measurements, not universal performance guarantees.",
        ]
        connection.execute(
            "INSERT INTO verification_control.acceptance_records ("
            "freeze_revision, status, mandatory_phases, provider_profiles, environment, "
            "evidence_inventory, commands, residual_risks) "
            "VALUES (%s, 'passed', %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (freeze_revision) DO UPDATE SET status = EXCLUDED.status, "
            "mandatory_phases = EXCLUDED.mandatory_phases, "
            "provider_profiles = EXCLUDED.provider_profiles, environment = EXCLUDED.environment, "
            "evidence_inventory = EXCLUDED.evidence_inventory, commands = EXCLUDED.commands, "
            "residual_risks = EXCLUDED.residual_risks, recorded_at = now()",
            [
                freeze_revision,
                Jsonb(mandatory_phases),
                Jsonb(provider_profiles),
                Jsonb(environment),
                Jsonb(evidence_inventory),
                Jsonb(_COMMANDS),
                Jsonb(residual_risks),
            ],
        )
        saved = connection.execute(
            "SELECT status, provider_profiles, residual_risks "
            "FROM verification_control.acceptance_records WHERE freeze_revision = %s",
            [freeze_revision],
        ).fetchone()
        assert saved is not None
        assert saved["status"] == "passed"
        assert saved["provider_profiles"] == provider_profiles
        assert saved["residual_risks"] == residual_risks


def _mapping_rows(rows: list[Mapping[str, Any]], *, key: str) -> dict[str, int]:
    return {str(row[key]): int(row["row_count"]) for row in rows}


def _ids(connection: psycopg.Connection[Any], query: str) -> list[str]:
    return [str(row["id"]) for row in connection.execute(query).fetchall()]
