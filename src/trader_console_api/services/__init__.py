"""Application services for the Trader Console API."""

from .context import ContextService
from .health import CompatibilityRepository, HealthService, IncompatibleDatabaseSchema
from .resources import ResourceDatabaseUnavailable, ResourceService
from .catalogue import (
    CatalogueDatabaseUnavailable,
    CatalogueService,
    ImplementationLineageResolver,
    PreflightService,
)
from .backtest_definitions import (
    BacktestDefinitionService,
    DefinitionDatabaseUnavailable,
    InvalidBacktestDefinition,
)
from .backtest_executions import BacktestExecutionService, ExecutionDatabaseUnavailable
from .saved_data_scopes import (
    SavedDataScopeDatabaseUnavailable,
    SavedDataScopeNotFound,
    SavedDataScopeService,
    SavedDataScopeStorageUnavailable,
)
from .paper_runtime import PaperRuntimeDatabaseUnavailable, PaperRuntimeService
from .paper_operator_commands import (
    PaperAdmissionUnavailable,
    PaperOperatorAuthorityError,
    PaperOperatorCommandConflict,
    PaperOperatorCommandDatabaseUnavailable,
    PaperOperatorCommandNotFound,
    PaperOperatorCommandService,
    PaperOperatorCommandStorageUnavailable,
    PaperOperatorScopeError,
)
from .next_research_decisions import (
    NextDecisionAuthorityError,
    NextDecisionDatabaseUnavailable,
    NextDecisionRevisionConflict,
    NextResearchDecisionService,
)
from .agent_sessions import (
    AgentSessionAuthorityError,
    AgentSessionCommandConflict,
    AgentSessionService,
)

__all__ = [
    "CompatibilityRepository",
    "ContextService",
    "HealthService",
    "IncompatibleDatabaseSchema",
    "ResourceService",
    "ResourceDatabaseUnavailable",
    "CatalogueDatabaseUnavailable",
    "CatalogueService",
    "ImplementationLineageResolver",
    "PreflightService",
    "BacktestDefinitionService",
    "DefinitionDatabaseUnavailable",
    "InvalidBacktestDefinition",
    "BacktestExecutionService",
    "ExecutionDatabaseUnavailable",
    "SavedDataScopeDatabaseUnavailable",
    "SavedDataScopeNotFound",
    "SavedDataScopeService",
    "SavedDataScopeStorageUnavailable",
    "PaperRuntimeDatabaseUnavailable",
    "PaperRuntimeService",
    "PaperAdmissionUnavailable",
    "PaperOperatorAuthorityError",
    "PaperOperatorCommandConflict",
    "PaperOperatorCommandDatabaseUnavailable",
    "PaperOperatorCommandNotFound",
    "PaperOperatorCommandService",
    "PaperOperatorCommandStorageUnavailable",
    "PaperOperatorScopeError",
    "NextDecisionAuthorityError",
    "NextDecisionDatabaseUnavailable",
    "NextDecisionRevisionConflict",
    "NextResearchDecisionService",
    "AgentSessionAuthorityError",
    "AgentSessionCommandConflict",
    "AgentSessionService",
]
