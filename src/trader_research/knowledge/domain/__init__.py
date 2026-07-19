"""Public knowledge domain model facade."""

from .cards import (
    MethodCard,
    MethodCardSet,
    MethodCardSummary,
    default_method_card_set_id,
)
from .common import (
    DEFAULT_SOURCE_TYPE,
    KNOWLEDGE_EVIDENCE_UNIT_ARTIFACT_TYPE,
    KNOWLEDGE_SCHEMA_VERSION,
    METHODOLOGY_CANDIDATE_STATUSES,
    METHODOLOGY_EVIDENCE_PACKET_STATUSES,
    METHOD_CARD_SET_STATUSES,
    METHOD_CARD_STATUSES,
    SOURCE_TYPE_LABELS,
    SUPPORTED_SOURCE_EXTENSIONS,
)
from .evidence import (
    EvidenceBackedField,
    EvidenceClaimSpan,
    EvidenceReference,
)
from .fields import (
    METHODOLOGY_CORE_FIELD_SCHEMA,
    METHODOLOGY_EXTENSION_FIELD_SCHEMA,
)
from .methodology import (
    MethodologyCandidate,
    MethodologyCandidateValidationReport,
    MethodologyEvidencePacket,
    MethodologyFieldExtractionReport,
)
from .reports import (
    CitationValidationReport,
    EvidenceChunkDereferenceReport,
    EvidenceRetrievalReport,
)
from .sources import (
    KnowledgeChunk,
    KnowledgeEmbeddingManifest,
    KnowledgeIngestionReport,
    KnowledgeSourceManifest,
)

__all__ = [
    "CitationValidationReport",
    "DEFAULT_SOURCE_TYPE",
    "EvidenceBackedField",
    "EvidenceChunkDereferenceReport",
    "EvidenceClaimSpan",
    "EvidenceReference",
    "EvidenceRetrievalReport",
    "KNOWLEDGE_EVIDENCE_UNIT_ARTIFACT_TYPE",
    "KNOWLEDGE_SCHEMA_VERSION",
    "KnowledgeChunk",
    "KnowledgeEmbeddingManifest",
    "KnowledgeIngestionReport",
    "KnowledgeSourceManifest",
    "METHODOLOGY_CANDIDATE_STATUSES",
    "METHODOLOGY_CORE_FIELD_SCHEMA",
    "METHODOLOGY_EVIDENCE_PACKET_STATUSES",
    "METHODOLOGY_EXTENSION_FIELD_SCHEMA",
    "METHOD_CARD_SET_STATUSES",
    "METHOD_CARD_STATUSES",
    "MethodCard",
    "MethodCardSet",
    "MethodCardSummary",
    "MethodologyCandidate",
    "MethodologyCandidateValidationReport",
    "MethodologyEvidencePacket",
    "MethodologyFieldExtractionReport",
    "SOURCE_TYPE_LABELS",
    "SUPPORTED_SOURCE_EXTENSIONS",
    "default_method_card_set_id",
]
