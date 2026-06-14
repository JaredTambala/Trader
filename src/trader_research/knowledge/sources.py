"""Source registration service for the Quant Methods knowledge base."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import stable_research_id

from .domain import DEFAULT_SOURCE_TYPE, KnowledgeSourceManifest, SOURCE_TYPE_LABELS, SUPPORTED_SOURCE_EXTENSIONS
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_REGISTER_SOURCE = "knowledge_register_source"
KNOWLEDGE_LIST_SOURCES = "knowledge_list_sources"


def register_source(
    *,
    artifact_root: str | Path,
    path: str | Path,
    title: str,
    source_type: str = DEFAULT_SOURCE_TYPE,
    canonical_citation: str | None = None,
    topics: Sequence[str] | None = None,
    method_families: Sequence[str] | None = None,
    access_policy: str = "local_curated",
    allowed_roots: Sequence[str | Path] | None = None,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Register a local source file and persist a source manifest."""
    store = knowledge_store or JsonKnowledgeStore(artifact_root, allowed_roots=allowed_roots)
    try:
        resolved = _validate_source_path(path, artifact_root=artifact_root, allowed_roots=allowed_roots)
        if resolved.suffix.lower() not in SUPPORTED_SOURCE_EXTENSIONS:
            raise ValueError(f"unsupported source file type: {resolved.suffix.lower()}")
        if not title.strip():
            raise ValueError("source title is required")
        normalized_source_type = source_type.strip() or DEFAULT_SOURCE_TYPE
        if normalized_source_type not in SOURCE_TYPE_LABELS:
            allowed = ", ".join(sorted(SOURCE_TYPE_LABELS))
            raise ValueError(f"unsupported source_type: {normalized_source_type}; allowed values: {allowed}")
        file_hash = _sha256_file(resolved)
        existing = store.find_sources_by_file_hash(file_hash)
        duplicate_source_ids = tuple(
            source.source_id
            for source in existing
            if source.file_hash == file_hash and Path(source.path).resolve() != resolved
        )
        source_id = stable_research_id(
            "knowledge_source",
            {"path": str(resolved), "file_hash": file_hash, "title": title.strip()},
        )
        warnings = tuple(f"duplicate file hash matches source {source_id}" for source_id in duplicate_source_ids)
        manifest = KnowledgeSourceManifest(
            source_id=source_id,
            title=title.strip(),
            source_type=normalized_source_type,
            path=str(resolved),
            file_hash=file_hash,
            file_size_bytes=resolved.stat().st_size,
            access_policy=access_policy.strip() or "local_curated",
            topics=tuple(str(topic) for topic in (topics or ()) if str(topic).strip()),
            method_families=tuple(str(family) for family in (method_families or ()) if str(family).strip()),
            canonical_citation=canonical_citation.strip() if canonical_citation else None,
            duplicate_source_ids=duplicate_source_ids,
            warnings=warnings,
        )
        store.save_source(manifest)
    except (OSError, ValueError, KnowledgeStoreError) as exc:
        return error_envelope(
            command=KNOWLEDGE_REGISTER_SOURCE,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="source_registration_error",
            message=str(exc),
        )
    return success_envelope(
        command=KNOWLEDGE_REGISTER_SOURCE,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={
            "knowledge_source_manifest": manifest.to_dict(),
            "duplicate_source_ids": list(duplicate_source_ids),
        },
        artifacts={
            "knowledge_source_manifest": store.artifact_reference("knowledge_source_manifest", source_id)
        },
        warnings=warnings,
    )


def list_sources(
    *,
    artifact_root: str | Path,
    topic: str | None = None,
    method_family: str | None = None,
    status: str | None = None,
    limit: int = 50,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """List registered source manifests with optional filters."""
    if limit < 1 or limit > 200:
        return error_envelope(
            command=KNOWLEDGE_LIST_SOURCES,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message="limit must be between 1 and 200",
        )
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    try:
        sources = [
            source.to_dict()
            for source in store.list_sources(topic=topic, method_family=method_family, status=status, limit=limit)
        ]
    except KnowledgeStoreError as exc:
        return error_envelope(
            command=KNOWLEDGE_LIST_SOURCES,
            side_effect=SideEffect.READ_ONLY,
            code="knowledge_store_error",
            message=str(exc),
        )
    return success_envelope(
        command=KNOWLEDGE_LIST_SOURCES,
        side_effect=SideEffect.READ_ONLY,
        data={"sources": sources, "source_count": len(sources)},
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_source_path(
    path: str | Path,
    *,
    artifact_root: str | Path,
    allowed_roots: Sequence[str | Path] | None = None,
) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise ValueError(f"source path does not exist: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"source path must be a file: {resolved}")
    roots = tuple(Path(root).resolve() for root in (allowed_roots or (Path.cwd(), Path(artifact_root))))
    if not any(_is_relative_to(resolved, root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise ValueError(f"source path is outside allowed directories: {resolved}; allowed roots: {allowed}")
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
