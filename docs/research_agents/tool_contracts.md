# Research Agent Tool Contracts

This document defines the active contract for research-agent tools. The current direction is:

```text
deterministic trader_research services
  -> MCP tools in trader_mcp
  -> LangGraph agent identities in trader_agents
```

MCP is the tool boundary. LangGraph is the agent identity and orchestration layer. Tools must produce structured
artifacts that match the owning agent's responsibilities in [agent_operating_model.md](agent_operating_model.md).
The Quant Research Supervisor Agent may coordinate specialist work, but each specialist-owned artifact keeps its own
`agent_owner`.

## Control Plane And Execution Plane

Research tooling has two separate configuration planes.

The MCP server is the control plane. It owns only:

- process startup and stdio transport
- server identity, registered tool names, descriptions, and static metadata
- artifact root and server-local policy flags
- capability gates such as `TRADER_MCP_ALLOW_DATA_LOADING`

The tool/runtime layer is the execution plane. It owns only:

- typed tool requests and deterministic service contracts
- injected dependencies such as event stores, catalog providers, runners, and policies
- trader runtime YAML used to build execution dependencies
- runtime dotenv values used by that YAML, such as Postgres and Alpaca credentials

These planes must remain one-way and lazy:

- The MCP server must be able to start, list tools, and answer `mcp_health` / `mcp_get_config` without a valid trader
  YAML, broker credentials, database connection, or backtest runtime.
- A broken execution-plane config must fail inside the affected tool call as a structured envelope. It must not prevent
  MCP server startup or tool registration.
- Execution services in `trader_research` must not read `local.env`, inspect MCP transport details, depend on MCP client
  identity, or branch on which process called them.
- MCP adapters may translate JSON-native tool inputs into typed requests and inject dependencies, but deterministic
  services must know only their request objects, dependency interfaces, and explicit runtime policy.
- Runtime `.env` files are for execution-plane YAML expansion only. They are loaded lazily before building the trader
  config for a tool, never as a prerequisite for MCP server startup.
- Duplicating values across env files is acceptable when those values serve different planes. Avoid "DRY" env loading
  that couples MCP process startup to execution runtime secrets, broker settings, database settings, or script defaults.

## Envelope

Every MCP tool returns a stable envelope:

```json
{
  "ok": true,
  "command": "data_get_inventory",
  "agent_owner": "Data Agent",
  "side_effect": "read_only",
  "schema_version": "1",
  "generated_at": "2026-05-26T12:00:00+00:00",
  "data": {},
  "artifacts": {},
  "warnings": [],
  "errors": []
}
```

Fields:

- `ok`: command success.
- `command`: stable MCP tool identifier.
- `agent_owner`: agent that owns the artifact and decision boundary.
- `side_effect`: declared side-effect class.
- `schema_version`: envelope schema version.
- `generated_at`: UTC timestamp.
- `data`: machine-readable result.
- `artifacts`: generated or consumed artifact references.
- `warnings`: non-fatal issues.
- `errors`: structured fatal errors when `ok=false`.

## Side Effects

| Class | Meaning | Allowed examples |
| --- | --- | --- |
| `read_only` | Reads config, event-store data, local artifacts, or broker/operator snapshots without writing. | Inventory, data quality summary, result lookup. |
| `local_mutating` | Writes local artifacts or bounded research records; never submits broker orders. | Dataset manifest, quality report, sample load, backtest artifact, robustness report. |
| `broker_read` | Reads broker state through operator-owned surfaces. | Future read-only operator context tools. |
| `broker_mutating` | Mutates broker state. | Not allowed for research-agent MCP tools. |

No research-agent tool may start `TraderService`, submit orders, clear halt state, reconcile broker state, run raw SQL,
or bypass core platform validation.

## Initial Data Agent Tools

| Tool | Side Effect | Primary artifact |
| --- | --- | --- |
| `data_get_inventory` | `read_only` | `dataset_manifest.json` payload or reference |
| `data_summarize_quality` | `read_only` | `data_quality_report.json` |
| `data_ensure_loaded` | `local_mutating` | load/backfill evidence plus dataset manifest update |

These tools are implemented first because the Data Agent owns the ingredients that later research agents consume.

## Planned Agent Tools

| Tool | Owning agent | Primary artifact |
| --- | --- | --- |
| `knowledge_register_source` | Quantitative Methods Agent | `knowledge_source_manifest.json` or `knowledge://postgres/knowledge_source_manifest/...` |
| `knowledge_ingest_documents` | Quantitative Methods Agent | `knowledge_ingestion_report.json`, Postgres `knowledge_chunks`, `knowledge_embedding_manifest.json` or `knowledge://postgres/...` refs |
| `knowledge_get_ingestion_status` | Quantitative Methods Agent | source and ingestion status summary |
| `knowledge_list_sources` | Quantitative Methods Agent | source manifest listing |
| `knowledge_search_methods` | Quantitative Methods Agent | approved method-card search result |
| `knowledge_retrieve_evidence` | Quantitative Methods Agent | `evidence_retrieval_report.json` with lexical/vector/combined rank diagnostics |
| `knowledge_get_evidence_chunks` | Quantitative Methods Agent | `evidence_chunk_dereference_report.json` with bounded stored chunk text |
| `knowledge_create_method_card_draft` | Quantitative Methods Agent | `method_card_draft.json` |
| `knowledge_publish_method_card` | Quantitative Methods Agent | approved `method_card.json` |
| `knowledge_validate_citations` | Quantitative Methods Agent | `citation_validation_report.json` |
| `math_list_method_contracts` | Quantitative Methods Agent | method contract catalog for indicators, transforms, statistical tests, diagnostics, and multiple-testing procedures |
| `math_validate_method_contract` | Quantitative Methods Agent | method contract validation report |
| `math_register_method_implementation` | Quantitative Methods Agent | `method_implementation_manifest.json` |
| `math_run_indicator_fixtures` | Quantitative Methods Agent | `indicator_validation_report.json` |
| `math_run_signal_fixtures` | Quantitative Methods Agent | `signal_implementation_validation_report.json` |
| `math_generate_python_method` | Quantitative Methods Agent | quarantined generated Python source plus registration and fixture-validation results |
| `math_run_signal_diagnostics` | Quantitative Methods Agent | `signal_diagnostic_report.json` |
| `math_run_multiple_testing_report` | Quantitative Methods Agent | `multiple_testing_report.json` |
| `math_generate_cpp_kernel` | Quantitative Methods Agent | draft `cxx_kernel_manifest.json` from an approved template |
| `math_compile_kernel` | Quantitative Methods Agent | local compiled-kernel build evidence |
| `math_run_python_cpp_parity` | Quantitative Methods Agent | `python_cpp_parity_report.json` |
| `math_package_method_artifact` | Quantitative Methods Agent | `method_package_manifest.json` |
| `ml_create_feature_manifest` | ML Agent | `feature_dataset_manifest.json` |
| `ml_summarize_model_artifact` | ML Agent | model card, prediction, or drift artifact summary |
| `hypothesis_create_card` | Hypothesis Agent | `hypothesis_card.json` |
| `research_create_plan` | Quant Research Supervisor Agent | experiment plan |
| `research_list_strategy_templates` | Quant Research Supervisor Agent | strategy template catalog |
| `research_validate_strategy_candidate` | Quant Research Supervisor Agent | validation report |
| `research_run_backtest` | Quant Research Supervisor Agent | backtest artifact bundle |
| `research_get_backtest_results` | Quant Research Supervisor Agent | result summary |
| `evaluation_generate_report` | Evaluation Agent | `evaluation_report.json` |
| `adversarial_run_robustness` | Adversarial Agent | `robustness_report.json` |
| `research_analyze_return_attribution` | Quant Research Supervisor Agent | attribution report |
| `research_generate_recommendation` | Quant Research Supervisor Agent | recommendation report |
| `research_run_experiment` | Quant Research Supervisor Agent | composed experiment output |

Compatibility aliases may be kept while the older Math Coder naming is retired:

| Alias | Canonical tool |
| --- | --- |
| `math_list_indicator_contracts` | `math_list_method_contracts` filtered to indicator and transform families |
| `math_validate_indicator_contract` | `math_validate_method_contract` filtered to indicator and transform families |

The `math_*` namespace is a tool namespace, not a claim that the agent is limited to coding indicators. The owning
identity is Quantitative Methods Agent.

Knowledge-base rules:

- Hybrid retrieval combines lexical and vector indexes; those indexes are retrieval infrastructure, not authority.
- Runtime MCP knowledge storage uses Postgres by default. PostgreSQL full-text search handles lexical retrieval and
  pgvector handles dense retrieval; tests may inject a JSON compatibility store.
- The authority is the approved source registry plus approved method cards.
- Evidence retrieval should return citeable chunks with source IDs, locators, source approval status, and lexical/vector
  rank metadata rather than opaque context blobs.
- Evidence dereferencing is explicit: agents call `knowledge_get_evidence_chunks` with retrieved `chunk_id` values to
  receive real stored chunk text, source metadata, locators, text hashes, `hash_verified`, text length metadata, and
  `text_truncated`.
- Ingestion does not imply approval; `method_card_draft.json` is not executable.
- Sophisticated statistical-test and multiple-testing contracts must cite approved method cards and pass
  `knowledge_validate_citations`. Seeded cards and persisted approved cards in the configured `KnowledgeStore` are both
  visible to citation and math validation.
- Knowledge tools must not expose arbitrary filesystem access, execute code from documents, or reproduce large source
  passages in artifacts.

`knowledge_get_evidence_chunks` contract:

- Request: `chunk_ids: list[str]` required, maximum 25; optional `source_id`; `include_text: bool = true`;
  `max_chars_per_chunk: int = 4000`, bounded to 1-20000.
- Success data: `evidence_chunk_dereference_report`, top-level `chunks`, `chunk_count`, and `missing_chunk_ids`.
- Each chunk includes `chunk_id`, `source_id`, source title/type/status, `approved_source`, `locator`, `topics`,
  `method_families`, `text_hash`, `hash_verified`, `text_char_count`, `text_word_count`, `text_truncated`, and `text`
  when requested.
- Missing chunk IDs or source mismatches fail closed with `code="chunk_dereference_error"` and structured
  `missing_chunk_ids` / `source_mismatch_chunk_ids`; no embedding vectors are returned.

`knowledge_create_method_card_draft` contract:

- Request: `method_id`, `title`, `family`, non-empty `assumptions`, `inputs`, `outputs`, `failure_modes`, and
  `evidence_refs`; optional `version`.
- Evidence refs must include at least one source or chunk reference and pass citation validation with
  `require_approved_method_card=false`.
- Success data contains `method_card_draft`; draft cards are persisted but excluded from default approved method search.

`knowledge_publish_method_card` contract:

- Request: `draft_method_card_id`, `approved_method_card_id`, `approved_by`, `approval_note`, and `approve=true`.
- Publishing preserves the draft and creates a separate approved `method_card` with approval provenance.
- Re-publishing the same approved card is idempotent only when the persisted content matches; conflicting content fails
  closed.

`math_register_method_implementation` contract:

- Request: `method_id`, non-empty `method_card_ids`, optional `method_contract`, optional `entrypoint`, optional
  `source_path`, optional `class_name`, optional `constructor_kwargs`, optional `implementation_kind`
  (`maintained` or `generated`), optional `dependency_allowlist`, and optional `expected_source_hash`.
- Runtime contract: the method contract declares the Trader runtime class. Current supported values are
  `trader.indicators.Indicator` and `trader.signals.Signal`. The entrypoint must resolve to a subclass of the declared
  runtime contract; this reuses Trader package contracts instead of creating a parallel implementation schema.
- Source provenance contract: the implementation source file must have a module-level docstring with `Source reference`
  and `Implements` sections. The docstring must name the registry method, at least one approved method-card reference,
  implementation class, Trader runtime contract, implemented formula/algorithm/action rule, input ordering, warmup
  behavior, output ordering for series methods, and no-lookahead boundary. For generated quarantined implementations,
  the docstring must name the exact method-card IDs passed to the tool.
- Validation: method ID must exist in `math_registry`; approved method-card refs must match the method; source hash must
  match when supplied; provenance docstring checks must pass; imports and calls must pass the static safety allowlist;
  generated implementations must resolve from their artifact source path.
- Success data contains `method_implementation_manifest` with method ID, language, implementation kind, entrypoint,
  class name, source path, source hash, constructor kwargs, approved method-card refs, method contract,
  source provenance, `runtime_contract`, dependency allowlist, safety profile, and `status="registered"`.

`math_run_indicator_fixtures` contract:

- Request: either `implementation_id` for a persisted manifest or `implementation_manifest` inline; optional `fixtures`.
- The manifest must have `runtime_contract="trader.indicators.Indicator"`; signal manifests fail closed with
  `code="invalid_runtime_contract"`.
- Fixture inputs use ascending close values. The service builds latest-first `Bar` sequences, calls
  `Indicator.compute_series(bars)`, expands warmup nulls, compares expected values, and runs prefix checks for
  no-lookahead behavior.
- Before fixtures run, the service revalidates the manifest, approved method cards, source hash, entrypoint, and static
  safety checks.
- Success data contains an updated `method_implementation_manifest` with `status="validated"` and an
  `indicator_validation_report` with validation ID, implementation ID, method ID, entrypoint, source hash,
  fixture results, warnings, and blockers. Fixture mismatches return `ok=false` and leave the manifest blocked.

`math_run_signal_fixtures` contract:

- Request: either `implementation_id` for a persisted manifest or `implementation_manifest` inline; optional `fixtures`.
- The manifest must have `runtime_contract="trader.signals.Signal"`; indicator manifests fail closed with
  `code="invalid_runtime_contract"`.
- Fixture inputs use ascending close values. The service builds latest-first `Bar` sequences and calls
  `Signal.compute(bars) -> float`.
- Fixture payloads use `expected` for the scalar output and may use `expected_prefix` for no-lookahead/warmup checks.
  An `expected_prefix` value of `null` means the prefix should raise warmup `ValueError`; a numeric value must match the
  scalar output for that prefix.
- Before fixtures run, the service revalidates the manifest, approved method cards, source hash, entrypoint, static
  safety checks, runtime subclass, and provenance docstring.
- Success data contains an updated `method_implementation_manifest` with `status="validated"` and a
  `signal_implementation_validation_report` with validation ID, implementation ID, method ID, entrypoint, source hash,
  scalar fixture results, prefix results, warnings, and blockers. Fixture mismatches return `ok=false` and leave the
  manifest blocked.

`math_generate_python_method` contract:

- Request: `method_id`, non-empty `method_card_ids`, `method_contract`, and optional `fixtures`.
- MCP calls the configured provider-neutral LLM client and requires JSON with `class_name` and `source_code`.
- The generation prompt requires `source_code` to start with the same module-level provenance docstring enforced by
  `math_register_method_implementation`.
- Generated code is written only under `artifacts/research/method_implementations/quarantine/`; it is never written to
  `src/` or imported as a maintained package.
- Static safety checks reject filesystem access, network/process/SQL/broker imports, dynamic imports, `eval`, `exec`,
  `open`, global/nonlocal mutation, and dependencies outside the allowlist.
- Passing generated drafts immediately run through `math_register_method_implementation` and
  the fixture runner selected by `runtime_contract`: `math_run_indicator_fixtures` for Indicator methods and
  `math_run_signal_fixtures` for Signal methods. Success data reports the generated source path, registration result,
  fixture-validation result, and `status="validated"`; failures remain quarantined with `status="blocked"`.

## LangGraph Use

Each LangGraph agent has its own identity, state schema, role policy, tool allowlist, and required output artifact.
Agents call MCP tools through an MCP client wrapper. They must not call platform internals directly when an MCP tool
exists.

Minimal allowlists:

| Agent | Allowed initial tools |
| --- | --- |
| Data Agent | `data_get_inventory`, `data_summarize_quality`, `data_ensure_loaded`, read-only health/config |
| Quant Research Supervisor Agent | Specialist artifact reads, supervisor handoff tools, `research_*` tools |
| Quantitative Methods Agent | `knowledge_*` retrieval/ingestion/citation tools, `math_list_method_contracts`, `math_validate_method_contract`, later fixture, diagnostic, multiple-testing, kernel, parity, and method-packaging tools |
| ML Agent | `ml_create_feature_manifest`, `ml_summarize_model_artifact` |
| Hypothesis Agent | Ingredient artifact reads, `hypothesis_create_card` |
| Evaluation Agent | Data/backtest artifact reads, `evaluation_generate_report` |
| Adversarial Agent | Baseline artifact reads, `adversarial_run_robustness` |

LangGraph state may store artifact references, status, public messages, and structured decisions. It must not persist
hidden reasoning or raw LLM scratchpads as product records.
