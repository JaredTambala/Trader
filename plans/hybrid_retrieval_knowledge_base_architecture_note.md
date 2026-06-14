# Architecture Note: Quant Methods Knowledge Base and Hybrid Retrieval

## 1. Purpose

This note defines the architecture for a **Quant Methods Knowledge Base** that supports the Math Coder / Deterministic Quant Methods Agent.

The goal is to let the system ingest approved statistical, econometric, trading, and numerical-method documents, then expose citeable retrieval tools to agent workflows. The Math Coder should use this knowledge base to create and validate method contracts, statistical-test definitions, indicator implementations, multiple-testing reports, and Python/C++ parity artifacts.

The key principle is:

> The vector store is retrieval infrastructure, not the source of truth. The authority is the approved source registry plus approved method cards.

The knowledge base should prevent the Math Coder from relying only on latent LLM knowledge when implementing statistical methods or making claims about assumptions, tests, or methodology.

## 2. Architectural Context

The trading research platform separates concerns as follows:

```text
trader
  Core trading platform, event store, broker/runtime interfaces, backtesting primitives.

trader_standard
  Maintained reusable implementations: indicators, signal generators, simple strategy/risk components.

trader_research
  Research artifacts, tool contracts, knowledge base, method cards, diagnostics, evaluation and experiment logic.

trader_mcp
  MCP server and deterministic tool adapters.

trader_agents
  LangGraph identities, state schemas, tool allowlists, control-policy nodes, and supervisor wiring.
```

The Quant Methods Knowledge Base belongs under `trader_research`, with MCP exposure through `trader_mcp`. Agents should access it only through approved MCP tools or service interfaces, not through direct ad hoc vector-store queries.

## 3. Design Goals

The knowledge base should:

1. Allow an operator to provide a document or set of documents for ingestion.
2. Register each document as an approved or pending source with metadata and file hashes.
3. Extract text with stable locators such as page number, section heading, and chunk ID.
4. Chunk documents into retrieval units while preserving source provenance.
5. Embed chunks into a versioned vector index.
6. Build a lexical index for exact keyword retrieval.
7. Support hybrid retrieval over both vector and lexical indexes.
8. Return citeable evidence chunks, not opaque context blobs.
9. Support method-card creation and validation from approved sources.
10. Allow Math Coder tools to require source-backed method contracts.
11. Make ingestion, retrieval, embedding, citation validation, and method approval auditable.

## 4. Non-Goals

The knowledge base should not:

- Approve a method merely because a retrieved chunk mentions it.
- Let the LLM invent uncited statistical methodology.
- Expose raw SQL or arbitrary vector-store queries through MCP.
- Store hidden LLM reasoning or raw scratchpads as product records.
- Republish large copyrighted document excerpts into artifacts.
- Allow knowledge retrieval tools to fetch market data, place orders, run backtests, or mutate broker state.
- Replace Evaluation or Adversarial review.

## 5. Core Concept: Hybrid Retrieval

Hybrid retrieval combines two retrieval modes:

```text
lexical / keyword retrieval
  + dense vector retrieval
  + optional reranking
  = hybrid retrieval
```

### 5.1 Lexical Retrieval

Lexical retrieval finds exact or near-exact terms. It is important for technical methods where exact labels matter:

```text
Newey-West
HAC
ADF
KPSS
White Reality Check
Hansen SPA
Benjamini-Hochberg
Deflated Sharpe Ratio
stationary bootstrap
```

A simple implementation can use PostgreSQL full-text search, BM25, OpenSearch, Tantivy, or another keyword index.

### 5.2 Dense Vector Retrieval

Vector retrieval embeds queries and document chunks into a numerical vector space and retrieves semantically similar chunks.

This helps with conceptual queries such as:

```text
How should I adjust for testing many trading rules?
How do I handle autocorrelation in strategy returns?
How do I estimate uncertainty when returns are dependent?
```

A vector search may find relevant chunks about data snooping, multiple testing, bootstrap inference, HAC covariance estimators, or backtest overfitting even if the query does not use the exact method name.

### 5.3 Why Hybrid Retrieval Is Required

Pure keyword retrieval can miss conceptually relevant passages when the exact wording differs. Pure vector retrieval can miss exact method names, acronyms, theorem labels, or author-specific terminology.

The Quant Methods Knowledge Base should use both.

## 6. Retrieval Flow

The intended retrieval flow is:

```text
query
  -> lexical search top K
  -> vector search top K
  -> merge and deduplicate
  -> rerank top N, if reranker is available
  -> apply source/method filters
  -> return citeable evidence chunks
```

The merge step may use reciprocal rank fusion or another deterministic rank-combination method.

The retrieval result should include both scores and provenance:

```json
{
  "chunk_id": "chunk_...",
  "source_id": "white_2000_reality_check",
  "source_title": "A Reality Check for Data Snooping",
  "locator": {
    "page": 3,
    "section": "Introduction"
  },
  "retrieval_scores": {
    "lexical_rank": 2,
    "vector_rank": 5,
    "combined_rank": 1,
    "vector_score": 0.81
  },
  "approved_source": true,
  "text_excerpt": "short excerpt or summary only"
}
```

## 7. Source Registration and Ingestion Pipeline

The ingestion pipeline should be deterministic and artifact-producing.

```text
operator provides document(s)
  -> register source manifest
  -> extract text and locators
  -> chunk document
  -> create chunk manifest
  -> embed chunks
  -> update vector index
  -> update lexical index
  -> produce ingestion report
```

### 7.1 Source Registration

Every source should receive a stable `source_id` and metadata record before it is indexed.

Example `source_manifest.json`:

```json
{
  "source_id": "lo_2002_statistics_of_sharpe_ratios",
  "title": "The Statistics of Sharpe Ratios",
  "authors": ["Andrew W. Lo"],
  "year": 2002,
  "source_type": "primary_paper",
  "domain_tags": ["sharpe_ratio", "serial_correlation", "performance_metrics"],
  "license_or_access": "local_private_reference",
  "canonical_citation": "...",
  "original_filename": "lo_2002_statistics_of_sharpe_ratios.pdf",
  "file_hash_sha256": "...",
  "approval_status": "pending",
  "registered_at": "..."
}
```

Recommended `source_type` values:

```text
foundation_textbook
method_textbook
primary_paper
software_documentation
internal_note
```

Recommended `approval_status` values:

```text
pending
approved
rejected
superseded
```

### 7.2 Text Extraction

The extraction layer should preserve locators. For PDFs, this means at minimum page numbers. Where possible, section headings should also be detected.

Example extracted text unit:

```json
{
  "source_id": "...",
  "page": 42,
  "section": "Bootstrap confidence intervals",
  "text": "...",
  "extractor": "pdf_text_extractor_v1",
  "extractor_warnings": []
}
```

Extraction should produce warnings for:

- empty pages,
- scanned pages requiring OCR,
- broken text order,
- missing page labels,
- tables/equations that could not be represented reliably,
- duplicate or corrupted pages.

OCR should be treated as a later enhancement and should be explicitly marked in the extraction metadata.

### 7.3 Chunking

Chunking should split extracted text into semantically useful retrieval units. Each chunk must preserve source provenance.

Example `source_chunk.json`:

```json
{
  "chunk_id": "chunk_...",
  "source_id": "...",
  "chunk_index": 17,
  "page_start": 41,
  "page_end": 42,
  "section_path": ["Chapter 4", "Bootstrap confidence intervals"],
  "text": "...",
  "token_count": 512,
  "chunker_version": "quant_kb_chunker_v1",
  "content_hash_sha256": "..."
}
```

Chunking should avoid mixing unrelated sections. Overlap is allowed, but it must be deterministic and versioned.

### 7.4 Embedding

Every embedding must record the model, provider, dimension, distance metric, chunker version, and source hash.

Example `embedding_manifest.json`:

```json
{
  "knowledge_index_id": "quant_methods_kb_v1_bge_m3_1024_cosine",
  "embedding_provider": "local_sentence_transformers",
  "embedding_model": "BAAI/bge-m3",
  "embedding_dimension": 1024,
  "distance_metric": "cosine",
  "chunker_version": "quant_kb_chunker_v1",
  "source_collection_id": "quant_methods_sources_v1",
  "created_at": "..."
}
```

Embedding indexes should be immutable. If the embedding model, chunker, source collection, or dimension changes, create a new index version.

## 8. Method Cards

A method card is the stable source-backed representation of a statistical, econometric, numerical, or signal-diagnostic method.

Retrieved chunks can support a method card, but they do not become authoritative by themselves.

Example `method_card.json`:

```json
{
  "method_id": "white_reality_check",
  "name": "White Reality Check",
  "family": "multiple_testing",
  "aliases": ["Reality Check", "data-snooping bootstrap test"],
  "purpose": "Adjust performance inference when many candidate rules are tested on the same dataset.",
  "inputs": ["candidate_return_matrix", "benchmark_return_series", "bootstrap_config"],
  "outputs": ["test_statistic", "p_value", "warnings"],
  "assumptions": [
    "candidate family is declared",
    "dependent time-series structure is handled through an appropriate bootstrap"
  ],
  "failure_modes": [
    "undeclared search space",
    "too few effective observations",
    "unstable bootstrap block length"
  ],
  "primary_sources": [
    {
      "source_id": "white_2000_reality_check",
      "locator": {
        "page": 2,
        "section": "Introduction"
      }
    }
  ],
  "approval_status": "approved",
  "approved_by": "maintainer",
  "approved_at": "..."
}
```

The Math Coder should prefer approved method cards over raw retrieval results.

## 9. Citation Validation

Citation validation should check whether a proposed method contract or report cites approved sources correctly.

The validator should ensure:

1. Every cited `source_id` exists.
2. The source is approved for use.
3. The locator exists within the extracted source manifest.
4. The cited chunk supports the claimed method or assumption.
5. High-risk methods cite either a `primary_paper` or `method_textbook`, not only broad foundation material.
6. Generated artifacts do not include excessive direct quotes.

Citation validation should produce a `citation_validation_report.json`.

## 10. MCP Tool Surface

Knowledge-base tools should be deterministic MCP tools.

### 10.1 Source and Ingestion Tools

| Tool | Side effect | Purpose |
| --- | --- | --- |
| `knowledge_register_source` | `local_mutating` | Register source metadata and file hash. |
| `knowledge_extract_source` | `local_mutating` | Extract text and locators from a registered source. |
| `knowledge_chunk_source` | `local_mutating` | Create deterministic chunks and chunk manifest. |
| `knowledge_embed_source` | `local_mutating` | Embed chunks into a versioned vector index. |
| `knowledge_index_source` | `local_mutating` | Update lexical and vector indexes for a registered source. |
| `knowledge_ingest_documents` | `local_mutating` | Convenience orchestrator for register -> extract -> chunk -> embed -> index. |

### 10.2 Retrieval and Validation Tools

| Tool | Side effect | Purpose |
| --- | --- | --- |
| `knowledge_list_sources` | `read_only` | List registered sources and approval status. |
| `knowledge_search_methods` | `read_only` | Search approved method cards. |
| `knowledge_retrieve_evidence` | `read_only` | Run hybrid retrieval and return citeable chunks. |
| `knowledge_get_evidence_chunks` | `read_only` | Dereference retrieved chunk IDs into bounded stored text for local downstream agent context. |
| `knowledge_validate_citations` | `read_only` | Validate source IDs, locators, and source approval. |
| `knowledge_create_method_card` | `local_mutating` | Create a draft method card from approved sources and retrieved evidence. |
| `knowledge_approve_method_card` | `local_mutating` | Maintainer-only approval of a method card. |

### 10.3 Math Coder Integration Tools

| Tool | Side effect | Purpose |
| --- | --- | --- |
| `math_create_method_contract` | `local_mutating` | Create a method contract from an approved method card. |
| `math_validate_method_contract` | `read_only` | Validate inputs, outputs, assumptions, and citation coverage. |
| `math_run_method_fixtures` | `local_mutating` | Run deterministic fixture tests for implemented methods. |
| `math_run_signal_diagnostics` | `local_mutating` | Run signal diagnostics using source-backed method contracts. |
| `math_run_multiple_testing_report` | `local_mutating` | Run multiple-testing/data-snooping controls from approved method contracts. |

## 11. Agent Access Pattern

The Math Coder Agent may use knowledge tools, but only through an allowlist.

Allowed pattern:

```text
Math Coder policy node
  -> search method cards
  -> retrieve evidence if needed
  -> validate citations
  -> create/validate method contract
  -> call deterministic implementation/test tools
  -> produce method artifact handoff
```

Disallowed pattern:

```text
Math Coder LLM
  -> retrieves arbitrary chunks
  -> invents method assumptions
  -> emits uncited code or statistical claims
```

The LLM may propose typed actions only. A deterministic router must validate:

- tool allowlist,
- source approval status,
- method-card availability,
- citation validity,
- side-effect policy,
- loop budget,
- artifact ownership.

## 12. Package Placement

Recommended package shape:

```text
src/trader_research/knowledge/
  __init__.py
  sources.py              # source manifests and approval status
  extraction.py           # text extraction and locator preservation
  chunking.py             # deterministic chunking
  embeddings.py           # embedding provider abstraction
  indexes.py              # lexical/vector index adapters
  retrieval.py            # hybrid retrieval and rank fusion
  method_cards.py         # method-card schema and lifecycle
  citation_validation.py  # citation checks and reports
  ingestion.py            # ingestion orchestration

src/trader_research/math_tools.py
  # method contracts, deterministic fixtures, diagnostics, multiple-testing reports

src/trader_mcp/knowledge_tools.py
  # MCP registrations/adapters for knowledge tools

src/trader_agents/math_coder_policy.py
  # typed Math Coder control decisions using knowledge tools
```

The `trader` core package must not import knowledge-base, MCP, or agent modules.

## 13. Storage Recommendation

Because the platform is already Postgres-backed, the first implementation can use:

```text
PostgreSQL tables for source/chunk/method metadata
PostgreSQL full-text search for lexical retrieval
pgvector for dense vector retrieval
filesystem/object storage for source files and extracted artifacts
```

This keeps metadata, source approval, chunk locators, and embedding indexes close to the rest of the research state.

However, the storage layer should be abstracted so that the retrieval implementation can later move to OpenSearch, Qdrant, LanceDB, or another index if required.

Implementation note for the first durable chunk:

- MCP runtime uses `TRADER_RESEARCH_KNOWLEDGE_STORE=postgres` and the existing trader Postgres config path.
- `KnowledgeStore` is the service boundary; Postgres is the production implementation and the JSON store remains a test/migration compatibility adapter.
- Postgres stores source, chunk, embedding-index, embedding-vector, and ingestion-run records in `knowledge_*` tables.
- PostgreSQL full-text search provides lexical retrieval; pgvector provides dense retrieval.
- `knowledge_retrieve_evidence` merges lexical and vector candidates with deterministic reciprocal-rank fusion.
- `knowledge_get_evidence_chunks` dereferences selected `chunk_id` values into real stored chunk text with locators,
  source metadata, hash verification, and truncation flags.
- Method-card draft/publish tools, reranking, OCR, external vector databases, and Quantitative Methods LangGraph handoff remain later chunks.

## 14. Embedding Provider Abstraction

The system should support interchangeable embedding providers.

Example interface:

```text
EmbeddingProvider
  - provider_name
  - model_name
  - model_revision
  - embedding_dimension
  - max_input_tokens
  - supports_instruction
  - supports_local_execution
  - embed_documents(chunks)
  - embed_queries(queries)
```

Every embedding index should record the provider and model version. Re-embedding should produce a new index version rather than silently overwriting existing embeddings.

## 15. Guardrails

1. Approved sources and approved method cards are the authority.
2. Retrieved evidence is advisory until linked to a method card or citation validation report.
3. Unsupported or uncited methods fail closed.
4. Knowledge tools do not fetch market data or run trading experiments.
5. Method contracts should cite method-specific sources, not only broad textbooks.
6. High-risk inference methods should require primary-paper or method-textbook support.
7. Generated reports should paraphrase and cite; they should not reproduce long source passages.
8. All ingestion and retrieval outputs should be artifacted and reproducible.
9. The Math Coder should produce evidence, not trading verdicts.
10. Evaluation and Adversarial agents remain responsible for critique and stress testing.

## 16. Revised Backlog Slice

Add the following chunks before the expanded Math Coder implementation work.

### 23A. Knowledge Source Schemas

Implement source manifests, extraction manifests, chunk manifests, embedding manifests, retrieval reports, citation-validation reports, and method-card schemas.

Acceptance criteria:

- Schemas serialize to JSON-safe dictionaries.
- Source IDs and file hashes are stable.
- Chunk locators preserve source/page/section metadata.
- Method cards can reference source IDs and locators.

### 23B. Source Registration Service

Implement source registration for local documents.

Acceptance criteria:

- Operator can register a PDF, Markdown, or text document.
- The system records source metadata, file hash, source type, approval status, and canonical citation.
- Duplicate files are detected by hash.

### 23C. Text Extraction and Chunking

Implement deterministic extraction and chunking.

Acceptance criteria:

- Markdown and text ingestion work first.
- PDF text extraction works for text-based PDFs.
- Extracted chunks include page/section locators where available.
- Extraction warnings are preserved.

### 23D. Embedding Provider and Index Versioning

Implement local embedding provider abstraction and index manifests.

Acceptance criteria:

- Fake embedding provider works for tests.
- One real local embedding provider can be configured.
- Embedding model, dimension, provider, and chunker version are recorded.
- New model/chunker versions create new index IDs.

### 23E. Lexical and Vector Retrieval

Implement lexical search, vector search, and rank fusion.

Acceptance criteria:

- Keyword queries retrieve exact method names.
- Semantic queries retrieve conceptually relevant chunks.
- Hybrid retrieval returns deduplicated ranked chunks with source metadata.

### 23F. Knowledge MCP Tools

Register knowledge ingestion and retrieval tools through MCP.

Acceptance criteria:

- MCP exposes source registration, ingestion, source listing, method search, evidence retrieval, chunk dereferencing, and citation validation.
- Tools return shared envelopes with side-effect class and artifact references.
- Tools do not expose raw SQL or arbitrary vector queries.

### 23G. Method Card Lifecycle

Implement draft and approval flow for method cards.

Acceptance criteria:

- Draft method cards can be created from approved sources and retrieved evidence.
- Method cards remain pending until approved.
- Math Coder method contracts can require approved method cards.

### 23H. Math Coder Knowledge Integration

Integrate approved method cards and citation validation into Math Coder method-contract creation.

Acceptance criteria:

- Unsupported or uncited method contracts fail closed.
- Method contracts include source-backed assumptions, inputs, outputs, and failure modes.
- Supervisor handoffs include method-card and citation-validation references.

## 17. First End-to-End Evidence Target

The first end-to-end evidence loop should be deliberately small:

```text
register one Markdown source
  -> extract and chunk it
  -> embed/index it
  -> retrieve evidence for a known method query
  -> create a draft method card
  -> approve the method card
  -> create a Math Coder method contract from it
  -> validate citations
  -> return a Math Coder handoff artifact
```

This should be tested with a small checked-in fixture document before ingesting large textbooks or papers.

## 18. Success Criteria

The knowledge-base architecture is successful when:

1. A new document can be registered, chunked, embedded, and retrieved through deterministic tools.
2. Retrieval results include citeable source IDs and locators.
3. The Math Coder can create method contracts only from approved method cards or approved source evidence.
4. Method contracts include explicit assumptions, inputs, outputs, failure modes, and citations.
5. The system can distinguish retrieval evidence from approved methodology.
6. The Supervisor can consume Math Coder handoffs without rewriting source-backed evidence.
7. Unsupported methodology fails closed rather than being improvised by the LLM.

## 19. Summary

The Quant Methods Knowledge Base provides a citeable retrieval and method-card layer for the Math Coder Agent.

It should ingest operator-provided documents, preserve source provenance, build both lexical and vector indexes, and expose hybrid retrieval through deterministic MCP tools. The Math Coder should use this retrieval layer to create source-backed method contracts, not to improvise statistical methods from arbitrary chunks.

The resulting architecture gives the trading research system a controlled bridge between statistical literature, deterministic code, and auditable agent artifacts.
