"""Provider-neutral optimization and trial-execution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


_OBSERVATION_FIELDS = frozenset(
    {"schema_version", "status", "metrics", "counts", "costs", "exposure", "risk", "quality", "constraints", "lineage"}
)


@dataclass(frozen=True)
class OptimizationObservation:
    """Versioned closed input exposed to optimization objective code."""

    payload: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OptimizationObservation":
        """Validate and normalize one observation without exposing runtime objects."""
        unknown = sorted(set(value).difference(_OBSERVATION_FIELDS))
        missing = sorted(_OBSERVATION_FIELDS.difference(value))
        if unknown:
            raise ValueError(f"optimization observation contains undeclared fields: {unknown}")
        if missing:
            raise ValueError(f"optimization observation is missing fields: {missing}")
        if str(value.get("schema_version") or "") not in {"1", "1.0"}:
            raise ValueError("optimization observation schema_version must be 1 or 1.0")
        normalized = {
            "schema_version": str(value["schema_version"]),
            "status": str(value["status"]),
            "metrics": _scalar_mapping(value["metrics"], "metrics", numeric=True),
            "counts": _count_mapping(value["counts"]),
            "costs": _scalar_mapping(value["costs"], "costs", numeric=True),
            "exposure": _bounded_json_mapping(value["exposure"], "exposure"),
            "risk": _bounded_json_mapping(value["risk"], "risk"),
            "quality": _bounded_json_mapping(value["quality"], "quality"),
            "constraints": _bounded_json_mapping(value["constraints"], "constraints"),
            "lineage": _scalar_mapping(value["lineage"], "lineage"),
        }
        return cls(payload=normalized)

    def to_dict(self) -> dict[str, Any]:
        """Return the isolated plain-data objective input."""
        return {key: _copy_json(value) for key, value in self.payload.items()}


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"optimization observation {label} must be an object")
    return value


def _scalar_mapping(value: Any, label: str, *, numeric: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in _mapping(value, label).items():
        if item is None:
            result[str(key)] = None
        elif numeric and (isinstance(item, bool) or not isinstance(item, (int, float))):
            raise ValueError(f"optimization observation {label}.{key} must be numeric or null")
        elif not numeric and not isinstance(item, (str, int, float, bool)):
            raise ValueError(f"optimization observation {label}.{key} must be scalar or null")
        else:
            result[str(key)] = item
    return result


def _count_mapping(value: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, item in _mapping(value, "counts").items():
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ValueError(f"optimization observation counts.{key} must be a non-negative integer")
        result[str(key)] = item
    return result


def _bounded_json_mapping(value: Any, label: str) -> dict[str, Any]:
    result = {str(key): _copy_json(item, depth=1) for key, item in _mapping(value, label).items()}
    if len(str(result)) > 100_000:
        raise ValueError(f"optimization observation {label} exceeds the bounded payload limit")
    return result


def _copy_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        raise ValueError("optimization observation nesting exceeds 6 levels")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _copy_json(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_copy_json(item, depth=depth + 1) for item in value]
    raise ValueError(f"optimization observation contains unsupported value: {type(value).__name__}")


@dataclass(frozen=True)
class OptimizationEngineProfile:
    """Immutable public identity and capabilities for an optimization engine."""

    profile_name: str
    provider: str
    algorithm: str
    provider_version: str
    configuration_digest: str
    capabilities: tuple[str, ...]
    available: bool = True
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the profile without credentials or provider state."""
        return {
            "profile_name": self.profile_name,
            "provider": self.provider,
            "algorithm": self.algorithm,
            "provider_version": self.provider_version,
            "configuration_digest": self.configuration_digest,
            "capabilities": list(self.capabilities),
            "available": self.available,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OptimizationSuggestion:
    """One parameter proposal produced by an engine."""

    engine_trial_id: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class OptimizationOutcome:
    """Closed result returned to an engine after canonical trial execution."""

    status: str
    value: float | None
    reason: str | None = None


@dataclass(frozen=True)
class TrialExecution:
    """Canonical child-artifact evidence produced by a trial executor."""

    status: str
    observation: Mapping[str, Any] | None
    child_refs: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()


class OptimizationEngineSession(Protocol):
    """Stateful ask/tell session isolated from Trader orchestration."""

    def ask(self) -> OptimizationSuggestion | None:
        """Return the next unique suggestion, or `None` when exhausted."""

    def tell(self, suggestion: OptimizationSuggestion, outcome: OptimizationOutcome) -> None:
        """Record one closed scalar outcome for future suggestions."""

    def snapshot(self) -> Mapping[str, Any]:
        """Return bounded non-authoritative provider state metadata."""


class OptimizationEngine(Protocol):
    """Provider-neutral parameter proposal engine."""

    def profile(self) -> OptimizationEngineProfile:
        """Return the resolved immutable engine profile."""

    def start(
        self,
        *,
        run_id: str,
        search_space: Sequence[Mapping[str, Any]],
        seed: int,
        max_trials: int,
        prior_trials: Sequence[Mapping[str, Any]],
        direction: str,
    ) -> OptimizationEngineSession:
        """Start or reconcile one sequential ask/tell session."""


class OptimizationTrialExecutor(Protocol):
    """Materialize and execute one proposal through canonical child services."""

    executor_kind: str

    def execute(
        self,
        *,
        plan: Mapping[str, Any],
        parameters: Mapping[str, Any],
        trial_id: str,
        optimization_run_id: str,
    ) -> TrialExecution:
        """Execute one trial and return a closed observation plus lineage refs."""


class ExperimentTrackingSink(Protocol):
    """Optional analytical projection sink; never a canonical evidence store."""

    def profile(self) -> Mapping[str, Any]:
        """Return non-secret configured sink identity."""

    def project(self, canonical_run: Mapping[str, Any]) -> Mapping[str, Any]:
        """Project one supported canonical run and return provider refs."""
