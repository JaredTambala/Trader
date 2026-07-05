"""Postgres schema statements for the knowledge record store."""

from __future__ import annotations


KNOWLEDGE_SCHEMA_STATEMENTS = (
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
)
