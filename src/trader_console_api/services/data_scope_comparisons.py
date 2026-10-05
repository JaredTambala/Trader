"""Deterministic comparison of saved market-data scope alternatives."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from ..contracts import DataEvidenceScope, MarketDataEvidenceResponse
from ..data_scope_comparison_contracts import (
    DataComparisonDimension,
    DataScopeComparisonAlternative,
    DataScopeComparisonPair,
    DataScopeComparisonRequest,
    DataScopeComparisonResponse,
)
from ..repositories.data_scope_comparisons import (
    DataScopeComparisonCandidate,
    DataScopeComparisonNotFound,
    DataScopeComparisonRepository,
    DataScopeComparisonStorageUnavailable,
)
from ..repositories.database import ConsoleDatabaseUnavailable
from .resources import _data_evidence_artifact, _json_mapping, _json_strings

DataScopeComparisonDatabaseUnavailable = ConsoleDatabaseUnavailable

_REQUIRED_DIMENSIONS = (
    "asset_class",
    "symbols",
    "universe",
    "timeframe",
    "interval",
    "research_role",
)


def _scope_value(candidate: DataScopeComparisonCandidate, dimension: str) -> Any:
    """Return one stable scope dimension for compatibility checks."""
    scope = candidate.scope
    if dimension == "source":
        return scope.source_policy.model_dump(mode="json")
    if dimension == "window":
        return {"start": scope.start.isoformat(), "end": scope.end.isoformat()}
    value = getattr(scope, dimension)
    return list(value) if isinstance(value, tuple) else value


def _evidence_scope(candidate: DataScopeComparisonCandidate, row: dict[str, Any] | None) -> DataEvidenceScope:
    """Project a saved scope into the exact producer-evidence scope."""
    scope = candidate.scope
    return DataEvidenceScope(
        asset_class=scope.asset_class,
        symbols=scope.symbols,
        timeframe=scope.timeframe,
        interval=scope.interval,
        bar_type=str((row or {}).get("bar_type") or "trade_bar"),
        start=scope.start,
        end=scope.end,
        provider=scope.source_policy.provider,
        source_policy=scope.source_policy.source,
    )


def _evidence(candidate: DataScopeComparisonCandidate) -> MarketDataEvidenceResponse:
    """Map one producer row while preserving unavailable evidence explicitly."""
    row = candidate.evidence
    scope = _evidence_scope(candidate, row)
    if row is None:
        return MarketDataEvidenceResponse(
            scope=scope,
            state="unavailable",
            evidence_reason="No matching Data manifest and quality evidence was published for this saved scope.",
            provider=scope.provider,
            source_policy=scope.source_policy,
            warnings=("Data evidence is unavailable for this saved scope.",),
        )
    manifest = _data_evidence_artifact(row, "manifest")
    quality = _data_evidence_artifact(row, "quality")
    return MarketDataEvidenceResponse(
        scope=scope,
        state=str(row.get("evidence_status") or "unavailable"),  # type: ignore[arg-type]
        evidence_reason=str(row.get("evidence_reason") or "Data evidence state was not published."),
        manifest=manifest,
        quality=quality,
        provider=row.get("provider") or scope.provider,
        source_policy=row.get("source_policy") or scope.source_policy,
        coverage=_json_mapping(row.get("coverage")),
        findings=_json_strings(row.get("findings")),
        warnings=_json_strings(row.get("warnings")),
        provenance=_json_strings(row.get("provenance_refs")),
    )


def _json_value(value: Any) -> Any:
    """Convert typed values into JSON-safe comparison evidence."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _numeric_coverage_difference(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Report numeric coverage deltas without merging or inferring rows."""
    differences: dict[str, Any] = {}
    for key in sorted(set(left) & set(right)):
        left_value, right_value = left[key], right[key]
        if (
            isinstance(left_value, (int, float))
            and not isinstance(left_value, bool)
            and isinstance(right_value, (int, float))
            and not isinstance(right_value, bool)
        ):
            differences[key] = {
                "left": left_value,
                "right": right_value,
                "delta": right_value - left_value,
            }
    return differences


def _pair(
    left: DataScopeComparisonCandidate,
    right: DataScopeComparisonCandidate,
    left_evidence: MarketDataEvidenceResponse,
    right_evidence: MarketDataEvidenceResponse,
    comparison_dimensions: tuple[DataComparisonDimension, ...],
) -> DataScopeComparisonPair:
    """Compare a pair only after checking every non-comparison dimension."""
    dimensions = (*_REQUIRED_DIMENSIONS, "source", "window")
    equal = tuple(dimension for dimension in dimensions if _scope_value(left, dimension) == _scope_value(right, dimension))
    varied = tuple(dimension for dimension in dimensions if dimension not in equal)
    reasons: list[str] = []
    allowed = set(comparison_dimensions)
    for dimension in varied:
        if dimension not in allowed:
            reasons.append(f"{dimension}_mismatch")
    for side, evidence in (("left", left_evidence), ("right", right_evidence)):
        if evidence.state in {"unavailable", "empty", "stale"}:
            reasons.append(f"{side}_evidence_{evidence.state}")
        if evidence.manifest is None:
            reasons.append(f"{side}_manifest_evidence_missing")
        if evidence.quality is None:
            reasons.append(f"{side}_quality_evidence_missing")
    eligible = not reasons
    differences: dict[str, Any] = {}
    if eligible:
        if "source" in varied:
            differences["source"] = {
                "left": _json_value(_scope_value(left, "source")),
                "right": _json_value(_scope_value(right, "source")),
            }
        if "window" in varied:
            differences["window"] = {
                "left": _json_value(_scope_value(left, "window")),
                "right": _json_value(_scope_value(right, "window")),
            }
        differences["coverage"] = _numeric_coverage_difference(
            left_evidence.coverage, right_evidence.coverage
        )
        differences["quality"] = {
            "left_state": left_evidence.state,
            "right_state": right_evidence.state,
            "left_findings": list(left_evidence.findings),
            "right_findings": list(right_evidence.findings),
            "left_warnings": list(left_evidence.warnings),
            "right_warnings": list(right_evidence.warnings),
        }
        differences["provenance"] = {
            "left": list(left_evidence.provenance),
            "right": list(right_evidence.provenance),
        }
    return DataScopeComparisonPair(
        left_scope_id=left.scope.saved_scope_id,
        right_scope_id=right.scope.saved_scope_id,
        eligible=eligible,
        equal_dimensions=equal,
        varied_dimensions=varied,
        exclusion_reasons=tuple(reasons),
        differences=differences,
    )


def _pairs(
    candidates: tuple[DataScopeComparisonCandidate, ...],
    evidence: tuple[MarketDataEvidenceResponse, ...],
    dimensions: tuple[DataComparisonDimension, ...],
) -> tuple[DataScopeComparisonPair, ...]:
    """Build every unordered pair so no source becomes a hidden reference."""
    result: list[DataScopeComparisonPair] = []
    for index, left in enumerate(candidates):
        for right_index in range(index + 1, len(candidates)):
            result.append(
                _pair(left, candidates[right_index], evidence[index], evidence[right_index], dimensions)
            )
    return tuple(result)


class DataScopeComparisonService:
    """Evaluate saved alternatives with independent evidence and exclusions."""

    def __init__(self, repository: DataScopeComparisonRepository) -> None:
        """Bind comparisons to the repository composed for this Console scope."""
        self._repository = repository

    async def compare(self, request: DataScopeComparisonRequest) -> DataScopeComparisonResponse:
        """Compare selected scopes without choosing a provider or combining bars."""
        async with self._repository.session() as session:
            await session.require_storage()
            candidates = await session.candidates(request.saved_scope_ids)
        found = {candidate.scope.saved_scope_id: candidate for candidate in candidates}
        missing = [scope_id for scope_id in request.saved_scope_ids if scope_id not in found]
        if missing:
            raise DataScopeComparisonNotFound(
                "Saved data scopes not found: " + ", ".join(str(scope_id) for scope_id in missing)
            )
        ordered = tuple(found[scope_id] for scope_id in request.saved_scope_ids)
        evidence = tuple(_evidence(candidate) for candidate in ordered)
        pairs = _pairs(ordered, evidence, request.comparison_dimensions)
        reasons_by_scope: dict[UUID, set[str]] = {candidate.scope.saved_scope_id: set() for candidate in ordered}
        comparable_by_scope: dict[UUID, bool] = {candidate.scope.saved_scope_id: False for candidate in ordered}
        for pair in pairs:
            if pair.eligible:
                comparable_by_scope[pair.left_scope_id] = True
                comparable_by_scope[pair.right_scope_id] = True
            for reason in pair.exclusion_reasons:
                reasons_by_scope[pair.left_scope_id].add(reason)
                reasons_by_scope[pair.right_scope_id].add(reason)
        alternatives = tuple(
            DataScopeComparisonAlternative(
                scope=candidate.scope,
                evidence=item,
                eligible=comparable_by_scope[candidate.scope.saved_scope_id],
                exclusion_reasons=tuple(sorted(reasons_by_scope[candidate.scope.saved_scope_id])),
            )
            for candidate, item in zip(ordered, evidence, strict=True)
        )
        comparable_count = sum(1 for pair in pairs if pair.eligible)
        state: Literal["ready", "partial", "unavailable"] = (
            "ready" if comparable_count == len(pairs) else "partial" if comparable_count else "unavailable"
        )
        return DataScopeComparisonResponse(
            state=state,
            comparison_dimensions=request.comparison_dimensions,
            alternatives=alternatives,
            pairs=pairs,
            comparable_pair_count=comparable_count,
            excluded_pair_count=len(pairs) - comparable_count,
        )


__all__ = [
    "DataScopeComparisonDatabaseUnavailable",
    "DataScopeComparisonNotFound",
    "DataScopeComparisonService",
    "DataScopeComparisonStorageUnavailable",
]
