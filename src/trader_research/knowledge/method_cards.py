"""Canonical method-card publication and lifecycle facade."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.foundation import (
    ApplicationResult,
    error_result,
    success_result,
)

from .domain import (
    MethodCard,
)
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError

from .method_card_catalog import (
    RETIRED_METHOD_CARD_STATUSES,
    _get_persisted_method_card_any_status,
    get_method_card,
    get_method_card_set as get_method_card_set,
    list_method_card_sets as list_method_card_sets,
    list_method_cards as list_method_cards,
    method_cards_for_method as method_cards_for_method,
    search_method_cards as search_method_cards,
)
from .method_card_drafting import (
    _collect_method_card_evidence_refs,
    _validate_source_evidence_refs,
    create_method_card_draft as create_method_card_draft,
)
from .method_card_sets import (
    _current_approved_method_card_id,
    _required_method_card_set_id,
    _sync_method_card_set,
)

KNOWLEDGE_PUBLISH_METHOD_CARD = "knowledge_publish_method_card"


KNOWLEDGE_UPDATE_METHOD_CARD_STATUS = "knowledge_update_method_card_status"


WRITABLE_RETIRED_METHOD_CARD_STATUSES = RETIRED_METHOD_CARD_STATUSES


def publish_method_card(
    *,
    artifact_root: str | Path,
    draft_method_card_id: str,
    approved_method_card_id: str,
    approved_by: str,
    approval_note: str,
    approve: bool,
    knowledge_store: KnowledgeStore | None = None,
) -> ApplicationResult:
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
        draft = get_method_card(
            artifact_root,
            draft_method_card_id,
            include_drafts=True,
            knowledge_store=store,
        )
        if draft is None:
            return _publish_error(f"unknown draft_method_card_id: {draft_method_card_id}")
        return _publish_method_card(
            artifact_root=artifact_root,
            store=store,
            draft=draft,
            approved_method_card_id=approved_method_card_id,
            approved_by=approved_by,
            approval_note=approval_note,
        )
    except KnowledgeStoreError as exc:
        return error_result(
            command=KNOWLEDGE_PUBLISH_METHOD_CARD,
            code="method_card_publish_error",
            message=str(exc),
        )
    raise AssertionError("unreachable")


def update_method_card_status(
    *,
    artifact_root: str | Path,
    method_card_id: str,
    status: str,
    updated_by: str,
    note: str,
    superseded_by_method_card_id: str | None = None,
    knowledge_store: KnowledgeStore | None = None,
) -> ApplicationResult:
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
        _sync_method_card_set(store, updated_card)
    except KnowledgeStoreError as exc:
        return error_result(
            command=KNOWLEDGE_UPDATE_METHOD_CARD_STATUS,
            code="method_card_lifecycle_error",
            message=str(exc),
        )
    return success_result(
        command=KNOWLEDGE_UPDATE_METHOD_CARD_STATUS,
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


def _publish_method_card(
    *,
    artifact_root: str | Path,
    store: KnowledgeStore,
    draft: MethodCard,
    approved_method_card_id: str,
    approved_by: str,
    approval_note: str,
) -> ApplicationResult:
    if draft.status != "draft":
        return _publish_error(f"method card is not a draft: {draft.method_card_id}")
    refs = _collect_method_card_evidence_refs(draft)
    citation_result = _validate_source_evidence_refs(
        artifact_root=artifact_root,
        refs=refs,
        knowledge_store=store,
    )
    if not citation_result.ok:
        return error_result(
            command=KNOWLEDGE_PUBLISH_METHOD_CARD,
            code="method_card_publish_validation_failed",
            message="method-card publish evidence validation failed",
            data=citation_result.data,
        )
    supersedes_method_card_id = _current_approved_method_card_id(
        store,
        _required_method_card_set_id(draft),
        excluding_method_card_id=approved_method_card_id.strip(),
    )
    approved = replace(
        draft,
        method_card_id=approved_method_card_id.strip(),
        status="approved",
        source_method_card_id=draft.method_card_id,
        approved_by=approved_by.strip(),
        approval_note=approval_note.strip(),
        supersedes_method_card_id=supersedes_method_card_id,
        lineage={
            **dict(draft.lineage),
            "approval": {
                "approved_by": approved_by.strip(),
                "approval_note": approval_note.strip(),
                "source_method_card_id": draft.method_card_id,
            },
        },
    )
    existing = get_method_card(
        artifact_root,
        approved.method_card_id,
        include_drafts=True,
        knowledge_store=store,
    )
    if existing is not None:
        approved = replace(approved, supersedes_method_card_id=existing.supersedes_method_card_id)
        if _comparable_card_payload(existing) != _comparable_card_payload(approved):
            return _publish_error(f"approved method card already exists with different content: {approved.method_card_id}")
        _sync_method_card_set(store, existing)
        return success_result(
            command=KNOWLEDGE_PUBLISH_METHOD_CARD,
            data={"method_card": existing.to_dict(), "idempotent": True},
            artifacts={
                "method_card": store.artifact_reference("method_card", approved.method_card_id),
            },
            warnings=("approved method card already exists with identical content",),
        )
    _supersede_prior_approved_revision(
        store,
        method_card_set_id=_required_method_card_set_id(approved),
        superseded_by_method_card_id=approved.method_card_id,
    )
    store.save_method_card(approved)
    _sync_method_card_set(store, approved)
    return success_result(
        command=KNOWLEDGE_PUBLISH_METHOD_CARD,
        data={"method_card": approved.to_dict(), "idempotent": False},
        artifacts={
            "method_card": store.artifact_reference("method_card", approved.method_card_id),
        },
    )


def _supersede_prior_approved_revision(
    store: KnowledgeStore,
    *,
    method_card_set_id: str,
    superseded_by_method_card_id: str,
) -> None:
    prior_id = _current_approved_method_card_id(
        store,
        method_card_set_id,
        excluding_method_card_id=superseded_by_method_card_id,
    )
    if prior_id is None:
        return
    prior = _get_persisted_method_card_any_status(
        ".",
        prior_id,
        knowledge_store=store,
    )
    if prior is not None:
        store.save_method_card(
            _retired_method_card(
                prior,
                status="superseded",
                updated_by="knowledge_publish_method_card",
                note="Superseded by a newer approved revision in the same method-card set.",
                superseded_by_method_card_id=superseded_by_method_card_id,
            )
        )


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


def _lifecycle_error(message: str) -> ApplicationResult:
    return error_result(
        command=KNOWLEDGE_UPDATE_METHOD_CARD_STATUS,
        code="method_card_lifecycle_error",
        message=message,
    )


def _publish_error(message: str) -> ApplicationResult:
    return error_result(
        command=KNOWLEDGE_PUBLISH_METHOD_CARD,
        code="method_card_publish_error",
        message=message,
    )


def _comparable_card_payload(card: MethodCard) -> Mapping[str, Any]:
    payload = card.to_dict()
    payload.pop("created_at", None)
    return payload
