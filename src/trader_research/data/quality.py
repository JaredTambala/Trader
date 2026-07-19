"""Read-only market-data quality reporting."""

from __future__ import annotations

from typing import Any

from trader.event_store import EventStore
from trader.market_data.quality import summarize_bar_quality
from trader.market_data.queries import EventStoreConnectionUnavailable

from trader_research.foundation import ApplicationResult, error_result, success_result

from .catalog import (
    _merge_provider_context_fields,
    _provider_context_from_request,
    _provider_error_result,
)
from .domain import DATA_SUMMARIZE_QUALITY, DataProviderResolutionError, DataQualityRequest
from .inventory import _bar_query_from_fields


def data_summarize_quality(event_store: EventStore, request: DataQualityRequest) -> ApplicationResult:
    """Return a read-only Data Agent data-quality result.

    Args:
        event_store: Event store that exposes a read-only database connection.
        request: Bounded quality request.

    Returns:
        Data Agent tool result with an embedded data-quality report.
    """
    try:
        provider_context = _provider_context_from_request(request)
        query = _bar_query_from_fields(
            symbols=request.symbols,
            asset_class=provider_context.legacy_asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
        )
        report, warnings = summarize_bar_quality(event_store, query)
        report["provider_context"] = provider_context.to_dict()
        _merge_provider_context_fields(report, provider_context)
    except DataProviderResolutionError as exc:
        return _provider_error_result(
            command=DATA_SUMMARIZE_QUALITY,
            error=exc,
        )
    except EventStoreConnectionUnavailable as exc:
        return error_result(
            command=DATA_SUMMARIZE_QUALITY,
            code="event_store_connection_unavailable",
            message=str(exc),
            data={"request": _raw_quality_request_payload(request)},
        )
    except ValueError as exc:
        return error_result(
            command=DATA_SUMMARIZE_QUALITY,
            code="validation_error",
            message=str(exc),
        )

    return success_result(
        command=DATA_SUMMARIZE_QUALITY,
        data={"data_quality_report": report},
        warnings=warnings,
    )


def _raw_quality_request_payload(request: DataQualityRequest) -> dict[str, Any]:
    """Build error context for an unnormalized quality request.

    Args:
        request: Raw quality request.

    Returns:
        JSON-compatible request payload.
    """
    return {
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "timeframe": request.timeframe,
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "source": request.source,
        "provider": request.provider,
        "instrument_type": request.instrument_type,
        "bar_type": request.bar_type,
        "configured_provider": request.configured_provider,
        "configured_asset_class": request.configured_asset_class,
    }
