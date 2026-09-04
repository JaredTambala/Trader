"""Provider-neutral model prediction contracts for trading runtimes."""

from .domain import (
    DECISION_SCOPES,
    FAILURE_ACTIONS,
    PREDICTION_STATUSES,
    FeatureBatch,
    FeatureColumn,
    FeatureRow,
    InferenceAdapterProfile,
    InferencePolicy,
    ModelIdentity,
    PredictionBatch,
    PredictionObservation,
    PredictionRequest,
    StrategyPrediction,
    canonical_json_hash,
)
from .protocols import (
    FeatureProvider,
    PredictionMapper,
    Predictor,
    ValidatedPredictionFallback,
)
from .runtime import (
    PredictionDecision,
    PredictionRuntimeError,
    PredictionRuntimeResolver,
    RuntimePredictionBinding,
)

__all__ = [
    "DECISION_SCOPES",
    "FAILURE_ACTIONS",
    "PREDICTION_STATUSES",
    "FeatureBatch",
    "FeatureColumn",
    "FeatureProvider",
    "FeatureRow",
    "InferenceAdapterProfile",
    "InferencePolicy",
    "ModelIdentity",
    "PredictionBatch",
    "PredictionDecision",
    "PredictionMapper",
    "PredictionObservation",
    "PredictionRequest",
    "PredictionRuntimeError",
    "PredictionRuntimeResolver",
    "Predictor",
    "RuntimePredictionBinding",
    "StrategyPrediction",
    "ValidatedPredictionFallback",
    "canonical_json_hash",
]
