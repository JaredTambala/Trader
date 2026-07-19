"""Canonical method-card catalog queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trader_research.foundation import (
    ApplicationResult,
    error_result,
    success_result,
)

from .domain import (
    MethodCard,
    MethodCardSet,
    MethodCardSummary,
)
from .storage import KnowledgeRepository
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_LIST_METHOD_CARD_SETS = "knowledge_list_method_card_sets"


KNOWLEDGE_GET_METHOD_CARD_SET = "knowledge_get_method_card_set"


RETIRED_METHOD_CARD_STATUSES = frozenset({"rejected", "superseded"})


def list_method_cards(
    artifact_root: str | Path,
    *,
    include_drafts: bool = False,
    knowledge_store: KnowledgeStore | None = None,
) -> tuple[MethodCard, ...]:
    """Return canonical method cards in deterministic ID order."""
    cards = list(_list_persisted_method_cards(artifact_root, knowledge_store=knowledge_store))
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
    """Look up one canonical method card by ID."""
    for card in list_method_cards(artifact_root, include_drafts=include_drafts, knowledge_store=knowledge_store):
        if card.method_card_id == method_card_id:
            return card
    return None


def list_method_card_sets(
    artifact_root: str | Path,
    *,
    method_id: str | None = None,
    family: str | None = None,
    status: str | None = None,
    include_retired: bool = False,
    limit: int = 50,
    knowledge_store: KnowledgeStore | None = None,
) -> ApplicationResult:
    """Return stable method-card set summaries for operator inspection."""
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    try:
        sets = tuple(sorted(store.list_method_card_sets(), key=lambda item: item.method_card_set_id))
    except KnowledgeStoreError as exc:
        return _set_read_error(KNOWLEDGE_LIST_METHOD_CARD_SETS, str(exc))
    normalized_method_id = str(method_id or "").strip()
    normalized_family = str(family or "").strip()
    normalized_status = str(status or "").strip()
    filtered = []
    for method_card_set in sets:
        if normalized_method_id and method_card_set.method_id != normalized_method_id:
            continue
        if normalized_family and method_card_set.family != normalized_family:
            continue
        if normalized_status and method_card_set.status != normalized_status:
            continue
        if not include_retired and method_card_set.status == "retired":
            continue
        filtered.append(method_card_set)
    bounded = filtered[: max(1, min(int(limit), 100))]
    return success_result(
        command=KNOWLEDGE_LIST_METHOD_CARD_SETS,
        data={
            "method_card_sets": [item.to_dict() for item in bounded],
            "method_card_set_count": len(bounded),
            "total_matching_count": len(filtered),
        },
    )


def get_method_card_set(
    artifact_root: str | Path,
    *,
    method_card_set_id: str,
    include_cards: bool = True,
    knowledge_store: KnowledgeStore | None = None,
) -> ApplicationResult:
    """Return one stable method-card set with optional revision history."""
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    set_id = method_card_set_id.strip()
    if not set_id:
        return _set_read_error(KNOWLEDGE_GET_METHOD_CARD_SET, "method_card_set_id is required")
    try:
        method_card_set = _method_card_set_by_id(store, set_id)
        if method_card_set is None:
            return _set_read_error(KNOWLEDGE_GET_METHOD_CARD_SET, f"unknown method_card_set_id: {set_id}")
        revisions = [
            card.to_dict()
            for card in sorted(
                _cards_for_set(store, set_id),
                key=lambda card: (int(card.revision_number or 0), card.created_at.isoformat(), card.method_card_id),
            )
        ]
    except KnowledgeStoreError as exc:
        return _set_read_error(KNOWLEDGE_GET_METHOD_CARD_SET, str(exc))
    data: dict[str, Any] = {"method_card_set": method_card_set.to_dict()}
    if include_cards:
        data["revision_history"] = revisions
        data["revision_count"] = len(revisions)
    return success_result(
        command=KNOWLEDGE_GET_METHOD_CARD_SET,
        data=data,
    )


def method_cards_for_method(
    artifact_root: str | Path,
    method_id: str,
    *,
    include_drafts: bool = False,
    knowledge_store: KnowledgeStore | None = None,
) -> tuple[MethodCard, ...]:
    """Return all canonical cards for one method ID."""
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
) -> tuple[MethodCardSummary, ...]:
    """Search compact projections with deterministic matching over card text.

    The search corpus includes method ID, title, family, assumptions, and failure
    modes, then optionally narrows results by family and draft visibility. It is
    intentionally simple and deterministic. Returned values are derived summaries;
    only complete evidence-backed cards are persisted.
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
            cards.append(card.to_summary())
    return tuple(cards[:limit])


def _list_persisted_method_cards(
    artifact_root: str | Path,
    *,
    knowledge_store: KnowledgeStore | None,
) -> tuple[MethodCard, ...]:
    if knowledge_store is not None:
        return knowledge_store.list_persisted_method_cards()
    return KnowledgeRepository(artifact_root).list_persisted_method_cards()


def _method_card_visible(card: MethodCard, *, include_drafts: bool) -> bool:
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


def _method_card_set_by_id(store: KnowledgeStore, method_card_set_id: str) -> MethodCardSet | None:
    for method_card_set in store.list_method_card_sets():
        if method_card_set.method_card_set_id == method_card_set_id:
            return method_card_set
    return None


def _cards_for_set(store: KnowledgeStore, method_card_set_id: str) -> tuple[MethodCard, ...]:
    return tuple(
        card
        for card in store.list_persisted_method_cards()
        if card.method_card_set_id == method_card_set_id
    )


def _set_read_error(command: str, message: str) -> ApplicationResult:
    return error_result(
        command=command,
        code="method_card_set_error",
        message=message,
    )
