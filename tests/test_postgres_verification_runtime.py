"""Isolation and manifest checks for the controlled Postgres verification runtime."""

from __future__ import annotations

import json
import os

import psycopg
from psycopg.rows import dict_row
import pytest

from trader.event_store import PostgresEventStore
from tests.support.postgres_verification import (
    MUTATION_GATE_NAMES,
    RETAIN_EVIDENCE_PHASE_ENV,
    VerificationConfigurationError,
    assert_verification_database,
    build_runtime_manifest,
    _is_harness_path,
    _validate_outcome,
    load_operator_settings,
    load_optuna_test_settings,
    load_retained_evidence_phase,
    load_test_settings,
    retain_verification_evidence,
    settings_from_mapping,
    _validate_phase_policy_gates,
)


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("README.md", True),
        ("docs/research_agents/operations.md", True),
        ("tests/conftest.py", True),
        ("plans/mcp_trading_research_tools_plan.md", True),
        ("src/trader_research/optimization/service.py", False),
        ("pyproject.toml", False),
        ("env.template", False),
        ("examples/verification.py", False),
    ],
)
def test_verification_harness_change_surface_is_closed(
    path: str, allowed: bool
) -> None:
    assert _is_harness_path(path) is allowed


def test_test_database_contract_uses_only_prefixed_settings() -> None:
    legacy = {
        "PG_HOST": "operator-host",
        "PG_PORT": "5432",
        "PG_DB": "trader",
        "PG_USER": "trader",
        "PG_PASSWORD": "secret",
    }
    assert load_test_settings(legacy, required=False) is None
    with pytest.raises(VerificationConfigurationError, match="PG_TEST_HOST"):
        load_test_settings({**legacy, "TRADER_VERIFICATION_MODE": "true"})


@pytest.mark.parametrize(
    "database_name", ["trader", "trader_verification", "trader-test"]
)
def test_test_database_contract_rejects_unsafe_names(database_name: str) -> None:
    values = {
        "PG_TEST_HOST": "localhost",
        "PG_TEST_PORT": "5432",
        "PG_TEST_DB": database_name,
        "PG_TEST_USER": "trader_verification_runner",
        "PG_TEST_PASSWORD": "secret",
        "PG_OPERATOR_DB": "trader",
        "PG_OPERATOR_USER": "trader",
    }
    with pytest.raises(VerificationConfigurationError, match="PG_TEST_DB"):
        load_test_settings(values, required=True)


def test_test_database_contract_rejects_operator_identity() -> None:
    values = {
        "PG_TEST_HOST": "localhost",
        "PG_TEST_PORT": "5432",
        "PG_TEST_DB": "trader_test",
        "PG_TEST_USER": "trader",
        "PG_TEST_PASSWORD": "secret",
        "PG_OPERATOR_DB": "trader",
        "PG_OPERATOR_USER": "trader",
    }
    with pytest.raises(VerificationConfigurationError, match="PG_TEST_USER"):
        load_test_settings(values, required=True)


def test_phase_outcome_contract_requires_explicit_consistent_blockers() -> None:
    assert _validate_outcome("passed", ()) == "passed"
    assert _validate_outcome("blocked", ("strict test failed",)) == "blocked"
    with pytest.raises(VerificationConfigurationError, match="at least one blocker"):
        _validate_outcome("blocked", ())
    with pytest.raises(VerificationConfigurationError, match="cannot record blockers"):
        _validate_outcome("passed", ("contradiction",))


def test_retained_evidence_contract_is_explicitly_limited_to_qualified_phases() -> None:
    assert load_retained_evidence_phase({}) is None
    assert retain_verification_evidence({}) is False
    values = {RETAIN_EVIDENCE_PHASE_ENV: "57m"}
    assert load_retained_evidence_phase(values) == "57M"
    assert retain_verification_evidence(values) is True
    values = {RETAIN_EVIDENCE_PHASE_ENV: "57n"}
    assert load_retained_evidence_phase(values) == "57N"
    assert retain_verification_evidence(values) is True
    values = {RETAIN_EVIDENCE_PHASE_ENV: "57r"}
    assert load_retained_evidence_phase(values) == "57R"
    assert retain_verification_evidence(values) is True
    with pytest.raises(VerificationConfigurationError, match="may only retain"):
        load_retained_evidence_phase({RETAIN_EVIDENCE_PHASE_ENV: "57L"})


def test_57m_phase_policy_requires_only_backtest_and_optimization_gates() -> None:
    disabled = {name: False for name in MUTATION_GATE_NAMES}
    _validate_phase_policy_gates(None, disabled)
    enabled = {
        **disabled,
        "TRADER_MCP_ALLOW_BACKTESTS": True,
        "TRADER_MCP_ALLOW_OPTIMIZATION": True,
    }
    _validate_phase_policy_gates("57M", enabled)
    _validate_phase_policy_gates("57N", enabled)
    _validate_phase_policy_gates("57O", enabled)
    _validate_phase_policy_gates("57P", enabled)
    _validate_phase_policy_gates("57R", enabled)
    with pytest.raises(VerificationConfigurationError, match="requires exactly"):
        _validate_phase_policy_gates("57M", disabled)
    with pytest.raises(VerificationConfigurationError, match="requires exactly"):
        _validate_phase_policy_gates(
            "57M",
            {**enabled, "TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES": True},
        )


@pytest.mark.postgres
def test_verification_database_has_server_checked_marker_and_manifest(
    postgres_settings: dict[str, object],
) -> None:
    identity = assert_verification_database(postgres_settings)
    manifest = build_runtime_manifest(phase="57J")

    assert identity["database_name"] == postgres_settings["dbname"]
    assert identity["role_name"] == postgres_settings["user"]
    assert identity["timezone"] == "UTC"
    assert identity["lc_collate"] == os.environ["PG_TEST_LOCALE"]
    assert identity["lc_ctype"] == os.environ["PG_TEST_LOCALE"]
    assert manifest["database_identity"] == identity
    assert manifest["freeze"]["freeze_tag"] == "verification-57i-freeze-v5"
    assert manifest["test_database"]["dbname"] == postgres_settings["dbname"]
    assert manifest["phase"] == "57J"
    assert manifest["retained_evidence_phase"] is None
    assert all(manifest["policy_gates"][name] is False for name in MUTATION_GATE_NAMES)
    serialized = json.dumps(manifest, sort_keys=True).lower()
    assert "password" not in serialized
    assert os.environ["PG_TEST_PASSWORD"].lower() not in serialized

    settings = settings_from_mapping(postgres_settings)
    with psycopg.connect(settings.conninfo(), row_factory=dict_row) as connection:
        phase = connection.execute(
            "SELECT isolation_status, qualification_status, blockers, "
            "executed_harness_revision, verdict_revision, "
            "operator_before_digest, manifest "
            "FROM verification_control.phase_runs WHERE phase = '57J'"
        ).fetchone()
    assert phase is not None
    assert phase["isolation_status"] == "running"
    assert phase["qualification_status"] == "running"
    assert phase["blockers"] == []
    assert phase["executed_harness_revision"]
    assert phase["verdict_revision"] is None
    assert phase["operator_before_digest"]
    assert phase["manifest"]["configuration_digest"] == manifest["configuration_digest"]


@pytest.mark.postgres
def test_verification_roles_are_distinct_and_non_privileged(
    postgres_settings: dict[str, object],
) -> None:
    test = settings_from_mapping(postgres_settings)
    operator = load_operator_settings()
    optuna = load_optuna_test_settings()
    assert len({test.user, operator.user, optuna.user}) == 3
    assert test.dbname != operator.dbname
    assert test.dbname == optuna.dbname

    with psycopg.connect(operator.conninfo(), row_factory=dict_row) as connection:
        role_rows = connection.execute(
            "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole "
            "FROM pg_roles WHERE rolname = ANY(%s)",
            [[test.user, optuna.user]],
        ).fetchall()
        by_name = {row["rolname"]: row for row in role_rows}
        for role_name in (test.user, optuna.user):
            assert by_name[role_name]["rolsuper"] is False
            assert by_name[role_name]["rolcreatedb"] is False
            assert by_name[role_name]["rolcreaterole"] is False
        for role_name in (test.user, optuna.user):
            for table_name in ("runs", "knowledge_sources", "research_artifacts"):
                exists = connection.execute(
                    "SELECT to_regclass(%s) IS NOT NULL AS present",
                    [f"public.{table_name}"],
                ).fetchone()
                if not exists["present"]:
                    continue
                for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    allowed = connection.execute(
                        "SELECT has_table_privilege(%s, %s, %s) AS allowed",
                        [role_name, f"public.{table_name}", privilege],
                    ).fetchone()
                    assert allowed["allowed"] is False


@pytest.mark.postgres
def test_verification_optuna_schema_is_isolated(
    postgres_settings: dict[str, object],
) -> None:
    test = settings_from_mapping(postgres_settings)
    optuna = load_optuna_test_settings()
    schema_name = os.environ["TRADER_OPTUNA_SCHEMA"]
    with psycopg.connect(test.conninfo(), row_factory=dict_row) as connection:
        schema = connection.execute(
            "SELECT n.nspname, r.rolname AS owner "
            "FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner "
            "WHERE n.nspname = %s",
            [schema_name],
        ).fetchone()
        can_create = connection.execute(
            "SELECT has_schema_privilege(%s, %s, 'CREATE') AS allowed",
            [optuna.user, schema_name],
        ).fetchone()
        test_can_create = connection.execute(
            "SELECT has_schema_privilege(%s, %s, 'CREATE') AS allowed",
            [test.user, schema_name],
        ).fetchone()
    assert schema == {"nspname": schema_name, "owner": optuna.user}
    assert can_create["allowed"] is True
    assert test_can_create["allowed"] is False


@pytest.mark.postgres
def test_destructive_fixture_smoke_is_confined_to_verification_database(
    postgres_event_store: PostgresEventStore,
) -> None:
    connection = postgres_event_store.connection()
    connection.execute(
        "INSERT INTO config_kv (key, value) VALUES (%s, %s)",
        ["verification-57j-sentinel", "test-database-only"],
    )
    row = connection.execute(
        "SELECT value FROM config_kv WHERE key = %s", ["verification-57j-sentinel"]
    ).fetchone()
    marker = connection.execute(
        "SELECT freeze_revision FROM verification_control.runtime_marker "
        "WHERE marker_id = 'trader_verification'"
    ).fetchone()
    assert row == ("test-database-only",)
    assert marker is not None
