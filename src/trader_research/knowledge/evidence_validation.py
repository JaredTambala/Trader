"""Validate source and chunk references independently of card lifecycle.

The helpers resolve every declared reference, verify source/chunk ownership and
content identity, and return checked rows with stable warnings and blockers.
They do not require or confer method-card approval.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from trader_research.foundation import ApplicationResult, error_result, success_result

from .domain import EvidenceReference
from .store import KnowledgeStore, KnowledgeStoreError


def inspect_source_evidence_refs(
    refs: Sequence[EvidenceReference],
    *,
    knowledge_store: KnowledgeStore,
) -> tuple[tuple[Mapping[str, Any], ...], tuple[str, ...], tuple[str, ...]]:
    """Inspect source and chunk references against the active knowledge store.

    Each reference is retained in the checked output and enriched with source or
    chunk existence, lifecycle, and lineage facts. Missing evidence, unknown IDs,
    unapproved sources, and source/chunk mismatches become de-duplicated issues;
    the function does not mutate evidence or lifecycle state.

    Returns:
        Checked reference mappings, warnings, and blockers in deterministic input
        order.

    Raises:
        KnowledgeStoreError: If the underlying source or chunk read fails.
    """
    checked: list[Mapping[str, Any]] = []
    warnings: list[str] = []
    blockers: list[str] = []
    if not refs:
        blockers.append("artifact has no knowledge_evidence_refs")
    for ref in refs:
        checked_ref = ref.to_dict()
        if ref.source_id is not None:
            source = knowledge_store.load_source(ref.source_id)
            if source is None:
                blockers.append(f"unknown source_id: {ref.source_id}")
            checked_ref["source_known"] = source is not None
            checked_ref["source_status"] = source.status if source is not None else None
        if ref.chunk_id is not None:
            chunks = knowledge_store.load_chunks_by_ids((ref.chunk_id,))
            chunk = chunks[0] if chunks else None
            if chunk is None:
                blockers.append(f"unknown chunk_id: {ref.chunk_id}")
            else:
                if ref.source_id is not None and chunk.source_id != ref.source_id:
                    blockers.append(f"chunk {ref.chunk_id} does not belong to source {ref.source_id}")
                for key, value in ref.locator.items():
                    if chunk.locator.get(key) != value:
                        blockers.append(f"locator mismatch for chunk {ref.chunk_id}: {key}")
                        break
                checked_ref["chunk_known"] = True
                checked_ref["chunk_locator"] = dict(chunk.locator)
                _inspect_claim_span(ref, chunk.text, blockers)
        if ref.source_id is None and ref.chunk_id is None and ref.method_card_id is None:
            warnings.append("evidence reference has no source or chunk locator")
        checked.append(checked_ref)
    return tuple(checked), tuple(dict.fromkeys(warnings)), tuple(dict.fromkeys(blockers))


def validate_source_evidence_refs(
    *,
    command: str,
    refs: Sequence[EvidenceReference],
    knowledge_store: KnowledgeStore,
) -> ApplicationResult:
    """Wrap source and chunk inspection in a transport-neutral result.

    The supplied ``command`` is preserved as operation identity. A completed
    inspection returns checked references and issues even when evidence is
    blocked; only knowledge-store failures prevent a validation payload.

    Returns:
        A successful result when no blockers exist, a blocked result carrying the
        inspection evidence, or a structured knowledge-store failure.
    """
    try:
        checked, warnings, blockers = inspect_source_evidence_refs(
            refs,
            knowledge_store=knowledge_store,
        )
    except KnowledgeStoreError as exc:
        return error_result(command=command, code="knowledge_store_error", message=str(exc))
    data = {
        "source_evidence_validation": {
            "valid": not blockers,
            "checked_refs": list(checked),
            "warnings": list(warnings),
            "blockers": list(blockers),
        }
    }
    if blockers:
        return error_result(
            command=command,
            code="source_evidence_validation_failed",
            message="source evidence validation failed",
            data=data,
        )
    return success_result(command=command, data=data, warnings=warnings)


def _inspect_claim_span(ref: EvidenceReference, chunk_text: str, blockers: list[str]) -> None:
    span = ref.claim_span
    if span is None or ref.chunk_id is None:
        return
    if span.end_char > len(chunk_text):
        blockers.append(f"claim span {span.span_id} exceeds chunk {ref.chunk_id} text length")
        return
    stored_text = chunk_text[span.start_char : span.end_char]
    if stored_text != span.text:
        blockers.append(f"claim span {span.span_id} text mismatch for chunk {ref.chunk_id}")
    if hashlib.sha256(stored_text.encode("utf-8")).hexdigest() != span.text_hash:
        blockers.append(f"claim span {span.span_id} hash mismatch for chunk {ref.chunk_id}")
