"""Research workflow helpers for experiment-backed backtests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import csv
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable, Mapping, Sequence

from trader.backtest import (
    BacktestAssumptions,
    BacktestResult,
    BacktestSpec,
    export_backtest_equity_curve_csv,
    export_backtest_result_json,
    export_backtest_trades_csv,
)
from trader.config import Config
from trader.data import EventStore
from trader.strategy_metadata import StrategyInfo


def experiment_slug(name: str) -> str:
    """Normalize an experiment name into a stable slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "experiment"


def experiment_id_from_name(name: str) -> str:
    """Build a stable experiment identifier from a name."""
    return f"exp_{experiment_slug(name)}"


def experiment_run_id(experiment_id: str, run_id: str) -> str:
    """Build a stable experiment-run identifier."""
    digest = hashlib.sha256(f"{experiment_id}:{run_id}".encode("utf-8")).hexdigest()[:16]
    return f"exp_run_{digest}"


def config_snapshot_hash(config_data: Mapping[str, Any]) -> str:
    """Return a stable hash for a parsed config mapping."""
    payload = json.dumps(_sanitize(config_data), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_parameter_grid(config_data: Mapping[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Expand a deterministic Cartesian grid from research.sweep.parameters."""
    research_cfg = _mapping(config_data.get("research"))
    sweep_cfg = _mapping(research_cfg.get("sweep"))
    parameter_cfg = sweep_cfg.get("parameters")
    if parameter_cfg is None:
        return [({}, deepcopy(dict(config_data)))]
    if not isinstance(parameter_cfg, Mapping):
        raise ValueError("research.sweep.parameters must be a mapping")
    normalized_parameters = {str(key): value for key, value in parameter_cfg.items()}
    keys = sorted(normalized_parameters.keys())
    values_by_key: list[list[Any]] = []
    for key in keys:
        raw_values = normalized_parameters[key]
        if not isinstance(raw_values, Sequence) or isinstance(raw_values, (str, bytes)):
            raise ValueError(f"research.sweep.parameters.{key} must be a list")
        values = list(raw_values)
        if not values:
            raise ValueError(f"research.sweep.parameters.{key} must not be empty")
        values_by_key.append(values)
    combinations = _product(values_by_key)
    max_runs = int(sweep_cfg.get("max_runs", 25))
    if len(combinations) > max_runs:
        raise ValueError(f"research sweep expands to {len(combinations)} runs; max_runs={max_runs}")
    expanded: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for combination in combinations:
        overrides = dict(zip(keys, combination))
        config_copy = deepcopy(dict(config_data))
        apply_parameter_overrides(config_copy, overrides)
        expanded.append((overrides, config_copy))
    return expanded


def apply_parameter_overrides(config_data: dict[str, Any], overrides: Mapping[str, Any]) -> None:
    """Apply dotted-path overrides to a mutable config mapping."""
    for path, value in overrides.items():
        parts = [part for part in str(path).split(".") if part]
        if not parts:
            raise ValueError("Parameter path must not be empty")
        current: dict[str, Any] = config_data
        for part in parts[:-1]:
            next_value = current.get(part)
            if next_value is None:
                next_value = {}
                current[part] = next_value
            if not isinstance(next_value, dict):
                raise ValueError(f"Cannot apply parameter override through non-mapping path: {path}")
            current = next_value
        current[parts[-1]] = value


def build_run_provenance(
    *,
    config_data: Mapping[str, Any],
    config: Config,
    spec: BacktestSpec,
    strategy_info: StrategyInfo,
    risk_config: Mapping[str, Any],
    assumptions: BacktestAssumptions,
    parameters: Mapping[str, Any],
    data_quality: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a run provenance payload."""
    warnings: list[str] = []
    if data_quality is None:
        warnings.append("No data quality report attached to this research run.")
        data_quality_payload: Mapping[str, Any] | None = None
    else:
        data_quality_payload = data_quality
        if _data_quality_missing_gaps(data_quality):
            warnings.append("Attached data quality report contains missing gaps.")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "package": {"name": "trader", "version": _package_version()},
        "git": _git_info(),
        "config_hash": config_snapshot_hash(config_data),
        "strategy": strategy_info.to_dict(),
        "risk": dict(risk_config),
        "parameters": dict(parameters),
        "symbols": list(config.market_data_symbols),
        "asset_class": config.market_data_asset_class,
        "timeframe": spec.timeframe,
        "data_window": {
            "start": spec.start.isoformat(),
            "end": spec.end.isoformat(),
        },
        "assumptions": _sanitize(asdict(assumptions)),
        "data_quality": _sanitize(data_quality_payload) if data_quality_payload is not None else None,
        "warnings": warnings,
    }


def attach_research_metadata(
    result: BacktestResult,
    *,
    experiment_id: str,
    experiment_run_id: str,
    provenance: Mapping[str, Any],
) -> BacktestResult:
    """Return a result enriched with research metadata."""
    return replace(
        result,
        experiment_id=experiment_id,
        experiment_run_id=experiment_run_id,
        provenance=dict(provenance),
    )


def result_summary(result: BacktestResult) -> dict[str, Any]:
    """Extract compact comparison metrics from a result."""
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


def export_research_bundle(
    result: BacktestResult,
    *,
    output_dir: str | Path,
    provenance: Mapping[str, Any],
) -> Path:
    """Export a portable research artifact bundle."""
    bundle_dir = Path(output_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    export_backtest_result_json(result, bundle_dir / "result.json")
    (bundle_dir / "provenance.json").write_text(
        json.dumps(_sanitize(provenance), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (bundle_dir / "metrics.json").write_text(
        json.dumps(_sanitize(result_summary(result)), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    export_backtest_equity_curve_csv(result, bundle_dir / "equity_curve.csv")
    _export_curve_csv(result.benchmark_curve, bundle_dir / "benchmark_curve.csv")
    _export_positions_csv(result, bundle_dir / "positions.csv")
    if result.trades:
        export_backtest_trades_csv(result, bundle_dir / "trades.csv")
    return bundle_dir


def comparison_payload(rows: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    """Build a stable comparison payload from experiment rows."""
    comparison_rows = [_comparison_row(row) for row in rows]
    warnings = _comparison_warnings(rows)
    return {"rows": comparison_rows, "warnings": warnings}


def list_experiment_comparison(
    event_store: EventStore,
    *,
    experiment_name: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """Load experiment rows and convert them into a comparison payload."""
    experiment_id = experiment_id_from_name(experiment_name)
    return comparison_payload(event_store.list_experiment_runs(experiment_id, limit=limit))


def _comparison_row(row: Mapping[str, object]) -> dict[str, Any]:
    result = _json_mapping(row.get("result_summary"))
    return {
        "experiment_run_id": row.get("experiment_run_id"),
        "run_id": row.get("run_id"),
        "status": row.get("status"),
        "strategy_id": row.get("strategy_id"),
        "strategy_name": row.get("strategy_name"),
        "strategy_version": row.get("strategy_version"),
        "total_return": result.get("total_return"),
        "sharpe": result.get("sharpe"),
        "max_drawdown": result.get("max_drawdown"),
        "turnover": result.get("turnover"),
        "fees": result.get("fees"),
        "slippage": result.get("slippage"),
        "alpha": result.get("alpha"),
        "beta": result.get("beta"),
        "warnings_count": result.get("warnings_count"),
        "trade_count": result.get("trade_count"),
        "symbols": row.get("symbols"),
        "asset_class": row.get("asset_class"),
        "timeframe": row.get("timeframe"),
        "start_ts": row.get("start_ts"),
        "end_ts": row.get("end_ts"),
        "parameters": _json_mapping(row.get("parameters")),
        "assumptions": _json_mapping(row.get("assumptions")),
        "artifact_dir": row.get("artifact_dir"),
        "error_message": row.get("error_message"),
    }


def _comparison_warnings(rows: Sequence[Mapping[str, object]]) -> list[str]:
    warnings: list[str] = []
    for key, label in (
        ("assumptions", "assumptions"),
        ("symbols", "symbols"),
        ("timeframe", "timeframe"),
        ("asset_class", "asset class"),
        ("start_ts", "data start"),
        ("end_ts", "data end"),
    ):
        values = {_stable_json(row.get(key)) for row in rows}
        if len(values) > 1:
            warnings.append(f"Compared runs differ in {label}.")
    return warnings


def _export_curve_csv(points: Iterable[Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ts", "equity"])
        writer.writeheader()
        for point in points:
            writer.writerow({"ts": point.ts.isoformat(), "equity": point.equity})


def _export_positions_csv(result: BacktestResult, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "qty",
                "avg_price",
                "last_price",
                "last_ts",
                "market_value",
                "unrealized_pnl",
            ],
        )
        writer.writeheader()
        for position in result.positions:
            writer.writerow(
                {
                    "symbol": position.symbol,
                    "qty": position.qty,
                    "avg_price": position.avg_price,
                    "last_price": position.last_price,
                    "last_ts": position.last_ts.isoformat() if position.last_ts is not None else None,
                    "market_value": position.market_value,
                    "unrealized_pnl": position.unrealized_pnl,
                }
            )


def _product(values_by_key: Sequence[Sequence[Any]]) -> list[tuple[Any, ...]]:
    if not values_by_key:
        return [tuple()]
    head, *tail = values_by_key
    suffixes = _product(tail)
    return [(value, *suffix) for value in head for suffix in suffixes]


def _mapping(value: object) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("Expected mapping")
    return value


def _package_version() -> str:
    try:
        return version("trader")
    except PackageNotFoundError:
        return "unknown"


def _git_info() -> dict[str, Any]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {"sha": sha, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"sha": None, "dirty": None}


def _data_quality_missing_gaps(data_quality: Mapping[str, Any]) -> bool:
    summaries = data_quality.get("summaries", [])
    if not isinstance(summaries, Sequence):
        return False
    for summary in summaries:
        if isinstance(summary, Mapping) and int(summary.get("missing_gaps", 0) or 0) > 0:
            return True
    return False


def _json_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value:
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return parsed
    return {}


def _stable_json(value: object) -> str:
    return json.dumps(_sanitize(value), sort_keys=True, separators=(",", ":"))


def _sanitize(value: object) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _sanitize(inner) for key, inner in value.items()}
    if isinstance(value, (tuple, list)):
        return [_sanitize(item) for item in value]
    return value
