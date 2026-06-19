"""Artifact I/O helpers for method implementation workflows."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, write_json_artifact
from trader_research.method_implementations.manifest import MethodImplementationManifest


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of an implementation source file's bytes.

    Registration uses this digest to compare caller-supplied source hashes against
    the exact bytes on disk, which prevents a manifest from being accepted for a
    different implementation file than the one that was reviewed.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def implementation_root(artifact_root: str | Path) -> Path:
    """Return the root directory for method implementation artifacts.

    All manifests, validation reports, and quarantined generated sources live under
    this subdirectory so the workflow has one predictable local-mutating artifact
    boundary beneath the caller-provided artifact root.
    """
    return Path(artifact_root) / "method_implementations"


def manifest_path(artifact_root: str | Path, implementation_id: str) -> Path:
    """Return the deterministic manifest path for a registered implementation ID.

    Registration writes manifests here and fixture runners resolve IDs from the
    same location, keeping generated, maintained, and caller-provided
    implementations discoverable through one artifact layout.
    """
    return implementation_root(artifact_root) / "manifests" / f"{implementation_id}.json"


def validation_report_path(artifact_root: str | Path, validation_id: str) -> Path:
    """Return the output path for an implementation validation report.

    Fixture runners use validation IDs derived from manifest and result payloads,
    then persist the report under this directory so repeated equivalent validation
    runs are easy to compare.
    """
    return implementation_root(artifact_root) / "validation_reports" / f"{validation_id}.json"


def quarantine_source_path(artifact_root: str | Path, method_id: str, source_code: str) -> Path:
    """Return a content-addressed path for generated Python source under quarantine.

    The path includes the method ID and a short source-code hash so generated code
    is persisted before safety checks without overwriting unrelated drafts. Later
    registration references this exact file path and source hash.
    """
    digest = hashlib.sha256(source_code.encode("utf-8")).hexdigest()[:16]
    return implementation_root(artifact_root) / "quarantine" / f"{method_id}_{digest}.py"


def save_manifest(artifact_root: str | Path, manifest: MethodImplementationManifest) -> Path:
    """Persist a method implementation manifest to its deterministic artifact path.

    The manifest is serialized through its typed `to_dict` contract before writing,
    ensuring downstream fixture runners and review tools read the same normalized
    fields that registration validated.
    """
    return write_json_artifact(manifest.to_dict(), manifest_path(artifact_root, manifest.implementation_id))


def load_manifest(artifact_root: str | Path, implementation_id: str) -> MethodImplementationManifest:
    """Load and parse a registered method implementation manifest by ID.

    Empty IDs fail with `ValueError` and unknown IDs fail with `FileNotFoundError`
    so callers can distinguish invalid input from a missing artifact. Existing
    files are parsed back into the typed manifest before any fixture execution.
    """
    if not implementation_id:
        raise ValueError("implementation_id is required")
    path = manifest_path(artifact_root, implementation_id)
    if not path.exists():
        raise FileNotFoundError(f"unknown implementation_id: {implementation_id}")
    return MethodImplementationManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def local_mutating_error(command: str, code: str, message: str) -> ToolEnvelope:
    """Build a standard local-mutating error envelope for implementation workflows.

    Registration, generation, and fixture runners all write or inspect local
    artifacts, so their validation failures share this helper to keep side-effect
    classification and machine-readable error codes consistent.
    """
    return error_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        code=code,
        message=message,
    )
