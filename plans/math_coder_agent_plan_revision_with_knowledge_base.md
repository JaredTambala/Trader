# Quantitative Methods Agent Revision: Knowledge-Backed Deterministic Quant Methods Agent

> Updated to include a Quant Methods Knowledge Base ingestion, embedding, retrieval, method-card, and citation-validation process.

## Purpose

This document proposes a revision to the former Math Coder Agent plan. The existing plan correctly separates agents by
owned artifacts, but the planned scope is too narrow if it is limited to indicator listing and validation. The canonical
identity should be Quantitative Methods Agent: owner of deterministic quantitative methods, mathematical transforms,
statistical tests, signal diagnostics, multiple-testing controls, and optional compiled C++ kernels that can be called
from Python.

The revised agent remains meaningfully distinct from the ML Agent and Hypothesis Agent. Its boundary is not “all quantitative thinking.” Its boundary is deterministic, auditable mathematical machinery and inference artifacts.

Recommended identity:

```text
Quantitative Methods Agent
  legacy source name: Math Coder Agent
  conceptual role: Deterministic Quant Methods Agent
  tool namespace: math_* and knowledge_*
```

## Design Principle

The agent boundary should remain artifact-based:

```text
If the output is a formula, transform, statistical test, method contract,
or compiled deterministic kernel -> Quantitative Methods Agent.

If the output is a fitted model, prediction series, feature dataset,
model card, or drift report -> ML Agent.

If the output is a falsifiable market claim using available ingredients
-> Hypothesis Agent.

If the output is a critique/verdict on research quality -> Evaluation Agent.

If the output is a final research plan, comparison, or recommendation
-> Quant Research Supervisor Agent.
```

This preserves the existing architecture: MCP tools provide deterministic capabilities, LangGraph provides identity and orchestration, and the Quant Research Supervisor consumes specialist artifacts without forging or rewriting them.

## Revised Mission

Current mission:

> Turn research math into auditable deterministic indicators and statistical tests.

Recommended expanded mission:

> Turn research math into auditable deterministic methods, statistical inference procedures, and operational numerical kernels. The Quantitative Methods Agent owns indicator contracts, transform contracts, statistical-test contracts, signal diagnostics, multiple-testing reports, and Python/C++ parity reports. It does not fetch data, generate strategy hypotheses, train ML models, run broad research campaigns, or make promotion decisions.


## New Architectural Requirement: Quant Methods Knowledge Base

The expanded Quantitative Methods Agent should not rely only on latent LLM knowledge for statistical methodology, inference procedures, or implementation conventions. It should be backed by a curated, versioned, citeable Quant Methods Knowledge Base.

The knowledge base is not a separate autonomous agent in the first release. It is a shared research service under `trader_research` with MCP tools that the Quantitative Methods Agent can call. Later, the Evaluation Agent and Quant Research Supervisor may be given read-only access to the same evidence layer.

Core rule:

```text
Hybrid lexical/vector retrieval indexes are retrieval infrastructure, not the authority.
The authority is the approved source registry plus approved method cards.
```

The intended pattern is:

```text
source documents
  -> source manifests
  -> extracted text with locators
  -> chunks with page/section metadata
  -> embeddings and retrieval index
  -> draft method cards
  -> human/maintainer approval
  -> approved method cards
  -> source-backed method contracts
  -> deterministic implementations and reports
```

The Quantitative Methods Agent may retrieve passages and method cards, but it must not create production method contracts from unapproved or uncited material.

## Quant Methods Knowledge Base Build Process

The platform should support a bounded process where the operator provides one document or a set of documents, and the system ingests them into the Quant Methods Knowledge Base.

### Ingestion Inputs

A knowledge-ingestion request should accept:

```json
{
  "request_id": "kb_ingest_...",
  "source_files": [
    {
      "path": "local/path/or/artifact/ref.pdf",
      "source_type": "paper|textbook|documentation|notes|article|other",
      "title": "A Reality Check for Data Snooping",
      "authors": ["Halbert White"],
      "year": 2000,
      "publisher_or_venue": "optional",
      "canonical_citation": "optional but recommended",
      "license_or_access": "local_private_reference|open_access|project_notes|unknown",
      "topics": ["multiple_testing", "data_snooping", "bootstrap"],
      "intended_method_families": ["white_reality_check"]
    }
  ],
  "ingestion_policy": {
    "allow_ocr": false,
    "allow_quotes_in_artifacts": false,
    "require_human_method_card_approval": true,
    "fail_on_missing_metadata": true
  }
}
```

A source can be a PDF, Markdown file, text file, or project note. DOCX can be supported later if useful, but the first implementation should start with PDF, Markdown, and plain text.

### Ingestion Pipeline

The ingestion service should perform the following steps:

```text
1. Validate ingestion request
   - reject missing title/source_type/access policy
   - reject unsupported file type
   - reject missing file or unreadable path
   - reject source files outside allowed local/artifact directories

2. Compute file identity
   - file hash
   - file size
   - source_id
   - ingestion_run_id
   - parser version
   - extraction timestamp

3. Register source manifest
   - source metadata
   - canonical citation if supplied
   - access/license policy
   - topics and intended methods
   - original file reference
   - file hash

4. Extract text
   - preserve document order
   - preserve page numbers when available
   - preserve headings/sections when available
   - record extraction warnings
   - do not silently OCR unless policy permits

5. Chunk text
   - chunk by heading/page where possible
   - preserve source_id, page, section, heading, offsets
   - record chunk hash
   - avoid over-large chunks
   - avoid chunks with no locator metadata

6. Embed chunks
   - record embedding model name/version
   - record embedding dimension
   - record embedding timestamp
   - store chunk text and vector in the knowledge index
   - store metadata relationally for exact filtering

7. Produce ingestion report
   - documents ingested
   - chunks created
   - skipped pages/chunks
   - extraction warnings
   - duplicate-source warnings
   - embedding model/version
   - artifact paths

8. Draft method cards, if requested
   - use retrieval over the newly ingested source
   - produce draft method cards only
   - require approval before use in production method contracts

9. Publish approved method cards
   - approval can initially be a local maintainer flag
   - only approved cards are available to Quantitative Methods contract generation
```

### Knowledge Artifacts

The knowledge base should produce structured artifacts, not just rows in a vector database.

| Artifact | Purpose |
| --- | --- |
| `knowledge_source_manifest.json` | Registers a source document, metadata, hash, access policy, topics, and canonical citation. |
| `knowledge_ingestion_report.json` | Records ingestion run status, parser version, chunks created, warnings, and embedding model/version. |
| `knowledge_chunk_manifest.json` | Records chunk IDs, source IDs, locators, headings, hashes, and index status. |
| `knowledge_embedding_manifest.json` | Records embedding backend, model/version, vector dimension, created_at, and compatibility constraints. |
| `method_card_draft.json` | Draft structured summary of a method extracted or synthesized from source evidence. Not executable by default. |
| `method_card.json` | Approved method card with assumptions, inputs, outputs, failure modes, and source locators. |
| `evidence_retrieval_report.json` | Records retrieved evidence chunks for a specific request, query, method, and source set. |
| `evidence_chunk_dereference_report.json` | Records bounded real chunk text dereferenced from retrieved chunk IDs for local downstream agent context. |
| `citation_validation_report.json` | Validates that a method contract or report cites approved source IDs and valid locators. |

### Source Manifest Sketch

```json
{
  "artifact_type": "knowledge_source_manifest",
  "source_id": "white_2000_reality_check",
  "title": "A Reality Check for Data Snooping",
  "authors": ["Halbert White"],
  "year": 2000,
  "source_type": "paper",
  "canonical_citation": "White, H. (2000). A Reality Check for Data Snooping.",
  "license_or_access": "local_private_reference",
  "file_hash": "sha256:...",
  "file_ref": "artifacts/knowledge/sources/white_2000_reality_check.pdf",
  "topics": ["multiple_testing", "data_snooping", "bootstrap"],
  "intended_method_families": ["white_reality_check"],
  "ingestion_status": "registered|ingested|indexed|blocked",
  "warnings": [],
  "created_at": "iso8601_timestamp"
}
```

### Chunk Manifest Sketch

```json
{
  "artifact_type": "knowledge_chunk_manifest",
  "source_id": "white_2000_reality_check",
  "ingestion_run_id": "kb_ingest_...",
  "chunks": [
    {
      "chunk_id": "chunk_...",
      "chunk_hash": "sha256:...",
      "page_start": 3,
      "page_end": 4,
      "section_title": "Methodology",
      "heading_path": ["Reality Check", "Bootstrap procedure"],
      "char_start": 1204,
      "char_end": 2450,
      "embedding_status": "indexed",
      "embedding_model": "configured_embedding_model_name",
      "metadata": {
        "method_candidates": ["white_reality_check"],
        "topics": ["bootstrap", "data_snooping"]
      }
    }
  ]
}
```

### Method Card Sketch

```json
{
  "artifact_type": "method_card",
  "method_id": "white_reality_check",
  "status": "approved",
  "family": "multiple_testing",
  "purpose": "Adjust performance inference for data-snooping across a declared candidate rule family.",
  "aliases": ["reality_check", "data_snooping_reality_check"],
  "required_inputs": [
    "candidate_return_matrix",
    "benchmark_return_series",
    "candidate_family_manifest",
    "bootstrap_config"
  ],
  "outputs": ["test_statistic", "p_value", "warnings"],
  "assumptions": [
    "candidate family is declared before inference",
    "dependence is handled by an approved bootstrap or resampling configuration"
  ],
  "failure_modes": [
    "undeclared candidate family",
    "too few effective observations",
    "unstable bootstrap configuration",
    "unresolved data-quality warnings"
  ],
  "source_evidence": [
    {
      "source_id": "white_2000_reality_check",
      "locator": "section/page reference",
      "chunk_ids": ["chunk_..."],
      "claim_supported": "method purpose and data-snooping motivation"
    }
  ],
  "approval": {
    "approved_by": "maintainer_or_operator",
    "approved_at": "iso8601_timestamp",
    "approval_notes": "optional"
  }
}
```

## Knowledge Retrieval Workflow for Quantitative Methods

The Quantitative Methods Agent should use knowledge retrieval before creating or validating sophisticated method contracts.

```text
1. Quantitative Methods receives a bounded method request.
2. Quantitative Methods calls `knowledge_search_methods` to find approved method cards.
3. If no approved method card exists, Quantitative Methods blocks or requests source ingestion.
4. Quantitative Methods calls `knowledge_retrieve_evidence` for the selected method and assumptions.
5. Quantitative Methods calls `knowledge_get_evidence_chunks` for selected chunk IDs when downstream local reasoning
   needs real stored chunk text.
6. Quantitative Methods calls `knowledge_validate_citations` against the proposed method contract.
7. Quantitative Methods creates or validates the method contract from the approved method card.
8. Quantitative Methods calls deterministic implementation/fixture/diagnostic tools.
9. Quantitative Methods packages the method artifact with source and citation provenance.
```

Failure cases should be explicit:

```text
No approved source supports this method -> block.
Source exists but no approved method card -> block or produce draft only.
Retrieved passage is relevant but locator is invalid -> block.
Method card exists but assumptions do not match the request -> block.
Citation validation fails -> block.
```

## Knowledge MCP Tool Surface

The knowledge base should be exposed through MCP tools. The first release can assign ownership to the Quantitative Methods Agent because Quantitative Methods is the first consumer. The implementation should still live under `trader_research.knowledge` so that Evaluation and Supervisor can later use read-only access.

| Tool | Owner | Side effect | Purpose |
| --- | --- | --- | --- |
| `knowledge_register_source` | Quantitative Methods Agent | `local_mutating` | Register document metadata, compute file hash, and create `knowledge_source_manifest.json`. |
| `knowledge_ingest_documents` | Quantitative Methods Agent | `local_mutating` | Extract text, chunk, embed, index, and produce `knowledge_ingestion_report.json`. |
| `knowledge_get_ingestion_status` | Quantitative Methods Agent | `read_only` | Fetch source/ingestion status, warnings, and indexed chunk counts. |
| `knowledge_list_sources` | Quantitative Methods Agent | `read_only` | List approved or available source manifests by topic, source type, method family, or status. |
| `knowledge_search_methods` | Quantitative Methods Agent | `read_only` | Search approved method cards and optionally draft method cards. |
| `knowledge_retrieve_evidence` | Quantitative Methods Agent | `read_only` | Retrieve citeable chunks for a method, assumption, implementation convention, or statistical test. |
| `knowledge_get_evidence_chunks` | Quantitative Methods Agent | `read_only` | Dereference retrieved chunk IDs into bounded real stored chunk text with source metadata, locators, hash verification, and truncation flags. |
| `knowledge_create_method_card_draft` | Quantitative Methods Agent | `local_mutating` | Create a non-approved draft method card from retrieved source evidence. |
| `knowledge_publish_method_card` | Quantitative Methods Agent | `local_mutating` | Promote a draft method card to approved status after maintainer/operator approval. |
| `knowledge_validate_citations` | Quantitative Methods Agent | `read_only` | Validate source IDs, chunk IDs, locators, and method-card coverage for a contract/report. |

`knowledge_publish_method_card` requires `approve=True`, an approver, and an approval note. Without explicit publish,
draft cards remain non-executable.

## Knowledge-Aware Quantitative Methods Tool Policy

The Quantitative Methods graph may call:

```text
mcp_health
mcp_get_config
knowledge_register_source
knowledge_ingest_documents
knowledge_get_ingestion_status
knowledge_list_sources
knowledge_search_methods
knowledge_retrieve_evidence
knowledge_get_evidence_chunks
knowledge_create_method_card_draft
knowledge_publish_method_card
knowledge_validate_citations
math_list_method_contracts
math_validate_method_contract
math_create_indicator_contract
math_run_indicator_fixtures
math_run_signal_diagnostics
math_run_multiple_testing_report
math_generate_cpp_kernel
math_compile_kernel
math_run_python_cpp_parity
math_package_method_artifact
```

The Quantitative Methods graph must not call:

```text
data_*
ml_*
hypothesis_*
evaluation_*
adversarial_*
research_run_backtest
research_generate_recommendation
place_order
cancel_order
raw_sql
broker_mutating_tools
```

Knowledge ingestion is a local-mutating research action. It mutates the local knowledge index and artifact directory, but it must not mutate broker state, market data, strategy promotion state, or live trading configuration.

## Package Shape for the Knowledge Base

Add a dedicated knowledge package under `trader_research`:

```text
src/trader_research/
  knowledge/
    __init__.py
    domain.py               # source manifests, chunk manifests, method cards, retrieval reports
    sources.py              # source registration and metadata validation
    extractors.py           # PDF/Markdown/text extraction adapters
    chunking.py             # chunk creation and locator preservation
    embeddings.py           # embedding provider protocol plus runtime/test implementations
    store.py                # KnowledgeStore interface plus JSON compatibility adapter
    postgres_store.py       # adapter to core Postgres knowledge persistence
    index.py                # embedding indexing, hybrid retrieval, and deterministic rank fusion
    retrieval.py            # hybrid retrieval, rank fusion, method-card search, and evidence services
    citation_validation.py  # source/locator/method-card coverage checks
    method_cards.py         # draft/publish method-card workflow
    ingestion.py            # end-to-end ingestion orchestration

src/trader_mcp/
  knowledge_tools.py        # MCP registrations/adapters for knowledge tools

src/trader_agents/
  quant_methods_agent.py       # knowledge-aware allowlist and state
  quant_methods_policy.py      # typed LLM decisions that may request retrieval/ingestion

src/trader/
  knowledge_store.py           # SQL-owning Postgres knowledge tables, full-text search, and pgvector retrieval
```

The durable implementation now uses a `KnowledgeStore` boundary. MCP runtime defaults to the Postgres implementation, using the existing trader Postgres config from `TRADER_MCP_TRADER_CONFIG_PATH`; tests can inject the JSON compatibility store or other fakes. Postgres owns source/chunk/embedding/ingestion records, PostgreSQL full-text search provides lexical retrieval, and pgvector provides dense retrieval. Deterministic embeddings are test doubles only; runtime ingestion requires explicit embedding-provider configuration. JSON artifacts remain compatibility/export records, while approved source registry records and approved method cards remain the authority.

## Hybrid Retrieval Requirement

`knowledge_retrieve_evidence` should use hybrid retrieval rather than pure vector search:

```text
query
  -> lexical search top K
  -> vector search top K
  -> merge and deduplicate
  -> deterministic rank fusion
  -> optional rerank later
  -> source/method/approval filters
  -> citeable evidence chunks
```

Lexical retrieval is required for exact method names and acronyms such as `Newey-West`, `HAC`, `ADF`, `KPSS`, `White Reality Check`, `Hansen SPA`, `Benjamini-Hochberg`, and `Deflated Sharpe Ratio`. Vector retrieval is required for conceptual queries such as data snooping, dependent-return uncertainty, bootstrap inference, and multiple-testing controls. Retrieval reports should include lexical rank, vector rank, combined rank, vector score, source title, source approval status, chunk ID, source ID, and locators.

## Revised Backlog: Knowledge-Backed Quantitative Methods

Replace the earlier Quantitative Methods chunks with the sequence below.

### 23A. Quant Methods Knowledge Domain Schemas

Description:

Define schemas for:

- `knowledge_source_manifest.json`
- `knowledge_ingestion_report.json`
- `knowledge_chunk_manifest.json`
- `knowledge_embedding_manifest.json`
- `method_card_draft.json`
- `method_card.json`
- `evidence_retrieval_report.json`
- `citation_validation_report.json`

Files affected:

```text
src/trader_research/knowledge/domain.py
tests/test_knowledge_domain.py
```

Acceptance criteria:

- Schemas serialize to JSON-safe dictionaries.
- Source manifests include source ID, title, source type, file hash, access policy, topics, and warnings.
- Chunk manifests preserve source ID, page/section/heading locators, offsets, and chunk hashes.
- Embedding manifests record embedding provider, model/version, dimensions, and created_at.
- Method cards include assumptions, inputs, outputs, failure modes, source evidence, and approval status.
- Draft method cards cannot be used as executable method contracts.

### 23B. Knowledge Source Registration

Description:

Implement source registration for local documents or artifact references.

Files affected:

```text
src/trader_research/knowledge/sources.py
src/trader_research/knowledge/ingestion.py
tests/test_knowledge_sources.py
```

Acceptance criteria:

- Valid source metadata produces `knowledge_source_manifest.json`.
- Missing metadata fails closed when `fail_on_missing_metadata=True`.
- Duplicate file hashes are detected.
- Unsupported file types are rejected.
- Sources outside allowed directories are rejected.
- Source registration does not embed or index content yet.

### 23C. Text Extraction and Chunking

Description:

Extract text from PDF, Markdown, and plain text sources and create locator-preserving chunks.

Files affected:

```text
src/trader_research/knowledge/extractors.py
src/trader_research/knowledge/chunking.py
tests/test_knowledge_extraction.py
tests/fixtures/knowledge/*
```

Acceptance criteria:

- Markdown and text fixtures are extracted deterministically.
- PDF extraction preserves page numbers where available.
- Extraction warnings are included in the ingestion report.
- Chunk IDs and chunk hashes are deterministic for unchanged content/config.
- Chunks include source ID and locator metadata.
- OCR is disabled unless explicitly permitted.

### 23D. Embedding and Indexing Service

Description:

Embed chunks and store them in a searchable Postgres-backed knowledge index with relational metadata filters, PostgreSQL full-text lexical search, and pgvector dense retrieval.

Files affected:

```text
src/trader_research/knowledge/embeddings.py
src/trader_research/knowledge/store.py
src/trader_research/knowledge/postgres_store.py
src/trader_research/knowledge/index.py
src/trader_research/knowledge/ingestion.py
tests/test_knowledge_embeddings.py
tests/test_knowledge_store.py
tests/test_postgres_knowledge_store.py
```

Acceptance criteria:

- Runtime embedding configuration supports a real OpenAI-compatible embedding model.
- A fake deterministic embedding provider exists only for tests.
- Embedding manifest records provider/model/revision/dimension/distance metric/chunker version/source collection/index ID.
- Source/chunk/embedding/ingestion metadata are stored in Postgres during MCP runtime.
- Lexical terms are indexed with PostgreSQL full-text search initially.
- Dense embeddings are stored in pgvector.
- Indexed chunks can be retrieved by source ID, topic, method family, lexical match, and vector similarity.
- Re-ingesting unchanged chunks does not create duplicate active chunks.
- Changing embedding model/chunker/source collection creates a distinct immutable index version.
- The service can run without an external LLM provider in tests.
- `mcp_get_config` reports `knowledge_store_runtime`; missing Postgres config or pgvector fails closed at tool execution.

### 23E. Knowledge Ingestion MCP Tools

Description:

Expose source registration, document ingestion, and ingestion status through MCP.

Files affected:

```text
src/trader_mcp/knowledge_tools.py
src/trader_mcp/server.py
tests/test_mcp_knowledge_tools.py
```

Acceptance criteria:

- MCP exposes `knowledge_register_source`, `knowledge_ingest_documents`, and `knowledge_get_ingestion_status`.
- Every tool returns a shared envelope with side-effect metadata.
- Ingestion tools are `local_mutating`, not `read_only`.
- Tools reject unsupported file types and unbounded directories.
- MCP smoke tests ingest at least one Markdown/text fixture and retrieve ingestion status.

### 23F. Method Card Drafting and Approval

Description:

Create draft method cards from source evidence and allow explicit approval/publishing. This tranche is implemented as
deterministic structured validation and persistence; it does not ask an LLM to author cards internally.

Files affected:

```text
src/trader_research/knowledge/method_cards.py
src/trader_research/knowledge/retrieval.py
tests/test_method_cards.py
```

Acceptance criteria:

- Draft method cards require at least one validated source evidence reference.
- Draft method cards include assumptions, inputs, outputs, and failure modes.
- Draft cards are not executable by Quantitative Methods method-contract tools.
- Publishing requires explicit approval input, approver, and approval note.
- Approved method cards are immutable by default; conflicting duplicate publishes fail closed.

### 23G. Knowledge Retrieval and Citation Validation MCP Tools

Description:

Expose method-card search, hybrid evidence retrieval, and citation validation through MCP.

Files affected:

```text
src/trader_research/knowledge/retrieval.py
src/trader_research/knowledge/citation_validation.py
src/trader_mcp/knowledge_tools.py
tests/test_knowledge_retrieval.py
tests/test_citation_validation.py
tests/test_mcp_knowledge_tools.py
```

Acceptance criteria:

- MCP exposes `knowledge_list_sources`, `knowledge_search_methods`, `knowledge_retrieve_evidence`, `knowledge_get_evidence_chunks`, `knowledge_create_method_card_draft`, `knowledge_publish_method_card`, and `knowledge_validate_citations`.
- Retrieval runs lexical search and vector search, merges/deduplicates results with deterministic rank fusion, and returns source IDs, chunk IDs, locators, source titles, approval status, lexical rank, vector rank, combined rank, vector score, and short excerpts/summaries; dereferencing returns bounded real chunk text by chunk ID with hash verification and truncation flags.
- Citation validation fails if a method contract references unknown source IDs, invalid locators, unapproved sources, unapproved method cards, unsupported claims, excessive direct quotation, or high-risk methods backed only by broad foundation sources.
- Retrieval can be filtered to approved sources/method cards only.

### 23H. Knowledge-Backed Math Method Domain Schemas

Description:

Define Quantitative Methods method schemas that require knowledge provenance for non-trivial statistical methods.

Files affected:

```text
src/trader_research/math_domain.py
src/trader_research/domain.py
tests/test_math_domain.py
```

Acceptance criteria:

- `indicator_contract.json`, `statistical_test_contract.json`, `signal_diagnostic_report.json`, `multiple_testing_report.json`, `cxx_kernel_manifest.json`, `python_cpp_parity_report.json`, and `method_package_manifest.json` include optional or required `knowledge_evidence_refs` depending on method complexity.
- Statistical-test and multiple-testing contracts require approved method cards.
- Simple arithmetic transforms may be allowed from maintained registry without external source retrieval.
- Unknown or uncited sophisticated methods fail closed.

### 23I. Knowledge-Backed Math Method Registry

Description:

Create the maintained registry of approved methods, linked to approved method cards where required.

Files affected:

```text
src/trader_research/math_registry.py
src/trader_research/math_tools.py
tests/test_math_registry.py
```

Acceptance criteria:

- Registry lists maintained methods by family.
- Each non-trivial statistical method links to one or more approved method cards.
- Unsupported methods fail closed.
- Registry can filter to legacy indicator-only views for compatibility.

### 23J. Indicator Contract and Fixture Validation

Description:

Implement deterministic indicator/transform validation.

Files affected:

```text
src/trader_research/math_tools.py
src/trader_standard/indicators/python/*
tests/test_math_indicator_contracts.py
tests/fixtures/math_indicators/*
```

Acceptance criteria:

- Contract validation checks parameter bounds, warmup behavior, NaN policy, output schema, and no-lookahead metadata.
- Fixture tests cover small known input/output cases.
- Validation returns `indicator_validation_report.json` or an embedded equivalent envelope.
- Unsupported indicators and invalid parameter grids fail closed.

### 23K. Signal Diagnostics and Multiple-Testing Reports

Description:

Implement first-pass signal diagnostics and family-level inference over declared candidate families.

Files affected:

```text
src/trader_research/signal_diagnostics.py
src/trader_research/multiple_testing.py
src/trader_research/math_tools.py
tests/test_signal_diagnostics.py
tests/test_multiple_testing.py
```

Acceptance criteria:

- Computes IC/rank IC, hit rate, quantile buckets, monotonicity, horizon decay, and symbol/session/regime breakdowns where inputs exist.
- Requires candidate family manifests for family-level inference.
- Records raw p-values, adjusted p-values, correction method, tested grid, and candidate count.
- Requires approved method-card references for sophisticated inference procedures.
- Produces `signal_diagnostic_report.json` and `multiple_testing_report.json` with warnings and blockers.

### 23L. C++ Kernel Path

Description:

Implement a controlled compiled-kernel path for approved deterministic transforms.

Files affected:

```text
src/trader_research/cpp_kernel_artifacts.py
src/trader_research/math_tools.py
src/trader_standard/indicators/cpp/*
src/trader_standard/indicators/bindings/*
tests/test_cpp_kernel_artifacts.py
tests/test_python_cpp_parity.py
```

Acceptance criteria:

- C++ generation is template-based only.
- Compilation occurs in an isolated local build directory.
- Kernel manifest records build settings, ABI/binding info, source/template provenance, and benchmark summary.
- Python/C++ parity tests run on deterministic fixtures and seeded generated cases.
- Failed compile or failed parity returns a blocking Quantitative Methods envelope.
- No generated kernel has access to broker mutation, SQL, network, or live trading controls.

### 24. Register Quantitative Methods MCP Tools

Description:

Expose the Quantitative Methods deterministic method surface through MCP after knowledge ingestion/retrieval tools exist.

Files affected:

```text
src/trader_mcp/server.py
src/trader_mcp/schemas.py
tests/test_mcp_math_tools.py
tests/test_mcp_server.py
```

Acceptance criteria:

- MCP exposes `math_list_method_contracts` and `math_validate_method_contract` first.
- Backward-compatible aliases for `math_list_indicator_contracts` and `math_validate_indicator_contract` may exist.
- Follow-on Quantitative Methods tools are registered only after direct services pass tests.
- Every tool returns a shared envelope with `agent_owner = "Quantitative Methods Agent"`.
- Every tool declares side-effect class.
- MCP rejects unbounded inputs and unknown methods.
- Statistical-test/multiple-testing tools require approved method-card references where configured.

### 25. Quantitative Methods Agent Graph

Description:

Create the knowledge-aware Quantitative Methods LangGraph identity and state model.

Files affected:

```text
src/trader_agents/quant_methods_agent.py
src/trader_agents/quant_methods_policy.py
src/trader_agents/state.py
tests/test_quant_methods_agent.py
tests/test_langgraph_agents.py
```

Acceptance criteria:

- Quantitative Methods graph has a distinct identity and state schema.
- Graph may call knowledge and Quantitative Methods MCP tools only.
- Graph cannot fetch data, create hypotheses, train models, run backtests, call evaluation tools, or promote strategies.
- Graph blocks if sophisticated methods lack approved source-backed method cards.
- Graph returns method artifact references, retrieval evidence refs, citation validation refs, and structured blockers.
- No raw prompts, hidden reasoning, or scratchpads are persisted.

### 26. Supervisor Consumes Knowledge-Backed Quantitative Methods Handoff

Description:

Allow the Quant Research Supervisor to consume Quantitative Methods artifacts and their knowledge provenance without rewriting them.

Files affected:

```text
src/trader_agents/quant_research.py
src/trader_research/domain.py
tests/test_supervisor_quant_methods_handoff.py
```

Acceptance criteria:

- Supervisor accepts valid Quantitative Methods handoffs with method artifacts and knowledge evidence references.
- Supervisor rejects handoffs with wrong `agent_owner`, missing provenance, missing artifact refs, unresolved blockers, or failed citation validation.
- Supervisor can require Quantitative Methods artifacts before strategy planning when a hypothesis depends on deterministic indicators or statistical tests.
- Supervisor stores references, warnings, blockers, and public status only.
- Supervisor does not modify Quantitative Methods artifacts or knowledge evidence.

## Revised Slice 5: Knowledge and Quantitative Methods MCP Tool Creation

Implement chunks 23A-24. This creates the knowledge base ingestion/retrieval layer and then proves the first Quantitative Methods MCP tools before the Quantitative Methods LangGraph identity exists.

Evidence target:

```text
knowledge_register_source
knowledge_ingest_documents
knowledge_get_ingestion_status
knowledge_search_methods
knowledge_retrieve_evidence
knowledge_get_evidence_chunks
knowledge_create_method_card_draft
knowledge_publish_method_card
knowledge_validate_citations
math_list_method_contracts
math_validate_method_contract
  -> source manifests, ingestion reports, retrieved refs, dereferenced chunk text, approved method cards, citation validation, and method metadata
  -> declares agent_owner = Quantitative Methods Agent for first release
  -> records source IDs, locators, assumptions, fixture status, and failure modes
```

Stretch evidence:

```text
math_run_signal_diagnostics
math_run_multiple_testing_report
  -> approved method card used to validate a statistical-test/multiple-testing contract
  -> report records candidate family size, tested parameter grid, raw p-values, adjusted p-values, warnings, and blockers
```

## Revised Slice 6: Knowledge-Aware Quantitative Methods Agent Identity and Handoff

Implement chunks 25-26. This proves that the Quantitative Methods graph has its own identity, can use knowledge tools and Quantitative Methods tools, and that the supervisor consumes but does not rewrite Quantitative Methods artifacts.

Evidence target:

```text
Quantitative Methods graph starts
  -> graph state includes Quantitative Methods identity
  -> graph calls only knowledge_* and math_* MCP tools
  -> graph blocks unsupported/uncited methods
  -> graph returns method artifact refs + retrieval/citation refs
  -> supervisor consumes Quantitative Methods handoff
  -> supervisor preserves ownership/provenance and blocks unresolved method warnings
```

## Updated Practical First Implementation Order

The smallest useful version is:

```text
1. Define knowledge artifact schemas.
2. Implement source registration for Markdown/text fixtures.
3. Implement deterministic extraction and chunking.
4. Implement runtime embedding-provider configuration with fake deterministic embeddings only for tests.
5. Implement Postgres-backed lexical and vector knowledge indexes.
6. Register knowledge_register_source, knowledge_ingest_documents, and knowledge_get_ingestion_status.
7. Add knowledge_search_methods, hybrid knowledge_retrieve_evidence, and knowledge_get_evidence_chunks over approved method cards and indexed sources.
8. Add citation validation.
9. Add method_card_draft and explicit publish/approval flow.
10. Define math artifact schemas that can reference knowledge evidence.
11. Build method registry linked to approved method cards.
12. Register math_list_method_contracts and math_validate_method_contract.
13. Implement deterministic fixtures for a tiny indicator set:
    - SMA
    - EMA
    - rolling volatility
    - z-score
    - RSI
14. Add signal diagnostics:
    - IC
    - rank IC
    - quantile buckets
    - horizon decay
15. Add multiple-testing report:
    - candidate family manifest
    - raw p-values
    - Bonferroni
    - Holm
    - Benjamini-Hochberg
16. Add Quantitative Methods LangGraph identity.
17. Add supervisor handoff consumption with knowledge provenance.
18. Add C++ path only after Python contracts, citations, and reports are stable.
```

## Additional Guardrails

- Ingestion does not imply approval.
- Retrieved chunks do not imply that a method is supported.
- Draft method cards are not executable.
- Production method contracts for statistical procedures must cite approved method cards.
- Artifacts should cite source IDs and locators, not reproduce large copyrighted passages.
- Knowledge tools must not expose arbitrary filesystem access.
- Knowledge tools must not execute code from documents.
- Embedding model and chunking configuration must be versioned.
- Re-indexing should be reproducible for unchanged source files and config.
- Quantitative Methods should block rather than improvise when no approved method source exists.

## Why Expand the Definition

Indicator implementation is the easiest part. The harder and more valuable responsibility is preventing the research system from mistaking noise, leakage, parameter mining, and data snooping for alpha.

A large indicator universe creates hidden statistical risk:

```text
symbols x timeframes x indicators x parameter grids x horizons x regimes x cost assumptions
```

If the system only reports the winning configuration, it will produce false confidence. The Quantitative Methods Agent should therefore record the full candidate family and produce inference artifacts that downstream agents can inspect.

The agent should never return only:

```text
best_indicator = "ema_cross_12_48"
```

It should return:

```text
candidate_family_id
candidate_count
full_parameter_grid
selection_rule
all tested metrics
raw p_values
adjusted_p_values
data_quality_references
cost_or_label_assumptions
warnings
accepted_candidates
rejected_candidates
```

## Agent Distinction

| Agent | Core question | Owns | Must not own |
| --- | --- | --- | --- |
| Quantitative Methods Agent | Is this deterministic mathematical object correctly defined, implemented, and statistically testable? | Indicators, transforms, statistical tests, multiple-testing methods, signal diagnostics, Python/C++ parity reports | Strategy ideas, model training, broad research campaigns, final verdicts |
| ML Agent | Can a learned model produce a versioned predictive artifact? | Feature manifests, model cards, fitted models, prediction artifacts, drift reports | Hand-coded deterministic method ownership, hypothesis generation, final recommendations |
| Hypothesis Agent | What is the tradable claim or mechanism worth testing? | Hypothesis cards with mechanism, required features, target regime, falsification criteria | Implementation, statistical-test ownership, model training, backtests, verdicts |
| Evaluation Agent | Does the evidence survive skeptical review? | Evaluation reports, blockers, caveats, weak-sample findings, overfit warnings | New methods, new strategy ideas, final recommendations |
| Quant Research Supervisor Agent | What should run next, and what does the evidence collectively imply? | Experiment plans, research suites, comparisons, recommendations | Specialist artifact creation, low-level indicators, model training, critique fabrication |

The same object can move through several agents without blurring ownership:

```text
rolling_volatility_30
  -> Quantitative Methods artifact as a deterministic transform

rolling_volatility_30 used as model input
  -> ML Agent feature input

"High-volatility regimes alter trend-following performance"
  -> Hypothesis Agent hypothesis card

"Strategy performance is unstable across volatility regimes"
  -> Evaluation Agent critique
```

## Owned Artifact Families

The Quantitative Methods Agent should own the following artifacts.

| Artifact | Purpose |
| --- | --- |
| `indicator_contract.json` | Defines a deterministic indicator or transform: inputs, parameters, lookback, warmup, output schema, NaN convention, no-lookahead guarantee, and implementation backend. |
| `statistical_test_contract.json` | Defines null hypothesis, alternative, statistic, assumptions, sample requirements, dependence handling, p-value method, correction method, and failure modes. |
| `indicator_validation_report.json` | Captures fixture tests, edge cases, warmup/NaN behavior, lookahead checks, deterministic replay status, and Python/C++ parity status. |
| `signal_diagnostic_report.json` | Captures predictive association diagnostics such as IC, rank IC, hit rate, quantile monotonicity, forward-return decay, turnover proxy, horizon sensitivity, and symbol/session/regime breakdowns. |
| `multiple_testing_report.json` | Captures tested family size, raw metrics, raw p-values, adjusted p-values, false discovery controls, data-snooping checks, accepted/rejected candidates, warnings, and blockers. |
| `cxx_kernel_manifest.json` | Captures compiled kernel identity, source/template provenance, ABI/build metadata, wrapper information, supported input/output schemas, and benchmark summary. |
| `python_cpp_parity_report.json` | Captures seeded parity fixtures, tolerance policy, mismatches, numerical warnings, and whether the compiled implementation is safe for downstream use. |
| `method_package_manifest.json` | Bundles contracts, implementations, tests, reports, provenance, and artifact references for supervisor handoff. |

## Method Contract Schema Sketches

### Indicator Contract

```json
{
  "artifact_type": "indicator_contract",
  "agent_owner": "Quantitative Methods Agent",
  "method_id": "ema_cross",
  "method_version": "1.0.0",
  "family": "trend_transform",
  "description": "Difference or sign relationship between two exponential moving averages.",
  "inputs": {
    "required_columns": ["timestamp", "close"],
    "index": "timestamp",
    "frequency_policy": "bar_aligned"
  },
  "parameters": {
    "fast_window": {"type": "integer", "minimum": 2},
    "slow_window": {"type": "integer", "minimum": 3, "must_exceed": "fast_window"}
  },
  "warmup": {
    "minimum_bars": "slow_window",
    "output_before_warmup": "null"
  },
  "outputs": {
    "columns": ["ema_fast", "ema_slow", "ema_diff", "ema_cross_signal"],
    "dtype_policy": "float64_except_signal_int8"
  },
  "numerical_policy": {
    "nan_policy": "propagate",
    "inf_policy": "reject",
    "tolerance": 1e-10
  },
  "lookahead_policy": {
    "uses_future_data": false,
    "alignment": "output_at_bar_close"
  },
  "implementations": {
    "python_reference": "trader_standard.indicators.python.ema_cross",
    "cpp_kernel": "optional"
  },
  "provenance": {
    "created_by": "Quantitative Methods Agent",
    "source_request_id": "req_...",
    "code_version": "git_sha_or_build_id"
  }
}
```

### Statistical Test Contract

```json
{
  "artifact_type": "statistical_test_contract",
  "agent_owner": "Quantitative Methods Agent",
  "method_id": "rank_ic_test",
  "method_version": "1.0.0",
  "family": "signal_diagnostic",
  "null_hypothesis": "Indicator ranks have no association with future return ranks.",
  "alternative": "Indicator ranks are associated with future return ranks.",
  "required_inputs": [
    "indicator_observation_reference",
    "forward_return_label_reference",
    "data_quality_report_reference"
  ],
  "statistic": "spearman_rank_correlation",
  "dependence_handling": {
    "method": "block_bootstrap_or_hac",
    "required_config": ["block_length", "num_resamples"]
  },
  "multiple_testing": {
    "supported_corrections": ["bonferroni", "holm", "benjamini_hochberg", "white_reality_check", "hansen_spa"]
  },
  "sample_requirements": {
    "minimum_observations": 500,
    "minimum_symbols": 1,
    "minimum_non_null_fraction": 0.95
  },
  "failure_modes": [
    "candidate_family_not_declared",
    "insufficient_effective_observations",
    "unresolved_data_quality_warnings",
    "overlapping_forward_returns_without_dependence_adjustment"
  ]
}
```

## Statistical Method Knowledge Base

The Quantitative Methods Agent should use a structured registry of methods, not free-form memory. Each method entry should define purpose, inputs, outputs, assumptions, failure modes, and whether the method is approved for MCP execution.

### Registry Entry Sketch

```json
{
  "method_id": "white_reality_check",
  "family": "multiple_testing",
  "status": "planned",
  "purpose": "Adjust performance inference for data-snooping across a declared candidate strategy or signal family.",
  "inputs": [
    "candidate_return_matrix",
    "benchmark_return_series",
    "block_bootstrap_config",
    "candidate_family_manifest"
  ],
  "outputs": [
    "test_statistic",
    "p_value",
    "candidate_family_size",
    "warnings"
  ],
  "assumptions": [
    "candidate family is fully declared before inference",
    "return series are suitable for dependence-aware resampling"
  ],
  "failure_modes": [
    "family not fully recorded",
    "too few effective observations",
    "unstable bootstrap configuration",
    "unresolved data quality warnings"
  ],
  "artifact_outputs": ["multiple_testing_report.json"]
}
```

### Initial Method Families

| Area | Initial methods |
| --- | --- |
| Core transforms | SMA, EMA, WMA, returns, log returns, cumulative returns, rolling mean, rolling standard deviation, z-score, min/max range, drawdown, rolling drawdown. |
| Trend and momentum | EMA cross, MACD, rate of change, Donchian breakout, slope over window, rolling regression beta/slope. |
| Mean reversion | RSI, Bollinger Band distance, rolling z-score, distance from moving average, spread/z-score transforms for pairs or baskets. |
| Volatility and range | ATR, Parkinson-style range proxy, realized volatility, rolling absolute return, volatility-of-volatility, gap/range diagnostics. |
| Cross-sectional transforms | Cross-sectional rank, percentile rank, demeaned value, sector/group neutralization if metadata exists, winsorization, robust z-score. |
| Dependence diagnostics | Autocorrelation, partial autocorrelation, Ljung-Box-style checks, overlapping-label warnings, HAC/Newey-West-style standard errors where applicable. |
| Stationarity and regime instability | ADF-style unit-root checks, KPSS-style stationarity checks, rolling statistic stability, structural-break flags. |
| Signal diagnostics | Pearson IC, Spearman rank IC, hit rate, quantile bucket returns, monotonicity score, forward-return decay, horizon sensitivity, turnover proxy. |
| Resampling | IID bootstrap only when valid, block bootstrap, stationary bootstrap, bootstrap confidence intervals. |
| Multiple testing | Bonferroni, Holm, Benjamini-Hochberg FDR, White Reality Check, Hansen SPA. |
| Backtest-overfitting diagnostics | Deflated Sharpe Ratio, Probability of Backtest Overfitting, combinatorially symmetric cross-validation, parameter stability surfaces. |
| Operational numerics | Streaming rolling windows, online mean/variance, warmup semantics, NaN propagation, finite precision tolerance, deterministic replay. |

## Expanded MCP Tool Surface

The existing planned tools should remain as the first slice, but they should be generalized from “indicator contracts” to “method contracts.”

### Initial Tools

| Tool | Owner | Side effect | Purpose |
| --- | --- | --- | --- |
| `math_list_method_contracts` | Quantitative Methods Agent | `read_only` | List maintained indicators, transforms, statistical tests, diagnostics, and multiple-testing procedures. |
| `math_validate_method_contract` | Quantitative Methods Agent | `read_only` | Validate method parameters, input schema, warmup behavior, assumptions, and fixture expectations. |

Backward-compatible aliases may be kept initially:

```text
math_list_indicator_contracts -> math_list_method_contracts filtered to indicator/transform families
math_validate_indicator_contract -> math_validate_method_contract filtered to indicator/transform families
```

### Follow-on Tools

| Tool | Owner | Side effect | Purpose |
| --- | --- | --- | --- |
| `math_create_indicator_contract` | Quantitative Methods Agent | `local_mutating` | Create a structured indicator contract from an approved template family. |
| `math_run_indicator_fixtures` | Quantitative Methods Agent | `local_mutating` | Run deterministic fixture tests and produce `indicator_validation_report.json`. |
| `math_run_signal_diagnostics` | Quantitative Methods Agent | `local_mutating` | Given indicator observations and forward-return labels, produce `signal_diagnostic_report.json`. |
| `math_run_multiple_testing_report` | Quantitative Methods Agent | `local_mutating` | Given a declared candidate family and metric matrix, produce `multiple_testing_report.json`. |
| `math_generate_cpp_kernel` | Quantitative Methods Agent | `local_mutating` | Generate C++ only from approved templates and produce draft kernel metadata. |
| `math_compile_kernel` | Quantitative Methods Agent | `local_mutating` | Compile the generated/maintained kernel locally and return build evidence. |
| `math_run_python_cpp_parity` | Quantitative Methods Agent | `local_mutating` | Compare Python reference output against C++ output on fixtures and seeded generated cases. |
| `math_package_method_artifact` | Quantitative Methods Agent | `local_mutating` | Bundle contracts, implementation refs, validation reports, parity reports, and provenance for handoff. |

## C++ Kernel Policy

The C++ path is valuable, but it should be template-restricted. The Quantitative Methods Agent should not emit arbitrary runtime code into the trading system.

Recommended flow:

```text
Python reference implementation
  -> deterministic fixtures
  -> approved C++ template selection
  -> C++ implementation
  -> Python binding
  -> Python/C++ parity tests
  -> benchmark report
  -> cxx_kernel_manifest.json
  -> supervisor handoff
```

### C++ Guardrails

- No arbitrary includes outside an allowlist.
- No network, filesystem mutation, broker access, SQL access, or process execution from generated kernels.
- No dynamic code loading in the live trading hot path.
- All generated kernels must compile in an isolated build directory.
- All compiled kernels must pass Python/C++ parity tests before registration.
- All kernels must declare warmup, NaN, alignment, dtype, and lookahead policies.
- All kernels must support deterministic replay.
- Failed parity blocks downstream operational use.

### Suggested Package Placement

Stable maintained kernels should live in `trader_standard`, while research orchestration and artifact reporting should live in `trader_research`.

```text
src/trader_standard/
  indicators/
    python/
    cpp/
    bindings/
    contracts/

src/trader_research/
  math_tools.py
  math_registry.py
  signal_diagnostics.py
  multiple_testing.py
  cpp_kernel_artifacts.py

src/trader_agents/
  quant_methods_agent.py
  quant_methods_policy.py
```

This keeps the core `trader` package free of agent/MCP schemas and keeps maintained reusable implementations separate from research artifact production.

## Quantitative Methods LangGraph Identity

The Quantitative Methods Agent graph should have its own state, policy, allowlist, and artifact contract.

### State Sketch

```python
class QuantMethodsState(TypedDict, total=False):
    agent_identity: str
    request_id: str
    bounded_request: dict
    input_artifact_refs: list[dict]
    method_contract_refs: list[dict]
    validation_report_refs: list[dict]
    signal_diagnostic_report_refs: list[dict]
    multiple_testing_report_refs: list[dict]
    cxx_kernel_manifest_refs: list[dict]
    parity_report_refs: list[dict]
    warnings: list[str]
    blockers: list[str]
    called_tools: list[dict]
    public_status: str
```

### Allowed Tool Pattern

The graph may call:

```text
mcp_health
mcp_get_config
math_list_method_contracts
math_validate_method_contract
math_create_indicator_contract
math_run_indicator_fixtures
math_run_signal_diagnostics
math_run_multiple_testing_report
math_generate_cpp_kernel
math_compile_kernel
math_run_python_cpp_parity
math_package_method_artifact
```

The graph must not call:

```text
data_*
ml_*
hypothesis_*
evaluation_*
adversarial_*
research_run_backtest
research_generate_recommendation
place_order
cancel_order
raw_sql
broker_mutating_tools
```

## LLM Policy for Quantitative Methods

The Quantitative Methods Agent may eventually use an LLM inside a bounded LangGraph control-policy node, but the LLM must not directly execute code or bypass deterministic tools.

Allowed LLM decisions:

```text
select_method_contract
request_missing_input
validate_method_contract
run_fixtures
run_signal_diagnostics
run_multiple_testing
request_cpp_kernel
run_parity_check
package_artifact
block
finish
```

Every proposed action must be validated by a deterministic router against:

- tool allowlist
- side-effect policy
- input artifact ownership
- required data-quality references
- candidate family declaration
- loop limit
- artifact output contract
- no raw prompt or hidden reasoning persistence

## Supervisor Handoff Contract

Every Quantitative Methods handoff to the Quant Research Supervisor should include:

```json
{
  "agent_owner": "Quantitative Methods Agent",
  "handoff_type": "math_method_artifact",
  "artifact_refs": [
    {
      "artifact_type": "indicator_contract",
      "path": "artifacts/research/.../indicator_contract.json"
    },
    {
      "artifact_type": "indicator_validation_report",
      "path": "artifacts/research/.../indicator_validation_report.json"
    },
    {
      "artifact_type": "multiple_testing_report",
      "path": "artifacts/research/.../multiple_testing_report.json"
    }
  ],
  "source_inputs": [
    "dataset_manifest_ref",
    "data_quality_report_ref",
    "candidate_family_manifest_ref"
  ],
  "warnings": [],
  "blockers": [],
  "side_effect": "local_mutating",
  "provenance": {
    "request_id": "req_...",
    "code_version": "git_sha_or_build_id",
    "created_at": "iso8601_timestamp"
  }
}
```

The supervisor may accept, reject, request more work, or block the research path. It must not rewrite Quantitative Methods artifacts to make a result look better.


> Knowledge-base update note: the replacement backlog below supersedes the earlier `23A-23F` Quantitative Methods backlog. The older chunks are retained after this section as historical context if needed, but implementation should follow the knowledge-backed sequence.

## Revised Backlog Chunks

Replace the current chunks 23-26 with the expanded sequence below. This keeps the existing delivery pattern: deterministic MCP evidence first, LangGraph identity second, supervisor handoff third.

### 23A. Math Method Domain Schemas

Description:

Define schemas for:

- `indicator_contract.json`
- `statistical_test_contract.json`
- `indicator_validation_report.json`
- `signal_diagnostic_report.json`
- `multiple_testing_report.json`
- `cxx_kernel_manifest.json`
- `python_cpp_parity_report.json`
- `method_package_manifest.json`

Files affected:

```text
src/trader_research/math_domain.py
src/trader_research/domain.py
tests/test_math_domain.py
```

Acceptance criteria:

- Schemas serialize to JSON-safe dictionaries.
- Every schema includes `agent_owner = "Quantitative Methods Agent"`.
- Every schema includes provenance fields.
- Validation rejects missing input references, missing parameters, missing version, and unknown artifact types.
- Schemas preserve artifact boundaries between Quantitative Methods, ML, Hypothesis, Evaluation, and Supervisor.

### 23B. Math Method Registry

Description:

Create a maintained registry of approved indicator, transform, statistical-test, diagnostic, and multiple-testing method contracts.

Files affected:

```text
src/trader_research/math_registry.py
src/trader_research/math_tools.py
tests/test_math_registry.py
```

Acceptance criteria:

- Registry lists maintained methods by family.
- Unsupported methods fail closed.
- Each method declares inputs, outputs, assumptions, failure modes, side-effect class, and artifact outputs.
- Registry can filter to legacy indicator-only views for compatibility.

### 23C. Indicator Contract and Fixture Validation

Description:

Implement deterministic indicator/transform validation.

Files affected:

```text
src/trader_research/math_tools.py
src/trader_standard/indicators/python/*
tests/test_math_indicator_contracts.py
tests/fixtures/math_indicators/*
```

Acceptance criteria:

- Contract validation checks parameter bounds, warmup behavior, NaN policy, output schema, and no-lookahead metadata.
- Fixture tests cover small known input/output cases.
- Validation returns `indicator_validation_report.json` or an embedded equivalent envelope.
- Unsupported indicators and invalid parameter grids fail closed.

### 23D. Signal Diagnostics

Description:

Implement first-pass signal diagnostics for indicator observations against forward-return labels.

Files affected:

```text
src/trader_research/signal_diagnostics.py
src/trader_research/math_tools.py
tests/test_signal_diagnostics.py
```

Acceptance criteria:

- Computes IC and rank IC where valid.
- Computes hit rate with sample counts.
- Computes quantile bucket summaries and monotonicity flags.
- Computes horizon decay when multiple forward horizons are supplied.
- Breaks results down by symbol and optionally session/regime if columns exist.
- Produces `signal_diagnostic_report.json` with warnings for weak sample size, missing labels, or unresolved data-quality issues.

### 23E. Multiple Testing and Data-Snooping Controls

Description:

Implement first-pass multiple-testing reports for declared candidate families.

Files affected:

```text
src/trader_research/multiple_testing.py
src/trader_research/math_tools.py
tests/test_multiple_testing.py
```

Acceptance criteria:

- Requires a declared candidate family manifest.
- Records full candidate count and parameter grid.
- Computes raw and adjusted p-values for supported correction methods.
- Supports at least Bonferroni, Holm, and Benjamini-Hochberg in the first implementation.
- Adds White Reality Check, Hansen SPA, Deflated Sharpe Ratio, and PBO as planned or partial methods with explicit status if not yet implemented.
- Produces `multiple_testing_report.json` with accepted/rejected candidates, warnings, and blockers.

### 23F. C++ Kernel Path

Description:

Implement a controlled compiled-kernel path for approved deterministic transforms.

Files affected:

```text
src/trader_research/cpp_kernel_artifacts.py
src/trader_research/math_tools.py
src/trader_standard/indicators/cpp/*
src/trader_standard/indicators/bindings/*
tests/test_cpp_kernel_artifacts.py
tests/test_python_cpp_parity.py
```

Acceptance criteria:

- C++ generation is template-based only.
- Compilation occurs in an isolated local build directory.
- Kernel manifest records build settings, ABI/binding info, source/template provenance, and benchmark summary.
- Python/C++ parity tests run on deterministic fixtures and seeded generated cases.
- Failed compile or failed parity returns a blocking Quantitative Methods envelope.
- No generated kernel has access to broker mutation, SQL, network, or live trading controls.

### 24. Register Quantitative Methods MCP Tools

Description:

Expose the Quantitative Methods deterministic tool surface through MCP.

Files affected:

```text
src/trader_mcp/server.py
src/trader_mcp/schemas.py
tests/test_mcp_math_tools.py
tests/test_mcp_server.py
```

Acceptance criteria:

- MCP exposes `math_list_method_contracts` and `math_validate_method_contract` first.
- Backward-compatible aliases for `math_list_indicator_contracts` and `math_validate_indicator_contract` may exist.
- Follow-on tools are registered only after their direct services pass tests.
- Every tool returns a shared envelope with `agent_owner = "Quantitative Methods Agent"`.
- Every tool declares side-effect class.
- MCP rejects unbounded inputs and unknown methods.

### 25. Quantitative Methods Agent Graph

Description:

Create the Quantitative Methods LangGraph identity and state model.

Files affected:

```text
src/trader_agents/quant_methods_agent.py
src/trader_agents/quant_methods_policy.py
src/trader_agents/state.py
tests/test_quant_methods_agent.py
tests/test_langgraph_agents.py
```

Acceptance criteria:

- Quantitative Methods graph has a distinct identity and state schema.
- Graph calls Quantitative Methods MCP tools only.
- Graph cannot fetch data, create hypotheses, train models, run backtests, call evaluation tools, or promote strategies.
- Graph returns method artifact references and structured blockers.
- No raw prompts, hidden reasoning, or scratchpads are persisted.

### 26. Supervisor Consumes Quantitative Methods Handoff

Description:

Allow the Quant Research Supervisor to consume Quantitative Methods artifacts without rewriting them.

Files affected:

```text
src/trader_agents/quant_research.py
src/trader_research/domain.py
tests/test_supervisor_quant_methods_handoff.py
```

Acceptance criteria:

- Supervisor accepts valid Quantitative Methods handoffs.
- Supervisor rejects handoffs with wrong `agent_owner`, missing provenance, missing artifact refs, or unresolved blockers.
- Supervisor can require Quantitative Methods artifacts before strategy planning when a hypothesis depends on deterministic indicators or statistical tests.
- Supervisor stores references, warnings, blockers, and public status only.
- Supervisor does not modify Quantitative Methods artifacts.

## Revised Slice 5 and Slice 6 Text

### Slice 5: Quantitative Methods MCP Tool Creation

Implement chunks 23A-24. This creates and proves the first Quantitative Methods MCP tools before the Quantitative Methods LangGraph identity exists.

Evidence target:

```text
math_list_method_contracts
math_validate_method_contract
math_run_indicator_fixtures
  -> returns method metadata or validation reports
  -> declares agent_owner = Quantitative Methods Agent
  -> records assumptions, warmup behavior, fixture status, and failure modes
```

Stretch evidence:

```text
math_run_signal_diagnostics
math_run_multiple_testing_report
  -> returns signal diagnostics and multiple-testing reports
  -> records candidate family size, tested parameter grid, raw p-values, adjusted p-values, warnings, and blockers
```

### Slice 6: Quantitative Methods Agent Identity and Handoff

Implement chunks 25-26. This proves that the Quantitative Methods graph has its own identity and that the supervisor consumes, but does not rewrite, Quantitative Methods artifacts.

Evidence target:

```text
Quantitative Methods graph starts
  -> graph state includes Quantitative Methods identity
  -> graph calls only Quantitative Methods MCP tools
  -> graph returns method artifact references
  -> supervisor consumes Quantitative Methods handoff
  -> supervisor preserves ownership/provenance and blocks unresolved method warnings
```

## End-to-End Example

```text
Data Agent
  -> dataset_manifest.json
  -> data_quality_report.json

Quantitative Methods Agent
  -> indicator_contract.json for rolling_volatility_30
  -> indicator_validation_report.json
  -> signal_diagnostic_report.json against 1h/1d forward returns
  -> multiple_testing_report.json for volatility-window grid
  -> optional cxx_kernel_manifest.json
  -> optional python_cpp_parity_report.json

Hypothesis Agent
  -> hypothesis_card.json:
     "Trend-following signals perform better in persistent high-volatility regimes."

ML Agent, if needed
  -> regime_model_card.json
  -> prediction_artifact.json
  -> drift_report.json

Quant Research Supervisor
  -> experiment_plan.json
  -> strategy validation
  -> backtest suite
  -> comparison report

Evaluation Agent
  -> evaluation_report.json

Adversarial Agent
  -> robustness_report.json

Quant Research Supervisor
  -> recommendation_report.json
```

## Non-Goals

The Quantitative Methods Agent should not:

- fetch or backfill market data
- choose the trading universe
- invent strategy hypotheses
- train ML models
- run broad strategy campaigns
- execute backtests except tiny deterministic method fixtures
- decide that a strategy passed or failed overall
- make promotion recommendations
- mutate broker state
- expose raw SQL
- place, cancel, or modify orders
- compile arbitrary unreviewed code into the live trading runtime

## Acceptance Criteria for the Expanded Quantitative Methods Release

1. Method contracts exist for deterministic indicators, transforms, statistical tests, diagnostics, and multiple-testing procedures.
2. Unsupported methods fail closed.
3. Indicator validation includes fixture tests, warmup behavior, NaN policy, output schema, and no-lookahead metadata.
4. Signal diagnostics are artifact-producing and include sample-size warnings.
5. Multiple-testing reports require a declared candidate family and record the full tested universe.
6. Raw and adjusted p-values are stored together with the correction method and assumptions.
7. Python reference implementations exist before C++ operational kernels are promoted.
8. C++ kernels are template-restricted, compiled locally, and parity-tested against Python.
9. Failed fixture, failed compile, or failed parity creates a blocker.
10. Quantitative Methods MCP tools return shared envelopes with `agent_owner = "Quantitative Methods Agent"` and explicit side-effect class.
11. The Quantitative Methods LangGraph graph can call only Quantitative Methods MCP tools.
12. Supervisor handoffs preserve Quantitative Methods ownership and provenance.
13. No Quantitative Methods output claims final alpha or promotion readiness.

## Practical First Implementation Order

The smallest useful version is:

```text
1. Define math artifact schemas.
2. Build method registry.
3. Register list/validate MCP tools.
4. Implement deterministic fixtures for a tiny indicator set:
   - SMA
   - EMA
   - rolling volatility
   - z-score
   - RSI
5. Add signal diagnostics:
   - IC
   - rank IC
   - quantile buckets
   - horizon decay
6. Add multiple-testing report:
   - candidate family manifest
   - raw p-values
   - Bonferroni
   - Holm
   - Benjamini-Hochberg
7. Add Quantitative Methods LangGraph identity.
8. Add supervisor handoff consumption.
9. Add C++ path only after Python contracts and reports are stable.
```

This avoids building a premature C++ system before the artifact contracts and statistical evidence layer are stable.

## Summary

The Quantitative Methods Agent should not be a strategy generator and should not be a generic ML substitute. It should be the system’s deterministic quant methods owner.

Its job is to answer:

```text
Is this transform mathematically defined?
Is it implemented correctly?
Does it avoid lookahead?
Does it have deterministic fixture coverage?
Does the signal show predictive association under valid assumptions?
Did we account for the number of things we tested?
Can the same calculation run consistently in Python research and C++ runtime?
Can another agent inspect the artifact and challenge the evidence?
```

That makes it meaningfully distinct from the ML Agent and Hypothesis Agent while giving the overall trading research system a much stronger statistical foundation.
