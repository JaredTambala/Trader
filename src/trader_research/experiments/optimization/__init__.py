"""Provider-neutral parameter optimization capability."""

from .contracts import (
    ExperimentTrackingSink,
    OptimizationEngine,
    OptimizationEngineProfile,
    OptimizationObservation,
    OptimizationOutcome,
    OptimizationSuggestion,
    OptimizationTrialExecutor,
    TrialExecution,
)
from .engines import GridOptimizationEngine, OptimizationEngineRegistry, RandomOptimizationEngine
from .executor import BacktestOptimizationTrialExecutor
from .orchestration import run_parameter_optimization
from .planning import create_parameter_optimization_plan, get_optimizer_runtime
from .queries import get_parameter_optimization_results
from .variants import required_optimizer_profiles_for_variants, run_parameter_optimization_variants

__all__ = [
    "ExperimentTrackingSink",
    "BacktestOptimizationTrialExecutor",
    "GridOptimizationEngine",
    "OptimizationEngine",
    "OptimizationEngineProfile",
    "OptimizationObservation",
    "OptimizationOutcome",
    "OptimizationSuggestion",
    "OptimizationEngineRegistry",
    "OptimizationTrialExecutor",
    "RandomOptimizationEngine",
    "TrialExecution",
    "create_parameter_optimization_plan",
    "get_optimizer_runtime",
    "get_parameter_optimization_results",
    "run_parameter_optimization",
    "run_parameter_optimization_variants",
    "required_optimizer_profiles_for_variants",
]
