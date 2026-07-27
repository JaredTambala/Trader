"""Specification-only DB-backed backtest execution and result services."""

from __future__ import annotations

from trader_research.foundation import (
    ApplicationResult,
    PredictionDeploymentReader,
    PredictionMapperCatalog,
    error_result,
    json_payload_hash,
    success_result,
)
from trader_research.foundation.artifacts import ArtifactReference, SCHEMA_VERSION

from collections.abc import Iterable
from dataclasses import asdict
from typing import Any, Mapping, Sequence

from trader.backtest import BacktestResult, BacktestRunner, BacktestSpec, build_backtest_assumptions
from trader.backtest.export_payloads import _build_equity_curve_csv_rows, _build_trade_csv_rows, serialize_backtest_result
from trader.config import Config
from trader.event_store import EventStore
from trader.predictions import PredictionRuntimeResolver
from trader.portfolio import Position
from trader.risk import RiskContext, RiskManager
from trader_standard.risk import NoOpRiskManager
from trader_research.foundation.artifacts import (
    ResearchArtifactNotFound,
    ResearchArtifactRecord,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    load_artifact_ref,
)
from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import (
    BACKTEST_RUN,
    COMPARISON_REPORT,
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    IMPLEMENTATION_VERSION,
)
from trader_research.experiments.implementations import ImplementationVersion, instantiate_risk_manager, instantiate_strategy
from trader_research.experiments.specifications import (
    load_passed_backtest_specification,
    load_passed_risk_stack_specification,
    load_passed_strategy_specification,
)
from trader_research.experiments.specifications.common import parse_datetime


RESEARCH_RUN_BACKTEST_SPECIFICATION = "research_run_backtest_specification"
RESEARCH_GET_BACKTEST_RESULTS = "research_get_backtest_results"
RESEARCH_COMPARE_BACKTEST_RESULTS = "research_compare_backtest_results"


class RecordingRiskPipeline(RiskManager):
    """Research-only ordered risk pipeline with bounded decision evidence."""

    def __init__(self, managers: Sequence[tuple[str, RiskManager]]) -> None:
        self._managers = tuple(managers)
        self._decisions: list[dict[str, Any]] = []

    @property
    def decisions(self) -> tuple[Mapping[str, Any], ...]:
        """Return recorded decisions in execution order."""
        return tuple(self._decisions)

    def validate(self, orders: Iterable[Mapping[str, object]], context: RiskContext) -> Sequence[Mapping[str, object]]:
        """Return orders that survive the complete pipeline."""
        approved, _ = self.evaluate(orders, context)
        return approved

    def evaluate(
        self,
        orders: Iterable[Mapping[str, object]],
        context: RiskContext,
    ) -> tuple[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]]:
        """Evaluate managers in order and retain rejection telemetry."""
        approved: Sequence[Mapping[str, object]] = tuple(orders)
        rejected_all: list[Mapping[str, object]] = []
        for index, (implementation_id, manager) in enumerate(self._managers):
            input_count = len(approved)
            next_approved, rejected = manager.evaluate(approved, context)
            approved = tuple(next_approved)
            rejected_tuple = tuple(rejected)
            rejected_all.extend(rejected_tuple)
            self._decisions.append(
                {
                    "manager_index": index,
                    "implementation_version_id": implementation_id,
                    "manager_class": manager.__class__.__name__,
                    "run_id": context.run_id,
                    "cycle_id": context.cycle_id,
                    "decision_ts": context.decision_ts.isoformat(),
                    "input_count": input_count,
                    "approved_count": len(approved),
                    "rejected_count": len(rejected_tuple),
                    "rejected_orders": [_order_evidence(order) for order in rejected_tuple],
                }
            )
            if not approved:
                break
        return approved, tuple(rejected_all)


def run_backtest_specification(
    *,
    event_store: EventStore,
    config: Config,
    backtest_specification_validation_ref: str,
    artifact_store: ResearchArtifactStore | None,
    prediction_deployment_reader: PredictionDeploymentReader | None = None,
    prediction_mapper_catalog: PredictionMapperCatalog | None = None,
    prediction_runtime_resolver: PredictionRuntimeResolver | None = None,
) -> ApplicationResult:
    """Execute one passed canonical backtest specification and persist the complete result."""
    command = RESEARCH_RUN_BACKTEST_SPECIFICATION
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        specification, validation = load_passed_backtest_specification(
            artifact_store,
            backtest_specification_validation_ref,
            prediction_deployment_reader=prediction_deployment_reader,
            prediction_mapper_catalog=prediction_mapper_catalog,
        )
        strategy_specification, _ = load_passed_strategy_specification(
            artifact_store,
            str(specification["strategy_specification_validation_id"]),
            prediction_deployment_reader=prediction_deployment_reader,
            prediction_mapper_catalog=prediction_mapper_catalog,
        )
        strategy_implementation = ImplementationVersion.from_dict(
            load_artifact_ref(
                artifact_store,
                IMPLEMENTATION_VERSION,
                str(strategy_specification["implementation_version_id"]),
            )
        )
        dataset = dict(specification["dataset"]["payload"])
        binding_evidence = list(strategy_specification.get("prediction_bindings") or [])
        if binding_evidence and prediction_runtime_resolver is None:
            raise ValueError("prediction runtime resolver is required for model-backed backtests")
        runtime_bindings = (
            tuple(
                prediction_runtime_resolver.resolve(
                    binding=binding,
                    symbols=list(dataset["symbols"]),
                    asset_class=str(dataset["asset_class"]),
                    timeframe=str(dataset["timeframe"]),
                )
                for binding in binding_evidence
            )
            if prediction_runtime_resolver is not None
            else ()
        )
        strategy = instantiate_strategy(
            strategy_implementation,
            symbols=list(dataset["symbols"]),
            asset_class=str(dataset["asset_class"]),
            timeframe=str(dataset["timeframe"]),
            parameters=dict(strategy_specification.get("parameters") or {}),
            sizing=dict(strategy_specification.get("sizing") or {}),
            prediction_bindings=runtime_bindings if binding_evidence else None,
        )
        risk_manager, risk_lineage = _build_risk_pipeline(artifact_store, specification)
        positions = [
            Position(symbol=str(row["symbol"]), qty=float(row["qty"]), avg_price=row.get("avg_price"))
            for row in specification.get("initial_positions", [])
        ]
        run_id = stable_research_id(
            "backtest_run",
            {
                "backtest_specification_id": specification["backtest_specification_id"],
                "backtest_specification_validation_id": validation["validation_id"],
                "strategy_source_hash": strategy_implementation.source_hash,
                "risk_source_hashes": [item["source_hash"] for item in risk_lineage],
                "prediction_binding_digest": (
                    f"sha256:{json_payload_hash({'bindings': binding_evidence})}"
                    if binding_evidence
                    else None
                ),
            },
        )
        persisted = _load_persisted_backtest_run(
            artifact_store,
            run_id=run_id,
            specification=specification,
            validation=validation,
            strategy_specification=strategy_specification,
            strategy_implementation=strategy_implementation,
            risk_lineage=risk_lineage,
        )
        if persisted is not None:
            return _backtest_application_result(
                command=command,
                payload=persisted.payload,
                artifact_reference=persisted.reference().to_dict(),
            )
        window = dataset["time_range"]
        runner = BacktestRunner(
            config,
            BacktestSpec(
                start=parse_datetime(window["start"], "dataset.start"),
                end=parse_datetime(window["end"], "dataset.end"),
                timeframe=str(dataset["timeframe"]),
                max_runs=specification.get("max_runs"),
            ),
            strategy=strategy,
            risk_manager=risk_manager,
            symbols=tuple(dataset["symbols"]),
            asset_class=str(dataset["asset_class"]),
            event_store=event_store,
            initial_positions=positions,
            initial_cash=float(specification["initial_cash"]),
            config_snapshot=_config_snapshot(config),
            assumptions=build_backtest_assumptions(dict(specification.get("assumptions") or {})),
            run_id=run_id,
            started_at=parse_datetime(window["start"], "dataset.start"),
        )
        backtest_result = runner.run(
            log_cycle_details=bool(specification.get("log_cycle_details"))
        )
    except (ValueError, KeyError, ResearchArtifactStoreError, RuntimeError) as exc:
        return _error(command, "backtest_specification_execution_failed", str(exc))
    except Exception as exc:
        return _error(command, "backtest_specification_execution_failed", f"backtest failed: {exc}")

    status = (
        "passed"
        if backtest_result.total_runs > 0 and backtest_result.failed_runs == 0
        else "blocked"
    )
    summary = _result_summary(backtest_result)
    symbol_metrics = _symbol_metrics(backtest_result)
    exposure_summary = _exposure_summary(backtest_result, symbol_metrics)
    risk_decisions = _risk_decisions(risk_manager)
    risk_limit_breaches = _risk_breaches(risk_decisions)
    risk_measure_summary = {
        "available_telemetry": _available_risk_telemetry(
            backtest_result, symbol_metrics
        ),
        "missing_required_telemetry": [],
        "var": None,
        "cvar": None,
    }
    backtest_kind = "portfolio" if risk_lineage else "baseline"
    payload = {
        "artifact_type": BACKTEST_RUN,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "backtest_kind": backtest_kind,
        "status": status,
        "backtest_specification_id": specification["backtest_specification_id"],
        "backtest_specification_validation_id": validation["validation_id"],
        "strategy_specification_id": strategy_specification["strategy_specification_id"],
        "strategy_implementation_version_id": strategy_implementation.implementation_version_id,
        "risk_stack_specification_id": specification.get("risk_stack_specification_id"),
        "risk_lineage": risk_lineage,
        "prediction_bindings": binding_evidence,
        "dataset_id": dataset["dataset_id"],
        "dataset_hash": specification["dataset"]["sha256"],
        "quality_hash": specification["data_quality"]["sha256"],
        "selection_origin_ref": specification.get("selection_origin_ref"),
        "parent_specification_ref": specification.get("parent_specification_ref"),
        "variant_reason": specification.get("variant_reason"),
        "summary": summary,
        "warnings": list(backtest_result.warnings),
        "blockers": [] if status == "passed" else ["backtest did not complete all replay cycles"],
        "bundle": {
            "result": serialize_backtest_result(backtest_result),
            "metrics": summary,
            "equity_curve": _build_equity_curve_csv_rows(backtest_result),
            "trades": _build_trade_csv_rows(backtest_result.trades),
            "positions": [asdict(position) for position in backtest_result.positions],
            "symbol_metrics": symbol_metrics,
            "exposure_summary": exposure_summary,
            "risk_decisions": risk_decisions,
            "risk_limit_breaches": risk_limit_breaches,
            "risk_measure_summary": risk_measure_summary,
            "provenance": {
                "backtest_specification": specification,
                "backtest_specification_validation": validation,
                "strategy_source_hash": strategy_implementation.source_hash,
                "risk_lineage": risk_lineage,
                "prediction_bindings": binding_evidence,
            },
        },
    }
    try:
        record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[BACKTEST_RUN],
            producer_tool=command,
            artifact_type=BACKTEST_RUN,
            artifact_id=run_id,
            payload=payload,
            status=status,
            metadata={
                "backtest_kind": backtest_kind,
                "dataset_id": dataset["dataset_id"],
                "backtest_specification_id": specification["backtest_specification_id"],
            },
        )
    except ResearchArtifactStoreError as exc:
        return _error(command, "backtest_run_persistence_failed", str(exc))
    return _backtest_application_result(
        command=command,
        payload=payload,
        artifact_reference=record.reference().to_dict(),
    )


def _load_persisted_backtest_run(
    store: ResearchArtifactStore,
    *,
    run_id: str,
    specification: Mapping[str, Any],
    validation: Mapping[str, Any],
    strategy_specification: Mapping[str, Any],
    strategy_implementation: ImplementationVersion,
    risk_lineage: Sequence[Mapping[str, Any]],
) -> ResearchArtifactRecord | None:
    """Return a complete canonical run or fail closed when persisted evidence drifted."""
    try:
        record = store.load_artifact_record(BACKTEST_RUN, run_id)
    except ResearchArtifactNotFound:
        return None

    payload = record.payload
    expected = {
        "artifact_type": BACKTEST_RUN,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "backtest_kind": "portfolio" if risk_lineage else "baseline",
        "backtest_specification_id": specification["backtest_specification_id"],
        "backtest_specification_validation_id": validation["validation_id"],
        "strategy_specification_id": strategy_specification["strategy_specification_id"],
        "strategy_implementation_version_id": strategy_implementation.implementation_version_id,
        "risk_stack_specification_id": specification.get("risk_stack_specification_id"),
        "risk_lineage": list(risk_lineage),
        "prediction_bindings": list(strategy_specification.get("prediction_bindings") or []),
        "dataset_id": specification["dataset"]["payload"]["dataset_id"],
        "dataset_hash": specification["dataset"]["sha256"],
        "quality_hash": specification["data_quality"]["sha256"],
        "selection_origin_ref": specification.get("selection_origin_ref"),
        "parent_specification_ref": specification.get("parent_specification_ref"),
        "variant_reason": specification.get("variant_reason"),
    }
    if record.artifact_type != BACKTEST_RUN or record.artifact_id != run_id:
        raise ValueError("persisted backtest run record identity drifted")
    if record.domain_owner != DOMAIN_OWNER_BY_ARTIFACT_TYPE[BACKTEST_RUN]:
        raise ValueError("persisted backtest run domain authority drifted")
    if record.producer_tool != RESEARCH_RUN_BACKTEST_SPECIFICATION:
        raise ValueError("persisted backtest run producer tool drifted")
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"persisted backtest run {key} drifted")

    status = str(payload.get("status") or "")
    blockers = payload.get("blockers")
    warnings = payload.get("warnings")
    if status not in {"passed", "blocked"} or record.status != status:
        raise ValueError("persisted backtest run status drifted")
    if not isinstance(blockers, list) or not isinstance(warnings, list):
        raise ValueError("persisted backtest run warnings or blockers are malformed")
    if (status == "passed" and blockers) or (status == "blocked" and not blockers):
        raise ValueError("persisted backtest run blockers do not match its status")

    summary = payload.get("summary")
    bundle = payload.get("bundle")
    if not isinstance(summary, Mapping) or summary.get("run_id") != run_id:
        raise ValueError("persisted backtest run summary identity drifted")
    if not isinstance(bundle, Mapping):
        raise ValueError("persisted backtest run bundle is malformed")
    required_bundle_fields = {
        "result",
        "metrics",
        "equity_curve",
        "trades",
        "positions",
        "symbol_metrics",
        "exposure_summary",
        "risk_decisions",
        "risk_limit_breaches",
        "risk_measure_summary",
        "provenance",
    }
    if not required_bundle_fields.issubset(bundle):
        raise ValueError("persisted backtest run bundle is incomplete")
    result = bundle.get("result")
    if not isinstance(result, Mapping) or result.get("run_id") != run_id:
        raise ValueError("persisted backtest result identity drifted")
    if bundle.get("metrics") != summary:
        raise ValueError("persisted backtest metrics drifted from its summary")
    provenance = bundle.get("provenance")
    expected_provenance = {
        "backtest_specification": specification,
        "backtest_specification_validation": validation,
        "strategy_source_hash": strategy_implementation.source_hash,
        "risk_lineage": list(risk_lineage),
        "prediction_bindings": list(strategy_specification.get("prediction_bindings") or []),
    }
    if not isinstance(provenance, Mapping) or dict(provenance) != expected_provenance:
        raise ValueError("persisted backtest run provenance drifted")
    return record


def _backtest_application_result(
    *,
    command: str,
    payload: Mapping[str, Any],
    artifact_reference: Mapping[str, Any],
) -> ApplicationResult:
    """Build the same service result for newly executed and recovered runs."""
    warnings = tuple(str(item) for item in payload.get("warnings", []))
    application_result = success_result(
        command=command,
        data={"backtest_run": payload, "summary": payload.get("summary") or {}},
        artifacts={"backtest_run": artifact_reference},
        warnings=warnings,
    )
    if payload.get("status") == "passed":
        return application_result
    blockers = list(payload.get("blockers") or [])
    return ApplicationResult(
        ok=False,
        operation=application_result.operation,
        data=application_result.data,
        artifacts=application_result.artifacts,
        warnings=application_result.warnings,
        errors=(
            {
                "code": "backtest_run_blocked",
                "message": str(blockers[0] if blockers else "backtest run is blocked"),
            },
        ),
    )


def get_backtest_results(
    *,
    run_id: str | None = None,
    backtest_run_uri: str | None = None,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Read one canonical Postgres backtest run."""
    command = RESEARCH_GET_BACKTEST_RESULTS
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    if bool(run_id) == bool(backtest_run_uri):
        return _error(command, "backtest_run_ref_required", "Exactly one run_id or backtest_run_uri is required.")
    try:
        payload = load_artifact_ref(artifact_store, BACKTEST_RUN, str(backtest_run_uri or run_id or ""))
    except ResearchArtifactStoreError as exc:
        return _error(command, "backtest_result_lookup_failed", str(exc))
    return success_result(
        command=command,
        data={"backtest_run": payload, "summary": payload.get("summary") or {}, "bundle": payload.get("bundle") or {}},
        artifacts={
            "backtest_run": ArtifactReference(
                artifact_type=BACKTEST_RUN,
                uri=f"research://postgres/{BACKTEST_RUN}/{payload['run_id']}",
                metadata={"run_id": payload["run_id"], "status": payload.get("status")},
            ).to_dict()
        },
        warnings=tuple(str(item) for item in payload.get("warnings", [])),
    )


def compare_backtest_results(
    *,
    backtest_run_refs: Sequence[str],
    ranking_metric: str = "sharpe",
    sort_order: str = "descending",
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Compare canonical backtest runs and persist the ranking report."""
    command = RESEARCH_COMPARE_BACKTEST_RESULTS
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        if not 2 <= len(backtest_run_refs) <= 50:
            raise ValueError("backtest_run_refs must contain between 2 and 50 refs")
        if sort_order not in {"ascending", "descending"}:
            raise ValueError("sort_order must be ascending or descending")
        runs = [load_artifact_ref(artifact_store, BACKTEST_RUN, ref) for ref in backtest_run_refs]
        rows = []
        for run in runs:
            value = (run.get("summary") or {}).get(ranking_metric)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"run {run.get('run_id')} lacks numeric metric {ranking_metric}")
            rows.append({"run_id": run["run_id"], "status": run.get("status"), "value": float(value)})
        rows.sort(key=lambda row: (row["value"], row["run_id"]), reverse=sort_order == "descending")
        ranked = [{**row, "rank": index + 1} for index, row in enumerate(rows)]
        report_id = stable_research_id(
            "backtest_comparison", {"run_ids": sorted(row["run_id"] for row in rows), "metric": ranking_metric, "order": sort_order}
        )
        payload = {
            "artifact_type": COMPARISON_REPORT,
            "schema_version": SCHEMA_VERSION,
            "comparison_id": report_id,
            "status": "passed",
            "ranking_metric": ranking_metric,
            "sort_order": sort_order,
            "ranked_runs": ranked,
        }
        record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[COMPARISON_REPORT],
            producer_tool=command,
            artifact_type=COMPARISON_REPORT,
            artifact_id=report_id,
            payload=payload,
            status="passed",
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return _error(command, "backtest_comparison_failed", str(exc))
    return success_result(
        command=command,
        data={"comparison_report": payload},
        artifacts={"comparison_report": record.reference().to_dict()},
    )


def _build_risk_pipeline(
    store: ResearchArtifactStore,
    specification: Mapping[str, Any],
) -> tuple[RiskManager, list[dict[str, Any]]]:
    validation_id = specification.get("risk_stack_specification_validation_id")
    if not validation_id:
        return NoOpRiskManager(), []
    risk_specification, _ = load_passed_risk_stack_specification(store, str(validation_id))
    managers: list[tuple[str, RiskManager]] = []
    lineage: list[dict[str, Any]] = []
    for row in risk_specification.get("risk_managers", []):
        implementation = ImplementationVersion.from_dict(
            load_artifact_ref(store, IMPLEMENTATION_VERSION, str(row["implementation_version_id"]))
        )
        managers.append(
            (
                implementation.implementation_version_id,
                instantiate_risk_manager(implementation, parameters=dict(row.get("parameters") or {})),
            )
        )
        lineage.append(
            {
                "order": row["order"],
                "implementation_version_id": implementation.implementation_version_id,
                "implementation_validation_id": row["implementation_validation_id"],
                "source_hash": implementation.source_hash,
                "parameters": dict(row.get("parameters") or {}),
            }
        )
    return RecordingRiskPipeline(managers), lineage


def _result_summary(result: BacktestResult) -> dict[str, Any]:
    return {
        "run_id": result.run_id,
        "total_runs": result.total_runs,
        "failed_runs": result.failed_runs,
        "total_return": result.strategy_performance.total_return,
        "sharpe": result.strategy_performance.sharpe,
        "max_drawdown": result.strategy_performance.max_drawdown,
        "turnover": result.strategy_performance.turnover,
        "fees": result.total_fees,
        "slippage": result.total_slippage,
        "alpha": result.alpha,
        "beta": result.beta,
        "warnings_count": len(result.warnings),
        "trade_count": len(result.trades),
    }


def _symbol_metrics(result: BacktestResult) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {symbol: _empty_symbol_metrics() for symbol in result.symbols}
    for trade in result.trades:
        row = rows.setdefault(trade.symbol, _empty_symbol_metrics())
        qty = abs(float(trade.fill_qty or 0.0))
        notional = abs(float(trade.notional or 0.0))
        row["trade_count"] += 1
        row["gross_notional"] += notional
        row["fees"] += float(trade.fee_amount or 0.0)
        row["slippage"] += float(trade.slippage_amount or 0.0)
        row["realized_pnl"] += float(trade.realized_pnl or 0.0)
        side = str(trade.side).lower()
        if side == "buy":
            row["buy_qty"] += qty
        elif side == "sell":
            row["sell_qty"] += qty
    end_equity = result.strategy_performance.end_equity
    for position in result.positions:
        row = rows.setdefault(position.symbol, _empty_symbol_metrics())
        market_value = position.market_value
        row.update(
            {
                "final_qty": position.qty,
                "final_notional": market_value,
                "final_weight": market_value / end_equity if market_value is not None and end_equity else None,
            }
        )
    return {symbol: rows[symbol] for symbol in sorted(rows)}


def _empty_symbol_metrics() -> dict[str, Any]:
    return {
        "trade_count": 0,
        "buy_qty": 0.0,
        "sell_qty": 0.0,
        "gross_notional": 0.0,
        "fees": 0.0,
        "slippage": 0.0,
        "realized_pnl": 0.0,
        "final_qty": 0.0,
        "final_notional": None,
        "final_weight": None,
    }


def _exposure_summary(result: BacktestResult, symbol_metrics: Mapping[str, Any]) -> dict[str, Any]:
    weights = [abs(float(row["final_weight"])) for row in symbol_metrics.values() if row.get("final_weight") is not None]
    performance = result.strategy_performance
    return {
        "position_count": result.position_count,
        "long_positions": result.long_positions,
        "short_positions": result.short_positions,
        "final_net_notional": result.net_notional,
        "final_gross_notional": result.gross_notional,
        "avg_net_exposure": performance.avg_net_exposure,
        "avg_gross_exposure": performance.avg_gross_exposure,
        "avg_invested_pct": performance.avg_invested_pct,
        "final_concentration": max(weights) if weights else None,
    }


def _risk_decisions(manager: RiskManager) -> dict[str, Any]:
    decisions = manager.decisions if isinstance(manager, RecordingRiskPipeline) else ()
    return {
        "decision_count": len(decisions),
        "rejected_order_count": sum(int(item.get("rejected_count") or 0) for item in decisions),
        "decisions": list(decisions),
    }


def _risk_breaches(summary: Mapping[str, Any]) -> dict[str, Any]:
    breaches = [
        {
            "source": "risk_manager_rejection",
            "implementation_version_id": decision.get("implementation_version_id"),
            "run_id": decision.get("run_id"),
            "cycle_id": decision.get("cycle_id"),
            "decision_ts": decision.get("decision_ts"),
            **dict(order),
        }
        for decision in summary.get("decisions", [])
        for order in decision.get("rejected_orders", [])
    ]
    return {"breach_count": len(breaches), "breaches": breaches}


def _available_risk_telemetry(result: BacktestResult, symbol_metrics: Mapping[str, Any]) -> list[str]:
    names = {"portfolio_value", "gross_exposure", "per_symbol_exposure"}
    if result.equity_curve:
        names.add("equity_curve")
    if len(result.equity_curve) > 1:
        names.add("portfolio_returns")
    if result.strategy_performance.max_drawdown is not None:
        names.add("drawdown")
    if not symbol_metrics:
        names.discard("per_symbol_exposure")
    return sorted(names)


def _order_evidence(order: Mapping[str, object]) -> dict[str, Any]:
    return {
        key: order.get(key)
        for key in ("client_order_id", "symbol", "side", "qty", "order_type", "rejection_reason")
        if order.get(key) is not None
    }


def _config_snapshot(config: Config) -> dict[str, Any]:
    payload = asdict(config)
    for key in ("alpaca_api_key", "alpaca_secret_key", "pg_dsn", "pg_password"):
        payload.pop(key, None)
    return payload


def _error(command: str, code: str, message: str) -> ApplicationResult:
    return error_result(
        command=command,
        code=code,
        message=message,
    )
