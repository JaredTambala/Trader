"""Provider-neutral parameter optimization capability."""

from .contracts import (
    ExperimentTrackingSink,
    OptimizationEngine,
    OptimizationEngineProfile,
    OptimizationObservation,
    OptimizationTrialExecutor,
    TrialExecution,
)
from .engines import GridOptimizationEngine, OptimizationEngineRegistry, RandomOptimizationEngine
from .optuna_adapter import OptunaOptimizationEngine
from .executor import BacktestOptimizationTrialExecutor
from .services import (
    create_parameter_optimization_plan,
    get_optimizer_runtime,
    get_parameter_optimization_results,
    run_parameter_optimization,
)
from .variants import required_optimizer_profiles_for_variants, run_parameter_optimization_variants

__all__ = [
    "ExperimentTrackingSink",
    "BacktestOptimizationTrialExecutor",
    "GridOptimizationEngine",
    "OptimizationEngine",
    "OptimizationEngineProfile",
    "OptimizationObservation",
    "OptimizationEngineRegistry",
    "OptimizationTrialExecutor",
    "OptunaOptimizationEngine",
    "RandomOptimizationEngine",
    "TrialExecution",
    "create_parameter_optimization_plan",
    "get_optimizer_runtime",
    "get_parameter_optimization_results",
    "run_parameter_optimization",
    "run_parameter_optimization_variants",
    "required_optimizer_profiles_for_variants",
]
