"""Validate optimization observations against declared scalar constraints.

The helpers are deterministic and side-effect free. They distinguish missing
or non-finite metrics from ordinary threshold failures and return stable blocker
messages for canonical trial records.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def constraint_blockers(
    constraints: Sequence[Mapping[str, Any]],
    observation: Mapping[str, Any],
) -> list[str]:
    """Evaluate declared scalar constraints against one closed observation.

    Metrics that are absent, boolean, or non-numeric are reported as unavailable.
    Maintained ``lt``, ``lte``, ``gt``, ``gte``, and ``eq`` operators compare
    finite values normalized by the plan-validation boundary.

    Returns:
        Blockers in declared constraint order; an empty list means every
        constraint passed.
    """
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
