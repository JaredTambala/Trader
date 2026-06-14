"""Citation validation for knowledge-backed method artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import stable_research_id

from .domain import CitationValidationReport, EvidenceReference
from .method_cards import get_method_card
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_VALIDATE_CITATIONS = "knowledge_validate_citations"


def validate_citations(
    *,
    artifact_root: str | Path,
    artifact: Mapping[str, Any],
    require_approved_method_card: bool = True,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Validate source, chunk, locator, and method-card references."""
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    refs = _evidence_refs(artifact)
    blockers: list[str] = []
    warnings: list[str] = []
    checked: list[Mapping[str, Any]] = []
    if not refs:
        blockers.append("artifact has no knowledge_evidence_refs")
    for ref in refs:
        checked_ref: dict[str, Any] = ref.to_dict()
        if ref.method_card_id is not None:
            card = get_method_card(artifact_root, ref.method_card_id, include_drafts=True)
            if card is None:
                blockers.append(f"unknown method_card_id: {ref.method_card_id}")
            elif require_approved_method_card and not card.approved:
                blockers.append(f"method_card_id is not approved: {ref.method_card_id}")
            checked_ref["method_card_status"] = card.status if card is not None else None
        if ref.source_id is not None:
            try:
                source = store.load_source(ref.source_id)
            except KnowledgeStoreError as exc:
                return _store_error(str(exc))
            if source is None:
                blockers.append(f"unknown source_id: {ref.source_id}")
            checked_ref["source_known"] = source is not None
            checked_ref["source_status"] = source.status if source is not None else None
        if ref.chunk_id is not None:
            try:
                chunk = _find_chunk(store, ref.chunk_id)
            except KnowledgeStoreError as exc:
                return _store_error(str(exc))
            if chunk is None:
                blockers.append(f"unknown chunk_id: {ref.chunk_id}")
            else:
                if ref.source_id is not None and chunk.source_id != ref.source_id:
                    blockers.append(f"chunk {ref.chunk_id} does not belong to source {ref.source_id}")
                if ref.locator:
                    for key, value in ref.locator.items():
                        if chunk.locator.get(key) != value:
                            blockers.append(f"locator mismatch for chunk {ref.chunk_id}: {key}")
                            break
                checked_ref["chunk_known"] = True
                checked_ref["chunk_locator"] = dict(chunk.locator)
        if ref.source_id is None and ref.chunk_id is None and ref.method_card_id is None:
            warnings.append("empty evidence reference ignored")
        checked.append(checked_ref)
    report = CitationValidationReport(
        validation_id=stable_research_id(
            "citation_validation",
            {"artifact": artifact, "require_approved_method_card": require_approved_method_card},
        ),
        valid=not blockers,
        checked_refs=tuple(checked),
        warnings=tuple(warnings),
        blockers=tuple(blockers),
    )
    data = {"citation_validation_report": report.to_dict()}
    if blockers:
        return error_envelope(
            command=KNOWLEDGE_VALIDATE_CITATIONS,
            side_effect=SideEffect.READ_ONLY,
            code="citation_validation_failed",
            message="citation validation failed",
            data=data,
        )
    return success_envelope(
        command=KNOWLEDGE_VALIDATE_CITATIONS,
        side_effect=SideEffect.READ_ONLY,
        data=data,
        warnings=tuple(warnings),
    )


def _evidence_refs(artifact: Mapping[str, Any]) -> tuple[EvidenceReference, ...]:
    raw_refs = artifact.get("knowledge_evidence_refs") or artifact.get("evidence_refs") or ()
    if isinstance(raw_refs, Mapping):
        raw_refs = (raw_refs,)
    if isinstance(raw_refs, (str, bytes)) or not isinstance(raw_refs, Sequence):
        return tuple()
    return tuple(EvidenceReference.from_dict(ref) for ref in raw_refs if isinstance(ref, Mapping))


def _find_chunk(repository: KnowledgeStore, chunk_id: str):
    for chunk in repository.list_chunks():
        if chunk.chunk_id == chunk_id:
            return chunk
    return None


def _store_error(message: str) -> ToolEnvelope:
    return error_envelope(
        command=KNOWLEDGE_VALIDATE_CITATIONS,
        side_effect=SideEffect.READ_ONLY,
        code="knowledge_store_error",
        message=message,
    )
