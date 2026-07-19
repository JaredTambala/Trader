"""JSON-backed storage for local Quant Methods knowledge artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .domain import (
    KnowledgeChunk,
    KnowledgeEmbeddingManifest,
    KnowledgeIngestionReport,
    KnowledgeSourceManifest,
    MethodCardSet,
    MethodCard,
)


class KnowledgeRepository:
    """File-based repository for local knowledge artifacts and search indexes.

    The repository owns the on-disk layout under `<artifact_root>/knowledge`,
    converts typed domain objects to JSON files, and validates source paths against
    allowed roots before registration. It is intentionally simple storage used by
    the JSON compatibility store and local tests; higher-level services decide
    which writes are allowed and how errors become tool results.
    """

    def __init__(self, artifact_root: str | Path, *, allowed_roots: Sequence[str | Path] | None = None) -> None:
        base = Path(artifact_root)
        self.artifact_root = (base / "knowledge").resolve()
        self.allowed_roots = tuple(Path(root).resolve() for root in (allowed_roots or (Path.cwd(), base)))

    @property
    def source_dir(self) -> Path:
        """Return the artifact directory containing persisted knowledge source manifests under root."""
        return self.artifact_root / "sources"

    @property
    def chunk_dir(self) -> Path:
        """Return the artifact directory containing per-source chunk manifest files under root."""
        return self.artifact_root / "chunks"

    @property
    def embedding_dir(self) -> Path:
        """Return the artifact directory containing embedding manifest artifacts for indexed chunks."""
        return self.artifact_root / "embeddings"

    @property
    def ingestion_dir(self) -> Path:
        """Return the artifact directory containing persisted ingestion report artifacts under root."""
        return self.artifact_root / "ingestions"

    @property
    def method_card_dir(self) -> Path:
        """Return the artifact directory containing persisted draft and approved method cards."""
        return self.artifact_root / "method_cards"

    @property
    def method_card_set_dir(self) -> Path:
        """Return the artifact directory containing stable method-card set records."""
        return self.artifact_root / "method_card_sets"

    @property
    def index_path(self) -> Path:
        """Return the JSON search-index artifact path used by the compatibility store."""
        return self.artifact_root / "index.json"

    def ensure_dirs(self) -> None:
        """Create every repository subdirectory needed for local knowledge artifact writes safely."""
        for directory in (
            self.source_dir,
            self.chunk_dir,
            self.embedding_dir,
            self.ingestion_dir,
            self.method_card_dir,
            self.method_card_set_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def validate_source_path(self, path: str | Path) -> Path:
        """Resolve and validate a source path against file existence and allowed roots."""
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
        """Return the source-manifest artifact path for a stable source identifier under root."""
        return self.source_dir / f"{source_id}.json"

    def chunk_manifest_path(self, source_id: str) -> Path:
        """Return the evidence-unit manifest path associated with a stable source identifier."""
        return self.chunk_dir / f"{source_id}.json"

    def ingestion_path(self, ingestion_id: str) -> Path:
        """Return the ingestion-report artifact path associated with a stable ingestion identifier."""
        return self.ingestion_dir / f"{ingestion_id}.json"

    def embedding_path(self, embedding_manifest_id: str) -> Path:
        """Return the embedding-manifest artifact path associated with one embedding index run."""
        return self.embedding_dir / f"{embedding_manifest_id}.json"

    def method_card_path(self, method_card_id: str) -> Path:
        """Return the method-card artifact path for a draft or approved card ID."""
        return self.method_card_dir / f"{method_card_id}.json"

    def method_card_set_path(self, method_card_set_id: str) -> Path:
        """Return the method-card set artifact path for a stable aggregate ID."""
        return self.method_card_set_dir / f"{method_card_set_id}.json"

    def save_source(self, manifest: KnowledgeSourceManifest) -> Path:
        """Persist a source manifest and return the written artifact path for callers."""
        self.ensure_dirs()
        return write_json_artifact(manifest.to_dict(), self.source_path(manifest.source_id))

    def load_source(self, source_id: str) -> KnowledgeSourceManifest | None:
        """Load a source manifest by ID, returning `None` when no artifact exists locally."""
        path = self.source_path(source_id)
        if not path.exists():
            return None
        return KnowledgeSourceManifest.from_dict(_read_json(path))

    def list_sources(self) -> tuple[KnowledgeSourceManifest, ...]:
        """Load all source manifests from disk in deterministic filename order for listing."""
        if not self.source_dir.exists():
            return tuple()
        return tuple(
            KnowledgeSourceManifest.from_dict(_read_json(path))
            for path in sorted(self.source_dir.glob("*.json"))
        )

    def save_chunks(self, source_id: str, chunks: Sequence[KnowledgeChunk]) -> Path:
        """Persist the active evidence-unit manifest for one registered source identifier under root."""
        self.ensure_dirs()
        payload = {
            "artifact_type": "knowledge_evidence_unit_manifest",
            "schema_version": "2",
            "source_id": source_id,
            "evidence_unit_count": len(chunks),
            "chunk_count": len(chunks),
            "evidence_units": [chunk.to_dict() for chunk in chunks],
        }
        return write_json_artifact(payload, self.chunk_manifest_path(source_id))

    def load_chunks(self, source_id: str) -> tuple[KnowledgeChunk, ...]:
        """Load schema-v2 evidence units for one source, returning empty when absent locally."""
        path = self.chunk_manifest_path(source_id)
        if not path.exists():
            return tuple()
        payload = _read_json(path)
        if payload.get("artifact_type") != "knowledge_evidence_unit_manifest":
            raise ValueError("legacy knowledge chunk manifest must be regenerated with evidence-unit ingestion")
        return tuple(KnowledgeChunk.from_dict(item) for item in _sequence(payload.get("evidence_units")))

    def list_chunks(self) -> tuple[KnowledgeChunk, ...]:
        """Load evidence units from every source manifest in deterministic file order for indexing."""
        if not self.chunk_dir.exists():
            return tuple()
        chunks: list[KnowledgeChunk] = []
        for path in sorted(self.chunk_dir.glob("*.json")):
            payload = _read_json(path)
            if payload.get("artifact_type") != "knowledge_evidence_unit_manifest":
                raise ValueError("legacy knowledge chunk manifest must be regenerated with evidence-unit ingestion")
            chunks.extend(KnowledgeChunk.from_dict(item) for item in _sequence(payload.get("evidence_units")))
        return tuple(chunks)

    def save_embedding_manifest(self, manifest: KnowledgeEmbeddingManifest) -> Path:
        """Persist embedding metadata for one indexing run and return its artifact path."""
        self.ensure_dirs()
        return write_json_artifact(manifest.to_dict(), self.embedding_path(manifest.embedding_manifest_id))

    def save_ingestion_report(self, report: KnowledgeIngestionReport) -> Path:
        """Persist an ingestion report and return the written artifact path for callers."""
        self.ensure_dirs()
        return write_json_artifact(report.to_dict(), self.ingestion_path(report.ingestion_id))

    def list_ingestion_reports(self) -> tuple[KnowledgeIngestionReport, ...]:
        """Load all ingestion reports from disk in deterministic filename order for status."""
        if not self.ingestion_dir.exists():
            return tuple()
        return tuple(
            KnowledgeIngestionReport.from_dict(_read_json(path))
            for path in sorted(self.ingestion_dir.glob("*.json"))
        )

    def save_index(self, entries: Sequence[Mapping[str, Any]]) -> Path:
        """Persist the JSON compatibility search index with entry-count metadata for retrieval."""
        self.ensure_dirs()
        payload = {
            "artifact_type": "knowledge_search_index",
            "entry_count": len(entries),
            "entries": list(entries),
        }
        return write_json_artifact(payload, self.index_path)

    def load_index_entries(self) -> tuple[Mapping[str, Any], ...]:
        """Load JSON compatibility search-index entries, returning empty when absent locally for retrieval."""
        if not self.index_path.exists():
            return tuple()
        payload = _read_json(self.index_path)
        return tuple(_mapping(item) for item in _sequence(payload.get("entries")))


    def save_method_card(self, method_card: MethodCard) -> Path:
        """Persist a method-card payload without dropping nullable methodology fields."""
        self.ensure_dirs()
        return write_json_artifact(method_card.to_dict(), self.method_card_path(method_card.method_card_id))

    def save_method_card_set(self, method_card_set: MethodCardSet) -> Path:
        """Persist a stable method-card set summary and return its artifact path."""
        self.ensure_dirs()
        return write_json_artifact(method_card_set.to_dict(), self.method_card_set_path(method_card_set.method_card_set_id))


    def list_persisted_method_cards(self) -> tuple[MethodCard, ...]:
        """Load canonical method-card payloads from disk."""
        if not self.method_card_dir.exists():
            return tuple()
        cards = []
        for path in sorted(self.method_card_dir.glob("*.json")):
            payload = _read_json(path)
            cards.append(MethodCard.from_dict(payload))
        return tuple(cards)

    def list_method_card_sets(self) -> tuple[MethodCardSet, ...]:
        """Load stable method-card set summaries from disk in deterministic order."""
        if not self.method_card_set_dir.exists():
            return tuple()
        return tuple(
            MethodCardSet.from_dict(_read_json(path)) for path in sorted(self.method_card_set_dir.glob("*.json"))
        )




def _read_json(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_artifact(payload: Mapping[str, Any], path: str | Path) -> Path:
    """Write a JSON artifact for the non-canonical local knowledge test adapter."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return output_path


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
