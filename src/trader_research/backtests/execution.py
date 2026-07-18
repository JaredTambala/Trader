"""Specification-only DB-backed backtest execution and result services."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from typing import Any, Mapping, Sequence

from trader.backtest import BacktestResult, BacktestRunner, BacktestSpec, build_backtest_assumptions
from trader.backtest.export_payloads import _build_equity_curve_csv_rows, _build_trade_csv_rows, serialize_backtest_result
from trader.config import Config
from trader.event_store import EventStore
from trader.portfolio import Position
from trader.risk import RiskContext, RiskManager
from trader_standard.risk import NoOpRiskManager
from trader_research.artifact_store import ResearchArtifactStore, ResearchArtifactStoreError, load_artifact_ref
from trader_research.contracts import ArtifactReference, SCHEMA_VERSION, SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import BACKTEST_RUN, COMPARISON_REPORT, IMPLEMENTATION_VERSION, stable_research_id
from trader_research.implementations import ImplementationVersion, instantiate_risk_manager, instantiate_strategy
from trader_research.specifications import (
    load_passed_backtest_specification,
    load_passed_risk_stack_specification,
    load_passed_strategy_specification,
)
from trader_research.specifications.common import parse_datetime


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
) -> ToolEnvelope:
    """Execute one passed canonical backtest specification and persist the complete result."""
    command = RESEARCH_RUN_BACKTEST_SPECIFICATION
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.")
    try:
        specification, validation = load_passed_backtest_specification(
            artifact_store, backtest_specification_validation_ref
        )
        strategy_specification, _ = load_passed_strategy_specification(
            artifact_store, str(specification["strategy_specification_validation_id"])
        )
        strategy_implementation = ImplementationVersion.from_dict(
            load_artifact_ref(
                artifact_store,
                IMPLEMENTATION_VERSION,
                str(strategy_specification["implementation_version_id"]),
            )
        )
        dataset = dict(specification["dataset"]["payload"])
        strategy = instantiate_strategy(
            strategy_implementation,
            symbols=list(dataset["symbols"]),
            asset_class=str(dataset["asset_class"]),
            timeframe=str(dataset["timeframe"]),
            parameters=dict(strategy_specification.get("parameters") or {}),
            sizing=dict(strategy_specification.get("sizing") or {}),
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
            },
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
        result = runner.run(log_cycle_details=bool(specification.get("log_cycle_details")))
    except (ValueError, KeyError, ResearchArtifactStoreError, RuntimeError) as exc:
        return _error(command, "backtest_specification_execution_failed", str(exc))
    except Exception as exc:
        return _error(command, "backtest_specification_execution_failed", f"backtest failed: {exc}")

    status = "passed" if result.total_runs > 0 and result.failed_runs == 0 else "blocked"
    summary = _result_summary(result)
    symbol_metrics = _symbol_metrics(result)
    exposure_summary = _exposure_summary(result, symbol_metrics)
    risk_decisions = _risk_decisions(risk_manager)
    risk_limit_breaches = _risk_breaches(risk_decisions)
    risk_measure_summary = {
        "available_telemetry": _available_risk_telemetry(result, symbol_metrics),
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
        "dataset_id": dataset["dataset_id"],
        "dataset_hash": specification["dataset"]["sha256"],
        "quality_hash": specification["data_quality"]["sha256"],
        "selection_origin_ref": specification.get("selection_origin_ref"),
        "parent_specification_ref": specification.get("parent_specification_ref"),
        "variant_reason": specification.get("variant_reason"),
        "summary": summary,
        "warnings": list(result.warnings),
        "blockers": [] if status == "passed" else ["backtest did not complete all replay cycles"],
        "bundle": {
            "result": serialize_backtest_result(result),
            "metrics": summary,
            "equity_curve": _build_equity_curve_csv_rows(result),
            "trades": _build_trade_csv_rows(result.trades),
            "positions": [asdict(position) for position in result.positions],
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
            },
        },
    }
    try:
        record = artifact_store.save_artifact(
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
    envelope = success_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"backtest_run": payload, "summary": summary},
        artifacts={"backtest_run": record.reference().to_dict()},
        warnings=tuple(result.warnings),
    )
    if status == "passed":
        return envelope
    return ToolEnvelope(
        ok=False,
        command=envelope.command,
        agent_owner=envelope.agent_owner,
        side_effect=envelope.side_effect,
        data=envelope.data,
        artifacts=envelope.artifacts,
        warnings=envelope.warnings,
        errors=({"code": "backtest_run_blocked", "message": payload["blockers"][0]},),
    )


def get_backtest_results(
    *,
    run_id: str | None = None,
    backtest_run_uri: str | None = None,
    artifact_store: ResearchArtifactStore | None,
) -> ToolEnvelope:
    """Read one canonical Postgres backtest run."""
    command = RESEARCH_GET_BACKTEST_RESULTS
    if artifact_store is None:
        return _error(command, "research_artifact_store_required", "A ResearchArtifactStore is required.", read_only=True)
    if bool(run_id) == bool(backtest_run_uri):
        return _error(command, "backtest_run_ref_required", "Exactly one run_id or backtest_run_uri is required.", read_only=True)
    try:
        payload = load_artifact_ref(artifact_store, BACKTEST_RUN, str(backtest_run_uri or run_id or ""))
    except ResearchArtifactStoreError as exc:
        return _error(command, "backtest_result_lookup_failed", str(exc), read_only=True)
    return success_envelope(
        command=command,
        side_effect=SideEffect.READ_ONLY,
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
) -> ToolEnvelope:
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
            artifact_type=COMPARISON_REPORT,
            artifact_id=report_id,
            payload=payload,
            status="passed",
        )
    except (ValueError, ResearchArtifactStoreError) as exc:
        return _error(command, "backtest_comparison_failed", str(exc))
    return success_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
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


def _error(command: str, code: str, message: str, *, read_only: bool = False) -> ToolEnvelope:
    return error_envelope(
        command=command,
        side_effect=SideEffect.READ_ONLY if read_only else SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
    )
