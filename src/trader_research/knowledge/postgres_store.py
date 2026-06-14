"""Research-layer adapter for the core Postgres knowledge record store."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence, TypeVar

from trader.knowledge_store import (
    PostgresKnowledgeEmbeddingDimensionError,
    PostgresKnowledgeRecordStore,
    PostgresKnowledgeStoreError,
    PostgresKnowledgeVectorExtensionUnavailable,
)
from trader_research.contracts import ArtifactReference

from .domain import KnowledgeChunk, KnowledgeEmbeddingManifest, KnowledgeIngestionReport, KnowledgeSourceManifest, MethodCard
from .store import (
    KnowledgeEmbeddingDimensionError,
    KnowledgeStoreError,
    KnowledgeVectorExtensionUnavailable,
    StoredEmbedding,
)


T = TypeVar("T")


class PostgresKnowledgeStore:
    """KnowledgeStore adapter backed by core Postgres persistence."""

    backend = "postgres"

    def __init__(
        self,
        *,
        dsn: str | None = None,
        host: str | None = None,
        port: int | None = None,
        dbname: str | None = None,
        user: str | None = None,
        password: str | None = None,
        ensure_schema: bool = True,
    ) -> None:
        self._records = _translate_errors(
            lambda: PostgresKnowledgeRecordStore(
                dsn=dsn,
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                ensure_schema=ensure_schema,
            )
        )

    def runtime_summary(self) -> Mapping[str, Any]:
        return _translate_errors(self._records.runtime_summary)

    def artifact_reference(self, artifact_type: str, artifact_id: str) -> ArtifactReference:
        return ArtifactReference(
            artifact_type=artifact_type,
            uri=f"knowledge://postgres/{artifact_type}/{artifact_id}",
            metadata={"id": artifact_id, "backend": self.backend},
        )

    def save_source(self, manifest: KnowledgeSourceManifest) -> None:
        _translate_errors(lambda: self._records.save_source(manifest.to_dict()))

    def load_source(self, source_id: str) -> KnowledgeSourceManifest | None:
        payload = _translate_errors(lambda: self._records.load_source(source_id))
        return KnowledgeSourceManifest.from_dict(payload) if payload is not None else None

    def list_sources(
        self,
        *,
        topic: str | None = None,
        method_family: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> tuple[KnowledgeSourceManifest, ...]:
        payloads = _translate_errors(
            lambda: self._records.list_sources(
                topic=topic,
                method_family=method_family,
                status=status,
                limit=limit,
            )
        )
        return tuple(KnowledgeSourceManifest.from_dict(payload) for payload in payloads)

    def find_sources_by_file_hash(self, file_hash: str) -> tuple[KnowledgeSourceManifest, ...]:
        payloads = _translate_errors(lambda: self._records.find_sources_by_file_hash(file_hash))
        return tuple(KnowledgeSourceManifest.from_dict(payload) for payload in payloads)

    def replace_chunks(self, source_id: str, chunks: Sequence[KnowledgeChunk]) -> None:
        _translate_errors(lambda: self._records.replace_chunks(source_id, [chunk.to_dict() for chunk in chunks]))

    def load_chunks(self, source_id: str) -> tuple[KnowledgeChunk, ...]:
        payloads = _translate_errors(lambda: self._records.load_chunks(source_id))
        return tuple(KnowledgeChunk.from_dict(payload) for payload in payloads)

    def list_chunks(self, *, source_ids: Sequence[str] | None = None) -> tuple[KnowledgeChunk, ...]:
        payloads = _translate_errors(lambda: self._records.list_chunks(source_ids=source_ids))
        return tuple(KnowledgeChunk.from_dict(payload) for payload in payloads)

    def load_chunks_by_ids(self, chunk_ids: Sequence[str]) -> tuple[KnowledgeChunk, ...]:
        payloads = _translate_errors(lambda: self._records.load_chunks_by_ids(chunk_ids))
        return tuple(KnowledgeChunk.from_dict(payload) for payload in payloads)

    def index_embeddings(
        self,
        manifest: KnowledgeEmbeddingManifest,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[StoredEmbedding],
    ) -> None:
        del chunks
        _translate_errors(
            lambda: self._records.index_embeddings(
                manifest.to_dict(),
                [{"chunk_id": embedding.chunk_id, "vector": list(embedding.vector)} for embedding in embeddings],
            )
        )

    def save_ingestion_report(self, report: KnowledgeIngestionReport) -> None:
        _translate_errors(lambda: self._records.save_ingestion_report(report.to_dict()))

    def list_ingestion_reports(
        self,
        *,
        source_ids: Sequence[str] | None = None,
        run_id: str | None = None,
    ) -> tuple[KnowledgeIngestionReport, ...]:
        payloads = _translate_errors(
            lambda: self._records.list_ingestion_reports(source_ids=source_ids, run_id=run_id)
        )
        return tuple(KnowledgeIngestionReport.from_dict(payload) for payload in payloads)

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
        return _translate_errors(
            lambda: self._records.search_lexical(
                query,
                source_ids=source_ids,
                topic=topic,
                method_family=method_family,
                approved_only=approved_only,
                limit=limit,
            )
        )

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
        return _translate_errors(
            lambda: self._records.search_vector(
                query_embedding,
                provider=provider,
                model=model,
                version=version,
                source_ids=source_ids,
                topic=topic,
                method_family=method_family,
                approved_only=approved_only,
                limit=limit,
            )
        )

    def save_method_card(self, method_card: MethodCard) -> None:
        _translate_errors(lambda: self._records.save_method_card(method_card.to_dict()))

    def list_persisted_method_cards(self) -> tuple[MethodCard, ...]:
        payloads = _translate_errors(self._records.list_persisted_method_cards)
        return tuple(MethodCard.from_dict(payload) for payload in payloads)

    def close(self) -> None:
        self._records.close()

    def connection(self) -> Any:
        return self._records.connection()


def _translate_errors(callback: Callable[[], T]) -> T:
    try:
        return callback()
    except PostgresKnowledgeVectorExtensionUnavailable as exc:
        raise KnowledgeVectorExtensionUnavailable(str(exc)) from exc
    except PostgresKnowledgeEmbeddingDimensionError as exc:
        raise KnowledgeEmbeddingDimensionError(str(exc)) from exc
    except PostgresKnowledgeStoreError as exc:
        raise KnowledgeStoreError(str(exc)) from exc
