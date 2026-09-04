"""Define the Postgres schema owned by research knowledge persistence."""

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
        evidence_unit_id TEXT,
        parent_section_id TEXT,
        paragraph_index INTEGER,
        sentence_start_index INTEGER,
        sentence_end_index INTEGER,
        detected_labels TEXT[] NOT NULL DEFAULT '{}',
        neighbor_chunk_ids TEXT[] NOT NULL DEFAULT '{}',
        chunker_version TEXT,
        schema_version TEXT,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        payload JSONB NOT NULL,
        search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED
    )
    """,
    "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS evidence_unit_id TEXT",
    "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS parent_section_id TEXT",
    "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS paragraph_index INTEGER",
    "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS sentence_start_index INTEGER",
    "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS sentence_end_index INTEGER",
    "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS detected_labels TEXT[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS neighbor_chunk_ids TEXT[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS chunker_version TEXT",
    "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS schema_version TEXT",
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
    CREATE TABLE IF NOT EXISTS knowledge_method_card_sets (
        method_card_set_id TEXT PRIMARY KEY,
        method_id TEXT NOT NULL,
        family TEXT NOT NULL,
        canonical_title TEXT NOT NULL,
        status TEXT NOT NULL,
        source_fingerprint TEXT,
        current_approved_method_card_id TEXT,
        current_draft_method_card_id TEXT,
        card_ids TEXT[] NOT NULL DEFAULT '{}',
        revision_count INTEGER NOT NULL DEFAULT 0,
        latest_revision_number INTEGER NOT NULL DEFAULT 0,
        status_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_method_cards (
        method_card_id TEXT PRIMARY KEY,
        method_card_set_id TEXT NOT NULL,
        method_id TEXT NOT NULL,
        family TEXT NOT NULL,
        status TEXT NOT NULL,
        card_format TEXT NOT NULL DEFAULT 'method_card',
        revision_number INTEGER NOT NULL,
        supersedes_method_card_id TEXT,
        source_methodology_candidate_id TEXT,
        validation_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL,
        payload JSONB NOT NULL
    )
    """,
    "ALTER TABLE knowledge_method_cards ADD COLUMN IF NOT EXISTS card_format TEXT NOT NULL DEFAULT 'method_card'",
    "ALTER TABLE knowledge_method_cards ADD COLUMN IF NOT EXISTS method_card_set_id TEXT",
    "ALTER TABLE knowledge_method_cards ALTER COLUMN method_card_set_id DROP DEFAULT",
    "ALTER TABLE knowledge_method_cards ALTER COLUMN method_card_set_id SET NOT NULL",
    "ALTER TABLE knowledge_method_cards ADD COLUMN IF NOT EXISTS revision_number INTEGER",
    "ALTER TABLE knowledge_method_cards ALTER COLUMN revision_number DROP DEFAULT",
    "ALTER TABLE knowledge_method_cards ALTER COLUMN revision_number SET NOT NULL",
    "ALTER TABLE knowledge_method_cards ADD COLUMN IF NOT EXISTS supersedes_method_card_id TEXT",
    "ALTER TABLE knowledge_method_cards ADD COLUMN IF NOT EXISTS source_methodology_candidate_id TEXT",
    "ALTER TABLE knowledge_method_cards ADD COLUMN IF NOT EXISTS validation_refs JSONB NOT NULL DEFAULT '[]'::jsonb",
    "CREATE INDEX IF NOT EXISTS knowledge_sources_file_hash_idx ON knowledge_sources(file_hash)",
    "CREATE INDEX IF NOT EXISTS knowledge_sources_status_idx ON knowledge_sources(status)",
    "CREATE INDEX IF NOT EXISTS knowledge_sources_topics_idx ON knowledge_sources USING GIN(topics)",
    "CREATE INDEX IF NOT EXISTS knowledge_sources_method_families_idx ON knowledge_sources USING GIN(method_families)",
    "CREATE INDEX IF NOT EXISTS knowledge_chunks_source_active_idx ON knowledge_chunks(source_id, active)",
    "CREATE INDEX IF NOT EXISTS knowledge_chunks_evidence_unit_idx ON knowledge_chunks(evidence_unit_id)",
    "CREATE INDEX IF NOT EXISTS knowledge_chunks_detected_labels_idx ON knowledge_chunks USING GIN(detected_labels)",
    "CREATE INDEX IF NOT EXISTS knowledge_chunks_search_idx ON knowledge_chunks USING GIN(search_vector)",
    "CREATE INDEX IF NOT EXISTS knowledge_embeddings_lookup_idx ON knowledge_embeddings(provider, model, version, dimension)",
    "CREATE INDEX IF NOT EXISTS knowledge_ingestion_runs_source_ids_idx ON knowledge_ingestion_runs USING GIN(source_ids)",
    "CREATE INDEX IF NOT EXISTS knowledge_method_card_sets_method_idx ON knowledge_method_card_sets(method_id, family)",
    "CREATE INDEX IF NOT EXISTS knowledge_method_card_sets_status_idx ON knowledge_method_card_sets(status)",
    "CREATE INDEX IF NOT EXISTS knowledge_method_cards_card_format_idx ON knowledge_method_cards(card_format)",
    "CREATE INDEX IF NOT EXISTS knowledge_method_cards_set_idx ON knowledge_method_cards(method_card_set_id)",
    "CREATE INDEX IF NOT EXISTS knowledge_method_cards_set_revision_idx ON knowledge_method_cards(method_card_set_id, revision_number)",
    "CREATE INDEX IF NOT EXISTS knowledge_method_cards_source_methodology_idx ON knowledge_method_cards(source_methodology_candidate_id)",
    """
    CREATE OR REPLACE VIEW knowledge_active_method_cards AS
    SELECT
        method_card_id,
        method_card_set_id,
        method_id,
        family,
        status,
        card_format,
        revision_number,
        supersedes_method_card_id,
        source_methodology_candidate_id,
        validation_refs,
        created_at,
        payload
    FROM knowledge_method_cards
    WHERE status NOT IN ('rejected', 'superseded')
    """,
    """
    CREATE OR REPLACE VIEW knowledge_method_card_revision_history AS
    SELECT
        card.method_card_set_id,
        card.revision_number,
        card.method_card_id,
        card.method_id,
        card.family,
        card.status,
        card.card_format,
        card.supersedes_method_card_id,
        card.source_methodology_candidate_id,
        card.created_at,
        card.payload
    FROM knowledge_method_cards card
    ORDER BY card.method_card_set_id, card.revision_number, card.created_at, card.method_card_id
    """,
    """
    CREATE OR REPLACE VIEW knowledge_method_card_set_summary AS
    SELECT
        sets.method_card_set_id,
        sets.method_id,
        sets.family,
        sets.canonical_title,
        sets.status,
        sets.source_fingerprint,
        sets.current_approved_method_card_id,
        sets.current_draft_method_card_id,
        sets.revision_count,
        sets.latest_revision_number,
        sets.status_counts,
        sets.updated_at,
        sets.payload
    FROM knowledge_method_card_sets sets
    """,
)
