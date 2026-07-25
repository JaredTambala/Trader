"""Public ML lifecycle capability for immutable runtime deployments."""

from trader_research.foundation import PredictionDeploymentReader

from .adapters import InferenceAdapter, InferenceAdapterProfile, InferenceAdapterRegistry
from .deployment import (
    ArtifactPredictionDeploymentReader,
    create_deployment_manifest,
    load_passed_deployment,
    validate_deployment,
)
from .runtime import ArtifactPredictionRuntimeResolver

__all__ = [
    "ArtifactPredictionDeploymentReader",
    "ArtifactPredictionRuntimeResolver",
    "InferenceAdapter",
    "InferenceAdapterProfile",
    "InferenceAdapterRegistry",
    "PredictionDeploymentReader",
    "create_deployment_manifest",
    "load_passed_deployment",
    "validate_deployment",
]
