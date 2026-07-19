"""Canonical backtest trial executor for provider-neutral optimization."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from trader.config import Config
from trader.event_store import EventStore
from trader_research.artifact_store import ResearchArtifactStore
from trader_research.backtests.execution import run_backtest_specification
from trader_research.specifications import (
    create_backtest_specification,
    create_risk_stack_specification,
    create_strategy_specification,
    load_passed_backtest_specification,
    load_passed_risk_stack_specification,
    load_passed_strategy_specification,
    validate_backtest_specification,
    validate_risk_stack_specification,
    validate_strategy_specification,
)

from .contracts import TrialExecution


class BacktestOptimizationTrialExecutor:
    """Materialize parameter proposals as immutable child specifications and runs."""

    executor_kind = "backtest_specification"

    def __init__(self, *, event_store: EventStore, config: Config, artifact_store: ResearchArtifactStore) -> None:
        self._event_store = event_store
        self._config = config
        self._store = artifact_store

    def execute(
        self,
        *,
        plan: Mapping[str, Any],
        parameters: Mapping[str, Any],
        trial_id: str,
        optimization_run_id: str,
    ) -> TrialExecution:
        """Execute a child selection-region backtest for one suggestion."""
        try:
            base, _ = load_passed_backtest_specification(
                self._store, str(plan["base_backtest_specification_validation_id"])
            )
            strategy, _ = load_passed_strategy_specification(
                self._store, str(base["strategy_specification_validation_id"])
            )
            child_strategy = deepcopy(dict(strategy))
            risk: dict[str, Any] | None = None
            if base.get("risk_stack_specification_validation_id"):
                loaded_risk, _ = load_passed_risk_stack_specification(
                    self._store, str(base["risk_stack_specification_validation_id"])
                )
                risk = deepcopy(dict(loaded_risk))
            for path, value in parameters.items():
                _apply_path(child_strategy, risk, str(path), value)

            created_strategy = create_strategy_specification(
                implementation_validation_ref=str(child_strategy["implementation_validation_id"]),
                parameters=dict(child_strategy.get("parameters") or {}),
                sizing=dict(child_strategy.get("sizing") or {}),
                portfolio_mode=str(child_strategy.get("portfolio_mode") or "single_or_multi_asset"),
                required_runtime_context=dict(child_strategy.get("required_runtime_context") or {}),
                execution_assumptions=dict(child_strategy.get("execution_assumptions") or {}),
                tunable_fields=list(child_strategy.get("tunable_fields") or []),
                provenance_refs=[
                    {
                        "artifact_type": "parameter_optimization_trial",
                        "artifact_id": trial_id,
                        "optimization_run_id": optimization_run_id,
                    }
                ],
                artifact_store=self._store,
            )
            child_strategy_id = _data(created_strategy, "strategy_specification")["strategy_specification_id"]
            validated_strategy = validate_strategy_specification(
                strategy_specification_id=child_strategy_id,
                artifact_store=self._store,
            )
            child_strategy_validation_id = _data(
                validated_strategy, "strategy_specification_validation_report"
            )["validation_id"]

            child_risk_validation_id = None
            child_risk_id = None
            if risk is not None:
                risk_items = [
                    {
                        "implementation_validation_ref": row["implementation_validation_id"],
                        "parameters": dict(row.get("parameters") or {}),
                        "tunable_fields": list(row.get("tunable_fields") or []),
                    }
                    for row in risk.get("risk_managers", [])
                ]
                created_risk = create_risk_stack_specification(
                    risk_managers=risk_items,
                    execution_assumptions=dict(risk.get("execution_assumptions") or {}),
                    provenance_refs=[
                        {
                            "artifact_type": "parameter_optimization_trial",
                            "artifact_id": trial_id,
                            "optimization_run_id": optimization_run_id,
                        }
                    ],
                    artifact_store=self._store,
                )
                child_risk_id = _data(created_risk, "risk_stack_specification")["risk_stack_specification_id"]
                validated_risk = validate_risk_stack_specification(
                    risk_stack_specification_id=child_risk_id,
                    artifact_store=self._store,
                )
                child_risk_validation_id = _data(
                    validated_risk, "risk_stack_specification_validation_report"
                )["validation_id"]

            created_backtest = create_backtest_specification(
                strategy_specification_validation_ref=child_strategy_validation_id,
                risk_stack_specification_validation_ref=child_risk_validation_id,
                dataset_manifest=dict(base["dataset"]["payload"]),
                data_quality_report=dict(base["data_quality"]["payload"]),
                assumptions=dict(base.get("assumptions") or {}),
                initial_cash=float(base["initial_cash"]),
                initial_positions=list(base.get("initial_positions") or []),
                benchmark=dict(base.get("benchmark") or {}),
                deterministic_seed=int(base.get("deterministic_seed") or 0),
                max_runs=base.get("max_runs"),
                log_cycle_details=bool(base.get("log_cycle_details")),
                runtime_limits=dict(base.get("runtime_limits") or {}),
                parent_specification_ref=str(base["backtest_specification_id"]),
                selection_origin_ref=optimization_run_id,
                artifact_store=self._store,
            )
            child_backtest_id = _data(created_backtest, "backtest_specification")["backtest_specification_id"]
            validated_backtest = validate_backtest_specification(
                backtest_specification_id=child_backtest_id,
                artifact_store=self._store,
            )
            child_backtest_validation_id = _data(
                validated_backtest, "backtest_specification_validation_report"
            )["validation_id"]
            run = run_backtest_specification(
                event_store=self._event_store,
                config=self._config,
                backtest_specification_validation_ref=child_backtest_validation_id,
                artifact_store=self._store,
            )
            run_payload = _data(run, "backtest_run")
            observation = backtest_optimization_observation(run_payload, trial_id)
            return TrialExecution(
                status="passed" if run.ok else "blocked",
                observation=observation,
                child_refs={
                    "strategy_specification_id": child_strategy_id,
                    "strategy_specification_validation_id": child_strategy_validation_id,
                    "risk_stack_specification_id": child_risk_id,
                    "risk_stack_specification_validation_id": child_risk_validation_id,
                    "backtest_specification_id": child_backtest_id,
                    "backtest_specification_validation_id": child_backtest_validation_id,
                    "backtest_run_id": run_payload["run_id"],
                },
                warnings=tuple(run.warnings),
                blockers=tuple(str(item) for item in run_payload.get("blockers", [])),
            )
        except Exception as exc:
            return TrialExecution(status="blocked", observation=None, blockers=(str(exc),))


def _apply_path(
    strategy: dict[str, Any],
    risk: dict[str, Any] | None,
    path: str,
    value: Any,
) -> None:
    parts = [part for part in path.split("/") if part]
    if len(parts) == 3 and parts[0] == "strategy" and parts[1] in {"parameters", "sizing"}:
        strategy.setdefault(parts[1], {})[parts[2]] = value
        return
    if len(parts) == 4 and parts[0] == "risk" and parts[2] == "parameters" and risk is not None:
        index = int(parts[1])
        risk["risk_managers"][index].setdefault("parameters", {})[parts[3]] = value
        return
    raise ValueError(f"unsupported trial parameter path: {path}")


def backtest_optimization_observation(
    run: Mapping[str, Any], trial_id: str
) -> dict[str, Any]:
    """Derive the closed optimization observation from one canonical backtest run."""
    bundle = dict(run.get("bundle") or {})
    summary = dict(run.get("summary") or {})
    metrics = {
        str(key): value
        for key, value in summary.items()
        if value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))
    }
    return {
        "schema_version": "1.0",
        "status": run.get("status"),
        "metrics": metrics,
        "counts": {
            "trade_count": int(summary.get("trade_count") or 0),
            "total_runs": int(summary.get("total_runs") or 0),
            "failed_runs": int(summary.get("failed_runs") or 0),
        },
        "costs": {
            "fees": summary.get("fees"),
            "slippage": summary.get("slippage"),
        },
        "exposure": dict(bundle.get("exposure_summary") or {}),
        "risk": {
            "decisions": dict(bundle.get("risk_decisions") or {}),
            "breaches": dict(bundle.get("risk_limit_breaches") or {}),
            "measures": dict(bundle.get("risk_measure_summary") or {}),
        },
        "quality": {"complete": run.get("status") == "passed", "blockers": list(run.get("blockers") or [])},
        "constraints": {},
        "lineage": {"trial_id": trial_id, "backtest_run_id": run.get("run_id"), "fold": "selection"},
    }


def _data(envelope: Any, key: str) -> Mapping[str, Any]:
    if not envelope.ok:
        message = envelope.errors[0]["message"] if envelope.errors else f"{envelope.command} failed"
        raise ValueError(str(message))
    value = envelope.data.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{envelope.command} did not return {key}")
    return value
