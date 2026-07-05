"""Pure record normalization helpers for the Postgres knowledge store."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def result_from_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    """Normalize one retrieval SQL row into the store result contract.

    Args:
        row: Mapping row returned by psycopg.

    Returns:
        JSON-compatible retrieval result mapping.
    """
    text = str(row.get("text") or "")
    source_status = str(row.get("source_status") or "")
    return {
        "source_id": row.get("source_id"),
        "source_title": row.get("source_title"),
        "source_type": row.get("source_type"),
        "source_status": source_status,
        "approved_source": source_status == "approved",
        "chunk_id": row.get("chunk_id"),
        "locator": mapping(row.get("locator")),
        "score": float(row.get("score") or 0.0),
        "excerpt": text[:360],
        "text_hash": row.get("text_hash"),
    }


def vector_literal(vector: Sequence[float]) -> str:
    """Return a pgvector literal for a numeric vector.

    Args:
        vector: Numeric vector values.

    Returns:
        Bracketed pgvector literal.
    """
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def mapping(value: Any) -> Mapping[str, Any]:
    """Return a mapping value or an empty mapping."""
    return value if isinstance(value, Mapping) else {}


def string_list(value: Any) -> list[str]:
    """Normalize a scalar or sequence into a list of nonblank strings."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
