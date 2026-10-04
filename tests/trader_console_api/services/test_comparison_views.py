"""Subject: saved comparison definitions and live eligibility evaluation.

Level: Application-service unit tests.
Collaborators: In-memory repository/session doubles; Pydantic contracts.
Guarantees: Selection reasons are deterministic, writes validate membership, and
loads reevaluate current evidence without copying producer results.
Non-goals: PostgreSQL SQL syntax, FastAPI serialization, and UI rendering.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from trader_console_api.comparison_contracts import (
    ComparisonViewDefinition,
    ComparisonViewUpdate,
    SavedComparisonView,
)
from trader_console_api.repositories.comparison_views import ComparisonCandidate
from trader_console_api.services.comparison_views import (
    ComparisonViewService,
    InvalidComparisonSelection,
    evaluate_selection,
)


def _definition(*run_ids: str, reference: str | None = None) -> ComparisonViewDefinition:
    """Build a small valid definition for service cases."""
    selected = tuple(run_ids)
    return ComparisonViewDefinition(
        name="candidate view",
        run_ids=selected,
        reference_run_id=reference if reference is not None else (selected[0] if selected else None),
    )


def test_evaluation_preserves_selection_and_reports_current_exclusions() -> None:
    """Excluded selections remain visible with stable reason codes."""
    definition = _definition("run-a", "run-b", "run-c", reference="run-a")
    candidates = {
        "run-a": ComparisonCandidate("run-a", "scope-1", True),
        "run-b": ComparisonCandidate("run-b", None, True),
        "run-c": ComparisonCandidate("run-c", "scope-2", True),
    }

    result = evaluate_selection(definition, candidates)

    assert result.state == "one_run"
    assert result.eligible_run_ids == ("run-a",)
    assert [(item.run_id, item.exclusion_reason) for item in result.runs] == [
        ("run-a", None),
        ("run-b", "missing_scope_fingerprint"),
        ("run-c", "scope_mismatch"),
    ]


def test_evaluation_distinguishes_missing_projection_and_missing_run() -> None:
    """The evidence explanation identifies absent projection versus membership."""
    definition = _definition("run-a", "run-b", reference="run-a")
    candidates = {"run-a": ComparisonCandidate("run-a", "scope-1", True)}

    result = evaluate_selection(definition, candidates)

    assert result.runs[1].exclusion_reason == "run_not_in_experiment"
    assert result.state == "one_run"

    no_projection = evaluate_selection(
        definition,
        {
            "run-a": ComparisonCandidate("run-a", "scope-1", False),
            "run-b": ComparisonCandidate("run-b", "scope-1", True),
        },
    )
    assert [item.exclusion_reason for item in no_projection.runs] == [
        "no_comparison_projection",
        None,
    ]


class _Session:
    """Minimal session double that exposes mutable current candidates."""

    def __init__(self, candidates: dict[str, ComparisonCandidate]) -> None:
        self.candidate_rows = candidates
        self.saved: SavedComparisonView | None = None
        self.storage_required = False

    async def require_storage(self) -> None:
        """Record that a command or persisted read required installed storage."""
        self.storage_required = True

    async def experiment_exists(self) -> bool:
        """Expose one existing experiment to the service."""
        return True

    async def candidates(self, run_ids: tuple[str, ...]) -> dict[str, ComparisonCandidate]:
        """Return only current rows requested by the definition."""
        return {run_id: self.candidate_rows[run_id] for run_id in run_ids if run_id in self.candidate_rows}

    async def get(self, view_id: UUID) -> SavedComparisonView | None:
        """Return the saved definition when the requested identity matches."""
        return self.saved if self.saved and self.saved.view_id == view_id else None

    async def save(
        self,
        definition: ComparisonViewDefinition,
        *,
        view_id: UUID | None = None,
        expected_revision: int | None = None,
    ) -> SavedComparisonView:
        """Persist only the definition and server metadata in the test double."""
        now = datetime.now(UTC)
        self.saved = SavedComparisonView(
            view_id=view_id or uuid4(),
            scope_id="test-scope",
            experiment_id="experiment-1",
            definition=definition,
            revision=(self.saved.revision + 1 if self.saved else 1),
            created_at=self.saved.created_at if self.saved else now,
            updated_at=now,
        )
        return self.saved


class _Repository:
    """Repository double with one session reused across service calls."""

    def __init__(self, session: _Session) -> None:
        self.session_value = session

    @asynccontextmanager
    async def session(self, experiment_id: str, *, write: bool = False):
        """Yield the configured session without opening a database transaction."""
        yield self.session_value


def test_save_rejects_unknown_membership_without_persisting() -> None:
    """A run outside the experiment cannot be smuggled into a saved view."""
    session = _Session({"run-a": ComparisonCandidate("run-a", "scope-1", True)})
    service = ComparisonViewService(_Repository(session))

    async def exercise() -> None:
        with pytest.raises(InvalidComparisonSelection):
            await service.save("experiment-1", _definition("run-a", "run-missing", reference="run-a"))

    asyncio.run(exercise())

    assert session.saved is None


def test_get_rereads_current_candidates_and_retains_saved_intent() -> None:
    """Loading a saved view reflects changed evidence without rewriting its definition."""
    session = _Session({
        "run-a": ComparisonCandidate("run-a", "scope-1", True),
        "run-b": ComparisonCandidate("run-b", "scope-1", True),
    })
    service = ComparisonViewService(_Repository(session))
    async def exercise() -> tuple[SavedComparisonView, object]:
        created = await service.save("experiment-1", _definition("run-a", "run-b", reference="run-a"))
        session.candidate_rows["run-b"] = ComparisonCandidate("run-b", None, True)
        return created.view, await service.get("experiment-1", created.view.view_id)

    created, loaded = asyncio.run(exercise())

    assert created.definition.run_ids == ("run-a", "run-b")
    assert loaded.view.definition.run_ids == ("run-a", "run-b")
    assert loaded.evaluation.runs[1].exclusion_reason == "missing_scope_fingerprint"


def test_replace_requires_current_revision_metadata() -> None:
    """The service passes complete replacement definitions through revision guards."""
    session = _Session({"run-a": ComparisonCandidate("run-a", "scope-1", True)})
    service = ComparisonViewService(_Repository(session))
    async def exercise() -> tuple[SavedComparisonView, object]:
        created = await service.save("experiment-1", _definition("run-a"))
        updated = await service.replace(
            "experiment-1",
            created.view.view_id,
            ComparisonViewUpdate(
                name="renamed", run_ids=("run-a",), reference_run_id="run-a", expected_revision=1
            ),
        )
        return created.view, updated

    created, updated = asyncio.run(exercise())

    assert updated.view.definition.name == "renamed"
    assert updated.view.revision == 2
