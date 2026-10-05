"""Deterministic contracts for saved market-data alternative comparison.

Subject: Pairwise compatibility and evidence projection for saved scopes.
Level: In-process application-service contract with a fake repository.
Collaborators: Typed saved scopes and producer evidence rows; no PostgreSQL or provider.
Guarantees: Scope identity, independent evidence, allowed source/window differences,
and explicit exclusions survive comparison without a preferred alternative.
Non-goals: Bar merging, provider selection, statistical inference, or browser rendering.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from trader_console_api.data_scope_comparison_contracts import DataScopeComparisonRequest
from trader_console_api.data_scope_contracts import (
    DataScopeEvidenceStatus,
    DataScopeSourcePolicy,
    SavedDataScope,
)
from trader_console_api.repositories.data_scope_comparisons import DataScopeComparisonCandidate
from trader_console_api.services.data_scope_comparisons import DataScopeComparisonService


_START = datetime(2026, 1, 1, tzinfo=UTC)


def _scope(
    *,
    source: str = "alpaca",
    timeframe: str = "1Min",
    start: datetime = _START,
    scope_id: UUID | None = None,
) -> SavedDataScope:
    """Build one immutable saved scope for the service fixture."""
    identifier = scope_id or uuid4()
    return SavedDataScope(
        saved_scope_id=identifier,
        scope_id="test-console",
        fingerprint=(str(identifier).replace("-", "") + "0" * 64)[:64],
        name=f"Scope {str(identifier)[:8]}",
        asset_class="stock",
        symbols=("AAPL",),
        universe=None,
        timeframe=timeframe,
        interval=timeframe,
        start=start,
        end=start + timedelta(hours=1),
        source_policy=DataScopeSourcePolicy(provider=source, source=source, allow_fallback=False),
        research_role="backtest_authoring",
        manifest_artifact_id=f"manifest-{identifier}",
        quality_artifact_id=f"quality-{identifier}",
        evidence_status=DataScopeEvidenceStatus.ACTIVE,
        evidence_reason=None,
        created_by="test",
        idempotency_key=f"key-{identifier}",
        created_at=start,
        updated_at=start,
    )


def _evidence(scope: SavedDataScope, *, total_bars: int = 10) -> dict[str, Any]:
    """Build a complete producer evidence projection for one scope."""
    return {
        "manifest_artifact_id": scope.manifest_artifact_id,
        "quality_artifact_id": scope.quality_artifact_id,
        "manifest_uri": f"research://manifest/{scope.saved_scope_id}",
        "quality_uri": f"research://quality/{scope.saved_scope_id}",
        "evidence_status": "complete",
        "evidence_reason": "Manifest and quality evidence match this scope.",
        "bar_type": "trade_bar",
        "provider": scope.source_policy.provider,
        "source_policy": scope.source_policy.source,
        "manifest_schema_version": "2026-01",
        "quality_schema_version": "2026-01",
        "manifest_created_at": scope.created_at,
        "manifest_updated_at": scope.updated_at,
        "quality_created_at": scope.created_at,
        "quality_updated_at": scope.updated_at,
        "manifest_source_hash": "manifest-hash",
        "quality_source_hash": "quality-hash",
        "manifest_payload": {"total_bars": total_bars},
        "quality_payload": {"complete": True},
        "coverage": {"total_bars": total_bars, "total_rows": total_bars},
        "findings": [],
        "warnings": [],
        "provenance_refs": [f"research://manifest/{scope.saved_scope_id}"],
    }


class _Session:
    """Fake comparison session with explicit candidate evidence."""

    def __init__(self, candidates: tuple[DataScopeComparisonCandidate, ...]) -> None:
        self._candidates = candidates

    async def require_storage(self) -> None:
        """Represent an installed saved-scope/read projection."""

    async def candidates(self, _scope_ids: tuple[UUID, ...]) -> tuple[DataScopeComparisonCandidate, ...]:
        """Return the fixture candidates in their caller-selected order."""
        return self._candidates


class _Repository:
    """Repository double exposing the production async-context contract."""

    def __init__(self, candidates: tuple[DataScopeComparisonCandidate, ...]) -> None:
        self._candidates = candidates

    @asynccontextmanager
    async def session(self):
        yield _Session(self._candidates)


def _service(*candidates: DataScopeComparisonCandidate) -> DataScopeComparisonService:
    return DataScopeComparisonService(_Repository(tuple(candidates)))


def _candidate(scope: SavedDataScope, *, evidence: bool = True) -> DataScopeComparisonCandidate:
    return DataScopeComparisonCandidate(scope=scope, evidence=_evidence(scope) if evidence else None)


def test_equal_source_and_window_remain_two_independent_eligible_alternatives() -> None:
    """Equal dimensions compare coverage without selecting a preferred scope."""
    first, second = _scope(), _scope()
    result = asyncio.run(
        _service(_candidate(first), _candidate(second, evidence=True)).compare(
            DataScopeComparisonRequest(saved_scope_ids=(first.saved_scope_id, second.saved_scope_id))
        )
    )

    assert result.state == "ready"
    assert result.comparable_pair_count == 1
    assert result.pairs[0].eligible is True
    assert "source" in result.pairs[0].equal_dimensions
    assert "window" in result.pairs[0].equal_dimensions
    assert {alternative.scope.saved_scope_id for alternative in result.alternatives} == {
        first.saved_scope_id,
        second.saved_scope_id,
    }
    assert result.pairs[0].differences["coverage"]["total_bars"]["delta"] == 0


@pytest.mark.parametrize(
    ("first_kwargs", "second_kwargs", "varied"),
    [
        ({"source": "alpaca"}, {"source": "polygon"}, "source"),
        ({"start": _START}, {"start": _START + timedelta(hours=1)}, "window"),
    ],
)
def test_allowed_source_or_window_alternatives_are_explicitly_different(
    first_kwargs: dict[str, Any], second_kwargs: dict[str, Any], varied: str
) -> None:
    """A declared source/window alternative is eligible and retains its difference."""
    first, second = _scope(**first_kwargs), _scope(**second_kwargs)
    result = asyncio.run(
        _service(_candidate(first), _candidate(second)).compare(
            DataScopeComparisonRequest(saved_scope_ids=(first.saved_scope_id, second.saved_scope_id))
        )
    )

    pair = result.pairs[0]
    assert pair.eligible is True
    assert varied in pair.varied_dimensions
    assert varied in pair.differences
    assert pair.exclusion_reasons == ()


def test_unrequested_source_difference_is_excluded_with_reason() -> None:
    """The caller must opt into source comparison before a difference is calculated."""
    first, second = _scope(source="alpaca"), _scope(source="polygon")
    result = asyncio.run(
        _service(_candidate(first), _candidate(second)).compare(
            DataScopeComparisonRequest(
                saved_scope_ids=(first.saved_scope_id, second.saved_scope_id),
                comparison_dimensions=("window",),
            )
        )
    )

    assert result.state == "unavailable"
    assert result.pairs[0].eligible is False
    assert result.pairs[0].exclusion_reasons == ("source_mismatch",)
    assert result.pairs[0].differences == {}


def test_missing_evidence_is_excluded_without_widening_the_scope() -> None:
    """An unavailable alternative remains visible and cannot become comparable."""
    first, second = _scope(), _scope()
    result = asyncio.run(
        _service(_candidate(first), _candidate(second, evidence=False)).compare(
            DataScopeComparisonRequest(saved_scope_ids=(first.saved_scope_id, second.saved_scope_id))
        )
    )

    assert result.state == "unavailable"
    assert result.alternatives[1].evidence.state == "unavailable"
    assert "right_evidence_unavailable" in result.pairs[0].exclusion_reasons
    assert result.alternatives[1].eligible is False


def test_missing_quality_artifact_is_excluded_even_when_scope_row_exists() -> None:
    """A malformed complete row cannot hide its absent quality artifact."""
    first, second = _scope(), _scope()
    missing_quality = _evidence(second)
    missing_quality["quality_artifact_id"] = None
    result = asyncio.run(
        _service(
            _candidate(first),
            DataScopeComparisonCandidate(scope=second, evidence=missing_quality),
        ).compare(
            DataScopeComparisonRequest(saved_scope_ids=(first.saved_scope_id, second.saved_scope_id))
        )
    )

    assert result.state == "unavailable"
    assert "right_quality_evidence_missing" in result.pairs[0].exclusion_reasons
    assert result.pairs[0].differences == {}


def test_incompatible_timeframe_is_excluded_before_any_difference() -> None:
    """A timeframe mismatch blocks comparison and produces no collapsed result."""
    first, second = _scope(timeframe="1Min"), _scope(timeframe="5Min")
    result = asyncio.run(
        _service(_candidate(first), _candidate(second)).compare(
            DataScopeComparisonRequest(saved_scope_ids=(first.saved_scope_id, second.saved_scope_id))
        )
    )

    assert result.state == "unavailable"
    assert result.pairs[0].eligible is False
    assert "timeframe_mismatch" in result.pairs[0].exclusion_reasons
    assert result.pairs[0].differences == {}
