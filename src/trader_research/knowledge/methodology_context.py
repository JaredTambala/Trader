"""Shared methodology candidate resolution and evidence context."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from trader_research.foundation import ApplicationResult, error_result
from trader_research.foundation.artifacts import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    load_artifact_ref,
)
from trader_research.governance.artifacts import (
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_EVIDENCE_PACKET,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
)

from .domain import (
    EvidenceBackedField,
    KnowledgeChunk,
    KnowledgeSourceManifest,
    MethodologyCandidate,
    MethodologyEvidencePacket,
    MethodologyFieldExtractionReport,
)
from .evidence_assembly import ACCEPTED_TARGET_BINDINGS
from .store import KnowledgeStore


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


def _iter_populated_fields(candidate: MethodologyCandidate) -> tuple[tuple[str, EvidenceBackedField], ...]:
    fields: list[tuple[str, EvidenceBackedField]] = []
    for scope_name, groups in (("core_fields", candidate.core_fields), ("extension_fields", candidate.extension_fields)):
        for group, values in groups.items():
            for field_name, field in values.items():
                if _has_value(field.value):
                    fields.append((f"{scope_name}.{group}.{field_name}", field))
    return tuple(fields)


def _accepted_role_chunk_ref(chunk_ref: Any) -> bool:
    if not isinstance(chunk_ref, Mapping):
        return False
    return (
        bool(chunk_ref.get("accepted_target_binding"))
        and str(chunk_ref.get("target_binding") or "") in ACCEPTED_TARGET_BINDINGS
    )


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


def _validation_error(command: str, message: str) -> ApplicationResult:
    return error_result(
        command=command,
        code="validation_error",
        message=message,
    )


def _artifact_store_error(command: str, message: str) -> ApplicationResult:
    return error_result(
        command=command,
        code="research_artifact_store_unavailable",
        message=message,
    )
