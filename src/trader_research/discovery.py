"""AI/tool research discovery orchestration."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader.backtest import BacktestRunner, BacktestSpec, build_backtest_assumptions
from trader.config import Config, build_config
from trader.data import EventStore, build_event_store
from trader.data_quality import run_data_quality, write_data_quality_report
from trader.identifiers import deterministic_run_session_id
from trader.market_data_backfill import BackfillSpec, MarketDataBackfillRunner, _parse_timeframe, _resolve_since
from trader.portfolio import Position
from trader_research.research import (
    attach_research_metadata,
    build_run_provenance,
    comparison_payload,
    experiment_id_from_name,
    experiment_run_id,
    experiment_slug,
    export_research_bundle,
    result_summary,
)
from trader.sample_data import load_sample_market_data_csv
from trader.strategy_metadata import resolve_strategy_info
from trader_research.artifacts import load_operator_context, load_strategy_artifacts
from trader_research.contracts import SideEffect, ToolEnvelope, success_envelope, write_json_artifact
from trader_research.recommendations import RecommendationSettings, build_recommendations
from trader_research.suites import SuiteMember, build_suite_members
from trader_standard.risk import NoOpRiskManager
from trader_standard.strategies import (
    build_bollinger_band_strategy,
    build_mean_reversion_strategy,
    build_trend_following_strategy,
)


@dataclass(frozen=True)
class DiscoveryRequest:
    """User-facing discovery request after transport-level parsing.

    The request fixes the symbol universe, bar semantics, strategy families, data
    loading mode, and artifact locations that the supervisor workflow will use.
    Validation happens before any local mutation so dry runs can return a data
    plan and suite plan without opening the event store, while non-dry runs use
    the same normalized values for backfill, quality checks, backtests, and
    recommendation artifacts.
    """

    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    strategy_families: tuple[str, ...]
    data_mode: str = "existing"
    since: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    max_runs: int = 25
    cost_profile: str = "conservative"
    risk_profile: str = "default"
    output_dir: str = "artifacts/discovery"
    experiment_name: str = "demo_discovery"
    dry_run: bool = False
    operator_context_paths: tuple[str, ...] = field(default_factory=tuple)
    prior_artifact_paths: tuple[str, ...] = field(default_factory=tuple)
    sample_csv: str = "examples/data/demo_stock_1min.csv"


def run_discovery(
    config_data: Mapping[str, Any],
    request: DiscoveryRequest,
) -> ToolEnvelope:
    """Plan or execute a bounded research discovery workflow.

    The workflow builds a deterministic suite from the request, optionally prepares
    market data, runs data-quality checks, persists experiment/run metadata, writes
    comparison artifacts, and produces recommendations from prior/operator context.
    Dry-run and `data_mode="plan"` requests stop after planning and return a
    read-only envelope; executed runs perform local writes and report generated
    artifact paths and recoverable warnings in the envelope.
    """
    _validate_request(request)
    output_root = Path(request.output_dir)
    discovery_root = output_root / experiment_slug(request.experiment_name)
    artifacts: dict[str, Any] = {"output_dir": str(discovery_root)}
    warnings: list[str] = []
    base_config = _discovery_config(config_data, request)
    data_plan = _data_plan(base_config, request)
    artifacts["data_plan"] = data_plan
    suite_members = build_suite_members(
        base_config,
        strategy_families=request.strategy_families,
        symbols=request.symbols,
        asset_class=request.asset_class,
        timeframe=request.timeframe,
        max_runs=request.max_runs,
    )
    suite_payload = _suite_payload(suite_members)
    artifacts["suite"] = suite_payload
    if request.dry_run or request.data_mode == "plan":
        return success_envelope(
            command="research_discovery",
            agent_owner="Quant Research Supervisor Agent",
            side_effect=SideEffect.READ_ONLY,
            data={
                "request": _request_payload(request),
                "data_plan": data_plan,
                "suite": suite_payload,
                "will_run_backtests": False,
            },
            artifacts=artifacts,
            warnings=warnings,
        )

    event_store = build_event_store(build_config(base_config))
    try:
        data_result = _prepare_data(event_store, base_config, request)
        artifacts["data"] = data_result
        data_quality_report = _run_quality(base_config, request, discovery_root / "data_quality.json")
        artifacts["data_quality_report"] = str(discovery_root / "data_quality.json")
        experiment_id = experiment_id_from_name(request.experiment_name)
        event_store.upsert_experiment(
            experiment_id=experiment_id,
            name=request.experiment_name,
            description="AI-tool discovery experiment",
            tags=("sprint5", "discovery"),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            metadata={"suite": suite_payload, "request": _request_payload(request)},
        )
        run_rows = []
        experiment_root = discovery_root / "research"
        for index, member in enumerate(suite_members, start=1):
            run_rows.append(
                _run_suite_member(
                    event_store=event_store,
                    member=member,
                    experiment_id=experiment_id,
                    experiment_name=request.experiment_name,
                    experiment_root=experiment_root,
                    data_quality_report=data_quality_report,
                    run_index=index,
                )
            )
        comparison = comparison_payload(event_store.list_experiment_runs(experiment_id))
        comparison_path = write_json_artifact(comparison, discovery_root / "comparison.json")
        operator_contexts, context_warnings = load_operator_context(request.operator_context_paths)
        warnings.extend(context_warnings)
        prior_artifacts = load_strategy_artifacts(request.prior_artifact_paths)
        recommendations = build_recommendations(
            comparison,
            experiment_name=request.experiment_name,
            data_quality=data_quality_report,
            operator_contexts=operator_contexts,
            prior_artifacts=prior_artifacts,
            settings=RecommendationSettings(),
        )
        warnings.extend(recommendations.warnings)
        recommendations_path = write_json_artifact(
            recommendations.payload,
            Path("artifacts/recommendations") / f"{experiment_slug(request.experiment_name)}.json",
        )
        return success_envelope(
            command="research_discovery",
            agent_owner="Quant Research Supervisor Agent",
            side_effect=SideEffect.LOCAL_MUTATING,
            data={
                "request": _request_payload(request),
                "experiment_id": experiment_id,
                "experiment_name": request.experiment_name,
                "runs": run_rows,
                "comparison": comparison,
                "recommendations": recommendations.payload,
            },
            artifacts={
                **artifacts,
                "comparison": str(comparison_path),
                "recommendations": str(recommendations_path),
            },
            warnings=warnings,
        )
    finally:
        event_store.close()


def _run_suite_member(
    *,
    event_store: EventStore,
    member: SuiteMember,
    experiment_id: str,
    experiment_name: str,
    experiment_root: Path,
    data_quality_report: Mapping[str, Any] | None,
    run_index: int,
) -> dict[str, Any]:
    config_data = member.config_data
    config = build_config(config_data)
    backtest_cfg = _mapping(config_data.get("backtest"))
    risk_cfg = _mapping(config_data.get("risk"))
    assumptions = build_backtest_assumptions(_mapping(backtest_cfg.get("assumptions")))
    spec = BacktestSpec(
        start=_parse_datetime(backtest_cfg["start"]),
        end=_parse_datetime(backtest_cfg["end"]),
        timeframe=str(backtest_cfg.get("timeframe", config.strategy_timeframe)),
        max_runs=int(backtest_cfg["max_runs"]) if backtest_cfg.get("max_runs") is not None else None,
    )
    strategy = _build_strategy(member.strategy_family, config_data, config)
    strategy_info = resolve_strategy_info(
        strategy,
        parameters={"suite_member_id": member.suite_member_id, **dict(member.parameters)},
        fallback_id=config.strategy_id,
    )
    provenance = build_run_provenance(
        config_data=config_data,
        config=config,
        spec=spec,
        strategy_info=strategy_info,
        risk_config=risk_cfg,
        assumptions=assumptions,
        parameters=member.parameters,
        data_quality=data_quality_report,
    )
    provenance["suite"] = {
        "suite_id": member.suite_id,
        "suite_member_id": member.suite_member_id,
        "strategy_family": member.strategy_family,
    }
    started_at = datetime.now(timezone.utc)
    run_id = deterministic_run_session_id("backtest", started_at)
    exp_run_id = experiment_run_id(experiment_id, run_id)
    artifact_dir = experiment_root / run_id
    event_store.record_experiment_run_start(
        experiment_run_id=exp_run_id,
        experiment_id=experiment_id,
        run_id=run_id,
        created_at=started_at,
        status="started",
        strategy_id=strategy_info.strategy_id,
        strategy_name=strategy_info.name,
        strategy_version=strategy_info.version,
        symbols=config.market_data_symbols,
        asset_class=config.market_data_asset_class,
        timeframe=spec.timeframe,
        start_ts=spec.start,
        end_ts=spec.end,
        parameters={"suite_member_id": member.suite_member_id, **dict(member.parameters)},
        assumptions=asdict(assumptions),
        provenance=provenance,
        data_quality=data_quality_report,
        artifact_dir=str(artifact_dir),
    )
    try:
        result = BacktestRunner(
            config=config,
            spec=spec,
            symbols=backtest_cfg.get("symbols"),
            asset_class=backtest_cfg.get("asset_class"),
            initial_cash=backtest_cfg.get("initial_cash"),
            initial_positions=_parse_initial_positions(backtest_cfg.get("initial_positions")),
            strategy=strategy,
            risk_manager=NoOpRiskManager(),
            event_store=event_store,
            config_snapshot=config_data,
            assumptions=assumptions,
            run_id=run_id,
            started_at=started_at,
        ).run(log_cycle_details=bool(backtest_cfg.get("log_cycle_details", False)))
        result = attach_research_metadata(result, experiment_id=experiment_id, experiment_run_id=exp_run_id, provenance=provenance)
        export_research_bundle(result, output_dir=artifact_dir, provenance=provenance)
        status = "success" if result.failed_runs == 0 else "failed"
        error_message = None if status == "success" else "One or more cycles failed."
        event_store.record_experiment_run_finish(
            experiment_run_id=exp_run_id,
            experiment_id=experiment_id,
            run_id=run_id,
            status=status,
            finished_at=result.finished_at,
            result_summary=result_summary(result),
            provenance=provenance,
            data_quality=data_quality_report,
            artifact_dir=str(artifact_dir),
            error_message=error_message,
        )
        return {
            "run_index": run_index,
            "run_id": run_id,
            "experiment_run_id": exp_run_id,
            "suite_member_id": member.suite_member_id,
            "strategy_family": member.strategy_family,
            "status": status,
            "artifact_dir": str(artifact_dir),
        }
    except Exception as exc:
        event_store.record_experiment_run_finish(
            experiment_run_id=exp_run_id,
            experiment_id=experiment_id,
            run_id=run_id,
            status="failed",
            finished_at=datetime.now(timezone.utc),
            result_summary={},
            provenance=provenance,
            data_quality=data_quality_report,
            artifact_dir=str(artifact_dir),
            error_message=str(exc),
        )
        return {
            "run_index": run_index,
            "run_id": run_id,
            "experiment_run_id": exp_run_id,
            "suite_member_id": member.suite_member_id,
            "strategy_family": member.strategy_family,
            "status": "failed",
            "artifact_dir": str(artifact_dir),
            "error_message": str(exc),
        }


def _prepare_data(event_store: EventStore, config_data: Mapping[str, Any], request: DiscoveryRequest) -> dict[str, Any]:
    if request.data_mode == "existing":
        return {"mode": "existing", "dataset_id": _dataset_id(request), "rows_written": None}
    if request.data_mode == "sample":
        loaded = load_sample_market_data_csv(event_store, request.sample_csv)
        return {"mode": "sample", "dataset_id": _dataset_id(request), "rows_written": loaded, "csv": request.sample_csv}
    if request.data_mode == "backfill":
        config = build_config(config_data)
        start, end = _request_window(request)
        spec = BackfillSpec(start=start, end=end, timeframe=_parse_timeframe(request.timeframe), limit=None)
        runner = MarketDataBackfillRunner(
            config,
            spec,
            symbols=list(request.symbols),
            asset_class=request.asset_class,
            event_store=event_store,
        )
        count = runner.run()
        return {"mode": "backfill", "dataset_id": _dataset_id(request), "rows_written": count}
    raise ValueError(f"Unsupported data mode: {request.data_mode}")


def _suite_payload(suite_members: Sequence[SuiteMember]) -> dict[str, Any]:
    return {
        "suite_id": suite_members[0].suite_id if suite_members else None,
        "member_count": len(suite_members),
        "members": [
            {
                "suite_member_id": member.suite_member_id,
                "strategy_family": member.strategy_family,
                "parameters": dict(member.parameters),
            }
            for member in suite_members
        ],
    }


def _run_quality(config_data: Mapping[str, Any], request: DiscoveryRequest, output_path: Path) -> Mapping[str, Any]:
    quality_config = deepcopy(dict(config_data))
    quality_config["data_quality"] = {
        **dict(_mapping(quality_config.get("data_quality"))),
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "timeframe": request.timeframe,
    }
    if request.start is not None:
        quality_config["data_quality"]["start"] = request.start.isoformat()
    if request.end is not None:
        quality_config["data_quality"]["end"] = request.end.isoformat()
    report = run_data_quality(quality_config)
    write_data_quality_report(report, output_path)
    return report


def _discovery_config(config_data: Mapping[str, Any], request: DiscoveryRequest) -> Mapping[str, Any]:
    config_copy = deepcopy(dict(config_data))
    market_data = dict(_mapping(config_copy.get("market_data")))
    market_data["symbols"] = list(request.symbols)
    market_data["asset_class"] = request.asset_class
    config_copy["market_data"] = market_data
    strategy = dict(_mapping(config_copy.get("strategy")))
    strategy["timeframe"] = request.timeframe
    config_copy["strategy"] = strategy
    backtest = dict(_mapping(config_copy.get("backtest")))
    backtest["symbols"] = list(request.symbols)
    backtest["asset_class"] = request.asset_class
    backtest["timeframe"] = request.timeframe
    backtest["assumptions"] = _cost_profile(backtest.get("assumptions"), request.cost_profile)
    if request.start is not None and request.end is not None:
        backtest["start"] = request.start.isoformat()
        backtest["end"] = request.end.isoformat()
    config_copy["backtest"] = backtest
    risk = dict(_mapping(config_copy.get("risk")))
    risk.setdefault("profile", request.risk_profile)
    config_copy["risk"] = risk
    return config_copy


def _data_plan(config_data: Mapping[str, Any], request: DiscoveryRequest) -> dict[str, Any]:
    start, end = _request_window(request)
    return {
        "mode": request.data_mode,
        "dataset_id": _dataset_id(request),
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "timeframe": request.timeframe,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "source": _mapping(config_data.get("market_data")).get("source", "alpaca"),
        "will_write_bars": request.data_mode in {"backfill", "sample"} and not request.dry_run,
    }


def _request_window(request: DiscoveryRequest) -> tuple[datetime, datetime]:
    if request.start is not None:
        end = request.end or datetime.now(timezone.utc)
        return request.start, end
    if request.since:
        return _resolve_since(request.since, datetime.now(timezone.utc))
    end = request.end or datetime.now(timezone.utc)
    return end - timedelta(days=1), end


def _request_payload(request: DiscoveryRequest) -> dict[str, Any]:
    return {
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "timeframe": request.timeframe,
        "strategy_families": list(request.strategy_families),
        "data_mode": request.data_mode,
        "since": request.since,
        "start": request.start.isoformat() if request.start else None,
        "end": request.end.isoformat() if request.end else None,
        "max_runs": request.max_runs,
        "cost_profile": request.cost_profile,
        "risk_profile": request.risk_profile,
        "output_dir": request.output_dir,
        "experiment_name": request.experiment_name,
        "dry_run": request.dry_run,
        "operator_context_paths": list(request.operator_context_paths),
        "prior_artifact_paths": list(request.prior_artifact_paths),
    }


def _dataset_id(request: DiscoveryRequest) -> str:
    import hashlib
    import json

    payload = _request_payload(request)
    payload.pop("dry_run", None)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return f"dataset_{digest}"


def _cost_profile(existing: object, profile: str) -> Mapping[str, Any]:
    assumptions = deepcopy(dict(_mapping(existing)))
    if profile == "default":
        return assumptions
    fees = dict(_mapping(assumptions.get("fees")))
    fees.setdefault("fixed_per_order", 0.1)
    fees.setdefault("bps", 0)
    fees.setdefault("minimum_fee", 0.1)
    slippage = dict(_mapping(assumptions.get("slippage")))
    slippage.setdefault("bps", 10)
    assumptions["fees"] = fees
    assumptions["slippage"] = slippage
    return assumptions


def _build_strategy(family: str, config_data: Mapping[str, Any], config: Config) -> Any:
    strategy_cfg = _mapping(config_data.get("strategy"))
    settings = _mapping(strategy_cfg.get(family))
    symbols = config.market_data_symbols
    asset_class = config.market_data_asset_class
    timeframe = config.strategy_timeframe
    target_qty_when_long = _float(settings.get("target_qty_when_long"), 1.0)
    if family == "trend_following":
        return build_trend_following_strategy(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            target_qty_when_long=target_qty_when_long,
            ema_fast_period=_int(settings.get("ema_fast_period"), 12),
            ema_slow_period=_int(settings.get("ema_slow_period"), 26),
            macd_fast_period=_int(settings.get("macd_fast_period"), 12),
            macd_slow_period=_int(settings.get("macd_slow_period"), 26),
            macd_signal_period=_int(settings.get("macd_signal_period"), 9),
        )
    if family == "mean_reversion":
        return build_mean_reversion_strategy(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            target_qty_when_long=target_qty_when_long,
            rsi_period=_int(settings.get("rsi_period"), 14),
            oversold=_float(settings.get("oversold"), 30.0),
            exit_rsi=_float(settings.get("exit_rsi"), 50.0),
            mean_period=_int(settings.get("mean_period"), 20),
            stretch_pct=_float(settings.get("stretch_pct"), 0.02),
        )
    if family == "bollinger_band":
        return build_bollinger_band_strategy(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            target_qty_when_long=target_qty_when_long,
            period=_int(settings.get("period"), 20),
            stddev_multiplier=_float(settings.get("stddev_multiplier"), 2.0),
        )
    raise ValueError(f"Unsupported strategy family: {family}")


def _parse_initial_positions(value: object) -> list[Position]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("backtest.initial_positions must be a list")
    positions: list[Position] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            raise ValueError("backtest.initial_positions entries must be mappings")
        positions.append(
            Position(
                symbol=str(entry["symbol"]).strip().upper(),
                qty=float(entry.get("qty", 0.0)),
                avg_price=float(entry["avg_price"]) if entry.get("avg_price") is not None else None,
            )
        )
    return positions


def _parse_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_request(request: DiscoveryRequest) -> None:
    if not request.symbols:
        raise ValueError("Discovery request requires at least one symbol")
    if len(request.symbols) > 20:
        raise ValueError("Discovery request supports at most 20 symbols")
    if request.max_runs <= 0:
        raise ValueError("max_runs must be positive")
    if request.data_mode not in {"plan", "backfill", "existing", "sample"}:
        raise ValueError(f"Unsupported data mode: {request.data_mode}")
    if request.cost_profile not in {"default", "conservative"}:
        raise ValueError(f"Unsupported cost profile: {request.cost_profile}")
    start, end = _request_window(request)
    if end < start:
        raise ValueError("Discovery request end must be after start")
    if end - start > timedelta(days=365):
        raise ValueError("Discovery request window must not exceed 365 days")


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _int(value: object, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, (int, float, str)):
        return int(value)
    return int(str(value))


def _float(value: object, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float, str)):
        return float(value)
    return float(str(value))
