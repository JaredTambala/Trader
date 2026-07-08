"""Method package manifests for source-backed strategy handoffs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.contracts import (
    ArtifactReference,
    SideEffect,
    ToolEnvelope,
    error_envelope,
    success_envelope,
    write_json_artifact,
)
from trader_research.artifact_store import ResearchArtifactStore, ResearchArtifactStoreError, load_artifact_ref
from trader_research.domain import (
    INDICATOR_VALIDATION_REPORT,
    METHOD_PACKAGE_MANIFEST,
    SIGNAL_IMPLEMENTATION_VALIDATION_REPORT,
    stable_research_id,
)
from trader_research.method_implementations.io import file_sha256, load_manifest, validation_report_path
from trader_research.method_implementations.manifest import (
    INDICATOR_RUNTIME_CONTRACT,
    SIGNAL_RUNTIME_CONTRACT,
    MethodImplementationManifest,
    mapping,
)


MATH_PACKAGE_METHOD_ARTIFACT = "math_package_method_artifact"
METHOD_PACKAGE_SCHEMA_VERSION = "1"
SUPPORTED_RUNTIME_CONTRACTS = frozenset({INDICATOR_RUNTIME_CONTRACT, SIGNAL_RUNTIME_CONTRACT})


@dataclass(frozen=True)
class MethodPackageManifest:
    """Source-backed handoff package for one validated method implementation.

    Attributes:
        package_id: Stable package ID derived from the validated Python reference.
        method_id: Maintained method contract identifier.
        runtime_contract: Trader runtime contract implemented by the package.
        implementation_id: Validated Python implementation manifest ID.
        entrypoint: Import path used to load the Python implementation.
        class_name: Concrete implementation class name.
        source_path: Source file path validated by registration and fixtures.
        source_hash: SHA-256 hash of the validated source file.
        source_provenance: Citation/provenance metadata copied from registration.
        constructor_kwargs: Constructor arguments validated with the implementation.
        method_contract: Method contract snapshot used during validation.
        method_card_ids: Approved method-card IDs backing the implementation.
        validation_report_ref: Reference to the passed fixture validation report.
        validation_summary: Compact fixture validation summary.
        safety_profile: Static safety profile inherited from implementation registration.
        dependency_allowlist: Imports allowed during implementation validation.
        cxx_kernel_refs: Optional accepted compiled-kernel metadata.
        warnings: Non-fatal packaging warnings.
        blockers: Blocking issues; successful packages keep this empty.
    """

    package_id: str
    method_id: str
    runtime_contract: str
    implementation_id: str
    entrypoint: str
    class_name: str
    source_path: str
    source_hash: str
    source_provenance: Mapping[str, Any]
    constructor_kwargs: Mapping[str, Any]
    method_contract: Mapping[str, Any]
    method_card_ids: tuple[str, ...]
    validation_report_ref: Mapping[str, Any]
    validation_summary: Mapping[str, Any]
    safety_profile: Mapping[str, Any]
    dependency_allowlist: tuple[str, ...]
    cxx_kernel_refs: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    status: str = "validated"
    artifact_type: str = METHOD_PACKAGE_MANIFEST
    schema_version: str = METHOD_PACKAGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize the method package into its stable artifact payload."""
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "method_id": self.method_id,
            "runtime_contract": self.runtime_contract,
            "implementation_id": self.implementation_id,
            "entrypoint": self.entrypoint,
            "class_name": self.class_name,
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "source_provenance": dict(self.source_provenance),
            "constructor_kwargs": dict(self.constructor_kwargs),
            "method_contract": dict(self.method_contract),
            "method_card_ids": list(self.method_card_ids),
            "validation_report_ref": dict(self.validation_report_ref),
            "validation_summary": dict(self.validation_summary),
            "safety_profile": dict(self.safety_profile),
            "dependency_allowlist": list(self.dependency_allowlist),
            "cxx_kernel_refs": [dict(ref) for ref in self.cxx_kernel_refs],
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodPackageManifest":
        """Parse a method package manifest from JSON-compatible artifact data."""
        return cls(
            package_id=str(payload.get("package_id") or ""),
            method_id=str(payload.get("method_id") or ""),
            runtime_contract=str(payload.get("runtime_contract") or ""),
            implementation_id=str(payload.get("implementation_id") or ""),
            entrypoint=str(payload.get("entrypoint") or ""),
            class_name=str(payload.get("class_name") or ""),
            source_path=str(payload.get("source_path") or ""),
            source_hash=str(payload.get("source_hash") or ""),
            source_provenance=mapping(payload.get("source_provenance")),
            constructor_kwargs=mapping(payload.get("constructor_kwargs")),
            method_contract=mapping(payload.get("method_contract")),
            method_card_ids=tuple(str(item) for item in _sequence(payload.get("method_card_ids"))),
            validation_report_ref=mapping(payload.get("validation_report_ref")),
            validation_summary=mapping(payload.get("validation_summary")),
            safety_profile=mapping(payload.get("safety_profile")),
            dependency_allowlist=tuple(str(item) for item in _sequence(payload.get("dependency_allowlist"))),
            cxx_kernel_refs=tuple(mapping(item) for item in _sequence(payload.get("cxx_kernel_refs"))),
            warnings=tuple(str(item) for item in _sequence(payload.get("warnings"))),
            blockers=tuple(str(item) for item in _sequence(payload.get("blockers"))),
            status=str(payload.get("status") or "validated"),
            artifact_type=str(payload.get("artifact_type") or METHOD_PACKAGE_MANIFEST),
            schema_version=str(payload.get("schema_version") or METHOD_PACKAGE_SCHEMA_VERSION),
        )


def package_method_artifact(
    *,
    artifact_root: str | Path,
    implementation_id: str | None = None,
    implementation_manifest: Mapping[str, Any] | None = None,
    validation_report_id: str | None = None,
    validation_report: Mapping[str, Any] | None = None,
    cxx_kernel_id: str | None = None,
    cxx_kernel_manifest: Mapping[str, Any] | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Package a validated Python implementation for strategy-construction handoff.

    Args:
        artifact_root: Root directory for local research artifacts.
        implementation_id: Optional persisted implementation manifest ID.
        implementation_manifest: Optional direct implementation manifest payload.
        validation_report_id: Optional persisted fixture validation report ID.
        validation_report: Optional direct fixture validation report payload.
        cxx_kernel_id: Optional persisted C++ kernel manifest ID.
        cxx_kernel_manifest: Optional direct C++ kernel manifest payload.

    Returns:
        Local-mutating package envelope. Invalid Python implementation or validation
        inputs fail closed; invalid C++ inputs produce warnings only.
    """
    warnings: list[str] = []
    blockers: list[str] = []
    try:
        implementation = _resolve_implementation_manifest(
            artifact_root=artifact_root,
            implementation_id=implementation_id,
            implementation_manifest=implementation_manifest,
            artifact_store=artifact_store,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _package_error([str(exc)], warnings)

    try:
        report, report_path = _resolve_validation_report(
            artifact_root=artifact_root,
            validation_report_id=validation_report_id,
            validation_report=validation_report,
            artifact_store=artifact_store,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return _package_error([str(exc)], warnings)

    blockers.extend(_implementation_blockers(implementation))
    blockers.extend(_source_hash_blockers(implementation))
    blockers.extend(_validation_report_blockers(report, implementation))
    if blockers:
        return _package_error(blockers, warnings, implementation=implementation, validation_report=report)

    cxx_refs, cxx_warnings = _accepted_cxx_refs(
        artifact_root=artifact_root,
        implementation=implementation,
        cxx_kernel_id=cxx_kernel_id,
        cxx_kernel_manifest=cxx_kernel_manifest,
    )
    warnings.extend(cxx_warnings)
    package_id = _package_id(implementation, report, cxx_refs)
    manifest = MethodPackageManifest(
        package_id=package_id,
        method_id=implementation.method_id,
        runtime_contract=implementation.runtime_contract,
        implementation_id=implementation.implementation_id,
        entrypoint=implementation.entrypoint,
        class_name=implementation.class_name,
        source_path=implementation.source_path,
        source_hash=implementation.source_hash,
        source_provenance=implementation.source_provenance,
        constructor_kwargs=implementation.constructor_kwargs,
        method_contract=implementation.method_contract,
        method_card_ids=implementation.method_card_ids,
        validation_report_ref=_validation_report_ref(report, report_path),
        validation_summary=_validation_summary(report),
        safety_profile=implementation.safety_profile,
        dependency_allowlist=implementation.dependency_allowlist,
        cxx_kernel_refs=tuple(cxx_refs),
        warnings=tuple(warnings),
    )
    manifest_payload = manifest.to_dict()
    if artifact_store is not None:
        manifest_record = artifact_store.save_artifact(
            artifact_type=METHOD_PACKAGE_MANIFEST,
            artifact_id=manifest.package_id,
            payload=manifest_payload,
            status=manifest.status,
            source_hash=manifest.source_hash,
            metadata={"method_id": manifest.method_id, "runtime_contract": manifest.runtime_contract},
        )
        manifest_ref = ArtifactReference(
            artifact_type=METHOD_PACKAGE_MANIFEST,
            uri=manifest_record.uri,
            metadata={"id": manifest.package_id},
        ).to_dict()
    else:
        manifest_path = _save_package_manifest(artifact_root, manifest)
        manifest_ref = ArtifactReference(
            artifact_type=METHOD_PACKAGE_MANIFEST,
            path=manifest_path,
            metadata={"id": manifest.package_id},
        ).to_dict()
    return success_envelope(
        command=MATH_PACKAGE_METHOD_ARTIFACT,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"method_package_manifest": manifest_payload},
        artifacts={
            "method_package_manifest": manifest_ref,
        },
        warnings=tuple(warnings),
    )


def method_package_path(artifact_root: str | Path, package_id: str) -> Path:
    """Return the deterministic local path for one method package manifest."""
    return Path(artifact_root) / "method_packages" / "manifests" / f"{package_id}.json"


def _resolve_implementation_manifest(
    *,
    artifact_root: str | Path,
    implementation_id: str | None,
    implementation_manifest: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore | None,
) -> MethodImplementationManifest:
    if implementation_manifest is not None:
        return MethodImplementationManifest.from_dict(implementation_manifest)
    if artifact_store is not None:
        return MethodImplementationManifest.from_dict(
            load_artifact_ref(artifact_store, "method_implementation_manifest", str(implementation_id or ""))
        )
    return load_manifest(artifact_root, str(implementation_id or ""))


def _resolve_validation_report(
    *,
    artifact_root: str | Path,
    validation_report_id: str | None,
    validation_report: Mapping[str, Any] | None,
    artifact_store: ResearchArtifactStore | None,
) -> tuple[Mapping[str, Any], Path | None]:
    if validation_report is not None:
        return dict(validation_report), None
    report_id = str(validation_report_id or "").strip()
    if not report_id:
        raise ValueError("validation_report_id or validation_report is required")
    if artifact_store is not None:
        for artifact_type in (SIGNAL_IMPLEMENTATION_VALIDATION_REPORT, INDICATOR_VALIDATION_REPORT):
            try:
                return load_artifact_ref(artifact_store, artifact_type, report_id), None
            except ResearchArtifactStoreError:
                continue
        raise FileNotFoundError(f"unknown validation_report_id: {report_id}")
    path = validation_report_path(artifact_root, report_id)
    if not path.exists():
        raise FileNotFoundError(f"unknown validation_report_id: {report_id}")
    return json.loads(path.read_text(encoding="utf-8")), path


def _implementation_blockers(implementation: MethodImplementationManifest) -> list[str]:
    blockers: list[str] = []
    if not implementation.implementation_id:
        blockers.append("implementation_id is required")
    if implementation.status != "validated":
        blockers.append("validated method implementation manifest is required")
    if implementation.runtime_contract not in SUPPORTED_RUNTIME_CONTRACTS:
        blockers.append(f"unsupported runtime_contract: {implementation.runtime_contract}")
    if not implementation.method_card_ids:
        blockers.append("approved method-card refs are required")
    if not implementation.source_hash:
        blockers.append("source_hash is required")
    if not implementation.source_path:
        blockers.append("source_path is required")
    return blockers


def _source_hash_blockers(implementation: MethodImplementationManifest) -> list[str]:
    if not implementation.source_path:
        return []
    source_path = Path(implementation.source_path)
    if not source_path.exists() or not source_path.is_file():
        return [f"source path does not exist: {source_path}"]
    actual_hash = file_sha256(source_path)
    if actual_hash != implementation.source_hash:
        return ["source hash does not match method implementation manifest"]
    return []


def _validation_report_blockers(
    report: Mapping[str, Any],
    implementation: MethodImplementationManifest,
) -> list[str]:
    blockers: list[str] = []
    expected_artifact_type = _expected_report_type(implementation.runtime_contract)
    if not expected_artifact_type:
        return blockers
    if str(report.get("artifact_type") or "") != expected_artifact_type:
        blockers.append(f"validation report artifact_type must be {expected_artifact_type}")
    if str(report.get("status") or "") != "passed":
        blockers.append("passed validation report is required")
    if list(_sequence(report.get("blockers"))):
        blockers.append("validation report blockers must be empty")
    if str(report.get("implementation_id") or "") != implementation.implementation_id:
        blockers.append("validation report implementation_id does not match method implementation manifest")
    if str(report.get("method_id") or "") != implementation.method_id:
        blockers.append("validation report method_id does not match method implementation manifest")
    if str(report.get("source_hash") or "") != implementation.source_hash:
        blockers.append("validation report source_hash does not match method implementation manifest")
    if not str(report.get("validation_id") or "").strip():
        blockers.append("validation report validation_id is required")
    return blockers


def _expected_report_type(runtime_contract: str) -> str:
    if runtime_contract == INDICATOR_RUNTIME_CONTRACT:
        return INDICATOR_VALIDATION_REPORT
    if runtime_contract == SIGNAL_RUNTIME_CONTRACT:
        return SIGNAL_IMPLEMENTATION_VALIDATION_REPORT
    return ""


def _accepted_cxx_refs(
    *,
    artifact_root: str | Path,
    implementation: MethodImplementationManifest,
    cxx_kernel_id: str | None,
    cxx_kernel_manifest: Mapping[str, Any] | None,
) -> tuple[list[Mapping[str, Any]], list[str]]:
    if cxx_kernel_manifest is None and not cxx_kernel_id:
        return [], []
    warnings: list[str] = []
    try:
        manifest = _resolve_cxx_kernel_manifest(
            artifact_root=artifact_root,
            cxx_kernel_id=cxx_kernel_id,
            cxx_kernel_manifest=cxx_kernel_manifest,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return [], [f"optional C++ kernel excluded: {exc}"]
    blockers = _cxx_kernel_blockers(manifest, implementation)
    if blockers:
        warnings.extend(f"optional C++ kernel excluded: {blocker}" for blocker in blockers)
        return [], warnings
    return [_cxx_kernel_ref(manifest)], []


def _resolve_cxx_kernel_manifest(
    *,
    artifact_root: str | Path,
    cxx_kernel_id: str | None,
    cxx_kernel_manifest: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if cxx_kernel_manifest is not None:
        return dict(cxx_kernel_manifest)
    kernel_id = str(cxx_kernel_id or "").strip()
    if not kernel_id:
        raise ValueError("cxx_kernel_id or cxx_kernel_manifest is required")
    path = Path(artifact_root) / "cpp_kernels" / "manifests" / f"{kernel_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"unknown cxx_kernel_id: {kernel_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _cxx_kernel_blockers(
    manifest: Mapping[str, Any],
    implementation: MethodImplementationManifest,
) -> list[str]:
    blockers: list[str] = []
    if str(manifest.get("artifact_type") or "") != "cxx_kernel_manifest":
        blockers.append("artifact_type must be cxx_kernel_manifest")
    if str(manifest.get("status") or "") != "compiled":
        blockers.append("status must be compiled")
    build = mapping(manifest.get("build"))
    if str(build.get("status") or "") != "compiled":
        blockers.append("build status must be compiled")
    if str(manifest.get("method_id") or "") != implementation.method_id:
        blockers.append("method_id does not match Python implementation")
    if str(manifest.get("python_implementation_id") or "") != implementation.implementation_id:
        blockers.append("python_implementation_id does not match Python implementation")
    if str(manifest.get("python_source_hash") or "") != implementation.source_hash:
        blockers.append("python_source_hash does not match Python implementation")
    if list(_sequence(manifest.get("blockers"))):
        blockers.append("C++ kernel manifest blockers must be empty")
    return blockers


def _cxx_kernel_ref(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "artifact_type": "cxx_kernel_manifest",
        "kernel_id": str(manifest.get("kernel_id") or ""),
        "status": str(manifest.get("status") or ""),
        "method_id": str(manifest.get("method_id") or ""),
        "python_implementation_id": str(manifest.get("python_implementation_id") or ""),
        "python_source_hash": str(manifest.get("python_source_hash") or ""),
        "template": dict(mapping(manifest.get("template"))),
        "generated_source": dict(mapping(manifest.get("generated_source"))),
        "build": dict(mapping(manifest.get("build"))),
        "abi": dict(mapping(manifest.get("abi"))),
        "benchmark_summary": dict(mapping(manifest.get("benchmark_summary"))),
    }


def _validation_report_ref(report: Mapping[str, Any], report_path: Path | None) -> dict[str, Any]:
    payload = {
        "artifact_type": str(report.get("artifact_type") or ""),
        "validation_id": str(report.get("validation_id") or ""),
        "status": str(report.get("status") or ""),
    }
    if report_path is not None:
        payload["path"] = str(report_path)
    return payload


def _validation_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "validation_id": str(report.get("validation_id") or ""),
        "status": str(report.get("status") or ""),
        "fixture_count": int(report.get("fixture_count") or 0),
        "fixture_ids": [
            str(item.get("fixture_id"))
            for item in _sequence(report.get("fixture_results"))
            if isinstance(item, Mapping) and item.get("fixture_id") is not None
        ],
        "warnings": [str(item) for item in _sequence(report.get("warnings"))],
        "blockers": [str(item) for item in _sequence(report.get("blockers"))],
    }


def _package_id(
    implementation: MethodImplementationManifest,
    validation_report: Mapping[str, Any],
    cxx_refs: Sequence[Mapping[str, Any]],
) -> str:
    return stable_research_id(
        "method_package",
        {
            "implementation_id": implementation.implementation_id,
            "method_id": implementation.method_id,
            "runtime_contract": implementation.runtime_contract,
            "source_hash": implementation.source_hash,
            "validation_id": str(validation_report.get("validation_id") or ""),
            "cxx_kernel_ids": [str(ref.get("kernel_id") or "") for ref in cxx_refs],
        },
    )


def _save_package_manifest(artifact_root: str | Path, manifest: MethodPackageManifest) -> Path:
    return write_json_artifact(manifest.to_dict(), method_package_path(artifact_root, manifest.package_id))


def _package_error(
    blockers: Sequence[str],
    warnings: Sequence[str],
    *,
    implementation: MethodImplementationManifest | None = None,
    validation_report: Mapping[str, Any] | None = None,
) -> ToolEnvelope:
    data: dict[str, Any] = {
        "blockers": list(dict.fromkeys(str(item) for item in blockers)),
        "warnings": list(dict.fromkeys(str(item) for item in warnings)),
    }
    if implementation is not None:
        data["method_implementation_manifest"] = implementation.to_dict()
    if validation_report is not None:
        data["validation_report"] = dict(validation_report)
    return error_envelope(
        command=MATH_PACKAGE_METHOD_ARTIFACT,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="method_package_validation_failed",
        message="method package validation failed",
        data=data,
    )


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return value
    return (value,)
