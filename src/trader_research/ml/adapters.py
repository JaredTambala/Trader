"""Define provider-neutral ports for qualified inference adapters.

Profiles expose stable non-secret provider identity and configuration. Registries
resolve exact profiles and build pinned predictors only when a caller explicitly
starts a runtime session; importing this module never loads a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from trader.predictions import Predictor


@dataclass(frozen=True)
class InferenceAdapterProfile:
    """Credential-free immutable identity and capabilities of an adapter."""

    profile_name: str
    provider: str
    adapter_version: str
    configuration_digest: str
    capabilities: tuple[str, ...]
    available: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        """Require a complete immutable profile identity."""
        for name in ("profile_name", "provider", "adapter_version", "configuration_digest"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"inference adapter {name} is required")

    def to_dict(self) -> dict[str, object]:
        """Return the stable non-secret payload."""
        return {
            "profile_name": self.profile_name,
            "provider": self.provider,
            "adapter_version": self.adapter_version,
            "configuration_digest": self.configuration_digest,
            "capabilities": list(self.capabilities),
            "available": self.available,
            "reason": self.reason,
        }


class InferenceAdapter(Protocol):
    """Validate and resolve one immutable raw-inference deployment."""

    def profile(self) -> InferenceAdapterProfile:
        """Return provider/version/configuration identity without loading a model."""

    def validate_deployment(self, manifest: Mapping[str, object]) -> Mapping[str, object]:
        """Load the pinned model and prove its parity fixture and output contract."""

    def build_predictor(self, manifest: Mapping[str, object]) -> Predictor:
        """Load one pinned predictor for session-start dependency injection."""


class InferenceAdapterRegistry:
    """Resolve explicitly configured inference adapters without provider fallback."""

    def __init__(self, adapters: Sequence[InferenceAdapter] = ()) -> None:
        self._adapters: dict[str, InferenceAdapter] = {}
        for adapter in adapters:
            name = adapter.profile().profile_name
            if name in self._adapters:
                raise ValueError(f"duplicate inference adapter profile: {name}")
            self._adapters[name] = adapter

    def get(self, profile_name: str) -> InferenceAdapter:
        """Return one exact profile or fail closed."""
        try:
            return self._adapters[str(profile_name)]
        except KeyError as exc:
            raise ValueError(f"unknown inference adapter profile: {profile_name}") from exc

    def profiles(self) -> tuple[InferenceAdapterProfile, ...]:
        """Return deterministic profile metadata without loading models."""
        return tuple(self._adapters[name].profile() for name in sorted(self._adapters))
