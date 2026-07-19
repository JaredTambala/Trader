"""Methodology candidate validation."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from trader_research.foundation import ApplicationResult, error_result, stable_research_id, success_result
from trader_research.foundation.artifacts import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
)
from trader_research.governance.artifacts import (
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    QUANTITATIVE_METHODS_OWNER,
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
)
from .evidence_assembly import ACCEPTED_TARGET_BINDINGS
from .evidence_profiles import profile_for_family, required_roles_for_readiness
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError

from .methodology_context import (
    _FIELD_SEMANTIC_TERMS,
    _accepted_role_chunk_ref,
    _artifact_store_error,
    _has_value,
    _iter_populated_fields,
    _load_candidate_context,
    _load_lineage_packet,
    _resolve_candidate_or_extraction,
    _validation_error,
)

KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE = "knowledge_validate_methodology_candidate"


HIGH_RISK_FAMILIES = frozenset(
    {"statistical_arbitrage", "options_derivatives", "portfolio_construction", "risk_models"}
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
) -> ApplicationResult:
    """Validate evidence-backed methodology candidates before card creation."""
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
            agent_owner=QUANTITATIVE_METHODS_OWNER,
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
            agent_owner=QUANTITATIVE_METHODS_OWNER,
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
        return error_result(
            command=KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE,
            code="methodology_candidate_validation_failed",
            message="methodology candidate validation failed",
            data=data,
        )
    return success_result(
        command=KNOWLEDGE_VALIDATE_METHODOLOGY_CANDIDATE,
        data=data,
        artifacts=artifacts,
        warnings=tuple(warnings),
    )


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
