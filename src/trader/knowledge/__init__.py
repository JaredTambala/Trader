"""Knowledge persistence adapters for research retrieval workflows."""

from .store import (
    PostgresKnowledgeEmbeddingDimensionError,
    PostgresKnowledgeRecordStore,
    PostgresKnowledgeStoreError,
    PostgresKnowledgeVectorExtensionUnavailable,
)

__all__ = [
    "PostgresKnowledgeEmbeddingDimensionError",
    "PostgresKnowledgeRecordStore",
    "PostgresKnowledgeStoreError",
    "PostgresKnowledgeVectorExtensionUnavailable",
]
