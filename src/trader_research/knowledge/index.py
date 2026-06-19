"""Knowledge indexing and hybrid retrieval helpers."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from trader_research.domain import stable_research_id

from .domain import KnowledgeChunk, KnowledgeEmbeddingManifest
from .embeddings import EmbeddingProvider
from .store import KnowledgeStore, StoredEmbedding


def index_chunks(
    store: KnowledgeStore,
    chunks: Sequence[KnowledgeChunk],
    *,
    provider: EmbeddingProvider,
) -> KnowledgeEmbeddingManifest:
    """Embed chunks, validate vector dimensions, and persist index metadata.

    Each chunk is embedded with the supplied provider, wrapped as a stored vector,
    and written together with a manifest that records provider/model/version and
    the indexed chunk IDs. Mixed vector dimensions are rejected before persistence
    because vector search cannot safely compare embeddings from inconsistent
    output shapes.
    """
    embeddings: list[StoredEmbedding] = []
    dimensions: set[int] = set()
    for chunk in chunks:
        embedding = provider.embed(chunk.text)
        dimensions.add(len(embedding))
        embeddings.append(StoredEmbedding(chunk_id=chunk.chunk_id, vector=embedding))
    if len(dimensions) > 1:
        raise ValueError("embedding provider returned inconsistent vector dimensions")
    dimension = next(iter(dimensions), 0)
    manifest = KnowledgeEmbeddingManifest(
        embedding_manifest_id=stable_research_id(
            "knowledge_embedding_manifest",
            {
                "provider": provider.provider,
                "model": provider.model,
                "version": provider.version,
                "chunk_ids": sorted(chunk.chunk_id for chunk in chunks),
            },
        ),
        provider=provider.provider,
        model=provider.model,
        version=provider.version,
        dimension=dimension,
        chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
    )
    store.index_embeddings(manifest, chunks, embeddings)
    return manifest


def search_chunks(
    store: KnowledgeStore,
    query: str,
    *,
    source_ids: Sequence[str] | None = None,
    topic: str | None = None,
    method_family: str | None = None,
    top_k: int = 5,
    provider: EmbeddingProvider,
    approved_only: bool = True,
) -> tuple[Mapping[str, Any], ...]:
    """Retrieve chunks by combining lexical search with provider-backed vector search.

    The query is embedded once, both search modes request an expanded candidate
    set, and the results are merged with reciprocal-rank fusion. Validation keeps
    `top_k` bounded so tool calls remain predictable even when a store has many
    indexed chunks.
    """
    if top_k < 1 or top_k > 25:
        raise ValueError("top_k must be between 1 and 25")
    query_embedding = provider.embed(query)
    candidate_k = max(top_k * 5, 50)
    lexical_results = store.search_lexical(
        query,
        source_ids=source_ids,
        topic=topic,
        method_family=method_family,
        approved_only=approved_only,
        limit=candidate_k,
    )
    vector_results = store.search_vector(
        query_embedding,
        provider=provider.provider,
        model=provider.model,
        version=provider.version,
        source_ids=source_ids,
        topic=topic,
        method_family=method_family,
        approved_only=approved_only,
        limit=candidate_k,
    )
    return reciprocal_rank_fusion(lexical_results, vector_results, top_k=top_k)


def reciprocal_rank_fusion(
    lexical_results: Sequence[Mapping[str, Any]],
    vector_results: Sequence[Mapping[str, Any]],
    *,
    top_k: int,
    rank_constant: int = 60,
) -> tuple[Mapping[str, Any], ...]:
    """Merge lexical and vector result lists into a stable ranked result set.

    Results are keyed by `chunk_id`, each modality contributes reciprocal-rank
    score when present, and ties are broken by chunk ID after sorting by fused
    score. The returned rows retain the original payload fields and gain a
    `retrieval_scores` block so callers can explain how lexical and vector ranks
    affected the final order.
    """
    by_chunk_id: dict[str, dict[str, Any]] = {}
    lexical_rank_by_chunk: dict[str, int] = {}
    vector_rank_by_chunk: dict[str, int] = {}
    lexical_score_by_chunk: dict[str, float] = {}
    vector_score_by_chunk: dict[str, float] = {}

    for rank, result in enumerate(lexical_results, start=1):
        chunk_id = str(result.get("chunk_id") or "")
        if not chunk_id:
            continue
        by_chunk_id.setdefault(chunk_id, dict(result))
        lexical_rank_by_chunk[chunk_id] = rank
        lexical_score_by_chunk[chunk_id] = float(result.get("score") or 0.0)

    for rank, result in enumerate(vector_results, start=1):
        chunk_id = str(result.get("chunk_id") or "")
        if not chunk_id:
            continue
        by_chunk_id.setdefault(chunk_id, dict(result))
        vector_rank_by_chunk[chunk_id] = rank
        vector_score_by_chunk[chunk_id] = float(result.get("score") or 0.0)

    fused: list[dict[str, Any]] = []
    for chunk_id, result in by_chunk_id.items():
        lexical_rank = lexical_rank_by_chunk.get(chunk_id)
        vector_rank = vector_rank_by_chunk.get(chunk_id)
        fusion_score = 0.0
        if lexical_rank is not None:
            fusion_score += 1.0 / (rank_constant + lexical_rank)
        if vector_rank is not None:
            fusion_score += 1.0 / (rank_constant + vector_rank)
        enriched = dict(result)
        enriched["score"] = fusion_score
        enriched["retrieval_scores"] = {
            "lexical_rank": lexical_rank,
            "vector_rank": vector_rank,
            "combined_rank": None,
            "lexical_score": lexical_score_by_chunk.get(chunk_id),
            "vector_score": vector_score_by_chunk.get(chunk_id),
            "fusion_score": fusion_score,
        }
        fused.append(enriched)

    fused.sort(key=lambda result: (-float(result["score"]), str(result.get("chunk_id") or "")))
    for combined_rank, result in enumerate(fused, start=1):
        scores = dict(result["retrieval_scores"])
        scores["combined_rank"] = combined_rank
        result["retrieval_scores"] = scores
    return tuple(fused[:top_k])
