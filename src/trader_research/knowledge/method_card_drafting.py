"""Create draft method cards from passed methodology validation evidence.

Drafting resolves one exact passed validation report and its upstream candidate,
extraction, and evidence packet, then constructs a new immutable card revision.
The operation does not approve or publish the card for implementation use.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from trader_research.foundation import (
    ApplicationResult,
    error_result,
    stable_research_id,
    success_result,
)
from trader_research.foundation.artifacts import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    load_artifact_ref,
    research_artifact_uri,
)
from trader_research.governance.artifacts import (
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
)

from .domain import (
    EvidenceBackedField,
    EvidenceReference,
    MethodCard,
    MethodologyCandidate,
    MethodologyCandidateValidationReport,
)
from .store import KnowledgeStore, KnowledgeStoreError

from .method_card_sets import (
    _resolve_method_card_set_id,
    _source_fingerprint_from_sources,
    _sync_method_card_set,
)

KNOWLEDGE_CREATE_METHOD_CARD_DRAFT = "knowledge_create_method_card_draft"


def create_method_card_draft(
    *,
    artifact_root: str | Path,
    methodology_candidate_validation_id: str | None = None,
    methodology_candidate_validation_uri: str | None = None,
    methodology_candidate_validation_report: Mapping[str, Any] | None = None,
    method_id: str | None = None,
    title: str | None = None,
    family: str | None = None,
    version: int = 1,
    method_card_set_id: str | None = None,
    knowledge_store: KnowledgeStore | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ApplicationResult:
    """Create an immutable draft from passed methodology validation evidence.

    Exactly one validation input is resolved and required to be passed. Candidate,
    extraction, evidence-packet, source, and claim-span lineage are rechecked
    before requested identity fields are applied. The research artifact store is
    used to revalidate upstream methodology evidence; the new revision is saved
    through the supplied knowledge store and joined to its stable card set. It
    remains a draft.

    Returns:
        A result containing the draft and its knowledge-store reference, or a
        structured validation, lineage, or persistence failure.
    """
    if artifact_store is None:
        return _method_card_draft_error("research artifact store is required")
    if knowledge_store is None:
        return _method_card_draft_error("knowledge store is required")
    try:
        report = _resolve_methodology_validation_report(
            artifact_store,
            validation_id=methodology_candidate_validation_id,
            validation_uri=methodology_candidate_validation_uri,
            validation_report=methodology_candidate_validation_report,
        )
        _require_passed_methodology_validation(report)
        candidate = _load_validated_methodology_candidate(artifact_store, report)
        chunks, sources = _load_candidate_context(knowledge_store, candidate)
        refs = _collect_methodology_evidence_refs(candidate)
        if not refs:
            return _method_card_draft_error("validated methodology candidate has no field-level evidence refs")
        citation_result = _validate_source_evidence_refs(
            artifact_root=artifact_root,
            refs=refs,
            knowledge_store=knowledge_store,
        )
        if not citation_result.ok:
            return error_result(
                command=KNOWLEDGE_CREATE_METHOD_CARD_DRAFT,
                code="method_card_draft_validation_failed",
                message="method-card draft evidence validation failed",
                data=citation_result.data,
            )
        source_fingerprint = _source_fingerprint_from_sources(sources)
        draft = _method_card_from_candidate(
            candidate=candidate,
            report=report,
            chunks=chunks,
            sources=sources,
            method_id=method_id,
            title=title,
            family=family,
            version=version,
            method_card_set_id=method_card_set_id,
            source_fingerprint=source_fingerprint,
            evidence_refs=refs,
        )
        knowledge_store.save_method_card(draft)
        _sync_method_card_set(knowledge_store, draft, source_fingerprint=source_fingerprint)
    except (ValueError, KnowledgeStoreError, ResearchArtifactStoreError) as exc:
        return _method_card_draft_error(str(exc))
    return success_result(
        command=KNOWLEDGE_CREATE_METHOD_CARD_DRAFT,
        data={"method_card_draft": draft.to_dict()},
        artifacts={
            "method_card_draft": knowledge_store.artifact_reference("method_card_draft", draft.method_card_id),
        },
    )


def _resolve_methodology_validation_report(
    artifact_store: ResearchArtifactStore,
    *,
    validation_id: str | None,
    validation_uri: str | None,
    validation_report: Mapping[str, Any] | None,
) -> MethodologyCandidateValidationReport:
    supplied = [bool(validation_id), bool(validation_uri), validation_report is not None]
    if sum(supplied) != 1:
        raise ValueError(
            "exactly one of methodology_candidate_validation_id, "
            "methodology_candidate_validation_uri, or methodology_candidate_validation_report is required"
        )
    if validation_report is not None:
        payload = validation_report
    elif validation_uri:
        payload = load_artifact_ref(artifact_store, METHODOLOGY_CANDIDATE_VALIDATION_REPORT, validation_uri)
    else:
        payload = artifact_store.load_artifact(METHODOLOGY_CANDIDATE_VALIDATION_REPORT, str(validation_id))
    if payload.get("artifact_type") != METHODOLOGY_CANDIDATE_VALIDATION_REPORT:
        raise ValueError("validation report artifact_type must be methodology_candidate_validation_report")
    return MethodologyCandidateValidationReport.from_dict(payload)


def _require_passed_methodology_validation(report: MethodologyCandidateValidationReport) -> None:
    if report.status != "passed" or not report.valid:
        raise ValueError("methodology candidate validation report must have status=passed and valid=true")
    if report.blockers:
        raise ValueError("methodology candidate validation report blockers must be empty")
    readiness_blockers = _readiness_gate_blockers(report.readiness_summary, "implementation")
    if readiness_blockers:
        raise ValueError("; ".join(readiness_blockers))


def _readiness_gate_blockers(readiness_summary: Mapping[str, Any], required_level: str) -> list[str]:
    if not readiness_summary or readiness_summary.get("source") != "methodology_evidence_packet":
        return [
            "methodology candidate validation must include methodology_evidence_packet readiness "
            f"for {required_level}"
        ]
    level = readiness_summary.get(required_level)
    if not isinstance(level, Mapping):
        return [f"methodology candidate validation missing {required_level} readiness"]
    if str(level.get("status") or "") != "passed":
        missing = ", ".join(str(role) for role in level.get("missing_roles", ()))
        suffix = f"; missing roles: {missing}" if missing else ""
        return [f"methodology candidate validation {required_level} readiness must be passed{suffix}"]
    return []


def _load_validated_methodology_candidate(
    artifact_store: ResearchArtifactStore,
    report: MethodologyCandidateValidationReport,
) -> MethodologyCandidate:
    candidate_ref = dict(report.candidate_ref)
    uri = str(candidate_ref.get("uri") or "").strip()
    if uri:
        payload = load_artifact_ref(artifact_store, METHODOLOGY_CANDIDATE, uri)
    else:
        payload = artifact_store.load_artifact(METHODOLOGY_CANDIDATE, report.methodology_candidate_id)
    if payload.get("artifact_type") != METHODOLOGY_CANDIDATE:
        raise ValueError("validated candidate artifact_type must be methodology_candidate")
    candidate = MethodologyCandidate.from_dict(payload)
    if candidate.methodology_candidate_id != report.methodology_candidate_id:
        raise ValueError("validation report candidate_id does not match persisted methodology candidate")
    if candidate.blockers:
        raise ValueError("validated methodology candidate blockers must be empty")
    return candidate


def _load_candidate_context(
    store: KnowledgeStore,
    candidate: MethodologyCandidate,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if not candidate.chunk_ids:
        raise ValueError("methodology candidate has no chunk_ids")
    chunks = store.load_chunks_by_ids(candidate.chunk_ids)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    missing = [chunk_id for chunk_id in candidate.chunk_ids if chunk_id not in chunks_by_id]
    if missing:
        raise ValueError(f"unknown candidate chunk_id: {', '.join(missing)}")
    sources: dict[str, Any] = {}
    for chunk in chunks:
        source = store.load_source(chunk.source_id)
        if source is None:
            raise ValueError(f"unknown source_id for chunk {chunk.chunk_id}: {chunk.source_id}")
        sources[source.source_id] = source
    return tuple(chunks_by_id[chunk_id] for chunk_id in candidate.chunk_ids), sources


def _method_card_from_candidate(
    *,
    candidate: MethodologyCandidate,
    report: MethodologyCandidateValidationReport,
    chunks: Sequence[Any],
    sources: Mapping[str, Any],
    method_id: str | None,
    title: str | None,
    family: str | None,
    version: int,
    method_card_set_id: str | None,
    source_fingerprint: str | None,
    evidence_refs: Sequence[EvidenceReference],
) -> MethodCard:
    override_blockers = _method_card_semantic_blockers(
        candidate=candidate,
        report=report,
        method_id=method_id,
        title=title,
        family=family,
    )
    if override_blockers:
        raise ValueError("; ".join(override_blockers))
    resolved_family = (family or (candidate.families[0] if candidate.families else "")).strip()
    if not resolved_family:
        raise ValueError("method-card family is required")
    resolved_title = (title or candidate.title).strip()
    resolved_method_id = (method_id or _method_id_from_title(resolved_title)).strip()
    resolved_set_id = _resolve_method_card_set_id(
        method_card_set_id=method_card_set_id,
        method_id=resolved_method_id,
        title=resolved_title,
        family=resolved_family,
        source_fingerprint=source_fingerprint,
    )
    assumptions, inputs, outputs, failure_modes, blockers = _derive_summary_fields(candidate)
    if blockers:
        raise ValueError("; ".join(blockers))
    draft_id = stable_research_id(
        "method_card_draft",
        {
            "method_card_set_id": resolved_set_id,
            "method_id": resolved_method_id,
            "candidate_id": candidate.methodology_candidate_id,
            "validation_id": report.validation_id,
            "family": resolved_family,
            "version": version,
            "evidence_refs": [ref.to_dict() for ref in evidence_refs],
        },
    )
    validation_ref = {
        "artifact_type": METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
        "artifact_id": report.validation_id,
        "uri": research_artifact_uri(METHODOLOGY_CANDIDATE_VALIDATION_REPORT, report.validation_id),
        "status": report.status,
    }
    return MethodCard(
        method_card_id=draft_id,
        method_id=resolved_method_id,
        title=resolved_title,
        family=resolved_family,
        status="draft",
        version=int(version),
        method_card_set_id=resolved_set_id,
        revision_number=int(version),
        assumptions=assumptions,
        inputs=inputs,
        outputs=outputs,
        failure_modes=failure_modes,
        evidence_refs=tuple(evidence_refs),
        core_fields=candidate.core_fields,
        extension_fields=candidate.extension_fields,
        source_methodology_candidate_id=candidate.methodology_candidate_id,
        validation_refs=(validation_ref,),
        lineage={
            "created_by": KNOWLEDGE_CREATE_METHOD_CARD_DRAFT,
            "methodology_candidate_id": candidate.methodology_candidate_id,
            "methodology_validation_id": report.validation_id,
            "candidate_ref": dict(report.candidate_ref),
            "readiness_summary": dict(report.readiness_summary),
            "source_fingerprint": source_fingerprint,
            "source_hashes": {source_id: source.file_hash for source_id, source in sorted(sources.items())},
            "chunk_hashes": {chunk.chunk_id: chunk.text_hash for chunk in chunks},
            "candidate_lineage": dict(candidate.lineage),
        },
    )


def _method_card_semantic_blockers(
    *,
    candidate: MethodologyCandidate,
    report: MethodologyCandidateValidationReport,
    method_id: str | None,
    title: str | None,
    family: str | None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    identity_terms = _candidate_identity_terms(candidate)
    normalized_terms = {_normalize_identity(term) for term in identity_terms if _normalize_identity(term)}
    identity = candidate.method_identity if isinstance(candidate.method_identity, Mapping) else {}
    evidence_ids = identity.get("identity_evidence_unit_ids")
    if not identity_terms:
        blockers.append("method-card draft requires source-backed method identity terms")
    if not isinstance(evidence_ids, Sequence) or isinstance(evidence_ids, (str, bytes)) or not evidence_ids:
        blockers.append("method-card draft requires method identity evidence-unit refs")

    resolved_title = str(title or candidate.title).strip()
    if normalized_terms and _normalize_identity(resolved_title) not in normalized_terms:
        blockers.append("method-card title must be supported by candidate identity or alias evidence")

    if method_id is not None:
        supported_method_ids = {_method_id_from_title(term) for term in identity_terms}
        if str(method_id).strip() not in supported_method_ids:
            blockers.append("method-card method_id must be derived from candidate identity or alias evidence")

    if family is not None and str(family).strip() not in set(candidate.families):
        blockers.append("method-card family override must match a validated candidate family")
    readiness_packet_id = str(report.readiness_summary.get("evidence_packet_id") or "")
    candidate_packet_id = str(candidate.lineage.get("evidence_packet_id") or "")
    if report.readiness_summary.get("source") != "methodology_evidence_packet":
        blockers.append("method-card draft requires packet-backed semantic validation")
    if not readiness_packet_id or readiness_packet_id != candidate_packet_id:
        blockers.append("method-card draft requires candidate lineage matching validation evidence_packet_id")
    return tuple(dict.fromkeys(blockers))


def _candidate_identity_terms(candidate: MethodologyCandidate) -> tuple[str, ...]:
    identity = candidate.method_identity if isinstance(candidate.method_identity, Mapping) else {}
    terms = [candidate.title, str(identity.get("canonical_name") or ""), str(identity.get("source_name") or "")]
    for key in ("aliases", "abbreviations"):
        values = identity.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            terms.extend(str(value) for value in values)
    return tuple(dict.fromkeys(term.strip() for term in terms if term.strip()))


def _normalize_identity(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+-]+", str(text).lower()))


def _derive_summary_fields(
    candidate: MethodologyCandidate,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    blockers: list[str] = []
    assumptions = _first_values(
        candidate,
        ("core_fields", "risk_validation", "assumptions"),
        ("core_fields", "risk_validation", "known_limitations"),
        ("core_fields", "identity", "limitations"),
        ("extension_fields", "statistical_arbitrage", "mean_reversion_assumption"),
    )
    if not assumptions and _has_any_methodology_field(
        candidate,
        ("extension_fields", "statistical_arbitrage", "cointegration_test"),
        ("extension_fields", "statistical_arbitrage", "stationarity_test"),
        ("extension_fields", "statistical_arbitrage", "hedge_ratio_method"),
    ):
        assumptions = ("spread relationship is source-backed and should be monitored for mean reversion",)
    if not assumptions:
        blockers.append("method-card assumptions could not be derived from evidence-backed fields")

    inputs = _first_values(
        candidate,
        ("core_fields", "data_requirements", "required_inputs"),
        ("core_fields", "data_requirements", "price_fields"),
        ("extension_fields", "technical_indicators", "input_series"),
        ("extension_fields", "statistical_arbitrage", "leg_universe"),
    )
    if not inputs and _has_any_methodology_field(
        candidate,
        ("extension_fields", "statistical_arbitrage", "spread_definition"),
    ):
        inputs = ("price series for paired assets",)
    if not inputs:
        blockers.append("method-card inputs could not be derived from evidence-backed fields")

    outputs = _first_values(
        candidate,
        ("core_fields", "signal_decision_logic", "signal_definition"),
        ("core_fields", "signal_decision_logic", "entry_rules"),
        ("core_fields", "signal_decision_logic", "exit_rules"),
        ("core_fields", "signal_decision_logic", "ranking_rules"),
    )
    if not outputs and _has_any_methodology_field(
        candidate,
        ("extension_fields", "statistical_arbitrage", "spread_definition"),
        ("extension_fields", "statistical_arbitrage", "entry_zscore"),
    ):
        outputs = ("spread z-score signal",)
    if not outputs:
        blockers.append("method-card outputs could not be derived from evidence-backed fields")

    failure_modes = _first_values(
        candidate,
        ("core_fields", "risk_validation", "failure_modes"),
        ("core_fields", "risk_validation", "known_limitations"),
        ("core_fields", "identity", "limitations"),
        ("extension_fields", "statistical_arbitrage", "stop_loss"),
    )
    if not failure_modes and _has_any_methodology_field(
        candidate,
        ("extension_fields", "statistical_arbitrage", "cointegration_test"),
        ("extension_fields", "statistical_arbitrage", "hedge_ratio_method"),
    ):
        failure_modes = ("structural break or unstable spread relationship",)
    if not failure_modes:
        blockers.append("method-card failure_modes could not be derived from evidence-backed fields")
    return assumptions, inputs, outputs, failure_modes, tuple(blockers)


def _collect_methodology_evidence_refs(candidate: MethodologyCandidate) -> tuple[EvidenceReference, ...]:
    refs: list[EvidenceReference] = []
    for field in _iter_methodology_fields(candidate):
        if field.value is not None:
            refs.extend(field.evidence_refs)
    return _dedupe_refs(refs)


def _collect_method_card_evidence_refs(card: MethodCard) -> tuple[EvidenceReference, ...]:
    refs = list(card.evidence_refs)
    for field in _iter_field_group_fields(card.core_fields):
        if field.value is not None:
            refs.extend(field.evidence_refs)
    for field in _iter_field_group_fields(card.extension_fields):
        if field.value is not None:
            refs.extend(field.evidence_refs)
    return _dedupe_refs(refs)


def _iter_methodology_fields(candidate: MethodologyCandidate) -> tuple[EvidenceBackedField, ...]:
    return (
        *_iter_field_group_fields(candidate.core_fields),
        *_iter_field_group_fields(candidate.extension_fields),
    )


def _iter_field_group_fields(groups: Mapping[str, Mapping[str, EvidenceBackedField]]) -> tuple[EvidenceBackedField, ...]:
    fields: list[EvidenceBackedField] = []
    for group_name in sorted(groups):
        for field_name in sorted(groups[group_name]):
            fields.append(groups[group_name][field_name])
    return tuple(fields)


def _field_at(candidate: MethodologyCandidate, scope: str, group: str, field_name: str) -> EvidenceBackedField | None:
    groups = candidate.core_fields if scope == "core_fields" else candidate.extension_fields
    return groups.get(group, {}).get(field_name)


def _first_values(candidate: MethodologyCandidate, *paths: tuple[str, str, str]) -> tuple[str, ...]:
    for scope, group, field_name in paths:
        field = _field_at(candidate, scope, group, field_name)
        if field is None or field.value is None:
            continue
        values = _string_values(field.value)
        if values:
            return values
    return tuple()


def _has_any_methodology_field(candidate: MethodologyCandidate, *paths: tuple[str, str, str]) -> bool:
    for scope, group, field_name in paths:
        field = _field_at(candidate, scope, group, field_name)
        if field is not None and field.value is not None:
            return True
    return False


def _string_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return tuple()
    if isinstance(value, Mapping):
        return tuple(f"{key}: {item}" for key, item in value.items() if str(item).strip())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    return (text,) if text else tuple()


def _method_id_from_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.strip().lower()).strip("_")
    return slug or "method"


def _dedupe_refs(refs: Sequence[EvidenceReference]) -> tuple[EvidenceReference, ...]:
    by_key: dict[tuple[Any, ...], EvidenceReference] = {}
    for ref in refs:
        key = (
            ref.source_id,
            ref.chunk_id,
            tuple(sorted((str(key), str(value)) for key, value in ref.locator.items())),
            ref.method_card_id,
            ref.claim,
        )
        by_key.setdefault(key, ref)
    return tuple(by_key[key] for key in sorted(by_key, key=repr))


def _validate_source_evidence_refs(
    *,
    artifact_root: str | Path,
    refs: Sequence[EvidenceReference],
    knowledge_store: KnowledgeStore,
) -> ApplicationResult:
    from .evidence_validation import validate_source_evidence_refs

    return validate_source_evidence_refs(
        command=KNOWLEDGE_CREATE_METHOD_CARD_DRAFT,
        refs=refs,
        knowledge_store=knowledge_store,
    )


def _method_card_draft_error(message: str) -> ApplicationResult:
    return error_result(
        command=KNOWLEDGE_CREATE_METHOD_CARD_DRAFT,
        code="method_card_draft_error",
        message=message,
    )
