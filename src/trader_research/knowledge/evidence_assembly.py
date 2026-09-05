"""Assemble role-labeled evidence packets for methodology candidates.

The service resolves one exact candidate, retrieves bounded neighboring chunks,
and fills the maintained evidence roles for its methodology family and readiness
goal. It persists a packet with warnings or blockers when support is incomplete
instead of manufacturing missing evidence.
"""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result, success_result

from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from trader_research.foundation.artifacts import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    load_artifact_ref,
)
from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_EVIDENCE_PACKET,
)

from .claim_spans import detect_local_method_labels, select_role_claim_spans
from .domain import KnowledgeChunk, MethodologyCandidate, MethodologyEvidencePacket
from .evidence_profiles import (
    EvidenceRoleProfile,
    normalize_family,
    normalize_readiness,
    profile_for_family,
    required_roles_for_readiness,
)
from .store import KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE = "knowledge_assemble_methodology_evidence"

ACCEPTED_TARGET_BINDINGS = frozenset({"direct_label", "alias_label", "same_sentence", "same_paragraph", "nearby_context"})
"""Evidence-unit bindings that may satisfy role/readiness requirements."""


def assemble_methodology_evidence(
    *,
    artifact_root: str | Path,
    methodology_candidate_id: str | None = None,
    methodology_candidate_uri: str | None = None,
    methodology_candidate: Mapping[str, Any] | None = None,
    readiness_goal: str = "descriptive",
    neighbor_radius: int = 1,
    max_chunks_per_role: int = 6,
    knowledge_store: KnowledgeStore | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Assemble a bounded role-labeled packet for one methodology candidate.

    Exactly one candidate input is resolved, its family profile and readiness
    goal determine required roles, and candidate plus neighboring chunks are
    ranked separately for each role. Selected sources and spans remain explicit;
    missing roles become blockers rather than inferred content. The packet is
    persisted under Methodology ownership.

    Returns:
        A result containing the canonical packet, selected evidence, warnings,
        blockers, and reference, or a structured input, store, or persistence
        failure.
    """
    if artifact_store is None:
        return _artifact_store_error("research artifact store is required")
    if knowledge_store is None:
        return _validation_error("knowledge store is required")
    if neighbor_radius < 0 or neighbor_radius > 5:
        return _validation_error("neighbor_radius must be between 0 and 5")
    if max_chunks_per_role < 1 or max_chunks_per_role > 25:
        return _validation_error("max_chunks_per_role must be between 1 and 25")

    try:
        candidate = _resolve_candidate(
            artifact_store,
            methodology_candidate_id=methodology_candidate_id,
            methodology_candidate_uri=methodology_candidate_uri,
            methodology_candidate=methodology_candidate,
        )
        chunks = _load_candidate_chunks(knowledge_store, candidate)
        source_chunks = _load_source_chunks(knowledge_store, candidate.source_ids or tuple({chunk.source_id for chunk in chunks}))
    except (ResearchArtifactStoreError, KnowledgeStoreError, ValueError) as exc:
        return _validation_error(str(exc))

    family = _select_family(candidate)
    profile = profile_for_family(family)
    if profile is None:
        return _validation_error(f"unsupported methodology family for evidence assembly: {family}")

    readiness = normalize_readiness(readiness_goal)
    required_roles = set(required_roles_for_readiness(profile, readiness))
    role_evidence: list[Mapping[str, Any]] = []
    missing_roles: list[str] = []
    all_chunk_ids: list[str] = []
    rejected_chunk_ids: list[str] = []
    diagnostics: dict[str, Any] = {
        "readiness_goal": readiness,
        "profile_family": profile.family,
        "required_roles": sorted(required_roles),
        "candidate_families": list(candidate.families),
        "target_identity": dict(candidate.method_identity),
        "target_binding_accepts": sorted(ACCEPTED_TARGET_BINDINGS),
    }

    for role in profile.roles:
        role_chunks = _chunks_for_role(
            role,
            candidate=candidate,
            candidate_chunks=chunks,
            chunks_by_source=source_chunks,
            neighbor_radius=neighbor_radius,
            max_chunks_per_role=max_chunks_per_role,
        )
        bound_refs = [
            _target_bound_chunk_ref(
                chunk,
                role,
                candidate,
                candidate_chunks=chunks,
                context_chunks=source_chunks.get(chunk.source_id, ()),
            )
            for chunk in role_chunks
        ]
        accepted_refs = tuple(ref for ref in bound_refs if _is_accepted_binding(ref))
        rejected_refs = tuple(ref for ref in bound_refs if not _is_accepted_binding(ref))
        if not accepted_refs:
            missing_roles.append(role.role_id)
        all_chunk_ids.extend(str(ref["chunk_id"]) for ref in accepted_refs)
        rejected_chunk_ids.extend(str(ref["chunk_id"]) for ref in rejected_refs)
        role_evidence.append(
            {
                "role_id": role.role_id,
                "description": role.description,
                "status": "found" if accepted_refs else "missing",
                "required": role.role_id in required_roles,
                "field_paths": [".".join(path) for path in role.field_paths],
                "semantic_expectation": role.semantic_expectation,
                "search_terms": list(role.search_terms),
                "target_binding_required": True,
                "accepted_target_bindings": sorted(ACCEPTED_TARGET_BINDINGS),
                "chunks": list(accepted_refs),
                "rejected_chunks": list(rejected_refs),
                "target_binding_summary": _target_binding_summary(bound_refs),
            }
        )
    diagnostics["rejected_or_weak_chunk_ids"] = sorted(set(rejected_chunk_ids))

    blockers = tuple(
        f"missing required evidence role for {readiness}: {role_id}"
        for role_id in sorted(required_roles.intersection(missing_roles))
    )
    status = "blocked" if blockers else "assembled"
    packet_id = stable_research_id(
        "methodology_evidence_packet",
        {
            "candidate_id": candidate.methodology_candidate_id,
            "family": profile.family,
            "readiness_goal": readiness,
            "role_chunks": {
                str(role["role_id"]): [
                    {
                        "chunk_id": chunk["chunk_id"],
                        "claim_span_ids": [span["span_id"] for span in chunk.get("claim_spans", ())],
                    }
                    for chunk in role.get("chunks", ())
                ]
                for role in role_evidence
            },
            "rejected_or_weak_chunk_ids": sorted(set(rejected_chunk_ids)),
            "blockers": list(blockers),
        },
    )
    packet = MethodologyEvidencePacket(
        evidence_packet_id=packet_id,
        methodology_candidate_id=candidate.methodology_candidate_id,
        family=profile.family,
        readiness_goal=readiness,
        status=status,
        candidate_ref={
            "artifact_type": METHODOLOGY_CANDIDATE,
            "artifact_id": candidate.methodology_candidate_id,
            "uri": f"research://postgres/{METHODOLOGY_CANDIDATE}/{candidate.methodology_candidate_id}",
            "status": candidate.status,
        },
        source_ids=tuple(dict.fromkeys(candidate.source_ids or tuple(chunk.source_id for chunk in chunks))),
        chunk_ids=tuple(dict.fromkeys(all_chunk_ids)),
        profile_version=profile.version,
        role_evidence=tuple(role_evidence),
        missing_roles=tuple(missing_roles),
        diagnostics=diagnostics,
        blockers=blockers,
    )
    try:
        record = artifact_store.save_artifact(
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_EVIDENCE_PACKET],
            producer_tool=KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE,
            artifact_type=METHODOLOGY_EVIDENCE_PACKET,
            artifact_id=packet.evidence_packet_id,
            payload=packet.to_dict(),
            status=packet.status,
            metadata={
                "methodology_candidate_id": packet.methodology_candidate_id,
                "family": packet.family,
                "readiness_goal": packet.readiness_goal,
                "source_ids": list(packet.source_ids),
                "chunk_ids": list(packet.chunk_ids),
                "missing_roles": list(packet.missing_roles),
            },
        )
    except ResearchArtifactStoreError as exc:
        return _artifact_store_error(str(exc))

    data = {"methodology_evidence_packet": packet.to_dict()}
    artifacts = {"methodology_evidence_packet": record.reference().to_dict()}
    if blockers:
        return error_result(
            command=KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE,
            code="methodology_evidence_assembly_blocked",
            message="methodology evidence assembly missing required roles",
            data=data,
        )
    return success_result(
        command=KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE,
        data=data,
        artifacts=artifacts,
    )


def _resolve_candidate(
    artifact_store: ResearchArtifactStore,
    *,
    methodology_candidate_id: str | None,
    methodology_candidate_uri: str | None,
    methodology_candidate: Mapping[str, Any] | None,
) -> MethodologyCandidate:
    supplied = [
        bool(methodology_candidate_id),
        bool(methodology_candidate_uri),
        methodology_candidate is not None,
    ]
    if sum(supplied) != 1:
        raise ValueError(
            "exactly one of methodology_candidate_id, methodology_candidate_uri, or methodology_candidate is required"
        )
    if methodology_candidate is not None:
        payload = methodology_candidate
    elif methodology_candidate_uri:
        payload = load_artifact_ref(artifact_store, METHODOLOGY_CANDIDATE, methodology_candidate_uri)
    else:
        payload = artifact_store.load_artifact(METHODOLOGY_CANDIDATE, str(methodology_candidate_id))
    if payload.get("artifact_type") != METHODOLOGY_CANDIDATE:
        raise ValueError("methodology candidate artifact_type must be methodology_candidate")
    return MethodologyCandidate.from_dict(payload)


def _load_candidate_chunks(store: KnowledgeStore, candidate: MethodologyCandidate) -> tuple[KnowledgeChunk, ...]:
    if not candidate.chunk_ids:
        raise ValueError("methodology candidate has no chunk_ids")
    chunks = store.load_chunks_by_ids(candidate.chunk_ids)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    missing = tuple(chunk_id for chunk_id in candidate.chunk_ids if chunk_id not in chunks_by_id)
    if missing:
        raise ValueError(f"unknown candidate chunk_id: {', '.join(missing)}")
    return tuple(chunks_by_id[chunk_id] for chunk_id in candidate.chunk_ids)


def _load_source_chunks(
    store: KnowledgeStore,
    source_ids: Sequence[str],
) -> dict[str, tuple[KnowledgeChunk, ...]]:
    chunks_by_source: dict[str, tuple[KnowledgeChunk, ...]] = {}
    for source_id in source_ids:
        chunks_by_source[source_id] = tuple(store.load_chunks(source_id))
    return chunks_by_source


def _select_family(candidate: MethodologyCandidate) -> str:
    for family in candidate.families:
        normalized = normalize_family(family)
        if profile_for_family(normalized) is not None:
            return normalized
    return normalize_family(candidate.families[0] if candidate.families else "")


def _chunks_for_role(
    role: EvidenceRoleProfile,
    *,
    candidate: MethodologyCandidate,
    candidate_chunks: Sequence[KnowledgeChunk],
    chunks_by_source: Mapping[str, Sequence[KnowledgeChunk]],
    neighbor_radius: int,
    max_chunks_per_role: int,
) -> tuple[KnowledgeChunk, ...]:
    scored: dict[str, tuple[KnowledgeChunk, int]] = {}
    terms = tuple(term.lower() for term in role.search_terms)
    method_terms = tuple(term.lower() for term in _candidate_terms(candidate))
    for chunk in _role_search_space(candidate_chunks, chunks_by_source):
        text = chunk.text.lower()
        role_score = sum(2 for term in terms if term and term in text)
        if role_score <= 0:
            continue
        method_score = sum(1 for term in method_terms if term and term in text)
        score = role_score + (3 * method_score)
        if chunk.chunk_id in candidate.chunk_ids:
            score += 8
        for expanded in _expand_neighbors(chunk, chunks_by_source.get(chunk.source_id, ()), neighbor_radius):
            expanded_score = score if expanded.chunk_id == chunk.chunk_id else max(score - 1, 1)
            existing = scored.get(expanded.chunk_id)
            if existing is None or expanded_score > existing[1]:
                scored[expanded.chunk_id] = (expanded, expanded_score)
    ordered = sorted(scored.values(), key=lambda item: (-item[1], item[0].source_id, item[0].ordinal, item[0].chunk_id))
    return tuple(chunk for chunk, _ in ordered[:max_chunks_per_role])


def _role_search_space(
    candidate_chunks: Sequence[KnowledgeChunk],
    chunks_by_source: Mapping[str, Sequence[KnowledgeChunk]],
) -> tuple[KnowledgeChunk, ...]:
    chunks: dict[str, KnowledgeChunk] = {chunk.chunk_id: chunk for chunk in candidate_chunks}
    for source_chunks in chunks_by_source.values():
        for chunk in source_chunks:
            chunks.setdefault(chunk.chunk_id, chunk)
    return tuple(sorted(chunks.values(), key=lambda item: (item.source_id, item.ordinal, item.chunk_id)))


def _candidate_terms(candidate: MethodologyCandidate) -> tuple[str, ...]:
    words = [
        word
        for word in candidate.title.replace("/", " ").replace("-", " ").split()
        if len(word.strip()) > 2
    ]
    return tuple(dict.fromkeys(words))


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


def _chunk_ref(chunk: KnowledgeChunk, role: EvidenceRoleProfile) -> Mapping[str, Any]:
    text = chunk.text.lower()
    matched_terms = tuple(term for term in role.search_terms if term.lower() in text)
    return {
        "source_id": chunk.source_id,
        "chunk_id": chunk.chunk_id,
        "evidence_unit_id": chunk.evidence_unit_id,
        "ordinal": chunk.ordinal,
        "locator": dict(chunk.locator),
        "text_hash": chunk.text_hash,
        "matched_terms": list(matched_terms),
        "detected_labels": list(chunk.detected_labels),
        "neighbor_chunk_ids": list(chunk.neighbor_chunk_ids),
        "chunker_version": chunk.chunker_version,
    }


def _target_bound_chunk_ref(
    chunk: KnowledgeChunk,
    role: EvidenceRoleProfile,
    candidate: MethodologyCandidate,
    *,
    candidate_chunks: Sequence[KnowledgeChunk],
    context_chunks: Sequence[KnowledgeChunk],
) -> Mapping[str, Any]:
    ref = dict(_chunk_ref(chunk, role))
    binding = _target_binding(
        chunk,
        role,
        candidate,
        candidate_chunks=candidate_chunks,
        context_chunks=context_chunks,
    )
    accepted_spans, rejected_spans = select_role_claim_spans(
        chunk,
        role,
        candidate,
        fallback_binding=str(binding.get("target_binding") or "weak"),
    )
    selected_binding = (
        accepted_spans[0].target_binding
        if accepted_spans
        else rejected_spans[0].target_binding
        if rejected_spans
        else str(binding.get("target_binding") or "weak")
    )
    matched_terms = tuple(
        dict.fromkeys(term for span in (*accepted_spans, *rejected_spans) for term in span.matched_terms)
    )
    ref.update(
        {
            **binding,
            "target_binding": selected_binding,
            "accepted_target_binding": bool(accepted_spans),
            "matched_role_terms": list(matched_terms),
            "claim_spans": [span.to_dict() for span in accepted_spans],
            "rejected_claim_spans": [span.to_dict() for span in rejected_spans],
            "target_binding_reason": (
                "one or more role-bearing claim spans bind to the candidate identity"
                if accepted_spans
                else "no role-bearing claim span binds to the candidate identity"
            ),
        }
    )
    return ref


def _target_binding(
    chunk: KnowledgeChunk,
    role: EvidenceRoleProfile,
    candidate: MethodologyCandidate,
    *,
    candidate_chunks: Sequence[KnowledgeChunk],
    context_chunks: Sequence[KnowledgeChunk],
) -> Mapping[str, Any]:
    direct_terms, alias_terms = _target_identity_terms(candidate)
    all_terms = tuple(dict.fromkeys((*direct_terms, *alias_terms)))
    labels = tuple(chunk.detected_labels)
    direct_label_terms = tuple(label for label in labels if _label_matches_any(label, direct_terms))
    alias_label_terms = tuple(label for label in labels if _label_matches_any(label, alias_terms))
    competing_labels = tuple(label for label in labels if not _label_matches_any(label, all_terms))
    matched_role_terms = tuple(term for term in role.search_terms if term.lower() in chunk.text.lower())
    identity_evidence_ids = _identity_evidence_ids(candidate)

    if not matched_role_terms:
        return _binding_payload(
            "rejected",
            "evidence unit did not contain role evidence after neighbor expansion",
            binding_terms=(),
            competing_labels=competing_labels,
            matched_role_terms=matched_role_terms,
        )
    if direct_label_terms:
        return _binding_payload(
            "direct_label",
            "detected method label matches the candidate identity",
            binding_terms=direct_label_terms,
            competing_labels=competing_labels,
            matched_role_terms=matched_role_terms,
        )
    if alias_label_terms:
        return _binding_payload(
            "alias_label",
            "detected method label matches a candidate alias or abbreviation",
            binding_terms=alias_label_terms,
            competing_labels=competing_labels,
            matched_role_terms=matched_role_terms,
        )

    same_sentence_terms = _same_sentence_binding_terms(chunk.text, role.search_terms, all_terms)
    if same_sentence_terms:
        return _binding_payload(
            "same_sentence",
            "role term and target identity term appear in the same sentence",
            binding_terms=same_sentence_terms,
            competing_labels=competing_labels,
            matched_role_terms=matched_role_terms,
        )

    contextual_label, contextual_binding = _nearest_preceding_method_binding(
        chunk,
        context_chunks,
        direct_terms=direct_terms,
        alias_terms=alias_terms,
    )
    if contextual_binding == "nearby_context":
        return _binding_payload(
            "nearby_context",
            "nearest preceding source method label matches the candidate identity",
            binding_terms=(contextual_label,),
            competing_labels=competing_labels,
            matched_role_terms=matched_role_terms,
        )

    if contextual_binding == "rejected":
        return _binding_payload(
            "rejected",
            "nearest preceding source method label belongs to another method",
            binding_terms=(),
            competing_labels=tuple(dict.fromkeys((*competing_labels, contextual_label))),
            matched_role_terms=matched_role_terms,
        )

    if _same_paragraph_as_identity(chunk, candidate_chunks, identity_evidence_ids) and matched_role_terms:
        return _binding_payload(
            "same_paragraph",
            "role evidence shares a source paragraph with target identity evidence",
            binding_terms=tuple(str(term) for term in all_terms[:3]),
            competing_labels=competing_labels,
            matched_role_terms=matched_role_terms,
        )

    if _near_identity_context(chunk, candidate_chunks, identity_evidence_ids) and matched_role_terms:
        return _binding_payload(
            "nearby_context",
            "role evidence is within accepted candidate context near target identity evidence",
            binding_terms=tuple(str(term) for term in all_terms[:3]),
            competing_labels=competing_labels,
            matched_role_terms=matched_role_terms,
        )

    if matched_role_terms:
        return _binding_payload(
            "weak",
            "role terms matched but no target identity binding was found",
            binding_terms=(),
            competing_labels=competing_labels,
            matched_role_terms=matched_role_terms,
        )
    return _binding_payload(
        "rejected",
        "evidence unit did not contain role evidence after neighbor expansion",
        binding_terms=(),
        competing_labels=competing_labels,
        matched_role_terms=matched_role_terms,
    )


def _binding_payload(
    target_binding: str,
    reason: str,
    *,
    binding_terms: Sequence[str],
    competing_labels: Sequence[str],
    matched_role_terms: Sequence[str],
) -> Mapping[str, Any]:
    return {
        "target_binding": target_binding,
        "accepted_target_binding": target_binding in ACCEPTED_TARGET_BINDINGS,
        "target_binding_terms": list(dict.fromkeys(str(term) for term in binding_terms if str(term).strip())),
        "competing_method_labels": list(dict.fromkeys(str(label) for label in competing_labels if str(label).strip())),
        "matched_role_terms": list(dict.fromkeys(str(term) for term in matched_role_terms if str(term).strip())),
        "target_binding_reason": reason,
    }


def _is_accepted_binding(chunk_ref: Mapping[str, Any]) -> bool:
    return bool(chunk_ref.get("accepted_target_binding")) and str(chunk_ref.get("target_binding") or "") in ACCEPTED_TARGET_BINDINGS


def _target_binding_summary(refs: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    counts: dict[str, int] = {}
    for ref in refs:
        binding = str(ref.get("target_binding") or "unknown")
        counts[binding] = counts.get(binding, 0) + 1
    return {
        "counts": counts,
        "accepted_count": sum(1 for ref in refs if _is_accepted_binding(ref)),
        "rejected_or_weak_count": sum(1 for ref in refs if not _is_accepted_binding(ref)),
    }


def _target_identity_terms(candidate: MethodologyCandidate) -> tuple[tuple[str, ...], tuple[str, ...]]:
    identity = candidate.method_identity if isinstance(candidate.method_identity, Mapping) else {}
    direct_terms = [
        candidate.title,
        str(identity.get("canonical_name") or ""),
        str(identity.get("source_name") or ""),
    ]
    aliases: list[str] = []
    for key in ("aliases", "abbreviations"):
        value = identity.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            aliases.extend(str(item) for item in value)
    direct = tuple(dict.fromkeys(term.strip() for term in direct_terms if term.strip()))
    alias = tuple(dict.fromkeys(term.strip() for term in aliases if term.strip() and term.strip() not in direct))
    return direct, alias


def _identity_evidence_ids(candidate: MethodologyCandidate) -> frozenset[str]:
    identity = candidate.method_identity if isinstance(candidate.method_identity, Mapping) else {}
    values = identity.get("identity_evidence_unit_ids")
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        return frozenset(str(value) for value in values if str(value).strip())
    return frozenset()


def _nearest_preceding_method_binding(
    chunk: KnowledgeChunk,
    context_chunks: Sequence[KnowledgeChunk],
    *,
    direct_terms: Sequence[str],
    alias_terms: Sequence[str],
) -> tuple[str, str]:
    for context in sorted(context_chunks, key=lambda item: (item.ordinal, item.chunk_id), reverse=True):
        if context.ordinal >= chunk.ordinal:
            continue
        labels = tuple(dict.fromkeys((*context.detected_labels, *detect_local_method_labels(context.text))))
        labels = tuple(label for label in labels if _context_label_is_boundary(label))
        if not labels:
            continue
        label = labels[-1]
        if _label_matches_any(label, direct_terms) or _label_matches_any(label, alias_terms):
            return label, "nearby_context"
        return label, "rejected"
    return "", "weak"


def _context_label_is_boundary(label: str) -> bool:
    words = _normalize_text(label).split()
    return len(words) >= 2 or (len(words) == 1 and label.isupper() and len(label) >= 2)


def _label_matches_any(label: str, terms: Sequence[str]) -> bool:
    normalized_label = _normalize_text(label)
    if not normalized_label:
        return False
    return any(normalized_label == _normalize_text(term) for term in terms if _normalize_text(term))


def _same_sentence_binding_terms(
    text: str,
    role_terms: Sequence[str],
    identity_terms: Sequence[str],
) -> tuple[str, ...]:
    matched: list[str] = []
    for sentence in _sentences(text):
        if not any(term.lower() in sentence.lower() for term in role_terms):
            continue
        matched.extend(term for term in identity_terms if _term_in_text(term, sentence))
        if not matched and _identity_token_overlap(identity_terms, sentence):
            matched.extend(_identity_token_overlap(identity_terms, sentence))
    return tuple(dict.fromkeys(matched))


def _same_paragraph_as_identity(
    chunk: KnowledgeChunk,
    candidate_chunks: Sequence[KnowledgeChunk],
    identity_evidence_ids: frozenset[str],
) -> bool:
    if not identity_evidence_ids:
        return False
    parent = chunk.parent_section_id or str(chunk.locator.get("parent_section_id") or "")
    paragraph = chunk.paragraph_index
    for candidate_chunk in candidate_chunks:
        if candidate_chunk.chunk_id not in identity_evidence_ids:
            continue
        candidate_parent = candidate_chunk.parent_section_id or str(candidate_chunk.locator.get("parent_section_id") or "")
        if parent and parent == candidate_parent and paragraph == candidate_chunk.paragraph_index:
            return True
    return False


def _near_identity_context(
    chunk: KnowledgeChunk,
    candidate_chunks: Sequence[KnowledgeChunk],
    identity_evidence_ids: frozenset[str],
) -> bool:
    if chunk.chunk_id in identity_evidence_ids:
        return True
    if chunk.chunk_id in {candidate_chunk.chunk_id for candidate_chunk in candidate_chunks}:
        return True
    for candidate_chunk in candidate_chunks:
        if candidate_chunk.chunk_id not in identity_evidence_ids:
            continue
        if chunk.chunk_id in candidate_chunk.neighbor_chunk_ids or candidate_chunk.chunk_id in chunk.neighbor_chunk_ids:
            return True
    return False


def _term_in_text(term: str, text: str) -> bool:
    normalized_term = _normalize_text(term)
    normalized_text = _normalize_text(text)
    if not normalized_term or not normalized_text:
        return False
    if " " in normalized_term:
        return normalized_term in normalized_text
    return re.search(rf"\b{re.escape(normalized_term)}\b", normalized_text) is not None


def _identity_token_overlap(identity_terms: Sequence[str], text: str) -> tuple[str, ...]:
    text_terms = set(_normalize_text(text).split())
    matches: list[str] = []
    for term in identity_terms:
        tokens = [token for token in _normalize_text(term).split() if len(token) > 2 and token not in {"and", "the", "method"}]
        if len(tokens) >= 2 and len(set(tokens) & text_terms) >= min(2, len(tokens)):
            matches.append(term)
    return tuple(matches)


def _normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+-]+", str(text).lower()))


def _sentences(text: str) -> tuple[str, ...]:
    normalized = " ".join(text.replace("\n", " ").split())
    if not normalized:
        return tuple()
    sentences = re.split(r"(?<=[.!?:;])\s+", normalized)
    return tuple(sentence.strip() for sentence in sentences if sentence.strip())


def _validation_error(message: str) -> ApplicationResult:
    return error_result(
        command=KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE,
        code="validation_error",
        message=message,
    )


def _artifact_store_error(message: str) -> ApplicationResult:
    return error_result(
        command=KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE,
        code="research_artifact_store_unavailable",
        message=message,
    )
