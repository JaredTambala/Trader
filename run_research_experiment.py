"""Run experiment-backed research backtests."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any, Mapping

from dotenv import load_dotenv

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"
if str(EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_DIR))

from strategy_library_support import build_library_risk_manager, build_library_strategy  # noqa: E402

from trader.backtest import BacktestRunner, BacktestSpec, build_backtest_assumptions  # noqa: E402
from trader.config import build_config, load_yaml_config, resolve_log_level  # noqa: E402
from trader.event_store import build_event_store  # noqa: E402
from trader.market_data.quality import run_data_quality, write_data_quality_report  # noqa: E402
from trader.identifiers import deterministic_run_session_id  # noqa: E402
from trader.portfolio import Position  # noqa: E402
from trader_research.research import (  # noqa: E402
    attach_research_metadata,
    build_parameter_grid,
    build_run_provenance,
    experiment_id_from_name,
    experiment_run_id,
    experiment_slug,
    export_research_bundle,
    result_summary,
)
from trader.strategy_metadata import resolve_strategy_info  # noqa: E402


logger = logging.getLogger(__name__)


def main() -> None:
    args = _parse_args()
    load_dotenv(".env")
    base_config_data = load_yaml_config(args.config)
    _configure_logging(resolve_log_level(base_config_data))

    experiment_name = args.experiment or _configured_experiment_name(base_config_data)
    description = args.description or _configured_experiment_description(base_config_data)
    tags = tuple(_configured_experiment_tags(base_config_data)) + tuple(args.tag or ())
    experiment_id = experiment_id_from_name(experiment_name)
    slug = experiment_slug(experiment_name)
    output_root = Path(args.output_dir or _configured_output_dir(base_config_data))
    experiment_root = output_root / slug
    experiment_root.mkdir(parents=True, exist_ok=True)

    data_quality_report = _resolve_data_quality_report(
        base_config_data,
        run_data_quality_flag=args.run_data_quality,
        report_path=args.data_quality_report,
        output_path=experiment_root / "data_quality.json",
    )

    event_store = build_event_store(build_config(base_config_data))
    try:
        now = datetime.now(timezone.utc)
        event_store.upsert_experiment(
            experiment_id=experiment_id,
            name=experiment_name,
            description=description,
            tags=tags,
            created_at=now,
            updated_at=now,
            metadata={"config_path": args.config},
        )
        runs = build_parameter_grid(base_config_data)
        print(f"experiment_id={experiment_id}")
        print(f"runs={len(runs)}")
        for index, (parameters, config_data) in enumerate(runs, start=1):
            _run_one(
                event_store=event_store,
                config_data=config_data,
                experiment_id=experiment_id,
                experiment_name=experiment_name,
                experiment_root=experiment_root,
                parameters=parameters,
                data_quality_report=data_quality_report,
                run_index=index,
            )
    finally:
        event_store.close()


def _run_one(
    *,
    event_store: Any,
    config_data: Mapping[str, Any],
    experiment_id: str,
    experiment_name: str,
    experiment_root: Path,
    parameters: Mapping[str, Any],
    data_quality_report: Mapping[str, Any] | None,
    run_index: int,
) -> None:
    config = build_config(config_data)
    backtest_cfg = _mapping(config_data.get("backtest"), "backtest")
    risk_cfg = _mapping(config_data.get("risk", {}), "risk")
    strategy = build_library_strategy(config_data, config)
    risk_manager = build_library_risk_manager(risk_cfg)
    assumptions = build_backtest_assumptions(_mapping(backtest_cfg.get("assumptions"), "backtest.assumptions"))
    spec = BacktestSpec(
        start=_parse_datetime(backtest_cfg["start"]),
        end=_parse_datetime(backtest_cfg["end"]),
        timeframe=str(backtest_cfg.get("timeframe", config.strategy_timeframe)),
        max_runs=int(backtest_cfg["max_runs"]) if backtest_cfg.get("max_runs") is not None else None,
    )
    strategy_parameters = _strategy_parameters(config_data)
    strategy_parameters.update(dict(parameters))
    strategy_info = resolve_strategy_info(
        strategy,
        parameters=strategy_parameters,
        fallback_id=config.strategy_id,
    )
    provenance = build_run_provenance(
        config_data=config_data,
        config=config,
        spec=spec,
        strategy_info=strategy_info,
        risk_config=risk_cfg,
        assumptions=assumptions,
        parameters=parameters,
        data_quality=data_quality_report,
    )
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
        parameters=strategy_parameters,
        assumptions=asdict(assumptions),
        provenance=provenance,
        data_quality=data_quality_report,
        artifact_dir=str(artifact_dir),
    )
    try:
        runner = BacktestRunner(
            config=config,
            spec=spec,
            symbols=backtest_cfg.get("symbols"),
            asset_class=backtest_cfg.get("asset_class"),
            initial_cash=backtest_cfg.get("initial_cash"),
            initial_positions=_parse_initial_positions(backtest_cfg.get("initial_positions")),
            strategy=strategy,
            risk_manager=risk_manager,
            event_store=event_store,
            config_snapshot=config_data,
            assumptions=assumptions,
            run_id=run_id,
            started_at=started_at,
        )
        result = runner.run(log_cycle_details=bool(backtest_cfg.get("log_cycle_details", False)))
        if result.run_id != run_id:
            raise RuntimeError(f"Backtest returned unexpected run_id: {result.run_id}")
        result = attach_research_metadata(
            result,
            experiment_id=experiment_id,
            experiment_run_id=exp_run_id,
            provenance=provenance,
        )
        export_research_bundle(result, output_dir=artifact_dir, provenance=provenance)
        event_store.record_experiment_run_finish(
            experiment_run_id=exp_run_id,
            experiment_id=experiment_id,
            run_id=run_id,
            status="success" if result.failed_runs == 0 else "failed",
            finished_at=result.finished_at,
            result_summary=result_summary(result),
            provenance=provenance,
            data_quality=data_quality_report,
            artifact_dir=str(artifact_dir),
            error_message=None if result.failed_runs == 0 else "One or more cycles failed.",
        )
        print(f"run[{run_index}] run_id={run_id} experiment_run_id={exp_run_id} artifact_dir={artifact_dir}")
    except Exception as exc:
        now = datetime.now(timezone.utc)
        event_store.record_experiment_run_finish(
            experiment_run_id=exp_run_id,
            experiment_id=experiment_id,
            run_id=run_id,
            status="failed",
            finished_at=now,
            result_summary={},
            provenance=provenance,
            data_quality=data_quality_report,
            artifact_dir=str(artifact_dir),
            error_message=str(exc),
        )
        logger.exception("Research run failed experiment=%s run_index=%s", experiment_name, run_index)
        print(f"run[{run_index}] failed experiment_run_id={exp_run_id} error={exc}")


def _resolve_data_quality_report(
    config_data: Mapping[str, Any],
    *,
    run_data_quality_flag: bool,
    report_path: str | None,
    output_path: Path,
) -> Mapping[str, Any] | None:
    if report_path:
        return json.loads(Path(report_path).read_text(encoding="utf-8"))
    if not run_data_quality_flag:
        return None
    report = run_data_quality(config_data)
    write_data_quality_report(report, output_path)
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a research experiment backtest.")
    parser.add_argument("config", help="Path to the YAML configuration file.")
    parser.add_argument("--experiment", help="Experiment name.")
    parser.add_argument("--description", help="Experiment description.")
    parser.add_argument("--tag", action="append", help="Experiment tag. Can be supplied more than once.")
    parser.add_argument("--output-dir", help="Root directory for research artifacts.")
    parser.add_argument("--data-quality-report", help="Attach an existing data-quality JSON report.")
    parser.add_argument("--run-data-quality", action="store_true", help="Run data quality before the experiment.")
    return parser.parse_args()


def _configure_logging(level_name: str | None = None) -> None:
    level_name = (level_name or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _configured_experiment_name(config_data: Mapping[str, Any]) -> str:
    experiment_cfg = _mapping(_mapping(config_data.get("research"), "research").get("experiment"), "research.experiment")
    return str(experiment_cfg.get("name") or "research_experiment")


def _configured_experiment_description(config_data: Mapping[str, Any]) -> str | None:
    experiment_cfg = _mapping(_mapping(config_data.get("research"), "research").get("experiment"), "research.experiment")
    value = experiment_cfg.get("description")
    return str(value) if value is not None else None


def _configured_experiment_tags(config_data: Mapping[str, Any]) -> list[str]:
    experiment_cfg = _mapping(_mapping(config_data.get("research"), "research").get("experiment"), "research.experiment")
    raw = experiment_cfg.get("tags", [])
    if not isinstance(raw, list):
        raise ValueError("research.experiment.tags must be a list")
    return [str(tag) for tag in raw]


def _configured_output_dir(config_data: Mapping[str, Any]) -> str:
    experiment_cfg = _mapping(_mapping(config_data.get("research"), "research").get("experiment"), "research.experiment")
    return str(experiment_cfg.get("output_dir") or "artifacts/research")


def _strategy_parameters(config_data: Mapping[str, Any]) -> dict[str, Any]:
    strategy_cfg = _mapping(config_data.get("strategy"), "strategy")
    strategy_id = str(strategy_cfg.get("id", ""))
    parameters: dict[str, Any] = {"id": strategy_id}
    settings = strategy_cfg.get(strategy_id)
    if isinstance(settings, Mapping):
        parameters.update(dict(settings))
    return parameters


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


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


if __name__ == "__main__":
    main()
