"""Helpers for resolving runtime strategy metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from .strategies.base import Strategy


@dataclass(frozen=True)
class StrategyInfo:
    """Structured strategy metadata for research provenance."""

    strategy_id: str
    name: str
    version: str = "unversioned"
    description: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    author: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable metadata mapping."""
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "parameters": dict(self.parameters),
            "author": self.author,
            "source": self.source,
        }


def infer_strategy_type_name(class_name: str) -> str:
    """Derive a readable strategy type from a class name."""
    normalized = class_name.strip() or "NoOpStrategy"
    if normalized.endswith("Strategy") and len(normalized) > len("Strategy"):
        normalized = normalized[: -len("Strategy")]
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", normalized).lower()
    return snake or "noop"


def resolve_strategy_id(strategy: Strategy | None, fallback: str) -> str:
    """Resolve the authoritative runtime strategy identifier."""
    if strategy is None:
        return fallback
    value = getattr(strategy, "strategy_id", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def resolve_strategy_type(strategy: Strategy | None, fallback: str) -> str:
    """Resolve the runtime strategy type from the concrete strategy class."""
    if strategy is None:
        return fallback
    return infer_strategy_type_name(strategy.__class__.__name__)


def resolve_strategy_info(
    strategy: Strategy | None,
    *,
    parameters: Mapping[str, Any] | None = None,
    fallback_id: str = "unknown",
) -> StrategyInfo:
    """Resolve structured strategy metadata from a strategy object."""
    if strategy is None:
        return StrategyInfo(
            strategy_id=fallback_id,
            name=fallback_id,
            parameters=dict(parameters or {}),
            source=None,
        )
    raw = getattr(strategy, "strategy_info", None)
    if callable(raw):
        raw = raw()
    if isinstance(raw, StrategyInfo):
        info = raw
    elif isinstance(raw, Mapping):
        info = StrategyInfo(
            strategy_id=str(raw.get("strategy_id") or resolve_strategy_id(strategy, fallback_id)),
            name=str(raw.get("name") or resolve_strategy_id(strategy, fallback_id)),
            version=str(raw.get("version") or "unversioned"),
            description=str(raw["description"]) if raw.get("description") is not None else None,
            parameters=_mapping_or_empty(raw.get("parameters")),
            author=str(raw["author"]) if raw.get("author") is not None else None,
            source=str(raw["source"]) if raw.get("source") is not None else None,
        )
    else:
        strategy_id = resolve_strategy_id(strategy, fallback_id)
        info = StrategyInfo(
            strategy_id=strategy_id,
            name=strategy_id,
            source=f"{strategy.__class__.__module__}.{strategy.__class__.__qualname__}",
        )
    merged_parameters = dict(info.parameters)
    merged_parameters.update(dict(parameters or {}))
    return StrategyInfo(
        strategy_id=info.strategy_id,
        name=info.name,
        version=info.version,
        description=info.description,
        parameters=merged_parameters,
        author=info.author,
        source=info.source or f"{strategy.__class__.__module__}.{strategy.__class__.__qualname__}",
    )


def _mapping_or_empty(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}
