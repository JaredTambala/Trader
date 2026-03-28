"""Helpers for resolving runtime strategy metadata."""

from __future__ import annotations

import re

from .strategies.base import Strategy


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
