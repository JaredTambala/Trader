"""Research suite expansion for AI/tool discovery workflows."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from trader_research.research import apply_parameter_overrides


SUPPORTED_STRATEGY_FAMILIES = ("trend_following", "mean_reversion", "bollinger_band")


@dataclass(frozen=True)
class SuiteMember:
    """One deterministic research-suite member."""

    suite_id: str
    suite_member_id: str
    strategy_family: str
    parameters: Mapping[str, Any]
    config_data: Mapping[str, Any]


def build_suite_members(
    config_data: Mapping[str, Any],
    *,
    strategy_families: Sequence[str],
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    max_runs: int = 25,
    source_recommendation_ids: Sequence[str] | None = None,
) -> list[SuiteMember]:
    """Expand strategy families into deterministic suite members."""
    if max_runs <= 0:
        raise ValueError("max_runs must be positive")
    if len(symbols) > 20:
        raise ValueError("Discovery suite supports at most 20 symbols")
    families = [_normalize_strategy_family(family) for family in strategy_families]
    if not families:
        raise ValueError("At least one strategy family is required")
    suite_payload = {
        "strategy_families": families,
        "symbols": list(symbols),
        "asset_class": asset_class,
        "timeframe": timeframe,
        "source_recommendation_ids": list(source_recommendation_ids or ()),
    }
    suite_id = _stable_id("suite", suite_payload)
    members: list[SuiteMember] = []
    suite_cfg = _mapping(_mapping(config_data.get("research")).get("suite"))
    strategy_cfg_by_family = _suite_strategy_config(suite_cfg)

    for family in families:
        parameter_grid = _family_parameter_grid(strategy_cfg_by_family.get(family, {}), family)
        for parameters in parameter_grid:
            if len(members) >= max_runs:
                raise ValueError(f"research suite expands beyond max_runs={max_runs}")
            member_config = _member_config(config_data, family, symbols, asset_class, timeframe, parameters)
            member_payload = {
                "suite_id": suite_id,
                "strategy_family": family,
                "parameters": dict(parameters),
            }
            members.append(
                SuiteMember(
                    suite_id=suite_id,
                    suite_member_id=_stable_id("suite_member", member_payload),
                    strategy_family=family,
                    parameters=dict(parameters),
                    config_data=member_config,
                )
            )
    return members


def suggest_follow_up_suite(recommendations: Mapping[str, Any]) -> dict[str, Any]:
    """Build a simple follow-up-suite suggestion from recommendation output."""
    accepted = recommendations.get("accepted_candidates", [])
    rejected = recommendations.get("rejected_candidates", [])
    strategy_families: list[str] = []
    source_ids: list[str] = []
    for candidate in accepted if isinstance(accepted, list) else []:
        if not isinstance(candidate, Mapping):
            continue
        family = str(candidate.get("strategy_id") or "").strip()
        if family and family not in strategy_families:
            strategy_families.append(family)
        recommendation_id = str(candidate.get("recommendation_id") or "").strip()
        if recommendation_id:
            source_ids.append(recommendation_id)
    excluded = [
        str(candidate.get("strategy_id"))
        for candidate in rejected
        if isinstance(candidate, Mapping)
        and any(
            reason in set(candidate.get("reasons", []))
            for reason in {"data_quality_missing_gaps", "excessive_turnover", "failed_run"}
        )
    ]
    return {
        "strategy_families": strategy_families,
        "source_recommendation_ids": source_ids,
        "excluded_strategy_families": sorted({item for item in excluded if item}),
        "reason": "Narrow around accepted candidates and exclude hard-rejected families.",
    }


def _suite_strategy_config(suite_cfg: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    strategies = suite_cfg.get("strategies", [])
    result: dict[str, Mapping[str, Any]] = {}
    if not isinstance(strategies, list):
        return result
    for entry in strategies:
        if not isinstance(entry, Mapping):
            continue
        family = _normalize_strategy_family(str(entry.get("id", "")))
        result[family] = entry
    return result


def _family_parameter_grid(entry: Mapping[str, Any], family: str) -> list[dict[str, Any]]:
    parameters = entry.get("parameters")
    if parameters is None:
        return [{}]
    if not isinstance(parameters, Mapping):
        raise ValueError(f"research.suite.strategies.{family}.parameters must be a mapping")
    keys = sorted(str(key) for key in parameters.keys())
    values_by_key: list[list[Any]] = []
    for key in keys:
        raw_values = parameters[key]
        if not isinstance(raw_values, Sequence) or isinstance(raw_values, (str, bytes)):
            raise ValueError(f"Suite parameter {key} must be a list")
        values = list(raw_values)
        if not values:
            raise ValueError(f"Suite parameter {key} must not be empty")
        values_by_key.append(values)
    return [dict(zip(keys, combination)) for combination in _product(values_by_key)]


def _member_config(
    config_data: Mapping[str, Any],
    family: str,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    parameters: Mapping[str, Any],
) -> Mapping[str, Any]:
    config_copy = deepcopy(dict(config_data))
    strategy_cfg = dict(_mapping(config_copy.get("strategy")))
    strategy_cfg["id"] = family
    strategy_cfg["timeframe"] = timeframe
    strategy_cfg.setdefault(family, {})
    config_copy["strategy"] = strategy_cfg
    market_data_cfg = dict(_mapping(config_copy.get("market_data")))
    market_data_cfg["symbols"] = list(symbols)
    market_data_cfg["asset_class"] = asset_class
    config_copy["market_data"] = market_data_cfg
    backtest_cfg = dict(_mapping(config_copy.get("backtest")))
    backtest_cfg["symbols"] = list(symbols)
    backtest_cfg["asset_class"] = asset_class
    backtest_cfg["timeframe"] = timeframe
    config_copy["backtest"] = backtest_cfg
    apply_parameter_overrides(config_copy, parameters)
    return config_copy


def _normalize_strategy_family(value: str) -> str:
    family = value.strip().lower().replace("-", "_")
    if family not in SUPPORTED_STRATEGY_FAMILIES:
        raise ValueError(f"Unsupported strategy family: {value}")
    return family


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _product(values_by_key: Sequence[Sequence[Any]]) -> list[tuple[Any, ...]]:
    if not values_by_key:
        return [tuple()]
    head, *tail = values_by_key
    suffixes = _product(tail)
    return [(value, *suffix) for value in head for suffix in suffixes]
