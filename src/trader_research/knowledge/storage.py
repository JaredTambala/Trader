"""JSON-backed storage for local Quant Methods knowledge artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.contracts import write_json_artifact
from trader_research.math_domain import MethodRegistryEntry

from .domain import (
    KnowledgeChunk,
    KnowledgeEmbeddingManifest,
    KnowledgeIngestionReport,
    KnowledgeSourceManifest,
    MethodCard,
)


class KnowledgeRepository:
    """Small JSON repository rooted under the MCP artifact directory."""

    def __init__(self, artifact_root: str | Path, *, allowed_roots: Sequence[str | Path] | None = None) -> None:
        base = Path(artifact_root)
        self.artifact_root = (base / "knowledge").resolve()
        self.allowed_roots = tuple(Path(root).resolve() for root in (allowed_roots or (Path.cwd(), base)))

    @property
    def source_dir(self) -> Path:
        return self.artifact_root / "sources"

    @property
    def chunk_dir(self) -> Path:
        return self.artifact_root / "chunks"

    @property
    def embedding_dir(self) -> Path:
        return self.artifact_root / "embeddings"

    @property
    def ingestion_dir(self) -> Path:
        return self.artifact_root / "ingestions"

    @property
    def method_card_dir(self) -> Path:
        return self.artifact_root / "method_cards"

    @property
    def method_contract_dir(self) -> Path:
        return self.artifact_root / "method_contracts"

    @property
    def index_path(self) -> Path:
        return self.artifact_root / "index.json"

    def ensure_dirs(self) -> None:
        for directory in (
            self.source_dir,
            self.chunk_dir,
            self.embedding_dir,
            self.ingestion_dir,
            self.method_card_dir,
            self.method_contract_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def validate_source_path(self, path: str | Path) -> Path:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f"source path does not exist: {resolved}")
        if not resolved.is_file():
            raise ValueError(f"source path must be a file: {resolved}")
        if not any(_is_relative_to(resolved, root) for root in self.allowed_roots):
            roots = ", ".join(str(root) for root in self.allowed_roots)
            raise ValueError(f"source path is outside allowed directories: {resolved}; allowed roots: {roots}")
        return resolved

    def source_path(self, source_id: str) -> Path:
        return self.source_dir / f"{source_id}.json"

    def chunk_manifest_path(self, source_id: str) -> Path:
        return self.chunk_dir / f"{source_id}.json"

    def ingestion_path(self, ingestion_id: str) -> Path:
        return self.ingestion_dir / f"{ingestion_id}.json"

    def embedding_path(self, embedding_manifest_id: str) -> Path:
        return self.embedding_dir / f"{embedding_manifest_id}.json"

    def method_card_path(self, method_card_id: str) -> Path:
        return self.method_card_dir / f"{method_card_id}.json"

    def method_contract_path(self, method_id: str) -> Path:
        return self.method_contract_dir / f"{method_id}.json"

    def save_source(self, manifest: KnowledgeSourceManifest) -> Path:
        self.ensure_dirs()
        return write_json_artifact(manifest.to_dict(), self.source_path(manifest.source_id))

    def load_source(self, source_id: str) -> KnowledgeSourceManifest | None:
        path = self.source_path(source_id)
        if not path.exists():
            return None
        return KnowledgeSourceManifest.from_dict(_read_json(path))

    def list_sources(self) -> tuple[KnowledgeSourceManifest, ...]:
        if not self.source_dir.exists():
            return tuple()
        return tuple(
            KnowledgeSourceManifest.from_dict(_read_json(path))
            for path in sorted(self.source_dir.glob("*.json"))
        )

    def save_chunks(self, source_id: str, chunks: Sequence[KnowledgeChunk]) -> Path:
        self.ensure_dirs()
        payload = {
            "artifact_type": "knowledge_chunk_manifest",
            "source_id": source_id,
            "chunk_count": len(chunks),
            "chunks": [chunk.to_dict() for chunk in chunks],
        }
        return write_json_artifact(payload, self.chunk_manifest_path(source_id))

    def load_chunks(self, source_id: str) -> tuple[KnowledgeChunk, ...]:
        path = self.chunk_manifest_path(source_id)
        if not path.exists():
            return tuple()
        payload = _read_json(path)
        return tuple(KnowledgeChunk.from_dict(item) for item in _sequence(payload.get("chunks")))

    def list_chunks(self) -> tuple[KnowledgeChunk, ...]:
        if not self.chunk_dir.exists():
            return tuple()
        chunks: list[KnowledgeChunk] = []
        for path in sorted(self.chunk_dir.glob("*.json")):
            payload = _read_json(path)
            chunks.extend(KnowledgeChunk.from_dict(item) for item in _sequence(payload.get("chunks")))
        return tuple(chunks)

    def save_embedding_manifest(self, manifest: KnowledgeEmbeddingManifest) -> Path:
        self.ensure_dirs()
        return write_json_artifact(manifest.to_dict(), self.embedding_path(manifest.embedding_manifest_id))

    def save_ingestion_report(self, report: KnowledgeIngestionReport) -> Path:
        self.ensure_dirs()
        return write_json_artifact(report.to_dict(), self.ingestion_path(report.ingestion_id))

    def list_ingestion_reports(self) -> tuple[KnowledgeIngestionReport, ...]:
        if not self.ingestion_dir.exists():
            return tuple()
        return tuple(
            KnowledgeIngestionReport.from_dict(_read_json(path))
            for path in sorted(self.ingestion_dir.glob("*.json"))
        )

    def save_index(self, entries: Sequence[Mapping[str, Any]]) -> Path:
        self.ensure_dirs()
        payload = {
            "artifact_type": "knowledge_search_index",
            "entry_count": len(entries),
            "entries": list(entries),
        }
        return write_json_artifact(payload, self.index_path)

    def load_index_entries(self) -> tuple[Mapping[str, Any], ...]:
        if not self.index_path.exists():
            return tuple()
        payload = _read_json(self.index_path)
        return tuple(_mapping(item) for item in _sequence(payload.get("entries")))

    def save_method_card(self, method_card: MethodCard) -> Path:
        self.ensure_dirs()
        return write_json_artifact(method_card.to_dict(), self.method_card_path(method_card.method_card_id))

    def list_persisted_method_cards(self) -> tuple[MethodCard, ...]:
        if not self.method_card_dir.exists():
            return tuple()
        return tuple(MethodCard.from_dict(_read_json(path)) for path in sorted(self.method_card_dir.glob("*.json")))

    def save_method_contract(self, method: MethodRegistryEntry) -> Path:
        self.ensure_dirs()
        return write_json_artifact(method.to_dict(), self.method_contract_path(method.method_id))

    def list_persisted_method_contracts(self) -> tuple[MethodRegistryEntry, ...]:
        if not self.method_contract_dir.exists():
            return tuple()
        return tuple(MethodRegistryEntry.from_dict(_read_json(path)) for path in sorted(self.method_contract_dir.glob("*.json")))


def _read_json(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
