"""Repository for Console database-schema compatibility checks."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Final, Mapping, Protocol

from .resource_contract import RESOURCE_CONTRACT_COLUMNS


class DatabaseTransactionManager(Protocol):
    """Transaction boundary required by the compatibility repository."""

    def transaction(self) -> AbstractAsyncContextManager[Any]:
        """Return one short database transaction context."""
        ...


CONTRACT_NAME: Final = "trader_console"
SUPPORTED_CONTRACT_VERSION: Final = 1
EXPECTED_CONTRACT_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = {
    "contract_versions": (
        "contract_name",
        "contract_version",
        "minimum_consumer_version",
        "installed_at",
    ),
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
    **RESOURCE_CONTRACT_COLUMNS,
}

_VERSION_QUERY: Final = """
SELECT contract_version, minimum_consumer_version
FROM console_read.contract_versions
WHERE contract_name = %s
"""
_CATALOG_QUERY: Final = """
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'console_read'
ORDER BY table_name, ordinal_position
"""


@dataclass(frozen=True)
class SchemaCompatibility:
    """Compatibility evidence for the configured Console database schema."""

    installed_version: int | None
    minimum_consumer_version: int | None
    issues: tuple[str, ...]

    @property
    def ready(self) -> bool:
        """Return whether the installed schema is compatible with this API."""
        return not self.issues


class SchemaCompatibilityRepository:
    """Inspect compatibility metadata and approved relation shapes."""

    def __init__(self, database: DatabaseTransactionManager) -> None:
        """Bind inspection queries to the repository transaction boundary."""
        self._database = database

    async def inspect(self) -> SchemaCompatibility:
        """Return database compatibility evidence for startup and readiness."""
        async with self._database.transaction() as connection:
            catalog_cursor = await connection.execute(_CATALOG_QUERY)
            catalog_rows = await catalog_cursor.fetchall()
            observed_contract_columns = tuple(
                str(column_name)
                for relation_name, column_name in catalog_rows
                if str(relation_name) == "contract_versions"
            )
            if (
                observed_contract_columns
                == EXPECTED_CONTRACT_COLUMNS["contract_versions"]
            ):
                version_cursor = await connection.execute(
                    _VERSION_QUERY, [CONTRACT_NAME]
                )
                version_row = await version_cursor.fetchone()
            else:
                version_row = None
            return assess_schema_compatibility(
                version_row=version_row,
                catalog_rows=catalog_rows,
            )


def assess_schema_compatibility(
    *,
    version_row: tuple[Any, ...] | None,
    catalog_rows: list[tuple[Any, ...]],
    consumer_version: int = SUPPORTED_CONTRACT_VERSION,
) -> SchemaCompatibility:
    """Assess raw catalog rows without database or application side effects."""
    issues: list[str] = []
    if version_row is None:
        installed_version = None
        minimum_consumer_version = None
        issues.append("schema_metadata_missing")
    else:
        installed_version = int(version_row[0])
        minimum_consumer_version = int(version_row[1])
        if minimum_consumer_version > installed_version:
            issues.append("schema_metadata_invalid")
        elif consumer_version < minimum_consumer_version:
            issues.append("consumer_schema_too_old")
        elif consumer_version > installed_version:
            issues.append("database_schema_too_old")

    observed_columns: dict[str, list[str]] = {}
    for relation_name, column_name in catalog_rows:
        observed_columns.setdefault(str(relation_name), []).append(str(column_name))
    for relation_name, expected_columns in EXPECTED_CONTRACT_COLUMNS.items():
        if tuple(observed_columns.get(relation_name, ())) != expected_columns:
            issues.append(f"schema_catalog_mismatch:{relation_name}")

    return SchemaCompatibility(
        installed_version=installed_version,
        minimum_consumer_version=minimum_consumer_version,
        issues=tuple(issues),
    )
