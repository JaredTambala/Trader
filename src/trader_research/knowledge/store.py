"""Knowledge-store abstraction for Quant Methods evidence retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from trader_research.contracts import ArtifactReference

from .domain import KnowledgeChunk, KnowledgeEmbeddingManifest, KnowledgeIngestionReport, KnowledgeSourceManifest, MethodCard
from .embeddings import TOKEN_PATTERN, cosine_similarity
from .storage import KnowledgeRepository


class KnowledgeStoreError(RuntimeError):
    """Base error for knowledge-store failures."""


class KnowledgeStoreUnavailable(KnowledgeStoreError):
    """Raised when no usable knowledge store is configured."""


class KnowledgeVectorExtensionUnavailable(KnowledgeStoreError):
    """Raised when pgvector is required but unavailable."""


class KnowledgeEmbeddingDimensionError(KnowledgeStoreError):
    """Raised when stored and query embedding dimensions do not match."""


@dataclass(frozen=True)
class StoredEmbedding:
    """Embedding vector associated with one chunk."""

    chunk_id: str
    vector: tuple[float, ...]


class KnowledgeStore(Protocol):
    """Storage boundary used by knowledge services."""

    backend: str

    def runtime_summary(self) -> Mapping[str, Any]:
        """Return non-secret runtime details for MCP config."""

    def artifact_reference(self, artifact_type: str, artifact_id: str) -> ArtifactReference:
        """Return an artifact reference for a persisted knowledge record."""

    def save_source(self, manifest: KnowledgeSourceManifest) -> None:
        """Persist or update a source manifest."""

    def load_source(self, source_id: str) -> KnowledgeSourceManifest | None:
        """Load one source manifest."""

    def list_sources(
        self,
        *,
        topic: str | None = None,
        method_family: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> tuple[KnowledgeSourceManifest, ...]:
        """List source manifests with optional filters."""

    def find_sources_by_file_hash(self, file_hash: str) -> tuple[KnowledgeSourceManifest, ...]:
        """Return sources with a matching file hash."""

    def replace_chunks(self, source_id: str, chunks: Sequence[KnowledgeChunk]) -> None:
        """Replace active chunks for a source."""

    def load_chunks(self, source_id: str) -> tuple[KnowledgeChunk, ...]:
        """Load active chunks for one source."""

    def list_chunks(self, *, source_ids: Sequence[str] | None = None) -> tuple[KnowledgeChunk, ...]:
        """List active chunks."""

    def load_chunks_by_ids(self, chunk_ids: Sequence[str]) -> tuple[KnowledgeChunk, ...]:
        """Load active chunks by stable chunk ID."""

    def index_embeddings(
        self,
        manifest: KnowledgeEmbeddingManifest,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[StoredEmbedding],
    ) -> None:
        """Persist one embedding index manifest and its chunk vectors."""

    def save_ingestion_report(self, report: KnowledgeIngestionReport) -> None:
        """Persist an ingestion report."""

    def list_ingestion_reports(
        self,
        *,
        source_ids: Sequence[str] | None = None,
        run_id: str | None = None,
    ) -> tuple[KnowledgeIngestionReport, ...]:
        """List ingestion reports."""

    def search_lexical(
        self,
        query: str,
        *,
        source_ids: Sequence[str] | None = None,
        topic: str | None = None,
        method_family: str | None = None,
        approved_only: bool = True,
        limit: int = 50,
    ) -> tuple[Mapping[str, Any], ...]:
        """Return lexical chunk matches ordered by relevance."""

    def search_vector(
        self,
        query_embedding: Sequence[float],
        *,
        provider: str,
        model: str,
        version: str,
        source_ids: Sequence[str] | None = None,
        topic: str | None = None,
        method_family: str | None = None,
        approved_only: bool = True,
        limit: int = 50,
    ) -> tuple[Mapping[str, Any], ...]:
        """Return vector chunk matches ordered by relevance."""

    def save_method_card(self, method_card: MethodCard) -> None:
        """Persist a method card."""

    def list_persisted_method_cards(self) -> tuple[MethodCard, ...]:
        """List persisted method cards."""


class JsonKnowledgeStore:
    """Compatibility store backed by the existing local JSON repository."""

    backend = "json"

    def __init__(self, artifact_root: str | Path, *, allowed_roots: Sequence[str | Path] | None = None) -> None:
        self.repository = KnowledgeRepository(artifact_root, allowed_roots=allowed_roots)

    def runtime_summary(self) -> Mapping[str, Any]:
        return {
            "backend": self.backend,
            "configured": True,
            "artifact_root": str(self.repository.artifact_root),
            "pgvector_available": None,
        }

    def artifact_reference(self, artifact_type: str, artifact_id: str) -> ArtifactReference:
        path_by_type = {
            "knowledge_source_manifest": self.repository.source_path,
            "knowledge_ingestion_report": self.repository.ingestion_path,
            "knowledge_embedding_manifest": self.repository.embedding_path,
            "method_card": self.repository.method_card_path,
        }
        path_factory = path_by_type.get(artifact_type)
        return ArtifactReference(
            artifact_type=artifact_type,
            path=path_factory(artifact_id) if path_factory is not None else None,
            uri=f"knowledge://json/{artifact_type}/{artifact_id}",
            metadata={"id": artifact_id, "backend": self.backend},
        )

    def save_source(self, manifest: KnowledgeSourceManifest) -> None:
        self.repository.save_source(manifest)

    def load_source(self, source_id: str) -> KnowledgeSourceManifest | None:
        return self.repository.load_source(source_id)

    def list_sources(
        self,
        *,
        topic: str | None = None,
        method_family: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> tuple[KnowledgeSourceManifest, ...]:
        sources = []
        for source in self.repository.list_sources():
            if topic and topic not in source.topics:
                continue
            if method_family and method_family not in source.method_families:
                continue
            if status and source.status != status:
                continue
            sources.append(source)
        return tuple(sources[:limit] if limit is not None else sources)

    def find_sources_by_file_hash(self, file_hash: str) -> tuple[KnowledgeSourceManifest, ...]:
        return tuple(source for source in self.repository.list_sources() if source.file_hash == file_hash)

    def replace_chunks(self, source_id: str, chunks: Sequence[KnowledgeChunk]) -> None:
        self.repository.save_chunks(source_id, chunks)
        active_chunk_ids = {chunk.chunk_id for chunk in chunks}
        retained_entries = [
            entry
            for entry in self.repository.load_index_entries()
            if str(entry.get("source_id") or "") != source_id or str(entry.get("chunk_id") or "") in active_chunk_ids
        ]
        self.repository.save_index(tuple(retained_entries))

    def load_chunks(self, source_id: str) -> tuple[KnowledgeChunk, ...]:
        return self.repository.load_chunks(source_id)

    def list_chunks(self, *, source_ids: Sequence[str] | None = None) -> tuple[KnowledgeChunk, ...]:
        source_filter = {str(source_id) for source_id in source_ids or ()}
        chunks = self.repository.list_chunks()
        if not source_filter:
            return chunks
        return tuple(chunk for chunk in chunks if chunk.source_id in source_filter)

    def load_chunks_by_ids(self, chunk_ids: Sequence[str]) -> tuple[KnowledgeChunk, ...]:
        requested = tuple(dict.fromkeys(str(chunk_id).strip() for chunk_id in chunk_ids if str(chunk_id).strip()))
        if not requested:
            return tuple()
        by_chunk_id = {chunk.chunk_id: chunk for chunk in self.repository.list_chunks()}
        return tuple(by_chunk_id[chunk_id] for chunk_id in requested if chunk_id in by_chunk_id)

    def index_embeddings(
        self,
        manifest: KnowledgeEmbeddingManifest,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[StoredEmbedding],
    ) -> None:
        existing = {str(entry.get("chunk_id")): dict(entry) for entry in self.repository.load_index_entries()}
        by_chunk_id = {embedding.chunk_id: embedding.vector for embedding in embeddings}
        for chunk in chunks:
            existing[chunk.chunk_id] = {
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "ordinal": chunk.ordinal,
                "text": chunk.text,
                "text_hash": chunk.text_hash,
                "locator": dict(chunk.locator),
                "topics": list(chunk.topics),
                "method_families": list(chunk.method_families),
                "embedding": list(by_chunk_id[chunk.chunk_id]),
                "embedding_provider": manifest.provider,
                "embedding_model": manifest.model,
                "embedding_version": manifest.version,
                "embedding_manifest_id": manifest.embedding_manifest_id,
                "embedding_dimension": manifest.dimension,
            }
        self.repository.save_index(tuple(existing.values()))
        self.repository.save_embedding_manifest(manifest)

    def save_ingestion_report(self, report: KnowledgeIngestionReport) -> None:
        self.repository.save_ingestion_report(report)

    def list_ingestion_reports(
        self,
        *,
        source_ids: Sequence[str] | None = None,
        run_id: str | None = None,
    ) -> tuple[KnowledgeIngestionReport, ...]:
        source_filter = {str(source_id) for source_id in source_ids or ()}
        reports = []
        for report in self.repository.list_ingestion_reports():
            if run_id and report.ingestion_id != run_id:
                continue
            if source_filter and not source_filter.intersection(report.source_ids):
                continue
            reports.append(report)
        return tuple(reports)

    def search_lexical(
        self,
        query: str,
        *,
        source_ids: Sequence[str] | None = None,
        topic: str | None = None,
        method_family: str | None = None,
        approved_only: bool = True,
        limit: int = 50,
    ) -> tuple[Mapping[str, Any], ...]:
        query_tokens = tuple(TOKEN_PATTERN.findall(query.lower()))
        if not query_tokens:
            return tuple()
        results = []
        for entry in self._filtered_index_entries(
            source_ids=source_ids,
            topic=topic,
            method_family=method_family,
            approved_only=approved_only,
        ):
            text = str(entry.get("text") or "")
            text_lower = text.lower()
            score = float(sum(text_lower.count(token) for token in query_tokens))
            if score <= 0.0:
                continue
            results.append(self._result_from_index_entry(entry, score=score))
        results.sort(key=lambda result: (-float(result["score"]), str(result["chunk_id"])))
        return tuple(results[:limit])

    def search_vector(
        self,
        query_embedding: Sequence[float],
        *,
        provider: str,
        model: str,
        version: str,
        source_ids: Sequence[str] | None = None,
        topic: str | None = None,
        method_family: str | None = None,
        approved_only: bool = True,
        limit: int = 50,
    ) -> tuple[Mapping[str, Any], ...]:
        query_vector = tuple(float(value) for value in query_embedding)
        results = []
        for entry in self._filtered_index_entries(
            source_ids=source_ids,
            topic=topic,
            method_family=method_family,
            approved_only=approved_only,
        ):
            if str(entry.get("embedding_provider") or "") != provider:
                continue
            if str(entry.get("embedding_model") or "") != model:
                continue
            if str(entry.get("embedding_version") or "") != version:
                continue
            embedding = tuple(float(value) for value in entry.get("embedding") or ())
            if len(embedding) != len(query_vector):
                raise KnowledgeEmbeddingDimensionError(
                    f"query dimension {len(query_vector)} does not match stored dimension {len(embedding)}"
                )
            score = cosine_similarity(query_vector, embedding)
            results.append(self._result_from_index_entry(entry, score=score))
        results.sort(key=lambda result: (-float(result["score"]), str(result["chunk_id"])))
        return tuple(results[:limit])

    def save_method_card(self, method_card: MethodCard) -> None:
        self.repository.save_method_card(method_card)

    def list_persisted_method_cards(self) -> tuple[MethodCard, ...]:
        return self.repository.list_persisted_method_cards()

    def _filtered_index_entries(
        self,
        *,
        source_ids: Sequence[str] | None,
        topic: str | None,
        method_family: str | None,
        approved_only: bool,
    ) -> tuple[Mapping[str, Any], ...]:
        source_filter = {str(source_id) for source_id in source_ids or ()}
        entries = []
        for entry in self.repository.load_index_entries():
            source_id = str(entry.get("source_id") or "")
            if source_filter and source_id not in source_filter:
                continue
            if topic and topic not in tuple(entry.get("topics") or ()):
                continue
            if method_family and method_family not in tuple(entry.get("method_families") or ()):
                continue
            source = self.repository.load_source(source_id)
            if source is None or not _source_status_allowed(source.status, approved_only=approved_only):
                continue
            enriched = dict(entry)
            enriched["source_title"] = source.title
            enriched["source_type"] = source.source_type
            enriched["source_status"] = source.status
            entries.append(enriched)
        return tuple(entries)

    def _result_from_index_entry(self, entry: Mapping[str, Any], *, score: float) -> Mapping[str, Any]:
        text = str(entry.get("text") or "")
        return {
            "source_id": entry.get("source_id"),
            "source_title": entry.get("source_title"),
            "source_type": entry.get("source_type"),
            "source_status": entry.get("source_status"),
            "approved_source": entry.get("source_status") == "approved",
            "chunk_id": entry.get("chunk_id"),
            "locator": entry.get("locator"),
            "score": score,
            "excerpt": text[:360],
            "text_hash": entry.get("text_hash"),
        }


class UnavailableKnowledgeStore:
    """Knowledge store used when the MCP runtime has no configured backend."""

    backend = "unavailable"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def runtime_summary(self) -> Mapping[str, Any]:
        return {
            "backend": self.backend,
            "configured": False,
            "reason": self.reason,
            "pgvector_available": None,
        }

    def __getattr__(self, name: str) -> Any:
        raise KnowledgeStoreUnavailable(self.reason)


def _source_status_allowed(status: str, *, approved_only: bool) -> bool:
    normalized = status.strip().lower()
    if normalized in {"rejected", "superseded"}:
        return False
    if not approved_only:
        return True
    return normalized in {"approved", "registered", "pending"}
