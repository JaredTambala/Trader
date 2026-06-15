"""Method-card metadata and lifecycle services for Quant Methods evidence."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import stable_research_id

from .domain import EvidenceReference, MethodCard
from .storage import KnowledgeRepository
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_CREATE_METHOD_CARD_DRAFT = "knowledge_create_method_card_draft"
KNOWLEDGE_PUBLISH_METHOD_CARD = "knowledge_publish_method_card"

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
    """Return seeded and persisted method cards."""
    cards = list(SEEDED_METHOD_CARDS)
    if knowledge_store is not None:
        cards.extend(knowledge_store.list_persisted_method_cards())
    else:
        repository = KnowledgeRepository(artifact_root)
        cards.extend(repository.list_persisted_method_cards())
    if not include_drafts:
        cards = [card for card in cards if card.status == "approved"]
    by_id = {card.method_card_id: card for card in cards}
    return tuple(by_id[key] for key in sorted(by_id))


def get_method_card(
    artifact_root: str | Path,
    method_card_id: str,
    *,
    include_drafts: bool = False,
    knowledge_store: KnowledgeStore | None = None,
) -> MethodCard | None:
    for card in list_method_cards(artifact_root, include_drafts=include_drafts, knowledge_store=knowledge_store):
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
    """Search method cards by simple deterministic text matching."""
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
    """Create a non-approved method-card draft from validated source evidence."""
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
    """Publish a draft method card as an approved immutable card."""
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


def _clean_tuple(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(str(value).strip() for value in values if str(value).strip())


def _publish_error(message: str) -> ToolEnvelope:
    return error_envelope(
        command=KNOWLEDGE_PUBLISH_METHOD_CARD,
        side_effect=SideEffect.LOCAL_MUTATING,
        code="method_card_publish_error",
        message=message,
    )


def _comparable_card_payload(card: MethodCard) -> Mapping[str, Any]:
    payload = card.to_dict()
    payload.pop("created_at", None)
    return payload
