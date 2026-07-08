"""Method-card metadata and lifecycle services for Quant Methods evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from trader_research.artifact_store import (
    ResearchArtifactStore,
    ResearchArtifactStoreError,
    load_artifact_ref,
    research_artifact_uri,
)
from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import (
    METHODOLOGY_CANDIDATE,
    METHODOLOGY_CANDIDATE_VALIDATION_REPORT,
    stable_research_id,
)

from .domain import (
    EvidenceBackedField,
    EvidenceReference,
    MethodCard,
    MethodologyCandidate,
    MethodologyCandidateValidationReport,
    RichMethodCard,
)
from .storage import KnowledgeRepository
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_CREATE_METHOD_CARD_DRAFT = "knowledge_create_method_card_draft"
KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT = "knowledge_create_rich_method_card_draft"
KNOWLEDGE_PUBLISH_METHOD_CARD = "knowledge_publish_method_card"
KNOWLEDGE_UPDATE_METHOD_CARD_STATUS = "knowledge_update_method_card_status"

RETIRED_METHOD_CARD_STATUSES = frozenset({"rejected", "superseded"})
WRITABLE_RETIRED_METHOD_CARD_STATUSES = RETIRED_METHOD_CARD_STATUSES

SEEDED_METHOD_CARDS: tuple[MethodCard, ...] = (
    MethodCard(
        method_card_id="method_card_sma_seed_v1",
        method_id="sma",
        title="Simple moving average contract",
        family="indicator",
        status="approved",
        assumptions=("input observations are ordered", "period is a positive integer"),
        inputs=("price series",),
        outputs=("rolling mean series",),
        failure_modes=("insufficient warmup observations", "non-finite input values"),
    ),
    MethodCard(
        method_card_id="method_card_ema_seed_v1",
        method_id="ema",
        title="Exponential moving average contract",
        family="indicator",
        status="approved",
        assumptions=("input observations are ordered", "period controls smoothing"),
        inputs=("price series",),
        outputs=("exponentially weighted mean series",),
        failure_modes=("insufficient warmup observations", "non-finite input values"),
    ),
    MethodCard(
        method_card_id="method_card_rsi_seed_v1",
        method_id="rsi",
        title="Relative strength index contract",
        family="indicator",
        status="approved",
        assumptions=("input observations are ordered", "lossless flat windows produce bounded output"),
        inputs=("price series",),
        outputs=("bounded oscillator series",),
        failure_modes=("insufficient warmup observations", "division by zero edge cases"),
    ),
    MethodCard(
        method_card_id="method_card_rolling_volatility_seed_v1",
        method_id="rolling_volatility",
        title="Rolling volatility contract",
        family="transform",
        status="approved",
        assumptions=("returns are computed from ordered observations", "window is fixed before use"),
        inputs=("return series",),
        outputs=("rolling standard deviation series",),
        failure_modes=("insufficient warmup observations", "unstable tiny samples"),
    ),
    MethodCard(
        method_card_id="method_card_z_score_seed_v1",
        method_id="z_score",
        title="Z-score transform contract",
        family="transform",
        status="approved",
        assumptions=("scale estimate is non-zero", "window is fixed before use"),
        inputs=("numeric series",),
        outputs=("standardized series",),
        failure_modes=("zero variance window", "insufficient warmup observations"),
    ),
    MethodCard(
        method_card_id="method_card_rank_ic_seed_v1",
        method_id="rank_ic",
        title="Rank information coefficient diagnostic",
        family="signal_diagnostic",
        status="approved",
        assumptions=("signal and forward returns are aligned", "candidate family is declared before inference"),
        inputs=("signal observations", "forward return labels"),
        outputs=("rank correlation statistic", "p-value"),
        failure_modes=("missing labels", "overlapping horizon warnings", "small effective sample size"),
    ),
    MethodCard(
        method_card_id="method_card_benjamini_hochberg_seed_v1",
        method_id="benjamini_hochberg",
        title="Benjamini-Hochberg FDR correction",
        family="multiple_testing",
        status="approved",
        assumptions=("candidate family size is declared", "raw p-values come from a declared family"),
        inputs=("raw p-values", "false discovery rate"),
        outputs=("adjusted p-values", "rejection indicators"),
        failure_modes=("missing candidate family manifest", "invalid p-value range"),
    ),
)


def list_method_cards(
    artifact_root: str | Path,
    *,
    include_drafts: bool = False,
    knowledge_store: KnowledgeStore | None = None,
) -> tuple[MethodCard, ...]:
    """Return the merged method-card catalog in deterministic ID order.

    Seeded approved cards are always included, persisted cards are loaded from the
    supplied store or local repository, and duplicate IDs are collapsed by the last
    loaded card. Drafts are filtered out by default so callers that require stable
    evidence contracts do not accidentally use unpublished cards.
    """
    cards = list(SEEDED_METHOD_CARDS)
    cards.extend(_list_persisted_method_cards(artifact_root, knowledge_store=knowledge_store))
    cards = [card for card in cards if _method_card_visible(card, include_drafts=include_drafts)]
    by_id = {card.method_card_id: card for card in cards}
    return tuple(by_id[key] for key in sorted(by_id))


def get_method_card(
    artifact_root: str | Path,
    method_card_id: str,
    *,
    include_drafts: bool = False,
    knowledge_store: KnowledgeStore | None = None,
) -> MethodCard | None:
    """Look up a single method card from the merged seeded/persisted catalog.

    The lookup shares `list_method_cards` filtering semantics, including the
    default exclusion of drafts. Returning `None` rather than raising lets citation
    validation accumulate all missing-card blockers in one report.
    """
    for card in list_method_cards(artifact_root, include_drafts=include_drafts, knowledge_store=knowledge_store):
        if card.method_card_id == method_card_id:
            return card
    return None


def list_rich_method_cards(
    artifact_root: str | Path,
    *,
    include_drafts: bool = False,
    knowledge_store: KnowledgeStore | None = None,
) -> tuple[RichMethodCard, ...]:
    """Return persisted rich method cards with full nullable methodology fields.

    The shallow catalog remains authoritative for legacy method-card search. This
    helper is for rich-card-aware tools that need the full `card_format` payload.
    """
    cards = list(_list_persisted_rich_method_cards(artifact_root, knowledge_store=knowledge_store))
    cards = [card for card in cards if _method_card_visible(card, include_drafts=include_drafts)]
    by_id = {card.method_card_id: card for card in cards}
    return tuple(by_id[key] for key in sorted(by_id))


def get_rich_method_card(
    artifact_root: str | Path,
    method_card_id: str,
    *,
    include_drafts: bool = False,
    knowledge_store: KnowledgeStore | None = None,
) -> RichMethodCard | None:
    """Look up one rich method-card payload by ID."""
    for card in list_rich_method_cards(artifact_root, include_drafts=include_drafts, knowledge_store=knowledge_store):
        if card.method_card_id == method_card_id:
            return card
    return None


def method_cards_for_method(
    artifact_root: str | Path,
    method_id: str,
    *,
    include_drafts: bool = False,
    knowledge_store: KnowledgeStore | None = None,
) -> tuple[MethodCard, ...]:
    """Return all cards for one method ID using the standard catalog merge rules.

    This keeps seeded contracts and locally curated cards visible through the same
    interface, while `include_drafts` determines whether review-in-progress cards
    are included. The result preserves the deterministic ordering from
    `list_method_cards`.
    """
    return tuple(
        card
        for card in list_method_cards(
            artifact_root,
            include_drafts=include_drafts,
            knowledge_store=knowledge_store,
        )
        if card.method_id == method_id
    )


def search_method_cards(
    artifact_root: str | Path,
    query: str,
    *,
    family: str | None = None,
    include_drafts: bool = False,
    limit: int = 10,
    knowledge_store: KnowledgeStore | None = None,
) -> tuple[MethodCard, ...]:
    """Search method cards with deterministic substring matching over contract text.

    The search corpus includes method ID, title, family, assumptions, and failure
    modes, then optionally narrows results by family and draft visibility. It is
    intentionally simple and deterministic so tests and agent tools receive stable
    method suggestions without requiring a separate search index.
    """
    needle = query.strip().lower()
    cards = []
    for card in list_method_cards(artifact_root, include_drafts=include_drafts, knowledge_store=knowledge_store):
        if family and card.family != family:
            continue
        searchable = " ".join(
            (
                card.method_id,
                card.title,
                card.family,
                " ".join(card.assumptions),
                " ".join(card.failure_modes),
            )
        ).lower()
        if not needle or needle in searchable:
            cards.append(card)
    return tuple(cards[:limit])


def approved_method_card_ids_for_method(
    artifact_root: str | Path,
    method_id: str,
    *,
    knowledge_store: KnowledgeStore | None = None,
) -> tuple[str, ...]:
    """Return approved method-card IDs that can satisfy a method implementation.

    Draft cards are excluded by the underlying catalog call, so the returned IDs
    are suitable for implementation manifests that require approved evidence. The
    caller can inject a store to include persisted approvals alongside seeded
    contracts.
    """
    return tuple(
        card.method_card_id
        for card in method_cards_for_method(artifact_root, method_id, knowledge_store=knowledge_store)
    )


def has_approved_method_card(
    artifact_root: str | Path,
    method_card_ids: Sequence[str],
    *,
    knowledge_store: KnowledgeStore | None = None,
    method_id: str | None = None,
) -> bool:
    """Check whether any supplied card ID names an approved evidence contract.

    When `method_id` is provided, the approved card must also belong to that method
    so implementation registration cannot cite an unrelated approved contract. The
    function uses the default approved-only catalog view and therefore treats
    missing, draft, and planned cards as false.
    """
    cards = {
        card.method_card_id: card
        for card in list_method_cards(artifact_root, knowledge_store=knowledge_store)
    }
    if method_id is None:
        return any(cards.get(str(card_id)) is not None and cards[str(card_id)].approved for card_id in method_card_ids)
    return any(
        cards.get(str(card_id)) is not None
        and cards[str(card_id)].approved
        and cards[str(card_id)].method_id == method_id
        for card_id in method_card_ids
    )


def create_method_card_draft(
    *,
    artifact_root: str | Path,
    method_id: str,
    title: str,
    family: str,
    assumptions: Sequence[str],
    inputs: Sequence[str],
    outputs: Sequence[str],
    failure_modes: Sequence[str],
    evidence_refs: Sequence[Mapping[str, Any]],
    version: int = 1,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Validate method-card fields and persist a draft tied to source evidence.

    The command cleans required text fields, converts evidence mappings into typed
    references, validates those references against the knowledge store without
    requiring approved method cards, and writes a deterministic draft ID derived
    from method metadata plus evidence. The resulting card remains non-approved
    until a separate publish step records reviewer approval.
    """
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    try:
        refs = _evidence_refs(evidence_refs)
        _validate_card_fields(
            method_id=method_id,
            title=title,
            family=family,
            assumptions=assumptions,
            inputs=inputs,
            outputs=outputs,
            failure_modes=failure_modes,
            evidence_refs=refs,
        )
        citation_result = _validate_source_evidence_refs(
            artifact_root=artifact_root,
            refs=refs,
            knowledge_store=store,
        )
        if not citation_result.ok:
            return error_envelope(
                command=KNOWLEDGE_CREATE_METHOD_CARD_DRAFT,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="method_card_draft_validation_failed",
                message="method-card draft evidence validation failed",
                data=citation_result.data,
            )
        draft = MethodCard(
            method_card_id=stable_research_id(
                "method_card_draft",
                {
                    "method_id": method_id.strip(),
                    "title": title.strip(),
                    "family": family.strip(),
                    "version": version,
                    "evidence_refs": [ref.to_dict() for ref in refs],
                },
            ),
            method_id=method_id.strip(),
            title=title.strip(),
            family=family.strip(),
            status="draft",
            version=int(version),
            assumptions=_clean_tuple(assumptions),
            inputs=_clean_tuple(inputs),
            outputs=_clean_tuple(outputs),
            failure_modes=_clean_tuple(failure_modes),
            evidence_refs=refs,
        )
        store.save_method_card(draft)
    except (ValueError, KnowledgeStoreError) as exc:
        return error_envelope(
            command=KNOWLEDGE_CREATE_METHOD_CARD_DRAFT,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="method_card_draft_error",
            message=str(exc),
        )
    return success_envelope(
        command=KNOWLEDGE_CREATE_METHOD_CARD_DRAFT,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"method_card_draft": draft.to_dict()},
        artifacts={
            "method_card_draft": store.artifact_reference("method_card_draft", draft.method_card_id),
        },
        warnings=(
            "knowledge_create_method_card_draft creates a legacy/projection draft; "
            "canonical methodology workflows must use validated rich method-card drafts",
        ),
    )


def create_rich_method_card_draft(
    *,
    artifact_root: str | Path,
    methodology_candidate_validation_id: str | None = None,
    methodology_candidate_validation_uri: str | None = None,
    methodology_candidate_validation_report: Mapping[str, Any] | None = None,
    method_id: str | None = None,
    title: str | None = None,
    family: str | None = None,
    version: int = 1,
    knowledge_store: KnowledgeStore | None = None,
    artifact_store: ResearchArtifactStore | None = None,
) -> ToolEnvelope:
    """Promote a passed methodology-candidate validation report into a rich draft card."""
    if artifact_store is None:
        return _rich_draft_error("research artifact store is required")
    if knowledge_store is None:
        return _rich_draft_error("knowledge store is required")
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
            return _rich_draft_error("validated methodology candidate has no field-level evidence refs")
        citation_result = _validate_source_evidence_refs(
            artifact_root=artifact_root,
            refs=refs,
            knowledge_store=knowledge_store,
        )
        if not citation_result.ok:
            return error_envelope(
                command=KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="rich_method_card_draft_validation_failed",
                message="rich method-card draft evidence validation failed",
                data=citation_result.data,
            )
        draft = _rich_method_card_from_candidate(
            candidate=candidate,
            report=report,
            chunks=chunks,
            sources=sources,
            method_id=method_id,
            title=title,
            family=family,
            version=version,
            evidence_refs=refs,
        )
        knowledge_store.save_rich_method_card(draft)
    except (ValueError, KnowledgeStoreError, ResearchArtifactStoreError) as exc:
        return _rich_draft_error(str(exc))
    return success_envelope(
        command=KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"method_card_draft": draft.to_dict()},
        artifacts={
            "method_card_draft": knowledge_store.artifact_reference("method_card_draft", draft.method_card_id),
        },
    )


def publish_method_card(
    *,
    artifact_root: str | Path,
    draft_method_card_id: str,
    approved_method_card_id: str,
    approved_by: str,
    approval_note: str,
    approve: bool,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Approve a draft method card after explicit reviewer confirmation.

    Publishing requires `approve=True`, reviewer identity, an approval note, and a
    target approved-card ID. The draft's evidence is revalidated, identical
    republish attempts are treated as idempotent successes, and conflicting
    existing approved IDs return structured errors rather than overwriting review
    history.
    """
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    if not approve:
        return _publish_error("explicit approve=True is required")
    if not approved_by.strip():
        return _publish_error("approved_by is required")
    if not approval_note.strip():
        return _publish_error("approval_note is required")
    if not approved_method_card_id.strip():
        return _publish_error("approved_method_card_id is required")
    try:
        rich_draft = get_rich_method_card(
            artifact_root,
            draft_method_card_id,
            include_drafts=True,
            knowledge_store=store,
        )
        if rich_draft is not None:
            return _publish_rich_method_card(
                artifact_root=artifact_root,
                store=store,
                draft=rich_draft,
                approved_method_card_id=approved_method_card_id,
                approved_by=approved_by,
                approval_note=approval_note,
            )
        draft = get_method_card(
            artifact_root,
            draft_method_card_id,
            include_drafts=True,
            knowledge_store=store,
        )
        if draft is None:
            return _publish_error(f"unknown draft_method_card_id: {draft_method_card_id}")
        if draft.status != "draft":
            return _publish_error(f"method card is not a draft: {draft_method_card_id}")
        citation_result = _validate_source_evidence_refs(
            artifact_root=artifact_root,
            refs=draft.evidence_refs,
            knowledge_store=store,
        )
        if not citation_result.ok:
            return error_envelope(
                command=KNOWLEDGE_PUBLISH_METHOD_CARD,
                side_effect=SideEffect.LOCAL_MUTATING,
                code="method_card_publish_validation_failed",
                message="method-card publish evidence validation failed",
                data=citation_result.data,
            )
        approved = replace(
            draft,
            method_card_id=approved_method_card_id.strip(),
            status="approved",
            source_method_card_id=draft.method_card_id,
            approved_by=approved_by.strip(),
            approval_note=approval_note.strip(),
        )
        existing = get_method_card(
            artifact_root,
            approved.method_card_id,
            include_drafts=True,
            knowledge_store=store,
        )
        if existing is not None:
            if _comparable_card_payload(existing) != _comparable_card_payload(approved):
                return _publish_error(f"approved method card already exists with different content: {approved.method_card_id}")
            return success_envelope(
                command=KNOWLEDGE_PUBLISH_METHOD_CARD,
                side_effect=SideEffect.LOCAL_MUTATING,
                data={"method_card": existing.to_dict(), "idempotent": True},
                artifacts={
                    "method_card": store.artifact_reference("method_card", existing.method_card_id),
                },
                warnings=("approved method card already exists with identical content",),
            )
        store.save_method_card(approved)
    except KnowledgeStoreError as exc:
        return error_envelope(
            command=KNOWLEDGE_PUBLISH_METHOD_CARD,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="method_card_publish_error",
            message=str(exc),
        )
    return success_envelope(
        command=KNOWLEDGE_PUBLISH_METHOD_CARD,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"method_card": approved.to_dict(), "idempotent": False},
        artifacts={
            "method_card": store.artifact_reference("method_card", approved.method_card_id),
        },
    )


def update_method_card_status(
    *,
    artifact_root: str | Path,
    method_card_id: str,
    status: str,
    updated_by: str,
    note: str,
    superseded_by_method_card_id: str | None = None,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Retire a persisted method card through a controlled lifecycle update.

    This service intentionally supports only non-approval lifecycle transitions.
    Cards can be marked `rejected` or `superseded`, preserving the stored record
    for audit while excluding it from normal method-card search and approval
    checks.
    """
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    requested_status = status.strip().lower()
    if not method_card_id.strip():
        return _lifecycle_error("method_card_id is required")
    if requested_status not in WRITABLE_RETIRED_METHOD_CARD_STATUSES:
        allowed = ", ".join(sorted(WRITABLE_RETIRED_METHOD_CARD_STATUSES))
        return _lifecycle_error(f"status must be one of: {allowed}")
    if not updated_by.strip():
        return _lifecycle_error("updated_by is required")
    if not note.strip():
        return _lifecycle_error("note is required")
    superseded_by = str(superseded_by_method_card_id or "").strip() or None
    if requested_status == "superseded" and superseded_by is None:
        return _lifecycle_error("superseded_by_method_card_id is required when status=superseded")
    try:
        rich_card = _get_persisted_rich_method_card_any_status(
            artifact_root,
            method_card_id.strip(),
            knowledge_store=store,
        )
        if rich_card is not None:
            previous_status = rich_card.status
            updated_card = _retired_rich_method_card(
                rich_card,
                status=requested_status,
                updated_by=updated_by,
                note=note,
                superseded_by_method_card_id=superseded_by,
            )
            store.save_rich_method_card(updated_card)
        else:
            card = _get_persisted_method_card_any_status(
                artifact_root,
                method_card_id.strip(),
                knowledge_store=store,
            )
            if card is None:
                return _lifecycle_error(f"unknown persisted method_card_id: {method_card_id}")
            previous_status = card.status
            updated_card = _retired_method_card(
                card,
                status=requested_status,
                updated_by=updated_by,
                note=note,
                superseded_by_method_card_id=superseded_by,
            )
            store.save_method_card(updated_card)
    except KnowledgeStoreError as exc:
        return error_envelope(
            command=KNOWLEDGE_UPDATE_METHOD_CARD_STATUS,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="method_card_lifecycle_error",
            message=str(exc),
        )
    return success_envelope(
        command=KNOWLEDGE_UPDATE_METHOD_CARD_STATUS,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={
            "method_card": updated_card.to_dict(),
            "previous_status": previous_status,
            "idempotent": previous_status == requested_status,
        },
        artifacts={
            "method_card": store.artifact_reference("method_card", updated_card.method_card_id),
        },
        warnings=("retired method cards are preserved in storage but hidden from normal method-card search",),
    )


def _publish_rich_method_card(
    *,
    artifact_root: str | Path,
    store: KnowledgeStore,
    draft: RichMethodCard,
    approved_method_card_id: str,
    approved_by: str,
    approval_note: str,
) -> ToolEnvelope:
    if draft.status != "draft":
        return _publish_error(f"method card is not a draft: {draft.method_card_id}")
    refs = _collect_rich_card_evidence_refs(draft)
    citation_result = _validate_source_evidence_refs(
        artifact_root=artifact_root,
        refs=refs,
        knowledge_store=store,
    )
    if not citation_result.ok:
        return error_envelope(
            command=KNOWLEDGE_PUBLISH_METHOD_CARD,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="method_card_publish_validation_failed",
            message="method-card publish evidence validation failed",
            data=citation_result.data,
        )
    approved = replace(
        draft,
        method_card_id=approved_method_card_id.strip(),
        status="approved",
        source_method_card_id=draft.method_card_id,
        approved_by=approved_by.strip(),
        approval_note=approval_note.strip(),
        lineage={
            **dict(draft.lineage),
            "approval": {
                "approved_by": approved_by.strip(),
                "approval_note": approval_note.strip(),
                "source_method_card_id": draft.method_card_id,
            },
        },
    )
    existing_rich = get_rich_method_card(
        artifact_root,
        approved.method_card_id,
        include_drafts=True,
        knowledge_store=store,
    )
    existing = existing_rich or get_method_card(
        artifact_root,
        approved.method_card_id,
        include_drafts=True,
        knowledge_store=store,
    )
    if existing is not None:
        if _comparable_card_payload(existing) != _comparable_card_payload(approved):
            return _publish_error(f"approved method card already exists with different content: {approved.method_card_id}")
        return success_envelope(
            command=KNOWLEDGE_PUBLISH_METHOD_CARD,
            side_effect=SideEffect.LOCAL_MUTATING,
            data={"method_card": existing.to_dict(), "idempotent": True},
            artifacts={
                "method_card": store.artifact_reference("method_card", approved.method_card_id),
            },
            warnings=("approved method card already exists with identical content",),
        )
    store.save_rich_method_card(approved)
    return success_envelope(
        command=KNOWLEDGE_PUBLISH_METHOD_CARD,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"method_card": approved.to_dict(), "idempotent": False},
        artifacts={
            "method_card": store.artifact_reference("method_card", approved.method_card_id),
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
    if not readiness_summary or readiness_summary.get("source") == "legacy_candidate_validation":
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


def _rich_method_card_from_candidate(
    *,
    candidate: MethodologyCandidate,
    report: MethodologyCandidateValidationReport,
    chunks: Sequence[Any],
    sources: Mapping[str, Any],
    method_id: str | None,
    title: str | None,
    family: str | None,
    version: int,
    evidence_refs: Sequence[EvidenceReference],
) -> RichMethodCard:
    resolved_family = (family or (candidate.families[0] if candidate.families else "")).strip()
    if not resolved_family:
        raise ValueError("rich method-card family is required")
    resolved_title = (title or candidate.title).strip()
    resolved_method_id = (method_id or _method_id_from_title(resolved_title)).strip()
    assumptions, inputs, outputs, failure_modes, blockers = _derive_shallow_method_fields(candidate)
    if blockers:
        raise ValueError("; ".join(blockers))
    draft_id = stable_research_id(
        "method_card_draft",
        {
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
    return RichMethodCard(
        method_card_id=draft_id,
        method_id=resolved_method_id,
        title=resolved_title,
        family=resolved_family,
        status="draft",
        version=int(version),
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
            "created_by": KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT,
            "methodology_candidate_id": candidate.methodology_candidate_id,
            "methodology_validation_id": report.validation_id,
            "candidate_ref": dict(report.candidate_ref),
            "readiness_summary": dict(report.readiness_summary),
            "source_hashes": {source_id: source.file_hash for source_id, source in sorted(sources.items())},
            "chunk_hashes": {chunk.chunk_id: chunk.text_hash for chunk in chunks},
            "candidate_lineage": dict(candidate.lineage),
        },
    )


def _derive_shallow_method_fields(
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
    if not assumptions and _has_any_rich_field(
        candidate,
        ("extension_fields", "statistical_arbitrage", "cointegration_test"),
        ("extension_fields", "statistical_arbitrage", "stationarity_test"),
        ("extension_fields", "statistical_arbitrage", "hedge_ratio_method"),
    ):
        assumptions = ("spread relationship is source-backed and should be monitored for mean reversion",)
    if not assumptions:
        blockers.append("rich method-card assumptions could not be derived from evidence-backed fields")

    inputs = _first_values(
        candidate,
        ("core_fields", "data_requirements", "required_inputs"),
        ("core_fields", "data_requirements", "price_fields"),
        ("extension_fields", "technical_indicators", "input_series"),
        ("extension_fields", "statistical_arbitrage", "leg_universe"),
    )
    if not inputs and _has_any_rich_field(candidate, ("extension_fields", "statistical_arbitrage", "spread_definition")):
        inputs = ("price series for paired assets",)
    if not inputs:
        blockers.append("rich method-card inputs could not be derived from evidence-backed fields")

    outputs = _first_values(
        candidate,
        ("core_fields", "signal_decision_logic", "signal_definition"),
        ("core_fields", "signal_decision_logic", "entry_rules"),
        ("core_fields", "signal_decision_logic", "exit_rules"),
        ("core_fields", "signal_decision_logic", "ranking_rules"),
    )
    if not outputs and _has_any_rich_field(
        candidate,
        ("extension_fields", "statistical_arbitrage", "spread_definition"),
        ("extension_fields", "statistical_arbitrage", "entry_zscore"),
    ):
        outputs = ("spread z-score signal",)
    if not outputs:
        blockers.append("rich method-card outputs could not be derived from evidence-backed fields")

    failure_modes = _first_values(
        candidate,
        ("core_fields", "risk_validation", "failure_modes"),
        ("core_fields", "risk_validation", "known_limitations"),
        ("core_fields", "identity", "limitations"),
        ("extension_fields", "statistical_arbitrage", "stop_loss"),
    )
    if not failure_modes and _has_any_rich_field(
        candidate,
        ("extension_fields", "statistical_arbitrage", "cointegration_test"),
        ("extension_fields", "statistical_arbitrage", "hedge_ratio_method"),
    ):
        failure_modes = ("structural break or unstable spread relationship",)
    if not failure_modes:
        blockers.append("rich method-card failure_modes could not be derived from evidence-backed fields")
    return assumptions, inputs, outputs, failure_modes, tuple(blockers)


def _collect_methodology_evidence_refs(candidate: MethodologyCandidate) -> tuple[EvidenceReference, ...]:
    refs: list[EvidenceReference] = []
    for field in _iter_methodology_fields(candidate):
        if field.value is not None:
            refs.extend(field.evidence_refs)
    return _dedupe_refs(refs)


def _collect_rich_card_evidence_refs(card: RichMethodCard) -> tuple[EvidenceReference, ...]:
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


def _has_any_rich_field(candidate: MethodologyCandidate, *paths: tuple[str, str, str]) -> bool:
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
    return slug or "rich_method"


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


def _validate_card_fields(
    *,
    method_id: str,
    title: str,
    family: str,
    assumptions: Sequence[str],
    inputs: Sequence[str],
    outputs: Sequence[str],
    failure_modes: Sequence[str],
    evidence_refs: Sequence[EvidenceReference],
) -> None:
    if not method_id.strip():
        raise ValueError("method_id is required")
    if not title.strip():
        raise ValueError("title is required")
    if not family.strip():
        raise ValueError("family is required")
    if not _clean_tuple(assumptions):
        raise ValueError("assumptions are required")
    if not _clean_tuple(inputs):
        raise ValueError("inputs are required")
    if not _clean_tuple(outputs):
        raise ValueError("outputs are required")
    if not _clean_tuple(failure_modes):
        raise ValueError("failure_modes are required")
    if not evidence_refs:
        raise ValueError("at least one evidence_ref is required")
    if not any(ref.source_id is not None or ref.chunk_id is not None for ref in evidence_refs):
        raise ValueError("at least one source or chunk evidence_ref is required")


def _validate_source_evidence_refs(
    *,
    artifact_root: str | Path,
    refs: Sequence[EvidenceReference],
    knowledge_store: KnowledgeStore,
) -> ToolEnvelope:
    from .citation_validation import validate_citations

    return validate_citations(
        artifact_root=artifact_root,
        artifact={"knowledge_evidence_refs": [ref.to_dict() for ref in refs]},
        require_approved_method_card=False,
        knowledge_store=knowledge_store,
    )


def _evidence_refs(evidence_refs: Sequence[Mapping[str, Any]]) -> tuple[EvidenceReference, ...]:
    if isinstance(evidence_refs, Mapping) or isinstance(evidence_refs, (str, bytes)):
        raise ValueError("evidence_refs must be a list of evidence reference objects")
    return tuple(EvidenceReference.from_dict(ref) for ref in evidence_refs if isinstance(ref, Mapping))


def _list_persisted_method_cards(
    artifact_root: str | Path,
    *,
    knowledge_store: KnowledgeStore | None,
) -> tuple[MethodCard, ...]:
    if knowledge_store is not None:
        return knowledge_store.list_persisted_method_cards()
    return KnowledgeRepository(artifact_root).list_persisted_method_cards()


def _list_persisted_rich_method_cards(
    artifact_root: str | Path,
    *,
    knowledge_store: KnowledgeStore | None,
) -> tuple[RichMethodCard, ...]:
    if knowledge_store is not None:
        return knowledge_store.list_persisted_rich_method_cards()
    return KnowledgeRepository(artifact_root).list_persisted_rich_method_cards()


def _method_card_visible(card: MethodCard | RichMethodCard, *, include_drafts: bool) -> bool:
    if card.status in RETIRED_METHOD_CARD_STATUSES:
        return False
    return include_drafts or card.status == "approved"


def _get_persisted_method_card_any_status(
    artifact_root: str | Path,
    method_card_id: str,
    *,
    knowledge_store: KnowledgeStore,
) -> MethodCard | None:
    for card in _list_persisted_method_cards(artifact_root, knowledge_store=knowledge_store):
        if card.method_card_id == method_card_id:
            return card
    return None


def _get_persisted_rich_method_card_any_status(
    artifact_root: str | Path,
    method_card_id: str,
    *,
    knowledge_store: KnowledgeStore,
) -> RichMethodCard | None:
    for card in _list_persisted_rich_method_cards(artifact_root, knowledge_store=knowledge_store):
        if card.method_card_id == method_card_id:
            return card
    return None


def _retired_method_card(
    card: MethodCard,
    *,
    status: str,
    updated_by: str,
    note: str,
    superseded_by_method_card_id: str | None,
) -> MethodCard:
    entry = _lifecycle_entry(
        previous_status=card.status,
        status=status,
        updated_by=updated_by,
        note=note,
        superseded_by_method_card_id=superseded_by_method_card_id,
    )
    return replace(
        card,
        status=status,
        approval_note=_append_lifecycle_note(card.approval_note, entry),
    )


def _retired_rich_method_card(
    card: RichMethodCard,
    *,
    status: str,
    updated_by: str,
    note: str,
    superseded_by_method_card_id: str | None,
) -> RichMethodCard:
    entry = _lifecycle_entry(
        previous_status=card.status,
        status=status,
        updated_by=updated_by,
        note=note,
        superseded_by_method_card_id=superseded_by_method_card_id,
    )
    lineage = dict(card.lineage)
    existing_updates = lineage.get("lifecycle_updates")
    updates = (
        list(existing_updates)
        if isinstance(existing_updates, Sequence) and not isinstance(existing_updates, (str, bytes))
        else []
    )
    updates.append(entry)
    lineage["lifecycle_updates"] = updates
    if superseded_by_method_card_id:
        lineage["superseded_by_method_card_id"] = superseded_by_method_card_id
    return replace(
        card,
        status=status,
        approval_note=_append_lifecycle_note(card.approval_note, entry),
        lineage=lineage,
    )


def _lifecycle_entry(
    *,
    previous_status: str,
    status: str,
    updated_by: str,
    note: str,
    superseded_by_method_card_id: str | None,
) -> dict[str, Any]:
    entry = {
        "previous_status": previous_status,
        "status": status,
        "updated_by": updated_by.strip(),
        "note": note.strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if superseded_by_method_card_id:
        entry["superseded_by_method_card_id"] = superseded_by_method_card_id
    return entry


def _append_lifecycle_note(existing_note: str | None, entry: Mapping[str, Any]) -> str:
    lifecycle_note = (
        f"Lifecycle {entry['previous_status']} -> {entry['status']} by {entry['updated_by']}: {entry['note']}"
    )
    if entry.get("superseded_by_method_card_id"):
        lifecycle_note = f"{lifecycle_note}; superseded_by={entry['superseded_by_method_card_id']}"
    if existing_note and existing_note.strip():
        return f"{existing_note.strip()}\n{lifecycle_note}"
    return lifecycle_note


def _clean_tuple(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(str(value).strip() for value in values if str(value).strip())


def _lifecycle_error(message: str) -> ToolEnvelope:
    return error_envelope(
        command=KNOWLEDGE_UPDATE_METHOD_CARD_STATUS,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="method_card_lifecycle_error",
        message=message,
    )


def _publish_error(message: str) -> ToolEnvelope:
    return error_envelope(
        command=KNOWLEDGE_PUBLISH_METHOD_CARD,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="method_card_publish_error",
        message=message,
    )


def _rich_draft_error(message: str) -> ToolEnvelope:
    return error_envelope(
        command=KNOWLEDGE_CREATE_RICH_METHOD_CARD_DRAFT,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="rich_method_card_draft_error",
        message=message,
    )


def _comparable_card_payload(card: MethodCard | RichMethodCard) -> Mapping[str, Any]:
    payload = card.to_dict()
    payload.pop("created_at", None)
    return payload
