"""Provider-neutral runtime protocols for feature construction and inference."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Protocol, Sequence, runtime_checkable

from trader.event_store import EventStore

from .domain import (
    FeatureBatch,
    ModelIdentity,
    PredictionBatch,
    PredictionRequest,
    StrategyPrediction,
)


@runtime_checkable
class FeatureProvider(Protocol):
    """Build the same point-in-time feature batch offline and at runtime."""

    @property
    def feature_set_id(self) -> str:
        """Return the immutable feature-set identity."""

    @property
    def feature_set_digest(self) -> str:
        """Return the immutable feature-set content digest."""

    @property
    def required_lookback(self) -> int:
        """Return the required bar warmup count."""

    @property
    def decision_scope(self) -> str:
        """Return `per_symbol` or `universe_snapshot`."""

    def build(
        self,
        *,
        decision_ts: datetime,
        symbols: Sequence[str],
        asset_class: str,
        timeframe: str,
        event_store: EventStore,
    ) -> FeatureBatch:
        """Build one point-in-time feature batch from declared runtime state."""


@runtime_checkable
class Predictor(Protocol):
    """Evaluate one closed feature batch using an immutable model."""

    @property
    def identity(self) -> ModelIdentity:
        """Return the immutable model and adapter identity."""

    def predict(self, request: PredictionRequest) -> PredictionBatch:
        """Return raw model outputs for a closed request."""


@runtime_checkable
class PredictionMapper(Protocol):
    """Convert raw outputs into typed strategy inputs without placing orders."""

    @property
    def mapper_id(self) -> str:
        """Return the immutable mapper implementation/version identity."""

    @property
    def parameters(self) -> Mapping[str, object]:
        """Return normalized mapping parameters."""

    def map_predictions(self, batch: PredictionBatch) -> Sequence[StrategyPrediction]:
        """Interpret a successful raw prediction batch for a strategy."""


@runtime_checkable
class ValidatedPredictionFallback(Protocol):
    """Produce bounded strategy inputs after an explicitly validated failure."""

    @property
    def validation_ref(self) -> str:
        """Return the immutable validation reference pinned by policy."""

    def fallback(
        self,
        *,
        decision_ts: datetime,
        symbols: Sequence[str],
        reason: str,
    ) -> Sequence[StrategyPrediction]:
        """Return deterministic fallback inputs for the failed decision."""
