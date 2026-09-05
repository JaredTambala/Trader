"""Checkpoint-role isolation for the frozen orchestration qualification runtime.

Subject: Database and schema authority granted to the orchestration checkpoint role.
Level: Cross-package controlled qualification.
Collaborators: Product, checkpoint, and operator Postgres roles plus runtime manifest generation.
Guarantees: Checkpoints remain writable while canonical product tables remain protected.
Non-goals: Agent checkpoint semantics, workflow recovery, or live database administration.
"""

from __future__ import annotations

import json
import os

import psycopg
from psycopg.rows import dict_row
import pytest

from tests.cross_package.qualification.support.postgres_verification import (
    DEFAULT_CHECKPOINT_SCHEMA,
    ORCHESTRATION_VERIFICATION_PROFILE,
    VERIFICATION_PROFILE_ENV,
    build_runtime_manifest,
    load_checkpoint_test_settings,
    load_operator_settings,
    load_qualification_profile,
    load_test_settings,
)


@pytest.mark.postgres
def test_checkpoint_role_can_write_only_its_checkpoint_schema() -> None:
    """Prove checkpoint credentials cannot mutate canonical product tables."""
    if load_qualification_profile().name != ORCHESTRATION_VERIFICATION_PROFILE:
        pytest.skip(
            f"set {VERIFICATION_PROFILE_ENV}={ORCHESTRATION_VERIFICATION_PROFILE}"
        )
    product = load_test_settings(required=True)
    checkpoint = load_checkpoint_test_settings()
    operator = load_operator_settings()
    assert product is not None
    assert len({product.user, checkpoint.user, operator.user}) == 3
    assert product.dbname == checkpoint.dbname
    assert product.dbname != operator.dbname
    schema_name = os.environ.get(
        "TRADER_CHECKPOINT_SCHEMA", DEFAULT_CHECKPOINT_SCHEMA
    )
    manifest = build_runtime_manifest(phase="ORCHESTRATION_RUNTIME")
    assert manifest["qualification_profile"] == ORCHESTRATION_VERIFICATION_PROFILE
    assert manifest["checkpoint_database"] == checkpoint.public_dict()
    assert manifest["checkpoint_schema"] == schema_name
    serialized_manifest = json.dumps(manifest, sort_keys=True).lower()
    assert "password" not in serialized_manifest
    assert checkpoint.password.lower() not in serialized_manifest

    with psycopg.connect(product.conninfo(), row_factory=dict_row) as connection:
        schema = connection.execute(
            "SELECT n.nspname, r.rolname AS owner "
            "FROM pg_namespace AS n JOIN pg_roles AS r ON r.oid = n.nspowner "
            "WHERE n.nspname = %s",
            [schema_name],
        ).fetchone()
        can_create_checkpoint = connection.execute(
            "SELECT has_schema_privilege(%s, %s, 'CREATE') AS allowed",
            [checkpoint.user, schema_name],
        ).fetchone()
        can_create_public = connection.execute(
            "SELECT has_schema_privilege(%s, 'public', 'CREATE') AS allowed",
            [checkpoint.user],
        ).fetchone()
        assert schema == {"nspname": schema_name, "owner": checkpoint.user}
        assert can_create_checkpoint == {"allowed": True}
        assert can_create_public == {"allowed": False}

        for table_name in (
            "runs",
            "stock_bar_events",
            "research_artifacts",
            "research_workflow_plans",
            "research_workflow_outcomes",
        ):
            for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                allowed = connection.execute(
                    "SELECT has_table_privilege(%s, %s, %s) AS allowed",
                    [checkpoint.user, f"public.{table_name}", privilege],
                ).fetchone()
                assert allowed == {"allowed": False}
