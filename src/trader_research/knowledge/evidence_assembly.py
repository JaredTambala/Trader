"""Methodology evidence assembly over family-level role profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.artifact_store import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    load_artifact_ref,
)
from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import METHODOLOGY_CANDIDATE, METHODOLOGY_EVIDENCE_PACKET, stable_research_id

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
) -> ToolEnvelope:
    """Assemble role-labeled evidence chunks for a methodology candidate."""
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
    diagnostics: dict[str, Any] = {
        "readiness_goal": readiness,
        "profile_family": profile.family,
        "required_roles": sorted(required_roles),
        "candidate_families": list(candidate.families),
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
        if not role_chunks:
            missing_roles.append(role.role_id)
        all_chunk_ids.extend(chunk.chunk_id for chunk in role_chunks)
        role_evidence.append(
            {
                "role_id": role.role_id,
                "description": role.description,
                "status": "found" if role_chunks else "missing",
                "required": role.role_id in required_roles,
                "field_paths": [".".join(path) for path in role.field_paths],
                "semantic_expectation": role.semantic_expectation,
                "search_terms": list(role.search_terms),
                "chunks": [_chunk_ref(chunk, role) for chunk in role_chunks],
            }
        )

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
                str(role["role_id"]): [chunk["chunk_id"] for chunk in role.get("chunks", ())]
                for role in role_evidence
            },
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
        return error_envelope(
            command=KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="methodology_evidence_assembly_blocked",
            message="methodology evidence assembly missing required roles",
            data=data,
        )
    return success_envelope(
        command=KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE,
        side_effect=SideEffect.LOCAL_MUTATING,
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
        "ordinal": chunk.ordinal,
        "locator": dict(chunk.locator),
        "text_hash": chunk.text_hash,
        "matched_terms": list(matched_terms),
    }


def _validation_error(message: str) -> ToolEnvelope:
    return error_envelope(
        command=KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="validation_error",
        message=message,
    )


def _artifact_store_error(message: str) -> ToolEnvelope:
    return error_envelope(
        command=KNOWLEDGE_ASSEMBLE_METHODOLOGY_EVIDENCE,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="research_artifact_store_unavailable",
        message=message,
    )
