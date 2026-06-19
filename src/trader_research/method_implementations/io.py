"""Artifact I/O helpers for method implementation workflows."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, write_json_artifact
from trader_research.method_implementations.manifest import MethodImplementationManifest


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def implementation_root(artifact_root: str | Path) -> Path:
    return Path(artifact_root) / "method_implementations"


def manifest_path(artifact_root: str | Path, implementation_id: str) -> Path:
    return implementation_root(artifact_root) / "manifests" / f"{implementation_id}.json"


def validation_report_path(artifact_root: str | Path, validation_id: str) -> Path:
    return implementation_root(artifact_root) / "validation_reports" / f"{validation_id}.json"


def quarantine_source_path(artifact_root: str | Path, method_id: str, source_code: str) -> Path:
    digest = hashlib.sha256(source_code.encode("utf-8")).hexdigest()[:16]
    return implementation_root(artifact_root) / "quarantine" / f"{method_id}_{digest}.py"


def save_manifest(artifact_root: str | Path, manifest: MethodImplementationManifest) -> Path:
    return write_json_artifact(manifest.to_dict(), manifest_path(artifact_root, manifest.implementation_id))


def load_manifest(artifact_root: str | Path, implementation_id: str) -> MethodImplementationManifest:
    if not implementation_id:
        raise ValueError("implementation_id is required")
    path = manifest_path(artifact_root, implementation_id)
    if not path.exists():
        raise FileNotFoundError(f"unknown implementation_id: {implementation_id}")
    return MethodImplementationManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def local_mutating_error(command: str, code: str, message: str) -> ToolEnvelope:
    return error_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
    )
