"""Typed artifacts for the Quant Methods knowledge base."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


KNOWLEDGE_SCHEMA_VERSION = "1"
"""Schema version for local knowledge artifacts."""

SUPPORTED_SOURCE_EXTENSIONS = frozenset({".md", ".txt", ".pdf"})
"""File types accepted by the first knowledge-ingestion slice."""

SOURCE_TYPE_LABELS = frozenset(
    {
        "foundation_textbook",
        "method_textbook",
        "primary_paper",
        "software_documentation",
        "internal_note",
    }
)
"""Allowed source-type labels for registered knowledge documents."""

DEFAULT_SOURCE_TYPE = "internal_note"
"""Default source-type label for local notes and operator-authored documents."""

METHODOLOGY_CANDIDATE_STATUSES = frozenset({"discovered", "extracted", "validated", "blocked", "rejected"})
"""Allowed lifecycle states for rich methodology candidates before card approval."""

METHODOLOGY_EVIDENCE_PACKET_STATUSES = frozenset({"assembled", "blocked"})
"""Allowed lifecycle states for assembled methodology evidence packets."""

METHOD_CARD_STATUSES = frozenset({"approved", "draft", "planned", "rejected", "superseded"})
"""Allowed lifecycle states for shallow and rich method-card records."""

RICH_METHOD_CARD_FORMAT = "rich_method_card"
"""Payload marker for method-card artifacts carrying rich methodology fields."""

METHODOLOGY_CORE_FIELD_SCHEMA: Mapping[str, frozenset[str]] = {
    "identity": frozenset(
        {
            "method_name",
            "description",
            "aliases",
            "intended_use",
            "source_context",
            "limitations",
        }
    ),
    "scope": frozenset(
        {
            "asset_classes",
            "instruments",
            "markets",
            "timeframes",
            "horizon",
            "universe_definition",
            "market_regime",
            "geography",
        }
    ),
    "data_requirements": frozenset(
        {
            "required_inputs",
            "price_fields",
            "fundamental_fields",
            "alternative_data_fields",
            "option_chain_fields",
            "frequency",
            "lookback_window",
            "preprocessing",
            "data_quality_requirements",
        }
    ),
    "method_specification": frozenset(
        {
            "hypothesis",
            "algorithm_steps",
            "equations",
            "parameters",
            "estimation_method",
            "statistical_tests",
            "optimization_objective",
            "calibration",
        }
    ),
    "signal_decision_logic": frozenset(
        {
            "signal_definition",
            "entry_rules",
            "exit_rules",
            "thresholds",
            "ranking_rules",
            "position_direction",
            "rebalance_rules",
        }
    ),
    "portfolio_execution": frozenset(
        {
            "sizing",
            "portfolio_construction",
            "constraints",
            "rebalancing",
            "execution_timing",
            "order_types",
            "transaction_cost_assumptions",
            "liquidity_assumptions",
        }
    ),
    "risk_validation": frozenset(
        {
            "risk_controls",
            "validation_tests",
            "benchmarks",
            "performance_metrics",
            "stress_tests",
            "failure_modes",
            "assumptions",
            "known_limitations",
        }
    ),
    "implementation_notes": frozenset(
        {
            "implementation_steps",
            "libraries",
            "numerical_stability",
            "edge_cases",
            "runtime_requirements",
            "monitoring",
        }
    ),
}
"""Common nullable field groups shared by all methodology families."""

METHODOLOGY_EXTENSION_FIELD_SCHEMA: Mapping[str, frozenset[str]] = {
    "technical_indicators": frozenset(
        {
            "indicator_formula",
            "input_series",
            "lookback_period",
            "smoothing_method",
            "normalization",
            "overbought_threshold",
            "oversold_threshold",
            "warmup_period",
            "divergence_rules",
            "parameter_defaults",
        }
    ),
    "statistical_arbitrage": frozenset(
        {
            "spread_definition",
            "hedge_ratio_method",
            "cointegration_test",
            "stationarity_test",
            "entry_zscore",
            "exit_zscore",
            "stop_loss",
            "formation_window",
            "trading_window",
            "rebalance_frequency",
            "leg_universe",
            "mean_reversion_assumption",
        }
    ),
    "options_derivatives": frozenset(
        {
            "instrument_type",
            "payoff_profile",
            "legs",
            "strike_selection",
            "expiry_selection",
            "volatility_assumption",
            "greeks",
            "delta_hedging",
            "margin_assumptions",
            "exercise_style",
            "assignment_risk",
            "scenario_analysis",
        }
    ),
    "fundamental_valuation": frozenset(
        {
            "valuation_model",
            "financial_statement_inputs",
            "forecast_horizon",
            "discount_rate",
            "terminal_value",
            "factor_exposures",
            "quality_filters",
            "revision_triggers",
            "normalization",
        }
    ),
    "sentiment_alternative_data": frozenset(
        {
            "source_type",
            "raw_signal",
            "entity_mapping",
            "aggregation_window",
            "scoring_model",
            "lag_assumptions",
            "coverage_requirements",
            "bias_controls",
            "noise_filters",
            "commodity_mapping",
        }
    ),
    "portfolio_construction": frozenset(
        {
            "objective",
            "allocation_method",
            "constraints",
            "rebalance_cadence",
            "turnover_limit",
            "risk_budget",
            "diversification_rule",
            "optimization_inputs",
            "cash_handling",
        }
    ),
    "risk_models": frozenset(
        {
            "risk_measure",
            "confidence_level",
            "lookback_window",
            "correlation_model",
            "covariance_estimator",
            "stress_scenarios",
            "limit_thresholds",
            "breach_actions",
            "model_validation",
        }
    ),
    "execution_methods": frozenset(
        {
            "execution_algorithm",
            "order_slicing",
            "participation_rate",
            "schedule",
            "venue_selection",
            "slippage_model",
            "latency_assumptions",
            "market_impact_model",
            "fill_assumptions",
        }
    ),
}
"""Nullable domain extension blocks for specific methodology families."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class KnowledgeSourceManifest:
    """Persisted registration record for a curated knowledge source file.

    The manifest captures file identity, source classification, optional topic and
    method-family tags, duplicate detection results, and registration warnings.
    Validation keeps source IDs, titles, supported file extensions, and allowed
    source types consistent before the document is chunked or cited by method
    cards.
    """

    source_id: str
    title: str
    source_type: str
    path: str
    file_hash: str
    file_size_bytes: int
    access_policy: str = "local_curated"
    topics: tuple[str, ...] = tuple()
    method_families: tuple[str, ...] = tuple()
    canonical_citation: str | None = None
    status: str = "registered"
    duplicate_source_ids: tuple[str, ...] = tuple()
    warnings: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not self.title.strip():
            raise ValueError("source title is required")
        if self.source_type not in SOURCE_TYPE_LABELS:
            allowed = ", ".join(sorted(SOURCE_TYPE_LABELS))
            raise ValueError(f"unsupported source_type: {self.source_type}; allowed values: {allowed}")
        if Path(self.path).suffix.lower() not in SUPPORTED_SOURCE_EXTENSIONS:
            raise ValueError(f"unsupported source file type: {Path(self.path).suffix}")
        if not self.file_hash.strip():
            raise ValueError("file_hash is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize source metadata into the persisted manifest artifact shape.

        Datetimes are converted to JSON-safe values, tuple fields become lists, and
        duplicate/warning metadata is preserved for source registration review.
        """
        return {
            "artifact_type": "knowledge_source_manifest",
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "title": self.title,
            "source_type": self.source_type,
            "path": self.path,
            "file_hash": self.file_hash,
            "file_size_bytes": self.file_size_bytes,
            "access_policy": self.access_policy,
            "topics": list(self.topics),
            "method_families": list(self.method_families),
            "canonical_citation": self.canonical_citation,
            "status": self.status,
            "duplicate_source_ids": list(self.duplicate_source_ids),
            "warnings": list(self.warnings),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeSourceManifest":
        """Parse a persisted source manifest while applying defaults for legacy fields.

        Optional tuples, citation text, timestamps, access policy, and schema
        version are normalized before dataclass validation enforces required
        source identity and file metadata.
        """
        return cls(
            source_id=str(payload.get("source_id") or ""),
            title=str(payload.get("title") or ""),
            source_type=str(payload.get("source_type") or DEFAULT_SOURCE_TYPE),
            path=str(payload.get("path") or ""),
            file_hash=str(payload.get("file_hash") or ""),
            file_size_bytes=int(payload.get("file_size_bytes") or 0),
            access_policy=str(payload.get("access_policy") or "local_curated"),
            topics=_string_tuple(payload.get("topics")),
            method_families=_string_tuple(payload.get("method_families")),
            canonical_citation=str(payload["canonical_citation"])
            if payload.get("canonical_citation") is not None
            else None,
            status=str(payload.get("status") or "registered"),
            duplicate_source_ids=_string_tuple(payload.get("duplicate_source_ids")),
            warnings=_string_tuple(payload.get("warnings")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class KnowledgeChunk:
    """Citeable unit of source text stored in the knowledge index.

    A chunk stores exact text, a content hash, its source ID, ordinal position, and
    locator metadata such as page, heading, or offsets. The validation contract
    requires non-empty text and locator data so retrieval results can be
    dereferenced and citation validation can prove which source span supports a
    claim.
    """

    chunk_id: str
    source_id: str
    ordinal: int
    text: str
    text_hash: str
    locator: Mapping[str, Any]
    topics: tuple[str, ...] = tuple()
    method_families: tuple[str, ...] = tuple()

    def __post_init__(self) -> None:
        if not self.chunk_id.strip():
            raise ValueError("chunk_id is required")
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not self.text.strip():
            raise ValueError("chunk text is required")
        if not self.text_hash.strip():
            raise ValueError("chunk text_hash is required")
        if not self.locator:
            raise ValueError("chunk locator is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize a citeable chunk with locator, topics, and exact text hash.

        Locator metadata is normalized through `_jsonable`, while tuple fields are
        emitted as lists so the chunk can be stored in JSON or Postgres payloads.
        """
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "ordinal": self.ordinal,
            "text": self.text,
            "text_hash": self.text_hash,
            "locator": _jsonable(self.locator),
            "topics": list(self.topics),
            "method_families": list(self.method_families),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeChunk":
        """Parse a chunk payload from storage into a validated domain object.

        Missing optional topics and method families become empty tuples, while
        required source, text, hash, ordinal, and locator fields are validated by
        the dataclass constructor.
        """
        return cls(
            chunk_id=str(payload.get("chunk_id") or ""),
            source_id=str(payload.get("source_id") or ""),
            ordinal=int(payload.get("ordinal") or 0),
            text=str(payload.get("text") or ""),
            text_hash=str(payload.get("text_hash") or ""),
            locator=_mapping(payload.get("locator")),
            topics=_string_tuple(payload.get("topics")),
            method_families=_string_tuple(payload.get("method_families")),
        )


@dataclass(frozen=True)
class KnowledgeEmbeddingManifest:
    """Runtime embedding metadata for chunks indexed in one ingestion run.

    The manifest records provider, model, version, vector dimension, and chunk IDs
    so future retrieval can detect incompatible embeddings and reviewers can audit
    which backend produced the indexed vectors. It intentionally excludes API keys
    and request payloads.
    """

    embedding_manifest_id: str
    provider: str
    model: str
    version: str
    dimension: int
    chunk_ids: tuple[str, ...]
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize embedding runtime metadata without including vector payloads.

        The manifest stores provider, model, version, dimension, chunk IDs, and
        creation time so retrieval can audit vector compatibility later.
        """
        return {
            "artifact_type": "knowledge_embedding_manifest",
            "schema_version": self.schema_version,
            "embedding_manifest_id": self.embedding_manifest_id,
            "provider": self.provider,
            "model": self.model,
            "version": self.version,
            "dimension": self.dimension,
            "chunk_ids": list(self.chunk_ids),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeEmbeddingManifest":
        """Parse a stored embedding manifest and normalize timestamps and chunk IDs."""
        return cls(
            embedding_manifest_id=str(payload.get("embedding_manifest_id") or ""),
            provider=str(payload.get("provider") or ""),
            model=str(payload.get("model") or ""),
            version=str(payload.get("version") or ""),
            dimension=int(payload.get("dimension") or 0),
            chunk_ids=_string_tuple(payload.get("chunk_ids")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class KnowledgeIngestionReport:
    """Summary artifact produced after extraction, chunking, and indexing.

    The report records which sources were processed, how many chunks were created
    and indexed, the embedding manifest generated for the run, and any warnings or
    blockers. It is the durable handoff that tells downstream agents whether a
    source is citeable or why ingestion could not make it available.
    """

    ingestion_id: str
    source_ids: tuple[str, ...]
    status: str
    chunks_created: int
    chunks_indexed: int
    embedding_manifest_id: str | None = None
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize ingestion status, counts, warnings, blockers, and schema metadata.

        The payload is the durable report used by tools to explain whether sources
        were indexed, partially reused, or blocked during extraction or embedding.
        """
        return {
            "artifact_type": "knowledge_ingestion_report",
            "schema_version": self.schema_version,
            "ingestion_id": self.ingestion_id,
            "source_ids": list(self.source_ids),
            "status": self.status,
            "chunks_created": self.chunks_created,
            "chunks_indexed": self.chunks_indexed,
            "embedding_manifest_id": self.embedding_manifest_id,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "KnowledgeIngestionReport":
        """Parse a stored ingestion report while normalizing optional collections, status, and counts."""
        return cls(
            ingestion_id=str(payload.get("ingestion_id") or ""),
            source_ids=_string_tuple(payload.get("source_ids")),
            status=str(payload.get("status") or ""),
            chunks_created=int(payload.get("chunks_created") or 0),
            chunks_indexed=int(payload.get("chunks_indexed") or 0),
            embedding_manifest_id=str(payload["embedding_manifest_id"])
            if payload.get("embedding_manifest_id") is not None
            else None,
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class EvidenceReference:
    """Serializable citation pointer used by method cards and generated artifacts.

    A reference can point at a source, a specific chunk, a method card, or a
    combination of those identifiers, with an optional locator snapshot and claim
    text. Citation validation uses these fields to prove that claimed evidence
    exists, belongs to the expected source, and has not been cited with a mismatched
    locator.
    """

    source_id: str | None = None
    chunk_id: str | None = None
    locator: Mapping[str, Any] = field(default_factory=dict)
    method_card_id: str | None = None
    claim: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize citation identifiers, locator details, and optional claim text.

        Locator mappings are normalized for JSON storage while absent source,
        chunk, or method-card IDs are preserved as `None` so validators can
        distinguish partial references from empty strings.
        """
        return {
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "locator": _jsonable(self.locator),
            "method_card_id": self.method_card_id,
            "claim": self.claim,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceReference":
        """Parse an evidence reference from JSON-compatible artifact data.

        Optional identifiers and claim text remain optional, while locator payloads
        are normalized to mappings so citation validation can compare fields
        against stored chunk locators.
        """
        return cls(
            source_id=str(payload["source_id"]) if payload.get("source_id") is not None else None,
            chunk_id=str(payload["chunk_id"]) if payload.get("chunk_id") is not None else None,
            locator=_mapping(payload.get("locator")),
            method_card_id=str(payload["method_card_id"]) if payload.get("method_card_id") is not None else None,
            claim=str(payload["claim"]) if payload.get("claim") is not None else None,
        )


@dataclass(frozen=True)
class EvidenceBackedField:
    """Nullable methodology field value with field-level citation evidence.

    Rich methodology artifacts can leave fields unset when a source does not
    support them. When a value is populated, at least one evidence reference is
    required so later extraction, validation, and strategy generation can explain
    exactly which chunk or source backs the claim.
    """

    value: Any | None = None
    evidence_refs: tuple[EvidenceReference, ...] = tuple()
    confidence: float | None = None
    quality: str | None = None
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()

    def __post_init__(self) -> None:
        if _has_methodology_value(self.value) and not self.evidence_refs:
            raise ValueError("populated methodology field requires evidence_refs")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("field confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        """Serialize a nullable field value, evidence refs, and quality metadata."""
        return {
            "value": _jsonable(self.value),
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "confidence": self.confidence,
            "quality": self.quality,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceBackedField":
        """Parse one evidence-backed field from JSON-compatible payload data."""
        return cls(
            value=payload.get("value"),
            evidence_refs=tuple(
                EvidenceReference.from_dict(_mapping(item))
                for item in _sequence(payload.get("evidence_refs"))
            ),
            confidence=float(payload["confidence"]) if payload.get("confidence") is not None else None,
            quality=str(payload["quality"]) if payload.get("quality") is not None else None,
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
        )


@dataclass(frozen=True)
class MethodologyCandidate:
    """Source-backed methodology candidate before method-card approval.

    Candidates describe what an ingested source appears to contain without making
    it executable. They carry candidate spans plus nullable rich fields so later
    extraction and validation can add evidence-backed structure before a draft
    method card is created.
    """

    methodology_candidate_id: str
    title: str
    families: tuple[str, ...]
    status: str = "discovered"
    source_ids: tuple[str, ...] = tuple()
    chunk_ids: tuple[str, ...] = tuple()
    candidate_spans: tuple[Mapping[str, Any], ...] = tuple()
    core_fields: Mapping[str, Mapping[str, EvidenceBackedField]] = field(default_factory=dict)
    extension_fields: Mapping[str, Mapping[str, EvidenceBackedField]] = field(default_factory=dict)
    lineage: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.methodology_candidate_id.strip():
            raise ValueError("methodology_candidate_id is required")
        if not self.title.strip():
            raise ValueError("methodology candidate title is required")
        if self.status not in METHODOLOGY_CANDIDATE_STATUSES:
            allowed = ", ".join(sorted(METHODOLOGY_CANDIDATE_STATUSES))
            raise ValueError(f"unsupported methodology candidate status: {self.status}; allowed values: {allowed}")
        object.__setattr__(
            self,
            "core_fields",
            _normalize_methodology_field_groups(
                self.core_fields,
                schema=METHODOLOGY_CORE_FIELD_SCHEMA,
                scope="core_fields",
            ),
        )
        object.__setattr__(
            self,
            "extension_fields",
            _normalize_methodology_field_groups(
                self.extension_fields,
                schema=METHODOLOGY_EXTENSION_FIELD_SCHEMA,
                scope="extension_fields",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the methodology candidate with candidate spans and rich fields."""
        return {
            "artifact_type": "methodology_candidate",
            "schema_version": self.schema_version,
            "methodology_candidate_id": self.methodology_candidate_id,
            "title": self.title,
            "families": list(self.families),
            "status": self.status,
            "source_ids": list(self.source_ids),
            "chunk_ids": list(self.chunk_ids),
            "candidate_spans": _jsonable(list(self.candidate_spans)),
            "core_fields": _serialize_methodology_field_groups(self.core_fields),
            "extension_fields": _serialize_methodology_field_groups(self.extension_fields),
            "lineage": _jsonable(self.lineage),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodologyCandidate":
        """Parse a persisted methodology-candidate payload."""
        return cls(
            methodology_candidate_id=str(payload.get("methodology_candidate_id") or ""),
            title=str(payload.get("title") or ""),
            families=_string_tuple(payload.get("families")),
            status=str(payload.get("status") or "discovered"),
            source_ids=_string_tuple(payload.get("source_ids")),
            chunk_ids=_string_tuple(payload.get("chunk_ids")),
            candidate_spans=tuple(_mapping(item) for item in _sequence(payload.get("candidate_spans"))),
            core_fields=_mapping(payload.get("core_fields")),
            extension_fields=_mapping(payload.get("extension_fields")),
            lineage=_mapping(payload.get("lineage")),
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MethodologyEvidencePacket:
    """Role-labeled evidence assembled before rich methodology field extraction.

    The packet is the inspectable bridge between open-world methodology discovery
    and closed-schema extraction. It records which family-level evidence roles
    were found, which roles are missing for the requested readiness goal, and the
    exact source/chunk/hash evidence available to field extractors.
    """

    evidence_packet_id: str
    methodology_candidate_id: str
    family: str
    readiness_goal: str = "descriptive"
    status: str = "assembled"
    candidate_ref: Mapping[str, Any] = field(default_factory=dict)
    source_ids: tuple[str, ...] = tuple()
    chunk_ids: tuple[str, ...] = tuple()
    profile_version: str = "1"
    role_evidence: tuple[Mapping[str, Any], ...] = tuple()
    missing_roles: tuple[str, ...] = tuple()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.evidence_packet_id.strip():
            raise ValueError("evidence_packet_id is required")
        if not self.methodology_candidate_id.strip():
            raise ValueError("methodology_candidate_id is required")
        if not self.family.strip():
            raise ValueError("methodology evidence packet family is required")
        if self.status not in METHODOLOGY_EVIDENCE_PACKET_STATUSES:
            allowed = ", ".join(sorted(METHODOLOGY_EVIDENCE_PACKET_STATUSES))
            raise ValueError(f"unsupported evidence packet status: {self.status}; allowed values: {allowed}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the role-labeled evidence packet for DB-backed persistence."""
        return {
            "artifact_type": "methodology_evidence_packet",
            "schema_version": self.schema_version,
            "evidence_packet_id": self.evidence_packet_id,
            "methodology_candidate_id": self.methodology_candidate_id,
            "family": self.family,
            "readiness_goal": self.readiness_goal,
            "status": self.status,
            "candidate_ref": _jsonable(self.candidate_ref),
            "source_ids": list(self.source_ids),
            "chunk_ids": list(self.chunk_ids),
            "profile_version": self.profile_version,
            "role_evidence": _jsonable(list(self.role_evidence)),
            "missing_roles": list(self.missing_roles),
            "diagnostics": _jsonable(self.diagnostics),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodologyEvidencePacket":
        """Parse a persisted methodology evidence packet payload."""
        return cls(
            evidence_packet_id=str(payload.get("evidence_packet_id") or ""),
            methodology_candidate_id=str(payload.get("methodology_candidate_id") or ""),
            family=str(payload.get("family") or ""),
            readiness_goal=str(payload.get("readiness_goal") or "descriptive"),
            status=str(payload.get("status") or "assembled"),
            candidate_ref=_mapping(payload.get("candidate_ref")),
            source_ids=_string_tuple(payload.get("source_ids")),
            chunk_ids=_string_tuple(payload.get("chunk_ids")),
            profile_version=str(payload.get("profile_version") or "1"),
            role_evidence=tuple(_mapping(item) for item in _sequence(payload.get("role_evidence"))),
            missing_roles=_string_tuple(payload.get("missing_roles")),
            diagnostics=_mapping(payload.get("diagnostics")),
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class RichMethodCard:
    """Method-card artifact with rich, evidence-backed methodology fields.

    Rich cards keep the existing method-card artifact types for compatibility:
    drafts serialize as `method_card_draft`, while approved cards serialize as
    `method_card`. The `card_format` marker tells richer tools that nullable core
    fields and extension blocks are available.
    """

    method_card_id: str
    method_id: str
    title: str
    family: str
    status: str
    assumptions: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    failure_modes: tuple[str, ...]
    evidence_refs: tuple[EvidenceReference, ...] = tuple()
    core_fields: Mapping[str, Mapping[str, EvidenceBackedField]] = field(default_factory=dict)
    extension_fields: Mapping[str, Mapping[str, EvidenceBackedField]] = field(default_factory=dict)
    source_methodology_candidate_id: str | None = None
    validation_refs: tuple[Mapping[str, Any], ...] = tuple()
    lineage: Mapping[str, Any] = field(default_factory=dict)
    version: int = 1
    source_method_card_id: str | None = None
    approved_by: str | None = None
    approval_note: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.method_card_id.strip():
            raise ValueError("method_card_id is required")
        if not self.method_id.strip():
            raise ValueError("method_id is required")
        if self.status not in METHOD_CARD_STATUSES:
            raise ValueError(f"unsupported method-card status: {self.status}")
        object.__setattr__(
            self,
            "core_fields",
            _normalize_methodology_field_groups(
                self.core_fields,
                schema=METHODOLOGY_CORE_FIELD_SCHEMA,
                scope="core_fields",
            ),
        )
        object.__setattr__(
            self,
            "extension_fields",
            _normalize_methodology_field_groups(
                self.extension_fields,
                schema=METHODOLOGY_EXTENSION_FIELD_SCHEMA,
                scope="extension_fields",
            ),
        )

    @property
    def approved(self) -> bool:
        """Return whether this rich card is approved for implementation evidence citations."""
        return self.status == "approved"

    def to_method_card(self) -> "MethodCard":
        """Return the shallow method-card projection used by legacy searches."""
        return MethodCard(
            method_card_id=self.method_card_id,
            method_id=self.method_id,
            title=self.title,
            family=self.family,
            status=self.status,
            assumptions=self.assumptions,
            inputs=self.inputs,
            outputs=self.outputs,
            failure_modes=self.failure_modes,
            evidence_refs=self.evidence_refs,
            version=self.version,
            source_method_card_id=self.source_method_card_id,
            approved_by=self.approved_by,
            approval_note=self.approval_note,
            created_at=self.created_at,
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the rich card while preserving method-card compatibility fields."""
        return {
            "artifact_type": "method_card_draft" if self.status == "draft" else "method_card",
            "card_format": RICH_METHOD_CARD_FORMAT,
            "schema_version": self.schema_version,
            "method_card_id": self.method_card_id,
            "method_id": self.method_id,
            "title": self.title,
            "family": self.family,
            "status": self.status,
            "version": self.version,
            "assumptions": list(self.assumptions),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "failure_modes": list(self.failure_modes),
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "core_fields": _serialize_methodology_field_groups(self.core_fields),
            "extension_fields": _serialize_methodology_field_groups(self.extension_fields),
            "source_methodology_candidate_id": self.source_methodology_candidate_id,
            "validation_refs": _jsonable(list(self.validation_refs)),
            "lineage": _jsonable(self.lineage),
            "source_method_card_id": self.source_method_card_id,
            "approved_by": self.approved_by,
            "approval_note": self.approval_note,
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RichMethodCard":
        """Parse a rich method-card payload while normalizing field-level evidence."""
        return cls(
            method_card_id=str(payload.get("method_card_id") or ""),
            method_id=str(payload.get("method_id") or ""),
            title=str(payload.get("title") or ""),
            family=str(payload.get("family") or ""),
            status=str(payload.get("status") or "planned"),
            assumptions=_string_tuple(payload.get("assumptions")),
            inputs=_string_tuple(payload.get("inputs")),
            outputs=_string_tuple(payload.get("outputs")),
            failure_modes=_string_tuple(payload.get("failure_modes")),
            evidence_refs=tuple(
                EvidenceReference.from_dict(_mapping(item))
                for item in _sequence(payload.get("evidence_refs"))
            ),
            core_fields=_mapping(payload.get("core_fields")),
            extension_fields=_mapping(payload.get("extension_fields")),
            source_methodology_candidate_id=str(payload["source_methodology_candidate_id"])
            if payload.get("source_methodology_candidate_id") is not None
            else None,
            validation_refs=tuple(_mapping(item) for item in _sequence(payload.get("validation_refs"))),
            lineage=_mapping(payload.get("lineage")),
            version=int(payload.get("version") or 1),
            source_method_card_id=str(payload["source_method_card_id"])
            if payload.get("source_method_card_id") is not None
            else None,
            approved_by=str(payload["approved_by"]) if payload.get("approved_by") is not None else None,
            approval_note=str(payload["approval_note"]) if payload.get("approval_note") is not None else None,
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MethodologyFieldExtractionReport:
    """Audit report for deterministic rich-field extraction from a candidate."""

    extraction_id: str
    methodology_candidate_id: str
    status: str
    evidence_packet_id: str | None = None
    candidate_ref: Mapping[str, Any] = field(default_factory=dict)
    source_ids: tuple[str, ...] = tuple()
    chunk_ids: tuple[str, ...] = tuple()
    extraction_engine: str = "deterministic_rules"
    populated_field_count: int = 0
    populated_fields: tuple[str, ...] = tuple()
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.extraction_id.strip():
            raise ValueError("extraction_id is required")
        if not self.methodology_candidate_id.strip():
            raise ValueError("methodology_candidate_id is required")
        if self.status not in {"extracted", "blocked"}:
            raise ValueError(f"unsupported methodology extraction status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize extraction status and populated-field evidence summary."""
        return {
            "artifact_type": "methodology_field_extraction_report",
            "schema_version": self.schema_version,
            "extraction_id": self.extraction_id,
            "methodology_candidate_id": self.methodology_candidate_id,
            "status": self.status,
            "evidence_packet_id": self.evidence_packet_id,
            "candidate_ref": _jsonable(self.candidate_ref),
            "source_ids": list(self.source_ids),
            "chunk_ids": list(self.chunk_ids),
            "extraction_engine": self.extraction_engine,
            "populated_field_count": self.populated_field_count,
            "populated_fields": list(self.populated_fields),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodologyFieldExtractionReport":
        """Parse a stored methodology field-extraction report."""
        return cls(
            extraction_id=str(payload.get("extraction_id") or ""),
            methodology_candidate_id=str(payload.get("methodology_candidate_id") or ""),
            status=str(payload.get("status") or ""),
            evidence_packet_id=str(payload["evidence_packet_id"])
            if payload.get("evidence_packet_id") is not None
            else None,
            candidate_ref=_mapping(payload.get("candidate_ref")),
            source_ids=_string_tuple(payload.get("source_ids")),
            chunk_ids=_string_tuple(payload.get("chunk_ids")),
            extraction_engine=str(payload.get("extraction_engine") or "deterministic_rules"),
            populated_field_count=int(payload.get("populated_field_count") or 0),
            populated_fields=_string_tuple(payload.get("populated_fields")),
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MethodologyCandidateValidationReport:
    """Validation report for a rich methodology candidate before draft-card creation."""

    validation_id: str
    methodology_candidate_id: str
    status: str
    valid: bool
    candidate_ref: Mapping[str, Any] = field(default_factory=dict)
    checked_refs: tuple[Mapping[str, Any], ...] = tuple()
    field_summary: Mapping[str, Any] = field(default_factory=dict)
    source_summary: Mapping[str, Any] = field(default_factory=dict)
    readiness_summary: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.validation_id.strip():
            raise ValueError("validation_id is required")
        if not self.methodology_candidate_id.strip():
            raise ValueError("methodology_candidate_id is required")
        if self.status not in {"passed", "blocked"}:
            raise ValueError(f"unsupported methodology validation status: {self.status}")
        if self.valid != (self.status == "passed"):
            raise ValueError("methodology validation valid flag must match status")

    def to_dict(self) -> dict[str, Any]:
        """Serialize validation status, checked refs, warnings, and blockers."""
        return {
            "artifact_type": "methodology_candidate_validation_report",
            "schema_version": self.schema_version,
            "validation_id": self.validation_id,
            "methodology_candidate_id": self.methodology_candidate_id,
            "status": self.status,
            "valid": self.valid,
            "candidate_ref": _jsonable(self.candidate_ref),
            "checked_refs": _jsonable(list(self.checked_refs)),
            "field_summary": _jsonable(self.field_summary),
            "source_summary": _jsonable(self.source_summary),
            "readiness_summary": _jsonable(self.readiness_summary),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodologyCandidateValidationReport":
        """Parse a stored methodology-candidate validation report."""
        return cls(
            validation_id=str(payload.get("validation_id") or ""),
            methodology_candidate_id=str(payload.get("methodology_candidate_id") or ""),
            status=str(payload.get("status") or ""),
            valid=bool(payload.get("valid")),
            candidate_ref=_mapping(payload.get("candidate_ref")),
            checked_refs=tuple(_mapping(item) for item in _sequence(payload.get("checked_refs"))),
            field_summary=_mapping(payload.get("field_summary")),
            source_summary=_mapping(payload.get("source_summary")),
            readiness_summary=_mapping(payload.get("readiness_summary")),
            warnings=_string_tuple(payload.get("warnings")),
            blockers=_string_tuple(payload.get("blockers")),
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class MethodCard:
    """Curated contract for a quantitative method and its evidence base.

    Method cards describe the method family, assumptions, inputs, outputs, failure
    modes, supporting evidence references, approval status, and version lineage.
    Draft cards can be created from validated source evidence; approved cards are
    the stable artifacts that method implementations and research tools are
    expected to cite.
    """

    method_card_id: str
    method_id: str
    title: str
    family: str
    status: str
    assumptions: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    failure_modes: tuple[str, ...]
    evidence_refs: tuple[EvidenceReference, ...] = tuple()
    version: int = 1
    source_method_card_id: str | None = None
    approved_by: str | None = None
    approval_note: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.method_card_id.strip():
            raise ValueError("method_card_id is required")
        if not self.method_id.strip():
            raise ValueError("method_id is required")
        if self.status not in METHOD_CARD_STATUSES:
            raise ValueError(f"unsupported method-card status: {self.status}")

    @property
    def approved(self) -> bool:
        """Return whether this method card is approved for implementation evidence citations."""
        return self.status == "approved"

    def to_dict(self) -> dict[str, Any]:
        """Serialize method-card contract fields, evidence refs, and approval metadata.

        Draft cards emit the draft artifact type, approved/planned cards emit the
        method-card artifact type, and all tuple fields are converted to lists for
        persistence or tool-envelope payloads.
        """
        return {
            "artifact_type": "method_card_draft" if self.status == "draft" else "method_card",
            "schema_version": self.schema_version,
            "method_card_id": self.method_card_id,
            "method_id": self.method_id,
            "title": self.title,
            "family": self.family,
            "status": self.status,
            "version": self.version,
            "assumptions": list(self.assumptions),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "failure_modes": list(self.failure_modes),
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "source_method_card_id": self.source_method_card_id,
            "approved_by": self.approved_by,
            "approval_note": self.approval_note,
            "created_at": _jsonable(self.created_at),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MethodCard":
        """Parse a method-card payload from seeded data or persisted artifacts.

        Evidence references, tuple fields, approval metadata, timestamps, status,
        version, and schema version are normalized before the constructor enforces
        method-card identity and allowed status values.
        """
        return cls(
            method_card_id=str(payload.get("method_card_id") or ""),
            method_id=str(payload.get("method_id") or ""),
            title=str(payload.get("title") or ""),
            family=str(payload.get("family") or ""),
            status=str(payload.get("status") or "planned"),
            assumptions=_string_tuple(payload.get("assumptions")),
            inputs=_string_tuple(payload.get("inputs")),
            outputs=_string_tuple(payload.get("outputs")),
            failure_modes=_string_tuple(payload.get("failure_modes")),
            evidence_refs=tuple(EvidenceReference.from_dict(_mapping(item)) for item in _sequence(payload.get("evidence_refs"))),
            version=int(payload.get("version") or 1),
            source_method_card_id=str(payload["source_method_card_id"])
            if payload.get("source_method_card_id") is not None
            else None,
            approved_by=str(payload["approved_by"]) if payload.get("approved_by") is not None else None,
            approval_note=str(payload["approval_note"]) if payload.get("approval_note") is not None else None,
            created_at=_parse_datetime(payload.get("created_at")),
            schema_version=str(payload.get("schema_version") or KNOWLEDGE_SCHEMA_VERSION),
        )


@dataclass(frozen=True)
class EvidenceRetrievalReport:
    """Retrieval artifact containing ranked chunks that downstream agents may cite.

    The report stores the original query, applied filters, and JSON-compatible
    result rows that include source/chunk identifiers and locators. It provides a
    reviewable bridge between search execution and later method-card or artifact
    citations.
    """

    retrieval_id: str
    query: str
    results: tuple[Mapping[str, Any], ...]
    filters: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize retrieval results, filters, query, and creation timestamp.

        Result rows are normalized recursively so downstream agents can cite
        returned chunk/source identifiers without depending on store-specific row
        objects.
        """
        return {
            "artifact_type": "evidence_retrieval_report",
            "schema_version": self.schema_version,
            "retrieval_id": self.retrieval_id,
            "query": self.query,
            "filters": _jsonable(self.filters),
            "results": _jsonable(list(self.results)),
            "created_at": _jsonable(self.created_at),
        }


@dataclass(frozen=True)
class EvidenceChunkDereferenceReport:
    """Dereference artifact for turning chunk IDs back into bounded source text.

    The report preserves the requested IDs, resolved chunk payloads, missing IDs,
    filters, and warnings so a tool can supply evidence context without silently
    dropping unresolved references. It is useful when generation or validation
    needs exact text rather than only search result metadata.
    """

    dereference_id: str
    requested_chunk_ids: tuple[str, ...]
    chunks: tuple[Mapping[str, Any], ...]
    missing_chunk_ids: tuple[str, ...] = tuple()
    filters: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize dereferenced chunk payloads together with missing IDs and warnings.

        The report includes request filters and counts so callers can verify that
        the evidence context contains exactly the chunks they asked to inspect.
        """
        return {
            "artifact_type": "evidence_chunk_dereference_report",
            "schema_version": self.schema_version,
            "dereference_id": self.dereference_id,
            "requested_chunk_ids": list(self.requested_chunk_ids),
            "filters": _jsonable(self.filters),
            "chunk_count": len(self.chunks),
            "chunks": _jsonable(list(self.chunks)),
            "missing_chunk_ids": list(self.missing_chunk_ids),
            "warnings": list(self.warnings),
            "created_at": _jsonable(self.created_at),
        }


@dataclass(frozen=True)
class CitationValidationReport:
    """Audit record for citation checks against knowledge-store state.

    The report captures every checked reference, whether all required evidence was
    valid, and the warnings or blockers produced during lookup. Tool envelopes use
    this object to expose the full validation trail even when invalid citations
    cause the command to return an error.
    """

    validation_id: str
    valid: bool
    checked_refs: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...] = tuple()
    blockers: tuple[str, ...] = tuple()
    created_at: datetime = field(default_factory=_utc_now)
    schema_version: str = KNOWLEDGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize citation-validation results with checked references and blockers.

        The report preserves every checked reference, warning, blocker, and
        validation status so failed tool envelopes still contain a complete audit
        trail for review.
        """
        return {
            "artifact_type": "citation_validation_report",
            "schema_version": self.schema_version,
            "validation_id": self.validation_id,
            "valid": self.valid,
            "checked_refs": _jsonable(list(self.checked_refs)),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "created_at": _jsonable(self.created_at),
        }


def _normalize_methodology_field_groups(
    groups: Mapping[str, Mapping[str, Any]],
    *,
    schema: Mapping[str, frozenset[str]],
    scope: str,
) -> dict[str, dict[str, EvidenceBackedField]]:
    normalized: dict[str, dict[str, EvidenceBackedField]] = {}
    for group_name, raw_fields in groups.items():
        group = str(group_name)
        if group not in schema:
            allowed = ", ".join(sorted(schema))
            raise ValueError(f"unsupported {scope} group: {group}; allowed values: {allowed}")
        fields = _mapping(raw_fields)
        normalized_fields: dict[str, EvidenceBackedField] = {}
        for field_name, raw_field in fields.items():
            name = str(field_name)
            if name not in schema[group]:
                allowed = ", ".join(sorted(schema[group]))
                raise ValueError(f"unsupported {scope} field for {group}: {name}; allowed values: {allowed}")
            normalized_fields[name] = _coerce_evidence_backed_field(raw_field)
        normalized[group] = normalized_fields
    return normalized


def _coerce_evidence_backed_field(value: Any) -> EvidenceBackedField:
    if isinstance(value, EvidenceBackedField):
        return value
    if isinstance(value, Mapping):
        return EvidenceBackedField.from_dict(value)
    return EvidenceBackedField(value=value)


def _serialize_methodology_field_groups(
    groups: Mapping[str, Mapping[str, EvidenceBackedField]],
) -> dict[str, dict[str, Any]]:
    return {
        group: {name: field.to_dict() for name, field in fields.items()}
        for group, fields in groups.items()
    }


def _has_methodology_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return bool(value)
    return True


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return _utc_now()


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return value
    return (value,)


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(value) if str(item).strip())
