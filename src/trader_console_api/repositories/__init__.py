"""Persistence adapters for the Trader Console API."""

from .database import (
    ConsoleConnectionPool,
    ConsoleDatabase,
    ConsoleDatabaseUnavailable,
    PoolFactory,
    create_connection_pool,
)
from .schema_compatibility import (
    DatabaseTransactionManager,
    EXPECTED_CONTRACT_COLUMNS,
    SchemaCompatibility,
    SchemaCompatibilityRepository,
    assess_schema_compatibility,
)

__all__ = [
    "EXPECTED_CONTRACT_COLUMNS",
    "ConsoleConnectionPool",
    "ConsoleDatabase",
    "ConsoleDatabaseUnavailable",
    "DatabaseTransactionManager",
    "PoolFactory",
    "SchemaCompatibility",
    "SchemaCompatibilityRepository",
    "assess_schema_compatibility",
    "create_connection_pool",
]
