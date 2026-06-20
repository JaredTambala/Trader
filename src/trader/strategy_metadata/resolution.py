"""Runtime strategy metadata resolution helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..strategies.base import Strategy


@dataclass(frozen=True)
class StrategyInfo:
    """Serializable metadata describing a strategy implementation and version.

    Research and backtest persistence use this shape to record strategy identity
    without importing the concrete strategy class later.
    """

    strategy_id: str
    name: str
    version: str = "unversioned"
    description: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    author: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize strategy identity and parameters for persistence and artifacts.

        The returned mapping contains only plain values, so run metadata can record
        the strategy implementation without importing or pickling the concrete
        strategy class later.
        """
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
    """Derive a snake_case strategy type label from a class name.

    A trailing `Strategy` suffix is removed before CamelCase is converted, and
    blank inputs fall back to `noop`.
    """
    normalized = class_name.strip() or "NoOpStrategy"
    if normalized.endswith("Strategy") and len(normalized) > len("Strategy"):
        normalized = normalized[: -len("Strategy")]
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", normalized).lower()
    return snake or "noop"


def resolve_strategy_id(strategy: Strategy | None, fallback: str) -> str:
    """Return the strategy-provided ID when present, otherwise a fallback.

    Blank or missing IDs are ignored so run metadata always has a stable
    configured identifier.
    """
    if strategy is None:
        return fallback
    value = getattr(strategy, "strategy_id", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def resolve_strategy_type(strategy: Strategy | None, fallback: str) -> str:
    """Resolve a runtime type label from the concrete strategy class name."""
    if strategy is None:
        return fallback
    return infer_strategy_type_name(strategy.__class__.__name__)


def resolve_strategy_info(
    strategy: Strategy | None,
    *,
    parameters: Mapping[str, Any] | None = None,
    fallback_id: str = "unknown",
) -> StrategyInfo:
    """Build complete strategy provenance from object metadata and overrides.

    The function accepts a `StrategyInfo`, a mapping returned by
    `strategy_info()`, or no explicit metadata. Caller-supplied parameters are
    merged last so research workflows can attach run-specific inputs.
    """
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
