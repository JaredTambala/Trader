from __future__ import annotations

from trader.knowledge.records import mapping, result_from_row, string_list, vector_literal
from trader.knowledge.schema import KNOWLEDGE_SCHEMA_STATEMENTS


def test_result_from_row_normalizes_retrieval_result_shape() -> None:
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
    assert vector_literal((1, "2.5", 3.0)) == "[1.0,2.5,3.0]"
    assert mapping({"a": 1}) == {"a": 1}
    assert mapping(None) == {}
    assert string_list(None) == []
    assert string_list("topic") == ["topic"]
    assert string_list(["a", "", " b "]) == ["a", " b "]
    assert string_list(3) == ["3"]


def test_knowledge_schema_statements_include_core_tables_and_indexes() -> None:
    joined = "\n".join(KNOWLEDGE_SCHEMA_STATEMENTS)

    assert "CREATE TABLE IF NOT EXISTS knowledge_sources" in joined
    assert "CREATE TABLE IF NOT EXISTS knowledge_chunks" in joined
    assert "CREATE TABLE IF NOT EXISTS knowledge_embeddings" in joined
    assert "knowledge_method_contracts_family_status_idx" in joined
