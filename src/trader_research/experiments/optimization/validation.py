"""Shared validation rules for optimization observations."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def constraint_blockers(
    constraints: Sequence[Mapping[str, Any]],
    observation: Mapping[str, Any],
) -> list[str]:
    """Return deterministic blockers for failed or unavailable constraint metrics."""
    metrics = dict(observation.get("metrics") or {})
    blockers: list[str] = []
    operations = {
        "lt": lambda actual, expected: actual < expected,
        "lte": lambda actual, expected: actual <= expected,
        "gt": lambda actual, expected: actual > expected,
        "gte": lambda actual, expected: actual >= expected,
        "eq": lambda actual, expected: actual == expected,
    }
    for constraint in constraints:
        name = str(constraint["metric"])
        actual = metrics.get(name)
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            blockers.append(f"constraint metric is unavailable: {name}")
            continue
        if not operations[str(constraint["operator"])](
            float(actual), float(constraint["value"])
        ):
            blockers.append(
                f"constraint failed: {name} {constraint['operator']} {constraint['value']}"
            )
    return blockers
