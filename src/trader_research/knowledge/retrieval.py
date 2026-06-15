"""Knowledge retrieval services for Quantitative Methods tools."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import stable_research_id

from .domain import EvidenceChunkDereferenceReport, EvidenceRetrievalReport, KnowledgeChunk, KnowledgeSourceManifest
from .embeddings import EmbeddingConfigurationError, EmbeddingProvider, EmbeddingRequestError
from .index import search_chunks
from .method_cards import search_method_cards
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_SEARCH_METHODS = "knowledge_search_methods"
KNOWLEDGE_RETRIEVE_EVIDENCE = "knowledge_retrieve_evidence"
KNOWLEDGE_GET_EVIDENCE_CHUNKS = "knowledge_get_evidence_chunks"
MAX_DEREFERENCE_CHUNKS = 25
MAX_CHARS_PER_CHUNK_LIMIT = 20_000


def search_methods(
    *,
    artifact_root: str | Path,
    query: str = "",
    family: str | None = None,
    include_drafts: bool = False,
    limit: int = 10,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Search approved method cards and return method metadata."""
    if limit < 1 or limit > 50:
        return error_envelope(
            command=KNOWLEDGE_SEARCH_METHODS,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message="limit must be between 1 and 50",
        )
    try:
        cards = search_method_cards(
            artifact_root,
            query,
            family=family,
            include_drafts=include_drafts,
            limit=limit,
            knowledge_store=knowledge_store,
        )
    except KnowledgeStoreError as exc:
        return error_envelope(
            command=KNOWLEDGE_SEARCH_METHODS,
            side_effect=SideEffect.READ_ONLY,
            code="knowledge_store_error",
            message=str(exc),
        )
    return success_envelope(
        command=KNOWLEDGE_SEARCH_METHODS,
        side_effect=SideEffect.READ_ONLY,
        data={
            "methods": [card.to_dict() for card in cards],
            "method_count": len(cards),
        },
    )


def retrieve_evidence(
    *,
    artifact_root: str | Path,
    query: str,
    method_id: str | None = None,
    source_ids: Sequence[str] | None = None,
    embedding_provider: EmbeddingProvider,
    top_k: int = 5,
    approved_only: bool = True,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Retrieve citeable chunks for a method or query."""
    if not query.strip():
        return error_envelope(
            command=KNOWLEDGE_RETRIEVE_EVIDENCE,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message="query is required",
        )
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    try:
        results = search_chunks(
            store,
            query,
            source_ids=source_ids,
            top_k=top_k,
            provider=embedding_provider,
            approved_only=approved_only,
        )
    except (EmbeddingConfigurationError, EmbeddingRequestError, ValueError, KnowledgeStoreError) as exc:
        return error_envelope(
            command=KNOWLEDGE_RETRIEVE_EVIDENCE,
            side_effect=SideEffect.READ_ONLY,
            code="embedding_configuration_error"
            if isinstance(exc, EmbeddingConfigurationError)
            else "knowledge_store_error"
            if isinstance(exc, KnowledgeStoreError)
            else "evidence_retrieval_error",
            message=str(exc),
        )
    report = EvidenceRetrievalReport(
        retrieval_id=stable_research_id(
            "evidence_retrieval",
            {
                "query": query,
                "method_id": method_id,
                "source_ids": list(source_ids or ()),
                "top_k": top_k,
                "approved_only": approved_only,
                "chunk_ids": [result.get("chunk_id") for result in results],
            },
        ),
        query=query,
        filters={
            "method_id": method_id,
            "source_ids": list(source_ids or ()),
            "top_k": top_k,
            "approved_only": approved_only,
        },
        results=tuple(results),
    )
    return success_envelope(
        command=KNOWLEDGE_RETRIEVE_EVIDENCE,
        side_effect=SideEffect.READ_ONLY,
        data={"evidence_retrieval_report": report.to_dict()},
        warnings=tuple() if results else ("no indexed chunks matched the query",),
    )


def get_evidence_chunks(
    *,
    artifact_root: str | Path,
    chunk_ids: Sequence[str],
    source_id: str | None = None,
    include_text: bool = True,
    max_chars_per_chunk: int = 4000,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Dereference citeable chunk IDs into bounded stored text payloads."""
    requested_chunk_ids = tuple(dict.fromkeys(str(chunk_id).strip() for chunk_id in chunk_ids if str(chunk_id).strip()))
    if not requested_chunk_ids:
        return error_envelope(
            command=KNOWLEDGE_GET_EVIDENCE_CHUNKS,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message="chunk_ids is required",
        )
    if len(requested_chunk_ids) > MAX_DEREFERENCE_CHUNKS:
        return error_envelope(
            command=KNOWLEDGE_GET_EVIDENCE_CHUNKS,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=f"chunk_ids must contain at most {MAX_DEREFERENCE_CHUNKS} entries",
            data={"requested_chunk_count": len(requested_chunk_ids), "max_chunk_count": MAX_DEREFERENCE_CHUNKS},
        )
    if max_chars_per_chunk < 1 or max_chars_per_chunk > MAX_CHARS_PER_CHUNK_LIMIT:
        return error_envelope(
            command=KNOWLEDGE_GET_EVIDENCE_CHUNKS,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=f"max_chars_per_chunk must be between 1 and {MAX_CHARS_PER_CHUNK_LIMIT}",
            data={"max_chars_per_chunk": max_chars_per_chunk},
        )

    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    try:
        chunks = store.load_chunks_by_ids(requested_chunk_ids)
        sources_by_id = _load_sources_for_chunks(store, chunks)
    except KnowledgeStoreError as exc:
        return error_envelope(
            command=KNOWLEDGE_GET_EVIDENCE_CHUNKS,
            side_effect=SideEffect.READ_ONLY,
            code="knowledge_store_error",
            message=str(exc),
        )

    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    missing_chunk_ids = tuple(chunk_id for chunk_id in requested_chunk_ids if chunk_id not in chunks_by_id)
    source_mismatch_chunk_ids = tuple(
        chunk.chunk_id for chunk in chunks if source_id is not None and chunk.source_id != source_id
    )
    if missing_chunk_ids or source_mismatch_chunk_ids:
        return error_envelope(
            command=KNOWLEDGE_GET_EVIDENCE_CHUNKS,
            side_effect=SideEffect.READ_ONLY,
            code="chunk_dereference_error",
            message="one or more evidence chunks could not be resolved",
            data={
                "requested_chunk_ids": list(requested_chunk_ids),
                "missing_chunk_ids": list(missing_chunk_ids),
                "source_mismatch_chunk_ids": list(source_mismatch_chunk_ids),
                "filters": {"source_id": source_id},
            },
        )

    resolved = tuple(
        _chunk_payload(
            chunks_by_id[chunk_id],
            source=sources_by_id.get(chunks_by_id[chunk_id].source_id),
            include_text=include_text,
            max_chars_per_chunk=max_chars_per_chunk,
        )
        for chunk_id in requested_chunk_ids
    )
    warnings = tuple(
        f"source metadata not found for chunk {chunk['chunk_id']}"
        for chunk in resolved
        if chunk["source_title"] is None
    )
    report = EvidenceChunkDereferenceReport(
        dereference_id=stable_research_id(
            "evidence_chunk_dereference",
            {
                "chunk_ids": list(requested_chunk_ids),
                "source_id": source_id,
                "include_text": include_text,
                "max_chars_per_chunk": max_chars_per_chunk,
            },
        ),
        requested_chunk_ids=requested_chunk_ids,
        filters={
            "source_id": source_id,
            "include_text": include_text,
            "max_chars_per_chunk": max_chars_per_chunk,
        },
        chunks=resolved,
        warnings=warnings,
    )
    payload = report.to_dict()
    return success_envelope(
        command=KNOWLEDGE_GET_EVIDENCE_CHUNKS,
        side_effect=SideEffect.READ_ONLY,
        data={
            "evidence_chunk_dereference_report": payload,
            "chunks": payload["chunks"],
            "chunk_count": payload["chunk_count"],
            "missing_chunk_ids": payload["missing_chunk_ids"],
        },
        warnings=warnings,
    )


def _load_sources_for_chunks(
    store: KnowledgeStore,
    chunks: Sequence[KnowledgeChunk],
) -> dict[str, KnowledgeSourceManifest]:
    sources: dict[str, KnowledgeSourceManifest] = {}
    for source_id in sorted({chunk.source_id for chunk in chunks}):
        source = store.load_source(source_id)
        if source is not None:
            sources[source_id] = source
    return sources


def _chunk_payload(
    chunk: KnowledgeChunk,
    *,
    source: KnowledgeSourceManifest | None,
    include_text: bool,
    max_chars_per_chunk: int,
) -> Mapping[str, Any]:
    text = chunk.text[:max_chars_per_chunk] if include_text else None
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "source_title": source.title if source is not None else None,
        "source_type": source.source_type if source is not None else None,
        "source_status": source.status if source is not None else None,
        "approved_source": source.status == "approved" if source is not None else False,
        "locator": dict(chunk.locator),
        "topics": list(chunk.topics),
        "method_families": list(chunk.method_families),
        "text_hash": chunk.text_hash,
        "hash_verified": hashlib.sha256(chunk.text.encode("utf-8")).hexdigest() == chunk.text_hash,
        "text_char_count": len(chunk.text),
        "text_word_count": len(chunk.text.split()),
        "text_truncated": include_text and len(chunk.text) > max_chars_per_chunk,
        "text": text,
    }
