"""FastAPI transport routers for the Console API."""

from .context import router as context_router
from .catalogue import router as catalogue_router
from .backtest_definitions import router as backtest_definition_router
from .backtest_executions import router as backtest_execution_router
from .health import router as health_router
from .resources import router as resource_router
from .saved_data_scopes import router as saved_data_scope_router
from .data_scope_comparisons import router as data_scope_comparison_router
from .paper_runtime import router as paper_runtime_router
from .paper_operator_commands import router as paper_operator_command_router
from .next_research_decisions import router as next_research_decision_router
__all__ = [
    "backtest_definition_router",
    "backtest_execution_router",
    "catalogue_router",
    "context_router",
    "health_router",
    "resource_router",
    "saved_data_scope_router",
    "data_scope_comparison_router",
    "paper_runtime_router",
    "paper_operator_command_router",
    "next_research_decision_router",
]
