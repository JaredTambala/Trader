"""Evaluation Agent performance reports over persisted backtest bundles."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    ArtifactReference,
    SCHEMA_VERSION,
    SideEffect,
    ToolEnvelope,
    error_envelope,
    success_envelope,
    write_json_artifact,
)
from .domain import BACKTEST_RUN_REF, DATA_QUALITY_REPORT, EVALUATION_REPORT, ResearchIssue, stable_research_id


EVALUATION_GENERATE_PERFORMANCE_REPORT = "evaluation_generate_performance_report"
PERFORMANCE_REPORT_KIND = "performance_report"


def generate_performance_report(
    *,
    artifact_root: str | Path,
    run_id: str | None = None,
    artifact_dir: str | Path | None = None,
    backtest_run_ref: Mapping[str, Any] | None = None,
    data_quality_report: Mapping[str, Any] | None = None,
    data_quality_report_path: str | Path | None = None,
    data_quality_report_ref: Mapping[str, Any] | None = None,
) -> ToolEnvelope:
    """Write an Evaluation-owned performance report for one backtest bundle.

    Args:
        artifact_root: Root directory for research artifacts.
        run_id: Optional persisted backtest run ID.
        artifact_dir: Optional task-28 run artifact directory.
        backtest_run_ref: Optional inline `backtest_run_ref` payload.
        data_quality_report: Optional inline Data Agent quality report.
        data_quality_report_path: Optional path to a quality report.
        data_quality_report_ref: Optional artifact reference containing a path
            or inline quality-report payload.

    Returns:
        Local-mutating envelope containing `evaluation_report`. Resolved backtest
        bundles produce a report even when report-level blockers are present.
    """
    try:
        bundle_dir = _resolve_bundle_dir(
            artifact_root=artifact_root,
            run_id=run_id,
            artifact_dir=artifact_dir,
            backtest_run_ref=backtest_run_ref,
        )
        bundle = _load_bundle(bundle_dir)
        quality_report, quality_source = _resolve_quality_report(
            data_quality_report=data_quality_report,
            data_quality_report_path=data_quality_report_path,
            data_quality_report_ref=data_quality_report_ref,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return error_envelope(
            command=EVALUATION_GENERATE_PERFORMANCE_REPORT,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="performance_report_failed",
            message=str(exc),
        )

    blockers = _bundle_blockers(bundle)
    warnings = _bundle_warnings(bundle)
    caveats = _bundle_caveats(bundle)
    quality_summary, quality_blockers, quality_warnings = _quality_evaluation(
        quality_report=quality_report,
        quality_source=quality_source,
        data_scope=_mapping(bundle.run_ref.get("data_scope")),
    )
    blockers.extend(quality_blockers)
    warnings.extend(quality_warnings)
    caveats.extend(_quality_caveats(quality_summary))

    core_metrics = _core_metrics(bundle.metrics, bundle.result)
    trade_stats = _trade_stats(bundle.metrics, bundle.result, bundle.trades_path)
    benchmark = _benchmark_metrics(bundle.metrics, bundle.result)
    costs = _cost_summary(bundle.metrics, bundle.result)
    caveats.extend(_metric_caveats(core_metrics, trade_stats, costs, benchmark))
    blockers.extend(_metric_blockers(bundle.metrics, trade_stats))

    report_id = stable_research_id(
        "evaluation_performance_report",
        {
            "run_id": bundle.run_id,
            "metrics": bundle.metrics,
            "result_summary": {
                "total_runs": bundle.result.get("total_runs"),
                "success_runs": bundle.result.get("success_runs"),
                "failed_runs": bundle.result.get("failed_runs"),
                "strategy_performance": bundle.result.get("strategy_performance"),
                "benchmark_performance": bundle.result.get("benchmark_performance"),
                "tracking_error": bundle.result.get("tracking_error"),
                "information_ratio": bundle.result.get("information_ratio"),
                "alpha": bundle.result.get("alpha"),
                "beta": bundle.result.get("beta"),
                "total_fees": bundle.result.get("total_fees"),
                "total_slippage": bundle.result.get("total_slippage"),
            },
            "data_scope": bundle.run_ref.get("data_scope"),
            "data_quality": _quality_identity(quality_summary),
        },
    )
    report = {
        "artifact_type": EVALUATION_REPORT,
        "report_kind": PERFORMANCE_REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id,
        "status": "blocked" if blockers else "passed",
        "run_id": bundle.run_id,
        "candidate_id": bundle.run_ref.get("candidate_id"),
        "validation_id": bundle.run_ref.get("validation_id"),
        "dataset_id": bundle.run_ref.get("dataset_id"),
        "data_scope": _jsonable(bundle.run_ref.get("data_scope")),
        "core_metrics": core_metrics,
        "trade_stats": trade_stats,
        "costs": costs,
        "benchmark": benchmark,
        "data_quality": quality_summary,
        "artifact_paths": bundle.artifact_paths,
        "caveats": _dedupe_text(caveats),
        "warnings": [issue.to_dict() for issue in _dedupe_issues(warnings)],
        "blockers": [issue.to_dict() for issue in _dedupe_issues(blockers)],
    }
    report_path = write_json_artifact(
        report,
        Path(artifact_root) / "evaluation" / "performance_reports" / f"{report_id}.json",
    )
    return success_envelope(
        command=EVALUATION_GENERATE_PERFORMANCE_REPORT,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"evaluation_report": report},
        artifacts={
            "evaluation_report": ArtifactReference(
                artifact_type=EVALUATION_REPORT,
                path=report_path,
                metadata={"id": report_id, "run_id": bundle.run_id, "status": report["status"]},
            ).to_dict()
        },
        warnings=tuple(issue["message"] for issue in report["warnings"]),
    )


@dataclass(frozen=True)
class _BacktestBundle:
    """Loaded task-28 artifact bundle used by performance reports."""

    bundle_dir: Path
    run_ref: Mapping[str, Any]
    metrics: Mapping[str, Any]
    result: Mapping[str, Any]
    provenance: Mapping[str, Any]
    artifact_paths: Mapping[str, Any]
    trades_path: Path | None
    run_id: str


def _resolve_bundle_dir(
    *,
    artifact_root: str | Path,
    run_id: str | None,
    artifact_dir: str | Path | None,
    backtest_run_ref: Mapping[str, Any] | None,
) -> Path:
    sources = [
        bool(run_id and run_id.strip()),
        artifact_dir is not None and str(artifact_dir).strip() != "",
        backtest_run_ref is not None,
    ]
    if sum(1 for selected in sources if selected) != 1:
        raise ValueError("exactly one of run_id, artifact_dir, or backtest_run_ref is required")
    if run_id:
        return Path(artifact_root) / "backtests" / "runs" / run_id.strip()
    if artifact_dir is not None:
        return Path(str(artifact_dir))
    if not isinstance(backtest_run_ref, MappingABC):
        raise ValueError("backtest_run_ref must be a mapping")
    ref_dir = backtest_run_ref.get("artifact_dir")
    if ref_dir is None or str(ref_dir).strip() == "":
        raise ValueError("backtest_run_ref.artifact_dir is required")
    return Path(str(ref_dir))


def _load_bundle(bundle_dir: Path) -> _BacktestBundle:
    run_ref_path = bundle_dir / "backtest_run_ref.json"
    metrics_path = bundle_dir / "metrics.json"
    result_path = bundle_dir / "result.json"
    provenance_path = bundle_dir / "provenance.json"
    if not run_ref_path.exists():
        raise FileNotFoundError(f"backtest_run_ref.json not found: {run_ref_path}")
    if not metrics_path.exists():
        raise FileNotFoundError(f"metrics.json not found: {metrics_path}")
    if not result_path.exists():
        raise FileNotFoundError(f"result.json not found: {result_path}")
    run_ref = _read_json(run_ref_path)
    if run_ref.get("artifact_type") != BACKTEST_RUN_REF:
        raise ValueError("backtest_run_ref artifact_type must be backtest_run_ref")
    metrics = _read_json(metrics_path)
    result = _read_json(result_path)
    provenance = _read_json(provenance_path) if provenance_path.exists() else {}
    run_id = str(run_ref.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("backtest_run_ref.run_id is required")
    artifact_paths = _bundle_paths(bundle_dir)
    artifact_paths["backtest_run_ref"] = str(run_ref_path)
    trades_path = bundle_dir / "trades.csv"
    return _BacktestBundle(
        bundle_dir=bundle_dir,
        run_ref=run_ref,
        metrics=metrics,
        result=result,
        provenance=provenance,
        artifact_paths=artifact_paths,
        trades_path=trades_path if trades_path.exists() else None,
        run_id=str(run_ref.get("run_id") or metrics.get("run_id") or result.get("run_id") or "").strip(),
    )


def _resolve_quality_report(
    *,
    data_quality_report: Mapping[str, Any] | None,
    data_quality_report_path: str | Path | None,
    data_quality_report_ref: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any]]:
    sources = [
        data_quality_report is not None,
        data_quality_report_path is not None and str(data_quality_report_path).strip() != "",
        data_quality_report_ref is not None,
    ]
    if sum(1 for selected in sources if selected) > 1:
        raise ValueError("provide at most one data_quality_report input")
    if data_quality_report is not None:
        return data_quality_report, {"kind": "inline"}
    if data_quality_report_path is not None and str(data_quality_report_path).strip() != "":
        path = Path(str(data_quality_report_path))
        if not path.exists():
            raise FileNotFoundError(f"data_quality_report not found: {path}")
        return _read_json(path), {"kind": "path", "path": str(path)}
    if data_quality_report_ref is None:
        return None, {"kind": "missing"}
    if not isinstance(data_quality_report_ref, MappingABC):
        raise ValueError("data_quality_report_ref must be a mapping")
    if data_quality_report_ref.get("data_quality_report") is not None:
        payload = data_quality_report_ref["data_quality_report"]
        if not isinstance(payload, MappingABC):
            raise ValueError("data_quality_report_ref.data_quality_report must be a mapping")
        return payload, {"kind": "ref_payload"}
    if data_quality_report_ref.get("payload") is not None:
        payload = data_quality_report_ref["payload"]
        if not isinstance(payload, MappingABC):
            raise ValueError("data_quality_report_ref.payload must be a mapping")
        return payload, {"kind": "ref_payload"}
    path_value = data_quality_report_ref.get("path")
    if path_value is None or str(path_value).strip() == "":
        raise ValueError("data_quality_report_ref requires path, payload, or data_quality_report")
    path = Path(str(path_value))
    if not path.exists():
        raise FileNotFoundError(f"data_quality_report not found: {path}")
    return _read_json(path), {"kind": "ref_path", "path": str(path)}


def _bundle_blockers(bundle: _BacktestBundle) -> list[ResearchIssue]:
    blockers: list[ResearchIssue] = []
    status = str(bundle.run_ref.get("status") or "").strip().lower()
    if status and status != "passed":
        blockers.append(_issue("backtest_status_not_passed", f"Backtest status is {status}."))
    for item in _issue_sequence(bundle.run_ref.get("blockers")):
        blockers.append(_issue("backtest_blocker", str(item.get("message") or item), item))
    failed_runs = _optional_float(bundle.metrics.get("failed_runs"))
    if failed_runs is not None and failed_runs > 0:
        blockers.append(_issue("failed_backtest_runs", f"Backtest has {int(failed_runs)} failed runs."))
    return blockers


def _bundle_warnings(bundle: _BacktestBundle) -> list[ResearchIssue]:
    warnings: list[ResearchIssue] = []
    for item in _issue_sequence(bundle.run_ref.get("warnings")):
        warnings.append(_issue("backtest_warning", str(item.get("message") or item), item))
    for item in _sequence(bundle.result.get("warnings")):
        warnings.append(_issue("runtime_warning", str(item), {"source": "result.json"}))
    return warnings


def _bundle_caveats(bundle: _BacktestBundle) -> list[str]:
    caveats: list[str] = []
    if not bundle.provenance:
        caveats.append("Backtest provenance was missing or empty.")
    return caveats


def _quality_evaluation(
    *,
    quality_report: Mapping[str, Any] | None,
    quality_source: Mapping[str, Any],
    data_scope: Mapping[str, Any],
) -> tuple[dict[str, Any], list[ResearchIssue], list[ResearchIssue]]:
    if quality_report is None:
        summary = {"provided": False, "source": dict(quality_source)}
        return summary, [_issue("missing_data_quality_report", "Data-quality report is required for evaluation.")], []

    summary = {
        "provided": True,
        "source": dict(quality_source),
        "artifact_type": quality_report.get("artifact_type", DATA_QUALITY_REPORT),
        "report_id": quality_report.get("report_id"),
        "complete": quality_report.get("complete"),
        "total_bars": quality_report.get("total_bars", quality_report.get("total_rows")),
        "missing_bar_count": quality_report.get("missing_bar_count"),
        "missing_gap_count": quality_report.get("missing_gap_count"),
        "warnings": list(str(item) for item in _sequence(quality_report.get("warnings"))),
    }
    blockers: list[ResearchIssue] = []
    warnings = [_issue("data_quality_warning", message, {"report_id": summary.get("report_id")}) for message in summary["warnings"]]
    if str(summary["artifact_type"]) not in {DATA_QUALITY_REPORT, ""}:
        blockers.append(_issue("invalid_data_quality_artifact_type", "Data-quality artifact type must be data_quality_report."))
    if quality_report.get("complete") is not True:
        blockers.append(_issue("incomplete_data_quality", "Data-quality report is incomplete."))
    blockers.extend(_quality_scope_blockers(quality_report, data_scope))
    return summary, blockers, warnings


def _quality_scope_blockers(quality_report: Mapping[str, Any], data_scope: Mapping[str, Any]) -> list[ResearchIssue]:
    blockers: list[ResearchIssue] = []
    if not data_scope:
        return blockers
    report_symbols = [str(item).strip().upper() for item in _sequence(quality_report.get("symbols")) if str(item).strip()]
    scope_symbols = [str(item).strip().upper() for item in _sequence(data_scope.get("symbols")) if str(item).strip()]
    if report_symbols and scope_symbols and report_symbols != scope_symbols:
        blockers.append(_issue("data_quality_symbol_mismatch", "Data-quality symbols do not match backtest data scope."))
    for field in ("asset_class", "timeframe", "source_filter"):
        report_value = quality_report.get(field)
        scope_value = data_scope.get(field)
        if _normalize_optional_text(report_value) != _normalize_optional_text(scope_value):
            blockers.append(_issue(f"data_quality_{field}_mismatch", f"Data-quality {field} does not match backtest data scope."))
    quality_window = _window_payload(quality_report)
    scope_window = _window_payload(data_scope)
    if quality_window and scope_window:
        quality_range = (_normalize_optional_text(quality_window.get("start")), _normalize_optional_text(quality_window.get("end")))
        scope_range = (_normalize_optional_text(scope_window.get("start")), _normalize_optional_text(scope_window.get("end")))
        if quality_range != scope_range:
            blockers.append(_issue("data_quality_window_mismatch", "Data-quality time window does not match backtest data scope."))
    total_bars = quality_report.get("total_bars", quality_report.get("total_rows"))
    scope_rows = data_scope.get("total_rows")
    if total_bars is not None and scope_rows is not None and int(total_bars) != int(scope_rows):
        blockers.append(_issue("data_quality_row_count_mismatch", "Data-quality row count does not match backtest data scope."))
    return blockers


def _quality_caveats(summary: Mapping[str, Any]) -> list[str]:
    if not summary.get("provided"):
        return ["Data-quality evidence was not supplied."]
    return [str(message) for message in _sequence(summary.get("warnings"))]


def _quality_identity(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Return transport-independent quality evidence for stable report IDs."""
    return {key: value for key, value in summary.items() if key != "source"}


def _core_metrics(metrics: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    strategy_performance = _mapping(result.get("strategy_performance"))
    return {
        "total_return": _first(metrics.get("total_return"), strategy_performance.get("total_return")),
        "sharpe": _first(metrics.get("sharpe"), strategy_performance.get("sharpe")),
        "max_drawdown": _first(metrics.get("max_drawdown"), strategy_performance.get("max_drawdown")),
        "turnover": _first(metrics.get("turnover"), strategy_performance.get("turnover")),
        "trade_count": _first(metrics.get("trade_count"), strategy_performance.get("trade_count")),
        "hit_rate": _first(strategy_performance.get("hit_rate"), strategy_performance.get("win_rate")),
        "failed_runs": metrics.get("failed_runs", result.get("failed_runs")),
        "warnings_count": metrics.get("warnings_count"),
        "alpha": metrics.get("alpha", result.get("alpha")),
        "beta": metrics.get("beta", result.get("beta")),
        "tracking_error": result.get("tracking_error"),
        "information_ratio": result.get("information_ratio"),
    }


def _trade_stats(metrics: Mapping[str, Any], result: Mapping[str, Any], trades_path: Path | None) -> dict[str, Any]:
    strategy_performance = _mapping(result.get("strategy_performance"))
    trade_count = _first(metrics.get("trade_count"), strategy_performance.get("trade_count"), len(_sequence(result.get("trades"))))
    trade_rows = _read_trade_rows(trades_path)
    if trade_rows is not None:
        trade_count = len(trade_rows)
    return {
        "trade_count": trade_count,
        "hit_rate": _first(strategy_performance.get("hit_rate"), strategy_performance.get("win_rate")),
        "profit_factor": strategy_performance.get("profit_factor"),
        "expectancy": strategy_performance.get("expectancy"),
        "avg_win": strategy_performance.get("avg_win"),
        "avg_loss": strategy_performance.get("avg_loss"),
        "realized_pnl": result.get("realized_pnl"),
        "trades_path": str(trades_path) if trades_path else None,
    }


def _cost_summary(metrics: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    assumptions = _mapping(result.get("assumptions"))
    return {
        "assumptions": {
            "fees": _mapping(assumptions.get("fees")),
            "slippage": _mapping(assumptions.get("slippage")),
        },
        "realized_fees": _first(metrics.get("fees"), result.get("total_fees")),
        "realized_slippage": _first(metrics.get("slippage"), result.get("total_slippage")),
    }


def _benchmark_metrics(metrics: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    benchmark = _mapping(result.get("benchmark_performance"))
    return {
        "benchmark_total_return": benchmark.get("total_return"),
        "benchmark_sharpe": benchmark.get("sharpe"),
        "benchmark_max_drawdown": benchmark.get("max_drawdown"),
        "alpha": _first(metrics.get("alpha"), result.get("alpha")),
        "beta": _first(metrics.get("beta"), result.get("beta")),
        "tracking_error": result.get("tracking_error"),
        "information_ratio": result.get("information_ratio"),
    }


def _metric_blockers(metrics: Mapping[str, Any], trade_stats: Mapping[str, Any]) -> list[ResearchIssue]:
    blockers: list[ResearchIssue] = []
    trade_count = _optional_float(trade_stats.get("trade_count"))
    if trade_count is not None and trade_count <= 0:
        blockers.append(_issue("zero_trades", "Backtest executed zero trades."))
    if metrics.get("run_id") is None:
        blockers.append(_issue("missing_metrics_run_id", "metrics.json does not contain run_id."))
    return blockers


def _metric_caveats(
    core_metrics: Mapping[str, Any],
    trade_stats: Mapping[str, Any],
    costs: Mapping[str, Any],
    benchmark: Mapping[str, Any],
) -> list[str]:
    caveats: list[str] = []
    if trade_stats.get("hit_rate") is None:
        caveats.append("Win-rate/hit-rate is unavailable.")
    if _optional_float(trade_stats.get("trade_count")) == 0:
        caveats.append("Backtest executed zero trades; performance is not strategy-action evidence.")
    if benchmark.get("benchmark_total_return") is None:
        caveats.append("Benchmark total return is unavailable.")
    if benchmark.get("tracking_error") is None:
        caveats.append("Tracking error is unavailable.")
    if _optional_float(costs.get("realized_fees")) == 0 and _optional_float(costs.get("realized_slippage")) == 0:
        caveats.append("Backtest used or realized zero fees and zero slippage.")
    if core_metrics.get("sharpe") is None:
        caveats.append("Sharpe ratio is unavailable.")
    return caveats


def _bundle_paths(bundle_dir: Path) -> dict[str, Any]:
    paths = {
        "artifact_dir": str(bundle_dir),
        "backtest_run_ref": str(bundle_dir / "backtest_run_ref.json"),
        "result": str(bundle_dir / "result.json"),
        "metrics": str(bundle_dir / "metrics.json"),
        "provenance": str(bundle_dir / "provenance.json"),
        "equity_curve": str(bundle_dir / "equity_curve.csv"),
        "benchmark_curve": str(bundle_dir / "benchmark_curve.csv"),
        "positions": str(bundle_dir / "positions.csv"),
    }
    trades_path = bundle_dir / "trades.csv"
    if trades_path.exists():
        paths["trades"] = str(trades_path)
    return paths


def _read_trade_rows(path: Path | None) -> list[dict[str, Any]] | None:
    if path is None or not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _issue(code: str, message: str, details: Mapping[str, Any] | None = None) -> ResearchIssue:
    return ResearchIssue(code=code, message=message, details=details or {})


def _dedupe_issues(issues: list[ResearchIssue]) -> list[ResearchIssue]:
    seen: set[tuple[str, str]] = set()
    output: list[ResearchIssue] = []
    for issue in issues:
        key = (issue.code, issue.message)
        if key in seen:
            continue
        seen.add(key)
        output.append(issue)
    return output


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _issue_sequence(value: Any) -> list[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    for item in _sequence(value):
        output.append(item if isinstance(item, MappingABC) else {"message": str(item)})
    return output


def _sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, MappingABC) else {}


def _window_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    window = payload.get("time_range", payload.get("requested_window"))
    return window if isinstance(window, MappingABC) else {}


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _jsonable(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
