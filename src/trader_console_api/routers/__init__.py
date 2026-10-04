"""FastAPI transport routers for the Console API."""

from .context import router as context_router
from .catalogue import router as catalogue_router
from .backtest_definitions import router as backtest_definition_router
from .backtest_executions import router as backtest_execution_router
from .health import router as health_router
from .resources import router as resource_router
__all__ = [
    "backtest_definition_router",
    "backtest_execution_router",
    "catalogue_router",
    "context_router",
    "health_router",
    "resource_router",
]
