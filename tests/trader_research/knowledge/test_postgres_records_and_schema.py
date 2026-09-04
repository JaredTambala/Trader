"""Unit contracts for Postgres knowledge row normalization and schema declarations.

Subject: Infrastructure helpers translating database values and declaring knowledge persistence tables.
Level: In-process unit contract.
Collaborators: Real Postgres record and schema helpers with plain mappings; no database connection.
Guarantees: Rows, vectors, mappings, and lists normalize predictably and retired tables stay absent.
Non-goals: Executing SQL, testing transactions, vector search, ingestion services, or core event storage.
"""

from __future__ import annotations

from trader_research.infrastructure.postgres.knowledge.records import (
    mapping,
    result_from_row,
    string_list,
    vector_literal,
)
from trader_research.infrastructure.postgres.knowledge.schema import (
    KNOWLEDGE_SCHEMA_STATEMENTS,
)


def test_result_from_row_normalizes_retrieval_result_shape() -> None:
    """A database retrieval row normalizes approval, scores, locators, and bounded excerpts."""
    result = result_from_row(
        {
            "source_id": "source_1",
            "source_title": "Method Source",
            "source_type": "method_textbook",
            "source_status": "approved",
            "chunk_id": "chunk_1",
            "locator": {"page": 3},
            "score": "0.75",
            "text": "x" * 400,
            "text_hash": "hash_1",
        }
    )

    assert result["approved_source"] is True
    assert result["locator"] == {"page": 3}
    assert result["score"] == 0.75
    assert result["excerpt"] == "x" * 360


def test_record_helpers_normalize_vectors_mappings_and_string_lists() -> None:
    """Record helpers normalize database vector, mapping, and list values into stable shapes."""
    assert vector_literal((1, "2.5", 3.0)) == "[1.0,2.5,3.0]"
    assert mapping({"a": 1}) == {"a": 1}
    assert mapping(None) == {}
    assert string_list(None) == []
    assert string_list("topic") == ["topic"]
    assert string_list(["a", "", " b "]) == ["a", " b "]
    assert string_list(3) == ["3"]


def test_knowledge_schema_statements_include_core_tables_and_indexes() -> None:
    """Knowledge schema declarations include active evidence tables and exclude retired method contracts."""
    joined = "\n".join(KNOWLEDGE_SCHEMA_STATEMENTS)

    assert "CREATE TABLE IF NOT EXISTS knowledge_sources" in joined
    assert "CREATE TABLE IF NOT EXISTS knowledge_chunks" in joined
    assert "CREATE TABLE IF NOT EXISTS knowledge_embeddings" in joined
    assert "knowledge_method_contracts" not in joined
