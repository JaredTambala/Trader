"""Document ingestion service for the Quant Methods knowledge base."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from trader_research.contracts import SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.domain import stable_research_id

from .chunking import chunk_sections
from .domain import KnowledgeChunk, KnowledgeIngestionReport
from .embeddings import EmbeddingConfigurationError, EmbeddingProvider, EmbeddingRequestError
from .extractors import extract_text
from .index import build_embedding_index
from .store import JsonKnowledgeStore, KnowledgeStore, KnowledgeStoreError


KNOWLEDGE_INGEST_DOCUMENTS = "knowledge_ingest_documents"
KNOWLEDGE_GET_INGESTION_STATUS = "knowledge_get_ingestion_status"


def ingest_documents(
    *,
    artifact_root: str | Path,
    source_ids: Sequence[str],
    embedding_provider: EmbeddingProvider,
    force: bool = False,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Ingest registered sources into citeable chunks and searchable embeddings.

    The command validates batch size, loads each source manifest, reuses existing
    chunks unless `force` is true, extracts text, creates deterministic chunks, and
    indexes all resulting embeddings through the configured store. Extraction,
    chunking, storage, and embedding failures are converted into tool envelopes
    with a saved ingestion report whenever possible so callers can inspect partial
    progress and blockers.
    """
    if not source_ids:
        return error_envelope(
            command=KNOWLEDGE_INGEST_DOCUMENTS,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="validation_error",
            message="at least one source_id is required",
        )
    if len(source_ids) > 25:
        return error_envelope(
            command=KNOWLEDGE_INGEST_DOCUMENTS,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="validation_error",
            message="at most 25 source_ids may be ingested in one call",
        )
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    warnings: list[str] = []
    blockers: list[str] = []
    all_chunks = []
    replacement_chunks: dict[str, tuple[KnowledgeChunk, ...]] = {}
    ingested_source_ids: list[str] = []
    try:
        for source_id in source_ids:
            source = store.load_source(str(source_id))
            if source is None:
                blockers.append(f"unknown source_id: {source_id}")
                continue
            if not force:
                existing_chunks = store.load_chunks(source.source_id)
                if existing_chunks:
                    all_chunks.extend(existing_chunks)
                    ingested_source_ids.append(source.source_id)
                    warnings.append(f"source {source.source_id} already indexed; reused existing chunks")
                    continue
            extracted = extract_text(source.path)
            warnings.extend(extracted.warnings)
            chunks = chunk_sections(source, extracted.sections)
            if not chunks:
                blockers.append(f"source {source.source_id} produced no chunks")
                continue
            replacement_chunks[source.source_id] = chunks
            all_chunks.extend(chunks)
            ingested_source_ids.append(source.source_id)
    except (OSError, ValueError, KnowledgeStoreError) as exc:
        return error_envelope(
            command=KNOWLEDGE_INGEST_DOCUMENTS,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="ingestion_error",
            message=str(exc),
        )
    try:
        if all_chunks:
            embedding_manifest, embeddings = build_embedding_index(all_chunks, provider=embedding_provider)
        else:
            embedding_manifest, embeddings = None, tuple()
    except (EmbeddingConfigurationError, EmbeddingRequestError, ValueError, KnowledgeStoreError) as exc:
        report = KnowledgeIngestionReport(
            ingestion_id=stable_research_id(
                "knowledge_ingestion",
                {
                    "source_ids": list(source_ids),
                    "chunk_ids": [chunk.chunk_id for chunk in all_chunks],
                    "force": force,
                    "embedding_error": str(exc),
                },
            ),
            source_ids=tuple(ingested_source_ids),
            status="blocked",
            chunks_created=len(all_chunks),
            chunks_indexed=0,
            warnings=tuple(warnings),
            blockers=(str(exc),),
        )
        try:
            store.save_ingestion_report(report)
        except KnowledgeStoreError:
            pass
        return error_envelope(
            command=KNOWLEDGE_INGEST_DOCUMENTS,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="embedding_configuration_error"
            if isinstance(exc, EmbeddingConfigurationError)
            else "embedding_index_error",
            message=str(exc),
            data={"knowledge_ingestion_report": report.to_dict()},
        )
    report = KnowledgeIngestionReport(
        ingestion_id=stable_research_id(
            "knowledge_ingestion",
            {
                "source_ids": list(source_ids),
                "chunk_ids": [chunk.chunk_id for chunk in all_chunks],
                "force": force,
            },
        ),
        source_ids=tuple(ingested_source_ids),
        status="blocked" if blockers else "indexed",
        chunks_created=len(all_chunks),
        chunks_indexed=len(all_chunks),
        embedding_manifest_id=embedding_manifest.embedding_manifest_id if embedding_manifest else None,
        warnings=tuple(warnings),
        blockers=tuple(blockers),
    )
    try:
        if embedding_manifest is not None:
            store.publish_ingestion(
                replacement_chunks,
                embedding_manifest,
                all_chunks,
                embeddings,
                report,
            )
        else:
            store.save_ingestion_report(report)
    except KnowledgeStoreError as exc:
        return error_envelope(
            command=KNOWLEDGE_INGEST_DOCUMENTS,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="ingestion_report_error",
            message=str(exc),
            data={"knowledge_ingestion_report": report.to_dict()},
        )
    artifacts = {
        "knowledge_ingestion_report": store.artifact_reference("knowledge_ingestion_report", report.ingestion_id)
    }
    if embedding_manifest is not None:
        artifacts["knowledge_embedding_manifest"] = store.artifact_reference(
            "knowledge_embedding_manifest",
            embedding_manifest.embedding_manifest_id,
        )
    if blockers:
        return error_envelope(
            command=KNOWLEDGE_INGEST_DOCUMENTS,
            side_effect=SideEffect.LOCAL_MUTATING,
            code="ingestion_blocked",
            message="one or more sources could not be ingested",
            data={"knowledge_ingestion_report": report.to_dict()},
        )
    return success_envelope(
        command=KNOWLEDGE_INGEST_DOCUMENTS,
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"knowledge_ingestion_report": report.to_dict()},
        artifacts=artifacts,
        warnings=tuple(warnings),
    )


def get_ingestion_status(
    *,
    artifact_root: str | Path,
    source_ids: Sequence[str] | None = None,
    run_id: str | None = None,
    knowledge_store: KnowledgeStore | None = None,
) -> ToolEnvelope:
    """Summarize registered-source and ingestion-report state without mutation.

    The status response lists matching sources with chunk counts and indexed flags,
    then appends persisted ingestion reports filtered by source IDs or run ID. Store
    failures become read-only error envelopes so monitoring tools can distinguish
    repository problems from an empty knowledge base.
    """
    store = knowledge_store or JsonKnowledgeStore(artifact_root)
    source_filter = {str(source_id) for source_id in source_ids or ()}
    sources = []
    try:
        for source in store.list_sources():
            if source_filter and source.source_id not in source_filter:
                continue
            chunks = store.load_chunks(source.source_id)
            sources.append(
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "status": source.status,
                    "source_type": source.source_type,
                    "chunk_count": len(chunks),
                    "indexed": bool(chunks),
                    "warnings": list(source.warnings),
                }
            )
    except KnowledgeStoreError as exc:
        return error_envelope(
            command=KNOWLEDGE_GET_INGESTION_STATUS,
            side_effect=SideEffect.READ_ONLY,
            code="knowledge_store_error",
            message=str(exc),
        )
    reports = []
    try:
        reports = [
            report.to_dict()
            for report in store.list_ingestion_reports(source_ids=source_ids, run_id=run_id)
        ]
    except KnowledgeStoreError as exc:
        return error_envelope(
            command=KNOWLEDGE_GET_INGESTION_STATUS,
            side_effect=SideEffect.READ_ONLY,
            code="knowledge_store_error",
            message=str(exc),
        )
    return success_envelope(
        command=KNOWLEDGE_GET_INGESTION_STATUS,
        side_effect=SideEffect.READ_ONLY,
        data={
            "sources": sources,
            "ingestion_reports": reports,
            "source_count": len(sources),
            "ingestion_report_count": len(reports),
        },
    )
