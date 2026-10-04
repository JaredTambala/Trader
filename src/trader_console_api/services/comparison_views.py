"""Comparison definition commands and deterministic eligibility evaluation."""

from __future__ import annotations

from uuid import UUID
from typing import Literal

from ..comparison_contracts import (
    ComparisonEvaluation, ComparisonRunEligibility, ComparisonViewDefinition,
    ComparisonViewDetail, ComparisonViewsResponse, ComparisonViewUpdate,
)
from ..contracts import PageInfo
from ..repositories.comparison_views import (
    ComparisonCandidate, ComparisonRevisionConflict, ComparisonViewRepository,
)
from ..repositories.comparison_schema import (
    ComparisonStorageUnavailable,
)
from ..repositories.database import ConsoleDatabaseUnavailable


class ComparisonNotFound(ValueError):
    """The requested experiment or scoped saved view does not exist."""


class InvalidComparisonSelection(ValueError):
    """One or more selected IDs are absent from the selected experiment."""


ComparisonDatabaseUnavailable = ConsoleDatabaseUnavailable


def evaluate_selection(
    definition: ComparisonViewDefinition, candidates: dict[str, ComparisonCandidate],
) -> ComparisonEvaluation:
    """Preserve selected IDs while admitting only current matching scope evidence."""
    reference = candidates.get(definition.reference_run_id or "")
    runs: list[ComparisonRunEligibility] = []
    for run_id in definition.run_ids:
        candidate = candidates.get(run_id)
        reason = None
        if candidate is None:
            reason = "run_not_in_experiment"
        elif not candidate.scope_fingerprint:
            reason = "missing_scope_fingerprint"
        elif not candidate.projection_available:
            reason = "no_comparison_projection"
        elif reference is None:
            reason = "target_run_not_found"
        elif not reference.scope_fingerprint:
            reason = "target_missing_scope_fingerprint"
        elif candidate.scope_fingerprint != reference.scope_fingerprint:
            reason = "scope_mismatch"
        runs.append(ComparisonRunEligibility(
            run_id=run_id, eligible=reason is None, exclusion_reason=reason,
            scope_fingerprint=candidate.scope_fingerprint if candidate else None,
        ))
    eligible = tuple(run.run_id for run in runs if run.eligible)
    state: Literal["empty", "unavailable", "one_run", "ready"] = (
        "empty" if not runs else "unavailable" if not eligible else "one_run" if len(eligible) == 1 else "ready"
    )
    return ComparisonEvaluation(state=state, eligible_run_ids=eligible, runs=tuple(runs))


class ComparisonViewService:
    """Save intent atomically and evaluate eligibility afresh on preview/load."""

    def __init__(self, repository: ComparisonViewRepository) -> None:
        """Use the scope-bound repository supplied by application composition."""
        self._repository = repository

    async def preview(self, experiment_id: str, definition: ComparisonViewDefinition) -> ComparisonEvaluation:
        """Evaluate a draft with read-only SQL, even before storage is installed."""
        async with self._repository.session(experiment_id) as session:
            if not await session.experiment_exists():
                raise ComparisonNotFound("Experiment not found")
            return evaluate_selection(definition, await session.candidates(definition.run_ids))

    async def save(
        self, experiment_id: str, definition: ComparisonViewDefinition, *,
        view_id: UUID | None = None, expected_revision: int | None = None,
    ) -> ComparisonViewDetail:
        """Validate membership and save only intent in a single command transaction."""
        async with self._repository.session(experiment_id, write=True) as session:
            await session.require_storage()
            if view_id is not None:
                existing = await session.get(view_id)
                if existing is None:
                    raise ComparisonNotFound("Comparison view not found")
                if existing.revision != expected_revision:
                    raise ComparisonRevisionConflict("The definition changed; reload before saving")
            if not await session.experiment_exists():
                raise ComparisonNotFound("Experiment not found")
            candidates = await session.candidates(definition.run_ids)
            missing = [run_id for run_id in definition.run_ids if run_id not in candidates]
            if missing:
                raise InvalidComparisonSelection("Runs are not in this experiment: " + ", ".join(missing))
            evaluation = evaluate_selection(definition, candidates)
            view = await session.save(definition, view_id=view_id, expected_revision=expected_revision)
        return ComparisonViewDetail(view=view, evaluation=evaluation)

    async def replace(self, experiment_id: str, view_id: UUID, update: ComparisonViewUpdate) -> ComparisonViewDetail:
        """Strip transport revision metadata before persisting the definition."""
        definition = ComparisonViewDefinition.model_validate(update.model_dump(exclude={"expected_revision"}))
        return await self.save(experiment_id, definition, view_id=view_id, expected_revision=update.expected_revision)

    async def get(self, experiment_id: str, view_id: UUID) -> ComparisonViewDetail:
        """Retain a saved selection if its evidence disappears, returning exclusions."""
        async with self._repository.session(experiment_id) as session:
            await session.require_storage()
            view = await session.get(view_id)
            if view is None:
                raise ComparisonNotFound("Comparison view not found")
            evaluation = evaluate_selection(view.definition, await session.candidates(view.definition.run_ids))
        return ComparisonViewDetail(view=view, evaluation=evaluation)

    async def list(self, experiment_id: str, *, limit: int, offset: int) -> ComparisonViewsResponse:
        """List definitions in scope without querying evidence once per saved view."""
        async with self._repository.session(experiment_id) as session:
            await session.require_storage()
            rows, total = await session.list(limit, offset)
        return ComparisonViewsResponse(
            items=tuple(rows), page=PageInfo(limit=limit, offset=offset, total=total, has_more=offset + limit < total),
        )


__all__ = [
    "ComparisonDatabaseUnavailable",
    "ComparisonNotFound",
    "ComparisonRevisionConflict",
    "ComparisonStorageUnavailable",
    "ComparisonViewService",
    "InvalidComparisonSelection",
    "evaluate_selection",
]
