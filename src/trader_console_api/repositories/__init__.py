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
from .resources import ConsoleResourceRepository
from .backtest_definitions import (
    BacktestDefinitionConflict,
    BacktestDefinitionNotFound,
    BacktestDefinitionRepository,
    BacktestDefinitionSession,
)
from .backtest_executions import (
    BacktestExecutionDefinitionNotFound,
    BacktestExecutionNotFound,
    BacktestExecutionRepository,
    BacktestExecutionSession,
)

__all__ = [
    "EXPECTED_CONTRACT_COLUMNS",
    "ConsoleConnectionPool",
    "ConsoleDatabase",
    "ConsoleDatabaseUnavailable",
    "ConsoleResourceRepository",
    "BacktestDefinitionConflict",
    "BacktestDefinitionNotFound",
    "BacktestDefinitionRepository",
    "BacktestDefinitionSession",
    "BacktestExecutionDefinitionNotFound",
    "BacktestExecutionNotFound",
    "BacktestExecutionRepository",
    "BacktestExecutionSession",
    "DatabaseTransactionManager",
    "PoolFactory",
    "SchemaCompatibility",
    "SchemaCompatibilityRepository",
    "assess_schema_compatibility",
    "create_connection_pool",
]
