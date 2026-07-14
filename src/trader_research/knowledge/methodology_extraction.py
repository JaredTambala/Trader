"""Deterministic methodology-field extraction and validation services."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from trader_research.artifact_store import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    load_artifact_ref,
)
from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import (
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    METHODOLOGY_EVIDENCE_PACKET,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
    stable_research_id,
)

from .domain import (
    EvidenceBackedField,
    EvidenceClaimSpan,
    EvidenceReference,
    KnowledgeChunk,
    KnowledgeSourceManifest,
    MethodologyCandidate,
    MethodologyCandidateValidationReport,
    MethodologyEvidencePacket,
    MethodologyFieldExtractionReport,
)
from .evidence_assembly import ACCEPTED_TARGET_BINDINGS
from .evidence_profiles import profile_for_family, required_roles_for_readiness
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS = "knowledge_extract_methodology_fields"
KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE = "knowledge_validate_methodology_candidate"
HIGH_RISK_FAMILIES = frozenset(
    {"statistical_arbitrage", "options_derivatives", "portfolio_construction", "risk_models"}
)


def extract_methodology_fields(
    *,
    artifact_root: str | Path,
    methodology_candidate_id: str | None = None,
    methodology_candidate_uri: str | None = None,
    methodology_candidate: Mapping[str, Any] | None = None,
    evidence_packet_id: str | None = None,
    evidence_packet_uri: str | None = None,
    evidence_packet: Mapping[str, Any] | None = None,
    max_chars_per_chunk: int = 4000,
    knowledge_store: KnowledgeStore | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Populate nullable rich methodology fields from cited candidate chunks."""
    if artifact_store is None:
        return _artifact_store_error(KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS, "research artifact store is required")
    if max_chars_per_chunk < 1 or max_chars_per_chunk > 20_000:
        return _validation_error(
            KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS,
            "max_chars_per_chunk must be between 1 and 20000",
        )
    try:
        candidate, packet = _resolve_candidate_or_packet(
            artifact_store,
            methodology_candidate_id=methodology_candidate_id,
            methodology_candidate_uri=methodology_candidate_uri,
            methodology_candidate=methodology_candidate,
            evidence_packet_id=evidence_packet_id,
            evidence_packet_uri=evidence_packet_uri,
            evidence_packet=evidence_packet,
        )
    except (ResearchArtifactStoreError, ValueError) as exc:
        return _validation_error(KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS, str(exc))

    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    try:
        chunks, sources = _load_candidate_context(
            store,
            candidate,
            extra_chunk_ids=packet.chunk_ids if packet is not None else (),
        )
    except (KnowledgeStoreError, ValueError) as exc:
        report = _extraction_report(
            candidate,
            status="blocked",
            evidence_packet_id=packet.evidence_packet_id if packet is not None else None,
            blockers=(str(exc),),
        )
        try:
            record = artifact_store.save_artifact(
                artifact_type=METHODOLOGY_FIELD_EXTRACTION_REPORT,
                artifact_id=report.extraction_id,
                payload=report.to_dict(),
                status=report.status,
                metadata={"methodology_candidate_id": candidate.methodology_candidate_id},
            )
        except ResearchArtifactStoreError as store_exc:
            return _artifact_store_error(KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS, str(store_exc))
        return error_envelope(
            command=KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="methodology_extraction_blocked",
            message=str(exc),
            data={
                "methodology_field_extraction_report": report.to_dict(),
                "methodology_field_extraction_report_ref": record.reference().to_dict(),
            },
        )

    if packet is not None:
        updated_candidate, populated_fields, warnings = _extract_fields_from_packet(
            candidate,
            packet,
            chunks,
            sources,
            max_chars_per_chunk,
        )
    else:
        updated_candidate, populated_fields, warnings = _extract_fields(candidate, chunks, sources, max_chars_per_chunk)
    report = _extraction_report(
        updated_candidate,
        status="extracted",
        evidence_packet_id=packet.evidence_packet_id if packet is not None else None,
        populated_fields=populated_fields,
        warnings=warnings,
    )
    try:
        candidate_record = artifact_store.save_artifact(
            artifact_type=METHODOLOGY_CANDIDATE,
            artifact_id=updated_candidate.methodology_candidate_id,
            payload=updated_candidate.to_dict(),
            status=updated_candidate.status,
            metadata={
                "families": list(updated_candidate.families),
                "source_ids": list(updated_candidate.source_ids),
                "chunk_ids": list(updated_candidate.chunk_ids),
            },
        )
        report = replace(report, candidate_ref=candidate_record.reference().to_dict())
        report_record = artifact_store.save_artifact(
            artifact_type=METHODOLOGY_FIELD_EXTRACTION_REPORT,
            artifact_id=report.extraction_id,
            payload=report.to_dict(),
            status=report.status,
            metadata={
                "methodology_candidate_id": updated_candidate.methodology_candidate_id,
                "evidence_packet_id": packet.evidence_packet_id if packet is not None else None,
            },
        )
    except ResearchArtifactStoreError as exc:
        return _artifact_store_error(KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS, str(exc))

    return success_envelope(
        command=KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={
            "methodology_candidate": updated_candidate.to_dict(),
            "methodology_field_extraction_report": report.to_dict(),
        },
        artifacts={
            "methodology_candidate": candidate_record.reference().to_dict(),
            "methodology_field_extraction_report": report_record.reference().to_dict(),
        },
        warnings=warnings,
    )


def validate_methodology_candidate(
    *,
    artifact_root: str | Path,
    methodology_candidate_id: str | None = None,
    methodology_candidate_uri: str | None = None,
    methodology_candidate: Mapping[str, Any] | None = None,
    extraction_report_id: str | None = None,
    extraction_report_uri: str | None = None,
    knowledge_store: KnowledgeStore | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Validate rich methodology candidates before rich method-card creation."""
    if artifact_store is None:
        return _artifact_store_error(KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE, "research artifact store is required")
    try:
        candidate = _resolve_candidate_or_extraction(
            artifact_store,
            methodology_candidate_id=methodology_candidate_id,
            methodology_candidate_uri=methodology_candidate_uri,
            methodology_candidate=methodology_candidate,
            extraction_report_id=extraction_report_id,
            extraction_report_uri=extraction_report_uri,
        )
    except (ResearchArtifactStoreError, ValueError) as exc:
        return _validation_error(KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE, str(exc))

    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    blockers: list[str] = []
    warnings: list[str] = []
    checked_refs: list[Mapping[str, Any]] = []
    source_types_by_id: dict[str, str] = {}
    packet = _load_lineage_packet(artifact_store, candidate)
    try:
        chunks, sources = _load_candidate_context(store, candidate)
        source_types_by_id = {source_id: source.source_type for source_id, source in sources.items()}
    except (KnowledgeStoreError, ValueError) as exc:
        chunks = tuple()
        sources = {}
        blockers.append(str(exc))

    field_entries = _iter_populated_fields(candidate)
    if not field_entries:
        blockers.append("candidate has no populated methodology fields")
    for path, field in field_entries:
        for ref in field.evidence_refs:
            checked_ref, ref_blockers = _validate_ref(ref, chunks, sources)
            checked_ref["field_path"] = path
            checked_refs.append(checked_ref)
            blockers.extend(ref_blockers)
        blockers.extend(_quote_blockers(path, field.value))
        blockers.extend(_field_claim_semantic_blockers(path, field, candidate))

    blockers.extend(_semantic_identity_blockers(candidate))
    readiness_summary = _readiness_summary(candidate, packet)
    if packet is None:
        blockers.append("methodology candidate validation requires methodology_evidence_packet lineage")
    else:
        blockers.extend(packet.blockers)
        blockers.extend(_semantic_role_blockers(candidate, field_entries, packet))
        blockers.extend(_target_bound_packet_blockers(field_entries, packet, chunks))
        requested_readiness = str(candidate.lineage.get("readiness_goal") or packet.readiness_goal or "descriptive")
        blockers.extend(_readiness_level_blockers(readiness_summary, requested_readiness))
    blockers.extend(_family_minimum_blockers(candidate))
    blockers.extend(_high_risk_blockers(candidate))
    blockers.extend(_source_policy_blockers(candidate, field_entries, source_types_by_id))
    status = "blocked" if blockers else "passed"
    report = MethodologyCandidateValidationReport(
        validation_id=stable_research_id(
            "methodology_candidate_validation",
            {
                "candidate_id": candidate.methodology_candidate_id,
                "status": status,
                "field_paths": [path for path, _ in field_entries],
                "blockers": blockers,
            },
        ),
        methodology_candidate_id=candidate.methodology_candidate_id,
        status=status,
        valid=status == "passed",
        field_summary={
            "populated_field_count": len(field_entries),
            "populated_fields": [path for path, _ in field_entries],
            "families": list(candidate.families),
        },
        source_summary={
            "source_ids": list(candidate.source_ids),
            "chunk_ids": list(candidate.chunk_ids),
            "source_types": source_types_by_id,
        },
        readiness_summary=readiness_summary,
        checked_refs=tuple(checked_refs),
        warnings=tuple(warnings),
        blockers=tuple(dict.fromkeys(blockers)),
    )
    try:
        candidate_record = artifact_store.save_artifact(
            artifact_type=METHODOLOGY_CANDIDATE,
            artifact_id=candidate.methodology_candidate_id,
            payload=candidate.to_dict(),
            status=candidate.status,
            metadata={
                "families": list(candidate.families),
                "source_ids": list(candidate.source_ids),
                "chunk_ids": list(candidate.chunk_ids),
            },
        )
        report = replace(report, candidate_ref=candidate_record.reference().to_dict())
        report_record = artifact_store.save_artifact(
            artifact_type=METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
            artifact_id=report.validation_id,
            payload=report.to_dict(),
            status=report.status,
            metadata={"methodology_candidate_id": candidate.methodology_candidate_id},
        )
    except ResearchArtifactStoreError as exc:
        return _artifact_store_error(KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE, str(exc))

    data = {
        "methodology_candidate_validation_report": report.to_dict(),
    }
    artifacts = {
        "methodology_candidate_validation_report": report_record.reference().to_dict(),
    }
    if blockers:
        return error_envelope(
            command=KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="methodology_candidate_validation_failed",
            message="methodology candidate validation failed",
            data=data,
        )
    return success_envelope(
        command=KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE,
        side_effect=SideEffect.LOCAL_MUTATING,
        data=data,
        artifacts=artifacts,
        warnings=tuple(warnings),
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


def _resolve_candidate_or_packet(
    artifact_store: ResearchArtifactStore,
    *,
    methodology_candidate_id: str | None,
    methodology_candidate_uri: str | None,
    methodology_candidate: Mapping[str, Any] | None,
    evidence_packet_id: str | None,
    evidence_packet_uri: str | None,
    evidence_packet: Mapping[str, Any] | None,
) -> tuple[MethodologyCandidate, MethodologyEvidencePacket | None]:
    candidate_inputs = [
        bool(methodology_candidate_id),
        bool(methodology_candidate_uri),
        methodology_candidate is not None,
    ]
    packet_inputs = [bool(evidence_packet_id), bool(evidence_packet_uri), evidence_packet is not None]
    if sum(candidate_inputs) + sum(packet_inputs) != 1:
        raise ValueError(
            "exactly one candidate input or evidence packet input is required"
        )
    if not any(packet_inputs):
        return (
            _resolve_candidate(
                artifact_store,
                methodology_candidate_id=methodology_candidate_id,
                methodology_candidate_uri=methodology_candidate_uri,
                methodology_candidate=methodology_candidate,
            ),
            None,
        )
    if evidence_packet is not None:
        packet_payload = evidence_packet
    elif evidence_packet_uri:
        packet_payload = load_artifact_ref(artifact_store, METHODOLOGY_EVIDENCE_PACKET, evidence_packet_uri)
    else:
        packet_payload = artifact_store.load_artifact(METHODOLOGY_EVIDENCE_PACKET, str(evidence_packet_id))
    if packet_payload.get("artifact_type") != METHODOLOGY_EVIDENCE_PACKET:
        raise ValueError("evidence packet artifact_type must be methodology_evidence_packet")
    packet = MethodologyEvidencePacket.from_dict(packet_payload)
    candidate_ref = dict(packet.candidate_ref)
    uri = str(candidate_ref.get("uri") or "").strip()
    if uri:
        candidate_payload = load_artifact_ref(artifact_store, METHODOLOGY_CANDIDATE, uri)
    else:
        candidate_payload = artifact_store.load_artifact(METHODOLOGY_CANDIDATE, packet.methodology_candidate_id)
    if candidate_payload.get("artifact_type") != METHODOLOGY_CANDIDATE:
        raise ValueError("evidence packet candidate_ref must resolve to methodology_candidate")
    candidate = MethodologyCandidate.from_dict(candidate_payload)
    if candidate.methodology_candidate_id != packet.methodology_candidate_id:
        raise ValueError("evidence packet candidate_id does not match resolved methodology candidate")
    return candidate, packet


def _resolve_candidate_or_extraction(
    artifact_store: ResearchArtifactStore,
    *,
    methodology_candidate_id: str | None,
    methodology_candidate_uri: str | None,
    methodology_candidate: Mapping[str, Any] | None,
    extraction_report_id: str | None,
    extraction_report_uri: str | None,
) -> MethodologyCandidate:
    supplied = [
        bool(methodology_candidate_id),
        bool(methodology_candidate_uri),
        methodology_candidate is not None,
        bool(extraction_report_id),
        bool(extraction_report_uri),
    ]
    if sum(supplied) != 1:
        raise ValueError(
            "exactly one candidate input or extraction report reference is required"
        )
    if extraction_report_id or extraction_report_uri:
        payload = (
            load_artifact_ref(artifact_store, METHODOLOGY_FIELD_EXTRACTION_REPORT, str(extraction_report_uri))
            if extraction_report_uri
            else artifact_store.load_artifact(METHODOLOGY_FIELD_EXTRACTION_REPORT, str(extraction_report_id))
        )
        if payload.get("artifact_type") != METHODOLOGY_FIELD_EXTRACTION_REPORT:
            raise ValueError("extraction report artifact_type must be methodology_field_extraction_report")
        report = MethodologyFieldExtractionReport.from_dict(payload)
        return MethodologyCandidate.from_dict(
            artifact_store.load_artifact(METHODOLOGY_CANDIDATE, report.methodology_candidate_id)
        )
    return _resolve_candidate(
        artifact_store,
        methodology_candidate_id=methodology_candidate_id,
        methodology_candidate_uri=methodology_candidate_uri,
        methodology_candidate=methodology_candidate,
    )


def _load_lineage_packet(
    artifact_store: ResearchArtifactStore,
    candidate: MethodologyCandidate,
) -> MethodologyEvidencePacket | None:
    packet_id = candidate.lineage.get("evidence_packet_id")
    if not packet_id:
        return None
    try:
        payload = artifact_store.load_artifact(METHODOLOGY_EVIDENCE_PACKET, str(packet_id))
    except ResearchArtifactStoreError:
        return None
    if payload.get("artifact_type") != METHODOLOGY_EVIDENCE_PACKET:
        return None
    return MethodologyEvidencePacket.from_dict(payload)


def _load_candidate_context(
    store: KnowledgeStore,
    candidate: MethodologyCandidate,
    *,
    extra_chunk_ids: Sequence[str] = (),
) -> tuple[tuple[KnowledgeChunk, ...], dict[str, KnowledgeSourceManifest]]:
    if not candidate.chunk_ids:
        raise ValueError("methodology candidate has no chunk_ids")
    chunk_ids = tuple(dict.fromkeys((*candidate.chunk_ids, *extra_chunk_ids)))
    chunks = store.load_chunks_by_ids(chunk_ids)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    missing = tuple(chunk_id for chunk_id in candidate.chunk_ids if chunk_id not in chunks_by_id)
    if missing:
        raise ValueError(f"unknown candidate chunk_id: {', '.join(missing)}")
    sources: dict[str, KnowledgeSourceManifest] = {}
    for chunk in chunks:
        source = store.load_source(chunk.source_id)
        if source is None:
            raise ValueError(f"unknown source_id for chunk {chunk.chunk_id}: {chunk.source_id}")
        sources[source.source_id] = source
    return tuple(chunks_by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in chunks_by_id), sources


def _extract_fields(
    candidate: MethodologyCandidate,
    chunks: Sequence[KnowledgeChunk],
    sources: Mapping[str, KnowledgeSourceManifest],
    max_chars_per_chunk: int,
) -> tuple[MethodologyCandidate, tuple[str, ...], tuple[str, ...]]:
    del max_chars_per_chunk
    core = {
        group: dict(fields)
        for group, fields in candidate.core_fields.items()
    }
    extension = {
        group: dict(fields)
        for group, fields in candidate.extension_fields.items()
    }
    populated: list[str] = []
    warnings: list[str] = []
    first_chunk = chunks[0]
    first_ref = _field_ref(first_chunk, "source span supports methodology identity")
    _put(core, "identity", "method_name", candidate.title, first_ref, populated)
    source_titles = [sources[chunk.source_id].title for chunk in chunks if chunk.source_id in sources]
    _put(
        core,
        "identity",
        "source_context",
        tuple(dict.fromkeys(source_titles)),
        first_ref,
        populated,
    )
    text = "\n".join(chunk.text for chunk in chunks).lower()
    if any(term in text for term in ("price", "return", "returns", "spread", "option", "sentiment")):
        _put(
            core,
            "data_requirements",
            "required_inputs",
            _required_inputs(text),
            _field_ref(first_chunk, "source span identifies required inputs"),
            populated,
        )
    if any(term in text for term in ("step", "estimate", "test", "compute", "calculate", "rank", "score")):
        _put(
            core,
            "method_specification",
            "algorithm_steps",
            _algorithm_steps(candidate.families, text),
            _field_ref(first_chunk, "source span supports algorithm steps"),
            populated,
        )
    if any(term in text for term in ("signal", "entry", "exit", "threshold", "z-score", "buy", "sell")):
        _put(
            core,
            "signal_decision_logic",
            "entry_rules",
            "source evidence describes threshold or signal-driven entries",
            _field_ref(first_chunk, "source span supports signal or entry rules"),
            populated,
        )
    if any(term in text for term in ("exit", "mean reverts", "mean revert", "reversion")):
        _put(
            core,
            "signal_decision_logic",
            "exit_rules",
            "source evidence describes exit or mean-reversion rules",
            _field_ref(first_chunk, "source span supports exit rules"),
            populated,
        )

    for family in candidate.families:
        _extract_family_fields(family, text, chunks, extension, populated)
    if not populated:
        warnings.append("deterministic extraction found no supported rich methodology fields")

    updated = MethodologyCandidate(
        methodology_candidate_id=candidate.methodology_candidate_id,
        title=candidate.title,
        families=candidate.families,
        status="extracted",
        source_ids=candidate.source_ids,
        chunk_ids=candidate.chunk_ids,
        candidate_spans=candidate.candidate_spans,
        method_identity=candidate.method_identity,
        core_fields=core,
        extension_fields=extension,
        lineage={**dict(candidate.lineage), "extraction_engine": "deterministic_rules"},
        warnings=tuple(dict.fromkeys((*candidate.warnings, *warnings))),
        blockers=candidate.blockers,
        created_at=candidate.created_at,
        schema_version=candidate.schema_version,
    )
    return updated, tuple(dict.fromkeys(populated)), tuple(warnings)


def _extract_fields_from_packet(
    candidate: MethodologyCandidate,
    packet: MethodologyEvidencePacket,
    chunks: Sequence[KnowledgeChunk],
    sources: Mapping[str, KnowledgeSourceManifest],
    max_chars_per_chunk: int,
) -> tuple[MethodologyCandidate, tuple[str, ...], tuple[str, ...]]:
    del sources
    core: dict[str, dict[str, EvidenceBackedField]] = {}
    extension: dict[str, dict[str, EvidenceBackedField]] = {}
    populated: list[str] = []
    warnings: list[str] = []
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    profile = profile_for_family(packet.family)
    if profile is None:
        warnings.append(f"unsupported evidence packet family: {packet.family}")
        return candidate, tuple(), tuple(warnings)

    role_claims_by_id = {
        str(role.get("role_id")): _role_claims(role, chunks_by_id)
        for role in packet.role_evidence
    }
    first_chunk = next(iter(chunks), None)
    identity_claims = role_claims_by_id.get("definition", tuple())
    identity_chunk = identity_claims[0][0] if identity_claims else first_chunk
    identity_span = identity_claims[0][1] if identity_claims else None
    if identity_chunk is not None and identity_span is not None:
        identity_ref = _field_ref(
            identity_chunk,
            "role evidence supports methodology identity",
            role_id="definition",
            claim_span=identity_span,
        )
        _put(
            core,
            "identity",
            "method_name",
            candidate.title,
            (identity_ref,),
            populated,
        )
        _put(
            core,
            "identity",
            "description",
            _claim_field_value("definition", packet.family, identity_claims, candidate, max_chars_per_chunk),
            (identity_ref,),
            populated,
        )

    for role in profile.roles:
        role_claims = role_claims_by_id.get(role.role_id, tuple())
        if not role_claims:
            continue
        for scope, group, field_name in role.field_paths:
            field_claims = _claims_for_field(field_name, role_claims)
            if not field_claims:
                continue
            value = _claim_field_value(
                role.role_id,
                packet.family,
                field_claims,
                candidate,
                max_chars_per_chunk,
            )
            if value is None:
                continue
            refs = tuple(
                _field_ref(
                    chunk,
                    f"role evidence supports {role.role_id.replace('_', ' ')}",
                    role_id=role.role_id,
                    claim_span=claim_span,
                )
                for chunk, claim_span in field_claims
            )
            if scope == "core_fields":
                _put(core, group, field_name, value, refs, populated, quality=f"role_evidence:{role.role_id}")
            elif scope == "extension_fields":
                _put(extension, group, field_name, value, refs, populated, quality=f"role_evidence:{role.role_id}")

    if not populated:
        warnings.append("role-grounded extraction found no supported fields")

    updated = MethodologyCandidate(
        methodology_candidate_id=candidate.methodology_candidate_id,
        title=candidate.title,
        families=tuple(dict.fromkeys((packet.family, *candidate.families))),
        status="extracted",
        source_ids=candidate.source_ids,
        chunk_ids=tuple(dict.fromkeys((*candidate.chunk_ids, *packet.chunk_ids))),
        candidate_spans=candidate.candidate_spans,
        method_identity=candidate.method_identity,
        core_fields=core,
        extension_fields=extension,
        lineage={
            **dict(candidate.lineage),
            "extraction_engine": "role_grounded_claim_spans",
            "extraction_version": "1",
            "evidence_packet_id": packet.evidence_packet_id,
            "evidence_profile": {"family": packet.family, "version": packet.profile_version},
            "readiness_goal": packet.readiness_goal,
            "missing_roles": list(packet.missing_roles),
        },
        warnings=tuple(dict.fromkeys((*candidate.warnings, *warnings))),
        blockers=tuple(dict.fromkeys((*candidate.blockers, *packet.blockers))),
        created_at=candidate.created_at,
        schema_version=candidate.schema_version,
    )
    return updated, tuple(dict.fromkeys(populated)), tuple(warnings)


def _extract_family_fields(
    family: str,
    text: str,
    chunks: Sequence[KnowledgeChunk],
    extension: dict[str, dict[str, EvidenceBackedField]],
    populated: list[str],
) -> None:
    ref = _field_ref(chunks[0], f"source span supports {family.replace('_', ' ')} field")
    if family == "statistical_arbitrage":
        if any(term in text for term in ("spread", "pair", "pairs")):
            _put(extension, family, "spread_definition", "spread between related assets", ref, populated)
            _put(extension, family, "leg_universe", "multiple related assets or legs", ref, populated)
        if "cointegration" in text:
            _put(extension, family, "cointegration_test", "cointegration test evidence", ref, populated)
        if "stationarity" in text or "stationary" in text:
            _put(extension, family, "stationarity_test", "stationarity check evidence", ref, populated)
        if "hedge ratio" in text or "regression" in text:
            _put(extension, family, "hedge_ratio_method", "hedge-ratio estimation evidence", ref, populated)
        if "z-score" in text or "standard deviation" in text:
            _put(extension, family, "entry_zscore", "z-score threshold evidence", ref, populated)
        if "exit" in text or "mean reverts" in text or "mean revert" in text:
            _put(extension, family, "exit_zscore", "mean-reversion exit threshold evidence", ref, populated)
    elif family == "options_derivatives":
        if any(term in text for term in ("option", "straddle", "call", "put")):
            _put(extension, family, "instrument_type", "options or derivative instruments", ref, populated)
        if "straddle" in text or ("call" in text and "put" in text):
            _put(extension, family, "legs", ("call leg", "put leg"), ref, populated)
            _put(extension, family, "payoff_profile", "straddle-style payoff exposure", ref, populated)
        if "strike" in text:
            _put(extension, family, "strike_selection", "strike selection evidence", ref, populated)
        if "expiry" in text or "expiration" in text:
            _put(extension, family, "expiry_selection", "expiry selection evidence", ref, populated)
        if "risk" in text or "greek" in text or "delta" in text:
            _put(extension, family, "greeks", "options risk sensitivity evidence", ref, populated)
    elif family == "technical_indicators":
        if any(term in text for term in ("rsi", "relative strength", "moving average", "indicator")):
            _put(extension, family, "input_series", "ordered price or return series", ref, populated)
            _put(extension, family, "indicator_formula", "technical indicator calculation evidence", ref, populated)
        if "period" in text or "lookback" in text or "window" in text:
            _put(extension, family, "lookback_period", "lookback or period evidence", ref, populated)
        if "overbought" in text:
            _put(extension, family, "overbought_threshold", "overbought threshold evidence", ref, populated)
        if "oversold" in text:
            _put(extension, family, "oversold_threshold", "oversold threshold evidence", ref, populated)
    elif family == "sentiment_alternative_data":
        if any(term in text for term in ("sentiment", "news", "social", "alternative data")):
            _put(extension, family, "source_type", "sentiment or alternative-data source", ref, populated)
            _put(extension, family, "raw_signal", "raw sentiment signal evidence", ref, populated)
        if "commodity" in text:
            _put(extension, family, "commodity_mapping", "commodity entity mapping evidence", ref, populated)
        if "aggregate" in text or "window" in text:
            _put(extension, family, "aggregation_window", "aggregation window evidence", ref, populated)
        if "score" in text or "scoring" in text:
            _put(extension, family, "scoring_model", "sentiment scoring evidence", ref, populated)
    elif family == "fundamental_valuation":
        if any(term in text for term in ("valuation", "discounted cash flow", "dcf")):
            _put(extension, family, "valuation_model", "valuation model evidence", ref, populated)
        if any(term in text for term in ("earnings", "cash flow", "balance sheet", "statement")):
            _put(extension, family, "financial_statement_inputs", "financial statement input evidence", ref, populated)
    elif family == "portfolio_construction":
        if any(term in text for term in ("portfolio", "allocation", "optimization")):
            _put(extension, family, "objective", "portfolio objective evidence", ref, populated)
            _put(extension, family, "allocation_method", "allocation method evidence", ref, populated)
        if "constraint" in text:
            _put(extension, family, "constraints", "portfolio constraint evidence", ref, populated)
        if "rebalance" in text:
            _put(extension, family, "rebalance_cadence", "rebalance cadence evidence", ref, populated)
    elif family == "risk_models":
        if any(term in text for term in ("risk", "var", "cvar", "value at risk")):
            _put(extension, family, "risk_measure", "risk measure evidence", ref, populated)
        if "confidence" in text:
            _put(extension, family, "confidence_level", "confidence level evidence", ref, populated)
        if "limit" in text:
            _put(extension, family, "limit_thresholds", "risk limit evidence", ref, populated)
    elif family == "execution_methods":
        if any(term in text for term in ("execution", "twap", "vwap", "order")):
            _put(extension, family, "execution_algorithm", "execution algorithm evidence", ref, populated)
        if "slice" in text:
            _put(extension, family, "order_slicing", "order-slicing evidence", ref, populated)
        if "slippage" in text:
            _put(extension, family, "slippage_model", "slippage model evidence", ref, populated)


def _role_claims(
    role: Mapping[str, Any],
    chunks_by_id: Mapping[str, KnowledgeChunk],
) -> tuple[tuple[KnowledgeChunk, EvidenceClaimSpan], ...]:
    claims: list[tuple[KnowledgeChunk, EvidenceClaimSpan]] = []
    seen: set[str] = set()
    for chunk_ref in role.get("chunks", ()):
        if not _accepted_role_chunk_ref(chunk_ref):
            continue
        chunk = chunks_by_id.get(str(chunk_ref.get("chunk_id") or ""))
        if chunk is None:
            continue
        for span_payload in chunk_ref.get("claim_spans", ()):
            if not isinstance(span_payload, Mapping):
                continue
            span = EvidenceClaimSpan.from_dict(span_payload)
            if span.span_id in seen:
                continue
            seen.add(span.span_id)
            claims.append((chunk, span))
    return tuple(claims)


_FIELD_SEMANTIC_TERMS: Mapping[str, tuple[str, ...]] = {
    "lookback_period": ("period", "lookback", "window"),
    "smoothing_method": ("smooth", "weighted", "exponential"),
    "warmup_period": ("warmup", "initial observations", "minimum observations"),
    "parameter_defaults": ("default", "recommended", "typically"),
    "overbought_threshold": ("overbought",),
    "oversold_threshold": ("oversold",),
    "normalization": ("normalize", "normalised", "normalized", "z-score", "ratio", "bounded"),
    "entry_rules": ("entry", "enter", "buy", "sell", "long", "short", "cross"),
    "exit_rules": ("exit", "close", "liquidat", "mean revert"),
    "assumptions": ("assume", "assumption", "requires", "subject to"),
    "failure_modes": ("failure", "risk", "whipsaw", "noise", "breakdown"),
    "known_limitations": ("limitation", "lag", "regime", "unstable", "sensitivity"),
    "validation_tests": ("validate", "test", "backtest", "out-of-sample", "no-lookahead", "sensitivity"),
}


def _claims_for_field(
    field_name: str,
    claims: Sequence[tuple[KnowledgeChunk, EvidenceClaimSpan]],
) -> tuple[tuple[KnowledgeChunk, EvidenceClaimSpan], ...]:
    terms = _FIELD_SEMANTIC_TERMS.get(field_name)
    if terms is None:
        return tuple(claims)
    return tuple(
        item
        for item in claims
        if any(term in item[1].text.lower() for term in terms)
    )


def _claim_field_value(
    role_id: str,
    family: str,
    claims: Sequence[tuple[KnowledgeChunk, EvidenceClaimSpan]],
    candidate: MethodologyCandidate,
    max_chars_per_chunk: int,
) -> Any | None:
    if role_id in {
        "formula_algorithm",
        "signal_logic",
        "entry_logic",
        "exit_logic",
        "spread_definition",
        "relationship_model",
        "limitations",
        "validation_requirements",
    }:
        synthesized = _bounded_claim_synthesis(candidate.title, claims)
        if synthesized:
            return synthesized
    synthetic_chunks = tuple(
        replace(chunk, text=span.text, text_hash=span.text_hash)
        for chunk, span in claims
    )
    return _role_field_value(role_id, family, synthetic_chunks, candidate, max_chars_per_chunk)


def _bounded_claim_synthesis(
    title: str,
    claims: Sequence[tuple[KnowledgeChunk, EvidenceClaimSpan]],
) -> str | None:
    selected: list[str] = []
    word_count = 0
    for _, span in claims:
        text = " ".join(span.text.split())
        if not text or text in selected:
            continue
        words = text.split()
        remaining = 60 - word_count
        if remaining <= 0:
            break
        selected.append(" ".join(words[:remaining]))
        word_count += min(len(words), remaining)
        if len(selected) == 3:
            break
    if not selected:
        return None
    return f"{title}: {' '.join(selected)}"[:480]


def _put(
    groups: dict[str, dict[str, EvidenceBackedField]],
    group: str,
    field_name: str,
    value: Any,
    refs: EvidenceReference | Sequence[EvidenceReference],
    populated: list[str],
    *,
    quality: str = "deterministic_keyword",
) -> None:
    groups.setdefault(group, {})
    existing = groups[group].get(field_name)
    if (
        existing is not None
        and existing.value is not None
        and not str(existing.quality or "").startswith("role_evidence:")
    ):
        return
    normalized_refs = (refs,) if isinstance(refs, EvidenceReference) else tuple(refs)
    groups[group][field_name] = EvidenceBackedField(
        value=value,
        evidence_refs=normalized_refs,
        confidence=0.65,
        quality=quality,
    )
    populated.append(f"{group}.{field_name}")


def _field_ref(
    chunk: KnowledgeChunk,
    claim: str,
    *,
    role_id: str | None = None,
    claim_span: EvidenceClaimSpan | None = None,
) -> EvidenceReference:
    if role_id is not None:
        claim = f"{claim}; evidence_role={role_id}"
    return EvidenceReference(
        source_id=chunk.source_id,
        chunk_id=chunk.chunk_id,
        locator=chunk.locator,
        claim=claim,
        claim_span=claim_span,
    )


def _first_role_chunk(
    role_chunks_by_id: Mapping[str, Sequence[KnowledgeChunk]],
    role_id: str,
) -> KnowledgeChunk | None:
    chunks = role_chunks_by_id.get(role_id, ())
    return chunks[0] if chunks else None


def _role_field_value(
    role_id: str,
    family: str,
    chunks: Sequence[KnowledgeChunk],
    candidate: MethodologyCandidate,
    max_chars_per_chunk: int,
) -> Any | None:
    if role_id in {"input_data", "leg_universe", "raw_source", "inputs", "data_estimator"}:
        return _role_inputs(role_id, family, chunks)
    if role_id in {"parameters", "selection_rules", "threshold_actions"}:
        return (
            _candidate_focused_sentence(candidate, chunks, max_chars_per_chunk=max_chars_per_chunk)
            or _role_sentence(role_id, chunks, max_chars_per_chunk=max_chars_per_chunk)
            or "source-backed parameters"
        )
    if role_id in {"signal_logic", "entry_logic", "exit_logic"}:
        return _role_sentence(role_id, chunks, max_chars_per_chunk=max_chars_per_chunk) or (
            "source-backed signal decision rule"
        )
    if role_id in {"limitations", "bias_limitations", "validation_limitations"}:
        return _role_sentence(role_id, chunks, max_chars_per_chunk=max_chars_per_chunk) or (
            "source-backed limitation or failure mode"
        )
    if role_id == "validation_requirements":
        return _role_sentence(role_id, chunks, max_chars_per_chunk=max_chars_per_chunk) or (
            "source-backed validation requirement"
        )
    if role_id in {
        "formula_algorithm",
        "spread_definition",
        "relationship_model",
        "stationarity_test",
        "objective",
        "allocation_constraints",
        "instrument_structure",
        "payoff_risk",
        "scoring_aggregation",
        "mapping",
        "rebalance_turnover",
        "risk_controls",
        "definition",
        "execution_methods",
        "scheduling_slicing",
        "cost_fill_model",
    }:
        return _role_summary(role_id, chunks, candidate=candidate, max_chars_per_chunk=max_chars_per_chunk)
    return _role_summary(role_id, chunks, candidate=candidate, max_chars_per_chunk=max_chars_per_chunk)


def _role_inputs(role_id: str, family: str, chunks: Sequence[KnowledgeChunk]) -> tuple[str, ...]:
    del role_id
    text = " ".join(chunk.text.lower() for chunk in chunks)
    inputs: list[str] = []
    if family == "statistical_arbitrage":
        if any(term in text for term in ("pair", "asset", "spread", "price")):
            inputs.append("aligned price series for multiple related assets")
    if family == "technical_indicators":
        if any(term in text for term in ("price", "close", "series")):
            inputs.append("ordered price series")
        if "return" in text:
            inputs.append("ordered return series")
    if family == "options_derivatives" and any(term in text for term in ("option", "call", "put")):
        inputs.append("option contract data")
    if family == "sentiment_alternative_data" and any(term in text for term in ("news", "text", "sentiment")):
        inputs.append("timestamped text or sentiment observations")
    if family == "risk_models" and any(term in text for term in ("return", "price", "portfolio", "covariance")):
        inputs.append("portfolio or asset return history")
    return tuple(dict.fromkeys(inputs or ("source-described input data",)))


def _role_summary(
    role_id: str,
    chunks: Sequence[KnowledgeChunk],
    *,
    candidate: MethodologyCandidate,
    max_chars_per_chunk: int = 4000,
) -> str:
    focused_sentence = _candidate_focused_sentence(candidate, chunks, max_chars_per_chunk=max_chars_per_chunk)
    if focused_sentence:
        return f"{candidate.title}: {focused_sentence}"
    sentence = _role_sentence(role_id, chunks, max_chars_per_chunk=max_chars_per_chunk)
    if sentence:
        return f"{candidate.title}: {sentence}"
    return f"{candidate.title}: source-backed {role_id.replace('_', ' ')} evidence"


def _candidate_focused_sentence(
    candidate: MethodologyCandidate,
    chunks: Sequence[KnowledgeChunk],
    *,
    max_chars_per_chunk: int,
) -> str | None:
    title = candidate.title.strip()
    if not title or title.lower().startswith("page "):
        return None
    title_terms = tuple(
        dict.fromkeys(
            term.lower()
            for term in title.replace("/", " ").replace("-", " ").split()
            if len(term.strip()) > 2
        )
    )
    if not title_terms:
        return None
    title_phrase = title.lower()
    for chunk in chunks:
        sentences = _sentences(chunk.text[:max_chars_per_chunk])
        for index, sentence in enumerate(sentences):
            if title_phrase in sentence.lower():
                return _join_formula_label(sentence, sentences, index)
    for chunk in chunks:
        sentences = _sentences(chunk.text[:max_chars_per_chunk])
        for index, sentence in enumerate(sentences):
            lower = sentence.lower()
            matched_terms = sum(1 for term in title_terms if term in lower)
            if matched_terms == len(title_terms):
                return _join_formula_label(sentence, sentences, index)
    return None


def _join_formula_label(sentence: str, sentences: Sequence[str], index: int) -> str:
    if sentence.rstrip().endswith(":") and index + 1 < len(sentences):
        return f"{sentence} {sentences[index + 1]}"[:240]
    return sentence[:240]


def _role_sentence(
    role_id: str,
    chunks: Sequence[KnowledgeChunk],
    *,
    max_chars_per_chunk: int,
) -> str | None:
    terms = tuple(term for term in role_id.replace("_", " ").split() if len(term) > 2)
    for chunk in chunks:
        text = chunk.text[:max_chars_per_chunk]
        sentences = _sentences(text)
        for index, sentence in enumerate(sentences):
            lower = sentence.lower()
            if any(term in lower for term in terms) or _role_sentence_matches(role_id, lower):
                if role_id == "formula_algorithm":
                    return _join_formula_label(sentence, sentences, index)
                return sentence[:240]
    for chunk in chunks:
        sentences = _sentences(chunk.text[:max_chars_per_chunk])
        if sentences:
            return sentences[0][:240]
    return None


def _role_sentence_matches(role_id: str, sentence: str) -> bool:
    if role_id in {"formula_algorithm", "definition"}:
        return any(term in sentence for term in ("formula", "compute", "calculate", "=", "defined"))
    if role_id == "parameters":
        return any(term in sentence for term in ("window", "width", "period", "lookback", "smoothing"))
    if role_id in {"signal_logic", "entry_logic", "exit_logic"}:
        return any(term in sentence for term in ("signal", "entry", "enter", "exit", "buy", "sell"))
    if role_id in {"limitations", "bias_limitations", "validation_limitations"}:
        return any(term in sentence for term in ("risk", "failure", "limitation", "assumption"))
    if role_id == "stationarity_test":
        return any(term in sentence for term in ("stationarity", "stationary", "cointegration", "test"))
    return False


def _sentences(text: str) -> tuple[str, ...]:
    normalized = " ".join(text.replace("\n", " ").split())
    if not normalized:
        return tuple()
    sentences: list[str] = []
    current: list[str] = []
    for char in normalized:
        current.append(char)
        if char in ".;:":
            sentence = "".join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
    tail = "".join(current).strip()
    if tail:
        sentences.append(tail)
    return tuple(sentences)


def _required_inputs(text: str) -> tuple[str, ...]:
    inputs: list[str] = []
    if "price" in text or "spread" in text:
        inputs.append("price series")
    if "return" in text:
        inputs.append("return series")
    if "option" in text:
        inputs.append("option chain")
    if "sentiment" in text or "news" in text:
        inputs.append("sentiment text")
    return tuple(inputs or ("source-described input data",))


def _algorithm_steps(families: Sequence[str], text: str) -> tuple[str, ...]:
    if "statistical_arbitrage" in families:
        return ("form spread", "estimate relationship", "evaluate mean-reversion signal")
    if "options_derivatives" in families:
        return ("select derivative legs", "evaluate payoff and risk exposure")
    if "technical_indicators" in families:
        return ("compute indicator from ordered series", "apply signal threshold")
    if "sentiment_alternative_data" in families:
        return ("map text to asset", "aggregate sentiment score")
    if "risk_models" in families:
        return ("estimate risk measure", "compare measure with limit")
    if "compute" in text or "calculate" in text:
        return ("compute source-described methodology",)
    return ("apply source-described methodology",)


def _extraction_report(
    candidate: MethodologyCandidate,
    *,
    status: str,
    evidence_packet_id: str | None = None,
    populated_fields: Sequence[str] = (),
    warnings: Sequence[str] = (),
    blockers: Sequence[str] = (),
) -> MethodologyFieldExtractionReport:
    extraction_id = stable_research_id(
        "methodology_field_extraction",
        {
            "candidate_id": candidate.methodology_candidate_id,
            "evidence_packet_id": evidence_packet_id,
            "chunk_ids": list(candidate.chunk_ids),
            "populated_fields": list(populated_fields),
            "blockers": list(blockers),
        },
    )
    return MethodologyFieldExtractionReport(
        extraction_id=extraction_id,
        methodology_candidate_id=candidate.methodology_candidate_id,
        status=status,
        evidence_packet_id=evidence_packet_id,
        source_ids=candidate.source_ids,
        chunk_ids=candidate.chunk_ids,
        populated_field_count=len(populated_fields),
        populated_fields=tuple(populated_fields),
        warnings=tuple(warnings),
        blockers=tuple(blockers),
    )


def _iter_populated_fields(candidate: MethodologyCandidate) -> tuple[tuple[str, EvidenceBackedField], ...]:
    fields: list[tuple[str, EvidenceBackedField]] = []
    for scope_name, groups in (("core_fields", candidate.core_fields), ("extension_fields", candidate.extension_fields)):
        for group, values in groups.items():
            for field_name, field in values.items():
                if _has_value(field.value):
                    fields.append((f"{scope_name}.{group}.{field_name}", field))
    return tuple(fields)


def _validate_ref(
    ref: EvidenceReference,
    chunks: Sequence[KnowledgeChunk],
    sources: Mapping[str, KnowledgeSourceManifest],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    blockers: list[str] = []
    checked = ref.to_dict()
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    if ref.source_id is None and ref.chunk_id is None:
        blockers.append("field evidence ref must include source_id or chunk_id")
        return checked, tuple(blockers)
    source = sources.get(ref.source_id or "")
    if ref.source_id is not None and source is None:
        blockers.append(f"unknown source_id: {ref.source_id}")
    chunk = chunks_by_id.get(ref.chunk_id or "")
    if ref.chunk_id is not None and chunk is None:
        blockers.append(f"unknown chunk_id: {ref.chunk_id}")
    if chunk is not None:
        if ref.source_id is not None and chunk.source_id != ref.source_id:
            blockers.append(f"chunk {ref.chunk_id} does not belong to source {ref.source_id}")
        for key, value in ref.locator.items():
            if chunk.locator.get(key) != value:
                blockers.append(f"locator mismatch for chunk {ref.chunk_id}: {key}")
                break
        checked["chunk_locator"] = dict(chunk.locator)
        if ref.claim_span is None:
            blockers.append(f"field evidence ref for chunk {ref.chunk_id} must include claim_span")
        else:
            blockers.extend(_claim_span_consistency_blockers(ref.claim_span, chunk))
    if source is not None:
        checked["source_type"] = source.source_type
        checked["source_status"] = source.status
    return checked, tuple(blockers)


def _quote_blockers(path: str, value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        word_count = len(value.split())
        if len(value) > 500 or word_count > 80:
            return (f"{path} appears to contain excessive direct quotation",)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        blockers: list[str] = []
        for item in value:
            blockers.extend(_quote_blockers(path, item))
        return tuple(blockers)
    return tuple()


def _semantic_role_blockers(
    candidate: MethodologyCandidate,
    fields: Sequence[tuple[str, EvidenceBackedField]],
    packet: MethodologyEvidencePacket,
) -> tuple[str, ...]:
    del candidate
    blockers: list[str] = []
    role_span_ids = {
        str(role.get("role_id")): {
            str(span.get("span_id"))
            for chunk in role.get("chunks", ())
            if isinstance(chunk, Mapping) and _accepted_role_chunk_ref(chunk)
            for span in chunk.get("claim_spans", ())
            if isinstance(span, Mapping)
        }
        for role in packet.role_evidence
    }
    for path, field in fields:
        role_id = _role_id_from_field(field)
        if role_id is None:
            continue
        allowed_span_ids = role_span_ids.get(role_id, set())
        if not allowed_span_ids:
            blockers.append(f"{path} cites role {role_id} but the evidence packet has no claim spans for that role")
            continue
        for ref in field.evidence_refs:
            if ref.claim_span is None:
                blockers.append(f"{path} must cite an addressable claim span for evidence role {role_id}")
                continue
            if ref.claim_span.evidence_role != role_id:
                blockers.append(f"{path} claim span role does not match evidence role {role_id}")
            if ref.claim_span.span_id not in allowed_span_ids:
                blockers.append(f"{path} cites claim spans outside evidence role {role_id}")
    return tuple(blockers)


def _field_claim_semantic_blockers(
    path: str,
    field: EvidenceBackedField,
    candidate: MethodologyCandidate,
) -> tuple[str, ...]:
    blockers: list[str] = []
    field_name = path.rsplit(".", 1)[-1]
    semantic_terms = _FIELD_SEMANTIC_TERMS.get(field_name)
    spans = tuple(ref.claim_span for ref in field.evidence_refs if ref.claim_span is not None)
    if semantic_terms and spans and not any(
        term in span.text.lower()
        for span in spans
        for term in semantic_terms
    ):
        blockers.append(f"{path} is not entailed by its cited claim spans")
    supported_targets = {_normalize_identity(term) for term in _identity_terms(candidate)}
    supported_targets.add(_normalize_identity(candidate.title))
    for span in spans:
        if _normalize_identity(span.target_method) not in supported_targets:
            blockers.append(f"{path} claim span target does not match candidate method identity")
        if span.target_binding not in ACCEPTED_TARGET_BINDINGS:
            blockers.append(f"{path} cites a claim span without accepted target binding")
    return tuple(blockers)


def _semantic_identity_blockers(candidate: MethodologyCandidate) -> tuple[str, ...]:
    identity = candidate.method_identity if isinstance(candidate.method_identity, Mapping) else {}
    identity_terms = _identity_terms(candidate)
    blockers: list[str] = []
    if not identity_terms:
        blockers.append("candidate method identity must include source-backed canonical name or aliases")
    evidence_ids = identity.get("identity_evidence_unit_ids")
    if not isinstance(evidence_ids, Sequence) or isinstance(evidence_ids, (str, bytes)) or not evidence_ids:
        blockers.append("candidate method identity must include direct or alias evidence-unit refs")
    if identity_terms and _normalize_identity(candidate.title) not in {
        _normalize_identity(term) for term in identity_terms
    }:
        blockers.append("candidate title is not supported by method identity or alias evidence")
    return tuple(blockers)


def _target_bound_packet_blockers(
    fields: Sequence[tuple[str, EvidenceBackedField]],
    packet: MethodologyEvidencePacket,
    chunks: Sequence[KnowledgeChunk],
) -> tuple[str, ...]:
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    blockers: list[str] = []
    accepted_by_chunk: dict[str, list[Mapping[str, Any]]] = {}
    accepted_span_ids: set[str] = set()
    for role in packet.role_evidence:
        for chunk_ref in role.get("chunks", ()):
            if not isinstance(chunk_ref, Mapping):
                continue
            chunk_id = str(chunk_ref.get("chunk_id") or "")
            if not _accepted_role_chunk_ref(chunk_ref):
                continue
            accepted_by_chunk.setdefault(chunk_id, []).append(chunk_ref)
            if not chunk_ref.get("matched_role_terms"):
                blockers.append(f"accepted role evidence chunk {chunk_id} is missing matched role terms")
            accepted_span_ids.update(
                str(span.get("span_id"))
                for span in chunk_ref.get("claim_spans", ())
                if isinstance(span, Mapping) and str(span.get("span_id") or "")
            )
            blockers.extend(_packet_ref_consistency_blockers(chunk_ref, chunks_by_id))

    accepted_chunk_ids = set(accepted_by_chunk)
    for path, field in fields:
        for ref in field.evidence_refs:
            if ref.chunk_id is None:
                continue
            if ref.chunk_id not in accepted_chunk_ids:
                blockers.append(f"{path} cites chunk {ref.chunk_id} outside accepted target-bound evidence")
            if ref.claim_span is None:
                blockers.append(f"{path} must cite a target-bound claim span")
                continue
            if ref.claim_span.span_id not in accepted_span_ids:
                blockers.append(f"{path} cites claim span outside accepted target-bound evidence")
    return tuple(dict.fromkeys(blockers))


def _packet_ref_consistency_blockers(
    chunk_ref: Mapping[str, Any],
    chunks_by_id: Mapping[str, KnowledgeChunk],
) -> tuple[str, ...]:
    chunk_id = str(chunk_ref.get("chunk_id") or "")
    chunk = chunks_by_id.get(chunk_id)
    if chunk is None:
        return (f"accepted role evidence chunk {chunk_id} is missing from candidate context",)
    blockers: list[str] = []
    if str(chunk_ref.get("source_id") or "") != chunk.source_id:
        blockers.append(f"accepted role evidence chunk {chunk_id} has stale source_id")
    if str(chunk_ref.get("text_hash") or "") != chunk.text_hash:
        blockers.append(f"accepted role evidence chunk {chunk_id} has stale text_hash")
    locator = chunk_ref.get("locator")
    if isinstance(locator, Mapping):
        for key, value in locator.items():
            if chunk.locator.get(key) != value:
                blockers.append(f"accepted role evidence chunk {chunk_id} has stale locator: {key}")
                break
    for span_payload in chunk_ref.get("claim_spans", ()):
        if not isinstance(span_payload, Mapping):
            blockers.append(f"accepted role evidence chunk {chunk_id} has invalid claim span payload")
            continue
        try:
            span = EvidenceClaimSpan.from_dict(span_payload)
        except (TypeError, ValueError) as exc:
            blockers.append(f"accepted role evidence chunk {chunk_id} has invalid claim span: {exc}")
            continue
        blockers.extend(_claim_span_consistency_blockers(span, chunk))
    return tuple(blockers)


def _claim_span_consistency_blockers(
    span: EvidenceClaimSpan,
    chunk: KnowledgeChunk,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if span.end_char > len(chunk.text):
        blockers.append(f"claim span {span.span_id} exceeds chunk {chunk.chunk_id} text length")
        return tuple(blockers)
    stored_text = chunk.text[span.start_char:span.end_char]
    if stored_text != span.text:
        blockers.append(f"claim span {span.span_id} text does not match chunk {chunk.chunk_id}")
    if span.text_hash != hashlib.sha256(stored_text.encode("utf-8")).hexdigest():
        blockers.append(f"claim span {span.span_id} has stale text_hash")
    return tuple(blockers)


def _readiness_level_blockers(readiness_summary: Mapping[str, Any], readiness_goal: str) -> tuple[str, ...]:
    normalized_goal = str(readiness_goal or "descriptive").strip().lower().replace("-", "_").replace(" ", "_")
    level = readiness_summary.get(normalized_goal)
    if not isinstance(level, Mapping):
        return (f"methodology candidate validation missing target-bound {normalized_goal} readiness",)
    if str(level.get("status") or "") == "passed":
        return tuple()
    missing = ", ".join(str(role) for role in level.get("missing_roles", ()))
    suffix = f"; missing roles: {missing}" if missing else ""
    return (f"methodology candidate {normalized_goal} readiness must be target-bound and passed{suffix}",)


def _role_id_from_field(field: EvidenceBackedField) -> str | None:
    quality = str(field.quality or "")
    prefix = "role_evidence:"
    if quality.startswith(prefix):
        return quality[len(prefix):]
    for ref in field.evidence_refs:
        claim = str(ref.claim or "")
        marker = "evidence_role="
        if marker in claim:
            return claim.split(marker, 1)[1].split()[0].strip(" ;,")
    return None


def _readiness_summary(
    candidate: MethodologyCandidate,
    packet: MethodologyEvidencePacket | None,
) -> Mapping[str, Any]:
    if packet is None:
        return {
            "source": "legacy_candidate_validation",
            "descriptive": {
                "status": "unknown",
                "reason": "no methodology_evidence_packet lineage was available",
            },
        }
    profile = profile_for_family(packet.family)
    if profile is None:
        return {"source": "methodology_evidence_packet", "family": packet.family, "blockers": ["unsupported family"]}
    found_roles = {
        str(role.get("role_id"))
        for role in packet.role_evidence
        if str(role.get("status") or "") == "found"
        and any(_accepted_role_chunk_ref(chunk) for chunk in role.get("chunks", ()))
    }
    levels: dict[str, Any] = {}
    for level in profile.readiness_required_roles:
        required = set(required_roles_for_readiness(profile, level))
        missing = sorted(required - found_roles)
        levels[level] = {
            "status": "passed" if not missing else "blocked",
            "required_roles": sorted(required),
            "missing_roles": missing,
        }
    levels["candidate_id"] = candidate.methodology_candidate_id
    levels["family"] = packet.family
    levels["evidence_packet_id"] = packet.evidence_packet_id
    levels["source"] = "methodology_evidence_packet"
    return levels


def _accepted_role_chunk_ref(chunk_ref: Any) -> bool:
    if not isinstance(chunk_ref, Mapping):
        return False
    return (
        bool(chunk_ref.get("accepted_target_binding"))
        and str(chunk_ref.get("target_binding") or "") in ACCEPTED_TARGET_BINDINGS
    )


def _identity_terms(candidate: MethodologyCandidate) -> tuple[str, ...]:
    identity = candidate.method_identity if isinstance(candidate.method_identity, Mapping) else {}
    terms = [
        str(identity.get("canonical_name") or ""),
        str(identity.get("source_name") or ""),
    ]
    for key in ("aliases", "abbreviations"):
        values = identity.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            terms.extend(str(value) for value in values)
    return tuple(dict.fromkeys(term.strip() for term in terms if term.strip()))


def _normalize_identity(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+-]+", str(text).lower()))


def _family_minimum_blockers(candidate: MethodologyCandidate) -> tuple[str, ...]:
    blockers: list[str] = []
    for family in candidate.families:
        has_method = _has_field(candidate, "core_fields", "identity", "method_name")
        has_input = _has_any_field(
            candidate,
            ("core_fields", "data_requirements", ("required_inputs", "price_fields", "option_chain_fields")),
            ("extension_fields", family, ("input_series", "instrument_type", "source_type", "financial_statement_inputs")),
        )
        if family == "technical_indicators":
            if not (has_method and has_input and _has_any_field(
                candidate,
                ("extension_fields", family, ("indicator_formula", "lookback_period")),
                ("core_fields", "method_specification", ("algorithm_steps",)),
                ("core_fields", "signal_decision_logic", ("signal_definition", "entry_rules")),
            )):
                blockers.append("technical_indicators requires method name, input data, and formula/algorithm/signal evidence")
        elif family == "statistical_arbitrage":
            if not (_has_any_field(candidate, ("extension_fields", family, ("spread_definition", "leg_universe"))) and _has_any_field(
                candidate,
                ("extension_fields", family, ("cointegration_test", "stationarity_test", "hedge_ratio_method")),
                ("core_fields", "signal_decision_logic", ("entry_rules", "exit_rules")),
            )):
                blockers.append("statistical_arbitrage requires leg/spread evidence plus relationship or entry/exit evidence")
        elif family == "options_derivatives":
            if not (_has_any_field(candidate, ("extension_fields", family, ("instrument_type", "legs", "payoff_profile"))) and _has_any_field(
                candidate,
                ("extension_fields", family, ("expiry_selection", "strike_selection", "greeks")),
                ("core_fields", "risk_validation", ("risk_controls",)),
            )):
                blockers.append("options_derivatives requires instrument/legs/payoff plus expiry/strike or risk evidence")
        elif family == "sentiment_alternative_data":
            if not (_has_any_field(candidate, ("extension_fields", family, ("source_type", "raw_signal"))) and _has_any_field(
                candidate,
                ("extension_fields", family, ("entity_mapping", "commodity_mapping")),
            ) and _has_any_field(candidate, ("extension_fields", family, ("aggregation_window", "scoring_model")))):
                blockers.append("sentiment_alternative_data requires source/raw signal, mapping, and aggregation/scoring evidence")
        elif family == "fundamental_valuation":
            if not _has_any_field(candidate, ("extension_fields", family, ("valuation_model", "financial_statement_inputs", "factor_exposures"))):
                blockers.append("fundamental_valuation requires valuation model or fundamental input evidence")
        elif family == "portfolio_construction":
            if not (_has_any_field(candidate, ("extension_fields", family, ("objective", "allocation_method"))) and _has_any_field(
                candidate,
                ("extension_fields", family, ("constraints", "rebalance_cadence", "risk_budget")),
            )):
                blockers.append("portfolio_construction requires objective/allocation plus constraint or rebalance evidence")
        elif family == "risk_models":
            if not (_has_any_field(candidate, ("extension_fields", family, ("risk_measure",))) and _has_any_field(
                candidate,
                ("extension_fields", family, ("confidence_level", "limit_thresholds", "stress_scenarios", "correlation_model", "covariance_estimator")),
            )):
                blockers.append("risk_models requires risk measure plus threshold, scenario, or model evidence")
        elif family == "execution_methods":
            if not (_has_any_field(candidate, ("extension_fields", family, ("execution_algorithm",))) and _has_any_field(
                candidate,
                ("extension_fields", family, ("order_slicing", "schedule", "fill_assumptions", "slippage_model")),
            )):
                blockers.append("execution_methods requires algorithm plus execution assumption evidence")
    return tuple(blockers)


def _high_risk_blockers(candidate: MethodologyCandidate) -> tuple[str, ...]:
    blockers = []
    for family in candidate.families:
        if family not in HIGH_RISK_FAMILIES:
            continue
        fields = candidate.extension_fields.get(family, {})
        evidenced_count = sum(
            1
            for field in fields.values()
            if _has_value(field.value) and any(ref.chunk_id for ref in field.evidence_refs)
        )
        if evidenced_count < 2:
            blockers.append(f"{family} requires at least two evidenced family-specific fields")
    return tuple(blockers)


def _source_policy_blockers(
    candidate: MethodologyCandidate,
    fields: Sequence[tuple[str, EvidenceBackedField]],
    source_types_by_id: Mapping[str, str],
) -> tuple[str, ...]:
    lineage = candidate.lineage.get("discovery") if isinstance(candidate.lineage.get("discovery"), Mapping) else {}
    claimed_source_types = set(str(item) for item in lineage.get("source_types", ())) if isinstance(lineage, Mapping) else set()
    if not claimed_source_types & {"method_textbook", "primary_paper", "foundation_textbook"}:
        return tuple()
    cited_source_types = {
        source_types_by_id.get(ref.source_id or "")
        for _, field in fields
        for ref in field.evidence_refs
        if ref.source_id is not None
    }
    if cited_source_types and cited_source_types <= {"internal_note"}:
        return ("textbook or primary-paper methodology claims cannot be backed only by internal_note evidence",)
    return tuple()


def _has_field(candidate: MethodologyCandidate, scope: str, group: str, field_name: str) -> bool:
    groups = candidate.core_fields if scope == "core_fields" else candidate.extension_fields
    field = groups.get(group, {}).get(field_name)
    return field is not None and _has_value(field.value)


def _has_any_field(candidate: MethodologyCandidate, *requirements: tuple[str, str, tuple[str, ...]]) -> bool:
    for scope, group, names in requirements:
        if any(_has_field(candidate, scope, group, name) for name in names):
            return True
    return False


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return bool(value)
    return True


def _validation_error(command: str, message: str) -> ToolEnvelope:
    return error_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="validation_error",
        message=message,
    )


def _artifact_store_error(command: str, message: str) -> ToolEnvelope:
    return error_envelope(
        command=command,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="research_artifact_store_unavailable",
        message=message,
    )
