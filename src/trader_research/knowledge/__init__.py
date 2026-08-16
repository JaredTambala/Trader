"""Expose the Quantitative Methods knowledge and evidence workflow.

The package registers approved sources, preserves locator-level chunks, retrieves
and validates evidence, and produces draft methodology artifacts. Knowledge
evidence may support implementation work but never bypasses normal implementation
admission or experiment validation.
"""

from .approved_cards import (
    ApprovedMethodCardReadError,
    ApprovedMethodCardReader,
    StoreBackedApprovedMethodCardReader,
)
from .citation_validation import validate_citations
from .domain import (
    DEFAULT_SOURCE_TYPE,
    CitationValidationReport,
    EvidenceClaimSpan,
    EvidenceReference,
    EvidenceRetrievalReport,
    MethodCard,
    MethodologyCandidate,
    MethodologyEvidencePacket,
    MethodologyCandidateValidationReport,
    MethodologyFieldExtractionReport,
    KnowledgeChunk,
    KnowledgeEmbeddingManifest,
    KnowledgeIngestionReport,
    KnowledgeSourceManifest,
    MethodCardSummary,
    MethodCardSet,
)
from .embeddings import (
    EmbeddingProvider,
    RuntimeConfiguredEmbeddingProvider,
    embedding_runtime_summary,
)
from .evidence_assembly import assemble_methodology_evidence
from .ingestion import get_ingestion_status, ingest_documents
from .method_cards import (
    create_method_card_draft,
    get_method_card_set,
    list_method_card_sets,
    publish_method_card,
    update_method_card_status,
)
from .methodology_candidates import discover_methodology_candidates
from .methodology_extraction import extract_methodology_fields
from .methodology_validation import validate_methodology_candidate
from .postgres_store import PostgresKnowledgeStore
from .retrieval import get_evidence_chunks, retrieve_evidence, search_methods
from .sources import list_sources, register_source
from .store import KnowledgeStore, UnavailableKnowledgeStore

__all__ = [
    "ApprovedMethodCardReadError",
    "ApprovedMethodCardReader",
    "CitationValidationReport",
    "DEFAULT_SOURCE_TYPE",
    "EmbeddingProvider",
    "EvidenceClaimSpan",
    "EvidenceReference",
    "EvidenceRetrievalReport",
    "MethodCard",
    "MethodologyCandidate",
    "MethodologyEvidencePacket",
    "MethodologyCandidateValidationReport",
    "MethodologyFieldExtractionReport",
    "KnowledgeChunk",
    "KnowledgeEmbeddingManifest",
    "KnowledgeIngestionReport",
    "KnowledgeSourceManifest",
    "KnowledgeStore",
    "MethodCardSummary",
    "MethodCardSet",
    "PostgresKnowledgeStore",
    "RuntimeConfiguredEmbeddingProvider",
    "StoreBackedApprovedMethodCardReader",
    "UnavailableKnowledgeStore",
    "assemble_methodology_evidence",
    "create_method_card_draft",
    "discover_methodology_candidates",
    "embedding_runtime_summary",
    "extract_methodology_fields",
    "get_evidence_chunks",
    "get_ingestion_status",
    "get_method_card_set",
    "ingest_documents",
    "list_method_card_sets",
    "list_sources",
    "publish_method_card",
    "register_source",
    "retrieve_evidence",
    "search_methods",
    "update_method_card_status",
    "validate_citations",
    "validate_methodology_candidate",
]
