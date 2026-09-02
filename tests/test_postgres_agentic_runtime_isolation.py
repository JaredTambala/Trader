"""Controlled runtime-isolation checks for model-backed agent qualification."""

from __future__ import annotations

from functools import partial
import json
import os
from pathlib import Path

import anyio
import psycopg
from psycopg.rows import dict_row
import pytest

from tests.support.postgres_verification import (
    AGENTIC_VERIFICATION_PROFILE,
    DEFAULT_CHECKPOINT_SCHEMA,
    VERIFICATION_PROFILE_ENV,
    build_runtime_manifest,
    load_checkpoint_test_settings,
    load_operator_settings,
    load_qualification_profile,
    load_test_settings,
)
from trader_agents.llm_client import (
    OllamaJsonLlmClient,
    build_llm_client_from_env,
)
from trader_agents.profiles import (
    development_model_profiles,
    profile_environment,
)


pytestmark = pytest.mark.postgres
_PHASE = "AGENTIC_RUNTIME_ISOLATION"
_RETIRED_AGENT_SURFACES = (
    Path("src/trader_agents/quant_research.py"),
    Path("src/trader_agents/state.py"),
)


def test_agentic_checkpoint_role_can_write_only_its_isolated_schema() -> None:
    """Prove checkpoint credentials cannot mutate canonical product tables."""
    _require_agentic_profile()
    product = load_test_settings(required=True)
    checkpoint = load_checkpoint_test_settings()
    operator = load_operator_settings()
    assert product is not None
    assert len({product.user, checkpoint.user, operator.user}) == 3
    assert product.dbname == checkpoint.dbname
    assert product.dbname != operator.dbname
    schema_name = os.environ.get(
        "TRADER_CHECKPOINT_SCHEMA",
        DEFAULT_CHECKPOINT_SCHEMA,
    )

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
            "stock_bar_events",
            "crypto_bar_events",
            "research_artifacts",
            "research_agent_sessions",
            "research_agent_decision_receipts",
        ):
            for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                allowed = connection.execute(
                    "SELECT has_table_privilege(%s, %s, %s) AS allowed",
                    [checkpoint.user, f"public.{table_name}", privilege],
                ).fetchone()
                assert allowed == {"allowed": False}


def test_agentic_runtime_identity_matches_served_model_and_clean_cutover() -> None:
    """Verify exact public identity, served model bytes, and retired surfaces."""
    _require_agentic_profile()
    manifest = build_runtime_manifest(phase=_PHASE)
    identity = manifest["agentic_identity"]
    profile = development_model_profiles().get(
        str(identity["selected_model_profile_id"])
    )
    client = build_llm_client_from_env({**os.environ, **profile_environment(profile)})
    assert isinstance(client, OllamaJsonLlmClient)
    anyio.run(partial(client.verify_model_identity, profile.model))

    assert manifest["qualification_profile"] == AGENTIC_VERIFICATION_PROFILE
    assert manifest["checkpoint_schema"] == os.environ.get(
        "TRADER_CHECKPOINT_SCHEMA",
        DEFAULT_CHECKPOINT_SCHEMA,
    )
    assert identity["runtime"]["model_profiles"]["profiles"] == [profile.to_dict()]
    assert len(str(identity["identity_digest"])) == 64
    assert [str(path) for path in _RETIRED_AGENT_SURFACES if path.exists()] == []
    serialized = json.dumps(manifest, sort_keys=True).lower()
    assert "password" not in serialized
    for settings in (
        load_test_settings(required=True),
        load_checkpoint_test_settings(),
        load_operator_settings(),
    ):
        assert settings is not None
        assert settings.password.lower() not in serialized


def _require_agentic_profile() -> None:
    """Skip outside the explicit controlled agentic profile."""
    if load_qualification_profile().name != AGENTIC_VERIFICATION_PROFILE:
        pytest.skip(f"set {VERIFICATION_PROFILE_ENV}={AGENTIC_VERIFICATION_PROFILE}")
