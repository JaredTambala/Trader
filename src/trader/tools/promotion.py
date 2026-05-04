"""Dry-run paper promotion packet helpers."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from trader.research import apply_parameter_overrides

from .artifacts import build_strategy_artifact_metadata, load_operator_context
from .contracts import write_json_artifact


def build_promotion_packet(
    *,
    base_config_data: Mapping[str, Any],
    recommendation_payload: Mapping[str, Any],
    recommendation_id: str,
    output_root: str | Path = "artifacts/promotions",
    operator_context_paths: Sequence[str | Path] | None = None,
) -> dict[str, Any]:
    """Build a dry-run paper promotion packet for one recommendation."""
    candidate = _find_candidate(recommendation_payload, recommendation_id)
    output_dir = Path(output_root) / recommendation_id
    output_dir.mkdir(parents=True, exist_ok=True)
    operator_contexts, operator_warnings = load_operator_context(tuple(operator_context_paths or ()))
    proposed_config = _proposed_config(base_config_data, candidate)
    validation = _validation(candidate, proposed_config, operator_contexts, operator_warnings)
    config_path = output_dir / "proposed_paper_config.yaml"
    config_path.write_text(yaml.safe_dump(proposed_config, sort_keys=False), encoding="utf-8")
    metadata = build_strategy_artifact_metadata(
        strategy={
            "strategy_id": candidate.get("strategy_id"),
            "name": candidate.get("strategy_name") or candidate.get("strategy_id"),
            "version": candidate.get("strategy_version"),
        },
        parameters=_mapping(candidate.get("parameters")),
        risk_profile=_mapping(base_config_data.get("risk")),
        data_assumptions=_mapping(candidate.get("assumptions"))
        or _mapping(_mapping(base_config_data.get("backtest")).get("assumptions")),
        suite_id=None,
        suite_member_id=None,
        experiment_id=str(recommendation_payload.get("experiment_name") or ""),
        run_id=str(candidate.get("run_id") or ""),
        output_files={"artifact_dir": str(candidate.get("artifact_dir") or "")},
        recommendation=candidate,
    )
    metadata_path = write_json_artifact(metadata, output_dir / "strategy_artifact.json")
    validation_path = write_json_artifact(validation, output_dir / "dry_run_validation.json")
    packet = {
        "schema_version": "1",
        "recommendation_id": recommendation_id,
        "promotion_ready": bool(validation["promotion_ready"]),
        "candidate": candidate,
        "proposed_config": str(config_path),
        "strategy_artifact": str(metadata_path),
        "dry_run_validation": str(validation_path),
    }
    packet_path = write_json_artifact(packet, output_dir / "promotion_packet.json")
    return {
        **packet,
        "promotion_packet": str(packet_path),
        "output_dir": str(output_dir),
    }


def _find_candidate(recommendation_payload: Mapping[str, Any], recommendation_id: str) -> Mapping[str, Any]:
    for key in ("accepted_candidates", "rejected_candidates"):
        candidates = recommendation_payload.get(key, [])
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if isinstance(candidate, Mapping) and candidate.get("recommendation_id") == recommendation_id:
                return candidate
    raise ValueError(f"Recommendation candidate not found: {recommendation_id}")


def _proposed_config(base_config_data: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    config = deepcopy(dict(base_config_data))
    runtime = dict(_mapping(config.get("runtime")))
    runtime["mode"] = "once"
    config["runtime"] = runtime
    broker = dict(_mapping(config.get("broker")))
    broker["type"] = "alpaca"
    config["broker"] = broker
    strategy = dict(_mapping(config.get("strategy")))
    if candidate.get("strategy_id"):
        strategy["id"] = candidate["strategy_id"]
    if candidate.get("timeframe"):
        strategy["timeframe"] = candidate["timeframe"]
    config["strategy"] = strategy
    market_data = dict(_mapping(config.get("market_data")))
    if candidate.get("symbols"):
        market_data["symbols"] = _symbols(candidate.get("symbols"))
    if candidate.get("asset_class"):
        market_data["asset_class"] = candidate["asset_class"]
    config["market_data"] = market_data
    parameters = candidate.get("parameters")
    if isinstance(parameters, Mapping):
        apply_parameter_overrides(config, parameters)
    config["promotion"] = {
        "source_recommendation_id": candidate.get("recommendation_id"),
        "source_run_id": candidate.get("run_id"),
        "source_experiment_run_id": candidate.get("experiment_run_id"),
        "dry_run_only": True,
    }
    return config


def _validation(
    candidate: Mapping[str, Any],
    proposed_config: Mapping[str, Any],
    operator_contexts: Sequence[Mapping[str, Any]],
    operator_warnings: Sequence[str],
) -> dict[str, Any]:
    blockers: list[str] = []
    broker = _mapping(proposed_config.get("broker"))
    broker_type = str(broker.get("type", "")).lower()
    if broker_type not in {"alpaca", "alpaca-paper", "alpaca_paper"}:
        blockers.append("broker_not_alpaca_paper")
    if not bool(candidate.get("promotion_ready")):
        blockers.append("candidate_not_promotion_ready")
    _append_context_blockers(candidate, proposed_config, blockers)
    for context in operator_contexts:
        halt = context.get("halt")
        if isinstance(halt, Mapping) and halt.get("halted"):
            blockers.append("operator_halted")
        open_orders = context.get("open_orders")
        if isinstance(open_orders, Mapping) and int(open_orders.get("stale_count", 0) or 0) > 0:
            blockers.append("stale_open_orders")
        market_data = context.get("market_data")
        if isinstance(market_data, Mapping) and int(market_data.get("stale_count", 0) or 0) > 0:
            blockers.append("stale_market_data")
    return {
        "schema_version": "1",
        "promotion_ready": not blockers,
        "blockers": sorted(set(blockers)),
        "warnings": list(operator_warnings),
        "operator_contexts_count": len(operator_contexts),
        "starts_trading": False,
    }


def _append_context_blockers(
    candidate: Mapping[str, Any],
    proposed_config: Mapping[str, Any],
    blockers: list[str],
) -> None:
    market_data = _mapping(proposed_config.get("market_data"))
    strategy = _mapping(proposed_config.get("strategy"))
    candidate_symbols = _symbols(candidate.get("symbols"))
    config_symbols = _symbols(market_data.get("symbols"))
    if candidate_symbols and config_symbols and candidate_symbols != config_symbols:
        blockers.append("symbols_mismatch")
    candidate_asset_class = str(candidate.get("asset_class") or "").strip().lower()
    config_asset_class = str(market_data.get("asset_class") or "").strip().lower()
    if candidate_asset_class and config_asset_class and candidate_asset_class != config_asset_class:
        blockers.append("asset_class_mismatch")
    candidate_timeframe = str(candidate.get("timeframe") or "").strip()
    config_timeframe = str(strategy.get("timeframe") or "").strip()
    if candidate_timeframe and config_timeframe and candidate_timeframe != config_timeframe:
        blockers.append("timeframe_mismatch")


def _symbols(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
    if isinstance(value, (list, tuple)):
        return [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
    return []


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}
