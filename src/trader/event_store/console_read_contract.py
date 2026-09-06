"""Producer-owned PostgreSQL read contract for the Trader Console.

This module installs a metadata-versioned contract of stable ordinary views over
core runtime evidence. It is an operator/deployment surface: the trading runtime
and Console API must not run these migrations during normal startup.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from typing import Any, Final, Mapping, Sequence

try:
    import psycopg
    from psycopg import sql
except ImportError:  # pragma: no cover - psycopg is a core dependency in production
    psycopg = None
    sql = None


CONSOLE_READ_SCHEMA: Final = "console_read"
CONSOLE_READ_CONTRACT: Final = "trader_console"
CONSOLE_READ_CONTRACT_VERSION: Final = 1
CONSOLE_READ_MINIMUM_CONSUMER_VERSION: Final = 1

# These are the complete columns exposed by the current contract. Variable configuration,
# generic payload, prediction value, metrics payload, and decision-evidence fields
# remain private until a typed producer-owned projection is approved.
CONSOLE_READ_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = {
    "sessions": (
        "session_id",
        "strategy_id",
        "started_at",
        "finished_at",
        "status",
        "error_message",
        "mode",
        "symbols",
        "timeframe",
        "start_ts",
        "end_ts",
    ),
    "runs": (
        "run_id",
        "run_type",
        "started_at",
        "finished_at",
        "status",
        "error_message",
        "mode",
        "symbols",
        "timeframe",
        "start_ts",
        "end_ts",
    ),
    "cycles": (
        "cycle_id",
        "run_id",
        "session_id",
        "strategy_id",
        "mode",
        "decision_ts",
        "started_at",
        "finished_at",
        "status",
        "error_message",
    ),
    "stock_bars": (
        "symbol",
        "timeframe",
        "ts",
        "ingested_at",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trade_count",
        "vwap",
        "source",
    ),
    "crypto_bars": (
        "symbol",
        "timeframe",
        "ts",
        "ingested_at",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trade_count",
        "vwap",
        "source",
    ),
    "signals": (
        "run_id",
        "session_id",
        "cycle_id",
        "symbol",
        "signal_name",
        "signal_value",
        "target_qty",
        "generated_at",
        "mapper_id",
    ),
    "indicators": (
        "run_id",
        "session_id",
        "cycle_id",
        "symbol",
        "indicator_name",
        "value",
        "bar_ts",
    ),
    "predictions": (
        "prediction_event_id",
        "run_id",
        "session_id",
        "cycle_id",
        "deployment_id",
        "deployment_validation_id",
        "model_version_id",
        "feature_set_id",
        "feature_batch_hash",
        "decision_ts",
        "symbol",
        "output_name",
        "semantics",
        "horizon",
        "latency_ms",
        "status",
        "error_message",
    ),
    "orders": (
        "order_event_id",
        "client_order_id",
        "run_id",
        "session_id",
        "cycle_id",
        "symbol",
        "side",
        "qty",
        "order_type",
        "status",
        "broker_order_id",
        "rejection_reason",
        "created_at",
    ),
    "fills": (
        "client_order_id",
        "run_id",
        "session_id",
        "cycle_id",
        "fill_ts",
        "fill_qty",
        "raw_fill_price",
        "slippage_amount",
        "fee_amount",
        "fill_price",
    ),
    "positions": (
        "asof_ts",
        "symbol",
        "qty",
        "avg_price",
        "cash_balance",
        "run_id",
        "session_id",
        "cycle_id",
    ),
}

CONSOLE_READ_SOURCES: Final[Mapping[str, str]] = {
    "sessions": "trading_sessions",
    "runs": "runs",
    "cycles": "run_events",
    "stock_bars": "stock_bar_events",
    "crypto_bars": "crypto_bar_events",
    "signals": "signal_events",
    "indicators": "indicator_events",
    "predictions": "prediction_events",
    "orders": "order_events",
    "fills": "fill_events",
    "positions": "position_snapshots",
}
CONSOLE_READ_CONTRACT_COLUMNS: Final[tuple[str, ...]] = (
    "contract_name",
    "contract_version",
    "minimum_consumer_version",
    "installed_at",
)

CONSOLE_READ_VERSION_QUERY: Final = """
SELECT contract_version, minimum_consumer_version
FROM console_read.contract_versions
WHERE contract_name = %s
"""


@dataclass(frozen=True)
class ConsoleReadCompatibility:
    """Compatibility result for one Console consumer and installed contract."""

    compatible: bool
    installed_version: int | None
    minimum_consumer_version: int | None
    consumer_version: int
    reason: str | None


@dataclass(frozen=True)
class ConsoleReadInspection:
    """Catalog and compatibility result for the installed read contract."""

    compatibility: ConsoleReadCompatibility
    issues: tuple[str, ...]

    @property
    def ready(self) -> bool:
        """Return whether the installed read contract is usable by this consumer."""
        return self.compatibility.compatible and not self.issues


def assess_console_read_compatibility(
    *,
    installed_version: int | None,
    minimum_consumer_version: int | None,
    consumer_version: int = CONSOLE_READ_CONTRACT_VERSION,
) -> ConsoleReadCompatibility:
    """Assess an installed contract without querying or mutating PostgreSQL.

    A newer additive database contract may continue admitting an older consumer by
    retaining a sufficiently low ``minimum_consumer_version``. Missing, invalid,
    or older contracts fail closed.
    """
    if installed_version is None or minimum_consumer_version is None:
        reason = "console_read_contract_missing"
    elif minimum_consumer_version > installed_version:
        reason = "console_read_contract_invalid"
    elif consumer_version < minimum_consumer_version:
        reason = "console_consumer_too_old"
    elif consumer_version > installed_version:
        reason = "console_read_contract_too_old"
    else:
        reason = None
    return ConsoleReadCompatibility(
        compatible=reason is None,
        installed_version=installed_version,
        minimum_consumer_version=minimum_consumer_version,
        consumer_version=consumer_version,
        reason=reason,
    )


def install_console_read_contract(connection: Any) -> None:
    """Install the current read contract without provisioning database identity.

    Args:
        connection: Psycopg connection authenticated as the producer migration
            owner. It must own the runtime source tables.

    Raises:
        RuntimeError: If installation would downgrade a newer contract.
        Exception: If PostgreSQL rejects a migration statement.
    """
    _require_psycopg()

    with connection.transaction():
        connection.execute("CREATE SCHEMA IF NOT EXISTS console_read")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS console_read.contract_versions (
                contract_name TEXT PRIMARY KEY,
                contract_version INTEGER NOT NULL CHECK (contract_version > 0),
                minimum_consumer_version INTEGER NOT NULL
                    CHECK (minimum_consumer_version > 0),
                installed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CHECK (minimum_consumer_version <= contract_version)
            )
            """
        )
        existing_version = connection.execute(
            CONSOLE_READ_VERSION_QUERY, [CONSOLE_READ_CONTRACT]
        ).fetchone()
        if existing_version is not None and int(existing_version[0]) > CONSOLE_READ_CONTRACT_VERSION:
            raise RuntimeError(
                "Refusing to downgrade Console read contract from version "
                f"{existing_version[0]} to {CONSOLE_READ_CONTRACT_VERSION}."
            )
        for view_name, source_table in CONSOLE_READ_SOURCES.items():
            columns = CONSOLE_READ_COLUMNS[view_name]
            connection.execute(
                sql.SQL(
                    "CREATE OR REPLACE VIEW console_read.{} "
                    "WITH (security_barrier=true, security_invoker=false) AS "
                    "SELECT {} FROM public.{}"
                ).format(
                    sql.Identifier(view_name),
                    sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                    sql.Identifier(source_table),
                )
            )
        connection.execute(
            """
            INSERT INTO console_read.contract_versions (
                contract_name, contract_version, minimum_consumer_version, installed_at
            ) VALUES (%s, %s, %s, now())
            ON CONFLICT (contract_name) DO UPDATE SET
                contract_version = EXCLUDED.contract_version,
                minimum_consumer_version = EXCLUDED.minimum_consumer_version,
                installed_at = EXCLUDED.installed_at
            """,
            [
                CONSOLE_READ_CONTRACT,
                CONSOLE_READ_CONTRACT_VERSION,
                CONSOLE_READ_MINIMUM_CONSUMER_VERSION,
            ],
        )


def rollback_console_read_contract(connection: Any) -> None:
    """Remove the current contract after confirming no later one is installed."""
    relation = connection.execute(
        "SELECT to_regclass('console_read.contract_versions')"
    ).fetchone()
    if relation is None or relation[0] is None:
        raise RuntimeError("Console read contract is not installed.")
    row = connection.execute(
        CONSOLE_READ_VERSION_QUERY, [CONSOLE_READ_CONTRACT]
    ).fetchone()
    installed_version = int(row[0]) if row is not None else None
    if installed_version != CONSOLE_READ_CONTRACT_VERSION:
        raise RuntimeError(
            "Refusing Console read-contract rollback: expected installed version "
            f"{CONSOLE_READ_CONTRACT_VERSION}, found {installed_version!r}."
        )
    with connection.transaction():
        connection.execute("DROP SCHEMA console_read CASCADE")


def inspect_console_read_contract(
    connection: Any,
    *,
    consumer_version: int = CONSOLE_READ_CONTRACT_VERSION,
) -> ConsoleReadInspection:
    """Inspect only the installed relation shape and compatibility metadata.

    Authentication and authorization are deployment extension points rather
    than responsibilities of this database migration. The Console API owns its
    connection policy and read-only transaction boundary.
    """
    issues: list[str] = []
    catalog_rows = connection.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'console_read'
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()
    observed_columns: dict[str, list[str]] = {}
    for table_name, column_name in catalog_rows:
        observed_columns.setdefault(str(table_name), []).append(str(column_name))
    expected_relations = {
        "contract_versions": CONSOLE_READ_CONTRACT_COLUMNS,
        **CONSOLE_READ_COLUMNS,
    }
    for relation_name, expected_columns in expected_relations.items():
        if tuple(observed_columns.get(relation_name, ())) != expected_columns:
            issues.append(f"console_read_catalog_mismatch:{relation_name}")

    contract_relation = connection.execute(
        "SELECT to_regclass('console_read.contract_versions')"
    ).fetchone()
    if contract_relation is None or contract_relation[0] is None:
        compatibility = assess_console_read_compatibility(
            installed_version=None,
            minimum_consumer_version=None,
            consumer_version=consumer_version,
        )
    else:
        version_row = connection.execute(
            CONSOLE_READ_VERSION_QUERY, [CONSOLE_READ_CONTRACT]
        ).fetchone()
        compatibility = assess_console_read_compatibility(
            installed_version=int(version_row[0]) if version_row else None,
            minimum_consumer_version=int(version_row[1]) if version_row else None,
            consumer_version=consumer_version,
        )
    return ConsoleReadInspection(
        compatibility=compatibility,
        issues=tuple(issues),
    )


def _require_psycopg() -> None:
    if psycopg is None or sql is None:  # pragma: no cover - import guard
        raise ImportError("psycopg is required to manage the Console read contract")


def _open_connection(environment_variable: str) -> Any:
    _require_psycopg()
    dsn = os.environ.get(environment_variable)
    if not dsn:
        raise RuntimeError(f"{environment_variable} must contain a PostgreSQL DSN.")
    return psycopg.connect(dsn)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install, verify, or roll back the Trader Console read contract."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("install")
    subparsers.add_parser("verify")
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument(
        "--confirm-version",
        type=int,
        required=True,
        choices=(CONSOLE_READ_CONTRACT_VERSION,),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit Console read-contract deployment command."""
    arguments = _parser().parse_args(argv)
    if arguments.command == "verify":
        with _open_connection("TRADER_CONSOLE_DATABASE_URL") as connection:
            inspection = inspect_console_read_contract(connection)
        if inspection.ready:
            print(
                "Console read contract is ready at version "
                f"{inspection.compatibility.installed_version}."
            )
            return 0
        problems = [
            *inspection.issues,
            inspection.compatibility.reason,
        ]
        print("Console read contract is not ready: " + ", ".join(p for p in problems if p))
        return 1

    with _open_connection("TRADER_CONSOLE_MIGRATION_DSN") as connection:
        if arguments.command == "install":
            install_console_read_contract(connection)
            print(f"Installed Console read contract {CONSOLE_READ_CONTRACT_VERSION}.")
        else:
            rollback_console_read_contract(connection)
            print(
                "Rolled back Console read contract version "
                f"{arguments.confirm_version}."
            )
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
