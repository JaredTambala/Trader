"""Application services for the Console's data resources."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..contracts import (
    BarPoint,
    BarsResponse,
    ExperimentRunSummary,
    ExperimentRunsResponse,
    ExperimentSummary,
    ExperimentsResponse,
    IndicatorSeriesPoint,
    MarketDataset,
    MarketDatasetsResponse,
    PageInfo,
    ResourceRecord,
    RiskCompositionEntry,
    RiskDecision,
    RiskDecisionsResponse,
    RiskSummary,
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


class ResourceService:
    """Normalize repository rows into stable public response contracts."""

    def __init__(self, repository: ConsoleResourceRepository) -> None:
        """Bind public resource operations to their persistence adapter."""
        self._repository = repository

    async def market_datasets(self, *, limit: int, offset: int) -> MarketDatasetsResponse:
        rows, total = await self._repository.list_market_datasets(limit=limit, offset=offset)
        return MarketDatasetsResponse(
            items=tuple(MarketDataset.model_validate(row) for row in rows),
            page=_page(limit=limit, offset=offset, total=total),
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
            signals=tuple(row.get("signals", ())),
            orders=tuple(row.get("orders", ())),
            fills=tuple(row.get("fills", ())),
        )


def _record(row: dict[str, Any] | None) -> ResourceRecord | None:
    return ResourceRecord.model_validate(row) if row else None


def _risk_composition_entry(row: dict[str, Any]) -> RiskCompositionEntry:
    """Map the producer projection's manager-parameter column to the public field."""
    data = dict(row)
    data["parameters"] = data.pop("manager_parameters", {})
    return RiskCompositionEntry.model_validate(data)


def _records(rows: Iterable[dict[str, Any]]) -> tuple[ResourceRecord, ...]:
    return tuple(ResourceRecord.model_validate(row) for row in rows)
