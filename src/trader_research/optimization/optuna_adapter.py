"""Optional Optuna ask/tell adapter isolated from canonical optimization code."""

from __future__ import annotations

from importlib import metadata
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from trader_research.artifact_store import json_payload_hash

from .contracts import OptimizationEngineProfile, OptimizationOutcome, OptimizationSuggestion


class OptunaOptimizationEngine:
    """Seeded sequential TPE engine backed by an adapter-owned Optuna schema."""

    def __init__(
        self,
        *,
        storage_url: str,
        profile_name: str = "optuna_tpe",
        study_prefix: str = "trader",
        schema_name: str = "trader_optuna",
        role_name: str = "trader_optuna_writer",
    ) -> None:
        self._storage_url = str(storage_url)
        self._profile_name = str(profile_name)
        self._study_prefix = str(study_prefix)
        self._schema_name = str(schema_name)
        self._role_name = str(role_name)

    def profile(self) -> OptimizationEngineProfile:
        """Return availability without importing Optuna at server startup."""
        try:
            version = metadata.version("optuna")
            reason = self._configuration_blocker()
            available = reason is None
        except metadata.PackageNotFoundError:
            version = "unavailable"
            available = False
            reason = "Install the optional optimization dependency to use Optuna"
        return OptimizationEngineProfile(
            profile_name=self._profile_name,
            provider="optuna",
            algorithm="tpe",
            provider_version=version,
            configuration_digest=json_payload_hash(
                {
                    "profile_name": self._profile_name,
                    "study_prefix": self._study_prefix,
                    "schema_name": self._schema_name,
                    "role_name": self._role_name,
                    "storage_identity": _storage_identity(self._storage_url),
                }
            ),
            capabilities=("ask_tell", "adaptive", "sequential", "single_objective", "no_pruning"),
            available=available,
            reason=reason,
        )

    def start(
        self,
        *,
        run_id: str,
        search_space: Sequence[Mapping[str, Any]],
        seed: int,
        max_trials: int,
        prior_trials: Sequence[Mapping[str, Any]],
        direction: str,
    ) -> "_OptunaSession":
        """Create or reconcile the adapter-owned study with canonical trials."""
        import optuna  # type: ignore[import-not-found]

        blocker = self._configuration_blocker()
        if blocker:
            raise ValueError(blocker)
        sampler = optuna.samplers.TPESampler(seed=seed, multivariate=False)
        storage = optuna.storages.RDBStorage(
            url=self._storage_url,
            engine_kwargs={"connect_args": {"options": f"-csearch_path={self._schema_name}"}},
        )
        study = optuna.create_study(
            study_name=f"{self._study_prefix}-{run_id}",
            storage=storage,
            load_if_exists=True,
            sampler=sampler,
            direction="maximize" if direction == "maximize" else "minimize",
        )
        return _OptunaSession(study, search_space, max_trials, prior_trials)

    def _configuration_blocker(self) -> str | None:
        if not self._storage_url:
            return "Optuna storage_url is not configured"
        if not self._schema_name or self._schema_name == "public":
            return "Optuna requires a dedicated non-public schema"
        if not self._role_name:
            return "Optuna requires a dedicated writer role"
        parsed = urlparse(self._storage_url)
        if not parsed.scheme.startswith("postgres"):
            return "Optuna requires PostgreSQL storage"
        if parsed.username != self._role_name:
            return "Optuna storage_url must authenticate as the configured dedicated writer role"
        return None


def _storage_identity(storage_url: str) -> Mapping[str, Any]:
    """Return a credential-free identity used to detect provider configuration drift."""
    parsed = urlparse(storage_url)
    return {
        "scheme": parsed.scheme,
        "hostname": parsed.hostname,
        "port": parsed.port,
        "database": parsed.path.lstrip("/"),
    }


class _OptunaSession:
    def __init__(self, study: Any, search_space: Sequence[Mapping[str, Any]], max_trials: int, prior_trials: Sequence[Mapping[str, Any]]) -> None:
        self._study = study
        self._search_space = tuple(dict(item) for item in search_space)
        self._max_trials = max_trials
        self._tokens: dict[str, Any] = {}
        canonical = len(prior_trials)
        completed = len([trial for trial in study.trials if trial.state.name in {"COMPLETE", "FAIL"}])
        if completed != canonical:
            raise ValueError(
                f"Optuna operational state has {completed} terminal trials but Trader has {canonical}; resume fails closed"
            )

    def ask(self) -> OptimizationSuggestion | None:
        if len(self._study.trials) >= self._max_trials:
            return None
        trial = self._study.ask()
        parameters: dict[str, Any] = {}
        for dimension in self._search_space:
            path = str(dimension["path"])
            kind = str(dimension["type"])
            if kind == "categorical":
                parameters[path] = trial.suggest_categorical(path, list(dimension["values"]))
            elif kind == "integer":
                parameters[path] = trial.suggest_int(
                    path, int(dimension["low"]), int(dimension["high"]), step=int(dimension.get("step", 1))
                )
            else:
                parameters[path] = trial.suggest_float(
                    path,
                    float(dimension["low"]),
                    float(dimension["high"]),
                    step=float(dimension["step"]),
                    log=bool(dimension.get("log", False)),
                )
        token = f"optuna-{trial.number}"
        self._tokens[token] = trial
        return OptimizationSuggestion(engine_trial_id=token, parameters=parameters)

    def tell(self, suggestion: OptimizationSuggestion, outcome: OptimizationOutcome) -> None:
        import optuna

        trial = self._tokens.pop(suggestion.engine_trial_id)
        if outcome.status == "passed" and outcome.value is not None:
            self._study.tell(trial, outcome.value)
        else:
            self._study.tell(trial, state=optuna.trial.TrialState.FAIL)

    def snapshot(self) -> Mapping[str, Any]:
        return {
            "study_name": self._study.study_name,
            "trial_count": len(self._study.trials),
            "storage": "configured_optuna_rdb",
        }
