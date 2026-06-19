"""Research recommendation scoring for AI/tool workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifacts import LoadedArtifacts, load_operator_context, load_strategy_artifacts
from .contracts import write_json_artifact
from .suites import suggest_follow_up_suite


@dataclass(frozen=True)
class RecommendationSettings:
    """Thresholds that decide whether comparison rows become accepted candidates.

    These settings gate data-quality requirements, warning counts, drawdown,
    turnover, and minimum trade count during recommendation scoring. Keeping them
    in a dataclass makes tests and operator workflows explicit about which risk
    tolerance was applied to a recommendation payload.
    """

    allow_missing_data_quality: bool = False
    allow_data_quality_gaps: bool = False
    max_warnings: int = 2
    max_drawdown: float = 0.15
    max_turnover: float = 10.0
    min_trade_count: int = 3


@dataclass(frozen=True)
class RecommendationResult:
    """Recommendation payload plus recoverable warnings from optional context loading.

    The payload contains accepted/rejected candidates, data-quality context,
    operator blockers, prior artifacts, and suggested follow-up experiments. The
    top-level warning sequence carries non-fatal issues from comparison inputs,
    operator context files, or prior artifact loading.
    """

    recommendation_id: str
    payload: Mapping[str, Any]
    warnings: Sequence[str] = field(default_factory=tuple)


def build_recommendations(
    comparison: Mapping[str, Any],
    *,
    experiment_name: str,
    data_quality: Mapping[str, Any] | None = None,
    operator_contexts: Sequence[Mapping[str, Any]] | None = None,
    prior_artifacts: LoadedArtifacts | None = None,
    settings: RecommendationSettings | None = None,
) -> RecommendationResult:
    """Score experiment comparison rows into accepted and rejected recommendations.

    Each successful row is checked against configured risk/data-quality thresholds,
    operator blocking context, and available prior artifacts, then assigned a
    bounded score from performance, drawdown, turnover, fees, warnings, and data
    quality. Accepted and rejected candidates are sorted deterministically, and the
    final recommendation ID is derived from the ranked candidate payload.
    """
    settings = settings or RecommendationSettings()
    rows = comparison.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    operator_contexts = tuple(operator_contexts or ())
    operator_reasons = _operator_blocking_reasons(operator_contexts)
    data_quality_reasons = _data_quality_reasons(data_quality, settings)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        reasons = _candidate_rejection_reasons(row, settings)
        reasons.extend(data_quality_reasons)
        score = _candidate_score(row, operator_reasons=operator_reasons, data_quality_reasons=data_quality_reasons)
        candidate = _candidate_payload(
            row,
            score=score,
            reasons=reasons,
            operator_reasons=operator_reasons,
            promotion_ready=not reasons and not operator_reasons,
        )
        if reasons:
            rejected.append(candidate)
        else:
            accepted.append(candidate)

    accepted.sort(key=lambda candidate: (-float(candidate["score"]), str(candidate.get("run_id") or "")))
    rejected.sort(key=lambda candidate: (-float(candidate["score"]), str(candidate.get("run_id") or "")))
    all_candidates = accepted + rejected
    rec_id = _recommendation_id(experiment_name, all_candidates)
    payload = {
        "schema_version": "1",
        "recommendation_id": rec_id,
        "experiment_name": experiment_name,
        "accepted_candidates": accepted,
        "rejected_candidates": rejected,
        "operator_context": {
            "blocking_reasons": operator_reasons,
            "contexts_count": len(operator_contexts),
        },
        "data_quality": data_quality or None,
        "prior_artifacts": prior_artifacts.artifacts if prior_artifacts is not None else {},
        "suggested_next_experiments": [
            suggest_follow_up_suite(
                {
                    "accepted_candidates": accepted,
                    "rejected_candidates": rejected,
                }
            )
        ],
    }
    warnings = list(comparison.get("warnings", [])) if isinstance(comparison.get("warnings"), list) else []
    if prior_artifacts is not None:
        warnings.extend(prior_artifacts.warnings)
    return RecommendationResult(recommendation_id=rec_id, payload=payload, warnings=tuple(str(warning) for warning in warnings))


def build_recommendations_from_files(
    comparison: Mapping[str, Any],
    *,
    experiment_name: str,
    data_quality_path: str | Path | None = None,
    operator_context_paths: Sequence[str | Path] | None = None,
    prior_artifact_paths: Sequence[str | Path] | None = None,
    output_path: str | Path | None = None,
    settings: RecommendationSettings | None = None,
) -> RecommendationResult:
    """Load file-backed context inputs before building recommendation output.

    Optional data-quality, operator-context, and prior-artifact files are parsed
    through the same best-effort helpers used by discovery. The resulting
    recommendation payload can optionally be written to disk, while load warnings
    are preserved on the returned result instead of aborting ranking.
    """
    data_quality = _load_optional_mapping(data_quality_path)
    operator_contexts, context_warnings = load_operator_context(tuple(operator_context_paths or ()))
    artifacts = load_strategy_artifacts(tuple(prior_artifact_paths or ()))
    result = build_recommendations(
        comparison,
        experiment_name=experiment_name,
        data_quality=data_quality,
        operator_contexts=operator_contexts,
        prior_artifacts=artifacts,
        settings=settings,
    )
    warnings = tuple([*result.warnings, *context_warnings])
    payload = dict(result.payload)
    if output_path is not None:
        write_json_artifact(payload, output_path)
    return RecommendationResult(result.recommendation_id, payload, warnings)


def _candidate_rejection_reasons(
    row: Mapping[str, Any],
    settings: RecommendationSettings,
) -> list[str]:
    reasons: list[str] = []
    if str(row.get("status") or "").lower() != "success":
        reasons.append("failed_run")
    if row.get("total_return") is None and row.get("sharpe") is None:
        reasons.append("missing_result_summary")
    warnings_count = _float(row.get("warnings_count"), 0.0)
    if warnings_count > settings.max_warnings:
        reasons.append("too_many_warnings")
    drawdown = abs(_float(row.get("max_drawdown"), 0.0))
    if drawdown > settings.max_drawdown:
        reasons.append("excessive_drawdown")
    turnover = abs(_float(row.get("turnover"), 0.0))
    if turnover > settings.max_turnover:
        reasons.append("excessive_turnover")
    trade_count_raw = row.get("trade_count")
    if trade_count_raw is not None and _float(trade_count_raw, 0.0) < settings.min_trade_count:
        reasons.append("insufficient_trade_count")
    return reasons


def _data_quality_reasons(
    data_quality: Mapping[str, Any] | None,
    settings: RecommendationSettings,
) -> list[str]:
    if data_quality is None:
        return [] if settings.allow_missing_data_quality else ["missing_data_quality"]
    if settings.allow_data_quality_gaps:
        return []
    summaries = data_quality.get("summaries", [])
    if not isinstance(summaries, list):
        return []
    for summary in summaries:
        if isinstance(summary, Mapping) and int(summary.get("missing_gaps", 0) or 0) > 0:
            return ["data_quality_missing_gaps"]
    return []


def _operator_blocking_reasons(contexts: Sequence[Mapping[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for context in contexts:
        halt = context.get("halt")
        if isinstance(halt, Mapping) and bool(halt.get("halted")):
            reasons.append("operator_halted")
        health = context.get("health")
        if isinstance(health, Mapping):
            exit_code = int(health.get("exit_code", 0) or 0)
            if exit_code >= 2:
                reasons.append("operator_unhealthy")
            elif exit_code >= 1:
                reasons.append("operator_degraded")
        market_data = context.get("market_data")
        if isinstance(market_data, Mapping) and int(market_data.get("stale_count", 0) or 0) > 0:
            reasons.append("operator_stale_market_data")
        open_orders = context.get("open_orders")
        if isinstance(open_orders, Mapping) and int(open_orders.get("stale_count", 0) or 0) > 0:
            reasons.append("operator_stale_open_orders")
    return sorted(set(reasons))


def _candidate_score(
    row: Mapping[str, Any],
    *,
    operator_reasons: Sequence[str],
    data_quality_reasons: Sequence[str],
) -> float:
    total_return = _clip(_float(row.get("total_return"), 0.0), -0.5, 0.5)
    sharpe = _clip(_float(row.get("sharpe"), 0.0), -3.0, 3.0)
    drawdown = _clip(abs(_float(row.get("max_drawdown"), 0.0)), 0.0, 0.5)
    turnover = _clip(abs(_float(row.get("turnover"), 0.0)), 0.0, 20.0)
    fees = _clip(abs(_float(row.get("fees"), 0.0)) + abs(_float(row.get("slippage"), 0.0)), 0.0, 1000.0)
    warnings_count = _clip(_float(row.get("warnings_count"), 0.0), 0.0, 10.0)
    score = 0.0
    score += 25.0 * ((total_return + 0.5) / 1.0)
    score += 25.0 * ((sharpe + 3.0) / 6.0)
    score += 20.0 * (1.0 - drawdown / 0.5)
    score += 10.0 * (1.0 - turnover / 20.0)
    score += 10.0 * (1.0 - fees / 1000.0)
    score += 5.0 * (0.0 if data_quality_reasons else 1.0)
    score += 5.0 * (1.0 - min(1.0, warnings_count / 10.0))
    if operator_reasons:
        score -= 5.0
    return round(max(0.0, min(100.0, score)), 4)


def _candidate_payload(
    row: Mapping[str, Any],
    *,
    score: float,
    reasons: Sequence[str],
    operator_reasons: Sequence[str],
    promotion_ready: bool,
) -> dict[str, Any]:
    payload = {
        "recommendation_id": _recommendation_id(str(row.get("run_id") or ""), [row]),
        "experiment_run_id": row.get("experiment_run_id"),
        "run_id": row.get("run_id"),
        "strategy_id": row.get("strategy_id"),
        "strategy_name": row.get("strategy_name"),
        "strategy_version": row.get("strategy_version"),
        "symbols": row.get("symbols"),
        "asset_class": row.get("asset_class"),
        "timeframe": row.get("timeframe"),
        "start_ts": row.get("start_ts"),
        "end_ts": row.get("end_ts"),
        "parameters": row.get("parameters") if isinstance(row.get("parameters"), Mapping) else {},
        "assumptions": row.get("assumptions") if isinstance(row.get("assumptions"), Mapping) else {},
        "score": score,
        "promotion_ready": promotion_ready,
        "reasons": list(reasons),
        "operator_reasons": list(operator_reasons),
        "metrics": {
            "total_return": row.get("total_return"),
            "sharpe": row.get("sharpe"),
            "max_drawdown": row.get("max_drawdown"),
            "turnover": row.get("turnover"),
            "fees": row.get("fees"),
            "slippage": row.get("slippage"),
            "alpha": row.get("alpha"),
            "beta": row.get("beta"),
            "warnings_count": row.get("warnings_count"),
            "trade_count": row.get("trade_count"),
        },
        "artifact_dir": row.get("artifact_dir"),
        "error_message": row.get("error_message"),
    }
    return payload


def _recommendation_id(seed: str, candidates: Sequence[Mapping[str, Any]]) -> str:
    payload = {"seed": seed, "candidates": list(candidates)}
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "rec_" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _load_optional_mapping(path: str | Path | None) -> Mapping[str, Any] | None:
    if path is None:
        return None
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(parsed, Mapping):
        raise ValueError(f"Expected JSON mapping: {path}")
    return parsed


def _float(value: object, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
