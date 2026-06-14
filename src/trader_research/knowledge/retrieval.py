"""Knowledge retrieval services for Quantitative Methods tools."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import stable_research_id

from .domain import EvidenceRetrievalReport
from .embeddings import EmbeddingConfigurationError, EmbeddingProvider, EmbeddingRequestError
from .index import search_chunks
from .method_cards import search_method_cards
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_SEARCH_METHODS = "knowledge_search_methods"
KNOWLEDGE_RETRIEVE_EVIDENCE = "knowledge_retrieve_evidence"


def search_methods(
    *,
    artifact_root: str | Path,
    query: str = "",
    family: str | None = None,
    include_drafts: bool = False,
    limit: int = 10,
) -> ToolEnvelope:
    """Search approved method cards and return method metadata."""
    if limit < 1 or limit > 50:
        return error_envelope(
            command=KNOWLEDGE_SEARCH_METHODS,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message="limit must be between 1 and 50",
        )
    cards = search_method_cards(
        artifact_root,
        query,
        family=family,
        include_drafts=include_drafts,
        limit=limit,
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
