"""Provide deterministic optimization engines and their profile registry.

Grid and seeded-random engines implement the common sequential ask/tell
contract over validated finite dimensions. Registry lookups expose only
configured immutable profiles and fail clearly for unavailable engines.
"""

from __future__ import annotations

from itertools import product
import json
import random
from typing import Any, Mapping, Sequence

from trader_research.foundation import json_payload_hash

from .contracts import (
    OptimizationEngine,
    OptimizationEngineProfile,
    OptimizationEngineSession,
    OptimizationOutcome,
    OptimizationSuggestion,
)


class OptimizationEngineRegistry:
    """Configured engine profiles available to generic research tools."""

    def __init__(self, engines: Sequence[OptimizationEngine] | None = None) -> None:
        builtins: list[OptimizationEngine] = [GridOptimizationEngine(), RandomOptimizationEngine()]
        for engine in engines or ():
            builtins.append(engine)
        self._engines = {engine.profile().profile_name: engine for engine in builtins}

    def profiles(self) -> tuple[OptimizationEngineProfile, ...]:
        """Return profiles in stable name order."""
        return tuple(self._engines[name].profile() for name in sorted(self._engines))

    def get(self, profile_name: str) -> OptimizationEngine:
        """Return one available configured engine."""
        try:
            engine = self._engines[str(profile_name)]
        except KeyError as exc:
            raise ValueError(f"unknown optimizer profile: {profile_name}") from exc
        profile = engine.profile()
        if not profile.available:
            raise ValueError(profile.reason or f"optimizer profile is unavailable: {profile_name}")
        return engine


class GridOptimizationEngine:
    """Deterministic exhaustive finite grid engine."""

    def profile(self) -> OptimizationEngineProfile:
        """Return the maintained grid profile."""
        return _profile("builtin_grid", "grid")

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
        """Create a finite Cartesian ask/tell session for a canonical plan.

        Every declared dimension is validated and enumerated, and already
        completed parameter sets are reconciled. The full grid must fit within
        ``max_trials`` or the engine rejects the plan.
        """
        del seed, direction
        values = [_dimension_values(dimension) for dimension in search_space]
        cardinality = 1
        for candidates in values:
            cardinality *= len(candidates)
        if cardinality > max_trials:
            raise ValueError(
                f"builtin_grid requires max_trials >= full grid cardinality ({cardinality}); use builtin_random for a budgeted subset"
            )
        paths = [str(dimension["path"]) for dimension in search_space]
        suggestions = [dict(zip(paths, combination)) for combination in product(*values)]
        return _SequenceSession(run_id, suggestions, prior_trials, algorithm="grid")


class RandomOptimizationEngine:
    """Deterministic duplicate-free seeded random engine."""

    def profile(self) -> OptimizationEngineProfile:
        """Return the maintained random profile."""
        return _profile("builtin_random", "seeded_random")

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
        """Create a seeded permutation over the plan's finite parameter space.

        The complete canonical grid is enumerated, then shuffled with ``seed`` so
        separate processes produce the same suggestion order. The session is
        truncated to the trial budget and reconciled with prior trials.
        """
        del direction
        values = [_dimension_values(dimension) for dimension in search_space]
        paths = [str(dimension["path"]) for dimension in search_space]
        suggestions = [dict(zip(paths, combination)) for combination in product(*values)]
        rng = random.Random(seed)
        rng.shuffle(suggestions)
        return _SequenceSession(run_id, suggestions[:max_trials], prior_trials, algorithm="seeded_random")


class _SequenceSession:
    def __init__(
        self,
        run_id: str,
        suggestions: Sequence[Mapping[str, Any]],
        prior_trials: Sequence[Mapping[str, Any]],
        *,
        algorithm: str,
    ) -> None:
        completed = {_parameter_key(trial.get("parameters") or {}) for trial in prior_trials}
        self._pending = [dict(item) for item in suggestions if _parameter_key(item) not in completed]
        self._run_id = run_id
        self._algorithm = algorithm
        self._asked = len(prior_trials)
        self._told = len(prior_trials)

    def ask(self) -> OptimizationSuggestion | None:
        if not self._pending:
            return None
        parameters = self._pending.pop(0)
        trial_id = f"{self._algorithm}-{self._asked:06d}-{json_payload_hash(parameters)[:12]}"
        self._asked += 1
        return OptimizationSuggestion(engine_trial_id=trial_id, parameters=parameters)

    def tell(self, suggestion: OptimizationSuggestion, outcome: OptimizationOutcome) -> None:
        del suggestion, outcome
        self._told += 1

    def snapshot(self) -> Mapping[str, Any]:
        return {
            "run_id": self._run_id,
            "algorithm": self._algorithm,
            "asked": self._asked,
            "told": self._told,
            "remaining": len(self._pending),
        }


def _profile(name: str, algorithm: str) -> OptimizationEngineProfile:
    payload = {"provider": "trader", "algorithm": algorithm, "provider_version": "1"}
    return OptimizationEngineProfile(
        profile_name=name,
        provider="trader",
        algorithm=algorithm,
        provider_version="1",
        configuration_digest=json_payload_hash(payload),
        capabilities=("ask_tell", "deterministic", "sequential", "single_objective", "no_pruning"),
    )


def dimension_values(dimension: Mapping[str, Any]) -> tuple[Any, ...]:
    """Validate and enumerate one finite optimization dimension.

    The public wrapper applies the same categorical, integer, and numeric rules as
    maintained engines and returns the canonical ordered candidate tuple.
    """
    return _dimension_values(dimension)


def _dimension_values(dimension: Mapping[str, Any]) -> tuple[Any, ...]:
    kind = str(dimension.get("type") or "").strip()
    if kind == "categorical":
        categorical_values = dimension.get("values")
        if (
            not isinstance(categorical_values, Sequence)
            or isinstance(categorical_values, (str, bytes))
            or not categorical_values
        ):
            raise ValueError("categorical dimensions require non-empty values")
        return tuple(categorical_values)
    low = dimension.get("low")
    high = dimension.get("high")
    step = dimension.get("step", 1 if kind == "integer" else None)
    if isinstance(low, bool) or isinstance(high, bool) or not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
        raise ValueError(f"{kind} dimensions require numeric low and high")
    if float(low) > float(high):
        raise ValueError("dimension low must be <= high")
    if step is None or isinstance(step, bool) or not isinstance(step, (int, float)) or float(step) <= 0:
        raise ValueError("numeric dimensions require a positive finite step in v1")
    numeric_values: list[Any] = []
    current = float(low)
    while current <= float(high) + float(step) / 1_000_000:
        numeric_values.append(int(round(current)) if kind == "integer" else round(current, 12))
        current += float(step)
        if len(numeric_values) > 10_000:
            raise ValueError("one search dimension cannot expand beyond 10000 values")
    if kind not in {"integer", "number"}:
        raise ValueError(f"unsupported search dimension type: {kind}")
    return tuple(numeric_values)


def _parameter_key(parameters: Mapping[str, Any]) -> str:
    return json.dumps(parameters, sort_keys=True, separators=(",", ":"), default=str)
