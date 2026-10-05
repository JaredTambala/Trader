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
from .saved_data_scopes import (
    SavedDataScopeConflict,
    SavedDataScopeNotFound,
    SavedDataScopeRepository,
    SavedDataScopeSession,
)
from .data_scope_comparisons import (
    DataScopeComparisonCandidate,
    DataScopeComparisonNotFound,
    DataScopeComparisonRepository,
    DataScopeComparisonSession,
    DataScopeComparisonStorageUnavailable,
)
from .paper_operator_commands import (
    PaperOperatorCommandConflict,
    PaperOperatorCommandNotFound,
    PaperOperatorCommandRepository,
    PaperOperatorCommandSession,
)
from .next_research_decisions import (
    NextResearchDecisionConflict,
    NextResearchDecisionEvidenceUnavailable,
    NextResearchDecisionNotFound,
    NextResearchDecisionRepository,
    NextResearchDecisionSession,
    NextResearchDecisionStorageUnavailable,
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
    "SavedDataScopeConflict",
    "SavedDataScopeNotFound",
    "SavedDataScopeRepository",
    "SavedDataScopeSession",
    "DataScopeComparisonCandidate",
    "DataScopeComparisonNotFound",
    "DataScopeComparisonRepository",
    "DataScopeComparisonSession",
    "DataScopeComparisonStorageUnavailable",
    "PaperOperatorCommandConflict",
    "PaperOperatorCommandNotFound",
    "PaperOperatorCommandRepository",
    "PaperOperatorCommandSession",
    "NextResearchDecisionConflict",
    "NextResearchDecisionEvidenceUnavailable",
    "NextResearchDecisionNotFound",
    "NextResearchDecisionRepository",
    "NextResearchDecisionSession",
    "NextResearchDecisionStorageUnavailable",
    "DatabaseTransactionManager",
    "PoolFactory",
    "SchemaCompatibility",
    "SchemaCompatibilityRepository",
    "assess_schema_compatibility",
    "create_connection_pool",
]
