"""Policy-gated market-data inspection and loading orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from trader.config import build_config, load_yaml_config
from trader.event_store import EventStore
from trader.market_data.backfill import BackfillSpec, MarketDataBackfillRunner
from trader.market_data.sample import load_sample_market_data_csv
from trader.timeframes import parse_timeframe

from trader_research.foundation import ApplicationResult, error_result, success_result

from .catalog import _provider_context_from_request, _provider_error_result
from .domain import (
    DATA_ENSURE_LOADED,
    _ENSURE_MODES,
    DataEnsureLoadedPolicy,
    DataEnsureLoadedRequest,
    DataInventoryRequest,
    DataProviderResolutionError,
    DataQualityRequest,
)
from .inventory import _bar_query_from_fields, get_data_inventory
from .quality import data_summarize_quality


def data_ensure_loaded(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    *,
    policy: DataEnsureLoadedPolicy | None = None,
) -> ApplicationResult:
    """Inspect or explicitly load bounded market data for the Data Agent.

    Args:
        event_store: Event store used for inspection and allowed local writes.
        request: Bounded ensure-loaded request.
        policy: Runtime policy controlling local mutation.

    Returns:
        Data Agent tool result containing load evidence or structured errors.
    """
    runtime_policy = policy or DataEnsureLoadedPolicy()
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
        mode = _normalize_ensure_mode(request.mode)
    except DataProviderResolutionError as exc:
        return _provider_error_result(
            command=DATA_ENSURE_LOADED,
            error=exc,
        )
    except ValueError as exc:
        return error_result(
            command=DATA_ENSURE_LOADED,
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
        provider=provider_context.resolved_provider,
        instrument_type=provider_context.instrument_type,
        bar_type=provider_context.bar_type,
        configured_provider=provider_context.configured_provider,
        configured_asset_class=provider_context.legacy_asset_class,
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
        Mapping containing manifest, quality report, warnings, or an error result.
    """
    inventory_result = get_data_inventory(
        event_store,
        DataInventoryRequest(
            symbols=request.symbols,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
            provider=request.provider,
            instrument_type=request.instrument_type,
            bar_type=request.bar_type,
            configured_provider=request.configured_provider,
            configured_asset_class=request.configured_asset_class,
        ),
    )
    if not inventory_result.ok:
        return {"error": _retarget_error(inventory_result)}

    quality_result = data_summarize_quality(
        event_store,
        DataQualityRequest(
            symbols=request.symbols,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            source=request.source,
            provider=request.provider,
            instrument_type=request.instrument_type,
            bar_type=request.bar_type,
            configured_provider=request.configured_provider,
            configured_asset_class=request.configured_asset_class,
        ),
    )
    if not quality_result.ok:
        return {"error": _retarget_error(quality_result)}

    inventory_data = inventory_result.to_dict()["data"]
    quality_data = quality_result.to_dict()["data"]
    return {
        "manifest": inventory_data["dataset_manifest"],
        "quality_report": quality_data["data_quality_report"],
        "warnings": [*inventory_result.warnings, *quality_result.warnings],
    }


def _ensure_existing(request: DataEnsureLoadedRequest, inspection: Mapping[str, Any]) -> ApplicationResult:
    """Build an ensure-loaded result for inspect-only existing mode.

    Args:
        request: Ensure-loaded request.
        inspection: Current data inspection payload.

    Returns:
        Successful or failed ensure-loaded result.
    """
    quality_report = dict(inspection["quality_report"])
    load_result = {
        "mode": "existing",
        "status": "already_loaded" if quality_report["complete"] else "data_missing",
        "rows_loaded": 0,
        "dry_run": True,
        "provider_context": _provider_context_from_request(request).to_dict(),
        "post_load_manifest": inspection["manifest"],
        "post_load_quality_report": quality_report,
    }
    if not quality_report["complete"]:
        return _ensure_error(
            "data_missing",
            "Requested data is incomplete in existing mode.",
            data={"load_result": load_result},
        )
    return success_result(
        command=DATA_ENSURE_LOADED,
        data={"load_result": load_result},
        warnings=tuple(inspection.get("warnings", ())),
    )


def _ensure_sample(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    policy: DataEnsureLoadedPolicy,
    inspection: Mapping[str, Any],
) -> ApplicationResult:
    """Load the checked-in sample CSV and inspect post-load coverage.

    Args:
        event_store: Event store that receives sample rows.
        request: Ensure-loaded request.
        policy: Runtime loading policy.
        inspection: Pre-load inspection payload.

    Returns:
        Ensure-loaded result with sample-load evidence.
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
        "provider_context": _provider_context_from_request(request).to_dict(),
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
    return success_result(
        command=DATA_ENSURE_LOADED,
        data={"load_result": load_result},
        warnings=tuple(post_load.get("warnings", ())),
    )


def _ensure_backfill(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    policy: DataEnsureLoadedPolicy,
    inspection: Mapping[str, Any],
) -> ApplicationResult:
    """Plan or run bounded backfill behavior.

    Args:
        event_store: Event store used for allowed local writes.
        request: Ensure-loaded request.
        policy: Runtime loading policy.
        inspection: Pre-backfill inspection payload.

    Returns:
        Ensure-loaded result with a dry-run plan or backfill run evidence.
    """
    plan = {
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "provider_context": _provider_context_from_request(request).to_dict(),
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
        return success_result(
            command=DATA_ENSURE_LOADED,
            data={
                "load_result": {
                    "mode": "backfill",
                    "status": "planned",
                    "rows_loaded": 0,
                    "dry_run": True,
                    "provider_context": _provider_context_from_request(request).to_dict(),
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
            data={
                "load_result": {
                    "mode": "backfill",
                    "status": "not_run",
                    "provider_context": _provider_context_from_request(request).to_dict(),
                    "backfill_plan": plan,
                }
            },
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
            data={
                "load_result": {
                    "mode": "backfill",
                    "status": "failed",
                    "provider_context": _provider_context_from_request(request).to_dict(),
                    "backfill_plan": plan,
                }
            },
        )
    post_load = _inspect_data(event_store, request)
    if post_load.get("error") is not None:
        return post_load["error"]
    return success_result(
        command=DATA_ENSURE_LOADED,
        data={
            "load_result": {
                "mode": "backfill",
                "status": "ran",
                "rows_loaded": int(runner_result.get("rows_loaded", runner_result.get("rows_written", 0)) or 0),
                "dry_run": False,
                "provider_context": _provider_context_from_request(request).to_dict(),
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


def _retarget_error(result: ApplicationResult) -> ApplicationResult:
    """Return an ensure-loaded error from another Data Agent result.

    Args:
        result: Failed result from inventory or quality inspection.

    Returns:
        Failed ensure-loaded result preserving the first error code/message.
    """
    first_error = dict(result.errors[0]) if result.errors else {}
    return error_result(
        command=DATA_ENSURE_LOADED,
        code=str(first_error.get("code", "error")),
        message=str(first_error.get("message", "Data inspection failed.")),
        data=result.data,
    )


def _ensure_error(code: str, message: str, *, data: Mapping[str, Any] | None = None) -> ApplicationResult:
    """Build a failed ensure-loaded result.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable error message.
        data: Optional error context.

    Returns:
        Failed Data Agent ensure-loaded result.
    """
    return error_result(
        command=DATA_ENSURE_LOADED,
        code=code,
        message=message,
        data=data,
    )
