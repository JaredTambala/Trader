"""Normalize shared inputs and enforce immutable specification invariants.

These helpers resolve canonical artifact references, validate Data evidence,
normalize numeric and portfolio values, and create embedded snapshots. They are
kept transport-neutral so strategy, risk, and backtest services fail consistently.
"""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result

from collections.abc import Mapping as MappingABC, Sequence as SequenceABC
from datetime import datetime
import math
from typing import Any, Mapping, Sequence

from trader_research.foundation.artifacts import (
    ResearchArtifactStore,
    load_artifact_ref,
)
from trader_research.foundation import json_payload_hash


def resolve_exactly_one(
    store: ResearchArtifactStore,
    artifact_type: str,
    *,
    artifact_id: str | None,
    artifact_uri: str | None,
    inline: Mapping[str, Any] | None,
    label: str,
) -> Mapping[str, Any]:
    """Resolve exactly one inline payload, artifact ID, or canonical URI.

    Inline mappings are copied to prevent caller mutation; stored references are
    loaded through the canonical artifact store using ``artifact_type``.

    Returns:
        A normalized mapping for the selected input form.

    Raises:
        ValueError: If zero or multiple input forms are supplied.
        ResearchArtifactStoreError: If a selected stored artifact cannot be read.
    """
    selected = [bool(artifact_id), bool(artifact_uri), inline is not None]
    if sum(selected) != 1:
        raise ValueError(f"exactly one {label} input is required")
    if inline is not None:
        return dict(inline)
    return load_artifact_ref(store, artifact_type, str(artifact_uri or artifact_id or ""))


def specification_error(command: str, code: str, message: str) -> ApplicationResult:
    """Build the standard failed result used by specification services.

    Operation, stable code, and actionable message are preserved without raising,
    logging, or performing any artifact mutation.
    """
    return error_result(command=command, code=code, message=message)


def mapping(value: Any, name: str) -> dict[str, Any]:
    """Copy a mapping while normalizing all keys to strings.

    ``name`` is included in the ``ValueError`` raised for non-mapping inputs so
    callers can identify the malformed request field.
    """
    if not isinstance(value, MappingABC):
        raise ValueError(f"{name} must be a mapping")
    return {str(key): item for key, item in value.items()}


def mappings(value: Any, name: str) -> tuple[Mapping[str, Any], ...]:
    """Normalize an optional sequence of mappings to an immutable tuple.

    ``None`` becomes empty, strings and bytes are rejected as sequences, and each
    item is copied through ``mapping`` with indexed field context.
    """
    if value is None:
        return ()
    if not isinstance(value, SequenceABC) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be an array")
    return tuple(mapping(item, f"{name} item") for item in value)


def normalized_dataset_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the Data Agent manifest required by canonical backtests.

    The manifest must name a dataset, ordered symbols, asset class, timeframe,
    timezone-aware window, positive row count, and complete coverage. Source-
    filtered manifests are rejected because canonical backtests require the full
    event-store scope described by the snapshot.

    Returns:
        A normalized manifest suitable for immutable snapshotting.

    Raises:
        ValueError: If identity, scope, window, row count, or completeness is
            invalid.
    """
    manifest = dict(payload)
    dataset_id = str(manifest.get("dataset_id") or "").strip()
    symbols = [str(item).strip().upper() for item in _sequence(manifest.get("symbols")) if str(item).strip()]
    asset_class = str(manifest.get("asset_class") or "").strip().lower()
    timeframe = str(manifest.get("timeframe") or "").strip()
    window = mapping(
        manifest.get("time_range") or manifest.get("requested_window") or manifest.get("window") or {},
        "dataset_manifest.time_range",
    )
    start = parse_datetime(window.get("start"), "dataset_manifest.time_range.start")
    end = parse_datetime(window.get("end"), "dataset_manifest.time_range.end")
    if not dataset_id or not symbols or not asset_class or not timeframe:
        raise ValueError("dataset_manifest requires dataset_id, symbols, asset_class, and timeframe")
    if start > end:
        raise ValueError("dataset_manifest start must be <= end")
    if manifest.get("complete") is not True:
        raise ValueError("dataset_manifest.complete must be true")
    total_rows = int(manifest.get("total_rows") or 0)
    if total_rows <= 0:
        raise ValueError("dataset_manifest.total_rows must be positive")
    if manifest.get("source_filter") not in {None, ""}:
        raise ValueError("dataset_manifest.source_filter is not supported by canonical backtests")
    return {
        **manifest,
        "dataset_id": dataset_id,
        "symbols": symbols,
        "asset_class": asset_class,
        "timeframe": timeframe,
        "time_range": {"start": start.isoformat(), "end": end.isoformat()},
        "total_rows": total_rows,
        "complete": True,
        "source_filter": None,
    }


def validate_quality_report(report: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate quality evidence against a normalized dataset manifest.

    The report must be complete. When it carries symbols, they must match the
    manifest order, and asset class, timeframe, start, and end must always match
    the manifest scope exactly.

    Returns:
        A copied quality-report payload after cross-evidence checks pass.

    Raises:
        ValueError: If the report is incomplete, malformed, or describes a
            different market-data scope.
    """
    payload = dict(report)
    if payload.get("complete") is not True:
        raise ValueError("data_quality_report.complete must be true")
    report_symbols = [str(item).strip().upper() for item in _sequence(payload.get("symbols")) if str(item).strip()]
    if report_symbols and report_symbols != list(manifest["symbols"]):
        raise ValueError("data_quality_report.symbols does not match dataset_manifest")
    for name in ("asset_class", "timeframe"):
        if str(payload.get(name) or "").strip().lower() != str(manifest.get(name) or "").strip().lower():
            raise ValueError(f"data_quality_report.{name} does not match dataset_manifest")
    window = mapping(
        payload.get("time_range") or payload.get("requested_window") or payload.get("window") or {},
        "data_quality_report.time_range",
    )
    if parse_datetime(window.get("start"), "data_quality_report.time_range.start").isoformat() != manifest["time_range"]["start"]:
        raise ValueError("data_quality_report start does not match dataset_manifest")
    if parse_datetime(window.get("end"), "data_quality_report.time_range.end").isoformat() != manifest["time_range"]["end"]:
        raise ValueError("data_quality_report end does not match dataset_manifest")
    return payload


def normalize_assumptions(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate numeric cost and latency values in execution assumptions.

    Maintained fee, slippage, and latency fields must be finite and non-negative.
    The original copied mapping, including additional assumption sections, is
    returned after validation.
    """
    assumptions = dict(payload or {})
    for section_name, fields in {"fees": ("fixed_per_order", "bps", "minimum_fee"), "slippage": ("bps",)}.items():
        section = assumptions.get(section_name)
        if section is None:
            continue
        section_payload = mapping(section, f"assumptions.{section_name}")
        for field in fields:
            if field in section_payload and number(section_payload[field], f"assumptions.{section_name}.{field}") < 0:
                raise ValueError(f"assumptions.{section_name}.{field} must be non-negative")
    if "latency_ms" in assumptions and number(assumptions["latency_ms"], "assumptions.latency_ms") < 0:
        raise ValueError("assumptions.latency_ms must be non-negative")
    return assumptions


def normalize_positions(values: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize explicit initial positions for a backtest specification.

    Symbols are uppercased, quantities must be finite, and optional average
    prices must be finite and non-negative. Input order and repeated symbols are
    preserved for downstream portfolio validation.

    Returns:
        JSON-compatible position rows with canonical symbols and numeric values.

    Raises:
        ValueError: If a position lacks a symbol or contains an invalid number.
    """
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(values or ()):
        row = mapping(item, f"initial_positions[{index}]")
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            raise ValueError(f"initial_positions[{index}].symbol is required")
        qty = number(row.get("qty"), f"initial_positions[{index}].qty")
        avg_price = row.get("avg_price")
        normalized_avg = number(avg_price, f"initial_positions[{index}].avg_price") if avg_price is not None else None
        if normalized_avg is not None and normalized_avg < 0:
            raise ValueError(f"initial_positions[{index}].avg_price must be non-negative")
        rows.append({"symbol": symbol, "qty": qty, "avg_price": normalized_avg})
    return rows


def artifact_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create an embedded payload snapshot with a canonical SHA-256 digest.

    The mapping is copied before hashing so specifications can later recompute and
    compare exact upstream evidence without another store lookup.
    """
    return {"payload": dict(payload), "sha256": json_payload_hash(payload)}


def parse_datetime(value: Any, name: str) -> datetime:
    """Parse a datetime boundary value and require timezone information.

    Existing datetime objects and ISO-8601 strings, including ``Z`` suffixes, are
    accepted. Failures include ``name`` for actionable specification errors.
    """
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include timezone information")
    return parsed


def number(value: Any, name: str) -> float:
    """Normalize one finite non-boolean numeric value to ``float``.

    Invalid types, infinities, and NaN raise ``ValueError`` containing ``name``;
    sign and domain-specific bounds remain the caller's responsibility.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite numeric")
    return float(value)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, SequenceABC) and not isinstance(value, (str, bytes)):
        return value
    return ()
