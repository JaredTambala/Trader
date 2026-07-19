"""Method-card aggregate and revision-set maintenance."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from trader_research.foundation import (
    stable_research_id,
)

from .domain import (
    EvidenceReference,
    MethodCard,
    MethodCardSet,
    default_method_card_set_id,
)
from .store import KnowledgeStore

from .method_card_catalog import _cards_for_set, _method_card_set_by_id

def _resolve_method_card_set_id(
    *,
    method_card_set_id: str | None,
    method_id: str,
    title: str,
    family: str,
    source_fingerprint: str | None,
) -> str:
    explicit = str(method_card_set_id or "").strip()
    if explicit:
        return explicit
    return default_method_card_set_id(
        method_id=method_id,
        title=title,
        family=family,
        source_fingerprint=source_fingerprint,
    )


def _source_fingerprint_from_refs(store: KnowledgeStore, refs: Sequence[EvidenceReference]) -> str | None:
    source_ids = sorted({str(ref.source_id) for ref in refs if ref.source_id})
    if not source_ids:
        return None
    source_rows = []
    for source_id in source_ids:
        source = store.load_source(source_id)
        if source is None:
            continue
        source_rows.append(
            {
                "source_id": source.source_id,
                "file_hash": source.file_hash,
                "title": source.title,
                "source_type": source.source_type,
            }
        )
    if not source_rows:
        return None
    return stable_research_id("source_fingerprint", {"sources": source_rows})


def _source_fingerprint_from_sources(sources: Mapping[str, Any]) -> str | None:
    source_rows = [
        {
            "source_id": source_id,
            "file_hash": source.file_hash,
            "title": source.title,
            "source_type": source.source_type,
        }
        for source_id, source in sorted(sources.items())
    ]
    if not source_rows:
        return None
    return stable_research_id("source_fingerprint", {"sources": source_rows})


def _required_method_card_set_id(card: MethodCard) -> str:
    method_card_set_id = str(card.method_card_set_id or "").strip()
    if not method_card_set_id:
        raise ValueError(f"method_card_set_id is required for method card {card.method_card_id}")
    return method_card_set_id


def _sync_method_card_set(
    store: KnowledgeStore,
    card: MethodCard,
    *,
    source_fingerprint: str | None = None,
) -> MethodCardSet:
    method_card_set = _build_method_card_set(
        store,
        _required_method_card_set_id(card),
        base_card=card,
        source_fingerprint=source_fingerprint,
    )
    store.save_method_card_set(method_card_set)
    return method_card_set


def _build_method_card_set(
    store: KnowledgeStore,
    method_card_set_id: str,
    *,
    base_card: MethodCard | None = None,
    source_fingerprint: str | None = None,
) -> MethodCardSet:
    if not method_card_set_id.strip():
        raise ValueError("method_card_set_id is required")
    cards = list(_cards_for_set(store, method_card_set_id))
    if base_card is not None and base_card.method_card_id not in {card.method_card_id for card in cards}:
        cards.append(base_card)
    if not cards:
        if base_card is None:
            raise ValueError(f"cannot build empty method-card set: {method_card_set_id}")
        cards = [base_card]
    cards.sort(key=lambda card: (int(card.revision_number or 0), card.created_at.isoformat(), card.method_card_id))
    existing = _method_card_set_by_id(store, method_card_set_id)
    first = cards[0]
    status_counts = Counter(card.status for card in cards)
    active_approved = [card for card in cards if card.status == "approved"]
    published_draft_ids = {card.source_method_card_id for card in cards if card.source_method_card_id}
    active_drafts = [
        card
        for card in cards
        if card.status == "draft" and card.method_card_id not in published_draft_ids
    ]
    current_approved = _latest_revision(active_approved)
    current_draft = _latest_revision(active_drafts)
    if len(active_approved) > 1:
        set_status = "needs_review"
    elif current_approved is not None or current_draft is not None:
        set_status = "active"
    else:
        set_status = "retired"
    existing_fingerprint = existing.source_fingerprint if existing is not None else None
    created_at = existing.created_at if existing is not None else min(card.created_at for card in cards)
    now = datetime.now(timezone.utc)
    return MethodCardSet(
        method_card_set_id=method_card_set_id,
        method_id=first.method_id,
        family=first.family,
        canonical_title=existing.canonical_title if existing is not None else first.title,
        status=set_status,
        source_fingerprint=source_fingerprint or existing_fingerprint,
        current_approved_method_card_id=current_approved.method_card_id if current_approved else None,
        current_draft_method_card_id=current_draft.method_card_id if current_draft else None,
        card_ids=tuple(card.method_card_id for card in cards),
        revision_count=len(cards),
        latest_revision_number=max(int(card.revision_number or 0) for card in cards),
        status_counts=dict(sorted(status_counts.items())),
        lineage={
            **(dict(existing.lineage) if existing is not None else {}),
            "updated_by": "method_card_set_sync",
            "updated_at": now.isoformat(),
        },
        created_at=created_at,
        updated_at=now,
    )


def _latest_revision(cards: Sequence[MethodCard]) -> MethodCard | None:
    if not cards:
        return None
    return max(cards, key=lambda card: (int(card.revision_number or 0), card.created_at.isoformat(), card.method_card_id))


def _current_approved_method_card_id(
    store: KnowledgeStore,
    method_card_set_id: str,
    *,
    excluding_method_card_id: str,
) -> str | None:
    approved = [
        card
        for card in _cards_for_set(store, method_card_set_id)
        if card.status == "approved" and card.method_card_id != excluding_method_card_id
    ]
    current = _latest_revision(approved)
    return current.method_card_id if current is not None else None
