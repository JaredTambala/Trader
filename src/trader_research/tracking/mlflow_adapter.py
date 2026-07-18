"""Optional MLflow sink for analytical projections of canonical Trader studies."""

from __future__ import annotations

from importlib import metadata
from typing import Any, Mapping
from urllib.parse import urlparse

from trader_research.artifact_store import json_payload_hash


class MLflowExperimentTrackingSink:
    """Project optimization parent/child runs into one configured MLflow namespace."""

    def __init__(self, *, tracking_uri: str, experiment_name: str) -> None:
        self._tracking_uri = str(tracking_uri)
        self._experiment_name = str(experiment_name)

    def profile(self) -> Mapping[str, Any]:
        """Return configured identity without exposing connection credentials."""
        try:
            version = metadata.version("mlflow")
            available = bool(self._tracking_uri and self._experiment_name)
        except metadata.PackageNotFoundError:
            version = "unavailable"
            available = False
        return {
            "profile_name": "mlflow_backtest_optimization",
            "provider": "mlflow",
            "provider_version": version,
            "namespace": self._experiment_name,
            "configuration_digest": json_payload_hash(
                {
                    "tracking_identity": _tracking_identity(self._tracking_uri),
                    "experiment_name": self._experiment_name,
                }
            ),
            "available": available,
            "authority": "analytical_projection_only",
        }

    def project(self, canonical_run: Mapping[str, Any]) -> Mapping[str, Any]:
        """Log a parent study and child trial runs derived only from canonical payloads."""
        import mlflow  # type: ignore[import-not-found]

        profile = self.profile()
        if not profile["available"]:
            raise ValueError("MLflow tracking sink is unavailable")
        run = dict(canonical_run["parameter_optimization_run"])
        mlflow.set_tracking_uri(self._tracking_uri)
        mlflow.set_experiment(self._experiment_name)
        child_refs: list[dict[str, Any]] = []
        with mlflow.start_run(run_name=str(run["optimization_run_id"])) as parent:
            mlflow.set_tags(
                {
                    "trader.authority": "projection",
                    "trader.optimization_run_id": str(run["optimization_run_id"]),
                    "trader.optimization_plan_id": str(run["optimization_plan_id"]),
                }
            )
            for trial in canonical_run.get("trials", []):
                with mlflow.start_run(
                    run_name=str(trial["trial_id"]),
                    nested=True,
                ) as child:
                    mlflow.log_params({str(key): value for key, value in dict(trial.get("parameters") or {}).items()})
                    if isinstance(trial.get("objective_value"), (int, float)):
                        mlflow.log_metric("objective_value", float(trial["objective_value"]))
                    mlflow.set_tags(
                        {
                            "trader.authority": "projection",
                            "trader.trial_id": str(trial["trial_id"]),
                            "trader.trial_status": str(trial.get("status")),
                        }
                    )
                    child_refs.append({"trial_id": trial["trial_id"], "mlflow_run_id": child.info.run_id})
            return {
                "mlflow_parent_run_id": parent.info.run_id,
                "mlflow_experiment_name": self._experiment_name,
                "child_runs": child_refs,
            }


def _tracking_identity(tracking_uri: str) -> Mapping[str, Any]:
    """Return a credential-free MLflow endpoint identity."""
    parsed = urlparse(tracking_uri)
    return {
        "scheme": parsed.scheme,
        "hostname": parsed.hostname,
        "port": parsed.port,
        "path": parsed.path,
    }
