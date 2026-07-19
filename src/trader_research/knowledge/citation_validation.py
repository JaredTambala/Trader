"""Citation validation for knowledge-backed method artifacts."""

from __future__ import annotations

from trader_research.foundation import ApplicationResult, error_result, stable_research_id, success_result

from pathlib import Path
from typing import Any, Mapping, Sequence

from .approved_cards import get_stored_method_card
from .domain import CitationValidationReport, EvidenceReference
from .evidence_validation import inspect_source_evidence_refs
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_VALIDATE_CITATIONS = "knowledge_validate_citations"


def validate_citations(
    *,
    artifact_root: str | Path,
    artifact: Mapping[str, Any],
    require_approved_method_card: bool = True,
    knowledge_store: KnowledgeStore | None = None,
) -> ApplicationResult:
    """Check that an artifact's knowledge citations resolve to approved evidence.

    The validator accepts either `knowledge_evidence_refs` or legacy
    `evidence_refs`, resolves method cards, sources, and chunks through the
    supplied knowledge store, and compares locator fields against the stored chunk
    locator when provided. Missing or mismatched evidence becomes a structured
    blocker in an error result; empty references and other non-fatal issues are
    returned as warnings without mutating storage.
    """
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    refs = _evidence_refs(artifact)
    try:
        source_checked, source_warnings, source_blockers = inspect_source_evidence_refs(
            refs,
            knowledge_store=store,
        )
    except KnowledgeStoreError as exc:
        return _store_error(str(exc))
    blockers = list(source_blockers)
    warnings = list(source_warnings)
    checked: list[Mapping[str, Any]] = []
    for ref, checked_source_ref in zip(refs, source_checked, strict=True):
        checked_ref = dict(checked_source_ref)
        if ref.method_card_id is not None:
            try:
                card = get_stored_method_card(store, ref.method_card_id)
            except KnowledgeStoreError as exc:
                return _store_error(str(exc))
            if card is None:
                blockers.append(f"unknown method_card_id: {ref.method_card_id}")
            elif require_approved_method_card and not card.approved:
                blockers.append(f"method_card_id is not approved: {ref.method_card_id}")
            checked_ref["method_card_status"] = card.status if card is not None else None
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
        return error_result(
            command=KNOWLEDGE_VALIDATE_CITATIONS,
            code="citation_validation_failed",
            message="citation validation failed",
            data=data,
        )
    return success_result(
        command=KNOWLEDGE_VALIDATE_CITATIONS,
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


def _store_error(message: str) -> ApplicationResult:
    return error_result(
        command=KNOWLEDGE_VALIDATE_CITATIONS,
        code="knowledge_store_error",
        message=message,
    )
