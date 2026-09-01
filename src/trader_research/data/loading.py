"""Coordinate policy-gated inspection and loading of market data.

The service distinguishes read-only evidence gathering from provider-backed
loading, enforces the configured mutation policy before writes, and returns
structured blockers when the requested operation is unavailable or forbidden.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import ceil
from typing import Any

from trader.config import build_config, load_yaml_config
from trader.event_store import EventStore
from trader.market_data.backfill import BackfillSpec, MarketDataBackfillRunner
from trader.market_data.sample import load_sample_market_data_csv
from trader.timeframes import parse_timeframe

from trader_research.foundation import (
    ApplicationResult,
    DATA_DOMAIN_OWNER,
    ResearchArtifactNotFound,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    error_result,
    json_payload_hash,
    stable_research_id,
    success_result,
)
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


_DATA_LOAD_OPERATION_ARTIFACT_TYPE = "data_load_operation"
_DATA_LOAD_EVIDENCE_ARTIFACT_TYPE = "data_load_evidence"


def data_ensure_loaded(
    event_store: EventStore,
    request: DataEnsureLoadedRequest,
    *,
    policy: DataEnsureLoadedPolicy | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Inspect or explicitly load bounded market data for the Data Agent.

    Args:
        event_store: Event store used for inspection and allowed local writes.
        request: Bounded ensure-loaded request.
        policy: Runtime policy controlling local mutation.
        artifact_store: Canonical store used to journal mutating operations.

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
        acquisition_plan_id=request.acquisition_plan_id,
        operation_id=request.operation_id,
        requested_by=request.requested_by,
        actor=request.actor,
    )

    if mode == "sample" and not runtime_policy.allow_data_loading:
        return _ensure_error("data_loading_not_allowed", "Sample data loading is not allowed by policy.")
    if mode == "backfill" and not request.dry_run and not runtime_policy.allow_data_loading:
        return _ensure_error("data_loading_not_allowed", "Non-dry-run backfill is not allowed by policy.")

    mutating = mode == "sample" or (mode == "backfill" and not request.dry_run)
    if mutating:
        operation_error = _validate_load_operation_context(
            normalized_request,
            artifact_store,
        )
        if operation_error is not None:
            return operation_error
        assert artifact_store is not None
        replay = _load_terminal_operation(
            normalized_request,
            artifact_store,
        )
        if replay is not None:
            return replay

    inspection = _inspect_data(event_store, normalized_request)
    if inspection.get("error") is not None:
        return inspection["error"]

    if mutating:
        assert artifact_store is not None
        prepared = _prepare_load_operation(
            normalized_request,
            inspection=inspection,
            artifact_store=artifact_store,
            policy=runtime_policy,
        )
        if isinstance(prepared, ApplicationResult):
            return prepared

    try:
        if mode == "existing":
            return _ensure_existing(normalized_request, inspection)
        if mode == "sample":
            result = _ensure_sample(
                event_store,
                normalized_request,
                runtime_policy,
                inspection,
            )
        else:
            result = _ensure_backfill(
                event_store,
                normalized_request,
                runtime_policy,
                inspection,
            )
    except ValueError as exc:
        return _ensure_error("data_loading_failed", str(exc))
    if not mutating:
        return result
    assert artifact_store is not None
    return _persist_terminal_operation(
        normalized_request,
        result=result,
        artifact_store=artifact_store,
    )


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


def _validate_load_operation_context(
    request: DataEnsureLoadedRequest,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult | None:
    """Validate canonical lineage required before a Data mutation."""
    missing = []
    if not str(request.operation_id or "").strip():
        missing.append("operation_id")
    if not str(request.requested_by or "").strip():
        missing.append("requested_by")
    if not str(request.actor or "").strip():
        missing.append("actor")
    if missing:
        return _ensure_error(
            "data_load_lineage_required",
            "Mutating Data loading requires " + ", ".join(missing) + ".",
        )
    if artifact_store is None:
        return _ensure_error(
            "data_load_journal_required",
            "Mutating Data loading requires a canonical operation journal.",
        )
    return None


def _load_terminal_operation(
    request: DataEnsureLoadedRequest,
    artifact_store: ResearchArtifactStore,
) -> ApplicationResult | None:
    """Return a prior terminal mutation result without repeating the provider."""
    operation_id = str(request.operation_id)
    try:
        record = artifact_store.load_artifact_record(
            _DATA_LOAD_EVIDENCE_ARTIFACT_TYPE,
            operation_id,
        )
    except ResearchArtifactNotFound:
        return None
    except ResearchArtifactStoreError as exc:
        return _ensure_error("data_load_journal_failed", str(exc))
    payload = dict(record.payload)
    try:
        _validate_load_receipt_identity(payload, request)
        result_payload = payload.get("result")
        if not isinstance(result_payload, Mapping):
            raise ValueError("terminal Data load evidence has no result")
        result = _application_result_from_payload(result_payload)
    except ValueError as exc:
        return _ensure_error("data_load_journal_conflict", str(exc))
    return _with_load_evidence(
        result,
        reference=record.reference().to_dict(),
        idempotent_replay=True,
    )


def _prepare_load_operation(
    request: DataEnsureLoadedRequest,
    *,
    inspection: Mapping[str, Any],
    artifact_store: ResearchArtifactStore,
    policy: DataEnsureLoadedPolicy,
) -> ApplicationResult | None:
    """Persist a prepared mutation or recover it from complete post-load Data."""
    operation_id = str(request.operation_id)
    try:
        record = artifact_store.load_artifact_record(
            _DATA_LOAD_OPERATION_ARTIFACT_TYPE,
            operation_id,
        )
    except ResearchArtifactNotFound:
        plan = (
            _backfill_plan(request, policy)
            if request.mode == "backfill"
            else None
        )
        payload = {
            **_load_receipt_identity(request),
            "status": "prepared",
            "backfill_plan": plan,
            "pre_load_manifest": inspection["manifest"],
            "pre_load_quality_report": inspection["quality_report"],
        }
        try:
            artifact_store.save_artifact(
                artifact_type=_DATA_LOAD_OPERATION_ARTIFACT_TYPE,
                artifact_id=operation_id,
                domain_owner=DATA_DOMAIN_OWNER,
                producer_tool=DATA_ENSURE_LOADED,
                payload=payload,
                requested_by=request.requested_by,
                actor=request.actor,
                status="prepared",
                metadata={"mode": request.mode},
            )
        except ResearchArtifactStoreError as exc:
            return _ensure_error("data_load_journal_failed", str(exc))
        return None
    except ResearchArtifactStoreError as exc:
        return _ensure_error("data_load_journal_failed", str(exc))

    prepared = dict(record.payload)
    try:
        _validate_load_receipt_identity(prepared, request)
    except ValueError as exc:
        return _ensure_error("data_load_journal_conflict", str(exc))
    quality = inspection.get("quality_report")
    pre_load_quality = prepared.get("pre_load_quality_report")
    can_prove_completion = (
        isinstance(quality, Mapping)
        and quality.get("complete") is True
        and isinstance(pre_load_quality, Mapping)
        and pre_load_quality.get("complete") is False
    )
    if not can_prove_completion:
        return _ensure_error(
            "data_load_reconciliation_required",
            (
                "A prepared Data load has no terminal receipt and current "
                "evidence cannot prove that provider mutation completed; "
                "automatic provider replay is forbidden."
            ),
        )
    recovered = _recovered_load_result(
        request,
        prepared=prepared,
        inspection=inspection,
    )
    return _persist_terminal_operation(
        request,
        result=recovered,
        artifact_store=artifact_store,
    )


def _persist_terminal_operation(
    request: DataEnsureLoadedRequest,
    *,
    result: ApplicationResult,
    artifact_store: ResearchArtifactStore,
) -> ApplicationResult:
    """Persist one immutable terminal mutation result and attach its ref."""
    operation_id = str(request.operation_id)
    payload = {
        **_load_receipt_identity(request),
        "status": "accepted" if result.ok else "failed",
        "result": result.to_dict(),
    }
    try:
        record = artifact_store.save_artifact(
            artifact_type=_DATA_LOAD_EVIDENCE_ARTIFACT_TYPE,
            artifact_id=operation_id,
            domain_owner=DATA_DOMAIN_OWNER,
            producer_tool=DATA_ENSURE_LOADED,
            payload=payload,
            requested_by=request.requested_by,
            actor=request.actor,
            status=str(payload["status"]),
            metadata={"mode": request.mode},
        )
    except ResearchArtifactStoreError as exc:
        return _ensure_error(
            "data_load_evidence_persistence_failed",
            str(exc),
            data=result.data,
        )
    return _with_load_evidence(
        result,
        reference=record.reference().to_dict(),
        idempotent_replay=False,
    )


def _recovered_load_result(
    request: DataEnsureLoadedRequest,
    *,
    prepared: Mapping[str, Any],
    inspection: Mapping[str, Any],
) -> ApplicationResult:
    """Build terminal evidence when post-load state proves prepared work done."""
    load_result = {
        "mode": request.mode,
        "status": "recovered_after_interruption",
        "rows_loaded": 0,
        "dry_run": False,
        "operation_id": request.operation_id,
        "provider_context": _provider_context_from_request(request).to_dict(),
        "pre_load_manifest": prepared.get("pre_load_manifest"),
        "post_load_manifest": inspection["manifest"],
        "post_load_quality_report": inspection["quality_report"],
    }
    if request.mode == "backfill":
        load_result["backfill_plan"] = prepared.get("backfill_plan")
    return success_result(
        command=DATA_ENSURE_LOADED,
        data={"load_result": load_result},
        warnings=(
            "Recovered a prepared Data load from complete post-load evidence "
            "without repeating provider mutation.",
        ),
    )


def _load_receipt_identity(request: DataEnsureLoadedRequest) -> dict[str, Any]:
    """Return immutable request lineage shared by prepared and terminal rows."""
    identity = {
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "timeframe": request.timeframe,
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "mode": request.mode,
        "source": request.source,
        "provider": request.provider,
        "instrument_type": request.instrument_type,
        "bar_type": request.bar_type,
        "acquisition_plan_id": request.acquisition_plan_id,
    }
    return {
        "operation_id": request.operation_id,
        "request_hash": json_payload_hash(identity),
        "request": identity,
        "requested_by": request.requested_by,
        "actor": request.actor,
    }


def _validate_load_receipt_identity(
    payload: Mapping[str, Any],
    request: DataEnsureLoadedRequest,
) -> None:
    """Reject operation-ID reuse for another Data mutation request."""
    expected = _load_receipt_identity(request)
    for key in ("operation_id", "request_hash", "requested_by", "actor"):
        if payload.get(key) != expected[key]:
            raise ValueError(
                f"Data load operation {key} does not match the current request"
            )


def _application_result_from_payload(
    payload: Mapping[str, Any],
) -> ApplicationResult:
    """Normalize a persisted application result into its strict value object."""
    data = payload.get("data")
    artifacts = payload.get("artifacts")
    warnings = payload.get("warnings")
    errors = payload.get("errors")
    if not isinstance(data, Mapping) or not isinstance(artifacts, Mapping):
        raise ValueError("persisted Data load result has invalid mappings")
    if not isinstance(warnings, list) or not isinstance(errors, list):
        raise ValueError("persisted Data load result has invalid issues")
    if not all(isinstance(item, Mapping) for item in errors):
        raise ValueError("persisted Data load errors must be objects")
    return ApplicationResult(
        ok=payload.get("ok") is True,
        operation=str(payload.get("operation") or ""),
        data=dict(data),
        artifacts=dict(artifacts),
        warnings=tuple(str(item) for item in warnings),
        errors=tuple(dict(item) for item in errors),
        schema_version=str(payload.get("schema_version") or "1"),
    )


def _with_load_evidence(
    result: ApplicationResult,
    *,
    reference: Mapping[str, Any],
    idempotent_replay: bool,
) -> ApplicationResult:
    """Attach canonical mutation evidence and an explicit replay flag."""
    data = dict(result.data)
    load_result = data.get("load_result")
    if isinstance(load_result, Mapping):
        data["load_result"] = {
            **dict(load_result),
            "idempotent_replay": idempotent_replay,
        }
    return ApplicationResult(
        ok=result.ok,
        operation=result.operation,
        data=data,
        artifacts={**dict(result.artifacts), "data_load_evidence": dict(reference)},
        warnings=result.warnings,
        errors=result.errors,
        schema_version=result.schema_version,
    )


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
    if not request.operation_id:
        return _ensure_error(
            "data_operation_id_required",
            "Mutating sample loading requires a trusted operation_id.",
        )
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
        "operation_id": request.operation_id,
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
    plan = _backfill_plan(request, policy)
    if not request.dry_run and request.acquisition_plan_id != plan["plan_id"]:
        return _ensure_error(
            "acquisition_plan_mismatch",
            "Non-dry-run backfill requires the exact matching dry-run plan ID.",
            data={"load_result": {"mode": "backfill", "backfill_plan": plan}},
        )
    if not request.dry_run and not request.operation_id:
        return _ensure_error(
            "data_operation_id_required",
            "Non-dry-run backfill requires a trusted operation_id.",
            data={"load_result": {"mode": "backfill", "backfill_plan": plan}},
        )
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
                "operation_id": request.operation_id,
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


def _backfill_plan(
    request: DataEnsureLoadedRequest,
    policy: DataEnsureLoadedPolicy,
) -> dict[str, Any]:
    """Build a deterministic costed acquisition plan for one exact request."""
    timeframe = parse_timeframe(request.timeframe)
    seconds_by_unit = {
        "Min": 60,
        "Hour": 3_600,
        "Day": 86_400,
        "Week": 604_800,
        "Month": 2_592_000,
    }
    unit = str(timeframe.unit.value)
    try:
        step_seconds = int(timeframe.amount) * seconds_by_unit[unit]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported timeframe unit for acquisition estimate: {unit}"
        ) from exc
    duration_seconds = max(0.0, (request.end - request.start).total_seconds())
    bars_per_symbol = int(duration_seconds // step_seconds) + 1
    requests_per_symbol = max(
        1,
        ceil(bars_per_symbol / policy.backfill_request_bar_limit),
    )
    estimated_requests = requests_per_symbol * len(request.symbols)
    estimated_cost = round(
        estimated_requests * policy.backfill_cost_per_request,
        8,
    )
    request_identity = {
        "symbols": list(request.symbols),
        "asset_class": request.asset_class,
        "provider_context": _provider_context_from_request(request).to_dict(),
        "timeframe": request.timeframe,
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "source": request.source,
    }
    request_hash = json_payload_hash(request_identity)
    plan_identity = {
        "request_hash": request_hash,
        "estimated_requests": estimated_requests,
        "request_bar_limit": policy.backfill_request_bar_limit,
        "cost_per_request": policy.backfill_cost_per_request,
        "cost_currency": policy.loading_cost_currency,
    }
    return {
        "plan_id": stable_research_id("data_acquisition_plan", plan_identity),
        "request_hash": request_hash,
        **request_identity,
        "estimated_bars_per_symbol": bars_per_symbol,
        "estimated_network_calls": estimated_requests,
        "estimated_cost": estimated_cost,
        "cost_currency": policy.loading_cost_currency,
        "network_calls": 0 if request.dry_run else None,
        "writes": 0 if request.dry_run else None,
        "request_bar_limit": policy.backfill_request_bar_limit,
        "cost_per_request": policy.backfill_cost_per_request,
        "config_path": (
            str(policy.backfill_config_path)
            if policy.backfill_config_path
            else None
        ),
    }


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
