"""Postgres persistence for Quant Methods knowledge records.

The store owns schema creation, source/chunk persistence, method metadata, and
lexical/vector retrieval SQL for research workflows. Keeping this adapter in the
knowledge package separates database-specific retrieval mechanics from the
top-level trading runtime modules.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .records import (
    mapping as _mapping,
    result_from_row as _result_from_row,
    string_list as _string_list,
    vector_literal as _vector_literal,
)
from .schema import KNOWLEDGE_SCHEMA_STATEMENTS

try:  # pragma: no cover - exercised by postgres integration tests
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - import guard
    psycopg = None
    dict_row = None
    Jsonb = None


class PostgresKnowledgeStoreError(RuntimeError):
    """Base exception for knowledge-store persistence and retrieval failures.

    Callers can catch this type for store-level failures without swallowing
    unrelated runtime errors.
    """


class PostgresKnowledgeVectorExtensionUnavailable(PostgresKnowledgeStoreError):
    """Raised when vector search is requested before pgvector is installed.

    The store can persist lexical metadata without pgvector, but vector queries
    require the extension to exist in the connected database.
    """


class PostgresKnowledgeEmbeddingDimensionError(PostgresKnowledgeStoreError):
    """Raised when query embeddings cannot be compared to stored vectors.

    This protects ranking code from silently comparing vectors with incompatible
    dimensions.
    """


class PostgresKnowledgeRecordStore:
    """Postgres repository for knowledge sources, chunks, and retrieval metadata.

    The store owns schema creation, deduplicated source/chunk persistence, and
    lexical/vector retrieval queries used by research workflows. It keeps SQL in
    this adapter so higher-level callers operate on mappings rather than
    connection-specific cursor details.
    """

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
        if psycopg is None:
            raise ImportError("psycopg is required to use PostgresKnowledgeRecordStore")
        if dsn:
            self._connection = psycopg.connect(dsn, row_factory=dict_row)
        else:
            self._connection = psycopg.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
                row_factory=dict_row,
            )
        self._connection.autocommit = True
        if ensure_schema:
            self.ensure_schema()

    def ensure_schema(self) -> None:
        """Create knowledge tables, indexes, and pgvector support when permitted.

        Schema setup installs pgvector if possible, creates source, chunk,
        embedding, ingestion, method-card, and method-contract tables, and adds the
        indexes used by lexical and filtered retrieval. Driver errors are wrapped
        in `PostgresKnowledgeStoreError` so service layers see one store boundary.
        """
        self._ensure_pgvector()
        try:
            with self._connection.cursor() as cursor:
                for statement in KNOWLEDGE_SCHEMA_STATEMENTS:
                    cursor.execute(statement)
        except Exception as exc:  # pragma: no cover - driver-specific details
            raise PostgresKnowledgeStoreError(f"failed to initialize knowledge schema: {exc}") from exc

    def runtime_summary(self) -> Mapping[str, Any]:
        """Return non-secret runtime metadata for MCP health and configuration output.

        The summary reports backend type, configured status, pgvector availability,
        and schema name without exposing connection strings or credentials.
        """
        return {
            "backend": "postgres",
            "configured": True,
            "pgvector_available": self.pgvector_available(),
            "schema": "public",
        }

    def pgvector_available(self) -> bool:
        """Return whether the connected database currently has pgvector installed for vector search."""
        row = self._connection.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS ok").fetchone()
        return bool(row and row["ok"])

    def save_source(self, payload: Mapping[str, Any]) -> None:
        """Insert or update one source manifest and its queryable metadata columns.

        The JSON payload is persisted intact while selected fields are also stored
        in typed columns for filtering by file hash, status, topics, and method
        families. Existing source IDs are updated in place.
        """
        self._connection.execute(
            """
            INSERT INTO knowledge_sources (
                source_id, title, source_type, path, file_hash, file_size_bytes, access_policy,
                topics, method_families, canonical_citation, status, duplicate_source_ids,
                warnings, created_at, schema_version, payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE SET
                title = EXCLUDED.title,
                source_type = EXCLUDED.source_type,
                path = EXCLUDED.path,
                file_hash = EXCLUDED.file_hash,
                file_size_bytes = EXCLUDED.file_size_bytes,
                access_policy = EXCLUDED.access_policy,
                topics = EXCLUDED.topics,
                method_families = EXCLUDED.method_families,
                canonical_citation = EXCLUDED.canonical_citation,
                status = EXCLUDED.status,
                duplicate_source_ids = EXCLUDED.duplicate_source_ids,
                warnings = EXCLUDED.warnings,
                payload = EXCLUDED.payload
            """,
            [
                payload["source_id"],
                payload["title"],
                payload["source_type"],
                payload["path"],
                payload["file_hash"],
                int(payload["file_size_bytes"]),
                payload["access_policy"],
                _string_list(payload.get("topics")),
                _string_list(payload.get("method_families")),
                payload.get("canonical_citation"),
                payload["status"],
                _string_list(payload.get("duplicate_source_ids")),
                _string_list(payload.get("warnings")),
                payload["created_at"],
                payload["schema_version"],
                Jsonb(dict(payload)),
            ],
        )

    def load_source(self, source_id: str) -> Mapping[str, Any] | None:
        """Load one stored source payload by ID, returning `None` when absent from storage."""
        row = self._connection.execute("SELECT payload FROM knowledge_sources WHERE source_id = %s", [source_id]).fetchone()
        return _mapping(row["payload"]) if row is not None else None

    def list_sources(
        self,
        *,
        topic: str | None = None,
        method_family: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        """List source payloads filtered by topic, method family, status, and limit.

        Filters are pushed into indexed Postgres columns and results are returned in
        deterministic source-ID order. The returned mappings are the original JSON
        source manifests.
        """
        where = []
        params: list[Any] = []
        if topic:
            where.append("%s = ANY(topics)")
            params.append(topic)
        if method_family:
            where.append("%s = ANY(method_families)")
            params.append(method_family)
        if status:
            where.append("status = %s")
            params.append(status)
        sql = "SELECT payload FROM knowledge_sources"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY source_id"
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        rows = self._connection.execute(sql, params).fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

    def find_sources_by_file_hash(self, file_hash: str) -> tuple[Mapping[str, Any], ...]:
        """Return source manifests with the same file hash for duplicate-source detection."""
        rows = self._connection.execute(
            "SELECT payload FROM knowledge_sources WHERE file_hash = %s ORDER BY source_id",
            [file_hash],
        ).fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

    def replace_chunks(self, source_id: str, chunks: Sequence[Mapping[str, Any]]) -> None:
        """Replace active chunks for a source inside one transaction.

        Existing chunks for the source are marked inactive before the new chunk
        payloads are inserted or updated and reactivated. This preserves historical
        rows while ensuring retrieval only sees the latest active chunk set.
        """
        with self._connection.transaction():
            self._connection.execute("UPDATE knowledge_chunks SET active = FALSE WHERE source_id = %s", [source_id])
            for chunk in chunks:
                self._connection.execute(
                    """
                    INSERT INTO knowledge_chunks (
                        chunk_id, source_id, ordinal, text, text_hash, locator,
                        topics, method_families, evidence_unit_id, parent_section_id,
                        paragraph_index, sentence_start_index, sentence_end_index,
                        detected_labels, neighbor_chunk_ids, chunker_version,
                        schema_version, active, payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        ordinal = EXCLUDED.ordinal,
                        text = EXCLUDED.text,
                        text_hash = EXCLUDED.text_hash,
                        locator = EXCLUDED.locator,
                        topics = EXCLUDED.topics,
                        method_families = EXCLUDED.method_families,
                        evidence_unit_id = EXCLUDED.evidence_unit_id,
                        parent_section_id = EXCLUDED.parent_section_id,
                        paragraph_index = EXCLUDED.paragraph_index,
                        sentence_start_index = EXCLUDED.sentence_start_index,
                        sentence_end_index = EXCLUDED.sentence_end_index,
                        detected_labels = EXCLUDED.detected_labels,
                        neighbor_chunk_ids = EXCLUDED.neighbor_chunk_ids,
                        chunker_version = EXCLUDED.chunker_version,
                        schema_version = EXCLUDED.schema_version,
                        active = TRUE,
                        payload = EXCLUDED.payload
                    """,
                    [
                        chunk["chunk_id"],
                        chunk["source_id"],
                        int(chunk["ordinal"]),
                        chunk["text"],
                        chunk["text_hash"],
                        Jsonb(_mapping(chunk.get("locator"))),
                        _string_list(chunk.get("topics")),
                        _string_list(chunk.get("method_families")),
                        chunk.get("evidence_unit_id") or chunk.get("chunk_id"),
                        chunk.get("parent_section_id"),
                        chunk.get("paragraph_index"),
                        chunk.get("sentence_start_index"),
                        chunk.get("sentence_end_index"),
                        _string_list(chunk.get("detected_labels")),
                        _string_list(chunk.get("neighbor_chunk_ids")),
                        chunk.get("chunker_version"),
                        chunk.get("schema_version"),
                        Jsonb(dict(chunk)),
                    ],
                )

    def load_chunks(self, source_id: str) -> tuple[Mapping[str, Any], ...]:
        """Load active chunk payloads for one source in deterministic ordinal order."""
        rows = self._connection.execute(
            """
            SELECT payload
            FROM knowledge_chunks
            WHERE source_id = %s AND active = TRUE
            ORDER BY ordinal, chunk_id
            """,
            [source_id],
        ).fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

    def list_chunks(self, *, source_ids: Sequence[str] | None = None) -> tuple[Mapping[str, Any], ...]:
        """List active chunk payloads, optionally restricted to specific sources.

        Results are ordered by source, ordinal, and chunk ID so callers receive a
        stable traversal of the active knowledge corpus.
        """
        params: list[Any] = []
        where = ["active = TRUE"]
        if source_ids:
            where.append("source_id = ANY(%s)")
            params.append(list(source_ids))
        rows = self._connection.execute(
            f"SELECT payload FROM knowledge_chunks WHERE {' AND '.join(where)} ORDER BY source_id, ordinal, chunk_id",
            params,
        ).fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

    def load_chunks_by_ids(self, chunk_ids: Sequence[str]) -> tuple[Mapping[str, Any], ...]:
        """Load active chunks by ID while preserving requested order and de-duplicating IDs.

        Empty or blank IDs are ignored, missing IDs are omitted, and returned
        payloads follow the caller's first-occurrence ordering.
        """
        requested = list(dict.fromkeys(str(chunk_id).strip() for chunk_id in chunk_ids if str(chunk_id).strip()))
        if not requested:
            return tuple()
        rows = self._connection.execute(
            """
            SELECT payload
            FROM knowledge_chunks
            WHERE active = TRUE AND chunk_id = ANY(%s)
            """,
            [requested],
        ).fetchall()
        by_chunk_id = {str(row["payload"].get("chunk_id") or ""): _mapping(row["payload"]) for row in rows}
        return tuple(by_chunk_id[chunk_id] for chunk_id in requested if chunk_id in by_chunk_id)

    def index_embeddings(
        self,
        manifest: Mapping[str, Any],
        embeddings: Sequence[Mapping[str, Any]],
    ) -> None:
        """Persist one embedding manifest and the vectors for its chunks.

        The manifest row is inserted idempotently, each vector is checked against
        the manifest dimension, and vectors are upserted under the
        manifest/chunk primary key. Dimension mismatches raise a typed store error
        before invalid vectors reach pgvector.
        """
        with self._connection.transaction():
            self._connection.execute(
                """
                INSERT INTO knowledge_embedding_indexes (
                    embedding_manifest_id, provider, model, version, dimension,
                    distance_metric, chunk_ids, created_at, schema_version, payload
                )
                VALUES (%s, %s, %s, %s, %s, 'cosine', %s, %s, %s, %s)
                ON CONFLICT (embedding_manifest_id) DO NOTHING
                """,
                [
                    manifest["embedding_manifest_id"],
                    manifest["provider"],
                    manifest["model"],
                    manifest["version"],
                    int(manifest["dimension"]),
                    _string_list(manifest.get("chunk_ids")),
                    manifest["created_at"],
                    manifest["schema_version"],
                    Jsonb(dict(manifest)),
                ],
            )
            for embedding in embeddings:
                vector = tuple(float(value) for value in embedding["vector"])
                if len(vector) != int(manifest["dimension"]):
                    raise PostgresKnowledgeEmbeddingDimensionError(
                        f"chunk {embedding['chunk_id']} dimension {len(vector)} does not match manifest dimension {manifest['dimension']}"
                    )
                self._connection.execute(
                    """
                    INSERT INTO knowledge_embeddings (
                        embedding_manifest_id, chunk_id, provider, model, version, dimension, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (embedding_manifest_id, chunk_id) DO UPDATE SET
                        provider = EXCLUDED.provider,
                        model = EXCLUDED.model,
                        version = EXCLUDED.version,
                        dimension = EXCLUDED.dimension,
                        embedding = EXCLUDED.embedding
                    """,
                    [
                        manifest["embedding_manifest_id"],
                        embedding["chunk_id"],
                        manifest["provider"],
                        manifest["model"],
                        manifest["version"],
                        int(manifest["dimension"]),
                        _vector_literal(vector),
                    ],
                )

    def save_ingestion_report(self, payload: Mapping[str, Any]) -> None:
        """Insert or update an ingestion report and its queryable status summary columns."""
        self._connection.execute(
            """
            INSERT INTO knowledge_ingestion_runs (
                ingestion_id, source_ids, status, chunks_created, chunks_indexed,
                embedding_manifest_id, warnings, blockers, created_at, schema_version, payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ingestion_id) DO UPDATE SET
                source_ids = EXCLUDED.source_ids,
                status = EXCLUDED.status,
                chunks_created = EXCLUDED.chunks_created,
                chunks_indexed = EXCLUDED.chunks_indexed,
                embedding_manifest_id = EXCLUDED.embedding_manifest_id,
                warnings = EXCLUDED.warnings,
                blockers = EXCLUDED.blockers,
                payload = EXCLUDED.payload
            """,
            [
                payload["ingestion_id"],
                _string_list(payload.get("source_ids")),
                payload["status"],
                int(payload["chunks_created"]),
                int(payload["chunks_indexed"]),
                payload.get("embedding_manifest_id"),
                _string_list(payload.get("warnings")),
                _string_list(payload.get("blockers")),
                payload["created_at"],
                payload["schema_version"],
                Jsonb(dict(payload)),
            ],
        )

    def publish_ingestion(
        self,
        replacements: Mapping[str, Sequence[Mapping[str, Any]]],
        embedding_manifest: Mapping[str, Any],
        embeddings: Sequence[Mapping[str, Any]],
        ingestion_report: Mapping[str, Any],
    ) -> None:
        """Publish chunks, vectors, and the indexed report in one transaction.

        The existing write methods open nested transaction contexts, which
        psycopg implements as savepoints. Any failure escapes this outer context
        and rolls back the entire generation, leaving the prior active chunks and
        retrieval index visible.
        """
        with self._connection.transaction():
            for source_id, chunks in replacements.items():
                self.replace_chunks(source_id, chunks)
            self.index_embeddings(embedding_manifest, embeddings)
            self.save_ingestion_report(ingestion_report)

    def list_ingestion_reports(
        self,
        *,
        source_ids: Sequence[str] | None = None,
        run_id: str | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        """List ingestion reports filtered by source overlap or exact run ID.

        Reports are returned as their original JSON payloads in creation order so
        status tools can reconstruct source-processing history.
        """
        where = []
        params: list[Any] = []
        if run_id:
            where.append("ingestion_id = %s")
            params.append(run_id)
        if source_ids:
            where.append("source_ids && %s")
            params.append(list(source_ids))
        sql = "SELECT payload FROM knowledge_ingestion_runs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at, ingestion_id"
        rows = self._connection.execute(sql, params).fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

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
        """Search active chunks using Postgres full-text ranking and source filters.

        The query uses generated `tsvector` data, applies source/topic/family/status
        filters, and returns normalized retrieval rows with source metadata,
        locator, score, excerpt, and text hash.
        """
        where, params = self._search_filters(
            source_ids=source_ids,
            topic=topic,
            method_family=method_family,
            approved_only=approved_only,
        )
        sql = f"""
            SELECT
                c.chunk_id, c.source_id, c.text, c.text_hash, c.locator,
                c.evidence_unit_id, c.detected_labels, c.neighbor_chunk_ids, c.chunker_version,
                s.title AS source_title, s.source_type, s.status AS source_status,
                ts_rank_cd(c.search_vector, plainto_tsquery('english', %s)) AS score
            FROM knowledge_chunks c
            JOIN knowledge_sources s ON s.source_id = c.source_id
            WHERE {' AND '.join(where)}
              AND c.search_vector @@ plainto_tsquery('english', %s)
            ORDER BY score DESC, c.chunk_id
            LIMIT %s
        """
        rows = self._connection.execute(sql, [query, *params, query, limit]).fetchall()
        return tuple(_result_from_row(row) for row in rows)

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
        """Search active chunks by pgvector distance for a provider/model/version.

        The query embedding is dimension-checked against stored vectors before SQL
        execution, then pgvector cosine distance is converted to a similarity score
        and combined with the same source filters used by lexical search.
        """
        vector = tuple(float(value) for value in query_embedding)
        self._validate_vector_dimension(vector, provider=provider, model=model, version=version)
        where, params = self._search_filters(
            source_ids=source_ids,
            topic=topic,
            method_family=method_family,
            approved_only=approved_only,
        )
        sql = f"""
            SELECT
                c.chunk_id, c.source_id, c.text, c.text_hash, c.locator,
                c.evidence_unit_id, c.detected_labels, c.neighbor_chunk_ids, c.chunker_version,
                s.title AS source_title, s.source_type, s.status AS source_status,
                1.0 - (e.embedding <=> %s::vector) AS score
            FROM knowledge_embeddings e
            JOIN knowledge_chunks c ON c.chunk_id = e.chunk_id
            JOIN knowledge_sources s ON s.source_id = c.source_id
            WHERE {' AND '.join(where)}
              AND e.provider = %s
              AND e.model = %s
              AND e.version = %s
              AND e.dimension = %s
            ORDER BY e.embedding <=> %s::vector ASC, c.chunk_id
            LIMIT %s
        """
        rows = self._connection.execute(
            sql,
            [
                _vector_literal(vector),
                *params,
                provider,
                model,
                version,
                len(vector),
                _vector_literal(vector),
                limit,
            ],
        ).fetchall()
        return tuple(_result_from_row(row) for row in rows)

    def save_method_card(self, payload: Mapping[str, Any]) -> None:
        """Insert or update one persisted method-card payload keyed by method-card ID."""
        validation_refs = payload.get("validation_refs")
        validation_refs_payload = (
            list(validation_refs)
            if isinstance(validation_refs, Sequence) and not isinstance(validation_refs, (str, bytes))
            else []
        )
        self._connection.execute(
            """
            INSERT INTO knowledge_method_cards (
                method_card_id, method_card_set_id, method_id, family, status, card_format,
                revision_number, supersedes_method_card_id, source_methodology_candidate_id,
                validation_refs, created_at, payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (method_card_id) DO UPDATE SET
                method_card_set_id = EXCLUDED.method_card_set_id,
                method_id = EXCLUDED.method_id,
                family = EXCLUDED.family,
                status = EXCLUDED.status,
                card_format = EXCLUDED.card_format,
                revision_number = EXCLUDED.revision_number,
                supersedes_method_card_id = EXCLUDED.supersedes_method_card_id,
                source_methodology_candidate_id = EXCLUDED.source_methodology_candidate_id,
                validation_refs = EXCLUDED.validation_refs,
                payload = EXCLUDED.payload
            """,
            [
                payload["method_card_id"],
                payload["method_card_set_id"],
                payload["method_id"],
                payload["family"],
                payload["status"],
                payload.get("card_format") or "method_card",
                int(payload.get("revision_number") or payload.get("version") or 1),
                payload.get("supersedes_method_card_id"),
                payload.get("source_methodology_candidate_id"),
                Jsonb(validation_refs_payload),
                payload["created_at"],
                Jsonb(dict(payload)),
            ],
        )

    def list_persisted_method_cards(self) -> tuple[Mapping[str, Any], ...]:
        """Return persisted method-card payloads ordered deterministically by method-card identifier for merging."""
        rows = self._connection.execute("SELECT payload FROM knowledge_method_cards ORDER BY method_card_id").fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

    def save_method_card_set(self, payload: Mapping[str, Any]) -> None:
        """Insert or update one stable method-card set payload keyed by set ID."""
        self._connection.execute(
            """
            INSERT INTO knowledge_method_card_sets (
                method_card_set_id, method_id, family, canonical_title, status,
                source_fingerprint, current_approved_method_card_id, current_draft_method_card_id,
                card_ids, revision_count, latest_revision_number, status_counts,
                created_at, updated_at, payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (method_card_set_id) DO UPDATE SET
                method_id = EXCLUDED.method_id,
                family = EXCLUDED.family,
                canonical_title = EXCLUDED.canonical_title,
                status = EXCLUDED.status,
                source_fingerprint = EXCLUDED.source_fingerprint,
                current_approved_method_card_id = EXCLUDED.current_approved_method_card_id,
                current_draft_method_card_id = EXCLUDED.current_draft_method_card_id,
                card_ids = EXCLUDED.card_ids,
                revision_count = EXCLUDED.revision_count,
                latest_revision_number = EXCLUDED.latest_revision_number,
                status_counts = EXCLUDED.status_counts,
                updated_at = EXCLUDED.updated_at,
                payload = EXCLUDED.payload
            """,
            [
                payload["method_card_set_id"],
                payload["method_id"],
                payload["family"],
                payload["canonical_title"],
                payload["status"],
                payload.get("source_fingerprint"),
                payload.get("current_approved_method_card_id"),
                payload.get("current_draft_method_card_id"),
                list(payload.get("card_ids") or ()),
                int(payload.get("revision_count") or 0),
                int(payload.get("latest_revision_number") or 0),
                Jsonb(dict(payload.get("status_counts") or {})),
                payload["created_at"],
                payload["updated_at"],
                Jsonb(dict(payload)),
            ],
        )

    def list_method_card_sets(self) -> tuple[Mapping[str, Any], ...]:
        """Return stable method-card set payloads ordered deterministically by set identifier."""
        rows = self._connection.execute(
            "SELECT payload FROM knowledge_method_card_sets ORDER BY method_card_set_id"
        ).fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

    def save_method_contract(self, payload: Mapping[str, Any]) -> None:
        """Insert or update one persisted method-contract payload keyed by method ID."""
        self._connection.execute(
            """
            INSERT INTO knowledge_method_contracts (method_id, family, status, purpose, payload)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (method_id) DO UPDATE SET
                family = EXCLUDED.family,
                status = EXCLUDED.status,
                purpose = EXCLUDED.purpose,
                payload = EXCLUDED.payload
            """,
            [
                payload["method_id"],
                payload["family"],
                payload["status"],
                payload["purpose"],
                Jsonb(dict(payload)),
            ],
        )

    def list_persisted_method_contracts(self) -> tuple[Mapping[str, Any], ...]:
        """Return persisted method-contract payloads ordered deterministically by maintained method ID for merging."""
        rows = self._connection.execute("SELECT payload FROM knowledge_method_contracts ORDER BY method_id").fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

    def close(self) -> None:
        """Close the underlying psycopg connection owned by this record store instance."""
        self._connection.close()

    def connection(self) -> Any:
        """Expose the underlying psycopg connection for integration-test inspection and adapters safely."""
        return self._connection

    def _ensure_pgvector(self) -> None:
        if self.pgvector_available():
            return
        try:
            self._connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception as exc:  # pragma: no cover - depends on DB permissions
            try:
                self._connection.rollback()
            except Exception:
                pass
            raise PostgresKnowledgeVectorExtensionUnavailable(
                "Postgres pgvector extension is required for knowledge embeddings"
            ) from exc
        if not self.pgvector_available():
            raise PostgresKnowledgeVectorExtensionUnavailable(
                "Postgres pgvector extension is required for knowledge embeddings"
            )

    def _search_filters(
        self,
        *,
        source_ids: Sequence[str] | None,
        topic: str | None,
        method_family: str | None,
        approved_only: bool,
    ) -> tuple[list[str], list[Any]]:
        where = ["c.active = TRUE"]
        params: list[Any] = []
        if source_ids:
            where.append("c.source_id = ANY(%s)")
            params.append(list(source_ids))
        if topic:
            where.append("%s = ANY(c.topics)")
            params.append(topic)
        if method_family:
            where.append("%s = ANY(c.method_families)")
            params.append(method_family)
        if approved_only:
            where.append("s.status = ANY(%s)")
            params.append(["approved", "registered", "pending"])
        else:
            where.append("s.status <> ALL(%s)")
            params.append(["rejected", "superseded"])
        return where, params

    def _validate_vector_dimension(
        self,
        vector: Sequence[float],
        *,
        provider: str,
        model: str,
        version: str,
    ) -> None:
        rows = self._connection.execute(
            """
            SELECT DISTINCT dimension
            FROM knowledge_embeddings
            WHERE provider = %s AND model = %s AND version = %s
            """,
            [provider, model, version],
        ).fetchall()
        dimensions = {int(row["dimension"]) for row in rows}
        if dimensions and len(vector) not in dimensions:
            raise PostgresKnowledgeEmbeddingDimensionError(
                f"query dimension {len(vector)} does not match stored dimensions {sorted(dimensions)}"
            )
