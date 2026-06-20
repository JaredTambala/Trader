"""Research-layer adapter for the core Postgres knowledge record store."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence, TypeVar

from trader.knowledge.store import (
    PostgresKnowledgeEmbeddingDimensionError,
    PostgresKnowledgeRecordStore,
    PostgresKnowledgeStoreError,
    PostgresKnowledgeVectorExtensionUnavailable,
)
from trader_research.contracts import ArtifactReference
from trader_research.math_domain import MethodRegistryEntry

from .domain import KnowledgeChunk, KnowledgeEmbeddingManifest, KnowledgeIngestionReport, KnowledgeSourceManifest, MethodCard
from .store import (
    KnowledgeEmbeddingDimensionError,
    KnowledgeStoreError,
    KnowledgeVectorExtensionUnavailable,
    StoredEmbedding,
)


T = TypeVar("T")


class PostgresKnowledgeStore:
    """KnowledgeStore adapter that translates core Postgres records into research types.

    The adapter delegates persistence and search to `PostgresKnowledgeRecordStore`,
    converts JSON payloads back into the research-domain dataclasses, and maps core
    Postgres exceptions onto the knowledge-store error hierarchy. This keeps
    service code independent of database details while preserving pgvector and
    dimension failures as actionable typed errors.
    """

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
        """Return backend runtime metadata translated from the core Postgres record store."""
        return _translate_errors(self._records.runtime_summary)

    def artifact_reference(self, artifact_type: str, artifact_id: str) -> ArtifactReference:
        """Build a `knowledge://postgres` reference for a persisted knowledge record artifact URI."""
        return ArtifactReference(
            artifact_type=artifact_type,
            uri=f"knowledge://postgres/{artifact_type}/{artifact_id}",
            metadata={"id": artifact_id, "backend": self.backend},
        )

    def save_source(self, manifest: KnowledgeSourceManifest) -> None:
        """Persist a source manifest by converting it to the core JSON payload."""
        _translate_errors(lambda: self._records.save_source(manifest.to_dict()))

    def load_source(self, source_id: str) -> KnowledgeSourceManifest | None:
        """Load and parse one source manifest from Postgres by source identifier."""
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
        """List Postgres-backed source manifests after applying metadata filters and parsing payloads."""
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
        """Return Postgres-backed sources with a matching file hash digest for duplicates."""
        payloads = _translate_errors(lambda: self._records.find_sources_by_file_hash(file_hash))
        return tuple(KnowledgeSourceManifest.from_dict(payload) for payload in payloads)

    def replace_chunks(self, source_id: str, chunks: Sequence[KnowledgeChunk]) -> None:
        """Replace active Postgres chunks for one source using typed chunk payloads."""
        _translate_errors(lambda: self._records.replace_chunks(source_id, [chunk.to_dict() for chunk in chunks]))

    def load_chunks(self, source_id: str) -> tuple[KnowledgeChunk, ...]:
        """Load active chunks for one source and parse them into domain objects."""
        payloads = _translate_errors(lambda: self._records.load_chunks(source_id))
        return tuple(KnowledgeChunk.from_dict(payload) for payload in payloads)

    def list_chunks(self, *, source_ids: Sequence[str] | None = None) -> tuple[KnowledgeChunk, ...]:
        """List active chunks from Postgres, optionally filtered by source identifiers for retrieval."""
        payloads = _translate_errors(lambda: self._records.list_chunks(source_ids=source_ids))
        return tuple(KnowledgeChunk.from_dict(payload) for payload in payloads)

    def load_chunks_by_ids(self, chunk_ids: Sequence[str]) -> tuple[KnowledgeChunk, ...]:
        """Load active chunks by stable ID and preserve the record-store ordering."""
        payloads = _translate_errors(lambda: self._records.load_chunks_by_ids(chunk_ids))
        return tuple(KnowledgeChunk.from_dict(payload) for payload in payloads)

    def index_embeddings(
        self,
        manifest: KnowledgeEmbeddingManifest,
        chunks: Sequence[KnowledgeChunk],
        embeddings: Sequence[StoredEmbedding],
    ) -> None:
        """Persist embedding vectors through the core Postgres record store.

        The adapter discards `chunks` because the core store already receives
        chunk IDs with each vector, then serializes vectors to plain lists for SQL
        binding.
        """
        del chunks
        _translate_errors(
            lambda: self._records.index_embeddings(
                manifest.to_dict(),
                [{"chunk_id": embedding.chunk_id, "vector": list(embedding.vector)} for embedding in embeddings],
            )
        )

    def save_ingestion_report(self, report: KnowledgeIngestionReport) -> None:
        """Persist an ingestion report by converting it to a core JSON payload."""
        _translate_errors(lambda: self._records.save_ingestion_report(report.to_dict()))

    def list_ingestion_reports(
        self,
        *,
        source_ids: Sequence[str] | None = None,
        run_id: str | None = None,
    ) -> tuple[KnowledgeIngestionReport, ...]:
        """List Postgres-backed ingestion reports and parse them into domain objects for status."""
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
        """Run lexical retrieval in Postgres and return normalized result mappings for fusion."""
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
        """Run pgvector retrieval in Postgres and return normalized result mappings for fusion."""
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
        """Persist a method card through the core Postgres record store adapter."""
        _translate_errors(lambda: self._records.save_method_card(method_card.to_dict()))

    def list_persisted_method_cards(self) -> tuple[MethodCard, ...]:
        """List persisted method cards from Postgres and parse each payload into domain objects."""
        payloads = _translate_errors(self._records.list_persisted_method_cards)
        return tuple(MethodCard.from_dict(payload) for payload in payloads)

    def save_method_contract(self, method: MethodRegistryEntry) -> None:
        """Persist a method contract through the core Postgres record store adapter."""
        _translate_errors(lambda: self._records.save_method_contract(method.to_dict()))

    def list_persisted_method_contracts(self) -> tuple[MethodRegistryEntry, ...]:
        """List persisted method contracts from Postgres and parse each payload into domain objects."""
        payloads = _translate_errors(self._records.list_persisted_method_contracts)
        return tuple(MethodRegistryEntry.from_dict(payload) for payload in payloads)

    def close(self) -> None:
        """Close the wrapped core Postgres knowledge record store connection after use."""
        self._records.close()

    def connection(self) -> Any:
        """Expose the wrapped core Postgres connection for integration utilities and tests."""
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
