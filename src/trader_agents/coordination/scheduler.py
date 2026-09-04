"""Deterministic dependency, concurrency, mutation, and budget scheduling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from trader_research.governance import AgentBudget

from trader_agents.contracts.domain import (
    AgendaTaskProposal,
    BudgetUsage,
    CoordinatorAgenda,
)


@dataclass(frozen=True)
class BudgetReservation:
    """Hard specialist budget reserved before concurrent dispatch."""

    model_calls: int
    tool_calls: int
    tokens: int

    def __post_init__(self) -> None:
        """Require usable positive reservations."""
        if min(self.model_calls, self.tool_calls, self.tokens) <= 0:
            raise ValueError("specialist budget reservations must be positive")


@dataclass(frozen=True)
class ScheduledTask:
    """One agenda task admitted to the current deterministic ready set."""

    task: AgendaTaskProposal
    mutation_keys: tuple[str, ...]
    reservation: BudgetReservation


class SchedulingError(ValueError):
    """Raised when no safe legal ready set can be constructed."""


def compute_ready_set(
    agenda: CoordinatorAgenda,
    *,
    completed_task_ids: Sequence[str],
    active_task_ids: Sequence[str] = (),
    active_mutation_keys: Sequence[str] = (),
    mutation_keys_by_task: Mapping[str, Sequence[str]] | None = None,
    budget: AgentBudget,
    usage: BudgetUsage,
) -> tuple[ScheduledTask, ...]:
    """Compute the legal bounded ready set without performing work.

    Tasks are considered in agenda order. Dependencies are hard joins, active
    tasks cannot be dispatched twice, and overlapping mutation keys serialize.
    Read-only tasks may run concurrently up to the session limit.

    Args:
        agenda: Validated visible task DAG.
        completed_task_ids: Tasks with accepted specialist returns.
        active_task_ids: Tasks already dispatched and not yet accepted.
        active_mutation_keys: Mutation resources held by active work.
        mutation_keys_by_task: Exact deterministic resource keys per task.
        budget: Immutable session budget.
        usage: Cumulative accepted session usage.

    Returns:
        Ordered tasks with hard budget reservations.

    Raises:
        SchedulingError: If identities are unknown or remaining resources
            cannot fund any otherwise-ready work.
    """
    known = {task.task_id for task in agenda.tasks}
    completed = set(completed_task_ids)
    active = set(active_task_ids)
    unknown = (completed | active) - known
    if unknown:
        raise SchedulingError(
            "task state contains unknown IDs: " + ", ".join(sorted(unknown))
        )
    if completed & active:
        raise SchedulingError("a task cannot be both active and completed")
    remaining_slots = budget.concurrency_limit - len(active)
    if remaining_slots <= 0:
        return ()

    mutation_map = mutation_keys_by_task or {}
    held_keys = set(active_mutation_keys)
    candidates: list[tuple[AgendaTaskProposal, tuple[str, ...]]] = []
    for task in agenda.tasks:
        if task.task_id in completed or task.task_id in active:
            continue
        if not set(task.dependencies).issubset(completed):
            continue
        keys = tuple(sorted(set(mutation_map.get(task.task_id, ()))))
        if task.mutation_requested and not keys:
            raise SchedulingError(
                f"mutating task {task.task_id} has no deterministic mutation key"
            )
        if held_keys.intersection(keys):
            continue
        candidates.append((task, keys))
        held_keys.update(keys)
        if len(candidates) >= remaining_slots:
            break
    if not candidates:
        return ()

    reservations = _reserve_budgets(
        count=len(candidates),
        budget=budget,
        usage=usage,
    )
    return tuple(
        ScheduledTask(task=task, mutation_keys=keys, reservation=reservation)
        for (task, keys), reservation in zip(candidates, reservations, strict=True)
    )


def _reserve_budgets(
    *,
    count: int,
    budget: AgentBudget,
    usage: BudgetUsage,
) -> tuple[BudgetReservation, ...]:
    """Split remaining model/tool/token ceilings across a ready set."""
    remaining_models = budget.max_model_calls - usage.model_calls
    remaining_tools = budget.max_tool_calls - usage.tool_calls
    remaining_tokens = budget.max_tokens - usage.total_tokens
    if min(remaining_models, remaining_tools, remaining_tokens) < count:
        raise SchedulingError("remaining session budget cannot fund the ready set")
    per_models = min(20, remaining_models // count)
    per_tools = min(20, remaining_tools // count)
    per_tokens = min(60_000, remaining_tokens // count)
    return tuple(
        BudgetReservation(
            model_calls=per_models,
            tool_calls=per_tools,
            tokens=per_tokens,
        )
        for _ in range(count)
    )
