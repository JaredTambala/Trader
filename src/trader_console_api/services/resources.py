"""Application services for the Console's data resources."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal, cast

from ..contracts import (
    BarPoint,
    BarsResponse,
    DataEvidenceArtifact,
    DataEvidenceScope,
    ExperimentRunSummary,
    ExperimentRunsResponse,
    ExperimentSummary,
    ExperimentsResponse,
    IndicatorSeriesPoint,
    MarketDataset,
    MarketDataDiscovery,
    MarketDataEvidenceResponse,
    MarketDatasetsResponse,
    PageInfo,
    ResourceRecord,
    RiskCompositionEntry,
    RiskDecision,
    RiskDecisionsResponse,
    RiskSummary,
    ReviewEvidence,
    RunDetail,
    SignalMarker,
)
from ..repositories.resources import AssetClass, ConsoleResourceRepository
from ..repositories.database import ConsoleDatabaseUnavailable

ResourceDatabaseUnavailable = ConsoleDatabaseUnavailable


def _page(*, limit: int, offset: int, total: int) -> PageInfo:
    return PageInfo(limit=limit, offset=offset, total=total, has_more=offset + limit < total)


def _symbols(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value if item is not None)


def _run_summary(row: dict[str, Any]) -> ExperimentRunSummary:
    data = dict(row)
    data["symbols"] = _symbols(data.get("symbols"))
    data["comparison_eligible"] = bool(data.get("comparison_eligible", False))
    # Repository queries intentionally select the complete producer projection
    # (`runs.*`) so the detail route can reuse the same row. Keep the public
    # summary contract closed by dropping producer columns that are not part of
    # the summary response.
    fields = ExperimentRunSummary.model_fields
    return ExperimentRunSummary.model_validate(
        {name: value for name, value in data.items() if name in fields}
    )


ReviewEvidenceKind = Literal["evaluation", "multiple_testing", "adversarial"]
ReviewEvidenceStatus = Literal["available", "missing", "incompatible", "blocked"]
ReviewEvidenceOrigin = Literal["independent_review", "optimization", "diagnostic"]

_REVIEW_KINDS: dict[str, ReviewEvidenceKind] = {
    "evaluation_report": "evaluation",
    "parameter_optimization_evaluation_report": "evaluation",
    "multiple_testing_report": "multiple_testing",
    "robustness_report": "adversarial",
    "parameter_optimization_robustness_report": "adversarial",
}
_REVIEW_LABELS = {
    "evaluation": "Evaluation evidence",
    "multiple_testing": "Multiple-testing evidence",
    "adversarial": "Adversarial/robustness evidence",
}


def _string_tuple(value: Any) -> tuple[str, ...]:
    """Normalize producer arrays into safe human-readable reason text."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return (str(value),)
    return tuple(str(item) for item in value if item is not None)


def _review_evidence(rows: Iterable[dict[str, Any]]) -> tuple[ReviewEvidence, ...]:
    """Map producer artifacts to a complete, claim-scoped review projection."""
    by_kind: dict[ReviewEvidenceKind, ReviewEvidence] = {}
    for row in rows:
        artifact_type = str(row.get("artifact_type") or "")
        kind = _REVIEW_KINDS.get(artifact_type)
        if kind is None:
            continue
        blockers = _string_tuple(row.get("blockers"))
        limitations = _string_tuple(row.get("limitations"))
        artifact_status = str(row.get("artifact_status") or "")
        origin_value = str(row.get("origin_kind") or "")
        origin: ReviewEvidenceOrigin | None = cast(
            ReviewEvidenceOrigin | None,
            origin_value if origin_value in {"independent_review", "optimization", "diagnostic"} else None,
        )
        if artifact_status in {"blocked", "failed", "error"}:
            status: ReviewEvidenceStatus = "blocked"
            reason = blockers[0] if blockers else f"{_REVIEW_LABELS[kind]} is blocked"
        elif artifact_status not in {"passed", "completed", "complete"}:
            status = "incompatible"
            reason = f"{_REVIEW_LABELS[kind]} status is {artifact_status or 'unknown'}"
        else:
            status = "available"
            reason = "Producer artifact is available for the declared claim scope"
        independent = bool(row.get("independent_confirmation", False))
        if origin == "optimization":
            independent = False
            limitations = (*limitations, "Optimisation-derived evidence is not independent confirmation")
        by_kind[kind] = ReviewEvidence(
            evidence_kind=kind, artifact_type=artifact_type,
            artifact_id=str(row.get("artifact_id") or "") or None,
            status=status, reason=reason,
            domain_owner=str(row.get("domain_owner") or "") or None,
            producer_tool=str(row.get("producer_tool") or "") or None,
            schema_version=str(row.get("schema_version") or "") or None,
            source_hash=str(row.get("source_hash") or "") or None,
            claim_scope=dict(row.get("claim_scope") or {}) if isinstance(row.get("claim_scope"), dict) else {},
            data_roles=tuple(item if isinstance(item, (str, dict)) else str(item) for item in (row.get("data_roles") or ())),
            limitations=limitations,
            blockers=blockers,
            independent_confirmation=independent,
            origin_kind=origin,
        )
    missing_reasons: dict[ReviewEvidenceKind, str] = {
        "evaluation": "No Evaluation artifact is linked to this run",
        "multiple_testing": "No multiple-testing report is linked to this run",
        "adversarial": "No Adversarial/robustness artifact is linked to this run",
    }
    review_kinds: tuple[ReviewEvidenceKind, ...] = ("evaluation", "multiple_testing", "adversarial")
    return tuple(
        by_kind.get(kind)
        or ReviewEvidence(evidence_kind=kind, status="missing", reason=missing_reasons[kind])
        for kind in review_kinds
    )


class ResourceService:
    """Normalize repository rows into stable public response contracts."""

    def __init__(self, repository: ConsoleResourceRepository) -> None:
        """Bind public resource operations to their persistence adapter."""
        self._repository = repository

    async def market_datasets(self, *, limit: int, offset: int) -> MarketDatasetsResponse:
        rows, total = await self._repository.list_market_datasets(limit=limit, offset=offset)
        return MarketDatasetsResponse(
            items=tuple(_market_dataset(row) for row in rows),
            page=_page(limit=limit, offset=offset, total=total),
            discovery=_market_data_discovery(rows=rows, total=total),
        )

    async def market_data_evidence(
        self,
        *,
        asset_class: AssetClass,
        symbols: tuple[str, ...],
        timeframe: str,
        interval: str,
        bar_type: str,
        start: datetime,
        end: datetime,
        provider: str | None,
        source_policy: str | None,
    ) -> MarketDataEvidenceResponse:
        """Return Data-owned evidence for one exact bounded market-data scope."""
        scope = DataEvidenceScope(
            asset_class=asset_class,
            symbols=tuple(symbols),
            timeframe=timeframe,
            interval=interval,
            bar_type=bar_type,
            start=start,
            end=end,
            provider=provider,
            source_policy=source_policy,
        )
        row = await self._repository.get_market_data_evidence(
            asset_class=asset_class,
            symbols=scope.symbols,
            timeframe=scope.timeframe,
            interval=scope.interval,
            bar_type=scope.bar_type,
            start=scope.start,
            end=scope.end,
            provider=scope.provider,
            source_policy=scope.source_policy,
        )
        if row is None:
            return MarketDataEvidenceResponse(
                scope=scope,
                state="unavailable",
                evidence_reason="No matching Data manifest and quality evidence was published for this exact scope.",
                provider=provider,
                source_policy=source_policy,
                warnings=("Data evidence is unavailable for the selected exact scope.",),
            )
        manifest = _data_evidence_artifact(row, "manifest")
        quality = _data_evidence_artifact(row, "quality")
        return MarketDataEvidenceResponse(
            scope=scope,
            state=str(row.get("evidence_status") or "unavailable"),  # type: ignore[arg-type]
            evidence_reason=str(row.get("evidence_reason") or "Data evidence state was not published."),
            manifest=manifest,
            quality=quality,
            provider=row.get("provider") or provider,
            source_policy=row.get("source_policy") or source_policy,
            coverage=_json_mapping(row.get("coverage")),
            findings=_json_strings(row.get("findings")),
            warnings=_json_strings(row.get("warnings")),
            provenance=_json_strings(row.get("provenance_refs")),
        )

    async def bars(
        self,
        *,
        asset_class: AssetClass,
        symbol: str,
        timeframe: str,
        source: str | None,
        start: Any,
        end: Any,
        limit: int,
        offset: int,
    ) -> BarsResponse:
        rows, total = await self._repository.list_bars(
            asset_class=asset_class,
            symbol=symbol,
            timeframe=timeframe,
            source=source,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
        return BarsResponse(
            items=tuple(BarPoint.model_validate(row) for row in rows),
            page=_page(limit=limit, offset=offset, total=total),
        )

    async def experiments(self, *, limit: int, offset: int) -> ExperimentsResponse:
        rows, total = await self._repository.list_experiments(limit=limit, offset=offset)
        return ExperimentsResponse(
            items=tuple(
                ExperimentSummary(
                    experiment_id=str(row["experiment_id"]),
                    run_count=int(row["run_count"]),
                    latest_created_at=row.get("latest_created_at"),
                    statuses=tuple(str(status) for status in (row.get("statuses") or ())),
                )
                for row in rows
            ),
            page=_page(limit=limit, offset=offset, total=total),
        )

    async def experiment_runs(
        self,
        *,
        experiment_id: str,
        compatible_with_run_id: str | None,
        limit: int,
        offset: int,
    ) -> ExperimentRunsResponse:
        rows, total = await self._repository.list_experiment_runs(
            experiment_id=experiment_id,
            compatible_with_run_id=compatible_with_run_id,
            limit=limit,
            offset=offset,
        )
        return ExperimentRunsResponse(
            items=tuple(_run_summary(row) for row in rows),
            page=_page(limit=limit, offset=offset, total=total),
        )

    async def risk_decisions(
        self,
        *,
        run_id: str,
        manager_id: str | None,
        outcome: str | None,
        cycle_id: str | None,
        client_order_id: str | None,
        limit: int,
        offset: int,
    ) -> RiskDecisionsResponse | None:
        """Return a filtered, bounded risk trace for one published run."""
        result = await self._repository.list_risk_decisions(
            run_id=run_id,
            manager_id=manager_id,
            outcome=outcome,
            cycle_id=cycle_id,
            client_order_id=client_order_id,
            limit=limit,
            offset=offset,
        )
        if result is None:
            return None
        rows, total = result
        return RiskDecisionsResponse(
            items=tuple(RiskDecision.model_validate(row) for row in rows),
            page=_page(limit=limit, offset=offset, total=total),
        )

    async def run_detail(self, *, run_id: str, section_limit: int) -> RunDetail | None:
        row = await self._repository.get_run_detail(run_id=run_id, section_limit=section_limit)
        if row is None:
            return None
        return RunDetail(
            run=_run_summary(row["run"]),
            performance=_record(row.get("performance")),
            comparison_summary=_record(row.get("comparison_summary")),
            exposure=_record(row.get("exposure")),
            scope=_record(row.get("scope")),
            assumptions=_record(row.get("assumptions")),
            evidence_coverage=_record(row.get("evidence_coverage")),
            equity_curve=_records(row.get("equity_curve", ())),
            comparison_curves=_records(row.get("comparison_curves", ())),
            trades=_records(row.get("trades", ())),
            positions=_records(row.get("positions", ())),
            warnings=_records(row.get("warnings", ())),
            provenance=_records(row.get("provenance", ())),
            indicator_series=tuple(
                IndicatorSeriesPoint.model_validate(item)
                for item in row.get("indicator_series", ())
            ),
            signal_markers=tuple(
                SignalMarker.model_validate(item)
                for item in row.get("signal_markers", ())
            ),
            risk_composition=tuple(
                _risk_composition_entry(item)
                for item in row.get("risk_composition", ())
            ),
            risk_summary=(
                RiskSummary.model_validate(row["risk_summary"])
                if row.get("risk_summary") is not None
                else None
            ),
            risk_decisions=tuple(
                RiskDecision.model_validate(item)
                for item in row.get("risk_decisions", ())
            ),
            review_evidence=_review_evidence(row.get("review_evidence", ())),
            signals=tuple(row.get("signals", ())),
            orders=tuple(row.get("orders", ())),
            fills=tuple(row.get("fills", ())),
        )


def _record(row: dict[str, Any] | None) -> ResourceRecord | None:
    return ResourceRecord.model_validate(row) if row else None


def _market_dataset(row: dict[str, Any]) -> MarketDataset:
    """Drop optional capability columns before validating one dataset item."""
    fields = MarketDataset.model_fields
    return MarketDataset.model_validate(
        {name: value for name, value in row.items() if name in fields}
    )


def _data_evidence_artifact(row: dict[str, Any], prefix: str) -> DataEvidenceArtifact | None:
    """Map one producer artifact projection into the bounded public contract."""
    artifact_id = row.get(f"{prefix}_artifact_id")
    if artifact_id is None:
        return None
    created_at = row.get(f"{prefix}_created_at")
    updated_at = row.get(f"{prefix}_updated_at")
    if not isinstance(created_at, datetime) or not isinstance(updated_at, datetime):
        raise ValueError(f"{prefix} evidence is missing artifact timestamps")
    return DataEvidenceArtifact(
        artifact_id=str(artifact_id),
        uri=str(row.get(f"{prefix}_uri") or ""),
        status=row.get(f"{prefix}_status"),
        schema_version=str(row.get(f"{prefix}_schema_version") or ""),
        source_hash=row.get(f"{prefix}_source_hash"),
        created_at=created_at,
        updated_at=updated_at,
        payload=_json_mapping(row.get(f"{prefix}_payload")),
    )


def _json_mapping(value: Any) -> dict[str, Any]:
    """Normalize JSONB mapping values at the repository/service boundary."""
    return dict(value) if isinstance(value, dict) else {}


def _json_strings(value: Any) -> tuple[str, ...]:
    """Normalize JSONB arrays into stable public text findings/references."""
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if item is not None)


def _market_data_discovery(
    *,
    rows: Iterable[dict[str, Any]],
    total: int,
) -> MarketDataDiscovery:
    """Normalize optional producer capability metadata for the Console view.

    Existing ``console_read`` projections contain stored slices, not a complete
    provider catalogue. The fallback therefore reports ``partial`` and
    ``discover_only`` with an actionable reason. A future producer projection
    may provide the same typed fields per page; those values are preserved when
    present without making catalogue visibility imply load support.
    """
    items = list(rows)
    first = items[0] if items else {}
    completeness = str(first.get("catalogue_completeness", "partial" if total else "unavailable"))
    freshness = str(first.get("catalogue_freshness", "unknown"))
    can_discover = bool(first.get("can_discover", bool(total)))
    can_load = bool(first.get("can_load", False))
    load_capability = str(
        first.get(
            "load_capability",
            "load_capable" if can_load else ("discover_only" if can_discover else "unavailable"),
        )
    )
    provider = str(first.get("provider", "alpaca"))
    reason = first.get("capability_reason")
    if reason is None:
        reason = (
            "Visible rows prove stored coverage only; provider catalogue completeness and load capability require Data evidence."
            if total
            else "No stored dataset slices are available for this Console scope."
        )
    return MarketDataDiscovery(
        provider=provider,
        catalogue_completeness=completeness,  # type: ignore[arg-type]
        catalogue_freshness=freshness,  # type: ignore[arg-type]
        can_discover=can_discover,
        can_load=can_load,
        load_capability=load_capability,  # type: ignore[arg-type]
        reason=str(reason),
    )


def _risk_composition_entry(row: dict[str, Any]) -> RiskCompositionEntry:
    """Map the producer projection's manager-parameter column to the public field."""
    data = dict(row)
    data["parameters"] = data.pop("manager_parameters", {})
    return RiskCompositionEntry.model_validate(data)


def _records(rows: Iterable[dict[str, Any]]) -> tuple[ResourceRecord, ...]:
    return tuple(ResourceRecord.model_validate(row) for row in rows)
