"""Expose immutable ML deployment and runtime-resolution contracts.

The implemented surface begins from pre-existing model-version and feature-set
evidence, validates provider adapters, and creates deployment manifests for
backtests. Training, promotion, and model-registry mutation are outside this
current package facade.
"""

from trader_research.foundation import PredictionDeploymentReader

from .adapters import InferenceAdapter, InferenceAdapterRegistry
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
    "InferenceAdapterRegistry",
    "PredictionDeploymentReader",
    "create_deployment_manifest",
    "load_passed_deployment",
    "validate_deployment",
]
