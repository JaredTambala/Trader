"""Citation-backed Python method implementation manifests and fixtures."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import importlib.util
import inspect
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

from trader.indicators import Indicator
from trader.signals import Bar

from trader_research.contracts import ArtifactReference, SideEffect, ToolEnvelope, error_envelope, success_envelope, write_json_artifact
from trader_research.domain import stable_research_id
from trader_research.knowledge.method_cards import has_approved_method_card
from trader_research.knowledge.store import KnowledgeStore, KnowledgeStoreError
from trader_research.math_registry import get_method


MATH_REGISTER_METHOD_IMPLEMENTATION = "math_register_method_implementation"
MATH_RUN_INDICATOR_FIXTURES = "math_run_indicator_fixtures"
MATH_GENERATE_PYTHON_METHOD = "math_generate_python_method"

SCHEMA_VERSION = "1"
DEFAULT_ALLOWED_IMPORTS = (
    "__future__",
    "dataclasses",
    "math",
    "statistics",
    "trader.indicators",
    "trader.signals",
    "typing",
)
FORBIDDEN_CALLS = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
DEFAULT_ENTRYPOINTS = {
    "sma": "trader_standard.indicators:SmaIndicator",
    "ema": "trader_standard.indicators:EmaIndicator",
    "rsi": "trader_standard.indicators:RsiIndicator",
    "rolling_volatility": "trader_standard.indicators:RollingVolatilityIndicator",
    "z_score": "trader_standard.indicators:ZScoreIndicator",
    "bollinger_wma_band_rule": "trader_standard.indicators:BollingerBandsIndicator",
}


@dataclass(frozen=True)
class MethodImplementationManifest:
    """Manifest that links method evidence to a concrete Python Indicator implementation."""

    implementation_id: str
    method_id: str
    language: str
    implementation_kind: str
    entrypoint: str
    class_name: str
    source_path: str
    source_hash: str
    source_provenance: Mapping[str, Any]
    constructor_kwargs: Mapping[str, Any]
    method_card_ids: tuple[str, ...]
    method_contract: Mapping[str, Any]
    dependency_allowlist: tuple[str, ...] = DEFAULT_ALLOWED_IMPORTS
    safety_profile: Mapping[str, Any] = field(default_factory=lambda: {
        "no_network": True,
        "no_filesystem_mutation": True,
        "no_sql": True,
        "no_broker_access": True,
        "no_process_execution": True,
    })
    status: str = "registered"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "method_implementation_manifest",
            "schema_version": self.schema_version,
            "implementation_id": self.implementation_id,
            "method_id": self.method_id,
            "language": self.language,
            "implementation_kind": self.implementation_kind,
            "entrypoint": self.entrypoint,
            "class_name": self.class_name,
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "source_provenance": dict(self.source_provenance),
            "constructor_kwargs": dict(self.constructor_kwargs),
            "method_card_ids": list(self.method_card_ids),
            "method_contract": dict(self.method_contract),
            "dependency_allowlist": list(self.dependency_allowlist),
            "safety_profile": dict(self.safety_profile),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodImplementationManifest":
        return cls(
            implementation_id=str(payload.get("implementation_id") or ""),
            method_id=str(payload.get("method_id") or ""),
            language=str(payload.get("language") or "python"),
            implementation_kind=str(payload.get("implementation_kind") or "maintained"),
            entrypoint=str(payload.get("entrypoint") or ""),
            class_name=str(payload.get("class_name") or ""),
            source_path=str(payload.get("source_path") or ""),
            source_hash=str(payload.get("source_hash") or ""),
            source_provenance=_mapping(payload.get("source_provenance")),
            constructor_kwargs=_mapping(payload.get("constructor_kwargs")),
            method_card_ids=tuple(str(item) for item in _sequence(payload.get("method_card_ids"))),
            method_contract=_mapping(payload.get("method_contract")),
            dependency_allowlist=tuple(str(item) for item in _sequence(payload.get("dependency_allowlist"))) or DEFAULT_ALLOWED_IMPORTS,
            safety_profile=_mapping(payload.get("safety_profile")),
            status=str(payload.get("status") or "registered"),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
        )


def register_method_implementation(
    *,
    artifact_root: str | Path,
    method_id: str,
    method_card_ids: Sequence[str],
    method_contract: Mapping[str, Any] | None = None,
    entrypoint: str | None = None,
    source_path: str | Path | None = None,
    class_name: str | None = None,
    constructor_kwargs: Mapping[str, Any] | None = None,
    implementation_kind: str = "maintained",
    dependency_allowlist: Sequence[str] | None = None,
    expected_source_hash: str | None = None,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Register a Python Indicator implementation manifest after deterministic checks."""
    blockers: list[str] = []
    warnings: list[str] = []
    method_id = method_id.strip()
    entrypoint = (entrypoint or DEFAULT_ENTRYPOINTS.get(method_id) or "").strip()
    method_card_ids = tuple(str(item).strip() for item in method_card_ids if str(item).strip())
    method_contract = _method_contract(method_id, method_contract, method_card_ids, constructor_kwargs)
    constructor_kwargs = _constructor_kwargs(method_id, method_contract, constructor_kwargs)
    dependency_allowlist = tuple(dependency_allowlist or DEFAULT_ALLOWED_IMPORTS)

    try:
        entry = get_method(method_id, knowledge_store=knowledge_store)
    except KnowledgeStoreError as exc:
        return _error(MATH_REGISTER_METHOD_IMPLEMENTATION, "knowledge_store_error", str(exc))
    if entry is None:
        blockers.append(f"unsupported method_id: {method_id}")
    if implementation_kind not in {"maintained", "generated"}:
        blockers.append("implementation_kind must be maintained or generated")
    if not method_card_ids:
        blockers.append("approved method-card refs are required")
    else:
        try:
            if not has_approved_method_card(
                artifact_root,
                method_card_ids,
                knowledge_store=knowledge_store,
                method_id=method_id,
            ):
                blockers.append("approved method-card evidence does not match the requested method")
        except KnowledgeStoreError as exc:
            return _error(MATH_REGISTER_METHOD_IMPLEMENTATION, "knowledge_store_error", str(exc))

    source: Path | None
    source = Path(source_path).expanduser().resolve() if source_path is not None else _source_path_for_entrypoint(entrypoint)
    if source is None:
        blockers.append(f"could not resolve source path for entrypoint: {entrypoint}")
        source_hash = ""
        source_provenance: Mapping[str, Any] = {}
    elif source.exists() and source.is_file():
        source_hash = _file_sha256(source)
        safety_blockers = _static_safety_blockers(source, dependency_allowlist=dependency_allowlist)
        blockers.extend(safety_blockers)
        source_provenance, provenance_blockers = _source_provenance(
            source,
            method_id=method_id,
            method_card_ids=method_card_ids,
            entrypoint=entrypoint,
            class_name=class_name,
            require_registered_method_cards=implementation_kind == "generated",
        )
        blockers.extend(provenance_blockers)
    else:
        source_hash = ""
        source_provenance = {}
        blockers.append(f"source path does not exist: {source}")
    if expected_source_hash and source_hash and expected_source_hash != source_hash:
        blockers.append("source hash does not match expected_source_hash")

    indicator_class = None
    if not blockers:
        try:
            indicator_class = _load_indicator_class(
                entrypoint=entrypoint,
                source_path=source if implementation_kind == "generated" else None,
                class_name=class_name,
            )
        except (ImportError, AttributeError, TypeError, ValueError) as exc:
            blockers.append(str(exc))
    if indicator_class is not None and not issubclass(indicator_class, Indicator):
        blockers.append("entrypoint is not a trader.indicators.Indicator subclass")

    if blockers:
        return error_envelope(
            command=MATH_REGISTER_METHOD_IMPLEMENTATION,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="method_implementation_registration_failed",
            message="method implementation registration failed",
            data={"blockers": blockers, "warnings": warnings},
        )

    resolved_class_name = class_name or entrypoint.split(":")[-1]
    manifest = MethodImplementationManifest(
        implementation_id=stable_research_id(
            "method_impl",
            {
                "method_id": method_id,
                "entrypoint": entrypoint,
                "source_hash": source_hash,
                "method_card_ids": list(method_card_ids),
                "constructor_kwargs": dict(constructor_kwargs),
            },
        ),
        method_id=method_id,
        language="python",
        implementation_kind=implementation_kind,
        entrypoint=entrypoint,
        class_name=resolved_class_name,
        source_path=str(source),
        source_hash=source_hash,
        source_provenance=source_provenance,
        constructor_kwargs=constructor_kwargs,
        method_card_ids=method_card_ids,
        method_contract=method_contract,
        dependency_allowlist=dependency_allowlist,
    )
    manifest_path = _save_manifest(artifact_root, manifest)
    return success_envelope(
        command=MATH_REGISTER_METHOD_IMPLEMENTATION,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"method_implementation_manifest": manifest.to_dict()},
        artifacts={
            "method_implementation_manifest": ArtifactReference(
                artifact_type="method_implementation_manifest",
                path=manifest_path,
                metadata={"id": manifest.implementation_id},
            ).to_dict(),
        },
        warnings=warnings,
    )


def run_indicator_fixtures(
    *,
    artifact_root: str | Path,
    implementation_id: str | None = None,
    implementation_manifest: Mapping[str, Any] | None = None,
    fixtures: Sequence[Mapping[str, Any]] | None = None,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Run deterministic indicator fixtures for a registered manifest."""
    try:
        manifest = (
            MethodImplementationManifest.from_dict(implementation_manifest)
            if implementation_manifest is not None
            else _load_manifest(artifact_root, str(implementation_id or ""))
        )
    except (FileNotFoundError, ValueError) as exc:
        return _error(MATH_RUN_INDICATOR_FIXTURES, "method_implementation_not_found", str(exc))

    register_check = register_method_implementation(
        artifact_root=artifact_root,
        method_id=manifest.method_id,
        method_card_ids=manifest.method_card_ids,
        method_contract=manifest.method_contract,
        entrypoint=manifest.entrypoint,
        source_path=manifest.source_path,
        class_name=manifest.class_name,
        constructor_kwargs=manifest.constructor_kwargs,
        implementation_kind=manifest.implementation_kind,
        dependency_allowlist=manifest.dependency_allowlist,
        expected_source_hash=manifest.source_hash,
        knowledge_store=knowledge_store,
    )
    if not register_check.ok:
        return error_envelope(
            command=MATH_RUN_INDICATOR_FIXTURES,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="method_implementation_validation_failed",
            message="method implementation validation failed before fixtures",
            data=register_check.data,
        )

    manifest = MethodImplementationManifest.from_dict(register_check.data["method_implementation_manifest"])
    fixture_payloads = tuple(fixtures or _default_fixtures(manifest.method_id))
    if not fixture_payloads:
        return _error(MATH_RUN_INDICATOR_FIXTURES, "fixtures_required", f"no fixtures configured for {manifest.method_id}")

    blockers: list[str] = []
    warnings: list[str] = []
    results = []
    try:
        indicator_class = _load_indicator_class(
            entrypoint=manifest.entrypoint,
            source_path=Path(manifest.source_path) if manifest.implementation_kind == "generated" else None,
            class_name=manifest.class_name,
        )
        indicator = indicator_class(**dict(manifest.constructor_kwargs))
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        return _error(MATH_RUN_INDICATOR_FIXTURES, "indicator_load_failed", str(exc))

    if not isinstance(indicator, Indicator):
        return _error(MATH_RUN_INDICATOR_FIXTURES, "invalid_indicator_contract", "implementation is not an Indicator")

    for fixture in fixture_payloads:
        result = _run_fixture(indicator, fixture)
        results.append(result)
        if result["status"] != "passed":
            blockers.append(f"fixture failed: {result['fixture_id']}")
        warnings.extend(str(warning) for warning in result.get("warnings", ()))

    status = "passed" if not blockers else "failed"
    validation_id = stable_research_id(
        "indicator_validation",
        {
            "implementation_id": manifest.implementation_id,
            "source_hash": manifest.source_hash,
            "fixtures": [result["fixture_id"] for result in results],
            "status": status,
        },
    )
    report = {
        "artifact_type": "indicator_validation_report",
        "schema_version": SCHEMA_VERSION,
        "validation_id": validation_id,
        "implementation_id": manifest.implementation_id,
        "method_id": manifest.method_id,
        "entrypoint": manifest.entrypoint,
        "source_hash": manifest.source_hash,
        "status": status,
        "fixture_count": len(results),
        "fixture_results": results,
        "warnings": warnings,
        "blockers": blockers,
    }
    report_path = _validation_report_path(artifact_root, validation_id)
    write_json_artifact(report, report_path)
    updated_manifest = replace(manifest, status="validated" if not blockers else "blocked")
    manifest_path = _save_manifest(artifact_root, updated_manifest)
    data = {
        "method_implementation_manifest": updated_manifest.to_dict(),
        "indicator_validation_report": report,
    }
    artifacts = {
        "method_implementation_manifest": ArtifactReference(
            artifact_type="method_implementation_manifest",
            path=manifest_path,
            metadata={"id": updated_manifest.implementation_id},
        ).to_dict(),
        "indicator_validation_report": ArtifactReference(
            artifact_type="indicator_validation_report",
            path=report_path,
            metadata={"id": validation_id},
        ).to_dict(),
    }
    if blockers:
        return error_envelope(
            command=MATH_RUN_INDICATOR_FIXTURES,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="indicator_fixture_validation_failed",
            message="indicator fixture validation failed",
            data=data,
        )
    return success_envelope(
        command=MATH_RUN_INDICATOR_FIXTURES,
        side_effect=SideEffect.LOCAL_MUTATING,
        data=data,
        artifacts=artifacts,
        warnings=warnings,
    )


def generate_python_method_from_payload(
    *,
    artifact_root: str | Path,
    method_id: str,
    method_card_ids: Sequence[str],
    method_contract: Mapping[str, Any],
    llm_payload: Mapping[str, Any],
    fixtures: Sequence[Mapping[str, Any]] | None = None,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Persist an LLM-authored Python draft, then register and fixture-validate it."""
    source_code = str(llm_payload.get("source_code") or "")
    class_name = str(llm_payload.get("class_name") or "").strip()
    if not source_code.strip():
        return _error(MATH_GENERATE_PYTHON_METHOD, "generated_source_required", "LLM payload did not include source_code")
    if not class_name:
        return _error(MATH_GENERATE_PYTHON_METHOD, "generated_class_required", "LLM payload did not include class_name")

    source_path = _quarantine_source_path(artifact_root, method_id, source_code)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source_code, encoding="utf-8")
    blockers = _static_safety_blockers(source_path, dependency_allowlist=DEFAULT_ALLOWED_IMPORTS)
    if blockers:
        return error_envelope(
            command=MATH_GENERATE_PYTHON_METHOD,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="generated_method_safety_failed",
            message="generated Python method failed static safety checks",
            data={
                "generated_source_path": str(source_path),
                "blockers": blockers,
                "status": "blocked",
            },
        )

    register_result = register_method_implementation(
        artifact_root=artifact_root,
        method_id=method_id,
        method_card_ids=method_card_ids,
        method_contract=method_contract,
        entrypoint=f"{source_path}:{class_name}",
        source_path=source_path,
        class_name=class_name,
        implementation_kind="generated",
        knowledge_store=knowledge_store,
    )
    if not register_result.ok:
        return error_envelope(
            command=MATH_GENERATE_PYTHON_METHOD,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="generated_method_registration_failed",
            message="generated Python method registration failed",
            data={
                "generated_source_path": str(source_path),
                "registration": register_result.to_dict(),
                "status": "blocked",
            },
        )
    fixture_result = run_indicator_fixtures(
        artifact_root=artifact_root,
        implementation_manifest=register_result.data["method_implementation_manifest"],
        fixtures=fixtures,
        knowledge_store=knowledge_store,
    )
    data = {
        "generated_source_path": str(source_path),
        "registration": register_result.data,
        "fixture_validation": fixture_result.data,
        "status": "validated" if fixture_result.ok else "blocked",
    }
    artifacts = {
        "generated_source": ArtifactReference(
            artifact_type="generated_python_method",
            path=source_path,
            metadata={"method_id": method_id, "status": data["status"]},
        ).to_dict()
    }
    if not fixture_result.ok:
        return error_envelope(
            command=MATH_GENERATE_PYTHON_METHOD,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="generated_method_fixture_validation_failed",
            message="generated Python method failed fixture validation",
            data=data,
        )
    return success_envelope(
        command=MATH_GENERATE_PYTHON_METHOD,
        side_effect=SideEffect.LOCAL_MUTATING,
        data=data,
        artifacts=artifacts,
    )


def generation_messages(
    method_id: str,
    method_contract: Mapping[str, Any],
    method_card_ids: Sequence[str] | None = None,
) -> tuple[Mapping[str, str], ...]:
    """Return provider-neutral generation prompt messages for the MCP LLM bridge."""
    resolved_method_card_ids = [str(method_card_id) for method_card_id in _sequence(method_card_ids)]
    resolved_method_card_ids.extend(
        str(ref["method_card_id"])
        for ref in _sequence(method_contract.get("knowledge_evidence_refs"))
        if isinstance(ref, Mapping) and ref.get("method_card_id")
    )
    resolved_method_card_ids = sorted(set(resolved_method_card_ids))
    return (
        {
            "role": "system",
            "content": (
                "Return JSON only with source_code and class_name for one Python class that subclasses "
                "trader.indicators.Indicator. Do not use filesystem, network, subprocess, SQL, dynamic imports, "
                "eval, or exec. The source_code must start with a module docstring containing a Source reference "
                "section and an Implements section."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Create a quarantined Python Indicator implementation for {method_id}: {dict(method_contract)}. "
                f"Approved method-card IDs: {resolved_method_card_ids}. The module docstring must name the registry "
                "method, approved method-card IDs, generated class, Trader Indicator runtime contract, exact implemented "
                "formula or algorithm, input ordering, warmup behavior, output ordering, and no-lookahead boundary."
            ),
        },
    )


def generation_response_schema() -> Mapping[str, Any]:
    """Return the expected JSON shape for generated Python methods."""
    return {
        "type": "object",
        "required": ["class_name", "source_code"],
        "properties": {
            "class_name": {"type": "string"},
            "source_code": {"type": "string"},
            "implementation_notes": {"type": "string"},
        },
    }


def _run_fixture(indicator: Indicator, fixture: Mapping[str, Any]) -> dict[str, Any]:
    fixture_id = str(fixture.get("fixture_id") or stable_research_id("fixture", fixture))
    closes = [float(value) for value in _sequence(fixture.get("closes"))]
    expected = [_expected_value(value) for value in _sequence(fixture.get("expected"))]
    tolerance = float(fixture.get("tolerance") or 1e-9)
    warnings: list[str] = []
    bars = _bars_from_ascending_closes(closes)
    try:
        raw_actual = list(indicator.compute_series(bars))
    except ValueError as exc:
        return {
            "fixture_id": fixture_id,
            "status": "failed",
            "message": str(exc),
            "input_count": len(closes),
            "expected": expected,
            "actual": [],
            "warnings": warnings,
        }
    actual = [None] * (indicator.window - 1) + list(reversed(raw_actual))
    mismatches = []
    if len(actual) != len(expected):
        mismatches.append({"reason": "output length mismatch", "expected_length": len(expected), "actual_length": len(actual)})
    for idx, (expected_value, actual_value) in enumerate(zip(expected, actual, strict=False)):
        if not _values_match(expected_value, actual_value, tolerance=tolerance):
            mismatches.append({"index": idx, "expected": expected_value, "actual": actual_value})
    lookahead_mismatches = _lookahead_mismatches(indicator, closes, actual, tolerance=tolerance)
    mismatches.extend(lookahead_mismatches)
    return {
        "fixture_id": fixture_id,
        "status": "passed" if not mismatches else "failed",
        "input_count": len(closes),
        "warmup_null_count": indicator.window - 1,
        "expected": expected,
        "actual": [_expected_value(value) for value in actual],
        "mismatches": mismatches,
        "warnings": warnings,
    }


def _lookahead_mismatches(indicator: Indicator, closes: Sequence[float], actual: Sequence[Any], *, tolerance: float) -> list[Mapping[str, Any]]:
    mismatches = []
    for idx in range(indicator.window - 1, len(closes)):
        prefix_bars = _bars_from_ascending_closes(closes[: idx + 1])
        prefix_actual = list(indicator.compute_series(prefix_bars))
        if not prefix_actual:
            mismatches.append({"index": idx, "reason": "prefix produced no output"})
            continue
        prefix_value = prefix_actual[0]
        if not _values_match(actual[idx], prefix_value, tolerance=tolerance):
            mismatches.append({"index": idx, "reason": "no-lookahead prefix mismatch", "expected": actual[idx], "actual": prefix_value})
    return mismatches


def _default_fixtures(method_id: str) -> tuple[Mapping[str, Any], ...]:
    fixtures = {
        "sma": (
            {
                "fixture_id": "sma_period_3_linear",
                "closes": [1, 2, 3, 4, 5],
                "expected": [None, None, 2.0, 3.0, 4.0],
                "tolerance": 1e-9,
            },
        ),
        "ema": (
            {
                "fixture_id": "ema_period_3_linear",
                "closes": [1, 2, 3, 4, 5, 6],
                "expected": [None, None, 2.0, 3.0, 4.0, 5.0],
                "tolerance": 1e-9,
            },
        ),
        "rsi": (
            {
                "fixture_id": "rsi_period_5_uptrend",
                "closes": [1, 2, 3, 4, 5, 6],
                "expected": [None, None, None, None, None, 100.0],
                "tolerance": 1e-9,
            },
        ),
        "rolling_volatility": (
            {
                "fixture_id": "rolling_volatility_window_3_linear",
                "closes": [1, 2, 3, 4, 5],
                "expected": [None, None, 1.0, 1.0, 1.0],
                "tolerance": 1e-9,
            },
        ),
        "z_score": (
            {
                "fixture_id": "z_score_window_3_linear",
                "closes": [1, 2, 3, 4, 5],
                "expected": [None, None, 1.0, 1.0, 1.0],
                "tolerance": 1e-9,
            },
        ),
        "bollinger_wma_band_rule": (
            {
                "fixture_id": "bollinger_wma_period_3_linear",
                "closes": [1, 2, 3, 4, 5],
                "expected": [
                    None,
                    None,
                    {
                        "middle": 2.0,
                        "upper": 3.632993161855452,
                        "lower": 0.36700683814454793,
                        "bandwidth": 1.632993161855452,
                    },
                    {
                        "middle": 3.0,
                        "upper": 4.6329931618554525,
                        "lower": 1.367006838144548,
                        "bandwidth": 1.088662107903635,
                    },
                    {
                        "middle": 4.0,
                        "upper": 5.6329931618554525,
                        "lower": 2.367006838144548,
                        "bandwidth": 0.8164965809277261,
                    },
                ],
                "tolerance": 1e-9,
            },
        ),
    }
    return fixtures.get(method_id, tuple())


def _method_contract(
    method_id: str,
    method_contract: Mapping[str, Any] | None,
    method_card_ids: Sequence[str],
    constructor_kwargs: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if method_contract:
        payload = dict(method_contract)
    else:
        payload = {"method_id": method_id, "parameters": _registry_parameters(method_id, constructor_kwargs), "no_lookahead": True}
    refs = payload.get("knowledge_evidence_refs") or [{"method_card_id": method_card_id} for method_card_id in method_card_ids]
    payload["knowledge_evidence_refs"] = list(refs) if not isinstance(refs, Mapping) else [dict(refs)]
    return payload


def _registry_parameters(method_id: str, constructor_kwargs: Mapping[str, Any] | None) -> Mapping[str, Any]:
    kwargs = dict(constructor_kwargs or {})
    if method_id in {"sma", "ema", "rsi"}:
        return {"period": int(kwargs.get("period", 3 if method_id != "rsi" else 5))}
    if method_id == "rolling_volatility":
        return {"window": int(kwargs.get("window", kwargs.get("window_size", 3))), "ddof": int(kwargs.get("ddof", 1))}
    if method_id == "z_score":
        return {"window": int(kwargs.get("window", kwargs.get("window_size", 3)))}
    if method_id == "bollinger_wma_band_rule":
        return {
            "period": int(kwargs.get("period", 3)),
            "stddev_multiplier": float(kwargs.get("stddev_multiplier", 2.0)),
        }
    return {}


def _constructor_kwargs(
    method_id: str,
    method_contract: Mapping[str, Any],
    constructor_kwargs: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if constructor_kwargs:
        return dict(constructor_kwargs)
    parameters = _mapping(method_contract.get("parameters"))
    if method_id in {"sma", "ema", "rsi"}:
        return {"period": int(parameters.get("period", 3 if method_id != "rsi" else 5))}
    if method_id == "rolling_volatility":
        return {"window_size": int(parameters.get("window", 3)), "ddof": int(parameters.get("ddof", 1))}
    if method_id == "z_score":
        return {"window_size": int(parameters.get("window", 3))}
    if method_id == "bollinger_wma_band_rule":
        return {
            "period": int(parameters.get("period", 3)),
            "stddev_multiplier": float(parameters.get("stddev_multiplier", 2.0)),
        }
    return {}


def _source_provenance(
    path: Path,
    *,
    method_id: str,
    method_card_ids: Sequence[str],
    entrypoint: str,
    class_name: str | None,
    require_registered_method_cards: bool,
) -> tuple[Mapping[str, Any], list[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return {}, [f"source syntax error: {exc}"]
    docstring = ast.get_docstring(tree, clean=True) or ""
    normalized = docstring.lower()
    blockers: list[str] = []
    required_terms = {
        "Source reference": "source reference",
        "Implements": "implements",
        "Trader Indicator runtime contract": "trader.indicators.indicator",
        "warmup behavior": "warmup",
        "no-lookahead boundary": "lookahead",
    }
    for label, term in required_terms.items():
        if term not in normalized:
            blockers.append(f"module docstring missing {label}")
    if method_id.lower() not in normalized:
        blockers.append(f"module docstring missing registry method: {method_id}")
    declared_method_card_ids = sorted(set(re.findall(r"method_card_[A-Za-z0-9_]+", docstring)))
    if not declared_method_card_ids:
        blockers.append("module docstring missing approved method-card reference")
    if require_registered_method_cards:
        for method_card_id in method_card_ids:
            if method_card_id.lower() not in normalized:
                blockers.append(f"module docstring missing approved method-card ref: {method_card_id}")
    resolved_class_name = class_name or entrypoint.split(":")[-1]
    if resolved_class_name and resolved_class_name.lower() not in normalized:
        blockers.append(f"module docstring missing implementation class: {resolved_class_name}")
    return {
        "module_docstring": docstring,
        "required_method_id": method_id,
        "registered_method_card_ids": list(method_card_ids),
        "declared_method_card_ids": declared_method_card_ids,
        "exact_registered_method_card_ids_required": require_registered_method_cards,
        "required_class_name": resolved_class_name,
        "validated": not blockers,
    }, sorted(set(blockers))


def _static_safety_blockers(path: Path, *, dependency_allowlist: Sequence[str]) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"source syntax error: {exc}"]
    allowed = set(dependency_allowlist)
    blockers: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _import_allowed(alias.name, allowed):
                    blockers.append(f"import is not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not _import_allowed(module, allowed):
                blockers.append(f"import is not allowed: {module}")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            blockers.append("global/nonlocal mutation is not allowed")
        elif isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in FORBIDDEN_CALLS:
                blockers.append(f"call is not allowed: {call_name}")
    return sorted(set(blockers))


def _import_allowed(module: str, allowed: set[str]) -> bool:
    return any(module == item or module.startswith(f"{item}.") for item in allowed)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _load_indicator_class(*, entrypoint: str, source_path: Path | None = None, class_name: str | None = None) -> type[Indicator]:
    if source_path is not None and source_path.exists() and class_name:
        module_name = f"_trader_generated_{hashlib.sha256(str(source_path).encode('utf-8')).hexdigest()[:12]}"
        spec = importlib.util.spec_from_file_location(module_name, source_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not load source path: {source_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        loaded = getattr(module, class_name)
    else:
        if ":" not in entrypoint:
            raise ValueError("entrypoint must use module:ClassName format")
        module_name, object_name = entrypoint.split(":", 1)
        module = importlib.import_module(module_name)
        loaded = getattr(module, object_name)
    if not isinstance(loaded, type):
        raise TypeError("entrypoint is not a class")
    return loaded


def _source_path_for_entrypoint(entrypoint: str) -> Path | None:
    if ":" not in entrypoint:
        path_text, _, _class_name = entrypoint.rpartition(":")
        path = Path(path_text)
        return path.resolve() if path.exists() else None
    module_name, object_name = entrypoint.split(":", 1)
    try:
        module = importlib.import_module(module_name)
        loaded = getattr(module, object_name)
    except (ImportError, AttributeError):
        return None
    source = inspect.getsourcefile(loaded)
    return Path(source).resolve() if source else None


def _bars_from_ascending_closes(closes: Sequence[float]) -> list[Bar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [
        Bar(
            ts=base + timedelta(minutes=idx),
            open=float(close),
            high=float(close),
            low=float(close),
            close=float(close),
            volume=1.0,
            vwap=None,
            trade_count=None,
        )
        for idx, close in enumerate(closes)
    ]
    return list(reversed(bars))


def _values_match(expected: Any, actual: Any, *, tolerance: float) -> bool:
    expected = _expected_value(expected)
    actual = _expected_value(actual)
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, Mapping) or isinstance(actual, Mapping):
        if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
            return False
        if set(expected) != set(actual):
            return False
        return all(_values_match(expected[key], actual[key], tolerance=tolerance) for key in sorted(expected))
    if isinstance(expected, (list, tuple)) or isinstance(actual, (list, tuple)):
        if not isinstance(expected, (list, tuple)) or not isinstance(actual, (list, tuple)):
            return False
        if len(expected) != len(actual):
            return False
        return all(
            _values_match(expected_value, actual_value, tolerance=tolerance)
            for expected_value, actual_value in zip(expected, actual, strict=False)
        )
    try:
        return abs(float(expected) - float(actual)) <= tolerance
    except (TypeError, ValueError):
        return expected == actual


def _expected_value(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value) and not isinstance(value, type):
        return {str(key): _expected_value(inner) for key, inner in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _expected_value(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [_expected_value(item) for item in value]
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _implementation_root(artifact_root: str | Path) -> Path:
    return Path(artifact_root) / "method_implementations"


def _manifest_path(artifact_root: str | Path, implementation_id: str) -> Path:
    return _implementation_root(artifact_root) / "manifests" / f"{implementation_id}.json"


def _validation_report_path(artifact_root: str | Path, validation_id: str) -> Path:
    return _implementation_root(artifact_root) / "validation_reports" / f"{validation_id}.json"


def _quarantine_source_path(artifact_root: str | Path, method_id: str, source_code: str) -> Path:
    digest = hashlib.sha256(source_code.encode("utf-8")).hexdigest()[:16]
    return _implementation_root(artifact_root) / "quarantine" / f"{method_id}_{digest}.py"


def _save_manifest(artifact_root: str | Path, manifest: MethodImplementationManifest) -> Path:
    return write_json_artifact(manifest.to_dict(), _manifest_path(artifact_root, manifest.implementation_id))


def _load_manifest(artifact_root: str | Path, implementation_id: str) -> MethodImplementationManifest:
    if not implementation_id:
        raise ValueError("implementation_id is required")
    path = _manifest_path(artifact_root, implementation_id)
    if not path.exists():
        raise FileNotFoundError(f"unknown implementation_id: {implementation_id}")
    import json

    return MethodImplementationManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return value
    return (value,)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _error(command: str, code: str, message: str) -> ToolEnvelope:
    return error_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
    )
