# Research Agent Workflows

This document describes the active research-agent workflow model. The current implementation direction is incremental:

```text
MCP tool evidence
  -> Data Agent tool and identity
  -> Quant Research Supervisor identity
  -> specialist agent tools and identities
  -> supervised research execution
  -> critique, robustness, and recommendation synthesis
```

The workflow is deliberately outside the live trading hot path. Research agents may read core platform artifacts and
operator context, but they must not start trading, clear halt state, reconcile broker state, submit orders, or run raw
SQL.

For agent responsibilities and owned artifacts, see [agent_operating_model.md](agent_operating_model.md). For envelope
and tool boundary details, see [tool_contracts.md](tool_contracts.md).

## Workflow Rule

The Quant Research Supervisor Agent coordinates the research loop. It does not replace specialist agents. Every slice
that adds a specialist capability must prove two things:

- the deterministic MCP tool can produce the specialist-owned artifact
- the specialist LangGraph identity can use its allowed tools and hand the artifact back to the supervisor

The supervisor may consume specialist artifacts and make orchestration decisions, but it must not fabricate Data,
Quantitative Methods, ML, Hypothesis, Evaluation, or Adversarial artifacts.

## Slice 1: First MCP Tool Evidence

Goal: prove the MCP server and a real Data Agent tool before broader research tooling exists.

Expected flow:

```text
MCP server starts
  -> client lists tools
  -> client calls data_get_inventory
  -> client receives a ToolEnvelope with agent_owner = Data Agent
```

Evidence to record in [mcp_trading_research_tools.md](mcp_trading_research_tools.md):

- command or test used to start/list tools
- request payload
- returned envelope
- warnings or limitations

## Slice 2: Data Agent LangGraph Identity

Goal: prove that the Data Agent has its own LangGraph identity and uses MCP tools to perform its purpose.

Expected flow:

```text
Data Agent graph starts
  -> state includes Data Agent identity and tool allowlist
  -> graph calls data_get_inventory through MCP client
  -> graph returns dataset manifest payload or artifact reference
```

The graph must not call core platform internals directly when an MCP tool exists.

## Slice 3: Data Agent Workflow

Goal: produce trustworthy, bounded, versioned market-data ingredients.

Expected flow:

```text
data_get_inventory
  -> data_summarize_quality
  -> data_ensure_loaded, only when policy permits
  -> data_summarize_quality
```

Owned artifacts:

- `dataset_manifest.json`
- `data_quality_report.json`
- load/backfill evidence envelope

Policy:

- `plan` and read-only inventory are safe defaults.
- sample loading is local-mutating and explicit.
- backfill is local-mutating and must be bounded by symbols, asset class, timeframe, and window.
- incomplete data must produce warnings and downstream Evaluation blockers.

## Slice 3A: Data Agent Symbol Discovery

Goal: let the Data Agent discover and validate provider-scoped symbols, instrument types, and bar types before a bounded
inventory, quality, or loading request is formed.

Expected flow:

```text
data_discover_symbols
  -> configured provider validation
  -> provider-scoped instrument/bar type validation
  -> exact symbol existence status or bounded catalog search results
  -> fail fast on provider mismatch or missing requested symbols
  -> selected symbols feed data_get_inventory, data_summarize_quality, and data_ensure_loaded
```

Owned artifact:

- `symbol_discovery_report.json`

The tool must support two related use cases:

- exploratory discovery: find available provider-scoped instruments by query, source, provider, instrument type, and bar type
- exact validation: confirm that requested symbols exist before downstream Data Agent workflows use them

The validation path should report missing symbols as structured data, not as hidden tool failure. A request can therefore
complete successfully while returning `all_requested_symbols_exist=false` and `missing_symbols=[...]`. Downstream Data
Agent graphs may treat that report as a blocker before calling inventory, quality, or ensure-loaded tools.

In composed Data Agent workflows, symbol discovery is mandatory preflight. The graph should call `data_discover_symbols`
against the configured source before it creates or calls inventory, quality, or loading requests. If the requested
symbols are not available from that configured source, the graph must stop with a structured blocker and must not query
the data source.

Implementation order:

- first add the shared provider context and provider-aware validation to existing Data Agent tools
- then add deterministic local/configured symbol discovery
- then register the MCP tool and wire the Data Agent graph preflight through MCP
- then add explicit-policy provider catalog adapters such as Alpaca asset lookup

Provider requests are validated in the same preflight. If the current config resolves to Alpaca and the request asks for
Polygon, the graph must stop with a structured provider blocker, such as `provider_not_configured`, before any local
inventory, quality, loading, or backfill path is attempted.

The existing Data Agent tools must also become provider-aware. `data_get_inventory`, `data_summarize_quality`, and
`data_ensure_loaded` should accept the resolved provider context and independently reject provider mismatches, so direct
MCP callers receive the same fail-fast behavior as agent workflows. `source` remains a local bar-source filter; provider
selection is a separate field resolved through configured provider adapters.

Instrument and bar semantics are provider-scoped. Current `stocks` and `crypto` labels are compatibility labels for the
existing Alpaca-backed bar tables, not universal assumptions. Data Agent tools should resolve provider, instrument type,
and bar type together before creating local queries or loading requests.

Policy:

- local symbol discovery is read-only and allowed by default
- configured-universe discovery is read-only when a bounded trader config path is present
- configured-source validation is the default for Data Agent preflight
- concrete requested providers must match the configured provider
- requested instrument types and bar types must be supported by the resolved provider
- provider-catalog discovery is read-only but requires explicit network/provider policy
- existing inventory, quality, and loading tools must validate provider context before querying or loading
- provider discovery must not use broker order APIs or imply that historical bars are already loaded

Implemented evidence:

- `tests/test_data_symbol_discovery.py` covers provider context resolution, existing-tool provider mismatch, local
  discovery, configured crypto canonicalization, and fake provider catalog injection.
- `tests/test_alpaca_symbol_provider.py` covers the policy-gated Alpaca asset-listing adapter with a fake client and
  missing-credentials failure.
- `tests/test_langgraph_data_workflow.py` covers mandatory preflight ordering and blockers for missing symbols or
  provider mismatch before inventory/quality/loading calls.

## Slice 4: Quant Research Supervisor Skeleton

Goal: create the Quant Research Supervisor identity before adding broad quant tools, so future work has a clear
orchestrator and handoff boundary.

Expected flow:

```text
Quant Research Supervisor graph starts
  -> state includes supervisor identity and specialist handoff slots
  -> graph consumes Data Agent artifact references
  -> graph records missing specialist artifacts as explicit blockers
```

Owned artifacts:

- supervisor state
- research request decomposition
- handoff ledger

The supervisor must not fetch data directly, invent missing specialist evidence, or run backtests before the required
artifact contracts exist.

## Slice 4A: Data Agent LLM Control Loop

Goal: power the now-complete Data Agent with a real LLM-backed control loop while keeping Data Agent tools
deterministic.

Expected flow:

```text
natural-language bounded data request
  -> provider-neutral LLM client selected from runtime configuration
  -> Data Agent LLM policy node emits one typed action proposal
  -> deterministic router validates provider context, mandatory discovery, allowlist, side-effect policy, and loop budget
  -> graph calls existing Data Agent MCP tools, blocks early, or finishes
```

LLM provider policy:

- the Data Agent policy node can use runtime-configured hosted gateways such as OpenRouter-style APIs or local backends
  such as Ollama
- external model providers live behind `trader_agents.llm_client`; they must not leak into Data Agent MCP tool schemas
- missing or unsupported LLM configuration must fail fast with a structured blocker before any MCP tool call
- tests should use fake LLM clients/transports and must not call external model providers

Guardrails:

- the LLM may only emit typed actions: `discover_symbols`, `inspect_inventory`, `summarize_quality`, `ensure_loaded`,
  `retry_with_changes`, `block`, or `finish`
- `data_discover_symbols` remains mandatory before inventory, quality, or loading
- downstream tool calls must match the resolved provider, instrument type, and bar type from discovery
- `data_ensure_loaded` remains policy-gated and bounded
- the Data Agent LLM cannot call SQL, broker, strategy, backtest, supervisor, or non-Data-Agent tools
- graph state may retain sanitized public decisions, but not raw prompts, hidden reasoning, messages, or scratchpads

Implemented evidence:

- `tests/test_llm_client.py` covers missing config, fake LLM responses, OpenAI-compatible/OpenRouter-style request
  construction, and Ollama request construction with fake transports.
- `tests/test_data_agent_llm_policy.py` covers the policy graph happy path, invalid tool rejection, missing-symbol
  blockers, provider-context mismatch, loading-policy refusal, loop limits, missing LLM config, and no raw prompt state.

## Slice 5: Knowledge-Backed Quantitative Methods MCP Tool Creation

Goal: define and prove the Quant Methods Knowledge Base plus the first deterministic Quantitative Methods tool surface
before building its graph.

Expected flow:

```text
source document or fixture reference
  -> knowledge_register_source
  -> knowledge_ingest_documents
  -> knowledge_get_ingestion_status
  -> knowledge_search_methods
  -> knowledge_retrieve_evidence
  -> knowledge_validate_citations
  -> math_list_method_contracts
  -> math_validate_method_contract
```

Owned artifacts:

- `knowledge_source_manifest.json`
- `knowledge_ingestion_report.json`
- `knowledge_chunk_manifest.json`
- `knowledge_embedding_manifest.json`
- `method_card_draft.json`
- `method_card.json`
- `evidence_retrieval_report.json`
- `citation_validation_report.json`
- `indicator_contract.json`
- `statistical_test_contract.json`
- `indicator_validation_report.json`
- `signal_diagnostic_report.json`
- `multiple_testing_report.json`
- optional `cxx_kernel_manifest.json`
- optional `python_cpp_parity_report.json`
- `method_package_manifest.json`

Evidence:

- MCP registers and ingests bounded local Markdown/text/PDF sources without arbitrary filesystem access.
- The vector index is retrieval infrastructure; approved source manifests and method cards are the authority.
- Draft method cards are not executable by method-contract tools.
- Citation validation fails closed for unknown source IDs, invalid locators, unapproved method cards, or unsupported
  claims.
- MCP returns maintained method contracts without importing arbitrary code.
- Validation fails closed for unsupported methods or parameter shapes.
- Fixture evidence records warmup behavior, NaN policy, output schema, alignment, no-lookahead metadata, and failure
  modes.
- Signal diagnostics and multiple-testing reports record candidate family size, tested parameter grid, raw p-values,
  adjusted p-values, warnings, and blockers before any winning configuration is promoted.

## Slice 6: Knowledge-Aware Quantitative Methods Agent Identity

Goal: create the Quantitative Methods LangGraph identity after the first knowledge and method MCP tools exist.

Expected flow:

```text
Quantitative Methods graph starts
  -> graph calls allowed knowledge_* and math_* MCP tools
  -> graph blocks unsupported or uncited sophisticated methods
  -> graph returns method artifact refs plus retrieval/citation refs
  -> supervisor records the handoff
```

The Quantitative Methods Agent cannot fetch market data directly, create hypotheses, train ML models, run backtests, or
make research verdicts.

## Slice 7: ML MCP Tool Creation

Goal: define model-artifact and feature-artifact contracts before any ML graph tries to plan with them.

Expected flow:

```text
dataset manifest + data-quality report + deterministic method artifacts
  -> ml_create_feature_manifest
  -> ml_summarize_model_artifact
```

Owned artifacts:

- `feature_dataset_manifest.json`
- `model_card.json`
- `prediction_artifact.json`, when predictions exist
- `drift_report.json`, when drift evidence exists

The first implementation can be registry/summary oriented. Training can remain out of scope until model artifact
contracts are stable.

## Slice 8: ML Agent Identity

Goal: create the ML LangGraph identity after ML artifact tools exist.

Expected flow:

```text
ML graph starts
  -> graph calls allowed ML MCP tools
  -> graph returns feature/model/prediction artifact references
  -> supervisor records the handoff
```

The ML Agent cannot produce final trading recommendations.

## Slice 9: Hypothesis MCP Tool Creation

Goal: create the first Hypothesis Agent tool after Data, Quantitative Methods, and optional ML ingredient contracts are
explicit.

Expected flow:

```text
available dataset + indicator/model ingredients
  -> hypothesis_create_card
  -> structured hypothesis_card.json
```

Owned artifacts:

- `hypothesis_card.json`

The tool must require a testable mechanism, data requirements, strategy family or template intent, and falsification
criteria.

## Slice 10: Hypothesis Agent Identity

Goal: create the Hypothesis Agent graph and handoff contract.

Expected flow:

```text
Hypothesis graph starts
  -> graph reads available ingredient artifact references
  -> graph calls hypothesis_create_card
  -> graph returns hypothesis cards to the supervisor
```

The Hypothesis Agent cannot run backtests or decide whether a hypothesis passed.

## Slice 11: Quant Research Strategy Tools

Goal: add Quant Research MCP tools for maintained strategy discovery and validation after the supervisor and specialist
artifact contracts exist.

Expected flow:

```text
hypothesis_card.json + available ingredients
  -> research_list_strategy_templates
  -> research_validate_strategy_candidate
```

Owned artifacts:

- strategy template catalog
- strategy validation report
- experiment-plan draft

Unsupported strategy families must fail closed.

## Slice 12: Quant Research Backtest Tools

Goal: add backtest execution and result lookup as MCP tools before synthesis.

Expected flow:

```text
dataset manifest + data-quality report + validated strategy
  -> research_run_backtest
  -> research_get_backtest_results
```

Owned artifacts:

- backtest artifact bundle
- result summary
- comparison-ready result reference

## Slice 13: Evaluation MCP Tool and Agent Identity

Goal: create skeptical research critique as a separate tool and graph.

Expected flow:

```text
backtest artifacts + data-quality report + hypothesis_card.json
  -> evaluation_generate_report
  -> Evaluation Agent graph reviews evaluation output
  -> supervisor records blockers and caveats
```

Owned artifacts:

- `evaluation_report.json`

The Evaluation Agent can critique evidence but cannot invent new strategy ideas or mutate data.

## Slice 14: Adversarial MCP Tool and Agent Identity

Goal: create robustness testing as a separate tool and graph.

Expected flow:

```text
baseline backtest artifacts
  -> adversarial_run_robustness
  -> Adversarial Agent graph reviews robustness output
  -> supervisor records stress failures
```

Owned artifacts:

- `robustness_report.json`

The Adversarial Agent can call robustness tools against supplied baseline artifacts, but it cannot recommend promotion.

## Slice 15: Quant Research Recommendation and Synthesis

Goal: create recommendation tooling and extend the Quant Research Supervisor graph to synthesize specialist artifacts.

Expected flow:

```text
data artifacts
  + indicator/model artifacts
  + hypothesis_card.json
  + backtest results
  + attribution
  + evaluation_report.json
  + robustness_report.json
  -> research_generate_recommendation
  -> supervisor records final recommendation state
```

Owned artifacts:

- recommendation report
- promotion-readiness assessment

Promotion readiness is blocked unless required Evaluation and Adversarial artifacts are present or the recommendation
explicitly states why they are absent.

## Slice 16: Supervised Experiment Runner

Goal: expose a composed runner only after the underlying agent-owned tools and handoffs are proven.

Expected flow:

```text
research request
  -> supervisor decomposes work
  -> specialist agents produce artifacts
  -> quant tools run validated experiments
  -> critique and robustness complete
  -> supervisor synthesizes recommendation
```

The runner composes prior capabilities. It is not the first proof of MCP, LangGraph, or any specialist identity.

## Documentation Rule

Documentation is part of the implementation workflow. Each tool or graph slice must update:

- this workflow document when behavior changes
- [agent_operating_model.md](agent_operating_model.md) when agent boundaries change
- [tool_contracts.md](tool_contracts.md) when tool shape or side effects change
- [mcp_trading_research_tools.md](mcp_trading_research_tools.md) with runnable evidence
