"""Core Postgres persistence for Quant Methods knowledge records."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

try:  # pragma: no cover - exercised by postgres integration tests
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - import guard
    psycopg = None
    dict_row = None
    Jsonb = None


class PostgresKnowledgeStoreError(RuntimeError):
    """Base error for Postgres knowledge persistence."""


class PostgresKnowledgeVectorExtensionUnavailable(PostgresKnowledgeStoreError):
    """Raised when pgvector is required but unavailable."""


class PostgresKnowledgeEmbeddingDimensionError(PostgresKnowledgeStoreError):
    """Raised when query and stored embedding dimensions differ."""


class PostgresKnowledgeRecordStore:
    """SQL-owning record store for knowledge metadata and retrieval."""

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
        self._ensure_pgvector()
        statements = [
            """
            CREATE TABLE IF NOT EXISTS knowledge_sources (
                source_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                file_size_bytes BIGINT NOT NULL,
                access_policy TEXT NOT NULL,
                topics TEXT[] NOT NULL DEFAULT '{}',
                method_families TEXT[] NOT NULL DEFAULT '{}',
                canonical_citation TEXT,
                status TEXT NOT NULL,
                duplicate_source_ids TEXT[] NOT NULL DEFAULT '{}',
                warnings TEXT[] NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL,
                schema_version TEXT NOT NULL,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                chunk_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES knowledge_sources(source_id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL,
                text TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                locator JSONB NOT NULL,
                topics TEXT[] NOT NULL DEFAULT '{}',
                method_families TEXT[] NOT NULL DEFAULT '{}',
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                payload JSONB NOT NULL,
                search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_embedding_indexes (
                embedding_manifest_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                version TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                distance_metric TEXT NOT NULL DEFAULT 'cosine',
                chunk_ids TEXT[] NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL,
                schema_version TEXT NOT NULL,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                embedding_manifest_id TEXT NOT NULL REFERENCES knowledge_embedding_indexes(embedding_manifest_id) ON DELETE CASCADE,
                chunk_id TEXT NOT NULL REFERENCES knowledge_chunks(chunk_id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                version TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                embedding vector NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (embedding_manifest_id, chunk_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_ingestion_runs (
                ingestion_id TEXT PRIMARY KEY,
                source_ids TEXT[] NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                chunks_created INTEGER NOT NULL,
                chunks_indexed INTEGER NOT NULL,
                embedding_manifest_id TEXT,
                warnings TEXT[] NOT NULL DEFAULT '{}',
                blockers TEXT[] NOT NULL DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL,
                schema_version TEXT NOT NULL,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_method_cards (
                method_card_id TEXT PRIMARY KEY,
                method_id TEXT NOT NULL,
                family TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_method_contracts (
                method_id TEXT PRIMARY KEY,
                family TEXT NOT NULL,
                status TEXT NOT NULL,
                purpose TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                payload JSONB NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS knowledge_sources_file_hash_idx ON knowledge_sources(file_hash)",
            "CREATE INDEX IF NOT EXISTS knowledge_sources_status_idx ON knowledge_sources(status)",
            "CREATE INDEX IF NOT EXISTS knowledge_sources_topics_idx ON knowledge_sources USING GIN(topics)",
            "CREATE INDEX IF NOT EXISTS knowledge_sources_method_families_idx ON knowledge_sources USING GIN(method_families)",
            "CREATE INDEX IF NOT EXISTS knowledge_chunks_source_active_idx ON knowledge_chunks(source_id, active)",
            "CREATE INDEX IF NOT EXISTS knowledge_chunks_search_idx ON knowledge_chunks USING GIN(search_vector)",
            "CREATE INDEX IF NOT EXISTS knowledge_embeddings_lookup_idx ON knowledge_embeddings(provider, model, version, dimension)",
            "CREATE INDEX IF NOT EXISTS knowledge_ingestion_runs_source_ids_idx ON knowledge_ingestion_runs USING GIN(source_ids)",
            "CREATE INDEX IF NOT EXISTS knowledge_method_contracts_family_status_idx ON knowledge_method_contracts(family, status)",
        ]
        try:
            with self._connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
        except Exception as exc:  # pragma: no cover - driver-specific details
            raise PostgresKnowledgeStoreError(f"failed to initialize knowledge schema: {exc}") from exc

    def runtime_summary(self) -> Mapping[str, Any]:
        return {
            "backend": "postgres",
            "configured": True,
            "pgvector_available": self.pgvector_available(),
            "schema": "public",
        }

    def pgvector_available(self) -> bool:
        row = self._connection.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS ok").fetchone()
        return bool(row and row["ok"])

    def save_source(self, payload: Mapping[str, Any]) -> None:
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
        rows = self._connection.execute(
            "SELECT payload FROM knowledge_sources WHERE file_hash = %s ORDER BY source_id",
            [file_hash],
        ).fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

    def replace_chunks(self, source_id: str, chunks: Sequence[Mapping[str, Any]]) -> None:
        with self._connection.transaction():
            self._connection.execute("UPDATE knowledge_chunks SET active = FALSE WHERE source_id = %s", [source_id])
            for chunk in chunks:
                self._connection.execute(
                    """
                    INSERT INTO knowledge_chunks (
                        chunk_id, source_id, ordinal, text, text_hash, locator,
                        topics, method_families, active, payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        ordinal = EXCLUDED.ordinal,
                        text = EXCLUDED.text,
                        text_hash = EXCLUDED.text_hash,
                        locator = EXCLUDED.locator,
                        topics = EXCLUDED.topics,
                        method_families = EXCLUDED.method_families,
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
                        Jsonb(dict(chunk)),
                    ],
                )

    def load_chunks(self, source_id: str) -> tuple[Mapping[str, Any], ...]:
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

    def list_ingestion_reports(
        self,
        *,
        source_ids: Sequence[str] | None = None,
        run_id: str | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
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
        where, params = self._search_filters(
            source_ids=source_ids,
            topic=topic,
            method_family=method_family,
            approved_only=approved_only,
        )
        sql = f"""
            SELECT
                c.chunk_id, c.source_id, c.text, c.text_hash, c.locator,
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
        self._connection.execute(
            """
            INSERT INTO knowledge_method_cards (method_card_id, method_id, family, status, created_at, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (method_card_id) DO UPDATE SET
                method_id = EXCLUDED.method_id,
                family = EXCLUDED.family,
                status = EXCLUDED.status,
                payload = EXCLUDED.payload
            """,
            [
                payload["method_card_id"],
                payload["method_id"],
                payload["family"],
                payload["status"],
                payload["created_at"],
                Jsonb(dict(payload)),
            ],
        )

    def list_persisted_method_cards(self) -> tuple[Mapping[str, Any], ...]:
        rows = self._connection.execute("SELECT payload FROM knowledge_method_cards ORDER BY method_card_id").fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

    def save_method_contract(self, payload: Mapping[str, Any]) -> None:
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
        rows = self._connection.execute("SELECT payload FROM knowledge_method_contracts ORDER BY method_id").fetchall()
        return tuple(_mapping(row["payload"]) for row in rows)

    def close(self) -> None:
        self._connection.close()

    def connection(self) -> Any:
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


def _result_from_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    text = str(row.get("text") or "")
    source_status = str(row.get("source_status") or "")
    return {
        "source_id": row.get("source_id"),
        "source_title": row.get("source_title"),
        "source_type": row.get("source_type"),
        "source_status": source_status,
        "approved_source": source_status == "approved",
        "chunk_id": row.get("chunk_id"),
        "locator": _mapping(row.get("locator")),
        "score": float(row.get("score") or 0.0),
        "excerpt": text[:360],
        "text_hash": row.get("text_hash"),
    }


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
