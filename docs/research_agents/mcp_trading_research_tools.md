# MCP and LangGraph Research Tools

This document is the active, iterative implementation companion for the MCP/LangGraph research-agent work.

Update it in the same change as each tool or graph slice:

- first MCP tool evidence
- Data Agent inventory, quality, and loading workflows
- LangGraph agent identity evidence
- Quant Research Supervisor handoff and synthesis evidence
- Quantitative Methods, ML, Hypothesis, Evaluation, and Adversarial tool/identity evidence
- safety boundaries and tool allowlists

The task register and detailed implementation sequence currently live in
[../../plans/mcp_trading_research_tools_plan.md](../../plans/mcp_trading_research_tools_plan.md).

## Boundary Recon

Chunk 0 confirms that the first useful MCP evidence should be the smallest read-only Data Agent slice:
`data_get_inventory`. That tool should accept bounded symbols, asset class, timeframe, start, and end values, then
return source metadata, symbol-level row counts, a dataset-manifest payload, and warnings for missing, sparse, or
unavailable data. It should not run data quality, load sample rows, backfill, validate strategies, run backtests, or
write artifacts in the first evidence loop.

Existing code should remain in place until its replacement slice is proven:

- `trader.tools.contracts` is the source to replace with `trader_research.contracts` in chunks 2 and 17.
- `trader.research` contains experiment and backtest artifact helpers that should move to `trader_research` in chunk
  18.
- `trader.tools.discovery`, `suites`, `recommendations`, `promotion`, and `artifacts` are later migration candidates;
  move them only as each capability becomes part of the new research service layer.
- `trader.backtest`, `trader.data`, `trader.data_quality`, sample data loading, and market-data backfill stay core
  platform services. Future `trader_research` services should wrap them instead of moving them.

## Minimal Envelope And MCP Adapter

Chunks 2 and 3 add the dependency-free `trader_research.contracts` envelope and `trader_mcp.adapters` conversion
helper. The adapter returns MCP-style `content`, `structuredContent`, and `isError` fields without requiring the MCP
SDK, so the next slice can add the first server skeleton on top of stable JSON contracts.

## MCP Server Skeleton

Chunk 4 adds the first stdio MCP server using `mcp>=1.27.1,<2`. Start it locally with:

```bash
uv run python -m trader_mcp.server
```

The server reads portable, non-secret control-plane configuration from `local.env`: environment label, transport,
artifact root, optional execution config pointers, and capability policy flags. Static identifiers such as server name,
tool names, and tool descriptions stay in Python metadata under `trader_mcp.constants`.

The MCP server must not require an execution environment to start. `local.env` can point at a trader YAML with
`TRADER_MCP_TRADER_CONFIG_PATH`, and it can point at the dotenv file used to expand that YAML with
`TRADER_MCP_TOOL_ENV_PATH`, but both are execution-plane inputs loaded lazily by affected tools. If either file is
missing or invalid, the failure belongs in that tool's `ToolEnvelope`; it must not break server startup, tool listing,
`mcp_health`, or `mcp_get_config`.

This boundary is intentionally not optimized for zero duplication. It is acceptable for `local.env` and `.env` to
repeat values when doing so avoids coupling MCP process startup to trader runtime secrets, database settings, broker
settings, or script defaults.

The server currently registers support tools, bounded Data Agent workflow tools, and the Quantitative Methods
knowledge/method tools:

- `mcp_health`
- `mcp_get_config`
- `data_discover_symbols`
- `data_get_inventory`
- `data_summarize_quality`
- `data_ensure_loaded`
- `knowledge_*`
- `math_*`

No broker tools, raw SQL tools, backtest tools, resources, or prompts are exposed by this server. The only LLM-backed
MCP workflow is `math_generate_python_method`; generated Python is written only to quarantine and must pass registration
plus fixtures before use. `data_discover_symbols`, `data_get_inventory`, and `data_summarize_quality` are read-only. `data_ensure_loaded` is
registered with `side_effect="local_mutating"`, but runtime mutation still requires
`TRADER_MCP_ALLOW_DATA_LOADING=true`; the default local policy rejects sample-loading requests. Provider-catalog symbol
discovery is separate and requires `TRADER_MCP_ALLOW_SYMBOL_PROVIDER_DISCOVERY=true`; local and configured-universe
symbol discovery remain read-only deterministic defaults. If `TRADER_MCP_TRADER_CONFIG_PATH` is unset, data tools use a
no-op event store unless tests inject a DuckDB store.

## Data Inventory Service

Chunk 5 adds the direct `trader_research.data.get_data_inventory` service only. It calls typed, validating core
market-data query helpers in `trader.market_data_queries`, which own the fixed table selection and parameterized SQL
against the platform `EventStore.connection()` read path. The research and MCP layers must not embed raw SQL, table
names, or direct `.execute(...)` calls. The service returns a Data Agent `ToolEnvelope` with an embedded
`dataset_manifest` payload. The manifest includes a stable dataset ID, asset class, symbols, timeframe, requested
window, source filter, total rows, completeness flag, and per-symbol row/source coverage.

Chunk 6 registers `data_get_inventory` over MCP using the same dependency-free envelope adapter. It accepts JSON-native
symbols, asset class, timeframe, start/end timestamps, and optional source, then returns `content`,
`structuredContent`, and `isError` with `agent_owner="Data Agent"` and `side_effect="read_only"`.

This tool does not load data, backfill data, write artifacts, run backtests, expose SQL tools, or mutate state.

## First MCP Tool Evidence

Chunk 7 proves the first end-to-end MCP evidence loop through a real stdio client:

```bash
uv run pytest tests/test_mcp_first_tool_evidence.py
```

The test starts a test-only DuckDB-backed MCP server, lists the registered tools, calls `data_get_inventory`, and
asserts a valid Data Agent envelope in both `structuredContent` and the JSON text block. The sample manifest contains
the `DEMO` stock bars from `2026-01-20T12:00:00Z` through `2026-01-20T12:11:00Z`, with 12 rows from source `sample`.

## Data Agent LangGraph Identity

Chunks 8 and 9 add the first deterministic LangGraph identity without LLM calls or checkpoint persistence. The Data
Agent graph owns `DataAgentState`, enforces the Data Agent MCP tool allowlist, calls `data_get_inventory` through an
MCP client wrapper, and stores the returned tool envelope plus `dataset_manifest` payload in graph state.

Reproduce the graph evidence with:

```bash
uv run pytest tests/test_langgraph_agents.py
```

The graph test uses the same test-only DuckDB-backed MCP server as the first MCP evidence test. `trader_agents` does
not import platform data/query modules or the MCP server implementation; it uses only identity metadata and an MCP
client boundary.

## Data Agent Symbol Discovery Preflight

Chunks 22A through 22G add provider-aware symbol discovery and validation to the Data Agent:

```text
data_discover_symbols
data_get_inventory
data_summarize_quality
data_ensure_loaded
data_summarize_quality
```

`data_discover_symbols` resolves provider, provider-scoped `instrument_type`, provider-scoped `bar_type`, and the
compatibility `asset_class` before any local query, quality check, load branch, or provider catalog adapter runs. Current
registered Alpaca data capabilities are `instrument_type="stock"` and `instrument_type="crypto"` with
`bar_type="trade_bar"`. A request for `provider="polygon"` while the bounded config/default provider is Alpaca returns a
Data Agent error envelope with `code="provider_not_configured"` and does not fall back to local bars or backfill.

The existing Data Agent tools also accept optional `provider`, `instrument_type`, and `bar_type`. Direct MCP callers get
the same fail-fast behavior as the LangGraph workflow: provider mismatch, unsupported instrument type, or unsupported
bar type fails before query construction or loading. Successful manifests, quality reports, and load results include
`provider_context`, `resolved_provider`, `instrument_type`, `bar_type`, and `legacy_asset_class` audit fields.

Discovery sources:

- `local`: reads distinct symbols already present in local bar tables through typed core query helpers.
- `configured`: validates against the configured `market_data.symbols` universe when a bounded trader config is present.
- `configured_source`: default Data Agent graph preflight; uses configured symbols when present, otherwise local evidence.
- `provider`: uses a policy-gated provider catalog adapter. The Alpaca adapter calls the read-only asset-listing API only
  when explicitly enabled and configured; tests use fake clients and do not make network calls.

Reproduce the symbol-discovery evidence with:

```bash
uv run pytest tests/test_data_symbol_discovery.py tests/test_alpaca_symbol_provider.py tests/test_mcp_tools.py tests/test_langgraph_agents.py tests/test_langgraph_data_workflow.py tests/test_market_data_queries.py
```

The tests prove local discovery, configured crypto canonicalization, fake provider catalog injection, missing credential
errors, direct MCP provider mismatch, mandatory graph preflight, missing-symbol blockers, provider mismatch blockers, and
no raw SQL in research/MCP layers.

## Data Agent Quality And Loading Workflow

Chunks 10 through 16 complete the deterministic Data Agent workflow:

```text
mcp_health
mcp_get_config
data_discover_symbols
data_get_inventory
data_summarize_quality
data_ensure_loaded
data_summarize_quality
```

Reproduce the Slice 3 evidence with:

```bash
uv run pytest tests/test_data_quality_service.py tests/test_data_ensure_loaded.py tests/test_mcp_data_workflow.py tests/test_langgraph_data_workflow.py tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py
```

The tests assert these envelope fields:

- `data_summarize_quality`: `ok`, `agent_owner="Data Agent"`, `side_effect="read_only"`, embedded
  `data_quality_report.report_id`, normalized `asset_class`, `symbols`, `timeframe`, `requested_window`,
  per-symbol `bar_count`, `missing_gap_count`, `expected_gap_count`, `session_gap_count`, `max_gap_seconds`, and
  report-level `complete` plus warnings for missing rows or detected gaps.
- `data_ensure_loaded`: `ok`, `agent_owner="Data Agent"`, `side_effect="local_mutating"`, explicit `mode`,
  `rows_loaded`, dry-run backfill plan fields with zero network calls/writes, permitted non-dry-run backfill runner
  evidence, sample-load evidence, and post-load `dataset_manifest` plus `data_quality_report`.
- MCP workflow evidence: every `CallToolResult.content[0].text` parses to the same JSON as `structuredContent`, and
  `isError` matches the shared `ToolEnvelope.ok` value.
- Data Agent graph evidence: ordered `called_tools`, initial manifest, initial quality report, load result, final
  quality report, accumulated warnings/errors, policy refusal when loading is not allowed, and no forbidden direct
  imports from platform data/query modules or the MCP server.

## Research Foundations And Supervisor Skeleton

Chunks 17 through 22 move the legacy research helpers and tool modules into the `trader_research` package boundary,
add typed research-domain schemas, and introduce the first deterministic Quant Research Supervisor graph skeleton.

The old `trader.research` and `trader.tools.*` import paths are compatibility shims only. Canonical implementations now
live under `trader_research`, and package-boundary tests verify that core `trader` modules do not depend on
`trader_research`, `trader_mcp`, or `trader_agents` outside those shims.

Reproduce the Slice 4 supervisor evidence with:

```bash
uv run pytest tests/test_research_contracts.py tests/test_tool_contracts.py tests/test_research.py tests/test_research_tools.py tests/test_research_domain.py tests/test_quant_research_supervisor.py tests/test_supervisor_data_handoff.py tests/test_package_boundaries.py
```

The tests assert these supervisor handoff fields and boundaries:

- `SpecialistHandoff`: `handoff_id`, producing `agent_owner`, `artifact_type`, optional `artifact_path`, structured
  `payload`, `source_request`, `provenance_refs`, structured `warnings`, structured `blockers`, and producing
  `side_effect`.
- Data Agent handoff consumption: supervisor state preserves `agent_owner="Data Agent"`, dataset manifest ID,
  data-quality report ID, requested symbols, asset class, timeframe, window, completeness, Data Agent warnings, and
  provenance from the Data Agent graph.
- Supervisor state: distinct `Quant Research Supervisor Agent` identity, bounded `research_request`, handoff ledger,
  specialist artifact slots, structured blockers, structured errors, public status, and ordered `called_tools`.
- Missing specialist evidence: absent Data, Quantitative Methods, ML, Hypothesis, Evaluation, and Adversarial artifacts are
  explicit blockers when required; ML artifacts can be represented as optional when the request does not require them.
- Boundary evidence: the supervisor does not call MCP tools, fetch raw bars, run backtests, invoke LLMs, mutate broker
  state, or import platform data/query modules. It consumes Data Agent artifact references and summaries only.

## Data Agent LLM Control Loop

Chunk 22H adds the first LLM-backed control loop, scoped narrowly to the Data Agent. The LLM does not live inside MCP
tools and does not query data sources directly. It emits one typed Data Agent action proposal at a time; a deterministic
router validates that proposal before any existing MCP tool is called.

Runtime LLM configuration is provider-neutral:

```bash
TRADER_AGENTS_LLM_PROVIDER=ollama
TRADER_AGENTS_LLM_MODEL=llama3.1
TRADER_AGENTS_LLM_BASE_URL=http://localhost:11434
TRADER_AGENTS_LLM_TIMEOUT_SECONDS=30
```

or for an OpenAI-compatible hosted gateway such as OpenRouter-style APIs:

```bash
TRADER_AGENTS_LLM_PROVIDER=openrouter
TRADER_AGENTS_LLM_MODEL=provider/model-name
TRADER_AGENTS_LLM_API_KEY=...
TRADER_AGENTS_LLM_TIMEOUT_SECONDS=30
```

If `TRADER_AGENTS_LLM_PROVIDER` or the required model configuration is missing, the LLM policy graph fails fast with a
structured `llm_not_configured` blocker and does not call MCP tools.

Allowed Data Agent LLM actions are:

- `discover_symbols`
- `inspect_inventory`
- `summarize_quality`
- `ensure_loaded`
- `retry_with_changes`
- `block`
- `finish`

The router enforces these invariants before tool execution:

- `data_discover_symbols` must run successfully before inventory, quality, or loading.
- Downstream requests cannot contradict the resolved provider, instrument type, or bar type from symbol discovery.
- `data_ensure_loaded` requires `policy.allow_data_loading=true` and an explicit bounded mode.
- The Data Agent LLM cannot call SQL, broker, strategy, backtest, supervisor, or non-Data-Agent tools.
- Graph state stores sanitized public decisions only, not raw prompts, hidden reasoning, messages, or scratchpads.

Reproduce the 22H evidence with:

```bash
uv run pytest tests/test_llm_client.py tests/test_data_agent_llm_policy.py tests/test_langgraph_agents.py tests/test_langgraph_data_workflow.py
```

The tests use fake LLM clients and fake HTTP transports. They prove OpenRouter-style and Ollama-style runtime adapter
request construction without external network calls, plus policy-graph happy path, invalid tool rejection,
missing-symbol blockers, provider-context mismatch, loading-policy refusal, loop limits, and missing-config fail-fast
behavior.

## Planned Knowledge-Backed Quantitative Methods Surface

The Quantitative Methods Agent replaces the earlier Math Coder Agent identity. Its scope is deterministic,
auditable quantitative methods rather than indicator coding alone. It owns method contracts, validation reports,
statistical inference procedures, signal diagnostics, multiple-testing controls, approved method cards, citation
validation, and optional parity-checked numerical kernels.

The Quant Methods Knowledge Base is a `trader_research` service, not a separate autonomous agent in the first release.
The runtime store is Postgres-backed: source/chunk/embedding/ingestion records live in `knowledge_*` tables, lexical
retrieval uses PostgreSQL full-text search, and dense retrieval uses pgvector. The vector index is retrieval
infrastructure, not authority. The authority is the approved source registry plus approved method cards. Later,
Evaluation and Supervisor may get read-only access to the same evidence layer.

Knowledge artifacts:

| Artifact | Purpose |
| --- | --- |
| `knowledge_source_manifest.json` or `knowledge://postgres/knowledge_source_manifest/...` | Source metadata, hash, access policy, topics, and citation. |
| `knowledge_ingestion_report.json` or `knowledge://postgres/knowledge_ingestion_report/...` | Ingestion run, parser version, chunks, warnings, and embedding model/version. |
| Postgres `knowledge_chunks` records | Chunk IDs, source IDs, locators, headings, hashes, active status, and full-text search data. |
| `knowledge_embedding_manifest.json` or `knowledge://postgres/knowledge_embedding_manifest/...` | Embedding backend/model/version, dimension, created_at, and compatibility constraints. |
| `method_card_draft.json` | Non-executable draft method summary from source evidence. |
| `method_card.json` | Approved method card with assumptions, inputs, outputs, failure modes, and locators. |
| `evidence_retrieval_report.json` | Retrieved evidence chunks for a request, query, method, and source set. |
| `evidence_chunk_dereference_report.json` | Bounded real chunk text dereferenced from retrieved chunk IDs for local downstream agent context. |
| `citation_validation_report.json` | Source ID, chunk ID, locator, method-card approval, and claim-coverage validation. |

Initial knowledge MCP tools:

| Tool | Side effect | Purpose |
| --- | --- | --- |
| `knowledge_register_source` | `local_mutating` | Register metadata, compute file hash, validate source type/path policy, and persist a source manifest. |
| `knowledge_ingest_documents` | `local_mutating` | Extract, chunk, embed with the configured provider, update Postgres full-text/pgvector indexes, and produce an ingestion report. |
| `knowledge_get_ingestion_status` | `read_only` | Fetch source/ingestion status, warnings, parser details, source type, and indexed chunk counts. |
| `knowledge_list_sources` | `read_only` | List source manifests by topic, source type, method family, or status. |
| `knowledge_search_methods` | `read_only` | Search approved method cards and optionally draft cards when policy permits. |
| `knowledge_retrieve_evidence` | `read_only` | Run hybrid full-text/pgvector retrieval with reciprocal-rank fusion and return citeable chunks plus lexical/vector/combined rank diagnostics. |
| `knowledge_get_evidence_chunks` | `read_only` | Dereference retrieved chunk IDs into bounded stored text with source metadata, locators, text hashes, and truncation flags. |
| `knowledge_create_method_card_draft` | `local_mutating` | Create a non-approved draft method card from validated source/chunk evidence refs. |
| `knowledge_publish_method_card` | `local_mutating` | Promote a draft to an approved method card with explicit local approval metadata. |
| `knowledge_validate_citations` | `read_only` | Validate source IDs, chunk IDs, locators, method-card approval, and claim coverage. |

Knowledge guardrails:

- Ingestion does not imply approval.
- Retrieved chunks do not imply method support.
- Draft method cards are not executable.
- Sophisticated statistical methods must cite approved method cards; persisted approved cards in the configured
  knowledge store can satisfy this requirement.
- Artifacts cite source IDs and locators rather than reproducing large source passages.
- Knowledge tools must not expose arbitrary filesystem access or execute code from documents.
- `knowledge_get_evidence_chunks` may return full local chunk text to trusted downstream agents, bounded by
  `max_chars_per_chunk`; final user-facing reports should cite locators and avoid reproducing large passages.
- Embedding model and chunking configuration must be versioned.
- Re-indexing should be reproducible for unchanged sources and config.
- `mcp_get_config` reports `knowledge_store_runtime`; missing Postgres config, missing embedding config, pgvector
  unavailability, and embedding dimension mismatch fail closed in tool envelopes.

Initial MCP tools:

| Tool | Side effect | Purpose |
| --- | --- | --- |
| `math_list_method_contracts` | `read_only` | List maintained indicators, transforms, statistical tests, diagnostics, and multiple-testing methods. |
| `math_validate_method_contract` | `read_only` | Validate parameters, input schema, warmup behavior, assumptions, fixture expectations, and failure modes. |

Compatibility aliases may be kept during migration:

| Alias | Canonical behavior |
| --- | --- |
| `math_list_indicator_contracts` | Calls `math_list_method_contracts` filtered to indicator/transform families. |
| `math_validate_indicator_contract` | Calls `math_validate_method_contract` filtered to indicator/transform families. |

Current and follow-on implementation tools:

| Tool | Side effect | Artifact |
| --- | --- | --- |
| `math_register_method_implementation` | `local_mutating` | Python `method_implementation_manifest.json` with entrypoint, source hash, dependency allowlist, safety profile, and approved method-card refs |
| `math_generate_python_method` | `local_mutating` | quarantined Python reference artifact requiring fixture validation before use |
| `math_run_indicator_fixtures` | `local_mutating` | `indicator_validation_report.json` for a registered Python reference implementation |
| `math_run_signal_diagnostics` | `local_mutating` | `signal_diagnostic_report.json` |
| `math_run_multiple_testing_report` | `local_mutating` | `multiple_testing_report.json` |
| `math_generate_cpp_kernel` | `local_mutating` | draft `cxx_kernel_manifest.json` from approved templates only, after a validated Python reference exists |
| `math_compile_kernel` | `local_mutating` | local build evidence for an approved deterministic kernel |
| `math_run_python_cpp_parity` | `local_mutating` | `python_cpp_parity_report.json` |
| `math_package_method_artifact` | `local_mutating` | `method_package_manifest.json` |

Python reference implementations are the first executable target. Maintained and generated implementation source files
must carry a module-level provenance docstring with `Source reference` and `Implements` sections naming the registry
method, approved method-card refs, implementation class, exact formula/algorithm, ordering, warmup behavior, and
no-lookahead boundary. Maintained source must declare an approved method-card reference; generated source must declare
the exact method-card IDs passed to the tool. `math_register_method_implementation` parses this docstring, fails closed
when it is missing or inconsistent, and records it in `method_implementation_manifest.json`. Generated Python artifacts stay quarantined until
they cite approved method cards, declare method contracts, record source hashes and dependency allowlists, and pass
fixtures. 23J/23K reuse the existing runtime contract in `trader.indicators.Indicator` and
`IndicatorObservation`; they do not create a parallel indicator-contract system. `method_implementation_manifest.json`
is the bridge between an approved method card, the maintained `math_registry` contract, a concrete Trader `Indicator`
entrypoint, the source hash, and fixture validation evidence. The C++ path is template-restricted and comes after a
validated Python reference exists. Generated or maintained kernels must declare warmup, NaN, alignment, dtype, and
lookahead policies; compile in an isolated local build directory; avoid broker, SQL, network, and live-trading access;
and pass Python/C++ parity before downstream operational use.

The first Quantitative Methods evidence should prove:

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
math_register_method_implementation
math_run_indicator_fixtures
math_generate_python_method
  -> source manifests, ingestion reports, retrieved refs, dereferenced chunk text, approved method cards, citation validation, method metadata, Python implementation manifests, quarantined generated Python, and fixture validation reports
  -> declares agent_owner = Quantitative Methods Agent
  -> records source IDs, locators, assumptions, implementation source hashes, fixture status, and failure modes
```

Stretch evidence should add signal diagnostics and multiple-testing reports that use approved method cards, record the
declared candidate family, tested parameter grid, raw p-values, adjusted p-values, accepted/rejected candidates,
warnings, and blockers.
