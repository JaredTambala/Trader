"""Create canonical Data evidence for resumable research workflows.

A snapshot binds one inventory manifest to quality evidence computed for the
same normalized request scope. The service persists both artifacts with Data
ownership so later workflow steps can revalidate exact inputs instead of
repeating discovery.
"""

from __future__ import annotations

from collections.abc import Mapping

from trader.event_store import EventStore

from trader_research.foundation import (
    ApplicationResult,
    DATA_DOMAIN_OWNER,
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    SCHEMA_VERSION,
    error_result,
    stable_research_id,
    success_result,
)

from .domain import DataInventoryRequest, DataQualityRequest
from .inventory import get_data_inventory
from .quality import data_summarize_quality


DATA_CREATE_RESEARCH_SNAPSHOT = "data_create_research_snapshot"
_DATASET_MANIFEST_ARTIFACT_TYPE = "dataset_manifest"
_DATA_QUALITY_REPORT_ARTIFACT_TYPE = "data_quality_report"


def create_data_research_snapshot(
    *,
    event_store: EventStore,
    inventory_request: DataInventoryRequest,
    quality_request: DataQualityRequest,
    requested_by: str,
    actor: str,
    artifact_store: ResearchArtifactStore | None,
) -> ApplicationResult:
    """Persist one exact inventory and quality pair as canonical Data evidence.

    The inventory and quality requests must describe the same normalized scope.
    The function runs both read-only services, verifies their dataset identity,
    and saves two content-derived artifacts whose identity and payload record
    ``requested_by`` and ``actor``. Neither artifact is written when an upstream
    service fails.

    Returns:
        A successful result containing both payloads and canonical references,
        or a structured failure for unavailable storage, mismatched evidence, or
        persistence errors. Upstream warnings are preserved.
    """
    if artifact_store is None:
        return error_result(
            command=DATA_CREATE_RESEARCH_SNAPSHOT,
            code="research_artifact_store_required",
            message="A ResearchArtifactStore is required.",
        )
    inventory = get_data_inventory(event_store, inventory_request)
    if not inventory.ok:
        return _upstream_error(inventory)
    quality = data_summarize_quality(event_store, quality_request)
    if not quality.ok:
        return _upstream_error(quality)
    manifest = dict(inventory.data["dataset_manifest"])
    report = dict(quality.data["data_quality_report"])
    try:
        requested_by = str(requested_by or "").strip()
        if not requested_by:
            raise ValueError("requested_by is required")
        actor = str(actor or "").strip()
        if not actor:
            raise ValueError("actor is required")
        _validate_matching_requests(inventory_request, quality_request)
        _validate_matching_snapshot(manifest, report)
        dataset_id = str(manifest["dataset_id"])
        manifest_id = stable_research_id(
            "dataset_manifest_snapshot",
            {
                "requested_by": requested_by,
                "actor": actor,
                "manifest": manifest,
            },
        )
        report_id = stable_research_id(
            "data_quality_snapshot",
            {
                "dataset_id": dataset_id,
                "requested_by": requested_by,
                "actor": actor,
                "manifest_artifact_id": manifest_id,
                "report": report,
            },
        )
        manifest_payload = {
            "artifact_type": _DATASET_MANIFEST_ARTIFACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            **manifest,
            "snapshot_request_id": requested_by,
            "snapshot_actor": actor,
            "status": "captured",
        }
        quality_payload = {
            "artifact_type": _DATA_QUALITY_REPORT_ARTIFACT_TYPE,
            "schema_version": SCHEMA_VERSION,
            **report,
            "dataset_id": dataset_id,
            "report_id": report_id,
            "snapshot_request_id": requested_by,
            "snapshot_actor": actor,
            "status": "captured",
        }
        manifest_record = artifact_store.save_artifact(
            artifact_type=_DATASET_MANIFEST_ARTIFACT_TYPE,
            artifact_id=manifest_id,
            domain_owner=DATA_DOMAIN_OWNER,
            producer_tool=DATA_CREATE_RESEARCH_SNAPSHOT,
            payload=manifest_payload,
            status="captured",
            metadata={
                "symbols": list(manifest.get("symbols") or ()),
                "timeframe": manifest.get("timeframe"),
            },
        )
        quality_record = artifact_store.save_artifact(
            artifact_type=_DATA_QUALITY_REPORT_ARTIFACT_TYPE,
            artifact_id=report_id,
            domain_owner=DATA_DOMAIN_OWNER,
            producer_tool=DATA_CREATE_RESEARCH_SNAPSHOT,
            payload=quality_payload,
            status="captured",
            metadata={
                "dataset_id": dataset_id,
                "dataset_manifest_artifact_id": manifest_id,
                "complete": bool(report.get("complete")),
            },
        )
    except (KeyError, ValueError, ResearchArtifactStoreError) as exc:
        return error_result(
            command=DATA_CREATE_RESEARCH_SNAPSHOT,
            code="data_research_snapshot_failed",
            message=str(exc),
        )
    return success_result(
        command=DATA_CREATE_RESEARCH_SNAPSHOT,
        data={
            "dataset_manifest": manifest_payload,
            "data_quality_report": quality_payload,
        },
        artifacts={
            "dataset_manifest": manifest_record.reference().to_dict(),
            "data_quality_report": quality_record.reference().to_dict(),
        },
        warnings=(*inventory.warnings, *quality.warnings),
    )


def _validate_matching_requests(
    inventory: DataInventoryRequest,
    quality: DataQualityRequest,
) -> None:
    fields = (
        "symbols",
        "asset_class",
        "timeframe",
        "start",
        "end",
        "source",
        "provider",
        "instrument_type",
        "bar_type",
    )
    for field in fields:
        if getattr(inventory, field) != getattr(quality, field):
            raise ValueError(
                f"inventory and quality requests differ for {field}"
            )


def _validate_matching_snapshot(
    manifest: dict[str, object],
    report: dict[str, object],
) -> None:
    for field in ("symbols", "asset_class", "timeframe"):
        if manifest.get(field) != report.get(field):
            raise ValueError(
                f"data quality report {field} does not match dataset manifest"
            )
    requested = _mapping(manifest.get("requested_window"))
    quality_window = _mapping(report.get("requested_window"))
    if requested.get("start") != quality_window.get("start"):
        raise ValueError(
            "data quality report start does not match dataset manifest"
        )
    if requested.get("end") != quality_window.get("end"):
        raise ValueError(
            "data quality report end does not match dataset manifest"
        )


def _upstream_error(result: ApplicationResult) -> ApplicationResult:
    error = result.errors[0] if result.errors else {}
    return error_result(
        command=DATA_CREATE_RESEARCH_SNAPSHOT,
        code=str(error.get("code") or "data_snapshot_upstream_failed"),
        message=str(error.get("message") or f"{result.operation} failed"),
        data=result.data,
    )


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}
