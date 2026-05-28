"""Data Agent services for market-data inventory."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from trader.config import build_config, load_yaml_config
from trader.data import EventStore
from trader.data_quality import summarize_bar_quality
from trader.market_data_backfill import BackfillSpec, MarketDataBackfillRunner
from trader.market_data_queries import (
    BarQuery,
    EventStoreConnectionUnavailable,
    count_bar_rows,
    count_bar_sources,
    fetch_bar_ranges,
    normalize_bar_query,
)
from trader.sample_data import load_sample_market_data_csv
from trader.timeframes import parse_timeframe

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope


DATA_GET_INVENTORY = "data_get_inventory"
DATA_SUMMARIZE_QUALITY = "data_summarize_quality"
DATA_ENSURE_LOADED = "data_ensure_loaded"
_SAMPLE_CSV = Path(__file__).resolve().parents[2] / "examples/data/demo_stock_1min.csv"
_ENSURE_MODES = {"existing", "sample", "backfill"}


BackfillRunner = Callable[["DataEnsureLoadedRequest", EventStore], Mapping[str, Any]]
"""Callable used by explicit non-dry-run backfill requests."""


@dataclass(frozen=True)
class DataInventoryRequest:
    """Request for read-only Data Agent inventory.

    Attributes:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp.
        end: Inclusive requested end timestamp.
        source: Optional source filter.
    """

    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    start: datetime
    end: datetime
    source: str | None = None


@dataclass(frozen=True)
class DataQualityRequest:
    """Request for read-only Data Agent quality summary.

    Attributes:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp.
        end: Inclusive requested end timestamp.
        source: Optional source filter.
    """

    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    start: datetime
    end: datetime
    source: str | None = None


@dataclass(frozen=True)
class DataEnsureLoadedRequest:
    """Request for explicit Data Agent data inspection or loading.

    Attributes:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp.
        end: Inclusive requested end timestamp.
        mode: Ensure mode: `existing`, `sample`, or `backfill`.
        source: Optional source filter.
        dry_run: Whether backfill mode should plan only.
    """

    symbols: tuple[str, ...]
    asset_class: str
    timeframe: str
    start: datetime
    end: datetime
    mode: str
    source: str | None = None
    dry_run: bool = True


@dataclass(frozen=True)
class DataEnsureLoadedPolicy:
    """Runtime policy for local data-loading behavior.

    Attributes:
        allow_data_loading: Whether local mutating sample/backfill behavior is allowed.
        sample_csv_path: Checked-in sample CSV path used by sample mode.
        backfill_config_path: Optional bounded config path for non-dry-run backfill.
        backfill_runner: Optional injected runner for non-dry-run backfill.
    """

    allow_data_loading: bool = False
    sample_csv_path: Path = _SAMPLE_CSV
    backfill_config_path: Path | None = None
    backfill_runner: BackfillRunner | None = None


def get_data_inventory(event_store: EventStore, request: DataInventoryRequest) -> ToolEnvelope:
    """Return a Data Agent inventory envelope for existing market data.

    Args:
        event_store: Event store that exposes a read-only database connection.
        request: Bounded inventory request.

    Returns:
        Data Agent tool envelope with an embedded dataset manifest.
    """
    try:
        query = _bar_query_from_request(request)
        manifest, warnings = _build_manifest(event_store, query)
    except EventStoreConnectionUnavailable as exc:
        return error_envelope(
            command=DATA_GET_INVENTORY,
            side_effect=SideEffect.READ_ONLY,
            code="event_store_connection_unavailable",
            message=str(exc),
            data={"request": _raw_request_payload(request)},
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_GET_INVENTORY,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=str(exc),
        )

    return success_envelope(
        command=DATA_GET_INVENTORY,
        side_effect=SideEffect.READ_ONLY,
        data={"dataset_manifest": manifest},
        warnings=warnings,
    )


def data_summarize_quality(event_store: EventStore, request: DataQualityRequest) -> ToolEnvelope:
    """Return a read-only Data Agent data-quality envelope.

    Args:
        event_store: Event store that exposes a read-only database connection.
        request: Bounded quality request.

    Returns:
        Data Agent tool envelope with an embedded data-quality report.
    """
    try:
        query = _bar_query_from_fields(
            symbols=request.symbols,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
        )
        report, warnings = summarize_bar_quality(event_store, query)
    except EventStoreConnectionUnavailable as exc:
        return error_envelope(
            command=DATA_SUMMARIZE_QUALITY,
            side_effect=SideEffect.READ_ONLY,
            code="event_store_connection_unavailable",
            message=str(exc),
            data={"request": _raw_quality_request_payload(request)},
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_SUMMARIZE_QUALITY,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=str(exc),
        )

    return success_envelope(
        command=DATA_SUMMARIZE_QUALITY,
        side_effect=SideEffect.READ_ONLY,
        data={"data_quality_report": report},
        warnings=warnings,
    )


def data_ensure_loaded(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    *,
    policy: DataEnsureLoadedPolicy | None = None,
) -> ToolEnvelope:
    """Inspect or explicitly load bounded market data for the Data Agent.

    Args:
        event_store: Event store used for inspection and allowed local writes.
        request: Bounded ensure-loaded request.
        policy: Runtime policy controlling local mutation.

    Returns:
        Data Agent tool envelope containing load evidence or structured errors.
    """
    runtime_policy = policy or DataEnsureLoadedPolicy()
    try:
        query = _bar_query_from_fields(
            symbols=request.symbols,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
        )
        mode = _normalize_ensure_mode(request.mode)
    except ValueError as exc:
        return error_envelope(
            command=DATA_ENSURE_LOADED,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="validation_error",
            message=str(exc),
        )
    normalized_request = DataEnsureLoadedRequest(
        symbols=query.symbols,
        asset_class=query.asset_class,
        timeframe=query.timeframe,
        start=query.start,
        end=query.end,
        mode=mode,
        source=query.source,
        dry_run=request.dry_run,
    )

    if mode == "sample" and not runtime_policy.allow_data_loading:
        return _ensure_error("data_loading_not_allowed", "Sample data loading is not allowed by policy.")
    if mode == "backfill" and not request.dry_run and not runtime_policy.allow_data_loading:
        return _ensure_error("data_loading_not_allowed", "Non-dry-run backfill is not allowed by policy.")

    inspection = _inspect_data(event_store, normalized_request)
    if inspection.get("error") is not None:
        return inspection["error"]

    try:
        if mode == "existing":
            return _ensure_existing(normalized_request, inspection)
        if mode == "sample":
            return _ensure_sample(event_store, normalized_request, runtime_policy, inspection)
        return _ensure_backfill(event_store, normalized_request, runtime_policy, inspection)
    except ValueError as exc:
        return _ensure_error("data_loading_failed", str(exc))


def _bar_query_from_request(request: DataInventoryRequest) -> BarQuery:
    """Convert a Data Agent inventory request into a normalized bar query.

    Args:
        request: Raw inventory request.

    Returns:
        Normalized core bar query.

    Raises:
        MarketDataQueryValidationError: If request fields are invalid.
    """
    return _bar_query_from_fields(
        symbols=request.symbols,
        asset_class=request.asset_class,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        source=request.source,
    )


def _bar_query_from_fields(
    *,
    symbols: tuple[str, ...],
    asset_class: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    source: str | None,
) -> BarQuery:
    """Convert request fields into a normalized bar query.

    Args:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp.
        end: Inclusive requested end timestamp.
        source: Optional source filter.

    Returns:
        Normalized core bar query.

    Raises:
        MarketDataQueryValidationError: If request fields are invalid.
    """
    return normalize_bar_query(
        BarQuery(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            source=source,
        )
    )


def _build_manifest(event_store: EventStore, query: BarQuery) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Build an embedded dataset manifest from typed market-data queries.

    Args:
        event_store: Event store to inspect.
        query: Normalized bar query.

    Returns:
        Tuple containing the manifest payload and non-fatal warnings.

    Raises:
        EventStoreConnectionUnavailable: If no queryable connection is available.
        MarketDataQueryValidationError: If the query is invalid.
    """
    counts = {item.symbol: item.row_count for item in count_bar_rows(event_store, query)}
    ranges = {item.symbol: item for item in fetch_bar_ranges(event_store, query)}
    source_counts = _source_counts_by_symbol(event_store, query)

    symbol_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_rows = 0
    for symbol in query.symbols:
        row_count = counts.get(symbol, 0)
        coverage = ranges[symbol]
        total_rows += row_count
        symbol_rows.append(
            {
                "symbol": symbol,
                "row_count": row_count,
                "first_ts": coverage.first_ts,
                "last_ts": coverage.last_ts,
                "sources": source_counts.get(symbol, {}),
            }
        )
        warnings.extend(_symbol_warnings(symbol, row_count, coverage.first_ts, coverage.last_ts, query))

    manifest = {
        "dataset_id": _dataset_id(query),
        "asset_class": query.asset_class,
        "symbols": list(query.symbols),
        "timeframe": query.timeframe,
        "requested_window": {
            "start": query.start,
            "end": query.end,
        },
        "source_filter": query.source,
        "total_rows": total_rows,
        "complete": not warnings,
        "symbols_detail": symbol_rows,
    }
    return manifest, tuple(warnings)


def _source_counts_by_symbol(event_store: EventStore, query: BarQuery) -> dict[str, dict[str, int]]:
    """Return source counts grouped by symbol.

    Args:
        event_store: Event store to inspect.
        query: Normalized bar query.

    Returns:
        Mapping from symbol to source-count mapping.

    Raises:
        EventStoreConnectionUnavailable: If no queryable connection is available.
        MarketDataQueryValidationError: If the query is invalid.
    """
    grouped: dict[str, dict[str, int]] = {}
    for item in count_bar_sources(event_store, query):
        grouped.setdefault(item.symbol, {})[item.source] = item.row_count
    return grouped


def _symbol_warnings(
    symbol: str,
    row_count: int,
    first_ts: datetime | None,
    last_ts: datetime | None,
    query: BarQuery,
) -> list[str]:
    """Build non-fatal coverage warnings for one symbol.

    Args:
        symbol: Canonical symbol inspected.
        row_count: Number of rows found.
        first_ts: First bar timestamp found, if any.
        last_ts: Last bar timestamp found, if any.
        query: Normalized bar query.

    Returns:
        List of warning messages.
    """
    if row_count == 0:
        return [f"No bars found for {symbol}."]
    warnings: list[str] = []
    if first_ts is not None and first_ts > query.start:
        warnings.append(f"First bar for {symbol} is after requested start.")
    if last_ts is not None and last_ts < query.end:
        warnings.append(f"Last bar for {symbol} is before requested end.")
    return warnings


def _dataset_id(query: BarQuery) -> str:
    """Build a stable dataset identifier for a normalized query.

    Args:
        query: Normalized bar query.

    Returns:
        Stable dataset identifier.
    """
    payload = _query_payload(query)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"dataset_{digest}"


def _query_payload(query: BarQuery) -> dict[str, Any]:
    """Build the stable query payload used for hashing.

    Args:
        query: Normalized bar query.

    Returns:
        JSON-compatible query payload.
    """
    return {
        "symbols": list(query.symbols),
        "asset_class": query.asset_class,
        "timeframe": query.timeframe,
        "start": query.start.isoformat(),
        "end": query.end.isoformat(),
        "source": query.source,
    }


def _raw_request_payload(request: DataInventoryRequest) -> dict[str, Any]:
    """Build error context for an unnormalized request.

    Args:
        request: Raw inventory request.

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
    }


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
    }


def _normalize_ensure_mode(mode: str) -> str:
    """Normalize and validate an ensure-loaded mode.

    Args:
        mode: Requested mode.

    Returns:
        Normalized mode.

    Raises:
        ValueError: If the mode is unsupported.
    """
    normalized = str(mode).strip().lower()
    if normalized not in _ENSURE_MODES:
        raise ValueError(f"Unsupported data ensure mode: {mode}")
    return normalized


def _inspect_data(event_store: EventStore, request: DataEnsureLoadedRequest) -> dict[str, Any]:
    """Inspect current inventory and quality for ensure-loaded workflows.

    Args:
        event_store: Event store to inspect.
        request: Ensure-loaded request.

    Returns:
        Mapping containing manifest, quality report, warnings, or an error envelope.
    """
    inventory_envelope = get_data_inventory(
        event_store,
        DataInventoryRequest(
            symbols=request.symbols,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
        ),
    )
    if not inventory_envelope.ok:
        return {"error": _retarget_error(inventory_envelope)}

    quality_envelope = data_summarize_quality(
        event_store,
        DataQualityRequest(
            symbols=request.symbols,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
        ),
    )
    if not quality_envelope.ok:
        return {"error": _retarget_error(quality_envelope)}

    inventory_data = inventory_envelope.to_dict()["data"]
    quality_data = quality_envelope.to_dict()["data"]
    return {
        "manifest": inventory_data["dataset_manifest"],
        "quality_report": quality_data["data_quality_report"],
        "warnings": [*inventory_envelope.warnings, *quality_envelope.warnings],
    }


def _ensure_existing(request: DataEnsureLoadedRequest, inspection: Mapping[str, Any]) -> ToolEnvelope:
    """Build an ensure-loaded result for inspect-only existing mode.

    Args:
        request: Ensure-loaded request.
        inspection: Current data inspection payload.

    Returns:
        Successful or failed ensure-loaded envelope.
    """
    quality_report = dict(inspection["quality_report"])
    load_result = {
        "mode": "existing",
        "status": "already_loaded" if quality_report["complete"] else "data_missing",
        "rows_loaded": 0,
        "dry_run": True,
        "post_load_manifest": inspection["manifest"],
        "post_load_quality_report": quality_report,
    }
    if not quality_report["complete"]:
        return _ensure_error(
            "data_missing",
            "Requested data is incomplete in existing mode.",
            data={"load_result": load_result},
        )
    return success_envelope(
        command=DATA_ENSURE_LOADED,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"load_result": load_result},
        warnings=tuple(inspection.get("warnings", ())),
    )


def _ensure_sample(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    policy: DataEnsureLoadedPolicy,
    inspection: Mapping[str, Any],
) -> ToolEnvelope:
    """Load the checked-in sample CSV and inspect post-load coverage.

    Args:
        event_store: Event store that receives sample rows.
        request: Ensure-loaded request.
        policy: Runtime loading policy.
        inspection: Pre-load inspection payload.

    Returns:
        Ensure-loaded envelope with sample-load evidence.
    """
    rows_loaded = load_sample_market_data_csv(event_store, policy.sample_csv_path)
    post_load = _inspect_data(event_store, request)
    if post_load.get("error") is not None:
        return post_load["error"]
    quality_report = dict(post_load["quality_report"])
    load_result = {
        "mode": "sample",
        "status": "loaded" if quality_report["complete"] else "loaded_incomplete",
        "rows_loaded": rows_loaded,
        "dry_run": False,
        "sample_csv_path": str(policy.sample_csv_path),
        "pre_load_manifest": inspection["manifest"],
        "post_load_manifest": post_load["manifest"],
        "post_load_quality_report": quality_report,
    }
    if not quality_report["complete"]:
        return _ensure_error(
            "data_missing",
            "Sample data was loaded but the requested data is still incomplete.",
            data={"load_result": load_result},
        )
    return success_envelope(
        command=DATA_ENSURE_LOADED,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"load_result": load_result},
        warnings=tuple(post_load.get("warnings", ())),
    )


def _ensure_backfill(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    policy: DataEnsureLoadedPolicy,
    inspection: Mapping[str, Any],
) -> ToolEnvelope:
    """Plan or run bounded backfill behavior.

    Args:
        event_store: Event store used for allowed local writes.
        request: Ensure-loaded request.
        policy: Runtime loading policy.
        inspection: Pre-backfill inspection payload.

    Returns:
        Ensure-loaded envelope with a dry-run plan or backfill run evidence.
    """
    plan = {
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "timeframe": request.timeframe,
        "start": request.start,
        "end": request.end,
        "source": request.source,
        "dry_run": request.dry_run,
        "network_calls": 0 if request.dry_run else None,
        "writes": 0 if request.dry_run else None,
        "config_path": str(policy.backfill_config_path) if policy.backfill_config_path else None,
    }
    if request.dry_run:
        return success_envelope(
            command=DATA_ENSURE_LOADED,
            side_effect=SideEffect.LOCAL_MUTATING,
            data={
                "load_result": {
                    "mode": "backfill",
                    "status": "planned",
                    "rows_loaded": 0,
                    "dry_run": True,
                    "backfill_plan": plan,
                    "pre_load_manifest": inspection["manifest"],
                    "pre_load_quality_report": inspection["quality_report"],
                }
            },
            warnings=tuple(inspection.get("warnings", ())),
        )
    if policy.backfill_runner is None and policy.backfill_config_path is None:
        return _ensure_error(
            "backfill_runner_required",
            "Non-dry-run backfill requires an injected runner or bounded config path.",
            data={"load_result": {"mode": "backfill", "status": "not_run", "backfill_plan": plan}},
        )
    try:
        runner_result = (
            dict(policy.backfill_runner(request, event_store))
            if policy.backfill_runner is not None
            else _run_configured_backfill(event_store, request, policy)
        )
    except Exception as exc:
        return _ensure_error(
            "backfill_failed",
            str(exc),
            data={"load_result": {"mode": "backfill", "status": "failed", "backfill_plan": plan}},
        )
    post_load = _inspect_data(event_store, request)
    if post_load.get("error") is not None:
        return post_load["error"]
    return success_envelope(
        command=DATA_ENSURE_LOADED,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={
            "load_result": {
                "mode": "backfill",
                "status": "ran",
                "rows_loaded": int(runner_result.get("rows_loaded", runner_result.get("rows_written", 0)) or 0),
                "dry_run": False,
                "backfill_plan": plan,
                "runner_result": runner_result,
                "pre_load_manifest": inspection["manifest"],
                "post_load_manifest": post_load["manifest"],
                "post_load_quality_report": post_load["quality_report"],
            }
        },
        warnings=tuple(post_load.get("warnings", ())),
    )


def _run_configured_backfill(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    policy: DataEnsureLoadedPolicy,
) -> dict[str, Any]:
    """Run platform backfill through the Data Agent tool boundary.

    Args:
        event_store: Event store used for allowed local writes.
        request: Normalized ensure-loaded request.
        policy: Runtime policy with a bounded trader config path.

    Returns:
        Backfill runner evidence.

    Raises:
        ValueError: If no bounded config path is supplied or the config is invalid.
    """
    if policy.backfill_config_path is None:
        raise ValueError("Non-dry-run backfill requires a bounded config path.")
    config_data = load_yaml_config(policy.backfill_config_path)
    config = build_config(config_data)
    service_cfg = config_data.get("trader_service", {})
    if service_cfg is None:
        service_cfg = {}
    if not isinstance(service_cfg, Mapping):
        raise ValueError("trader_service section must be a mapping")
    notify_channel = service_cfg.get("notify_channel")
    spec = BackfillSpec(
        start=request.start,
        end=request.end,
        timeframe=parse_timeframe(request.timeframe),
        limit=None,
    )
    runner = MarketDataBackfillRunner(
        config,
        spec,
        symbols=request.symbols,
        asset_class=request.asset_class,
        event_store=event_store,
        notify_channel=str(notify_channel) if notify_channel else None,
    )
    rows_written = runner.run()
    return {
        "runner": "MarketDataBackfillRunner",
        "config_path": str(policy.backfill_config_path),
        "rows_written": rows_written,
        "rows_loaded": rows_written,
        "source": "alpaca",
    }


def _retarget_error(envelope: ToolEnvelope) -> ToolEnvelope:
    """Return an ensure-loaded error from another Data Agent envelope.

    Args:
        envelope: Failed envelope from inventory or quality inspection.

    Returns:
        Failed ensure-loaded envelope preserving the first error code/message.
    """
    first_error = dict(envelope.errors[0]) if envelope.errors else {}
    return error_envelope(
        command=DATA_ENSURE_LOADED,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=str(first_error.get("code", "error")),
        message=str(first_error.get("message", "Data inspection failed.")),
        data=envelope.data,
    )


def _ensure_error(code: str, message: str, *, data: Mapping[str, Any] | None = None) -> ToolEnvelope:
    """Build a failed ensure-loaded envelope.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable error message.
        data: Optional error context.

    Returns:
        Failed Data Agent ensure-loaded envelope.
    """
    return error_envelope(
        command=DATA_ENSURE_LOADED,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
        data=data,
    )
