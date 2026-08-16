"""Extract nullable methodology fields from a canonical evidence packet.

Extraction is limited to cited packet chunks and records exact span support for
every populated value. Unsupported fields remain null with blockers or warnings;
the service never invents details merely to produce a complete method card.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.foundation import ApplicationResult, error_result, stable_research_id, success_result
from trader_research.foundation.artifacts import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
)
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_FIELD_EXTRACTION_REPORT,
)

from .domain import (
    EvidenceBackedField,
    EvidenceClaimSpan,
    EvidenceReference,
    KnowledgeChunk,
    KnowledgeSourceManifest,
    MethodologyCandidate,
    MethodologyEvidencePacket,
    MethodologyFieldExtractionReport,
)
from .evidence_profiles import profile_for_family
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError

from .methodology_context import (
    _FIELD_SEMANTIC_TERMS,
    _accepted_role_chunk_ref,
    _artifact_store_error,
    _load_candidate_context,
    _resolve_candidate_or_packet,
    _validation_error,
)

KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS = "knowledge_extract_methodology_fields"


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
) -> ApplicationResult:
    """Extract nullable methodology fields from one exact evidence packet.

    Candidate and packet inputs are resolved and their lineage is checked before
    role evidence is mapped to the maintained field schema. Only bounded cited
    text up to ``max_chars_per_chunk`` may populate a value, and each populated
    field retains exact evidence support. Missing support remains null.

    Returns:
        A result containing the persisted extraction report, field evidence,
        warnings, blockers, and canonical reference, or a structured validation,
        store, or persistence failure.
    """
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
                domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_FIELD_EXTRACTION_REPORT],
                producer_tool=KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS,
                artifact_type=METHODOLOGY_FIELD_EXTRACTION_REPORT,
                artifact_id=report.extraction_id,
                payload=report.to_dict(),
                status=report.status,
                metadata={"methodology_candidate_id": candidate.methodology_candidate_id},
            )
        except ResearchArtifactStoreError as store_exc:
            return _artifact_store_error(KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS, str(store_exc))
        return error_result(
            command=KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS,
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
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_CANDIDATE],
            producer_tool=KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS,
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
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[METHODOLOGY_FIELD_EXTRACTION_REPORT],
            producer_tool=KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS,
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

    return success_result(
        command=KNOWLEDGE_EXTRACT_METHODOLOGY_FIELDS,
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
        warnings.append("deterministic extraction found no supported methodology fields")

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
