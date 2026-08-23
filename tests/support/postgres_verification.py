"""Controlled Postgres verification runtime and operator-isolation helpers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_VERIFICATION_PROFILE = "controlled_optimization_v6"
ORCHESTRATION_VERIFICATION_PROFILE = "controlled_orchestration_v1"
VERIFICATION_PROFILE_ENV = "TRADER_VERIFICATION_PROFILE"
FREEZE_TAG = "verification-57i-freeze-v6"
ORCHESTRATION_FREEZE_TAG = "verification-orchestration-v1-freeze"
VERIFICATION_MARKER_ID = "trader_verification"
VERIFICATION_SCHEMA = "verification_control"
DEFAULT_CHECKPOINT_SCHEMA = "orchestration_checkpoint"
TEST_DATABASE_SUFFIXES = ("_test", "_testing")
VERIFICATION_MODE_ENV = "TRADER_VERIFICATION_MODE"
RETAIN_EVIDENCE_PHASE_ENV = "TRADER_VERIFICATION_RETAIN_PHASE"
MUTATION_GATE_NAMES = (
    "TRADER_MCP_ALLOW_BROKER_MUTATION",
    "TRADER_MCP_ALLOW_RAW_SQL",
    "TRADER_MCP_ALLOW_DATA_LOADING",
    "TRADER_MCP_ALLOW_BACKTESTS",
    "TRADER_MCP_ALLOW_OPTIMIZATION",
    "TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES",
    "TRADER_MCP_ALLOW_OPTUNA_WRITES",
    "TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES",
)
_PHASE_ENABLED_MUTATION_GATES = {
    "57O": frozenset(
        {
            "TRADER_MCP_ALLOW_BACKTESTS",
            "TRADER_MCP_ALLOW_OPTIMIZATION",
        }
    ),
    "57P": frozenset(
        {
            "TRADER_MCP_ALLOW_BACKTESTS",
            "TRADER_MCP_ALLOW_OPTIMIZATION",
        }
    ),
    "57M": frozenset(
        {
            "TRADER_MCP_ALLOW_BACKTESTS",
            "TRADER_MCP_ALLOW_OPTIMIZATION",
        }
    ),
    "57N": frozenset(
        {
            "TRADER_MCP_ALLOW_BACKTESTS",
            "TRADER_MCP_ALLOW_OPTIMIZATION",
        }
    ),
    "57R": frozenset(
        {
            "TRADER_MCP_ALLOW_BACKTESTS",
            "TRADER_MCP_ALLOW_OPTIMIZATION",
        }
    ),
}
_RETAINABLE_EVIDENCE_PHASES = frozenset({"57M", "57N", "57R"})


@dataclass(frozen=True)
class QualificationProfile:
    """Code-owned contract for one controlled qualification campaign.

    Attributes:
        name: Stable profile identifier recorded with evidence.
        freeze_tag: Immutable Git tag containing the product under test.
        phases: Closed set of accepted evidence record keys.
        enabled_mutation_gates: Exact enabled mutation gates for each phase.
        retainable_phases: Phases whose disposable evidence may survive teardown.
        requires_checkpoint_role: Whether an isolated checkpoint role is mandatory.
    """

    name: str
    freeze_tag: str
    phases: frozenset[str]
    enabled_mutation_gates: Mapping[str, frozenset[str]]
    retainable_phases: frozenset[str]
    requires_checkpoint_role: bool = False


_LEGACY_PROFILE = QualificationProfile(
    name=LEGACY_VERIFICATION_PROFILE,
    freeze_tag=FREEZE_TAG,
    phases=frozenset(f"57{letter}" for letter in "ABCDEFGHIJKLMNOPQRS"),
    enabled_mutation_gates=_PHASE_ENABLED_MUTATION_GATES,
    retainable_phases=_RETAINABLE_EVIDENCE_PHASES,
)
_ORCHESTRATION_PHASES = frozenset(
    {
        "ORCHESTRATION_RUNTIME",
        "ORCHESTRATION_CORE",
        "ORCHESTRATION_E2E",
        "ORCHESTRATION_RECOVERY",
        "ORCHESTRATION_POLICY",
        "ORCHESTRATION_SCALE",
        "ORCHESTRATION_ACCEPTANCE",
    }
)
_ORCHESTRATION_EXECUTION_GATES = frozenset(
    {
        "TRADER_MCP_ALLOW_BACKTESTS",
        "TRADER_MCP_ALLOW_OPTIMIZATION",
    }
)
_ORCHESTRATION_PROFILE = QualificationProfile(
    name=ORCHESTRATION_VERIFICATION_PROFILE,
    freeze_tag=ORCHESTRATION_FREEZE_TAG,
    phases=_ORCHESTRATION_PHASES,
    enabled_mutation_gates={
        "ORCHESTRATION_E2E": _ORCHESTRATION_EXECUTION_GATES,
        "ORCHESTRATION_RECOVERY": frozenset({"TRADER_MCP_ALLOW_BACKTESTS"}),
        "ORCHESTRATION_SCALE": frozenset({"TRADER_MCP_ALLOW_BACKTESTS"}),
    },
    retainable_phases=frozenset(
        {
            "ORCHESTRATION_E2E",
            "ORCHESTRATION_RECOVERY",
            "ORCHESTRATION_SCALE",
        }
    ),
    requires_checkpoint_role=True,
)
_QUALIFICATION_PROFILES = {
    profile.name: profile for profile in (_LEGACY_PROFILE, _ORCHESTRATION_PROFILE)
}

RUNTIME_TABLES = (
    "runs",
    "trading_sessions",
    "run_events",
    "stock_bar_events",
    "crypto_bar_events",
    "signal_events",
    "indicator_events",
    "order_events",
    "fill_events",
    "position_snapshots",
    "config_kv",
    "metrics_snapshots",
    "experiments",
    "experiment_runs",
)
KNOWLEDGE_TABLES = (
    "knowledge_sources",
    "knowledge_chunks",
    "knowledge_embedding_indexes",
    "knowledge_embeddings",
    "knowledge_ingestion_runs",
    "knowledge_method_card_sets",
    "knowledge_method_cards",
    "knowledge_method_contracts",
)
RESEARCH_TABLES = (
    "research_artifacts",
    "research_ml_deployments",
    "research_ml_deployment_validations",
    "research_implementation_versions",
    "research_implementation_validations",
    "research_strategy_specifications",
    "research_strategy_specification_validations",
    "research_risk_stack_specifications",
    "research_risk_stack_specification_validations",
    "research_backtest_specifications",
    "research_backtest_specification_validations",
    "research_backtest_runs",
    "research_parameter_optimization_plans",
    "research_parameter_optimization_runs",
    "research_parameter_optimization_trials",
    "research_experiment_tracking_projections",
    "research_parameter_optimization_evaluations",
    "research_parameter_optimization_audit_plans",
    "research_parameter_optimization_robustness_reports",
    "research_methodology_candidates",
    "research_methodology_field_extractions",
    "research_methodology_evidence_packets",
    "research_methodology_validations",
)

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_PRODUCT_PATHS = ("src", "pyproject.toml", "uv.lock", "env.template")
_HARNESS_PATH_PREFIXES = ("docs/", "tests/")
_HARNESS_PATHS = (
    "README.md",
    "plans/mcp_trading_research_tools_plan.md",
    "plans/research_capability_roadmap.md",
)
_KNOWLEDGE_FINGERPRINT_EXPRESSIONS = {
    "knowledge_sources": (
        "jsonb_build_object('source_id', t.source_id, 'file_hash', t.file_hash, "
        "'status', t.status, 'schema_version', t.schema_version)"
    ),
    "knowledge_chunks": (
        "jsonb_build_object('chunk_id', t.chunk_id, 'source_id', t.source_id, "
        "'ordinal', t.ordinal, 'text_hash', t.text_hash, 'active', t.active, "
        "'chunker_version', t.chunker_version, 'schema_version', t.schema_version)"
    ),
    "knowledge_embedding_indexes": (
        "jsonb_build_object('embedding_manifest_id', t.embedding_manifest_id, "
        "'provider', t.provider, 'model', t.model, 'version', t.version, "
        "'dimension', t.dimension, 'chunk_ids', t.chunk_ids)"
    ),
    "knowledge_embeddings": (
        "jsonb_build_object('embedding_manifest_id', t.embedding_manifest_id, "
        "'chunk_id', t.chunk_id, 'provider', t.provider, 'model', t.model, "
        "'version', t.version, 'dimension', t.dimension)"
    ),
    "knowledge_ingestion_runs": (
        "jsonb_build_object('ingestion_id', t.ingestion_id, 'source_ids', t.source_ids, "
        "'status', t.status, 'chunks_created', t.chunks_created, "
        "'chunks_indexed', t.chunks_indexed, 'embedding_manifest_id', t.embedding_manifest_id)"
    ),
    "knowledge_method_card_sets": (
        "jsonb_build_object('method_card_set_id', t.method_card_set_id, 'method_id', t.method_id, "
        "'status', t.status, 'current_approved_method_card_id', "
        "t.current_approved_method_card_id, 'current_draft_method_card_id', "
        "t.current_draft_method_card_id, 'revision_count', t.revision_count)"
    ),
    "knowledge_method_cards": (
        "jsonb_build_object('method_card_id', t.method_card_id, "
        "'method_card_set_id', t.method_card_set_id, 'method_id', t.method_id, "
        "'status', t.status, 'card_format', t.card_format, "
        "'revision_number', t.revision_number)"
    ),
    "knowledge_method_contracts": (
        "jsonb_build_object('method_id', t.method_id, 'family', t.family, 'status', t.status)"
    ),
}


class VerificationConfigurationError(RuntimeError):
    """Raised when the verification runtime is unsafe or incomplete."""


@dataclass(frozen=True)
class PostgresConnectionSettings:
    """Normalized connection settings that never serialize their password."""

    host: str
    port: int
    dbname: str
    user: str
    password: str

    def connect_kwargs(self) -> dict[str, object]:
        """Return psycopg-compatible connection keyword arguments."""
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
        }

    def conninfo(self) -> str:
        """Return an escaped psycopg connection string."""
        return make_conninfo(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
        )

    def public_dict(self) -> dict[str, object]:
        """Return credential-free settings for manifests and diagnostics."""
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
        }


def verification_mode_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether strict controlled-verification behavior is enabled."""
    values = os.environ if environ is None else environ
    return _parse_bool(
        values.get(VERIFICATION_MODE_ENV, "false"), VERIFICATION_MODE_ENV
    )


def load_qualification_profile(
    environ: Mapping[str, str] | None = None,
) -> QualificationProfile:
    """Return the selected closed qualification profile.

    The historical optimisation profile remains the default so existing controlled
    runbooks do not silently change behavior. New campaigns must opt in explicitly.

    Args:
        environ: Optional environment mapping used instead of ``os.environ``.

    Returns:
        The immutable code-owned qualification profile.

    Raises:
        VerificationConfigurationError: If the requested profile is unknown.
    """
    values = os.environ if environ is None else environ
    name = (
        str(values.get(VERIFICATION_PROFILE_ENV) or "").strip()
        or LEGACY_VERIFICATION_PROFILE
    )
    profile = _QUALIFICATION_PROFILES.get(name)
    if profile is None:
        raise VerificationConfigurationError(
            f"{VERIFICATION_PROFILE_ENV} must be one of "
            f"{sorted(_QUALIFICATION_PROFILES)}."
        )
    return profile


def load_test_settings(
    environ: Mapping[str, str] | None = None,
    *,
    required: bool | None = None,
) -> PostgresConnectionSettings | None:
    """Load the test-only Postgres contract without legacy variable fallback."""
    values = os.environ if environ is None else environ
    must_exist = verification_mode_enabled(values) if required is None else required
    settings = _load_prefixed_settings("PG_TEST", values, required=must_exist)
    if settings is None:
        return None
    _validate_test_identity(settings, values)
    return settings


def load_operator_settings(
    environ: Mapping[str, str] | None = None,
) -> PostgresConnectionSettings:
    """Load explicit operator settings used only for read-only fingerprints."""
    values = os.environ if environ is None else environ
    settings = _load_prefixed_settings("PG_OPERATOR", values, required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise VerificationConfigurationError("PG_OPERATOR settings are required.")
    return settings


def load_optuna_test_settings(
    environ: Mapping[str, str] | None = None,
) -> PostgresConnectionSettings:
    """Load the isolated optional-provider role settings."""
    values = os.environ if environ is None else environ
    settings = _load_prefixed_settings("PG_OPTUNA_TEST", values, required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise VerificationConfigurationError("PG_OPTUNA_TEST settings are required.")
    return settings


def load_checkpoint_test_settings(
    environ: Mapping[str, str] | None = None,
) -> PostgresConnectionSettings:
    """Load the isolated orchestration-checkpoint role settings.

    Args:
        environ: Optional environment mapping used instead of ``os.environ``.

    Returns:
        Normalized settings for the checkpoint-only role.

    Raises:
        VerificationConfigurationError: If settings are incomplete or do not target
            the configured disposable product-test database.
    """
    values = os.environ if environ is None else environ
    settings = _load_prefixed_settings("PG_CHECKPOINT_TEST", values, required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise VerificationConfigurationError(
            "PG_CHECKPOINT_TEST settings are required."
        )
    test = _load_prefixed_settings("PG_TEST", values, required=True)
    if test is None:  # pragma: no cover - required=True fails first
        raise VerificationConfigurationError("PG_TEST settings are required.")
    _assert_role_targets_test_database(
        test,
        settings,
        role_prefix="PG_CHECKPOINT_TEST",
    )
    _validate_identifier(settings.user, "PG_CHECKPOINT_TEST_USER")
    if settings.user == test.user:
        raise VerificationConfigurationError(
            "PG_CHECKPOINT_TEST_USER must differ from PG_TEST_USER."
        )
    return settings


def checkpoint_test_conninfo(
    environ: Mapping[str, str] | None = None,
) -> str:
    """Return checkpoint-role conninfo pinned to its isolated schema.

    Args:
        environ: Optional environment mapping used instead of ``os.environ``.

    Returns:
        Escaped libpq conninfo suitable for the LangGraph Postgres saver.

    Raises:
        VerificationConfigurationError: If checkpoint settings or the schema name
            are incomplete or unsafe.
    """
    values = os.environ if environ is None else environ
    settings = load_checkpoint_test_settings(values)
    schema = str(
        values.get("TRADER_CHECKPOINT_SCHEMA", DEFAULT_CHECKPOINT_SCHEMA)
    ).strip()
    _validate_identifier(schema, "TRADER_CHECKPOINT_SCHEMA")
    return make_conninfo(
        **settings.connect_kwargs(),
        options=f"-csearch_path={schema}",
    )


def settings_from_mapping(settings: Mapping[str, object]) -> PostgresConnectionSettings:
    """Normalize fixture mapping values into connection settings."""
    return PostgresConnectionSettings(
        host=str(settings["host"]),
        port=int(str(settings["port"])),
        dbname=str(settings["dbname"]),
        user=str(settings["user"]),
        password=str(settings["password"]),
    )


def resolve_freeze_revision(
    profile: QualificationProfile | None = None,
) -> str:
    """Resolve the selected profile's immutable freeze tag to its commit SHA."""
    selected = profile or load_qualification_profile()
    return _git("rev-parse", f"{selected.freeze_tag}^{{}}")


def assert_frozen_product() -> Mapping[str, str]:
    """Require a clean harness revision with frozen product bytes unchanged."""
    profile = load_qualification_profile()
    freeze_revision = resolve_freeze_revision(profile)
    harness_revision = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=all", allow_empty=True)
    if status:
        raise VerificationConfigurationError(
            "Verification requires a clean Git worktree."
        )
    _run_git("merge-base", "--is-ancestor", freeze_revision, harness_revision)
    changed_paths = _git(
        "diff", "--name-only", freeze_revision, harness_revision, allow_empty=True
    ).splitlines()
    invalid_paths = [path for path in changed_paths if not _is_harness_path(path)]
    if invalid_paths:
        raise VerificationConfigurationError(
            f"Verification harness contains changes outside tests/docs/tracker: {invalid_paths}"
        )
    result = subprocess.run(
        ["git", "diff", "--quiet", freeze_revision, "--", *_PRODUCT_PATHS],
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise VerificationConfigurationError(
            f"Product paths differ from {profile.freeze_tag}; create a new freeze "
            "instead of waiving product drift."
        )
    return {
        "qualification_profile": profile.name,
        "freeze_tag": profile.freeze_tag,
        "freeze_revision": freeze_revision,
        "harness_revision": harness_revision,
    }


def assert_verification_database(
    settings: PostgresConnectionSettings | Mapping[str, object],
    *,
    freeze_revision: str | None = None,
) -> Mapping[str, str]:
    """Verify server identity, marker, role, and timezone before destructive tests."""
    normalized = (
        settings_from_mapping(settings) if isinstance(settings, Mapping) else settings
    )
    _validate_test_identity(normalized, os.environ)
    expected_freeze = freeze_revision or resolve_freeze_revision()
    try:
        with psycopg.connect(normalized.conninfo(), row_factory=dict_row) as connection:
            return assert_connection_targets_verification_database(
                connection,
                normalized,
                freeze_revision=expected_freeze,
            )
    except psycopg.Error as exc:
        raise VerificationConfigurationError(
            f"Could not validate verification database {normalized.dbname!r}: {exc}"
        ) from exc


def assert_connection_targets_verification_database(
    connection: psycopg.Connection[Any],
    settings: PostgresConnectionSettings | Mapping[str, object],
    *,
    freeze_revision: str | None = None,
) -> Mapping[str, str]:
    """Recheck a live connection immediately before destructive SQL."""
    normalized = (
        settings_from_mapping(settings) if isinstance(settings, Mapping) else settings
    )
    expected_freeze = freeze_revision or resolve_freeze_revision()
    identity = connection.execute(
        "SELECT current_database() AS database_name, current_user AS role_name, "
        "current_setting('TimeZone') AS timezone, d.datcollate AS lc_collate, "
        "d.datctype AS lc_ctype FROM pg_database AS d "
        "WHERE d.datname = current_database()"
    ).fetchone()
    database_name, role_name, timezone_name, lc_collate, lc_ctype = _row_values(
        identity, "database_name", "role_name", "timezone", "lc_collate", "lc_ctype"
    )
    if database_name != normalized.dbname:
        raise VerificationConfigurationError(
            f"Server database {database_name!r} does not match PG_TEST_DB {normalized.dbname!r}."
        )
    if role_name != normalized.user:
        raise VerificationConfigurationError(
            f"Server role {role_name!r} does not match PG_TEST_USER {normalized.user!r}."
        )
    if str(timezone_name).upper() != "UTC":
        raise VerificationConfigurationError(
            f"Verification database timezone must be UTC, got {timezone_name!r}."
        )
    marker = connection.execute(
        "SELECT database_name, freeze_revision, locale_name "
        "FROM verification_control.runtime_marker "
        "WHERE marker_id = %s",
        [VERIFICATION_MARKER_ID],
    ).fetchone()
    if marker is None:
        raise VerificationConfigurationError("Verification database marker is missing.")
    marker_database, marker_freeze, marker_locale = _row_values(
        marker, "database_name", "freeze_revision", "locale_name"
    )
    if marker_database != normalized.dbname:
        raise VerificationConfigurationError(
            "Verification marker database identity does not match."
        )
    if marker_freeze != expected_freeze:
        profile = load_qualification_profile()
        raise VerificationConfigurationError(
            "Verification marker freeze revision does not match "
            f"{profile.freeze_tag}."
        )
    if lc_collate != marker_locale or lc_ctype != marker_locale:
        raise VerificationConfigurationError(
            "Verification database collation does not match its pinned runtime marker."
        )
    return {
        "database_name": str(database_name),
        "role_name": str(role_name),
        "timezone": str(timezone_name),
        "lc_collate": str(lc_collate),
        "lc_ctype": str(lc_ctype),
        "freeze_revision": str(marker_freeze),
    }


def build_runtime_manifest(*, phase: str | None = None) -> Mapping[str, Any]:
    """Build a credential-free manifest for the current verification harness."""
    profile = load_qualification_profile()
    if phase is not None:
        _validate_phase(phase)
    revisions = assert_frozen_product()
    test_settings = load_test_settings(required=True)
    if test_settings is None:  # pragma: no cover - required=True fails first
        raise VerificationConfigurationError("PG_TEST settings are required.")
    operator_settings = _load_prefixed_settings(
        "PG_OPERATOR", os.environ, required=True
    )
    optuna_settings = _load_prefixed_settings(
        "PG_OPTUNA_TEST", os.environ, required=True
    )
    if operator_settings is None or optuna_settings is None:  # pragma: no cover
        raise VerificationConfigurationError(
            "Operator and Optuna settings are required."
        )
    role_names = {test_settings.user, operator_settings.user, optuna_settings.user}
    checkpoint_settings = None
    if profile.requires_checkpoint_role:
        checkpoint_settings = load_checkpoint_test_settings()
        role_names.add(checkpoint_settings.user)
    expected_role_count = 4 if profile.requires_checkpoint_role else 3
    if len(role_names) != expected_role_count:
        raise VerificationConfigurationError(
            "Product-test, operator, optional-provider, and required checkpoint "
            "roles must be distinct."
        )
    _assert_optuna_targets_test_database(test_settings, optuna_settings)
    identity = assert_verification_database(
        test_settings, freeze_revision=revisions["freeze_revision"]
    )
    gates = {
        name: _parse_bool(os.environ.get(name, "false"), name)
        for name in MUTATION_GATE_NAMES
    }
    _validate_phase_policy_gates(phase, gates)
    retained_evidence_phase = load_retained_evidence_phase()
    if retained_evidence_phase is not None and retained_evidence_phase != phase:
        raise VerificationConfigurationError(
            f"{RETAIN_EVIDENCE_PHASE_ENV} must match the active controlled phase."
        )
    with psycopg.connect(test_settings.conninfo(), row_factory=dict_row) as connection:
        server = connection.execute(
            "SELECT current_setting('server_version') AS server_version"
        ).fetchone()
    (server_version,) = _row_values(server, "server_version")
    manifest = {
        "qualification_profile": profile.name,
        "phase": phase,
        "freeze": dict(revisions),
        "dependency_lock_sha256": _sha256_file(REPO_ROOT / "uv.lock"),
        "python_version": sys.version.split()[0],
        "postgres": {
            "server_version": server_version,
            "timezone": identity["timezone"],
            "lc_collate": identity["lc_collate"],
            "lc_ctype": identity["lc_ctype"],
        },
        "test_database": test_settings.public_dict(),
        "operator_database": operator_settings.public_dict(),
        "optuna_database": optuna_settings.public_dict(),
        "optuna_schema": os.environ.get(
            "TRADER_OPTUNA_SCHEMA", "trader_optuna_verification"
        ),
        "optuna_study_prefix": os.environ.get(
            "TRADER_OPTUNA_STUDY_PREFIX", "trader-verification-09b0b5e"
        ),
        "tracking_experiment": os.environ.get(
            "TRADER_MLFLOW_OPTIMIZATION_EXPERIMENT",
            "trader-verification-09b0b5e",
        ),
        "policy_gates": gates,
        "retained_evidence_phase": retained_evidence_phase,
        "database_identity": dict(identity),
        "python_hash_seed": os.environ.get("PYTHONHASHSEED", ""),
        "process_timezone": os.environ.get("TZ", ""),
    }
    if checkpoint_settings is not None:
        checkpoint_schema = os.environ.get(
            "TRADER_CHECKPOINT_SCHEMA", DEFAULT_CHECKPOINT_SCHEMA
        )
        _validate_identifier(checkpoint_schema, "TRADER_CHECKPOINT_SCHEMA")
        manifest["checkpoint_database"] = checkpoint_settings.public_dict()
        manifest["checkpoint_schema"] = checkpoint_schema
    manifest["configuration_digest"] = _stable_digest(manifest)
    return manifest


def provision_verification_runtime(*, reset: bool) -> Mapping[str, Any]:
    """Provision isolated roles, database, schemas, and verification control tables."""
    profile = load_qualification_profile()
    revisions = assert_frozen_product()
    admin = _required_settings("PG_ADMIN")
    operator = _required_settings("PG_OPERATOR")
    test = _required_settings("PG_TEST")
    optuna = _required_settings("PG_OPTUNA_TEST")
    locale_name = _required_environment_value("PG_TEST_LOCALE")
    _validate_test_identity(test, os.environ)
    _validate_identifier(optuna.user, "PG_OPTUNA_TEST_USER")
    _assert_optuna_targets_test_database(test, optuna)
    checkpoint = (
        load_checkpoint_test_settings() if profile.requires_checkpoint_role else None
    )
    schema_name = os.environ.get("TRADER_OPTUNA_SCHEMA", "trader_optuna_verification")
    _validate_identifier(schema_name, "TRADER_OPTUNA_SCHEMA")
    checkpoint_schema = os.environ.get(
        "TRADER_CHECKPOINT_SCHEMA", DEFAULT_CHECKPOINT_SCHEMA
    )
    _validate_identifier(checkpoint_schema, "TRADER_CHECKPOINT_SCHEMA")
    if test.dbname in {admin.dbname, operator.dbname}:
        raise VerificationConfigurationError(
            "PG_TEST_DB must differ from both PG_ADMIN_DB and PG_OPERATOR_DB."
        )
    isolated_roles = {operator.user, test.user, optuna.user}
    if checkpoint is not None:
        isolated_roles.add(checkpoint.user)
    expected_isolated_roles = 4 if checkpoint is not None else 3
    if len(isolated_roles) != expected_isolated_roles:
        raise VerificationConfigurationError(
            "Verification product, operator, optional-provider, and checkpoint roles "
            "must be isolated."
        )
    freeze_revision = revisions["freeze_revision"]

    with psycopg.connect(admin.conninfo(), autocommit=True) as connection:
        _ensure_role(connection, test)
        _ensure_role(connection, optuna)
        if checkpoint is not None:
            _ensure_role(connection, checkpoint)
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", [test.dbname]
        ).fetchone()
        if exists and reset:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                [test.dbname],
            )
            connection.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(test.dbname))
            )
            exists = None
        if not exists:
            connection.execute(
                sql.SQL(
                    "CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8' "
                    "LC_COLLATE {} LC_CTYPE {}"
                ).format(
                    sql.Identifier(test.dbname),
                    sql.Identifier(test.user),
                    sql.Literal(locale_name),
                    sql.Literal(locale_name),
                )
            )
        database = connection.execute(
            "SELECT pg_get_userbyid(datdba), datcollate, datctype "
            "FROM pg_database WHERE datname = %s",
            [test.dbname],
        ).fetchone()
        if database is None or database[0] != test.user:
            raise VerificationConfigurationError(
                f"Verification database must be owned by {test.user!r}."
            )
        if database[1:] != (locale_name, locale_name):
            raise VerificationConfigurationError(
                "Verification database locale does not match PG_TEST_LOCALE."
            )
        connection.execute(
            sql.SQL("ALTER DATABASE {} SET timezone TO 'UTC'").format(
                sql.Identifier(test.dbname)
            )
        )
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(test.dbname), sql.Identifier(optuna.user)
            )
        )
        if checkpoint is not None:
            connection.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(test.dbname), sql.Identifier(checkpoint.user)
                )
            )

    admin_test = PostgresConnectionSettings(
        host=admin.host,
        port=admin.port,
        dbname=test.dbname,
        user=admin.user,
        password=admin.password,
    )
    with psycopg.connect(admin_test.conninfo(), autocommit=True) as connection:
        current = connection.execute("SELECT current_database()").fetchone()
        if current is None or current[0] != test.dbname:
            raise VerificationConfigurationError(
                "Admin connection did not reach PG_TEST_DB."
            )
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute(
            sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
                sql.Identifier(test.user)
            )
        )
        connection.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(
                sql.Identifier(schema_name), sql.Identifier(optuna.user)
            )
        )
        connection.execute(
            sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(
                sql.Identifier(schema_name)
            )
        )
        connection.execute(
            sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {}").format(
                sql.Identifier(schema_name), sql.Identifier(optuna.user)
            )
        )
        if checkpoint is not None:
            connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(
                    sql.Identifier(checkpoint_schema), sql.Identifier(checkpoint.user)
                )
            )
            checkpoint_owner = connection.execute(
                "SELECT r.rolname FROM pg_namespace AS n "
                "JOIN pg_roles AS r ON r.oid = n.nspowner WHERE n.nspname = %s",
                [checkpoint_schema],
            ).fetchone()
            if checkpoint_owner is None or checkpoint_owner[0] != checkpoint.user:
                raise VerificationConfigurationError(
                    "checkpoint schema must be owned by PG_CHECKPOINT_TEST_USER; "
                    "run provision --reset"
                )
            connection.execute(
                sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(
                    sql.Identifier(checkpoint_schema)
                )
            )
            connection.execute(
                sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {}").format(
                    sql.Identifier(checkpoint_schema), sql.Identifier(checkpoint.user)
                )
            )
            connection.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(checkpoint_schema), sql.Identifier(test.user)
                )
            )
            connection.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
                    "GRANT SELECT ON TABLES TO {}"
                ).format(
                    sql.Identifier(checkpoint.user),
                    sql.Identifier(checkpoint_schema),
                    sql.Identifier(test.user),
                )
            )

    _initialize_product_schemas(test)
    with psycopg.connect(test.conninfo(), autocommit=True) as connection:
        current = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if current != (test.dbname, test.user):
            raise VerificationConfigurationError(
                "Test-role connection identity mismatch."
            )
        _ensure_control_schema(connection)
        connection.execute(
            """
            INSERT INTO verification_control.runtime_marker (
                marker_id, database_name, role_name, freeze_revision, locale_name
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (marker_id) DO UPDATE SET
                database_name = EXCLUDED.database_name,
                role_name = EXCLUDED.role_name,
                freeze_revision = EXCLUDED.freeze_revision,
                locale_name = EXCLUDED.locale_name,
                updated_at = now()
            """,
            [
                VERIFICATION_MARKER_ID,
                test.dbname,
                test.user,
                freeze_revision,
                locale_name,
            ],
        )
    identity = assert_verification_database(test, freeze_revision=freeze_revision)
    result = {
        "status": "provisioned",
        "qualification_profile": profile.name,
        "database": identity["database_name"],
        "role": identity["role_name"],
        "freeze_revision": freeze_revision,
        "optuna_schema": schema_name,
        "optuna_role": optuna.user,
    }
    if checkpoint is not None:
        result["checkpoint_schema"] = checkpoint_schema
        result["checkpoint_role"] = checkpoint.user
    return result


def begin_phase(phase: str) -> Mapping[str, Any]:
    """Capture the runtime manifest and operator fingerprint before a phase."""
    _validate_phase(phase)
    manifest = build_runtime_manifest(phase=phase)
    fingerprint = fingerprint_operator_database()
    test = _required_settings("PG_TEST")
    freeze_revision = str(manifest["freeze"]["freeze_revision"])
    with psycopg.connect(test.conninfo(), autocommit=True) as connection:
        assert_connection_targets_verification_database(
            connection, test, freeze_revision=freeze_revision
        )
        connection.execute(
            """
            INSERT INTO verification_control.phase_runs (
                phase, freeze_revision, executed_harness_revision, verdict_revision,
                isolation_status, qualification_status, blockers, manifest,
                operator_before_digest, operator_after_digest, started_at, finished_at
            ) VALUES (%s, %s, %s, NULL, 'running', 'running', '[]'::jsonb, %s, %s, NULL, now(), NULL)
            ON CONFLICT (phase, freeze_revision) DO UPDATE SET
                executed_harness_revision = EXCLUDED.executed_harness_revision,
                verdict_revision = NULL,
                isolation_status = 'running',
                qualification_status = 'running',
                blockers = '[]'::jsonb,
                manifest = EXCLUDED.manifest,
                operator_before_digest = EXCLUDED.operator_before_digest,
                operator_after_digest = NULL,
                started_at = now(),
                finished_at = NULL
            """,
            [
                phase,
                freeze_revision,
                manifest["freeze"]["harness_revision"],
                Jsonb(manifest),
                fingerprint["digest"],
            ],
        )
        connection.execute(
            "DELETE FROM verification_control.operator_fingerprints "
            "WHERE phase = %s AND freeze_revision = %s AND stage = 'after'",
            [phase, freeze_revision],
        )
        _save_fingerprint(connection, phase, freeze_revision, "before", fingerprint)
    return {
        "phase": phase,
        "stage": "before",
        "freeze_revision": freeze_revision,
        "harness_revision": manifest["freeze"]["harness_revision"],
        "operator_fingerprint": fingerprint["digest"],
        "configuration_digest": manifest["configuration_digest"],
    }


def end_phase(
    phase: str,
    *,
    outcome: str,
    blockers: Sequence[str] = (),
) -> Mapping[str, Any]:
    """Record a qualification verdict and verify operator isolation."""
    _validate_phase(phase)
    normalized_outcome = _validate_outcome(outcome, blockers)
    normalized_blockers = _normalize_blockers(blockers)
    revisions = assert_frozen_product()
    current_manifest = build_runtime_manifest(phase=phase)
    test = _required_settings("PG_TEST")
    after = fingerprint_operator_database()
    with psycopg.connect(
        test.conninfo(), autocommit=True, row_factory=dict_row
    ) as connection:
        assert_connection_targets_verification_database(
            connection, test, freeze_revision=revisions["freeze_revision"]
        )
        phase_run = connection.execute(
            "SELECT operator_before_digest, executed_harness_revision, manifest "
            "FROM verification_control.phase_runs "
            "WHERE phase = %s AND freeze_revision = %s",
            [phase, revisions["freeze_revision"]],
        ).fetchone()
        if phase_run is None:
            raise VerificationConfigurationError(
                f"No begin fingerprint exists for phase {phase!r}."
            )
        before_digest = str(phase_run["operator_before_digest"])
        harness_matched = (
            phase_run["executed_harness_revision"] == revisions["harness_revision"]
        )
        operator_matched = before_digest == after["digest"]
        configuration_matched = (
            phase_run["manifest"].get("configuration_digest")
            == current_manifest["configuration_digest"]
        )
        isolation_passed = harness_matched and operator_matched and configuration_matched
        recorded_blockers = list(normalized_blockers)
        if not harness_matched:
            recorded_blockers.append(
                "verification harness revision changed between phase begin and end"
            )
        if not operator_matched:
            recorded_blockers.append(
                "operator database fingerprint changed during verification"
            )
        if not configuration_matched:
            recorded_blockers.append(
                "verification configuration changed between phase begin and end"
            )
        qualification_status = normalized_outcome if isolation_passed else "blocked"
        _save_fingerprint(
            connection, phase, revisions["freeze_revision"], "after", after
        )
        connection.execute(
            "UPDATE verification_control.phase_runs SET isolation_status = %s, "
            "qualification_status = %s, blockers = %s, verdict_revision = %s, "
            "operator_after_digest = %s, finished_at = now() "
            "WHERE phase = %s AND freeze_revision = %s",
            [
                "passed" if isolation_passed else "blocked",
                qualification_status,
                Jsonb(recorded_blockers),
                revisions["harness_revision"],
                after["digest"],
                phase,
                revisions["freeze_revision"],
            ],
        )
    if not isolation_passed:
        if not harness_matched:
            raise VerificationConfigurationError(
                "Verification harness revision changed between phase begin and end."
            )
        if not configuration_matched:
            raise VerificationConfigurationError(
                "Verification configuration changed between phase begin and end."
            )
        raise VerificationConfigurationError(
            "Operator database fingerprint changed during verification; stop immediately."
        )
    return {
        "phase": phase,
        "stage": "after",
        "freeze_revision": revisions["freeze_revision"],
        "operator_fingerprint": after["digest"],
        "isolation_status": "passed",
        "qualification_status": normalized_outcome,
        "blockers": normalized_blockers,
    }


def fingerprint_operator_database() -> Mapping[str, Any]:
    """Return deterministic table counts and hashes through a read-only transaction."""
    operator = _required_settings("PG_OPERATOR")
    test = _required_settings("PG_TEST")
    if operator.dbname == test.dbname:
        raise VerificationConfigurationError("Operator and test databases must differ.")
    groups: dict[str, dict[str, Mapping[str, Any]]] = {}
    with psycopg.connect(operator.conninfo()) as connection:
        connection.read_only = True
        connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        current = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if current != (operator.dbname, operator.user):
            raise VerificationConfigurationError(
                "Operator fingerprint connection identity mismatch."
            )
        for group_name, tables in (
            ("runtime", RUNTIME_TABLES),
            ("knowledge", KNOWLEDGE_TABLES),
            ("research", RESEARCH_TABLES),
        ):
            groups[group_name] = {
                table: _fingerprint_table(connection, table) for table in tables
            }
    payload = {
        "database": operator.dbname,
        "groups": groups,
    }
    return {**payload, "digest": _stable_digest(payload)}


def _fingerprint_table(
    connection: psycopg.Connection[Any], table_name: str
) -> Mapping[str, Any]:
    exists = connection.execute(
        "SELECT to_regclass(%s) IS NOT NULL", [f"public.{table_name}"]
    ).fetchone()
    if exists is None or not exists[0]:
        return {"present": False, "row_count": 0, "digest": _sha256_text("")}
    expression = _KNOWLEDGE_FINGERPRINT_EXPRESSIONS.get(table_name, "to_jsonb(t)")
    query = sql.SQL(
        "SELECT md5(({})::text) AS row_digest FROM {} AS t ORDER BY row_digest"
    ).format(sql.SQL(expression), sql.Identifier("public", table_name))
    digest = hashlib.sha256()
    row_count = 0
    with connection.cursor(name=f"fingerprint_{table_name}") as cursor:
        cursor.execute(query)
        while rows := cursor.fetchmany(1000):
            for row in rows:
                digest.update(str(row[0]).encode("ascii"))
                digest.update(b"\n")
                row_count += 1
    return {"present": True, "row_count": row_count, "digest": digest.hexdigest()}


def _initialize_product_schemas(settings: PostgresConnectionSettings) -> None:
    from trader.event_store import PostgresEventStore
    from trader_research.knowledge.postgres_store import PostgresKnowledgeStore
    from trader_research.infrastructure.postgres import PostgresResearchArtifactStore

    event_store = PostgresEventStore(**settings.connect_kwargs())
    event_store.close()
    knowledge_store = PostgresKnowledgeStore(**settings.connect_kwargs())
    knowledge_store.close()
    artifact_store = PostgresResearchArtifactStore(**settings.connect_kwargs())
    artifact_store.close()


def _ensure_control_schema(connection: psycopg.Connection[Any]) -> None:
    connection.execute("CREATE SCHEMA IF NOT EXISTS verification_control")
    phase_columns = {
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'verification_control' "
            "AND table_name = 'phase_runs'"
        ).fetchall()
    }
    expected_phase_columns = {
        "phase",
        "freeze_revision",
        "executed_harness_revision",
        "verdict_revision",
        "isolation_status",
        "qualification_status",
        "blockers",
        "manifest",
        "operator_before_digest",
        "operator_after_digest",
        "started_at",
        "finished_at",
    }
    if phase_columns and phase_columns != expected_phase_columns:
        raise VerificationConfigurationError(
            "verification control schema is incompatible; run provision --reset"
        )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.runtime_marker (
            marker_id TEXT PRIMARY KEY,
            database_name TEXT NOT NULL,
            role_name TEXT NOT NULL,
            freeze_revision TEXT NOT NULL,
            locale_name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.phase_runs (
            phase TEXT NOT NULL,
            freeze_revision TEXT NOT NULL,
            executed_harness_revision TEXT NOT NULL,
            verdict_revision TEXT,
            isolation_status TEXT NOT NULL CHECK (
                isolation_status IN ('running', 'passed', 'blocked')
            ),
            qualification_status TEXT NOT NULL CHECK (
                qualification_status IN ('running', 'passed', 'blocked')
            ),
            blockers JSONB NOT NULL,
            manifest JSONB NOT NULL,
            operator_before_digest TEXT NOT NULL,
            operator_after_digest TEXT,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            PRIMARY KEY (phase, freeze_revision)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.operator_fingerprints (
            phase TEXT NOT NULL,
            freeze_revision TEXT NOT NULL,
            stage TEXT NOT NULL,
            digest TEXT NOT NULL,
            payload JSONB NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (phase, freeze_revision, stage)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.acceptance_records (
            freeze_revision TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('passed', 'blocked')),
            mandatory_phases JSONB NOT NULL,
            provider_profiles JSONB NOT NULL,
            environment JSONB NOT NULL,
            evidence_inventory JSONB NOT NULL,
            commands JSONB NOT NULL,
            residual_risks JSONB NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.orchestration_call_ledger (
            qualification_profile TEXT NOT NULL,
            freeze_revision TEXT NOT NULL,
            phase TEXT NOT NULL,
            composition_id TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK (sequence > 0),
            command TEXT NOT NULL,
            argument_digest TEXT NOT NULL,
            result_identity JSONB NOT NULL,
            retry_disposition TEXT NOT NULL CHECK (
                retry_disposition IN (
                    'accepted', 'identical_retry', 'rejected', 'response_lost'
                )
            ),
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (
                qualification_profile, freeze_revision, phase,
                composition_id, sequence
            )
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.orchestration_scale_results (
            qualification_profile TEXT NOT NULL,
            freeze_revision TEXT NOT NULL,
            phase TEXT NOT NULL,
            profile TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('passed', 'blocked')),
            task_count INTEGER NOT NULL CHECK (task_count >= 0),
            transition_count INTEGER NOT NULL CHECK (transition_count >= 0),
            tool_call_count INTEGER NOT NULL CHECK (tool_call_count >= 0),
            checkpoint_bytes BIGINT NOT NULL CHECK (checkpoint_bytes >= 0),
            artifact_count INTEGER NOT NULL CHECK (artifact_count >= 0),
            database_bytes BIGINT NOT NULL CHECK (database_bytes >= 0),
            wall_seconds DOUBLE PRECISION NOT NULL CHECK (wall_seconds >= 0),
            payload JSONB NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (qualification_profile, freeze_revision, phase, profile)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS verification_control.orchestration_acceptance_records (
            qualification_profile TEXT NOT NULL,
            freeze_revision TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('passed', 'blocked')),
            qualified_surface JSONB NOT NULL,
            exclusions JSONB NOT NULL,
            mandatory_phases JSONB NOT NULL,
            environment JSONB NOT NULL,
            evidence_inventory JSONB NOT NULL,
            commands JSONB NOT NULL,
            residual_risks JSONB NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (qualification_profile, freeze_revision)
        )
        """
    )


def _save_fingerprint(
    connection: psycopg.Connection[Any],
    phase: str,
    freeze_revision: str,
    stage: str,
    fingerprint: Mapping[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO verification_control.operator_fingerprints (
            phase, freeze_revision, stage, digest, payload
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (phase, freeze_revision, stage) DO UPDATE SET
            digest = EXCLUDED.digest,
            payload = EXCLUDED.payload,
            recorded_at = now()
        """,
        [phase, freeze_revision, stage, fingerprint["digest"], Jsonb(fingerprint)],
    )


def _ensure_role(
    connection: psycopg.Connection[Any], settings: PostgresConnectionSettings
) -> None:
    _validate_identifier(settings.user, "Postgres role")
    exists = connection.execute(
        "SELECT 1 FROM pg_roles WHERE rolname = %s", [settings.user]
    ).fetchone()
    statement = sql.SQL(
        "{} ROLE {} WITH LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE "
        "NOREPLICATION"
    ).format(
        sql.SQL("ALTER" if exists else "CREATE"),
        sql.Identifier(settings.user),
        sql.Literal(settings.password),
    )
    connection.execute(statement)


def _required_settings(prefix: str) -> PostgresConnectionSettings:
    settings = _load_prefixed_settings(prefix, os.environ, required=True)
    if settings is None:  # pragma: no cover - required=True fails first
        raise VerificationConfigurationError(f"{prefix} settings are required.")
    return settings


def _required_environment_value(name: str) -> str:
    value = str(os.environ.get(name, "")).strip()
    if not value:
        raise VerificationConfigurationError(f"{name} is required.")
    return value


def _assert_optuna_targets_test_database(
    test: PostgresConnectionSettings, optuna: PostgresConnectionSettings
) -> None:
    _assert_role_targets_test_database(
        test,
        optuna,
        role_prefix="PG_OPTUNA_TEST",
    )


def _assert_role_targets_test_database(
    test: PostgresConnectionSettings,
    role: PostgresConnectionSettings,
    *,
    role_prefix: str,
) -> None:
    """Require an isolated role to target the disposable product-test database.

    Args:
        test: Product-test database settings.
        role: Isolated role settings to compare.
        role_prefix: Environment prefix used in actionable errors.

    Raises:
        VerificationConfigurationError: If host, port, or database differ.
    """
    if (role.host, role.port, role.dbname) != (
        test.host,
        test.port,
        test.dbname,
    ):
        raise VerificationConfigurationError(
            f"{role_prefix} settings must target "
            "PG_TEST_HOST/PG_TEST_PORT/PG_TEST_DB."
        )


def _load_prefixed_settings(
    prefix: str,
    environ: Mapping[str, str],
    *,
    required: bool,
) -> PostgresConnectionSettings | None:
    names = {
        "host": f"{prefix}_HOST",
        "port": f"{prefix}_PORT",
        "dbname": f"{prefix}_DB",
        "user": f"{prefix}_USER",
        "password": f"{prefix}_PASSWORD",
    }
    values = {key: str(environ.get(name, "")).strip() for key, name in names.items()}
    supplied = [key for key, value in values.items() if value]
    if not supplied and not required:
        return None
    missing = [names[key] for key, value in values.items() if not value]
    if missing:
        raise VerificationConfigurationError(
            f"Incomplete {prefix} Postgres settings; missing {missing}."
        )
    try:
        port = int(values["port"])
    except ValueError as exc:
        raise VerificationConfigurationError(
            f"{names['port']} must be an integer."
        ) from exc
    if port <= 0:
        raise VerificationConfigurationError(f"{names['port']} must be positive.")
    return PostgresConnectionSettings(
        host=values["host"],
        port=port,
        dbname=values["dbname"],
        user=values["user"],
        password=values["password"],
    )


def _validate_test_identity(
    settings: PostgresConnectionSettings, environ: Mapping[str, str]
) -> None:
    if not settings.dbname.lower().endswith(TEST_DATABASE_SUFFIXES):
        raise VerificationConfigurationError(
            "PG_TEST_DB must end in _test or _testing."
        )
    _validate_identifier(settings.dbname, "PG_TEST_DB")
    _validate_identifier(settings.user, "PG_TEST_USER")
    operator_db = str(environ.get("PG_OPERATOR_DB", "")).strip()
    operator_user = str(environ.get("PG_OPERATOR_USER", "")).strip()
    if operator_db and settings.dbname == operator_db:
        raise VerificationConfigurationError(
            "PG_TEST_DB must differ from PG_OPERATOR_DB."
        )
    if operator_user and settings.user == operator_user:
        raise VerificationConfigurationError(
            "PG_TEST_USER must differ from PG_OPERATOR_USER."
        )


def _validate_identifier(value: str, field_name: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise VerificationConfigurationError(
            f"{field_name} must be a simple Postgres identifier."
        )


def _validate_phase(phase: str) -> None:
    profile = load_qualification_profile()
    if phase not in profile.phases:
        raise VerificationConfigurationError(
            f"phase must be one of {sorted(profile.phases)} for profile {profile.name!r}"
        )


def load_retained_evidence_phase(
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Return the explicitly retained verification phase, if configured."""
    values = os.environ if environ is None else environ
    profile = load_qualification_profile(values)
    value = str(values.get(RETAIN_EVIDENCE_PHASE_ENV, "")).strip().upper()
    if not value:
        return None
    if value not in profile.retainable_phases:
        raise VerificationConfigurationError(
            f"{RETAIN_EVIDENCE_PHASE_ENV} may only retain one of "
            f"{sorted(profile.retainable_phases)} for profile {profile.name!r}."
        )
    return value


def retain_verification_evidence(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether a controlled retained phase should survive teardown."""
    profile = load_qualification_profile(environ)
    return load_retained_evidence_phase(environ) in profile.retainable_phases


def _validate_phase_policy_gates(
    phase: str | None,
    gates: Mapping[str, bool],
) -> None:
    profile = load_qualification_profile()
    expected = profile.enabled_mutation_gates.get(phase, frozenset())
    enabled = frozenset(name for name, value in gates.items() if value)
    if enabled != expected:
        raise VerificationConfigurationError(
            f"Controlled phase {phase or 'manifest'} requires exactly these enabled mutation "
            f"gates: {sorted(expected)}; received {sorted(enabled)}."
        )


def _validate_outcome(outcome: str, blockers: Sequence[str]) -> str:
    normalized = str(outcome).strip().lower()
    if normalized not in {"passed", "blocked"}:
        raise VerificationConfigurationError("outcome must be passed or blocked")
    normalized_blockers = _normalize_blockers(blockers)
    if normalized == "passed" and normalized_blockers:
        raise VerificationConfigurationError(
            "a passed qualification cannot record blockers"
        )
    if normalized == "blocked" and not normalized_blockers:
        raise VerificationConfigurationError(
            "a blocked qualification must record at least one blocker"
        )
    return normalized


def _normalize_blockers(blockers: Sequence[str]) -> list[str]:
    if len(blockers) > 20:
        raise VerificationConfigurationError("at most 20 blockers may be recorded")
    normalized: list[str] = []
    for blocker in blockers:
        value = str(blocker).strip()
        if not value:
            raise VerificationConfigurationError("blockers must not be empty")
        if len(value) > 500:
            raise VerificationConfigurationError(
                "each blocker must be at most 500 characters"
            )
        normalized.append(value)
    return normalized


def _is_harness_path(path: str) -> bool:
    return path in _HARNESS_PATHS or any(
        path.startswith(prefix) for prefix in _HARNESS_PATH_PREFIXES
    )


def _parse_bool(value: str, name: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in _FALSE_VALUES:
        return False
    if normalized in _TRUE_VALUES:
        return True
    raise VerificationConfigurationError(f"{name} must be a boolean value.")


def _row_values(row: Any, *names: str) -> tuple[Any, ...]:
    if isinstance(row, Mapping):
        return tuple(row[name] for name in names)
    return tuple(row[index] for index in range(len(names)))


def _stable_digest(value: Mapping[str, Any]) -> str:
    return _sha256_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _git(*args: str, allow_empty: bool = False) -> str:
    result = _run_git(*args)
    output = result.stdout.strip()
    if not output and not allow_empty:
        raise VerificationConfigurationError(f"git {' '.join(args)} returned no output")
    return output


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise VerificationConfigurationError(
            f"git {' '.join(args)} failed: {exc.stderr.strip()}"
        ) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    provision = subparsers.add_parser(
        "provision", help="Provision the isolated verification runtime."
    )
    provision.add_argument(
        "--reset", action="store_true", help="Drop and recreate only PG_TEST_DB."
    )
    for command in ("begin", "end"):
        phase = subparsers.add_parser(
            command, help=f"{command.title()} a fingerprinted phase."
        )
        phase.add_argument("--phase", required=True)
        if command == "end":
            phase.add_argument(
                "--outcome", choices=("passed", "blocked"), required=True
            )
            phase.add_argument("--blocker", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the verification provisioning/fingerprint command line interface."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "provision":
            result = provision_verification_runtime(reset=bool(args.reset))
        elif args.command == "begin":
            result = begin_phase(str(args.phase))
        else:
            result = end_phase(
                str(args.phase), outcome=str(args.outcome), blockers=args.blocker
            )
    except VerificationConfigurationError as exc:
        raise SystemExit(f"verification failed: {exc}") from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
