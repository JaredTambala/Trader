"""Methodology-candidate discovery services for Quant Methods sources."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from trader_research.artifact_store import ResearchArtifactStore, ResearchArtifactStoreError
from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import METHODOLOGY_CANDIDATE, stable_research_id

from .domain import KnowledgeChunk, KnowledgeSourceManifest, MethodologyCandidate
from .embeddings import EmbeddingProvider
from .index import search_chunks
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES = "knowledge_discover_methodology_candidates"

FAMILY_KEYWORDS: Mapping[str, tuple[str, ...]] = {
    "technical_indicators": (
        "indicator",
        "moving average",
        "rsi",
        "relative strength",
        "oscillator",
        "signal line",
    ),
    "statistical_arbitrage": (
        "pairs trading",
        "pair trading",
        "statistical arbitrage",
        "cointegration",
        "spread",
        "hedge ratio",
        "stationarity",
        "z-score",
        "mean reversion",
    ),
    "options_derivatives": (
        "option",
        "straddle",
        "call",
        "put",
        "strike",
        "expiry",
        "delta",
        "vega",
    ),
    "fundamental_valuation": (
        "valuation",
        "discounted cash flow",
        "earnings",
        "book value",
        "financial statement",
        "fundamental",
    ),
    "sentiment_alternative_data": (
        "sentiment",
        "news",
        "alternative data",
        "commodity",
        "social media",
        "textual",
    ),
    "portfolio_construction": (
        "portfolio construction",
        "allocation",
        "optimization",
        "rebalance",
        "risk budget",
        "diversification",
    ),
    "risk_models": (
        "risk model",
        "value at risk",
        "var",
        "cvar",
        "covariance",
        "correlation",
        "stress",
        "limit",
    ),
    "execution_methods": (
        "execution",
        "twap",
        "vwap",
        "order slicing",
        "market impact",
        "slippage",
        "participation rate",
    ),
}

_METHOD_LABEL_PATTERNS = (
    re.compile(
        r"(?:^|[.;]\s+)([A-Z][A-Za-z][A-Za-z0-9 /,+-]{2,90}?)\s*\(([A-Z][A-Z0-9]{1,12})\)\s*:"
    ),
    re.compile(r"(?:^|[.;]\s+)([A-Z][A-Za-z][A-Za-z0-9 /,+-]{2,90}?)\s*\(([A-Z][A-Z0-9]{1,12})\)"),
    re.compile(r"(?:^|[.;]\s+)([A-Z][A-Za-z][A-Za-z0-9 /,+-]{2,90}?)\s+Rule\s*:"),
)

_GENERIC_IDENTITY_WORDS = frozenset(
    {
        "method",
        "methods",
        "trading",
        "strategy",
        "strategies",
        "technical",
        "indicator",
        "indicators",
        "source",
        "page",
        "chapter",
        "section",
        "rule",
        "rules",
    }
)


def discover_methodology_candidates(
    *,
    artifact_root: str | Path,
    query: str | None = None,
    source_ids: Sequence[str] | None = None,
    method_families: Sequence[str] | None = None,
    top_k: int = 25,
    neighbor_radius: int = 1,
    max_candidates: int = 10,
    approved_only: bool = True,
    embedding_provider: EmbeddingProvider | None = None,
    knowledge_store: KnowledgeStore | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Discover source-backed methodology candidates without approving methods."""
    if artifact_store is None:
        return _artifact_store_unavailable("research artifact store is required")
    normalized_query = (query or "").strip()
    normalized_source_ids = tuple(dict.fromkeys(str(item).strip() for item in (source_ids or ()) if str(item).strip()))
    normalized_families = _normalize_families(method_families or ())
    if not normalized_query and not normalized_source_ids and not normalized_families:
        return error_envelope(
            command=KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="validation_error",
            message="query, source_ids, or method_families is required",
        )
    if top_k < 1 or top_k > 25:
        return _validation_error("top_k must be between 1 and 25")
    if neighbor_radius < 0 or neighbor_radius > 5:
        return _validation_error("neighbor_radius must be between 0 and 5")
    if max_candidates < 1 or max_candidates > 25:
        return _validation_error("max_candidates must be between 1 and 25")

    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    try:
        sources = _load_sources(store, normalized_source_ids)
        chunks = _candidate_seed_chunks(
            store,
            normalized_query,
            normalized_source_ids,
            normalized_families,
            top_k=top_k,
            approved_only=approved_only,
            embedding_provider=embedding_provider,
        )
        if normalized_source_ids:
            missing = tuple(source_id for source_id in normalized_source_ids if source_id not in sources)
            if missing:
                return _validation_error(f"unknown source_id: {', '.join(missing)}")
            empty_sources = tuple(source_id for source_id in normalized_source_ids if not store.load_chunks(source_id))
            if empty_sources:
                return _validation_error(f"source has no indexed chunks: {', '.join(empty_sources)}")
        all_chunks_by_source = {
            source_id: tuple(store.load_chunks(source_id))
            for source_id in sorted({chunk.source_id for chunk in chunks} | set(normalized_source_ids))
        }
        for source_id in all_chunks_by_source:
            if source_id not in sources:
                source = store.load_source(source_id)
                if source is not None:
                    sources[source_id] = source
    except (KnowledgeStoreError, ValueError) as exc:
        return error_envelope(
            command=KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="methodology_discovery_error",
            message=str(exc),
        )

    candidates = _build_candidates(
        chunks,
        chunks_by_source=all_chunks_by_source,
        sources=sources,
        method_families=normalized_families,
        query=normalized_query,
        neighbor_radius=neighbor_radius,
        max_candidates=max_candidates,
    )
    if not candidates:
        return error_envelope(
            command=KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="methodology_discovery_blocked",
            message="no methodology candidates were discovered",
            data={"candidate_count": 0},
        )

    records = []
    try:
        for candidate in candidates:
            records.append(
                artifact_store.save_artifact(
                    artifact_type=METHODOLOGY_CANDIDATE,
                    artifact_id=candidate.methodology_candidate_id,
                    payload=candidate.to_dict(),
                    status=candidate.status,
                    metadata={
                        "families": list(candidate.families),
                        "source_ids": list(candidate.source_ids),
                        "chunk_ids": list(candidate.chunk_ids),
                        "method_identity": dict(candidate.method_identity),
                    },
                )
            )
    except ResearchArtifactStoreError as exc:
        return _artifact_store_unavailable(str(exc))

    return success_envelope(
        command=KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={
            "methodology_candidates": [candidate.to_dict() for candidate in candidates],
            "candidate_count": len(candidates),
        },
        artifacts={
            "methodology_candidates": [record.reference().to_dict() for record in records],
        },
        warnings=tuple() if candidates else ("no methodology candidates were discovered",),
    )


def _candidate_seed_chunks(
    store: KnowledgeStore,
    query: str,
    source_ids: Sequence[str],
    method_families: Sequence[str],
    *,
    top_k: int,
    approved_only: bool,
    embedding_provider: EmbeddingProvider | None,
) -> tuple[KnowledgeChunk, ...]:
    if source_ids:
        chunks: list[KnowledgeChunk] = []
        for source_id in source_ids:
            chunks.extend(store.load_chunks(source_id))
        return tuple(chunks[: max(top_k, 1) * 5])

    if query or (method_families and not source_ids):
        if embedding_provider is None:
            raise ValueError("embedding_provider is required for retrieval-backed discovery")
        rows: list[Mapping[str, Any]] = []
        retrieval_query = query or " ".join(method_families)
        families = method_families or (None,)
        for family in families:
            rows.extend(
                search_chunks(
                    store,
                    retrieval_query,
                    source_ids=source_ids or None,
                    method_family=family,
                    top_k=top_k,
                    provider=embedding_provider,
                    approved_only=approved_only,
                )
            )
        chunk_ids = tuple(dict.fromkeys(str(row.get("chunk_id")) for row in rows if row.get("chunk_id")))
        return store.load_chunks_by_ids(chunk_ids)

    return tuple()


def _build_candidates(
    seed_chunks: Sequence[KnowledgeChunk],
    *,
    chunks_by_source: Mapping[str, Sequence[KnowledgeChunk]],
    sources: Mapping[str, KnowledgeSourceManifest],
    method_families: Sequence[str],
    query: str,
    neighbor_radius: int,
    max_candidates: int,
) -> tuple[MethodologyCandidate, ...]:
    groups: dict[tuple[str, str, tuple[str, ...]], dict[str, KnowledgeChunk]] = {}
    identities: dict[tuple[str, str, tuple[str, ...]], Mapping[str, Any]] = {}
    headings: dict[tuple[str, str, tuple[str, ...]], str] = {}
    for chunk in seed_chunks:
        source_chunks = chunks_by_source.get(chunk.source_id, ())
        expanded = _expand_neighbors(chunk, source_chunks, neighbor_radius)
        discovered_identities = _discover_method_identities(chunk, expanded, query=query)
        families_for_expanded = _candidate_families(expanded, sources.get(chunk.source_id), method_families)
        if not discovered_identities or not families_for_expanded:
            continue
        heading = _group_heading(chunk)
        for identity in discovered_identities:
            bound_chunks = _identity_bound_chunks(identity, expanded, seed_chunk=chunk, query=query)
            families = _candidate_families(bound_chunks, sources.get(chunk.source_id), method_families)
            if not families:
                continue
            key = (chunk.source_id, str(identity["identity_key"]), families)
            groups.setdefault(key, {})
            identities[key] = _identity_with_context(identity, bound_chunks)
            headings.setdefault(key, heading)
            for expanded_chunk in bound_chunks:
                groups[key][expanded_chunk.chunk_id] = expanded_chunk

    seen_chunk_sets: set[tuple[str, ...]] = set()
    candidates: list[MethodologyCandidate] = []
    for key, chunk_by_id in sorted(groups.items(), key=lambda item: item[0]):
        source_id, _identity_key, families = key
        heading = headings.get(key, "")
        identity = identities[key]
        ordered_chunks = tuple(sorted(chunk_by_id.values(), key=lambda item: (item.source_id, item.ordinal, item.chunk_id)))
        chunk_ids = tuple(chunk.chunk_id for chunk in ordered_chunks)
        if chunk_ids in seen_chunk_sets:
            continue
        seen_chunk_sets.add(chunk_ids)
        source = sources.get(source_id)
        title = str(identity.get("canonical_name") or identity.get("source_name") or "")
        if not title:
            title = _candidate_title(heading, families, source, ordered_chunks=ordered_chunks, query=query)
        candidate_id = stable_research_id(
            "methodology_candidate",
            {
                "source_id": source_id,
                "chunk_ids": list(chunk_ids),
                "families": list(families),
                "title": title,
                "method_identity": identity,
            },
        )
        candidates.append(
            MethodologyCandidate(
                methodology_candidate_id=candidate_id,
                title=title,
                families=families,
                status="discovered",
                source_ids=(source_id,),
                chunk_ids=chunk_ids,
                candidate_spans=(
                    {
                        "source_id": source_id,
                        "heading": heading,
                        "chunk_ids": list(chunk_ids),
                        "evidence_unit_ids": list(chunk_ids),
                        "ordinals": [chunk.ordinal for chunk in ordered_chunks],
                        "locators": [dict(chunk.locator) for chunk in ordered_chunks],
                        "method_identity": identity,
                    },
                ),
                method_identity=identity,
                lineage={
                    "discovery": {
                        "query": query,
                        "method_families": list(method_families),
                        "source_types": [source.source_type] if source is not None else [],
                        "candidate_name_evidence": _candidate_name_evidence(heading, ordered_chunks, query, identity),
                        "family_attribution": _family_attribution(ordered_chunks, families),
                        "source_family_metadata_used_as_label": False,
                        "identity_grouping": {
                            "identity_key": identity.get("identity_key"),
                            "canonical_name": identity.get("canonical_name"),
                            "aliases": list(identity.get("aliases") or ()),
                            "identity_evidence_unit_ids": list(identity.get("identity_evidence_unit_ids") or ()),
                            "query_alignment": identity.get("query_alignment"),
                            "competing_method_labels": list(identity.get("competing_method_labels") or ()),
                        },
                    }
                },
            )
        )
        if len(candidates) >= max_candidates:
            break
    return tuple(candidates)


def _expand_neighbors(
    chunk: KnowledgeChunk,
    source_chunks: Sequence[KnowledgeChunk],
    neighbor_radius: int,
) -> tuple[KnowledgeChunk, ...]:
    lower = chunk.ordinal - neighbor_radius
    upper = chunk.ordinal + neighbor_radius
    return tuple(
        item
        for item in sorted(source_chunks, key=lambda candidate: (candidate.ordinal, candidate.chunk_id))
        if lower <= item.ordinal <= upper
    ) or (chunk,)


def _candidate_families(
    chunks: Sequence[KnowledgeChunk],
    source: KnowledgeSourceManifest | None,
    requested_families: Sequence[str],
) -> tuple[str, ...]:
    requested = set(requested_families)
    detected: set[str] = set()
    for chunk in chunks:
        text = chunk.text.lower()
        for family, keywords in FAMILY_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                detected.add(family)
    if requested and not detected and source is not None:
        source_families = set(source.method_families)
        detected.update(requested & source_families)
    if requested:
        detected &= requested
    return tuple(sorted(detected))


def _discover_method_identities(
    seed_chunk: KnowledgeChunk,
    expanded_chunks: Sequence[KnowledgeChunk],
    *,
    query: str,
) -> tuple[Mapping[str, Any], ...]:
    mentions: list[Mapping[str, Any]] = []
    for chunk in expanded_chunks:
        mentions.extend(_label_mentions(chunk))

    heading = _group_heading(seed_chunk)
    if heading and not _is_generic_heading(heading) and _heading_identity_supported(seed_chunk, heading, query):
        mentions.append(
            {
                "source_name": heading,
                "aliases": (),
                "abbreviations": (),
                "chunk_id": seed_chunk.chunk_id,
                "locator": dict(seed_chunk.locator),
                "evidence": "heading",
                "confidence": 0.75,
            }
        )

    query_identity = _query_identity(seed_chunk, query)
    if query_identity is not None:
        mentions.append(query_identity)

    if not mentions:
        return tuple()

    by_key: dict[str, dict[str, Any]] = {}
    for mention in mentions:
        source_name = str(mention.get("source_name") or "").strip()
        if not source_name or _is_generic_identity(source_name):
            continue
        aliases = tuple(dict.fromkeys(str(alias).strip() for alias in mention.get("aliases") or () if str(alias).strip()))
        abbreviations = tuple(
            dict.fromkeys(str(alias).strip() for alias in mention.get("abbreviations") or () if str(alias).strip())
        )
        identity_key = _identity_key(source_name, aliases=aliases, abbreviations=abbreviations)
        existing = by_key.setdefault(
            identity_key,
            {
                "identity_key": identity_key,
                "canonical_name": source_name,
                "source_name": source_name,
                "aliases": [],
                "abbreviations": [],
                "identity_evidence_unit_ids": [],
                "identity_evidence": [],
                "identity_confidence": 0.0,
            },
        )
        for alias in (*aliases, *abbreviations):
            if alias and alias not in existing["aliases"]:
                existing["aliases"].append(alias)
        for abbreviation in abbreviations:
            if abbreviation and abbreviation not in existing["abbreviations"]:
                existing["abbreviations"].append(abbreviation)
        chunk_id = str(mention.get("chunk_id") or "")
        if chunk_id and chunk_id not in existing["identity_evidence_unit_ids"]:
            existing["identity_evidence_unit_ids"].append(chunk_id)
        existing["identity_evidence"].append(
            {
                "evidence_unit_id": chunk_id,
                "chunk_id": chunk_id,
                "locator": mention.get("locator") or {},
                "evidence": mention.get("evidence"),
                "source_name": source_name,
                "aliases": list(aliases),
            }
        )
        existing["identity_confidence"] = max(float(existing["identity_confidence"]), float(mention.get("confidence") or 0.0))

    identities = []
    all_labels = tuple(_all_labels(expanded_chunks))
    for identity in by_key.values():
        aliases = tuple(dict.fromkeys((*identity["aliases"], identity["source_name"])))
        competing_labels = tuple(
            label for label in all_labels if not _label_matches_identity(label, identity["source_name"], aliases)
        )
        enriched = dict(identity)
        enriched["aliases"] = list(aliases)
        enriched["query_alignment"] = _query_alignment(query, identity["source_name"], aliases)
        enriched["competing_method_labels"] = list(dict.fromkeys(competing_labels))
        identities.append(enriched)
    identities.sort(
        key=lambda item: (
            -float(item.get("identity_confidence") or 0.0),
            str(item.get("canonical_name") or "").lower(),
            str(item.get("identity_key") or ""),
        )
    )
    return tuple(identities)


def _heading_identity_supported(chunk: KnowledgeChunk, heading: str, query: str) -> bool:
    text_lower = chunk.text.lower()
    heading_terms = set(_normalize_identity_text(heading).split())
    text_terms = set(re.findall(r"[a-z][a-z0-9+-]{2,}", text_lower))
    if heading_terms and heading_terms <= text_terms:
        return True
    if query and heading_terms and heading_terms.intersection(set(_normalize_identity_text(query).split())):
        return True
    return _chunk_matches_families(chunk, tuple(FAMILY_KEYWORDS))


def _label_mentions(chunk: KnowledgeChunk) -> tuple[Mapping[str, Any], ...]:
    labels = list(chunk.detected_labels)
    text = " ".join(chunk.text.split())
    mentions: list[Mapping[str, Any]] = []
    for pattern in _METHOD_LABEL_PATTERNS:
        for match in pattern.finditer(text):
            source_name = " ".join(match.group(1).split()).strip(" :-")
            abbreviation = str(match.group(2)).strip() if match.lastindex and match.lastindex >= 2 else ""
            if source_name and len(source_name.split()) <= 10:
                aliases = (abbreviation,) if abbreviation else tuple()
                mentions.append(
                    {
                        "source_name": source_name,
                        "aliases": aliases,
                        "abbreviations": aliases,
                        "chunk_id": chunk.chunk_id,
                        "locator": dict(chunk.locator),
                        "evidence": "local_label",
                        "confidence": 0.95,
                    }
                )
    if not mentions and labels:
        primary = next((label for label in labels if len(label) > 2 and not label.isupper()), labels[0])
        aliases = tuple(label for label in labels if label != primary)
        mentions.append(
            {
                "source_name": primary,
                "aliases": aliases,
                "abbreviations": tuple(label for label in aliases if label.isupper()),
                "chunk_id": chunk.chunk_id,
                "locator": dict(chunk.locator),
                "evidence": "detected_label",
                "confidence": 0.85,
            }
        )
    if not mentions:
        title_line = _title_line_identity(text)
        if title_line is not None:
            mentions.append(
                {
                    "source_name": title_line,
                    "aliases": (),
                    "abbreviations": (),
                    "chunk_id": chunk.chunk_id,
                    "locator": dict(chunk.locator),
                    "evidence": "title_line",
                    "confidence": 0.7,
                }
            )
    return tuple(mentions)


def _title_line_identity(text: str) -> str | None:
    normalized = " ".join(text.split()).strip(" :-")
    if not normalized or re.search(r"[.!?]", normalized):
        return None
    normalized = re.sub(r"^chapter\s+\d+[.: -]*", "", normalized, flags=re.IGNORECASE).strip()
    words = re.findall(r"[A-Za-z][A-Za-z0-9+-]*", normalized)
    if not 2 <= len(words) <= 10:
        return None
    titleish = sum(1 for word in words if word[:1].isupper() or word.lower() in {"and", "or", "of", "the"})
    if titleish / len(words) < 0.7:
        return None
    if _is_generic_identity(normalized):
        return None
    return normalized


def _query_identity(chunk: KnowledgeChunk, query: str) -> Mapping[str, Any] | None:
    normalized_query = " ".join(query.split()).strip()
    if not normalized_query:
        return None
    lowered_text = chunk.text.lower()
    candidates = _query_phrases(normalized_query)
    for phrase in candidates:
        if phrase.lower() in lowered_text and not _is_generic_identity(phrase):
            return {
                "source_name": phrase,
                "aliases": (),
                "abbreviations": (),
                "chunk_id": chunk.chunk_id,
                "locator": dict(chunk.locator),
                "evidence": "query_phrase_in_source",
                "confidence": 0.65,
            }
    return None


def _query_phrases(query: str) -> tuple[str, ...]:
    parts = [part.strip(" ,;:.") for part in re.split(r"\bor\b|,|/|\(|\)", query, flags=re.IGNORECASE)]
    phrases = []
    for part in parts:
        words = [word for word in re.findall(r"[A-Za-z][A-Za-z0-9+-]*", part) if word.lower() not in _GENERIC_IDENTITY_WORDS]
        if 1 <= len(words) <= 6:
            phrases.append(" ".join(words))
    return tuple(dict.fromkeys(phrase for phrase in phrases if phrase))


def _identity_bound_chunks(
    identity: Mapping[str, Any],
    chunks: Sequence[KnowledgeChunk],
    *,
    seed_chunk: KnowledgeChunk,
    query: str,
) -> tuple[KnowledgeChunk, ...]:
    aliases = tuple(str(alias) for alias in identity.get("aliases") or ())
    source_name = str(identity.get("source_name") or identity.get("canonical_name") or "")
    evidence_ids = {str(chunk_id) for chunk_id in identity.get("identity_evidence_unit_ids") or ()}
    query_terms = {term.lower() for term in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", query)}
    accepted: list[KnowledgeChunk] = []
    for chunk in chunks:
        labels = _chunk_labels(chunk)
        competing = [label for label in labels if not _label_matches_identity(label, source_name, aliases)]
        if chunk.chunk_id in evidence_ids:
            accepted.append(chunk)
            continue
        if competing:
            continue
        text_lower = chunk.text.lower()
        if _label_matches_text(source_name, aliases, text_lower):
            accepted.append(chunk)
            continue
        if chunk.chunk_id == seed_chunk.chunk_id:
            accepted.append(chunk)
            continue
        if query_terms and query_terms.intersection(set(re.findall(r"[a-z][a-z0-9+-]{2,}", text_lower))):
            accepted.append(chunk)
            continue
        if _chunk_matches_families(chunk, tuple(FAMILY_KEYWORDS)):
            accepted.append(chunk)
    if not accepted:
        accepted.append(seed_chunk)
    accepted.sort(key=lambda item: (item.ordinal, item.chunk_id))
    deduped: dict[str, KnowledgeChunk] = {}
    for chunk in accepted:
        deduped.setdefault(chunk.chunk_id, chunk)
    return tuple(deduped.values())


def _identity_with_context(identity: Mapping[str, Any], chunks: Sequence[KnowledgeChunk]) -> Mapping[str, Any]:
    labels = tuple(_all_labels(chunks))
    aliases = tuple(str(alias) for alias in identity.get("aliases") or ())
    source_name = str(identity.get("source_name") or identity.get("canonical_name") or "")
    competing = tuple(label for label in labels if not _label_matches_identity(label, source_name, aliases))
    enriched = dict(identity)
    enriched["competing_method_labels"] = list(dict.fromkeys(competing))
    enriched["context_evidence_unit_ids"] = [chunk.chunk_id for chunk in chunks]
    return enriched


def _all_labels(chunks: Sequence[KnowledgeChunk]) -> tuple[str, ...]:
    labels: list[str] = []
    for chunk in chunks:
        labels.extend(_chunk_labels(chunk))
    return tuple(dict.fromkeys(label for label in labels if label))


def _chunk_labels(chunk: KnowledgeChunk) -> tuple[str, ...]:
    labels = list(chunk.detected_labels)
    labels.extend(str(item.get("source_name") or "") for item in _label_mentions(chunk))
    labels.extend(alias for item in _label_mentions(chunk) for alias in item.get("aliases") or ())
    return tuple(dict.fromkeys(label for label in labels if label))


def _identity_key(source_name: str, *, aliases: Sequence[str], abbreviations: Sequence[str]) -> str:
    key_terms = [source_name, *aliases, *abbreviations]
    normalized = "|".join(_normalize_identity_text(term) for term in key_terms if _normalize_identity_text(term))
    digest = stable_research_id("method_identity", normalized)
    return digest


def _normalize_identity_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+-]+", text.lower()))


def _label_matches_identity(label: str, source_name: str, aliases: Sequence[str]) -> bool:
    normalized = _normalize_identity_text(label)
    if not normalized:
        return False
    return normalized in {_normalize_identity_text(source_name), *(_normalize_identity_text(alias) for alias in aliases)}


def _label_matches_text(source_name: str, aliases: Sequence[str], text_lower: str) -> bool:
    terms = [source_name, *aliases]
    return any(term and _normalize_identity_text(term) in _normalize_identity_text(text_lower) for term in terms)


def _query_alignment(query: str, source_name: str, aliases: Sequence[str]) -> Mapping[str, Any]:
    if not query.strip():
        return {"status": "not_requested", "matched_terms": []}
    query_norm = _normalize_identity_text(query)
    labels = [source_name, *aliases]
    exact = [label for label in labels if _normalize_identity_text(label) and _normalize_identity_text(label) in query_norm]
    if exact:
        return {"status": "direct", "matched_terms": exact}
    query_terms = set(query_norm.split())
    label_terms = set(_normalize_identity_text(" ".join(labels)).split())
    matched = sorted(query_terms & label_terms)
    return {"status": "term_overlap" if matched else "none", "matched_terms": matched}


def _is_generic_identity(text: str) -> bool:
    terms = [term.lower() for term in re.findall(r"[A-Za-z][A-Za-z0-9+-]*", text)]
    if not terms:
        return True
    meaningful = [term for term in terms if term not in _GENERIC_IDENTITY_WORDS]
    return not meaningful


def _chunk_matches_families(chunk: KnowledgeChunk, method_families: Sequence[str]) -> bool:
    if not method_families:
        return True
    text = chunk.text.lower()
    requested = set(method_families)
    return any(any(keyword in text for keyword in FAMILY_KEYWORDS[family]) for family in requested)


def _load_sources(store: KnowledgeStore, source_ids: Sequence[str]) -> dict[str, KnowledgeSourceManifest]:
    sources: dict[str, KnowledgeSourceManifest] = {}
    for source_id in source_ids:
        source = store.load_source(source_id)
        if source is not None:
            sources[source.source_id] = source
    return sources


def _normalize_families(families: Sequence[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for raw_family in families:
        text = str(raw_family).strip().lower().replace("-", "_").replace(" ", "_")
        if not text:
            continue
        if text in FAMILY_KEYWORDS:
            normalized.add(text)
        elif "pair" in text or "cointegration" in text or "statistical" in text:
            normalized.add("statistical_arbitrage")
        elif "option" in text or "straddle" in text or "derivative" in text:
            normalized.add("options_derivatives")
        elif "sentiment" in text or "alternative" in text or "commodity" in text:
            normalized.add("sentiment_alternative_data")
        elif "technical" in text or "indicator" in text or text in {"rsi", "moving_average"}:
            normalized.add("technical_indicators")
        elif "fundamental" in text or "valuation" in text:
            normalized.add("fundamental_valuation")
        elif "portfolio" in text:
            normalized.add("portfolio_construction")
        elif "risk" in text:
            normalized.add("risk_models")
        elif "execution" in text:
            normalized.add("execution_methods")
    return tuple(sorted(normalized))


def _group_heading(chunk: KnowledgeChunk) -> str:
    for key in ("heading", "section", "title"):
        value = chunk.locator.get(key)
        if value:
            return str(value)
    window = max(chunk.ordinal // 3, 0)
    return f"ordinal_window_{window}"


def _candidate_title(
    heading: str,
    families: Sequence[str],
    source: KnowledgeSourceManifest | None,
    *,
    ordered_chunks: Sequence[KnowledgeChunk] = (),
    query: str = "",
) -> str:
    explicit_title = _explicit_method_title(ordered_chunks, query=query)
    if explicit_title and _is_generic_heading(heading):
        return explicit_title
    if heading and not _is_generic_heading(heading):
        return heading
    if explicit_title:
        return explicit_title
    family_label = ", ".join(family.replace("_", " ") for family in families) or "methodology"
    if source is not None:
        return f"{source.title}: {family_label}"
    return family_label.title()


def _is_generic_heading(heading: str) -> bool:
    stripped = heading.strip()
    return not stripped or stripped.startswith("ordinal_window_") or re.fullmatch(r"page[- ]?\d+", stripped.lower()) is not None


def _explicit_method_title(chunks: Sequence[KnowledgeChunk], *, query: str) -> str | None:
    query_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", query)
        if term.lower() not in {"method", "trading", "strategy", "average", "technical", "indicator"}
    }
    patterns = (
        re.compile(r"\b([A-Z][A-Za-z][A-Za-z /-]{2,80}?)\s*\(([A-Z][A-Z0-9]{1,8})\)\s*:"),
        re.compile(r"\b([A-Z][A-Za-z][A-Za-z /-]{2,80}?)\s+Rule\s*:"),
    )
    for chunk in chunks:
        text = " ".join(chunk.text.split())
        for pattern in patterns:
            for match in pattern.finditer(text):
                title = " ".join(match.group(1).split())
                acronym = match.group(2).lower() if match.lastindex and match.lastindex >= 2 else ""
                title_terms = {term.lower() for term in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", title)}
                if query_terms and not (query_terms & title_terms or acronym in query_terms):
                    continue
                return title[:120]
    return None


def _candidate_name_evidence(
    heading: str,
    chunks: Sequence[KnowledgeChunk],
    query: str,
    identity: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    return {
        "heading": heading,
        "query": query,
        "method_identity": dict(identity or {}),
        "chunk_ids": [chunk.chunk_id for chunk in chunks[:3]],
        "evidence_unit_ids": [chunk.chunk_id for chunk in chunks[:3]],
        "locators": [dict(chunk.locator) for chunk in chunks[:3]],
    }


def _family_attribution(
    chunks: Sequence[KnowledgeChunk],
    families: Sequence[str],
) -> Mapping[str, Any]:
    attribution: dict[str, list[Mapping[str, Any]]] = {family: [] for family in families}
    for chunk in chunks:
        text = chunk.text.lower()
        for family in families:
            matched = [keyword for keyword in FAMILY_KEYWORDS[family] if keyword in text]
            if matched:
                attribution[family].append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "evidence_unit_id": chunk.evidence_unit_id,
                        "matched_terms": matched,
                        "locator": dict(chunk.locator),
                    }
                )
    return attribution


def _validation_error(message: str) -> ToolEnvelope:
    return error_envelope(
        command=KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="validation_error",
        message=message,
    )


def _artifact_store_unavailable(message: str) -> ToolEnvelope:
    return error_envelope(
        command=KNOWLEDGE_DISCOVER_METHODOLOGY_CANDIDATES,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="research_artifact_store_unavailable",
        message=message,
    )
