# MCP Trading Research Tools Implementation Plan

## Overview

This plan translates `docs/research_agents/agents.md` and `docs/research_agents/history/codex_trading_research_framework_brief.md` into an implementation backlog for a clean research-tool, MCP, and LangGraph agent layer. The goal is to expose deterministic, artifact-producing tools to Codex, ChatGPT, Claude, or other MCP clients while giving each research agent a distinct identity, tool allowlist, state model, and artifact contract. This must not rebuild the older over-scoped agent system or expand the core `trader` package beyond its runtime platform responsibilities.

The first useful product surface follows the Data Agent contract:

```text
Bounded data request
  -> dataset manifest
  -> data-quality report
  -> explicit load/backfill result, if permitted
  -> reproducible MCP evidence
```

The current strategy research toolchain is implementation-first:

```text
handwritten, maintained, AI-produced, or method-informed source
  -> content-addressed implementation registration and validation
  -> immutable strategy and ordered risk specifications
  -> Data Agent-scoped backtest specification
  -> canonical Postgres backtest run
  -> optimisation, Evaluation, and Adversarial evidence
```

This toolchain is the shortest path to meaningful MCP value. Agent graphs, generated hypotheses, ML artifacts,
adversarial robustness, recommendations, and compiled-kernel acceleration should compose this deterministic toolchain
after it exists; they should not block it.

Risk-aware portfolio construction now uses registered implementations and immutable specifications. Method cards and
maintained catalogs may inform producers, but they are not execution dependencies. The current composition is:

```text
validated strategy implementation
  -> validated risk-manager implementation(s)
  -> strategy and ordered risk-stack specifications
  -> Data Agent-scoped backtest specification
  -> canonical multi-asset backtest run
  -> holdout Evaluation and independent Adversarial review
```

Later slices add the Quant Research Supervisor and each specialist agent carefully: first a deterministic MCP tool that
produces the agent-owned artifact, then the LangGraph identity that is allowed to use that tool, then a supervisor
handoff. MCP should be the deterministic tool boundary, not the agent identity layer. LangGraph should provide agent
identity and orchestration: each agent gets its own graph or subgraph, state schema, prompt/role policy, MCP tool
allowlist, and output artifact contract. The Quant Research Supervisor graph coordinates the loop, but it must not
forge or bypass specialist outputs. The research implementation should remain normal Python services with typed
inputs/outputs; the MCP server should validate requests, call those services, and return stable JSON envelopes;
LangGraph agents should consume those MCP tools rather than bypassing them.

The package boundary is part of the design:

```text
trader
  Core platform only: market data, brokers, event store, strategies/risk interfaces,
  event-driven backtesting, live trading runtime, metrics, and operational primitives.

trader_standard
  Optional maintained implementations that quant researchers can use with trader:
  indicators, signal generators, common strategies, and simple risk managers.

trader_research
  Research experiment orchestration, research domain models, tool contracts,
  data-quality/tool wrappers, implementation/specification validation, robustness,
  attribution, reports, and agent-owned research artifact handling.

trader_mcp
  MCP server and MCP-specific adapters over trader_research services.

trader_agents
  LangGraph agent identities, state schemas, tool allowlists, and graph wiring
  over MCP tools. No direct platform mutation and no direct SQL access.
```

## Current Repository Signals

- `docs/research_agents/agents.md` defines a supervisor hierarchy. The current Supervisor tools register and validate
  implementation versions, create immutable strategy/risk/backtest specifications, run canonical DB-backed backtests,
  orchestrate provider-neutral optimisation, and execute Adversarial-requested variants. Candidate-era execution tools
  are removed. Data Agent and Quantitative Methods artifacts remain specialist-owned; Evaluation and Adversarial own
  their independent reports; ML, Hypothesis, broader robustness, recommendation, and compiled-kernel acceleration
  remain follow-on layers.
- `src/trader/research.py` currently contains useful research helper behavior, but it is misplaced in the core platform package and should be moved or re-created under `src/trader_research/`.
- `src/trader/tools/` currently contains useful tool-facing behavior, but it is also misplaced in the core platform package and should be moved or re-created under `src/trader_research/` or `src/trader_mcp/` depending on whether the code is research-domain logic or MCP transport logic.
- Existing backtest entry points are centered on `trader.backtest.BacktestRunner`, `BacktestSpec`, `BacktestAssumptions`, and export helpers.
- Existing strategy and risk contracts already live in the core platform. Research tools should generate artifacts that
  implement those interfaces for backtesting, not invent an agent-only runtime.
- Existing persistence uses `EventStore` methods such as `upsert_experiment`, `record_experiment_run_start`, `record_experiment_run_finish`, and `list_experiment_runs`.
- Existing docs already define JSON envelopes and side-effect classes in `docs/research_agents/tool_contracts.md`.
- The older scratch directories have been removed. Start with tracked source files only.

## Design Guardrails

- Agents are separated by the artifacts they own, not by broad domain labels.
- Agent identity is implemented with LangGraph, not with ad hoc prompt routing. Each agent graph has its own state, role policy, tool allowlist, and required output artifact.
- Keep platform behavior deterministic.
- Keep `src/trader/` free of research-tool, agent-tool, and MCP schemas/definitions. The core package may expose platform primitives that research packages import, but it should not import research packages.
- Keep `src/trader_standard/` focused on reusable implementations of platform interfaces. It should not own experiment orchestration, reports, MCP schemas, or agent tooling.
- Do not expose SQL tools through MCP.
- Do not expose broker-mutating or live-trading tools.
- Do not persist raw LLM messages, hidden reasoning, or every tool-call payload.
- Real LLM-backed control is needed at two levels: inside mature specialist agents for bounded domain decisions, and
  inside the Quant Research Supervisor for cross-agent orchestration. LLM-backed control belongs in LangGraph
  control-policy nodes, not in MCP tools. A specialist agent may use an LLM to choose among its own validated MCP tool
  allowlist after its deterministic tool surface is complete. The Quant Research Supervisor uses an LLM to assess
  specialist artifacts, decide which agent/tool should run next, block, retry, or finish. In both cases, the LLM may
  only emit typed decisions that a deterministic router validates against state, provider context, allowlists,
  side-effect policy, loop limits, and artifact ownership.
- Persist or write reproducible agent artifacts: dataset manifests, data-quality reports, hypothesis cards, experiment plans, strategy hashes, backtest configs/results, evaluation reports, robustness reports, recommendation reports, and paper-promotion packets.
- Use existing platform services where possible before adding new abstractions.
- Use a single stdio MCP server as soon as the first data service exists. Do not wait for the full research stack before proving MCP behavior.
- LangGraph agents use planned MCP tools to do their work. They should not call platform internals directly when an MCP tool exists for that operation.
- LangGraph state may store artifact references, status, public messages, and structured decisions. It must not persist hidden reasoning or raw LLM scratchpads as product records.
- Treat MCP tools as coarse-grained research actions. Avoid dozens of tiny implementation-detail tools.
- Documentation is part of each implementation slice. Core platform documentation belongs under `docs/core/`; research-agent, MCP, and LangGraph documentation belongs under `docs/research_agents/`; historical plans and audits belong under `docs/history/`.

## Agent Alignment

This plan follows `docs/research_agents/agents.md`: agents are implemented as LangGraph identities that use deterministic MCP tools to produce inspectable artifacts. The plan does not require building every autonomous workflow before useful tools exist; it proves one tool, then wraps it with one agent identity, then repeats.

| Agent | First MCP responsibility in this plan | Owned artifacts |
| --- | --- | --- |
| Quant Research Supervisor Agent | Supervisor state, implementation/specification coordination, backtest orchestration, recommendations | strategy/risk implementation versions and validations, strategy/risk/backtest specifications, experiment plans, runs, comparisons, recommendations; current candidate/stack artifacts retire in task 57A |
| Data Agent | Symbol discovery/preflight, data inventory, data quality, explicit load/backfill | `symbol_discovery_report.json`, `dataset_manifest.json`, `data_quality_report.json`, load result envelopes |
| Quantitative Methods Agent | Knowledge-backed method contract listing, validation, signal diagnostics, multiple-testing controls, and method packaging | source manifests, method cards, retrieval/citation reports, method contracts, validation reports, signal diagnostics, multiple-testing reports, method packages |
| ML Agent | Feature/model artifact registration and summary | feature manifests, model cards, prediction artifacts, drift reports |
| Hypothesis Agent | Hypothesis-card creation from available ingredients | `hypothesis_card.json` |
| Evaluation Agent | Skeptical review of data and research evidence | `evaluation_report.json` |
| Adversarial Agent | Stress tests and robustness attacks | `robustness_report.json` |

No research agent controls the live trading hot path. Promotion remains a human-reviewed proposal.

## LangGraph Identity Model

LangGraph is the identity and orchestration layer for agents. MCP is the tool boundary. The same MCP tool can be callable by multiple agents, but each agent's graph decides whether it is allowed, how inputs are formed, what state is retained, and which artifact must be produced.

| Agent | LangGraph identity requirement | MCP tool access pattern |
| --- | --- | --- |
| Data Agent | Owns `DataAgentState`, dataset-manifest state, quality status, load policy, symbol-discovery state, and optional Data Agent LLM control decisions. | May call only Data Agent MCP tools plus read-only health/config tools. |
| Quant Research Supervisor Agent | Owns `QuantResearchSupervisorState`, request decomposition, handoff ledger, LLM control-policy decisions, experiment plan state, comparison state, and recommendation synthesis. | May consume specialist artifact references, assess evidence, request/reuse allowed specialist tools through graph routing, stop early, and call Quant Research MCP tools; deterministic routers validate every LLM-proposed action. |
| Evaluation Agent | Owns `EvaluationState` and skeptical critique policy. | May read data/backtest artifacts and call evaluation tools; cannot create new hypotheses or mutate data. |
| Adversarial Agent | Owns `AdversarialState` and robustness attack policy. | May call robustness tools against supplied baseline artifacts; cannot recommend promotion. |
| Hypothesis Agent | Owns `HypothesisState` and hypothesis-card generation policy. | May read known ingredients and prior results; cannot run backtests or make verdicts. |
| Quantitative Methods Agent | Owns `QuantMethodsState`, knowledge source/card/retrieval/citation state, method-contract state, validation status, diagnostic state, multiple-testing state, method-package state, optional kernel state, and optional bounded LLM control decisions. | May call only Quantitative Methods `knowledge_*` and `math_*` tools plus read-only health/config tools; cannot fetch data, create hypotheses, create strategies, train models, run backtests, or promote strategies. |
| ML Agent | Owns `MLAgentState` and model-artifact policy. | May call ML tools for feature/model/prediction/drift artifacts; cannot produce final trading recommendations. |

The first LangGraph evidence should be the Data Agent graph calling `data_get_inventory` through the MCP client and returning a dataset manifest-style artifact reference or envelope. Do not wait for all planned MCP tools before creating the first LangGraph identity.

## Delivery Principle

Build MCP evidence in thin vertical slices. The first shippable slice is not a full Quant Research runner; it is a working Data Agent MCP surface that can answer data inventory, data quality, and bounded data-loading requests through the same envelope clients will use later.

The intended progression is:

```text
MCP server boots
  -> health/config tool works
  -> Data Agent symbol discovery and exact-symbol validation works
  -> Data Agent inventory tool works
  -> Data Agent LangGraph identity uses the inventory tool
  -> Data Agent quality tool works
  -> Data Agent explicit loading/backfill tool works
  -> Data Agent LLM control loop turns natural-language data requests into validated Data Agent tool calls
  -> Quant Research Supervisor identity consumes Data Agent artifacts
  -> Quantitative Methods knowledge/method tools produce source-backed deterministic method artifacts
  -> Optional producers submit source through one content-addressed implementation registry
  -> Quant Research Supervisor tools validate implementations and immutable specifications
  -> Canonical DB-backed backtests bind only Data Agent scope and passed specifications
  -> Provider-neutral optimisation records complete trial and selection lineage
  -> Evaluation and Adversarial tools independently assess untouched holdout and robustness evidence
  -> Supervisor, Quant Methods, Hypothesis, ML, Evaluation, and Adversarial graph/LLM layers compose the proven tools
  -> Recommendation and experiment-runner tools synthesize later evidence
```

Every current stage should leave behind a usable MCP tool, a direct service test, an MCP contract/smoke test, and an
artifact that matches the owning agent's contract. Earlier completion rows below are historical delivery evidence;
their candidate-era APIs are retired and are not current contracts.

## Completion Status Register

Use this register as the source of truth for implementation status. Keep statuses to `Not started`, `In progress`, `Blocked`, or `Done`. A chunk should only move to `Done` when its acceptance criteria are met and the evidence column points to tests, docs, command output, or artifact paths that prove it.

| Chunk | Status | Evidence | Notes |
| --- | --- | --- | --- |
| 0. Boundary Recon | Done | `docs/research_agents/history/mcp_trading_research_tools.md` Boundary Recon notes | Smallest first MCP data slice and later migration candidates documented. |
| 1. Clean Package Skeleton | Done | `tests/test_agent_identities.py`; `uv run pytest tests/test_agent_identities.py`; `uv run python -c "import trader_research, trader_mcp, trader_agents"` | Importable metadata-only packages added for `trader_research`, `trader_mcp`, and `trader_agents`. |
| 2. Minimal Tool Contracts | Done | `tests/test_research_contracts.py`; `uv run pytest tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py` | Research-owned `ToolEnvelope`, `SideEffect`, `ArtifactReference`, and JSON helpers added without moving legacy contracts. |
| 3. MCP Envelope Adapter | Done | `tests/test_mcp_adapters.py`; `uv run python -c "from trader_research.contracts import ToolEnvelope; from trader_mcp.adapters import envelope_to_mcp_result"` | Dependency-free MCP result adapter returns `content`, `structuredContent`, and `isError`. |
| 4. MCP Server Skeleton | Done | `tests/test_mcp_server.py`; stdio client smoke test; `uv run python -c "import trader_mcp; import trader_mcp.server as s; s.create_server()"` | Stdio MCP server exposes only read-only `mcp_health` and `mcp_get_config` support tools. |
| 5. Data Inventory Service | Done | `tests/test_market_data_queries.py`; `tests/test_data_inventory.py`; `tests/test_sql_boundaries.py`; `uv run pytest tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py tests/test_mcp_server.py` | Direct read-only Data Agent service returns embedded dataset manifests through typed core market-data queries; research/MCP layers do not embed raw SQL; MCP registration remains chunk 6. |
| 6. Register Data Inventory MCP Tool | Done | `tests/test_mcp_tools.py`; `tests/test_mcp_server.py`; `uv run pytest tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py` | `data_get_inventory` is registered as a read-only Data Agent MCP tool with injectable event-store wiring and shared envelope output. |
| 7. First MCP Tool Evidence | Done | `tests/test_mcp_first_tool_evidence.py`; `uv run pytest tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py` | Stdio MCP client starts a sample-data server, lists tools, calls `data_get_inventory`, and receives a valid Data Agent envelope. |
| 8. LangGraph Agent Identity Skeleton | Done | `tests/test_langgraph_agents.py`; `uv run python -c "from trader_agents.data_agent import build_data_agent_inventory_graph"` | LangGraph dependency, Data Agent state schema, and MCP client wrapper added without LLM calls or persistence. |
| 9. Data Agent Inventory Graph | Done | `tests/test_langgraph_agents.py`; `uv run pytest tests/test_langgraph_agents.py` | Deterministic Data Agent graph calls `data_get_inventory` through MCP and returns the dataset manifest in graph state. |
| 10. Data Quality Service | Done | `tests/test_data_quality_service.py`; `uv run pytest tests/test_data_quality_service.py tests/test_data_ensure_loaded.py` | Read-only Data Agent quality service returns stable report IDs, per-symbol totals, missing-gap counts, max-gap seconds, completeness, warnings, validation errors, and unavailable-store envelopes. |
| 11. Register Data Quality MCP Tool | Done | `tests/test_mcp_data_workflow.py`; `tests/test_mcp_tools.py`; `tests/test_mcp_server.py` | `data_summarize_quality` is registered as a read-only Data Agent MCP tool with JSON-native inputs and shared envelope output. |
| 12. Extend Data Agent Graph for Quality | Done | `tests/test_langgraph_data_workflow.py`; `uv run pytest tests/test_langgraph_agents.py tests/test_langgraph_data_workflow.py` | Data Agent quality graph calls `data_get_inventory` then `data_summarize_quality` through the MCP client and preserves reports, warnings, errors, and ordered tool calls. |
| 13. Data Ensure/Loading Service | Done | `tests/test_data_ensure_loaded.py`; `uv run pytest tests/test_data_quality_service.py tests/test_data_ensure_loaded.py` | `data_ensure_loaded` supports existing, sample, dry-run backfill, and permitted non-dry-run backfill through bounded config or injected runner policy with post-load evidence. |
| 14. Register Data Loading MCP Tool | Done | `tests/test_mcp_data_workflow.py`; `tests/test_mcp_tools.py`; `tests/test_mcp_server.py` | `data_ensure_loaded` is registered as `local_mutating`; config distinguishes registration from `TRADER_MCP_ALLOW_DATA_LOADING` runtime permission and MCP can run permitted injected/configured backfill through the tool. |
| 15. Extend Data Agent Graph for Loading | Done | `tests/test_langgraph_data_workflow.py` | Full Data Agent graph enforces loading policy and calls inventory, quality, ensure-loaded, and final quality through MCP tools only. |
| 16. Data MCP and LangGraph Workflow Evidence | Done | `tests/test_mcp_data_workflow.py`; `tests/test_langgraph_data_workflow.py`; `docs/research_agents/history/mcp_trading_research_tools.md` | Stdio MCP evidence covers health/config/inventory/quality/ensure/final quality with JSON text parity; LangGraph evidence completes the same workflow through the MCP client. |
| 17. Move Shared Tool Contracts | Done | `tests/test_research_contracts.py`; `tests/test_tool_contracts.py`; `tests/test_package_boundaries.py` | `trader_research.contracts` is canonical; `trader.tools.contracts` is a compatibility shim that returns the same envelope classes and preserves agent ownership. |
| 18. Move Research Helpers | Done | `tests/test_research.py`; `tests/test_sprint5_cli.py`; `tests/test_package_boundaries.py` | Research helper behavior runs through `trader_research.research`; `trader.research` is a temporary compatibility shim only. |
| 19. Move Research Tool Modules | Done | `tests/test_research_tools.py`; `tests/test_sprint5_cli.py`; `tests/test_package_boundaries.py` | Artifacts, discovery, promotion, recommendations, and suite helpers now live under `trader_research` with legacy `trader.tools.*` shims and no MCP/LangGraph imports. |
| 20. Research Domain Schemas | Done | `tests/test_research_domain.py` | Bounded requests, data requirements, specialist handoffs, artifact slots, planned artifact refs, run refs, and verdict schemas serialize to JSON-safe dictionaries and validate ownership/bounds. |
| 21. Quant Research Supervisor Graph Skeleton | Done | `tests/test_quant_research_supervisor.py`; `uv run python -c "from trader_agents.quant_research import build_quant_research_supervisor_graph"` | Supervisor graph records bounded requests, distinct identity, handoff ledger, artifact slots, public status, empty `called_tools`, and explicit missing-specialist blockers. |
| 22. Supervisor Consumes Data Agent Handoff | Done | `tests/test_supervisor_data_handoff.py`; `tests/test_quant_research_supervisor.py` | Supervisor accepts Data Agent manifest/quality handoffs, preserves ownership/provenance, blocks incomplete quality, rejects forged/mismatched handoffs, and does not fetch raw data. |
| 22A. Shared Provider Context and Capability Resolver | Done | `tests/test_data_symbol_discovery.py`; `uv run pytest -m 'not postgres'`; `uv run ruff check src tests` | Shared provider resolution covers configured Alpaca, omitted provider, matching/mismatched providers, unsupported instrument types, unsupported bar types, and asset-class compatibility aliases. |
| 22B. Provider-Aware Existing Data Tools | Done | `tests/test_data_symbol_discovery.py`; `tests/test_data_inventory.py`; `tests/test_data_quality_service.py`; `tests/test_data_ensure_loaded.py`; `uv run pytest -m 'not postgres'` | `data_get_inventory`, `data_summarize_quality`, and `data_ensure_loaded` accept optional provider context, fail fast on provider/instrument/bar mismatch before query/loading branches, and include provider context in successful payloads. |
| 22C. Data Symbol Discovery Service and Local/Configured Sources | Done | `tests/test_data_symbol_discovery.py`; `tests/test_market_data_queries.py`; `uv run pytest -m 'not postgres'` | `data_discover_symbols` supports local event-store discovery, configured-universe discovery, exact-symbol validation, crypto canonicalization, limits, and typed core local symbol queries without SQL in research/MCP layers. |
| 22D. Register Symbol Discovery MCP Tool | Done | `tests/test_mcp_tools.py`; `tests/test_mcp_server.py`; `uv run pytest -m 'not postgres'` | MCP registers `data_discover_symbols`, exposes provider policy metadata, parses provider/instrument/bar fields on Data Agent tools, and returns shared Data Agent envelopes. |
| 22E. Data Agent Symbol Discovery Graph | Done | `tests/test_langgraph_agents.py`; `tests/test_langgraph_data_workflow.py`; `tests/test_supervisor_data_handoff.py`; `uv run pytest -m 'not postgres'` | Data Agent graphs call `data_discover_symbols` through MCP before inventory, quality, or loading, propagate resolved provider context, and block downstream tools on missing symbols or provider mismatch. |
| 22F. Provider Catalog Adapters | Done | `tests/test_alpaca_symbol_provider.py`; `tests/test_data_symbol_discovery.py`; `uv run pytest -m 'not postgres'` | Provider catalog discovery is policy-gated; fake provider injection and the Alpaca read-only asset-listing adapter are tested without network calls or broker mutation APIs. |
| 22G. Symbol Discovery Documentation and Evidence | Done | `docs/research_agents/history/mcp_trading_research_tools.md`; `docs/research_agents/history/ai_tool_workflows.md`; `plans/data_agent_symbol_discovery_tool_plan.md`; `uv run pytest -m 'not postgres'` | Docs describe provider-scoped stock/crypto discovery, provider/instrument/bar selection, mandatory preflight, provider policy, and discovery versus inventory/loading/backtest behavior. |
| 22H. Data Agent LLM Control Loop | Done | `tests/test_llm_client.py`; `tests/test_data_agent_llm_policy.py`; `tests/test_langgraph_agents.py`; `tests/test_langgraph_data_workflow.py`; `uv run pytest tests/test_langgraph_agents.py tests/test_langgraph_data_workflow.py tests/test_data_agent_llm_policy.py tests/test_llm_client.py` | Provider-neutral LLM client boundary, runtime OpenAI-compatible/OpenRouter-style and Ollama-style adapters, fake LLM test client, bounded Data Agent LLM policy graph, deterministic action router, mandatory discovery enforcement, provider-context validation, loading policy checks, loop limit, missing-config fail-fast behavior, and no raw prompt/scratchpad state persistence are implemented. |
| 23A. Quant Methods Knowledge Domain Schemas | Done | `tests/test_knowledge_domain.py` | Knowledge source, ingestion, chunk, embedding, method-card, retrieval, and citation-validation schemas serialize to JSON-safe dictionaries. |
| 23B. Knowledge Source Registration | Done | `tests/test_knowledge_services.py`; `tests/test_knowledge_store.py` | Register local PDF/Markdown/text sources with source type labels, file hashes, access policy, duplicate detection, and allowed-directory checks. |
| 23C. Knowledge Text Extraction and Chunking | Done | `tests/test_knowledge_services.py`; `tests/test_knowledge_domain.py` | Extract PDF/Markdown/text sources and create deterministic locator-preserving chunks without silent OCR; sanitize PDF NUL bytes before hashing/storage. |
| 23D. Knowledge Embedding, Lexical, and Vector Indexing Service | Done | `tests/test_knowledge_embeddings.py`; `tests/test_knowledge_store.py`; `tests/test_postgres_knowledge_store.py` | Runtime-configured real embeddings, deterministic test embeddings, store abstraction, Postgres source/chunk/embedding tables, PostgreSQL full-text lexical search, pgvector dense retrieval, and deterministic rank fusion are implemented. |
| 23E. Knowledge Ingestion MCP Tools | Done | `tests/test_mcp_quant_methods_tools.py`; `tests/test_mcp_server.py` | Register source, ingest documents, get ingestion status, list sources, retrieve evidence, and validate citations through shared envelopes with injectable test stores and Postgres runtime configuration. |
| 23F. Method Card Drafting and Approval | Done | `tests/test_method_cards.py`; `tests/test_mcp_quant_methods_tools.py` | Create draft method cards from validated source evidence and publish approved immutable method-card versions only with explicit approval. |
| 23G. Hybrid Retrieval and Citation Validation MCP Tools | Done | `tests/test_mcp_quant_methods_tools.py`; `tests/test_method_cards.py` | Search approved/persisted method cards, run hybrid lexical/vector retrieval with deterministic rank fusion, return citeable evidence chunks, dereference chunks, and validate source IDs, locators, method-card approval, and claim support. |
| 23H. Knowledge-Backed Math Method Domain Schemas | Done | `tests/test_math_methods.py` | Method contracts/reports include knowledge evidence refs required for sophisticated statistical methods. |
| 23I. Knowledge-Backed Math Method Registry | Done | `tests/test_math_methods.py`; `tests/test_method_cards.py` | Link non-trivial statistical methods to approved method cards, including persisted approved cards; keep unsupported methods fail-closed and legacy indicator filters. |
| 23J. Citation-Backed Python Implementation Validation | Done | `tests/test_method_implementations.py`; `tests/test_mcp_quant_methods_tools.py` | Reuses Trader `Indicator` as the runtime contract; validates approved method-card/contract-backed Python implementations for `sma`, `ema`, `rsi`, `rolling_volatility`, and `z_score` with source hashes, parsed provenance docstrings, static safety checks, deterministic fixtures, warmup/null behavior, output length, and no-lookahead prefix checks. |
| 23K. Python Method Artifact Generation and Registration | Done | `tests/test_method_implementations.py`; `tests/test_mcp_quant_methods_tools.py` | Registers maintained Python `Indicator` implementations through `method_implementation_manifest.json`; generated Python drafts are written only to quarantine, must include the same citation/provenance docstring, are statically screened, registered as generated implementations, and fixture-validated before being marked `validated`. |
| 23K-A. Citation-Backed Signal Method Vertical Slice | Done | `tests/test_method_implementations.py`; `tests/test_mcp_quant_methods_tools.py` | Proves the full Quantitative Methods research process for the Bollinger/BWMA action rule as a `trader.signals.Signal`: evidence is retrieved/dereferenced, a signal method card is created/published in the MCP flow, the method contract declares `runtime_contract="trader.signals.Signal"`, `trader_standard.signals:BollingerBwmaActionSignal` registers as a citation-backed implementation, and `math_run_signal_fixtures` emits `signal_implementation_validation_report.json`. Diagnostics and family-level inference remain 23L. |
| 23L. Signal Diagnostics and Multiple-Testing Reports | Done | `tests/test_signal_diagnostics.py`; `tests/test_multiple_testing.py`; `tests/test_mcp_quant_methods_tools.py`; `tests/test_agent_identities.py`; `uv run pytest -q` | Signal-composition diagnostics and Benjamini-Hochberg family-level correction are implemented. Diagnostics operate on declared signal candidates, not raw indicators, require approved `rank_ic` method-card evidence, warn for observational candidates without executable implementations, and record validated signal implementation refs when provided. Multiple-testing reports require a candidate-family manifest, one p-value row per candidate, approved `benjamini_hochberg` evidence, raw/adjusted p-values, accepted/rejected candidates, warnings, and blockers. Bonferroni, Holm, White Reality Check, Hansen SPA, Deflated Sharpe Ratio, and PBO remain follow-on methods. |
| 23M. C++ / Compiled Kernel Path | Done | `tests/test_cpp_kernel_artifacts.py`; `tests/test_mcp_quant_methods_tools.py`; `tests/test_agent_identities.py`; `tests/test_research_domain.py`; `uv run ruff check src tests`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents src/trader_standard` | Template-restricted SMA C++ kernel generation and local compilation are implemented after validated Python references. `math_generate_cpp_kernel` writes generated source and `cxx_kernel_manifest.json`; `math_compile_kernel` compiles in an isolated artifact build directory, records compiler/build/binary/log metadata, and fails closed on missing compilers, tampered sources, unsafe includes/calls, and compile failures. Further C++ conformance/runtime acceleration is deferred behind the meaningful MCP research toolchain. |
| 23N. Method Package Manifests | Done | `uv run ruff check src/trader_research/methods/packages.py src/trader_research/methods/tools.py src/trader_research/domain.py src/trader_research/agents.py src/trader_mcp/constants.py src/trader_mcp/knowledge_tools.py tests/test_method_package_artifacts.py tests/test_mcp_quant_methods_tools.py tests/test_agent_identities.py tests/test_research_domain.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_method_package_artifacts.py tests/test_mcp_quant_methods_tools.py tests/test_agent_identities.py tests/test_research_domain.py -q`; `uv run mypy` | Bundles source-backed, fixture-validated Python indicator and signal implementations into `method_package_manifest.json` handoff artifacts through `math_package_method_artifact`. Python validation is the gate; C++ refs are optional warning-only optimization metadata. Task 26 can now consume validated method packages. |
| 24. Register Quantitative Methods MCP Tools | Done | `tests/test_mcp_quant_methods_tools.py`; `tests/test_mcp_server.py`; `tests/test_agent_identities.py` | MCP registers the current `knowledge_*` and `math_*` Quantitative Methods tool surface with `agent_owner="Quantitative Methods Agent"`, correct side-effect metadata, config listing, and injectable fake stores/LLM clients for tests. |
| 25. Strategy Candidate Schema and Template Catalog | Done | `uv run ruff check src/trader_research/strategy_candidates/ src/trader_research/domain.py src/trader_research/suites.py tests/test_strategy_candidates.py tests/test_research_domain.py`; `python -m compileall -q src/trader_research`; `uv run pytest tests/test_strategy_candidates.py tests/test_research_domain.py tests/test_research_tools.py -q`; `uv run mypy` | Adds the declarative `strategy_candidate_manifest.json` domain schema and read-only `research_list_strategy_templates` service for maintained `trend_following`, `mean_reversion`, and `bollinger_band` templates. Supported strategy families are centralized in the catalog. Candidate creation is handled by task 26; MCP registration remains 27. |
| 26. Source-Backed Strategy Candidate Builder | Done | `uv run ruff check src/trader_research/strategy_candidates/validation.py src/trader_research/strategy_candidates/ src/trader_research/domain.py src/trader_research/agents.py src/trader_mcp/constants.py src/trader_mcp/research_tools.py src/trader_mcp/server.py tests/test_strategy_validation.py tests/test_mcp_strategy_tools.py tests/test_strategy_candidates.py tests/test_agent_identities.py tests/test_research_domain.py tests/test_mcp_server.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_strategy_validation.py tests/test_mcp_strategy_tools.py tests/test_strategy_candidates.py tests/test_method_package_artifacts.py tests/test_agent_identities.py tests/test_research_domain.py tests/test_mcp_server.py -q`; `uv run mypy` | Adds direct local-mutating `research_create_strategy_candidate` service. It consumes validated signal `method_package_manifest.json` refs, enforces catalog role coverage and scalar bounded parameters, records sizing/risk/execution assumptions, derives signal refs, writes a deterministic importable Python `strategy_implementation` source file implementing `trader.strategies.Strategy`, and records that source in `strategy_candidate_manifest.json`. Generated source class names are semantic template-derived names, such as `BollingerBandResearchStrategy`; candidate provenance remains in `candidate_id`, `CANDIDATE_ID`, and manifest metadata. It does not register MCP, run backtests, or validate executable behavior; those remain task 27 and later. |
| 27. Strategy Candidate Validation MCP Tools | Done | `uv run ruff check src/trader_research/strategy_candidates/validation.py src/trader_research/strategy_candidates/ src/trader_research/domain.py src/trader_research/agents.py src/trader_mcp/constants.py src/trader_mcp/research_tools.py src/trader_mcp/server.py tests/test_strategy_validation.py tests/test_mcp_strategy_tools.py tests/test_strategy_candidates.py tests/test_agent_identities.py tests/test_research_domain.py tests/test_mcp_server.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_strategy_validation.py tests/test_mcp_strategy_tools.py tests/test_strategy_candidates.py tests/test_method_package_artifacts.py tests/test_agent_identities.py tests/test_research_domain.py tests/test_mcp_server.py -q`; `uv run mypy` | Registers `research_list_strategy_templates`, `research_create_strategy_candidate`, and `research_validate_strategy_candidate` through MCP. Validation writes supervisor-owned `strategy_candidate_validation_report.json`, verifies the generated strategy source hash, loads the generated `build_strategy(...)` factory, instantiates the `trader.strategies.Strategy` implementation with an internal synthetic context, runs deterministic synthetic-bar smoke checks, and keeps backtests deferred to task 28. |
| 28. Baseline Backtest Service | Done | `uv run ruff check src/trader_research/backtests/ src/trader_research/domain.py src/trader_research/agents.py src/trader_mcp/constants.py src/trader_mcp/research_tools.py src/trader_mcp/server.py tests/test_research_backtests.py tests/test_mcp_backtest_tools.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_research_backtests.py tests/test_mcp_backtest_tools.py tests/test_strategy_validation.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py -q`; `uv run pytest tests/test_mcp_tools.py tests/test_mcp_data_workflow.py tests/test_mcp_strategy_tools.py -q`; `uv run mypy` | Adds `trader_research.backtests.run_baseline_backtest`. The service consumes a validated strategy candidate, a passed strategy validation report, and exactly one Data Agent `dataset_manifest`; it rejects loose symbols/asset class/timeframe/start/end/source fields, derives the normalized `BacktestDataScope` from the manifest, runs `BacktestRunner` with `NoOpRiskManager`, and writes `backtest_run_ref.json`, result, metrics, provenance, curves, positions, and optional trades. |
| 29. Backtest MCP Tools | Done | `uv run ruff check src/trader_research/backtests/ src/trader_research/domain.py src/trader_research/agents.py src/trader_mcp/constants.py src/trader_mcp/research_tools.py src/trader_mcp/server.py tests/test_research_backtests.py tests/test_mcp_backtest_tools.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_research_backtests.py tests/test_mcp_backtest_tools.py tests/test_strategy_validation.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py -q`; `uv run pytest tests/test_mcp_tools.py tests/test_mcp_data_workflow.py tests/test_mcp_strategy_tools.py -q`; `uv run mypy` | Registers `research_run_backtest` and `research_get_backtest_results` through MCP with Quant Research Supervisor ownership. The run tool is local-mutating and execution-gated by `TRADER_MCP_ALLOW_BACKTESTS=true`; disabled environments list the tool but fail closed before runtime access. Result lookup is read-only and returns run refs, summary metrics, data scope, warnings/blockers, provenance, and artifact paths. |
| 30. Backtest Result Query And Comparison | Done | `uv run ruff check src/trader_research/backtests/ src/trader_research/domain.py src/trader_research/agents.py src/trader_mcp/constants.py src/trader_mcp/research_tools.py src/trader_mcp/server.py tests/test_research_backtests.py tests/test_mcp_backtest_tools.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_research_backtests.py tests/test_mcp_backtest_tools.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py -q`; `uv run mypy` | Adds supervisor-owned `research_compare_backtest_results` over explicit task-28/29 run refs. It reads persisted run refs, metrics, and provenance only; ranks comparable runs; warns for non-like-for-like dimensions; and writes deterministic `comparison_report.json` artifacts without running backtests or querying SQL/event-store experiment tables. |
| 31. Performance Report Service | Done | `uv run ruff check src/trader_research/evaluation/performance.py src/trader_research/domain.py src/trader_research/agents.py src/trader_mcp/constants.py src/trader_mcp/evaluation_tools.py src/trader_mcp/server.py tests/test_performance_reports.py tests/test_mcp_evaluation_tools.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_performance_reports.py tests/test_mcp_evaluation_tools.py tests/test_research_backtests.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py -q`; `uv run mypy` | Adds Evaluation-owned `generate_performance_report` over one persisted task-28 backtest bundle. It reads run refs, metrics, result, provenance, optional trades, and optional Data Agent quality evidence; writes deterministic `evaluation_report.json`; and reports blocked status for missing/incomplete quality, failed runs, run blockers, zero trades, or mismatched evidence. |
| 32. Performance Report MCP Tool | Done | `uv run ruff check src/trader_research/evaluation/performance.py src/trader_research/domain.py src/trader_research/agents.py src/trader_mcp/constants.py src/trader_mcp/evaluation_tools.py src/trader_mcp/server.py tests/test_performance_reports.py tests/test_mcp_evaluation_tools.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_performance_reports.py tests/test_mcp_evaluation_tools.py tests/test_research_backtests.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py -q`; `uv run mypy` | Registers `evaluation_generate_performance_report` through MCP with Evaluation Agent ownership and local-mutating side effect. The tool is not gated by `TRADER_MCP_ALLOW_BACKTESTS` because it reads persisted bundles and writes only Evaluation-owned reports. |
| 33. End-to-End Research Toolchain Test | Done | `uv run ruff check tests/test_mcp_research_toolchain.py`; `uv run pytest tests/test_mcp_research_toolchain.py -q`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_mcp_research_toolchain.py tests/test_mcp_quant_methods_tools.py tests/test_mcp_strategy_tools.py tests/test_mcp_backtest_tools.py tests/test_mcp_evaluation_tools.py -q`; `uv run mypy` | Adds the end-to-end MCP evidence test. A deterministic Bollinger signal package is registered, fixture-validated, packaged, converted into a source-backed strategy candidate, validated, run through a data-scoped baseline backtest with real trade evidence, and reported through `evaluation_generate_performance_report`. Failure cases assert missing method provenance and unvalidated strategy candidates fail closed. |
| 33A. Multi-Asset And Risk Artifact Schemas | Done | `uv run ruff check src/trader_research/risk_managers/ src/trader_research/domain.py src/trader_research/agents.py src/trader_mcp/constants.py src/trader_mcp/research_tools.py src/trader_mcp/server.py tests/test_risk_manager_candidates.py tests/test_mcp_risk_manager_tools.py tests/test_agent_identities.py tests/test_research_domain.py tests/test_mcp_server.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_risk_manager_candidates.py tests/test_mcp_risk_manager_tools.py tests/test_agent_identities.py tests/test_research_domain.py tests/test_mcp_server.py -q` | Defines `risk_manager_candidate_manifest.json`, `risk_manager_implementation.py`, `risk_manager_candidate_validation_report.json`, `strategy_risk_stack_manifest.json`, `strategy_risk_stack_validation_report.json`, and `portfolio_backtest_run_ref.json` artifact contracts. Backtest refs now carry optional strategy/risk stack IDs, symbol metrics, exposure summaries, and risk-measure summaries. Strategy and risk candidates remain data-free; symbols, timeframe, and date windows still come from Data Agent dataset manifests. |
| 33B. Risk Manager Template Catalog And Builder | Done | `uv run ruff check src/trader_research/risk_managers/ src/trader_research/domain.py src/trader_research/agents.py src/trader_mcp/constants.py src/trader_mcp/research_tools.py src/trader_mcp/server.py tests/test_risk_manager_candidates.py tests/test_mcp_risk_manager_tools.py tests/test_agent_identities.py tests/test_research_domain.py tests/test_mcp_server.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_risk_manager_candidates.py tests/test_mcp_risk_manager_tools.py tests/test_agent_identities.py tests/test_research_domain.py tests/test_mcp_server.py -q` | Adds supervisor-owned `research_list_risk_manager_templates` and `research_create_risk_manager_candidate`. The catalog covers gross exposure caps, per-symbol exposure caps, concentration caps, drawdown guards, and VaR/CVaR-style filters as generation targets. Candidate creation writes importable backtest-only `trader.risk.RiskManager` source plus `risk_manager_candidate_manifest.json`, records source hashes, bounded scalar parameters, optional validated method-package refs for risk measures, and no-live-trading execution assumptions. Risk-manager validation, stack composition, portfolio backtests, and portfolio/risk reports remain 33D-33F. |
| 54. `trader_research` Capability Packaging And Docstring Standardization | Done | `uv run ruff check src/trader_research src/trader_mcp src/trader_agents tests`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run mypy`; `uv run pytest -m 'not postgres' -q`; targeted moved-family suites for Data, Quant Methods, strategy candidates, risk managers, backtests, Evaluation, MCP, docs, and package boundaries | Moves broad top-level research service modules into bounded capability packages: `data/`, `methods/`, `strategy_candidates/`, `risk_managers/`, `backtests/`, and `evaluation/`. Package-level exports remain canonical public surfaces; old flat modules and imports are removed rather than shimmed. Boundary tests prevent reintroducing broad flat service modules. This cleanup precedes 33C feature work. |
| 33C. Multi-Asset Strategy Candidate Generation | Done | `uv run ruff check src/trader_standard/strategies src/trader_research/strategy_candidates src/trader_research/risk_managers src/trader_research/portfolio_stacks src/trader_mcp src/trader_research/agents.py tests/test_strategy_candidates.py tests/test_strategy_validation.py tests/test_risk_manager_validation.py tests/test_strategy_risk_stacks.py tests/test_mcp_risk_manager_tools.py tests/test_mcp_strategy_risk_stack_tools.py tests/test_mcp_strategy_tools.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_agent_docs.py tests/test_tool_contracts.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents src/trader_standard`; `uv run pytest tests/test_strategy_candidates.py tests/test_strategy_validation.py tests/test_risk_manager_candidates.py tests/test_risk_manager_validation.py tests/test_strategy_risk_stacks.py tests/test_mcp_strategy_tools.py tests/test_mcp_risk_manager_tools.py tests/test_mcp_strategy_risk_stack_tools.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py tests/test_research_agent_docs.py tests/test_tool_contracts.py -q`; `uv run mypy`; `uv run pytest tests/test_mcp_tools.py tests/test_mcp_research_toolchain.py tests/test_mcp_backtest_tools.py tests/test_mcp_evaluation_tools.py -q` | Strategy templates now declare portfolio mode, rebalance cadence, allocation bounds, and portfolio-state requirements. Existing long/flat templates are explicit per-symbol independent multi-asset templates, and a maintained cross-sectional momentum template is available for ranked top-N allocation. Generated strategy source metadata records portfolio-construction semantics while still accepting symbols from validation/backtest data scope and never storing symbols or dates in candidate manifests. Strategy validation now uses a deterministic three-symbol fixture. |
| 33D. Strategy/Risk Stack Builder And Validation | Done | `uv run ruff check src/trader_standard/strategies src/trader_research/strategy_candidates src/trader_research/risk_managers src/trader_research/portfolio_stacks src/trader_mcp src/trader_research/agents.py tests/test_strategy_candidates.py tests/test_strategy_validation.py tests/test_risk_manager_validation.py tests/test_strategy_risk_stacks.py tests/test_mcp_risk_manager_tools.py tests/test_mcp_strategy_risk_stack_tools.py tests/test_mcp_strategy_tools.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_agent_docs.py tests/test_tool_contracts.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents src/trader_standard`; `uv run pytest tests/test_strategy_candidates.py tests/test_strategy_validation.py tests/test_risk_manager_candidates.py tests/test_risk_manager_validation.py tests/test_strategy_risk_stacks.py tests/test_mcp_strategy_tools.py tests/test_mcp_risk_manager_tools.py tests/test_mcp_strategy_risk_stack_tools.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py tests/test_research_agent_docs.py tests/test_tool_contracts.py -q`; `uv run mypy`; `uv run pytest tests/test_mcp_tools.py tests/test_mcp_research_toolchain.py tests/test_mcp_backtest_tools.py tests/test_mcp_evaluation_tools.py -q` | Adds supervisor-owned `research_validate_risk_manager_candidate`, `research_create_strategy_risk_stack`, and `research_validate_strategy_risk_stack`. Risk-manager validation writes deterministic validation reports after source/hash/safety/runtime fixture checks. Stack creation requires passed strategy and risk-manager validation reports, records ordered risk-manager priority and validation provenance, and writes `strategy_risk_stack_manifest.json`. Stack validation imports the validated sources, checks ordering, runtime contracts, allowed side effects, telemetry hooks, source hashes, and runs a deterministic multi-asset fixture through `RiskPipeline` before portfolio backtests are allowed. |
| 33E. Risk-Scoped Portfolio Backtest Tools | Done | `uv run ruff check src/trader_research/artifact_store.py src/trader_research/postgres_artifact_store.py src/trader_research/backtests/services.py src/trader_research/evaluation/performance.py src/trader_research/methods/tools.py src/trader_research/method_implementations/registration.py src/trader_research/method_implementations/fixtures.py src/trader_research/methods/packages.py src/trader_research/strategy_candidates/services.py src/trader_research/strategy_candidates/validation.py src/trader_research/risk_managers/services.py src/trader_research/risk_managers/validation.py src/trader_research/portfolio_stacks/services.py src/trader_mcp/server.py src/trader_mcp/knowledge_tools.py src/trader_mcp/research_tools.py src/trader_mcp/evaluation_tools.py tests/test_mcp_portfolio_risk_toolchain.py tests/test_mcp_strategy_tools.py tests/test_mcp_risk_manager_tools.py tests/test_mcp_strategy_risk_stack_tools.py tests/test_mcp_research_toolchain.py tests/test_mcp_quant_methods_tools.py tests/test_mcp_evaluation_tools.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents src/trader_standard`; `uv run pytest tests/test_mcp_portfolio_risk_toolchain.py -q`; `uv run pytest tests/test_mcp_strategy_tools.py tests/test_mcp_risk_manager_tools.py tests/test_mcp_strategy_risk_stack_tools.py tests/test_mcp_research_toolchain.py tests/test_mcp_quant_methods_tools.py tests/test_mcp_evaluation_tools.py -q`; `uv run pytest tests/test_portfolio_backtests.py tests/test_performance_reports.py -q` | Adds gated `research_run_portfolio_backtest`, resolving a passed strategy/risk stack validation report and one Data Agent dataset manifest before running `BacktestRunner` with a recording risk pipeline over ordered validated risk managers. MCP now persists method, strategy, risk-manager, stack, portfolio-backtest, and evaluation artifacts through the structured research artifact store with `research://postgres/{artifact_type}/{artifact_id}` refs; direct services keep filesystem exports as fallback. |
| 33F. Portfolio And Risk Evaluation Reports | Done | Same verification as 33E. | Extends `evaluation_generate_performance_report` to resolve baseline or portfolio bundles, accept inline `portfolio_backtest_run_ref`, include `backtest_kind`, stack refs, symbol metrics, exposure summaries, risk decisions, breach evidence, and risk-measure summaries, and block when portfolio risk sidecars or required risk telemetry are missing. |
| 33G. Multi-Asset Risk Toolchain Evidence | Done | Same verification as 33E, including `tests/test_mcp_portfolio_risk_toolchain.py`. | Adds deterministic MCP evidence for method package -> cross-sectional multi-asset strategy candidate -> risk-manager candidate -> validated strategy/risk stack -> risk-scoped portfolio backtest -> Evaluation report, including fail-closed assertions for unvalidated risk-manager evidence and non-passed stack validation. |
| 33H. Rich Methodology Candidate Schema | Done | `uv run ruff check src/trader_research/knowledge/domain.py src/trader_research/domain.py tests/test_knowledge_domain.py tests/test_research_domain.py docs/research_agents/agents.md docs/research_agents/architecture.md docs/research_agents/tool_contracts.md`; `python -m compileall -q src/trader_research`; `uv run pytest tests/test_knowledge_domain.py tests/test_research_domain.py tests/test_agent_identities.py -q`; `uv run pytest tests/test_research_agent_docs.py tests/test_tool_contracts.py -q`; `uv run mypy`; `git diff --check` | Adds `methodology_candidate` artifact ownership plus rich nullable methodology schemas with closed core groups, closed domain extension blocks, and field-level evidence requirements for populated values. Rich method cards keep `method_card_draft` / `method_card` artifact types with `card_format="rich_method_card"` and a shallow `MethodCard` projection. Tests cover JSON round trips, unsupported fields, nullable fields, and representative RSI, straddle, pairs/cointegration, and commodity sentiment blocks. |
| 33I. Methodology Candidate Discovery MCP Tools | Done | `uv run ruff check src/trader_research/knowledge src/trader_research/domain.py src/trader_research/agents.py src/trader_research/postgres_artifact_store.py src/trader_mcp/constants.py src/trader_mcp/knowledge_tools.py src/trader_mcp/server.py tests/test_knowledge_domain.py tests/test_methodology_candidates.py tests/test_mcp_quant_methods_tools.py tests/test_agent_identities.py tests/test_research_domain.py docs/research_agents/agents.md docs/research_agents/architecture.md docs/research_agents/mcp_tools.md docs/research_agents/operations.md docs/research_agents/tool_contracts.md docs/research_agents/workflows.md`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents`; `uv run pytest tests/test_knowledge_domain.py tests/test_research_domain.py tests/test_agent_identities.py tests/test_methodology_candidates.py tests/test_mcp_quant_methods_tools.py -q`; `uv run pytest tests/test_research_agent_docs.py tests/test_tool_contracts.py tests/test_package_boundaries.py -q`; `uv run pytest tests/test_mcp_server.py tests/test_mcp_tools.py -q`; `uv run mypy`; `git diff --check` | Adds DB-first `knowledge_discover_methodology_candidates` with Quantitative Methods ownership and `local_mutating` side effect. Discovery accepts query, source, or method-family scope; uses retrieval or direct source chunk scans; expands neighboring chunks; groups deterministic source spans; writes `methodology_candidate` artifacts to the research artifact store; returns `research://postgres/methodology_candidate/{id}` refs; and fails closed without canonical DB persistence. |
| 33J. Evidence-Grounded Field Extraction And Validation | Done | Same verification as 33I. | Adds DB-first `knowledge_extract_methodology_fields` and `knowledge_validate_methodology_candidate` with deterministic rich-field extraction, field-level evidence refs, nullable unsupported fields, closed field/group validation, source/chunk/locator checks, family-specific minimum evidence, high-risk family evidence requirements, quote-limit blockers, internal-note-only textbook/source blockers, persisted extraction/validation reports, MCP registration/config metadata, and Postgres projection tables for pgAdmin visibility. |
| 33K. Rich Method Card Draft And Approval Tools | Done | `uv run ruff check src/trader_research/knowledge/method_cards.py src/trader_research/knowledge/store.py src/trader_research/knowledge/storage.py src/trader_research/knowledge/postgres_store.py src/trader/knowledge/schema.py src/trader/knowledge/store.py src/trader_research/strategy_candidates/services.py src/trader_research/strategy_candidates/validation.py src/trader_research/risk_managers/services.py src/trader_research/risk_managers/validation.py src/trader_standard/strategies/policy_driven.py src/trader_standard/strategies/__init__.py src/trader_standard/__init__.py src/trader_mcp/knowledge_tools.py src/trader_mcp/research_tools.py src/trader_mcp/server.py src/trader_mcp/constants.py src/trader_research/domain.py src/trader_research/agents.py src/trader_research/knowledge/methodology_extraction.py tests/test_method_cards.py tests/test_strategy_candidates.py tests/test_risk_manager_candidates.py tests/test_mcp_quant_methods_tools.py tests/test_mcp_strategy_tools.py tests/test_agent_identities.py tests/test_knowledge_domain.py`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents src/trader_standard src/trader`; `uv run pytest tests/test_method_cards.py tests/test_strategy_candidates.py tests/test_risk_manager_candidates.py tests/test_mcp_quant_methods_tools.py tests/test_agent_identities.py tests/test_knowledge_domain.py tests/test_research_domain.py -q`; `uv run pytest tests/test_research_agent_docs.py tests/test_tool_contracts.py tests/test_package_boundaries.py tests/test_mcp_server.py tests/test_mcp_tools.py tests/test_mcp_strategy_tools.py tests/test_mcp_risk_manager_tools.py -q`; `uv run pytest tests/test_methodology_candidates.py tests/test_method_implementations.py tests/test_method_package_artifacts.py -q`; `uv run pytest tests/test_mcp_research_toolchain.py tests/test_mcp_portfolio_risk_toolchain.py -q`; `uv run pytest tests/test_mcp_backtest_tools.py tests/test_mcp_evaluation_tools.py tests/test_mcp_data_workflow.py -q`; `uv run pytest tests/test_performance_reports.py tests/test_portfolio_backtests.py tests/test_strategy_validation.py tests/test_risk_manager_validation.py -q`; `uv run pytest tests/test_postgres_knowledge_store.py -q` skipped because local Postgres settings were unavailable; `uv run mypy`; `git diff --check` | Adds `knowledge_create_rich_method_card_draft`, rich-card storage/listing in knowledge stores, Postgres method-card projection columns, and rich-card publishing that preserves full nullable fields while keeping shallow method-card search/citation compatibility. Draft creation requires a passed methodology-candidate validation report, matching candidate, field-level evidence, source/chunk revalidation, and derivable shallow assumptions/inputs/outputs/failure modes. |
| 33L. Strategy Generation From Rich Method Cards | Done | Same verification as 33K. | Extends strategy/risk candidate manifests with `methodology_refs`, lets approved rich cards drive bounded candidate generation, adds the maintained `pairs_mean_reversion` strategy template/runtime builder for statistical-arbitrage cards, validates required pair-method evidence, keeps symbols/timeframes/date windows in Data Agent scope, and maps explicit rich risk-model thresholds into risk-manager candidates without inventing values from prose. |
| 33M. Rich Methodology Documentation And Operator Guide | Done | `uv run pytest tests/test_research_agent_docs.py tests/test_tool_contracts.py -q`; `uv run ruff check tests/test_research_agent_docs.py`; `rg -n "Planned:|backtest tools are not registered yet|No backtest tool is exposed" docs/research_agents --glob '!history/**'` returned no matches; `git diff --check` | Updates the canonical research-agent docs with the source registration versus full-document ingestion distinction, DB-first rich methodology operating checklist, candidate discovery/extraction/validation semantics, field-level citation rules, draft versus approved rich-card behavior, source suitability policy, and how approved rich cards feed method packaging, strategy/risk generation, backtests, and Evaluation. Operator examples now cover pairs/cointegration, options straddles, RSI/technical indicators, and commodity sentiment indicators. |
| 33N. Rich Methodology End-To-End Evidence | Done | `uv run ruff check src/trader_standard/strategies/policy_driven.py tests/test_mcp_rich_methodology_toolchain.py`; `uv run pytest tests/test_mcp_rich_methodology_toolchain.py -q` | Adds deterministic MCP evidence for a generated book-style PDF source -> full-document ingestion -> methodology candidate discovery -> rich field extraction -> methodology validation -> rich method-card draft -> approved rich method card -> rich-card-driven `pairs_mean_reversion` strategy candidate -> validated risk stack -> risk-scoped portfolio backtest -> Evaluation report. The regression includes fail-closed assertions for unapproved drafts, shallow/thin method cards, missing field evidence, unsupported rich-card families, and internal-note-only methodology evidence, and it now covers both pair legs executing in the portfolio backtest. |
| 33O. Canonical Method Card Architecture Review | Done | `uv run pytest tests/test_research_agent_docs.py -q`; `git diff --check` | Documents the target agentic methodology architecture in `docs/research_agents/architecture.md`: method cards are canonical evidence-backed methodology artifacts, shallow fields are derived projections, retrieval is distinct from methodology understanding, evidence assembly precedes extraction, bounded enrichment remains validation-gated, strategy-grade readiness is separate from descriptive validity, method discovery is open-world, evidence roles are family-level closed contracts, and the next capability work should retire shallow public methodology drafting, add diagnostics, discover named methods from source/query text without hardcoded targets, assemble field-role evidence, strengthen extraction, and validate semantic readiness. |
| 33P. Canonical Method Card Workflow And Legacy Shallow Retirement | Done | `uv run pytest tests/test_methodology_candidates.py tests/test_method_cards.py tests/test_strategy_candidates.py tests/test_risk_manager_candidates.py -q`; `uv run pytest tests/test_mcp_quant_methods_tools.py tests/test_mcp_rich_methodology_toolchain.py tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py tests/test_research_agent_docs.py tests/test_tool_contracts.py -q`; `uv run pytest tests/test_package_boundaries.py -q`; `uv run ruff check ...`; `python -m compileall -q ...`; `uv run mypy`; `git diff --check` | Makes evidence-backed rich cards the strategy-grade method-card workflow. Shallow draft creation is explicitly legacy/projection behavior, rich draft creation requires packet-backed validation readiness, shallow/thin cards cannot satisfy rich strategy/risk generation, and derived shallow projections remain searchable compatibility records only. |
| 33Q. Family Evidence Role Ontology | Done | Same verification as 33P. | Adds versioned family-level evidence profiles rather than known-target profiles. Profiles define role names, purposes, lexical hints, field mappings, and required roles by readiness level for technical indicators, statistical arbitrage, options/derivatives, sentiment/alternative data, portfolio construction, risk models, fundamental valuation, and execution methods. |
| 33R. Open-World Method Discovery And Diagnostics | Done | Same verification as 33P. | Discovery now treats source-level method families as scope hints rather than candidate labels, derives candidate families from local chunk evidence, and records name evidence, family attribution terms, span diagnostics, duplicate behavior, warnings, and blockers in candidate lineage. |
| 33S. Methodology Evidence Assembly Packets | Done | Same verification as 33P. | Adds DB-first `methodology_evidence_packet` artifacts, Postgres projections, and `knowledge_assemble_methodology_evidence`. The service requires both knowledge and research artifact stores, consumes candidate refs or inline candidates, gathers role-labeled chunks using the family profile, expands source neighbors, records found/missing roles, hashes, diagnostics, and fails closed on missing stores, sources, chunks, profiles, or readiness roles. |
| 33T. Role-Grounded Field Extraction And Bounded Enrichment | Done | Same verification as 33P. | `knowledge_extract_methodology_fields` accepts evidence packet refs and populates rich fields from role-labeled chunks. Field refs carry evidence-role claims, unsupported fields remain null, extraction reports record `evidence_packet_id`, and validation blocks fields that cite chunks outside the claimed role evidence. Bounded enrichment remains deferred behind the deterministic packet/extraction boundary. |
| 33U. Semantic Validation And Readiness Gates | Done | Same verification as 33P. | Methodology validation now includes role/chunk consistency checks and readiness statuses for descriptive, implementation, signal, strategy-template, and risk-manager levels. Rich method-card drafts require implementation readiness, approved rich cards preserve readiness in lineage, and strategy/risk candidate generation consumes strategy-template or risk-manager readiness gates before accepting rich-card evidence. |
| 33V. Open-World Method Card Evidence Regression | Done | `uv run ruff check src/trader_research/knowledge/evidence_profiles.py tests/test_mcp_open_world_method_cards.py`; `uv run pytest tests/test_mcp_open_world_method_cards.py tests/test_methodology_candidates.py tests/test_method_cards.py tests/test_strategy_candidates.py -q`; `uv run pytest tests/test_mcp_quant_methods_tools.py tests/test_mcp_rich_methodology_toolchain.py tests/test_research_agent_docs.py tests/test_tool_contracts.py tests/test_package_boundaries.py -q`; `python -m compileall -q src/trader_research src/trader_mcp`; `uv run mypy`; `git diff --check` | Proves the upgraded target-agnostic flow through MCP using previously unseen technical-indicator and statistical-arbitrage method names. The regression ingests schema-v2 evidence units, discovers separate identities, assembles target-bound role evidence, extracts specific cited fields, validates implementation/strategy readiness, creates and publishes canonical revisions in stable method-card sets, and passes the approved statistical-arbitrage card into a maintained strategy template. It also rejects an approved shallow card, blocks a definition-only technical method with no formula evidence, and rejects a target field contaminated by an adjacent named method. |
| 33W. Stable Method-Card Set Identity And Revision Lineage | Done | `uv run ruff check src/trader_research/knowledge/domain.py src/trader_research/knowledge/method_cards.py src/trader_research/knowledge/storage.py src/trader_research/knowledge/store.py src/trader_research/knowledge/postgres_store.py src/trader/knowledge/schema.py src/trader/knowledge/store.py src/trader_mcp/constants.py src/trader_mcp/knowledge_tools.py src/trader_research/agents.py src/trader_research/strategy_candidates/services.py src/trader_research/risk_managers/services.py tests/test_method_cards.py tests/test_mcp_quant_methods_tools.py tests/test_agent_identities.py tests/test_knowledge_domain.py tests/test_postgres_knowledge_store.py`; `uv run pytest tests/test_method_cards.py tests/test_mcp_quant_methods_tools.py tests/test_agent_identities.py tests/test_knowledge_domain.py tests/test_research_agent_docs.py tests/test_tool_contracts.py -q`; `uv run pytest tests/test_mcp_server.py tests/test_mcp_tools.py tests/test_mcp_strategy_tools.py tests/test_mcp_risk_manager_tools.py tests/test_strategy_candidates.py tests/test_risk_manager_candidates.py -q`; `uv run pytest tests/test_mcp_rich_methodology_toolchain.py tests/test_methodology_candidates.py -q`; `uv run pytest tests/test_postgres_knowledge_store.py -q` skipped because the local Postgres fixture was unavailable; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents src/trader`; `uv run mypy` | Adds stable `method_card_set_id` lineage separate from immutable `method_card_id` revisions; persists revision numbers, supersession links, current approved/draft pointers, source fingerprints, set summaries, and pgAdmin-friendly active/history views. Draft, publish, lifecycle, strategy/risk generation, and method-card evidence regression work now preserve and consume set lineage rather than aggregating by volatile card IDs or candidate IDs. Legacy Postgres method-card rows without explicit set lineage are unsupported; no automatic compatibility backfill or synthetic legacy set IDs are used. |
| 33X. Target-Bound Evidence Units And Reingestion | Done | `python -m compileall -q src/trader_research/knowledge src/trader/knowledge`; `uv run ruff check ...`; `uv run pytest tests/test_knowledge_domain.py tests/test_knowledge_store.py tests/test_knowledge_services.py tests/test_methodology_candidates.py tests/test_mcp_quant_methods_tools.py tests/test_mcp_rich_methodology_toolchain.py tests/test_research_agent_docs.py tests/test_tool_contracts.py -q`; `uv run pytest tests/test_knowledge_records.py tests/test_postgres_knowledge_store.py -q` with the Postgres test skipped when the local fixture was unavailable. | Replaces coarse chunks as the primary methodology extraction/indexing surface with schema-v2 evidence units under the existing `chunk_id` API field. Evidence units have deterministic `knowledge_evidence_unit_*` IDs, parent section IDs, paragraph/sentence indexes, locator metadata, detected local method labels, neighbor refs, text hashes, `evidence_unit_id`, and `chunker_version`. JSON storage writes `knowledge_evidence_unit_manifest` and rejects legacy `knowledge_chunk_manifest` data rather than translating it; Postgres rows carry evidence-unit metadata in `knowledge_chunks`. Ingestion reports include evidence-unit count aliases while preserving current envelope fields. Forced ingestion now bypasses legacy evidence deserialization and directly replaces the source's active evidence set; `tests/test_knowledge_services.py` covers this no-compatibility reingestion path. |
| 33Y. Method Identity Discovery And Alias Binding | Done | Same verification as 33X, plus the rich MCP methodology regression. | Discovery now scans explicit source IDs directly over stored evidence units, extracts source-backed method identities from local labels, abbreviations, title-like headings, query phrases, and repeated local labels, then groups candidates by method identity rather than broad heading/family proximity. Candidate payloads carry `method_identity` with canonical/source names, aliases, abbreviations, identity evidence-unit refs, query alignment, context refs, and competing method-label diagnostics. Adjacent SMA/EWA/Bollinger/RSI-style source passages remain separate candidates without a maintained target registry. |
| 33Z. Target-Bound Evidence Packets And Extraction | Done | 33Y complete. | `knowledge_assemble_methodology_evidence` now annotates every role evidence ref with target-binding metadata, requires role terms plus an accepted target binding before readiness roles count, and carries weak/rejected neighboring evidence as diagnostics. Packet-backed extraction and validation readiness consume only accepted target-bound role refs. |
| 33AA. Semantic Method-Card Validation And Draft Gates | Done | `uv run pytest tests/test_methodology_candidates.py tests/test_method_cards.py -q`; `uv run pytest tests/test_mcp_quant_methods_tools.py tests/test_mcp_rich_methodology_toolchain.py tests/test_research_agent_docs.py tests/test_tool_contracts.py -q`; `uv run pytest tests/test_strategy_candidates.py tests/test_risk_manager_candidates.py tests/test_package_boundaries.py -q`; `python -m compileall -q src/trader_research/knowledge src/trader/knowledge` | Validation now requires packet-backed method identity lineage, blocks packet-less candidates from passing semantic validation, rejects fields that cite rejected or competing-method packet refs, detects stale packet source/locator/text hashes, and emits target-bound readiness summaries. Canonical method-card draft materialization rejects caller `method_id`, `title`, or `family` overrides unless candidate identity/alias/family evidence supports them and the candidate lineage matches the validation packet. |
| 33AB. Claim-Level Semantic Extraction And Ingestion Consistency | Done | `uv run pytest tests/test_knowledge_domain.py tests/test_knowledge_store.py tests/test_knowledge_services.py tests/test_postgres_knowledge_store.py tests/test_methodology_candidates.py tests/test_method_cards.py tests/test_mcp_quant_methods_tools.py tests/test_mcp_rich_methodology_toolchain.py tests/test_mcp_open_world_method_cards.py tests/test_research_agent_docs.py tests/test_tool_contracts.py tests/test_package_boundaries.py -q`; live Postgres MCP rerun for source `knowledge_source_0af8c59c04b6ddd2`, candidate `methodology_candidate_b62dc8ef3b7968e1`, packet `methodology_evidence_packet_b177f724cee389bc`, extraction `methodology_field_extraction_49c82571ffae047a`, validation `methodology_candidate_validation_b2e88f21980818aa` | Adds exact hashed claim spans inside reusable evidence units, target-conditioned local and cross-unit binding, field-specific semantic filters, bounded multi-span synthesis, and span-level validation. A shared unit can support multiple methods without exclusive ownership. The real book rerun removes Bollinger/RSI and overbought/oversold contamination from Moving Average Oscillator evidence, then correctly blocks implementation readiness because target-bound input evidence is missing. Ingestion stages embeddings before replacement and atomically publishes successful Postgres evidence, vector, manifest, and report generations. |
| 33AC. Composite Methodology Architecture | Deferred | The architectural direction is documented in `docs/research_agents/architecture.md`; implementation is deliberately paused after the 33AB baseline. | Future work may replace the single-family, local-span methodology assumption with claim-relationship graphs and atomic/composite method boundaries without hardcoded known targets. Existing knowledge and bounded extraction tools remain maintained; composite methodology expansion is not on the current delivery path. |
| 34. Supervisor Consumes Toolchain Artifacts | Not started |  | Add minimal supervisor handoff consumption after tasks 56-57 using implementation-version, strategy/risk/backtest specification, run, and performance-report refs. Method packages and rich cards remain optional specialist provenance, not Supervisor execution inputs. |
| 35. Quantitative Methods Agent Graph | Not started |  | Deferred until the source-backed method-to-backtest MCP toolchain is useful; graph should orchestrate existing Quant Methods MCP tools only. |
| 36. Supervisor LLM Control Loop | Not started |  | Deferred until the supervisor has useful method, strategy, backtest, and performance artifacts to assess. |
| 37. Hypothesis Card Service and MCP Tool | Not started |  | Deferred; structured hypothesis cards should build on the working method/strategy/backtest loop. |
| 38. Hypothesis Agent Graph and Handoff | Not started |  | Deferred until hypothesis cards are useful inputs to the proven toolchain. |
| 39. MLflow Predictive-Model Lifecycle Tool Universe | Planned | Umbrella for 39A-39J after external strategy implementation intake and reproducible backtest specifications. | Coordinate point-in-time feature engineering, time-series fitting, MLflow tracking/registry, immutable model versions, evaluation, deployment evidence, strategy integration, predictions, and drift without granting live-trading authority. |
| 39A. MLflow Runtime Adapter And Mutation Policy | Planned | Follows the provider-neutral 57H projection boundary. | Configure one approved MLflow instance for ML training telemetry, model packages, and Model Registry records; register the optional optimisation-projection sink; and gate projection writes, ML training writes, and alias promotion independently. MLflow is not canonical for generic studies or backtests. |
| 39B. Feature-Set Engineering And Validation | Planned | Follows 39A. | Add immutable feature-set specifications with feature source hashes, lookbacks, event/availability times, schemas, preprocessing scope, and no-lookahead validation. |
| 39C. Point-In-Time Training Datasets And Split Plans | Planned | Follows 39B. | Materialize Data-Agent-scoped training datasets and chronological walk-forward folds with target horizons, purge/embargo, dataset digests, and leakage reports. |
| 39D. Training Pipeline Registration And Fitting | Planned | Follows 39C. | Register maintained or supplied training pipelines, create bounded training specs, execute gated fitting, and log parameters, metrics, datasets, source refs, environments, and model packages to MLflow. |
| 39E. MLflow Run Reconciliation And Lineage | Planned | Implement with 39D. | Reconcile completed MLflow runs into DB-visible Trader refs, verify run/model/dataset/source identity, and fail closed on missing, partial, foreign, or inconsistent records. |
| 39F. Time-Series Model Evaluation And Comparison | Planned | Follows successful fitting. | Evaluate fold/holdout predictions, calibration, predictive stability, leakage, baselines, and uncertainty; keep model metrics separate from strategy PnL conclusions. |
| 39G. Model Registry Versioning And Promotion Evidence | Planned | Follows passed model evaluation. | Register immutable model versions, resolve aliases to pinned versions, compare candidates, and require an explicit gated promotion report before assigning aliases; do not use deprecated model stages. |
| 39H. Runtime Prediction Contract And MLflow Adapter | Planned | Required before strategy integration. | Add MLflow-independent core prediction interfaces plus an optional MLflow loader/serving adapter, signature checks, feature parity fixtures, latency bounds, and explicit failure policies. |
| 39I. Model-Backed Strategy And Deployment Integration | Planned | Follows 39H. | Create version-pinned deployment manifests, bind validated predictors into maintained or registered strategies, prove backtest/runtime parity, and restrict initial deployment eligibility to backtest and paper environments. |
| 39J. Prediction Monitoring And Drift | Planned | Follows model-backed execution evidence. | Persist bounded prediction events with model/feature versions and compute input, output, calibration, performance, latency, and stale-feature/model drift reports without MCP calls in the hot path. |
| 40. ML Agent Graph and Handoff | Deferred | Implement only after 39A-39J deterministic services are proven. | The graph coordinates ML tools and returns ML-owned artifact refs; it cannot choose hidden data scope, execute arbitrary prompt text, approve final strategy performance, move aliases without policy, or mutate live trading. |
| 41. Attribution Service and MCP Tool | Not started |  | Follow-on analysis after baseline backtests and performance reports exist. |
| 42. Evaluation Critique Logic and MCP Tool | Not started |  | Extend beyond the first performance report into skeptical evaluation rules, data-quality blockers, cost sensitivity, and sample-size critique. |
| 43. Evaluation Agent Graph and Handoff | Not started |  | Deferred until Evaluation-owned MCP reports are useful. |
| 44. Adversarial Robustness Core and MCP Tool | Planned | Optimisation-specific audit planning/judgment is delivered in 57F; general backtest attacks remain. | Generalise the independent plan/execute/judge pattern to cost, split, concentration, parameter, and data perturbations over immutable canonical runs. Adversarial plans and judges; Supervisor executes variants. |
| 45. Adversarial Agent Graph and Handoff | Not started |  | Deferred until robustness tools are useful. |
| 46. Robustness Backtest Variants | Planned | Implement with or immediately after task 44 using the 57F variant contract. | Add Supervisor-executed fee, slippage, parameter, data-window, provider/seed/budget/objective, and perturbation variants that preserve baseline lineage and change only declared assumptions. |
| 47. Recommendation Renderer and MCP Tool | Not started |  | Deferred until performance, critique, and robustness artifacts can be consumed. |
| 48. Quant Research Supervisor Synthesis Graph | Not started |  | Deferred synthesis layer over proven specialist artifacts. |
| 49. Experiment Runner and MCP Tool | Not started |  | Last-mile orchestrator; compose earlier tools rather than becoming the first proof of the workflow. |
| 50. Compiled Kernel Conformance and Runtime Acceleration | Not started |  | Deferred performance work: contract-first C++ conformance/equivalence and runtime integration only after profiling shows value. |
| 51. Import Boundary Tests | Not started |  | Keep architectural separation executable as new strategy/backtest/report services are added. |
| 52. MCP, Toolchain, and LangGraph Contract Tests | Not started |  | Expand contract tests around tool names, schemas, side effects, envelope shapes, owners, and later graph boundaries. |
| 53. Iterative Documentation | Done | `uv run pytest tests/test_research_agent_docs.py -q`; `rg -n "backtest tools are not registered yet|No backtest tool is exposed|Planned:" docs/research_agents --glob '!history/**'`; `uv run pytest tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py -q`; `uv run ruff check tests`; `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents` | Research-agent docs are restructured into canonical current docs for architecture, agents, MCP tools, workflows, and operations. Superseded docs moved under `docs/research_agents/history/`; current docs are checked against registered MCP tools and agent identities. |
| 56. Implementation Registry And Method-Card Decoupling | Done | Implemented with the 57A-C atomic cutover. | Canonical execution begins at immutable implementation versions. Methodology refs are optional generic provenance and candidate artifacts are not registered execution inputs. |
| 56A. Canonical Implementation-Version Domain | Done | `src/trader_research/implementations/` plus Postgres projections. | Adds content-addressed DB-backed implementation versions for indicator, signal, strategy, risk-manager, and optimisation-objective kinds without knowledge-domain imports. |
| 56B. Strategy And Risk Implementation Registration And Validation | Done | Registered MCP intake and deterministic validation. | Handwritten, AI-produced, maintained, or method-generated source uses the same hash/interface/parameter/resource/no-live-trading checks; no methodology ref is required. |
| 56C. Maintained And Method-Generated Producer Adapters | Done | Producer-neutral registration accepts `authoring_origin` and generic `provenance_refs`. | Producers submit source to the same registry; origin affects lineage only and cannot change downstream eligibility. |
| 56D. Remove Method-Card Execution Coupling | Done | Atomic no-compatibility cutover. | Candidate create/validate, candidate stack, and candidate backtest tools are no longer registered or supported artifact types. Canonical execution packages do not import knowledge types. |
| 57. Reproducible Strategy, Risk, Backtest, And Optimisation Specifications | In progress | 57K-R is removing the stale candidate-era surface and warning failures found by the first 57K run. A replacement 57I freeze and rerun of 57J-K are required before 57L. | Immutable Postgres specifications, runs, trial ledgers, projections, Evaluation, and Adversarial refs compose without provider authority or filesystem identity; the slice is complete only after mandatory verification passes. |
| 57A. Strategy And Risk Specifications | Done | Canonical DB-backed services and MCP tools. | Adds data-scope-free strategy and ordered risk-stack specifications over passed implementation validations. |
| 57B. Reproducible Backtest Specifications | Done | Canonical DB-backed services and MCP tools. | Binds passed behavior to exactly one Data Agent manifest, quality snapshot, costs, assumptions, seed, limits, and lineage before execution. |
| 57C. DB-First Specification Execution And Evaluation | Done | Canonical specification runner and result services. | Executes only passed specifications and stores complete baseline/portfolio result evidence in `backtest_run`; no canonical filesystem bundle or candidate request form remains. |
| 57D. Provider-Neutral Optimisation Ledger And Protocols | Done | `src/trader_research/optimization/contracts.py` and typed Postgres projections. | Adds `OptimizationEngine`, `OptimizationTrialExecutor`, and `ExperimentTrackingSink`; canonical plans/runs/trials pin engine identity while provider state remains operational only. |
| 57E. Validated Optimisation Objectives | Done | Quantitative Methods registration/validation tools. | Adds `optimization_objective` implementation versions and the closed `OptimizationObservation`; objective code has no artifact, database, filesystem, network, raw-event, or tool input. |
| 57F. Deterministic Optimisation Execution And Independent Review | Done | Grid/random execution, MCP services, Evaluation, and Adversarial tools. | Persists every proposal, attempt, failure, observation, objective result, child ref, selection, and tie-break; holdout Evaluation and Adversarial audit remain separate and cannot rewrite selections. |
| 57G. Optional Optuna Adapter | Done | Lazy optional adapter and runtime profile. | Adds seeded sequential single-objective TPE behind the provider-neutral protocol, dedicated schema/role checks, canonical reconciliation, no pruning, and fail-closed provider loss/drift. |
| 57H. Provider-Neutral Experiment Tracking Projection | Done | Explicit `research_project_experiment_tracking`. | Derives an idempotent, non-authoritative projection from canonical evidence. The optional MLflow sink is independently gated and deletion/unavailability cannot affect Trader reads. |
| 57I. Freeze Revision And Build Acceptance Matrix | In progress | The first freeze was invalidated by 57K; replacement tag will be `verification-57i-freeze-v2`. | Freeze the cleaned product only after strict static/non-Postgres verification passes. |
| 57J. Provision Isolated Verification Runtime | Blocked | Requires the replacement 57I freeze and disposable control-schema reset. | Reprovision from scratch and record separate isolation and qualification results. |
| 57K. Static, Contract, And Regression Gate | Blocked | Ruff, compileall, mypy, 691 non-Postgres tests, 60 focused contract tests, and diff checks passed; operator fingerprints matched. Strict warnings and retired-surface audits failed. | Remove candidate-era domain models/direct services/readers/current docs/tests, add absence regressions, replace deprecated FastAPI/Pydantic calls, resolve or explicitly isolate the Alpaca/websockets import warning, then repeat 57I-J-K. 57L must not begin against the current freeze. |
| 57K-R. Candidate Retirement And Warning Remediation | In progress | Implements the no-compatibility cleanup required by the failed 57K gate. | Separate qualification and isolation verdicts; preserve only neutral maintained-template discovery; delete retired candidate/stack/bundle contracts; fix FastAPI/Pydantic warnings; isolate the upstream Alpaca live import warning; add absence regressions; update active docs; then replace the 57I freeze and rerun 57J-K. |
| 57L. Realistic Deterministic Evidence Fixture | Planned | Requires 57K. | Add a bounded multi-asset chronological dataset and handwritten strategy/risk/objective implementations that produce actual trades, nonzero exposure and costs, parameter-sensitive results, and both risk approvals and rejections across disjoint selection and holdout regions. |
| 57M. Postgres-Native MCP Evidence Graph | Planned | Requires 57L. | Execute the full implementation -> specification -> selection backtest -> objective -> optimisation -> selected specification -> sealed holdout -> Evaluation -> Adversarial variants/report chain through MCP with only `research://postgres/...` canonical refs. |
| 57N. Determinism, Integrity, And Leakage Tests | Planned | Requires 57M. | Repeat clean runs and verify stable IDs, trial order, observations, tie-breaks, and selection; prove complete failed-trial evidence, immutable selections, source/config drift rejection, distinct selection/holdout hashes, and no holdout access during optimisation. |
| 57O. Restart, Resume, And Fault-Injection Tests | Planned | Requires 57N. | Interrupt after persisted phase boundaries, recreate service processes, resume without duplicate trials, exercise bounded retry/timeout/provider-loss paths, and prove partial or blocked runs remain inspectable and cannot be silently continued under changed configuration. |
| 57P. Provider Independence And Adapter Qualification | Planned | Requires 57O. | Prove built-in grid/random and canonical reads with Optuna/MLflow unavailable; separately qualify Optuna schema isolation/reconciliation and each tracking sink's idempotence, deletion tolerance, and non-authority before enabling that profile. |
| 57Q. Policy, Security, And Resource-Boundary Tests | Planned | Requires 57O; may run in parallel with profile-specific 57P checks. | Verify independent gates, closed objective inputs, forbidden filesystem/network/database/tool access, immutable dataset/implementation/cost/holdout boundaries, run budgets/timeouts, SQL/package boundaries, and absence of canonical filesystem artifacts. |
| 57R. Projection, Operator, And Bounded-Scale Checks | Planned | Requires 57M, 57N, and 57Q. | Reconcile canonical JSONB with every typed pgAdmin projection, run bounded multi-symbol grid/random loads within declared resource limits, inspect query/storage behavior, and prove cleanup affects only the verification database/provider namespace. |
| 57S. Acceptance Record And Release Decision | Planned | Final verification task; requires all mandatory profiles and every provider profile intended for use. | Record the exact revision, environment/profile digests, commands, results, skips, evidence refs, row counts, operator DB fingerprints, defects, and residual risks. Mark task 57 done only when mandatory blockers are empty; optional profiles receive independent qualified/not-qualified status. |
| 58. Walk-Forward Optimisation Core | Deferred | Implement after model-backed strategy integration through 39I and general robustness primitives 44/46. | Compose the same provider-neutral optimisation protocol inside each immutable fold; lock each selected parameter/model before untouched out-of-sample execution and preserve every child specification/run ref. |
| 59. Walk-Forward Evaluation And Adversarial Audit | Deferred | Follows task 58 and consumes completed walk-forward runs. | Evaluation aggregates stitched out-of-sample evidence; Adversarial independently audits fold-boundary sensitivity, parameter/model instability, neighboring choices, costs, concentration, degradation, and selection bias. Neither tool changes the selected implementation or promotes it. |
| 60. Calendar-Aware Data Quality | Not started | AMD 12-month `1Min` MCP run exposed wall-clock gap overcounting in `artifacts/research/amd_12mo_1min_data_agent_quality_full_2026-05-28.json` | Later backlog item: add market-calendar/session-aware expected-bar and gap classification for stocks so nights, weekends, holidays, early closes, and feed/session windows are not reported as missing data. Preserve warnings for true intra-session gaps and coverage edges. |

## Current Delivery Priority After 33AB

Knowledge-base creation and bounded method extraction are pinned at the 33AB baseline. Their registered MCP tools remain
supported, Postgres-first product surfaces, but new composite-method and autonomous semantic-extraction work is deferred
under 33AC. Data Agent inventory, quality, manifest, and gated loading tools also remain maintained dependencies.

The completed foundation and active implementation order are:

1. `57I-57S`: freeze and qualify the implementation-complete 56/57 cutover through the controlled core/Postgres acceptance profile;
   keep Optuna and each tracking sink disabled until its independent adapter profile passes.
2. `56A-56D` and `57A-57H` are implementation-complete: implementation/specification intake, canonical backtests,
   provider-neutral optimisation, independent review, and disposable tracking projection form the system under test.
3. `44` and `46`: generalise the delivered optimisation audit split so Adversarial plans and judges attacks while the
   Supervisor executes immutable backtest and optimisation variants.
4. `39A-39J`: add the MLflow lifecycle from point-in-time feature engineering and gated fitting through immutable model
   versions, deployment manifests, strategy integration, prediction events, and drift.
5. `58` and `59`: compose the provider-neutral optimisation protocol inside each fold and add independent
   Evaluation/Adversarial interpretation only after the
   implementation, ML, and robustness foundations are proven.
6. `41` and `42`: deepen attribution and skeptical Evaluation once the new baseline/variant evidence is available.

Agent graphs, recommendation synthesis, and high-level experiment orchestration remain deferred until these direct tools
are proven. Source-code generation remains available only as a quarantined bounded path; it is no longer the assumed
entry point for strategy evidence.

## Proposed Package Shape

```text
src/trader_research/
  __init__.py
  agents.py             # Agent/tool ownership metadata from agents.md
  domain.py              # Shared experiment, report, verdict, and artifact-reference types
  contracts.py           # ToolEnvelope, side-effect declarations, shared JSON helpers
  data.py                # Data Agent inventory, manifests, quality, and loading wrappers
  math_domain.py         # Quantitative Methods artifact schemas and validation
  math_registry.py       # Maintained method registry and approved families
  math_tools.py          # Quantitative Methods service wrappers and envelopes
  method_implementations.py # Python implementation manifests, entrypoint allowlists, source hashes, and fixture validation
  signal_diagnostics.py  # IC, rank IC, hit-rate, quantile, decay, and breakdown reports
  multiple_testing.py    # Multiple-testing and data-snooping controls
  cpp_kernel_artifacts.py # Template-restricted compiled-kernel manifests; runtime acceleration is deferred
  method_packages.py      # Method package manifests for source-backed validated implementations
  knowledge/
    __init__.py
    domain.py            # Source, chunk, embedding, method-card, retrieval, and citation schemas
    sources.py           # Source registration, approval status, and metadata validation
    extractors.py        # PDF, Markdown, and text extraction adapters
    chunking.py          # Chunk creation and locator preservation
    embeddings.py        # Embedding provider protocol plus runtime/test implementations
    store.py             # KnowledgeStore interface plus JSON compatibility adapter
    postgres_store.py    # Adapter from research domain objects to core Postgres knowledge persistence
    index.py             # Embedding indexing, hybrid retrieval, and deterministic rank fusion
    retrieval.py         # Hybrid retrieval, rank fusion, method-card search, and evidence services
    citation_validation.py # Source/locator/method-card coverage checks
    method_cards.py      # Draft and publish method-card workflow
    ingestion.py         # End-to-end ingestion orchestration
  implementations/
    __init__.py          # Canonical implementation registration and validation exports
    domain.py            # Immutable implementation versions and validation reports
    registration.py      # Postgres-first source/package registration
    validation.py        # Interface, fixture, dependency, resource, and safety validation
  specifications/
    __init__.py          # Canonical strategy/risk/backtest specification exports
    strategy.py          # Implementation version plus validated strategy parameters/behavior
    risk.py              # Ordered risk implementation versions and explicit policy parameters
    backtest.py          # Data Agent scope, costs, assumptions, seeds, and runtime policy
  backtests/
    __init__.py          # Specification-only execution, result lookup, and comparison exports
    execution.py         # Baseline/risk-scoped BacktestRunner adapter
    results.py           # DB-backed run payloads, sidecars, retrieval, and comparison
  ml/
    __init__.py          # Canonical ML lifecycle service exports
    domain.py            # Feature, dataset, split, training, run, model, deployment, prediction, and drift artifacts
    features.py          # Point-in-time feature-set specifications and validation
    datasets.py          # Training datasets, targets, chronological folds, purge/embargo, and leakage checks
    training.py          # Validated trainer registration, bounded specs, and fitting orchestration
    tracking.py          # MLflow run reconciliation and lineage
    evaluation.py        # Time-series predictive evaluation and model comparison
    registry.py          # Immutable model versions, tags, aliases, and promotion evidence
    deployment.py        # Version-pinned inference/deployment manifests and validation
    monitoring.py        # Prediction summaries and drift analysis
  hypotheses.py          # Hypothesis-card creation and validation
  attribution.py         # Return attribution summaries
  robustness.py          # Robustness suite and concentration checks
  evaluation.py          # Evaluation Agent critique logic
  reports.py             # Markdown and JSON report rendering
  suites.py              # Research suite expansion
  recommendations.py     # Conservative scoring/ranking
  artifacts.py           # Research artifact loading/writing
  promotion.py           # Human-approved paper-promotion packet builder, future phase
  runner.py              # ResearchExperimentRunner orchestration

src/trader_mcp/
  __init__.py
  server.py              # MCP server factory and tool registration
  knowledge_tools.py     # MCP registrations/adapters for Quant Methods knowledge tools
  schemas.py             # MCP-facing request/response models if needed
  adapters.py            # ToolEnvelope <-> MCP response helpers
  settings.py            # Config path, artifact root, read/write policy

src/trader/
  knowledge_store.py     # SQL-owning Postgres knowledge tables, full-text search, and pgvector retrieval
  predictions/           # Dependency-neutral predictor, feature batch, result, identity, event, and failure contracts

src/trader_mlflow/
  client.py              # Optional configured MLflow tracking/registry adapter
  inference.py           # Pinned local-model or serving-endpoint predictor implementation

src/trader_agents/
  __init__.py
  identities.py          # Agent identities, role policies, and tool allowlists
  state.py               # LangGraph state schemas per agent
  tool_client.py         # MCP client wrappers used by LangGraph nodes
  llm_client.py          # Provider-neutral LLM client protocol, config, and test fake
  data_agent.py          # Data Agent graph
  data_agent_policy.py   # Typed Data Agent LLM decisions and deterministic routing validation
  quant_research.py      # Quant Research graph and handoffs
  supervisor_policy.py   # Typed supervisor LLM decisions and deterministic routing validation
  evaluation_agent.py    # Evaluation Agent graph
  adversarial_agent.py   # Adversarial Agent graph
  hypothesis_agent.py    # Hypothesis-card graph
  quant_methods_agent.py # Quantitative Methods graph
  quant_methods_policy.py # Typed Quantitative Methods LLM decisions and deterministic routing validation
  ml_agent.py            # ML graph

tests/
  test_research_domain.py
  test_knowledge_domain.py
  test_knowledge_sources.py
  test_knowledge_extraction.py
  test_knowledge_embeddings.py
  test_knowledge_index.py
  test_knowledge_retrieval.py
  test_citation_validation.py
  test_method_cards.py
  test_mcp_knowledge_tools.py
  test_agent_identities.py
  test_research_runner.py
  test_research_robustness.py
  test_research_reports.py
  test_mcp_tools.py
  test_langgraph_agents.py
```

Migration rule: after the separation is complete, `trader_research` may import from `trader` and `trader_standard`, `trader_mcp` may import from `trader_research`, and `trader_agents` may use MCP clients/tools. `trader` must not import from `trader_research`, `trader_mcp`, `trader_agents`, or any agent/tool package.

## MCP Tool Set

### Initial Data Agent Evidence Tools

These are the Data Agent tools that prove MCP functionality before broader Quant Research foundations are built:

| Tool | Owning agent | Side Effect | Artifact / Purpose |
| --- | --- | --- | --- |
| `data_get_inventory` | Data Agent | `read_only` | Produce a dataset manifest-style envelope with source, symbols, timeframe, window, row counts, and warnings. |
| `data_summarize_quality` | Data Agent | `read_only` | Produce or load `data_quality_report.json`. |
| `data_ensure_loaded` | Data Agent | `local_mutating` | Verify, sample-load, or explicitly backfill bounded data and return load evidence. |

### Planned Research Tools

| Tool | Owning agent | Side Effect | Artifact / Purpose |
| --- | --- | --- | --- |
| `knowledge_register_source` | Quantitative Methods Agent | `local_mutating` | Register document metadata, compute file hash, and persist a source manifest in the configured knowledge store. |
| `knowledge_ingest_documents` | Quantitative Methods Agent | `local_mutating` | Extract text, chunk, create real embeddings, update Postgres lexical/vector indexes, and produce `knowledge_ingestion_report.json`. |
| `knowledge_get_ingestion_status` | Quantitative Methods Agent | `read_only` | Fetch source/ingestion status, warnings, parser details, embedding metadata, and indexed chunk counts. |
| `knowledge_list_sources` | Quantitative Methods Agent | `read_only` | List source manifests by topic, source type, method family, approval/index status, or access policy. |
| `knowledge_search_methods` | Quantitative Methods Agent | `read_only` | Search approved method cards and optionally draft method cards when policy permits. |
| `knowledge_retrieve_evidence` | Quantitative Methods Agent | `read_only` | Run hybrid PostgreSQL full-text/pgvector retrieval with deterministic rank fusion and return citeable chunks for a method, assumption, implementation convention, or statistical test. |
| `knowledge_get_evidence_chunks` | Quantitative Methods Agent | `read_only` | Dereference retrieved chunk IDs into bounded real stored chunk text with source metadata, locators, hash verification, and truncation flags. |
| `knowledge_discover_methodology_candidates` | Quantitative Methods Agent | `local_mutating` | Discover candidate methodology spans from ingested sources using retrieval, neighboring chunks, source metadata, and deterministic grouping; write DB-backed `methodology_candidate` refs without creating approved methods. |
| `knowledge_extract_methodology_fields` | Quantitative Methods Agent | `local_mutating` | Populate nullable rich methodology fields from candidate spans, preserving nulls for unsupported fields and attaching field-level evidence refs to every populated claim. |
| `knowledge_validate_methodology_candidate` | Quantitative Methods Agent | `local_mutating` | Validate field-level citations, source suitability, unsupported-claim blockers, and family-specific minimum evidence before rich method-card draft creation; write DB-backed validation reports. |
| `knowledge_create_method_card_draft` | Quantitative Methods Agent | `local_mutating` | Create a non-approved draft method card from retrieved source evidence. |
| `knowledge_create_rich_method_card_draft` | Quantitative Methods Agent | `local_mutating` | Create a non-approved rich method-card draft from a passed methodology-candidate validation report with nullable field groups and field-level evidence refs. |
| `knowledge_publish_method_card` | Quantitative Methods Agent | `local_mutating` | Promote a draft method card to approved status after explicit maintainer/operator approval. |
| `knowledge_update_method_card_status` | Quantitative Methods Agent | `local_mutating` | Mark a persisted method card rejected or superseded while preserving the stored audit record. |
| `knowledge_validate_citations` | Quantitative Methods Agent | `read_only` | Validate source IDs, chunk IDs, locators, method-card approval, and claim coverage for a contract/report. |
| `math_list_method_contracts` | Quantitative Methods Agent | `read_only` | Return maintained indicators, transforms, statistical tests, diagnostics, multiple-testing methods, assumptions, and metadata requirements. |
| `math_validate_method_contract` | Quantitative Methods Agent | `read_only` | Validate method parameters, input schema, warmup behavior, assumptions, fixture expectations, and failure modes. |
| `math_register_method_implementation` | Quantitative Methods Agent | `local_mutating` | Register a Python reference implementation manifest with entrypoint, source hash, dependency allowlist, safety profile, method contract refs, and approved method-card refs. |
| `math_generate_python_method` | Quantitative Methods Agent | `local_mutating` | Create a quarantined Python reference artifact from an approved method card/contract and immediately require fixture validation before use. |
| `math_run_indicator_fixtures` | Quantitative Methods Agent | `local_mutating` | Run deterministic fixtures against a registered Python reference implementation and produce `indicator_validation_report.json`. |
| `math_run_signal_fixtures` | Quantitative Methods Agent | `local_mutating` | Run deterministic latest-first bar fixtures against a registered `trader.signals.Signal` implementation and produce a signal implementation validation report. |
| `math_run_signal_diagnostics` | Quantitative Methods Agent | `local_mutating` | Produce `signal_diagnostic_report.json` from declared signal observations and forward-return labels. |
| `math_run_multiple_testing_report` | Quantitative Methods Agent | `local_mutating` | Produce a Benjamini-Hochberg `multiple_testing_report.json` for a declared candidate family and metric matrix. |
| `math_generate_cpp_kernel` | Quantitative Methods Agent | `local_mutating` | Generate C++ only from approved deterministic templates after a validated Python reference exists. |
| `math_compile_kernel` | Quantitative Methods Agent | `local_mutating` | Compile an approved kernel locally and return build evidence. |
| `math_package_method_artifact` | Quantitative Methods Agent | `local_mutating` | Bundle source-backed validated Python indicator/signal implementations, contracts, validation reports, and provenance for handoff. |
| `math_run_cpp_conformance` | Quantitative Methods Agent | `local_mutating` | Deferred: check contract-first C++ implementation conformance/equivalence only when compiled acceleration becomes valuable. |
| `ml_get_runtime`, `ml_health`, `ml_list_training_experiments` | ML Agent | `read_only` | Inspect the configured ML training/registry runtime without accepting caller-supplied connection targets. The old generic list name is not retained. |
| `ml_create_feature_set`, `ml_validate_feature_set` | ML Agent | `local_mutating` | Write and validate immutable point-in-time feature specifications with source hashes and runtime schema. |
| `ml_create_training_dataset`, `ml_create_time_series_split_plan` | ML Agent | `local_mutating` | Bind Data Agent refs to point-in-time targets, chronological folds, purge/embargo, dataset digests, and leakage reports. |
| `ml_register_training_pipeline`, `ml_validate_training_pipeline`, `ml_create_training_spec` | ML Agent | `local_mutating` | Register immutable trainer code and bounded fitting configuration without executing prompts or unvalidated packages. |
| `ml_run_training` | ML Agent | `external_research_mutating` | Run explicitly gated fitting and record datasets, parameters, metrics, artifacts, signatures, and models in MLflow. |
| `ml_get_training_run`, `ml_reconcile_mlflow_run` | ML Agent | `read_only` / `local_mutating` | Read MLflow run state and persist verified Trader lineage refs. |
| `ml_evaluate_model`, `ml_compare_model_versions` | ML Agent | `local_mutating` | Produce time-series predictive evaluation and comparison evidence without strategy PnL verdicts. |
| `ml_register_model_version`, `ml_get_model_version`, `ml_list_model_versions`, `ml_resolve_model_alias` | ML Agent | `external_research_mutating` / `read_only` | Register or inspect immutable versions and resolve mutable aliases to pinned refs. |
| `ml_assign_model_alias` | ML Agent | `external_research_mutating` | Assign an alias only with a passed promotion report, expected-current-version check, and explicit promotion gate. |
| `ml_create_deployment_manifest`, `ml_validate_deployment` | ML Agent | `local_mutating` | Create and validate version-pinned backtest/paper inference configuration without mutating live runtime. |
| `ml_summarize_predictions`, `ml_compute_drift_report` | ML Agent | `local_mutating` | Summarize persisted prediction events and write version-aware drift evidence outside the trading hot path. |
| `hypothesis_create_card` | Hypothesis Agent | `read_only` | Produce `hypothesis_card.json` from structured input. |
| `research_create_plan` | Quant Research Supervisor Agent | `read_only` | Convert a hypothesis card or structured request into an explicit experiment plan. |
| `research_list_strategy_templates` | Quant Research Supervisor Agent | `read_only` | Return supported maintained strategy families and parameter schemas. |
| `research_create_strategy_candidate` | Quant Research Supervisor Agent | `local_mutating` | Compose validated method/signal packages with a maintained strategy template into an importable strategy source file plus `strategy_candidate_manifest.json`. |
| `research_validate_strategy_candidate` | Quant Research Supervisor Agent | `local_mutating` | Validate a bounded strategy candidate before any backtest and write `strategy_candidate_validation_report.json`. |
| `research_list_risk_manager_templates` | Quant Research Supervisor Agent | `read_only` | Return source-generatable risk manager templates for exposure limits, concentration limits, drawdown controls, and VaR/CVaR-style filters. |
| `research_create_risk_manager_candidate` | Quant Research Supervisor Agent | `local_mutating` | Compose optional validated method packages and bounded risk parameters into an importable backtest-only risk manager source file plus `risk_manager_candidate_manifest.json`. |
| `research_validate_risk_manager_candidate` | Quant Research Supervisor Agent | `local_mutating` | Validate generated risk-manager source against the `trader.risk` runtime contract before strategy/risk stack use. |
| `research_create_strategy_risk_stack` | Quant Research Supervisor Agent | `local_mutating` | Compose one validated strategy candidate with one or more validated risk-manager candidates into a strategy/risk stack manifest. |
| `research_validate_strategy_risk_stack` | Quant Research Supervisor Agent | `local_mutating` | Smoke-test a strategy/risk stack over a deterministic multi-asset fixture and write `strategy_risk_stack_validation_report.json`. |
| `research_run_backtest` | Quant Research Supervisor Agent | `local_mutating` | Run one reproducible baseline backtest and export result artifacts. |
| `research_run_portfolio_backtest` | Quant Research Supervisor Agent | `local_mutating` | Planned: run a multi-asset backtest from a Data Agent dataset manifest using a validated strategy/risk stack and export portfolio/risk evidence. |
| `research_get_backtest_results` | Quant Research Supervisor Agent | `read_only` | Fetch summary metrics, warnings, and artifact paths for a backtest run. |
| `evaluation_generate_performance_report` | Evaluation Agent | `local_mutating` | Produce the first practical `evaluation_report.json` from data quality, backtest metrics, assumptions, warnings, and blockers. |
| `evaluation_generate_report` | Evaluation Agent | `local_mutating` | Later skeptical critique report that extends the first performance report with stronger evaluation policy. |
| `adversarial_run_robustness` | Adversarial Agent | `local_mutating` | Produce `robustness_report.json` through slippage, fee, split, perturbation, and concentration attacks. |
| `research_analyze_return_attribution` | Quant Research Supervisor Agent | `read_only` | Summarize PnL by symbol, period, side if available, and top trades. |
| `research_generate_recommendation` | Quant Research Supervisor Agent | `local_mutating` | Produce recommendation report by synthesizing experiment, evaluation, and robustness artifacts. |
| `research_run_experiment` | Quant Research Supervisor Agent | `local_mutating` | High-level orchestrator for the full workflow; should compose earlier tools and run last. |

Backward-compatible aliases may be retained initially:

| Alias | Canonical behavior |
| --- | --- |
| `math_list_indicator_contracts` | Calls `math_list_method_contracts` filtered to indicator and transform families. |
| `math_validate_indicator_contract` | Calls `math_validate_method_contract` filtered to indicator and transform families. |

### Explicitly Out of Scope

- `place_order`, `cancel_order`, `start_trading`, `clear_halt`, or any broker-mutating tool.
- Raw SQL execution.
- Open-ended code execution from an MCP prompt.
- Automatic strategy search loops that keep optimizing until a result looks good.
- Persisting raw agent conversations as first-class database records.

## Incremental Tasks

| Chunk | Description | Files Affected | Acceptance Criteria |
| --- | --- | --- | --- |
| 0. Boundary Recon | Re-read the brief, current `trader.research`, current `trader.tools.*`, `trader.backtest`, `trader.data`, and current docs. Classify only the minimum code needed for first data-tool evidence, then separately note what should move later. | Docs and source only | Short notes identify the smallest first MCP data slice and the later migration candidates. |
| 1. Clean Package Skeleton | Add tracked source files for `trader_research`, `trader_mcp`, and `trader_agents`. Include lightweight agent ownership metadata aligned with `agents.md`. | `src/trader_research/*`, `src/trader_mcp/*`, `src/trader_agents/*` | Packages import cleanly; no behavior depends on untracked/generated files; Data Agent ownership can be represented in tool metadata and LangGraph identity metadata. |
| 2. Minimal Tool Contracts | Create the minimal `ToolEnvelope`, `SideEffect`, agent owner, artifact reference, and JSON helper surface needed for the first MCP data tool. Do not migrate every historical helper yet. | `src/trader_research/contracts.py`, tests | The first Data Agent tool can return a stable envelope from `trader_research.contracts`. |
| 3. MCP Envelope Adapter | Add small adapter helpers for converting `trader_research.contracts.ToolEnvelope` values into MCP tool responses. | `src/trader_mcp/adapters.py` | The adapter can return the envelope as MCP-compatible structured content. |
| 4. MCP Server Skeleton | Add MCP server startup with a stdio transport and register read-only health/config tools before any broad research schemas or backtest work. | `src/trader_mcp/server.py`, `pyproject.toml`, tests | `uv run python -m trader_mcp.server` starts; an MCP-capable client can list at least health/config tools. |
| 5. Data Inventory Service | Implement the smallest useful Data Agent `get_data_inventory` service against existing market-data/event-store interfaces. Start with symbol/timeframe/window validation, source metadata, bar counts, and dataset manifest payload. | `src/trader_research/data/`, tests | Missing data produces warnings and does not silently pass as complete; output can be saved as or embedded in `dataset_manifest.json`. |
| 6. Register Data Inventory MCP Tool | Expose `data_get_inventory` immediately after the service exists. | `src/trader_mcp/server.py`, `tests/test_mcp_tools.py` | Tool inputs are validated; output uses the shared envelope and declares `agent_owner=Data Agent`. |
| 7. First MCP Tool Evidence | Run and document the first evidence loop: MCP server boots, client lists tools, client calls `data_get_inventory`, and receives a valid Data Agent envelope. | `docs/research_agents/history/mcp_trading_research_tools.md`, tests or command output | There is reproducible MCP evidence before data-quality, loading, strategy, backtest, or report work begins. |
| 8. LangGraph Agent Identity Skeleton | Add LangGraph identity scaffolding: agent registry, state base, MCP tool client wrapper, and per-agent tool allowlist model. | `src/trader_agents/*`, tests | A Data Agent graph can be instantiated with a distinct identity and only the allowed MCP tools. |
| 9. Data Agent Inventory Graph | Implement the first Data Agent LangGraph graph using `data_get_inventory` through the MCP client. | `src/trader_agents/data_agent.py`, tests | The graph returns Data Agent state with dataset manifest payload/artifact reference and does not call platform internals directly. |
| 10. Data Quality Service | Implement Data Agent `summarize_data_quality` as a wrapper around existing data-quality checks and report writing. | `src/trader_research/data/`, tests | Tool can produce `data_quality_report.json` with missing bars, duplicate bars, suspicious prices, and symbol-level coverage when the underlying platform can detect them. |
| 11. Register Data Quality MCP Tool | Expose `data_summarize_quality` as soon as the service works. | `src/trader_mcp/server.py`, `tests/test_mcp_tools.py` | MCP smoke test returns a Data Agent quality envelope and optional `data_quality_report.json` artifact path for sample/existing data. |
| 12. Extend Data Agent Graph for Quality | Add a Data Agent LangGraph node that calls `data_summarize_quality` and updates quality state. | `src/trader_agents/data_agent.py`, tests | The Data Agent graph can run inventory -> quality through MCP and return both artifact references. |
| 13. Data Ensure/Loading Service | Implement Data Agent `ensure_market_data` as an explicit policy wrapper around existing sample/backfill/existing modes. Require bounded symbols, timeframe, and date window. | `src/trader_research/data/`, tests | Backfill/sample modes are opt-in; unpermitted missing data returns a failed envelope; successful loads return dataset/load evidence. |
| 14. Register Data Loading MCP Tool | Expose `data_ensure_loaded` with clear side-effect metadata and bounded-write guardrails. | `src/trader_mcp/server.py`, `tests/test_mcp_tools.py` | MCP smoke test can run dry-run/plan mode and sample-load mode; live backfill remains explicit and bounded. |
| 15. Extend Data Agent Graph for Loading | Add a Data Agent LangGraph node that can call `data_ensure_loaded` only when policy permits mutation. | `src/trader_agents/data_agent.py`, tests | The Data Agent graph preserves load policy in state and refuses unbounded or unapproved writes. |
| 16. Data MCP and LangGraph Workflow Evidence | Run and document the complete Data Agent workflow: health -> inventory -> quality -> ensure/load -> quality, all through MCP tools and the Data Agent graph. | `docs/research_agents/history/mcp_trading_research_tools.md`, tests or command output | A developer can reproduce data-tool MCP evidence and Data Agent LangGraph identity evidence without strategy/backtest/report implementation. |
| 17. Move Shared Tool Contracts | Move or delete the old `trader.tools.contracts` surface after the replacement contract is proven through MCP and the Data Agent graph. Update CLIs/tests that should remain. | `src/trader_research/contracts.py`, `run_*.py`, tests | Tool contracts no longer live under `src/trader/`; compatibility needs are explicit and temporary. |
| 18. Move Research Helpers | Move or re-create the useful parts of `src/trader/research.py` under `src/trader_research/` with imports pointed at `trader` platform primitives. | `src/trader_research/*`, `src/trader/research.py`, tests | `src/trader/research.py` is deleted or reduced to a temporary compatibility shim only if needed for one migration commit. Final target has no research module in `trader`. |
| 19. Move Research Tool Modules | Move `trader.tools.artifacts`, `discovery`, `promotion`, `recommendations`, and `suites` into `trader_research` only as their capabilities are needed. Keep MCP-specific code out of these modules. | `src/trader_research/*`, `src/trader/tools/*`, CLIs, tests | `src/trader/tools/` is deleted after imports are updated; research CLIs import from `trader_research`. |
| 20. Research Domain Schemas | Define schemas for specialist artifacts and supervisor handoffs: `hypothesis_card.json`, method contracts, deterministic method validation reports, statistical-test reports, feature manifests, model cards, `ExperimentPlan`, `DataRequirement`, `StrategyCandidate`, `BacktestRunRef`, `evaluation_report.json`, `robustness_report.json`, recommendation reports, and `ResearchVerdict`. Prefer stdlib dataclasses unless validation complexity justifies Pydantic. | `src/trader_research/domain.py`, tests | Schemas serialize to JSON-compatible dicts and preserve agent-owned artifact boundaries. |
| 21. Quant Research Supervisor Graph Skeleton | Add the supervisor LangGraph identity, state, handoff ledger, and empty specialist artifact slots before broad Quant Research tools exist. | `src/trader_agents/quant_research.py`, tests | Supervisor graph can start, record a bounded research request, consume Data Agent artifact references, and mark missing specialist artifacts as blockers. |
| 22. Supervisor Consumes Data Agent Handoff | Add a supervisor node that accepts Data Agent manifest/quality references produced by the Data Agent graph. | `src/trader_agents/quant_research.py`, tests | Supervisor state preserves Data Agent ownership and does not fetch raw data directly. |
| 22H. Data Agent LLM Control Loop | Add a provider-neutral LLM client protocol/configuration layer, then add a Data Agent policy node that converts natural-language data requests into typed Data Agent action proposals. The deterministic router validates every proposal before a tool call and rejects attempts to bypass mandatory discovery or leave the Data Agent tool allowlist. | `src/trader_agents/llm_client.py`, `src/trader_agents/data_agent_policy.py`, `src/trader_agents/data_agent.py`, tests | The Data Agent can plan and execute discovery, inventory, quality, and permitted loading through existing MCP tools only. LLM access is selected at runtime so hosted gateways such as OpenRouter-style APIs or local backends such as Ollama can be used without changing Data Agent tools. Tests cover fake-LLM happy paths, invalid tool rejection, provider mismatch blocking, missing-symbol blocking, loading permission checks, loop limits, invalid-output repair/fail-closed behavior, missing LLM config fail-fast behavior, and no persistence of raw prompts, hidden reasoning, or scratchpads. |
| 23A. Quant Methods Knowledge Domain Schemas | Define schemas for `knowledge_source_manifest.json`, `knowledge_ingestion_report.json`, `knowledge_chunk_manifest.json`, `knowledge_embedding_manifest.json`, `method_card_draft.json`, `method_card.json`, `evidence_retrieval_report.json`, and `citation_validation_report.json`. | `src/trader_research/knowledge/domain.py`, `tests/test_knowledge_domain.py` | Schemas serialize to JSON-safe dictionaries; source manifests include source ID, title, approved source-type label, source approval status, canonical citation, file hash, access policy, topics, and warnings; chunks preserve source/page/section/heading locators, offsets, hashes, chunker version, and token counts where available; embedding manifests record provider/model/revision/dimension/distance metric/chunker version/source collection/index ID; method cards include assumptions, inputs, outputs, failure modes, source evidence, and approval status; drafts are not executable method contracts. |
| 23B. Knowledge Source Registration | Implement source registration for local documents or artifact references. | `src/trader_research/knowledge/sources.py`, `src/trader_research/knowledge/ingestion.py`, `tests/test_knowledge_sources.py` | Valid metadata produces `knowledge_source_manifest.json`; source type is one of `foundation_textbook`, `method_textbook`, `primary_paper`, `software_documentation`, or `internal_note`; approval status is one of `pending`, `approved`, `rejected`, or `superseded`; missing metadata fails closed when policy requires it; duplicate hashes are detected; unsupported file types and sources outside allowed directories are rejected; registration does not embed or index content yet. |
| 23C. Knowledge Text Extraction and Chunking | Extract text from PDF, Markdown, and plain text sources and create locator-preserving chunks. | `src/trader_research/knowledge/extractors.py`, `src/trader_research/knowledge/chunking.py`, `tests/test_knowledge_extraction.py`, `tests/fixtures/knowledge/*` | Markdown/text fixtures extract deterministically; PDF extraction preserves pages where available; warnings are reported; chunk IDs/hashes are deterministic for unchanged content/config; chunks include source IDs and locators; OCR is disabled unless explicitly permitted. |
| 23D. Knowledge Embedding, Lexical, and Vector Indexing Service | Embed chunks and store them in a searchable Postgres-backed knowledge index with relational metadata filters, PostgreSQL full-text lexical search, and pgvector dense retrieval. | `src/trader_research/knowledge/embeddings.py`, `src/trader_research/knowledge/index.py`, `src/trader_research/knowledge/ingestion.py`, tests | Runtime embedding configuration supports a real OpenAI-compatible embedding model; fake deterministic embeddings exist only for tests; embedding manifests record provider/model/revision/dimension/distance metric/chunker version/source collection/index ID; source/chunk/method metadata are stored in Postgres; chunk embeddings are stored in pgvector or a backend-neutral vector adapter; lexical terms use PostgreSQL full-text search initially; unchanged chunks do not create duplicate active chunks; changing embedding model/chunker/source collection creates a distinct immutable index version; tests require no external embedding provider. |
| 23E. Knowledge Ingestion MCP Tools | Expose source registration, document ingestion, and ingestion status through MCP. | `src/trader_mcp/knowledge_tools.py`, `src/trader_mcp/server.py`, `tests/test_mcp_knowledge_tools.py` | MCP exposes `knowledge_register_source`, `knowledge_ingest_documents`, and `knowledge_get_ingestion_status`; every tool returns a shared envelope; ingestion tools are `local_mutating`; unsupported file types and unbounded directories are rejected; smoke tests ingest Markdown/text fixtures and retrieve status. |
| 23F. Method Card Drafting and Approval | Create draft method cards from source evidence and allow explicit approval/publishing. | `src/trader_research/knowledge/method_cards.py`, `src/trader_research/knowledge/retrieval.py`, `tests/test_method_cards.py` | Draft cards require validated source evidence and include assumptions, inputs, outputs, and failure modes; drafts are not executable by method-contract tools; publishing requires explicit approval input, approver, and approval note; approved cards are immutable by default and conflicting duplicate publishes fail closed. |
| 23G. Hybrid Retrieval, Chunk Dereference, and Citation Validation MCP Tools | Expose method-card search, hybrid evidence retrieval, explicit chunk dereferencing, and citation validation through MCP. | `src/trader_research/knowledge/retrieval.py`, `src/trader_research/knowledge/citation_validation.py`, `src/trader_mcp/knowledge_tools.py`, `tests/test_knowledge_retrieval.py`, `tests/test_citation_validation.py`, `tests/test_mcp_knowledge_tools.py` | MCP exposes `knowledge_list_sources`, `knowledge_search_methods`, `knowledge_retrieve_evidence`, `knowledge_get_evidence_chunks`, `knowledge_create_method_card_draft`, `knowledge_publish_method_card`, and `knowledge_validate_citations`; retrieval runs lexical search and vector search, merges/deduplicates results with deterministic rank fusion, and returns source IDs, chunk IDs, locators, source titles, approval status, lexical rank, vector rank, combined rank, vector score, and short excerpts/summaries; dereference returns bounded real chunk text by chunk ID with source metadata, locators, text hashes, and truncation flags; citation validation fails on unknown sources/chunks, invalid locators, unapproved sources or method cards, unsupported claims, excessive direct quotation, or high-risk methods backed only by broad foundation sources; retrieval can filter to approved sources/cards only. |
| 23H. Knowledge-Backed Math Method Domain Schemas | Define Quantitative Methods schemas that require knowledge provenance for non-trivial statistical methods. | `src/trader_research/methods/contracts.py`, `src/trader_research/domain.py`, `tests/test_math_domain.py` | `indicator_contract.json`, `statistical_test_contract.json`, `signal_diagnostic_report.json`, `multiple_testing_report.json`, `cxx_kernel_manifest.json`, and `method_package_manifest.json` include optional/required `knowledge_evidence_refs` by method complexity; statistical-test and multiple-testing contracts require approved method cards; simple arithmetic transforms may use maintained registry entries; unknown or uncited sophisticated methods fail closed. Future compiled-kernel conformance reports are deferred. |
| 23I. Knowledge-Backed Math Method Registry | Create the maintained registry of approved methods, linked to approved method cards where required. | `src/trader_research/methods/registry.py`, `src/trader_research/methods/tools.py`, `tests/test_math_registry.py` | Registry lists maintained methods by family; each non-trivial statistical method links to one or more approved method cards; unsupported methods fail closed; legacy indicator-only views remain filterable for compatibility. |
| 23J. Citation-Backed Python Implementation Validation | Implement the first real implementation gate for deterministic indicators/transforms. | `src/trader_research/method_implementations.py`, `src/trader_research/methods/tools.py`, `src/trader_standard/indicators/*`, `tests/test_method_implementations.py`, `tests/test_mcp_quant_methods_tools.py` | Reuses `trader.indicators.Indicator` and `IndicatorObservation` as the runtime contract; validates that a Python reference implementation is tied to an approved method card and method contract; records entrypoint, source hash, source provenance docstring, implementation language, dependency allowlist, and safety profile; validates `sma`, `ema`, `rsi`, `rolling_volatility`, and `z_score`; checks warmup/null behavior, output length, default deterministic fixtures, and no-lookahead prefix behavior; unknown entrypoints, unsafe dependencies, missing provenance docstrings, unapproved method-card refs, hash mismatches, fixture mismatches, and non-`Indicator` classes fail closed. |
| 23K. Python Method Artifact Generation and Registration | Add the controlled Python implementation artifact path after the 23J validation gate exists. | `src/trader_research/method_implementations.py`, `src/trader_research/methods/tools.py`, `src/trader_mcp/knowledge_tools.py`, `tests/test_method_implementations.py`, `tests/test_mcp_quant_methods_tools.py` | Existing maintained Python `Indicator` implementations can be registered as `method_implementation_manifest.json` records; LLM-authored Python drafts are written only to `artifacts/research/method_implementations/quarantine/`, never directly into runtime packages; generated artifacts must start with a source/provenance docstring, cite approved method cards, declare method contracts, pass static safety checks, record source hashes and dependency allowlists, and pass 23J fixtures before they are marked `validated`. |
| 23K-A. Citation-Backed Signal Method Vertical Slice | Prove a non-indicator code artifact through the full knowledge-backed process using the existing `trader.signals.Signal` interface. | `src/trader_research/method_implementations.py`, `src/trader_research/methods/tools.py`, `src/trader_mcp/knowledge_tools.py`, `src/trader_standard/signals/*`, `src/trader_research/method_contracts_seed.json`, `tests/test_method_implementations.py`, `tests/test_mcp_quant_methods_tools.py` | Select one textbook-backed trading-rule method; retrieve and dereference evidence through `knowledge_retrieve_evidence` and `knowledge_get_evidence_chunks`; create and publish an approved method card; add a persisted/store-backed method contract with `runtime_contract="trader.signals.Signal"` or equivalent metadata; extend implementation registration to accept `Signal` subclasses without weakening the existing `Indicator` checks; add deterministic latest-first bar fixtures for `compute(bars) -> float`, warmup behavior, no-lookahead prefix checks, source hash, provenance docstring, and approved method-card refs; write `method_implementation_manifest.json` and a signal fixture validation report. Diagnostics and family-level inference remain 23L, not part of this vertical slice. |
| 23L. Signal Diagnostics and Multiple-Testing Reports | Implement first-pass signal-composition diagnostics and Benjamini-Hochberg family-level inference over declared candidate families. | `src/trader_research/methods/diagnostics.py`, `src/trader_research/methods/multiple_testing.py`, `src/trader_research/methods/tools.py`, `src/trader_mcp/knowledge_tools.py`, `src/trader_mcp/server.py`, `src/trader_research/agents.py`, `tests/test_signal_diagnostics.py`, `tests/test_multiple_testing.py`, `tests/test_mcp_quant_methods_tools.py`, `tests/test_agent_identities.py` | Computes IC/rank IC, action hit rate, action-conditioned returns, coverage, turnover proxy, quantile buckets for continuous signals, monotonicity, horizon results, and symbol/session/regime breakdowns where inputs exist; treats indicators as explanatory metadata rather than primary tested units; requires candidate-family manifests for family inference; requires approved method-card evidence for `rank_ic` and `benjamini_hochberg`; records raw p-values, adjusted p-values, rejection flags, accepted/rejected candidates, correction method, tested grid, and candidate count; validates declared executable signal implementation refs and warns when candidates are observational; outputs include warnings and blockers. Bonferroni, Holm, White Reality Check, Hansen SPA, Deflated Sharpe Ratio, and PBO remain follow-on methods. |
| 23M. C++ / Compiled Kernel Path | Implement a controlled compiled-kernel path for approved deterministic transforms after Python references are validated. | `src/trader_research/methods/kernels.py`, `src/trader_research/methods/tools.py`, `src/trader_mcp/knowledge_tools.py`, `src/trader_standard/indicators/cpp/*`, `src/trader_standard/indicators/bindings/*`, `tests/test_cpp_kernel_artifacts.py`, `tests/test_mcp_quant_methods_tools.py` | C++ generation is template-based only and currently supports `sma_scalar_series_v1`; generation requires an approved Python reference implementation manifest plus passing fixture validation; compilation occurs in an isolated local build directory; manifests record build settings, ABI/binding info, source/template provenance, generated source hash, compiler/binary/log metadata, and compile-only benchmark summary; failed compile returns a blocking envelope; kernels cannot access broker mutation, SQL, network, filesystem mutation, or live trading controls. C++ conformance/equivalence and runtime acceleration are deferred behind the first meaningful MCP research toolchain. |
| 23N. Method Package Manifests | Package validated Python indicator and signal implementations for handoff into strategy construction. | `src/trader_research/methods/packages.py`, `src/trader_research/methods/tools.py`, `src/trader_mcp/knowledge_tools.py`, `src/trader_research/domain.py`, `tests/test_method_package_artifacts.py`, `tests/test_mcp_quant_methods_tools.py` | Done. `math_package_method_artifact` writes `method_package_manifest.json` from a validated `method_implementation_manifest`, method contract snapshot, approved method-card refs, fixture validation report ref, source hash, runtime contract, warnings, and blockers. Python-only packages are valid. Optional C++ kernel refs may be included as non-gating optimization metadata, but no package requires compiled-kernel output equivalence. |
| 24. Register Quantitative Methods MCP Tools | Expose the deterministic method surface through MCP after knowledge ingestion/retrieval tools exist. | `src/trader_mcp/server.py`, `src/trader_mcp/schemas.py`, `tests/test_mcp_math_tools.py`, `tests/test_mcp_server.py` | MCP exposes `math_list_method_contracts` and `math_validate_method_contract` first; backward-compatible indicator aliases may exist; follow-on tools register only after direct services pass tests; every tool returns a shared envelope with `agent_owner="Quantitative Methods Agent"`, declares side effect, rejects unbounded inputs or unknown methods, and requires approved method-card references for sophisticated statistical procedures where configured. |
| 25. Strategy Candidate Schema and Template Catalog | Define the strategy candidate artifact and expose maintained templates that can consume validated signal/method packages. | `src/trader_research/strategy_candidates/`, `src/trader_research/domain.py`, `tests/test_strategy_candidates.py` | Done. `strategy_candidate_manifest.json` records template family, method package refs, signal refs, strategy source refs, entry/exit semantics, sizing, risk assumptions, execution assumptions, warnings, and blockers without binding symbols, timeframe, or date windows. Template discovery returns maintained families, strategy parameters, defaults, constraints, required artifact types, and declarative backtest context requirements without importing arbitrary strategy code. Candidate creation is direct service task 26; MCP registration remains 27. |
| 26. Source-Backed Strategy Candidate Builder | Compose validated method/signal packages into bounded strategy candidates. | `src/trader_research/strategy_candidates/`, `src/trader_research/domain.py`, `src/trader_research/agents.py`, `tests/test_strategy_candidates.py` | Done. `research_create_strategy_candidate` accepts validated `method_package_manifest.json` refs by package ID, path, or inline payload; enforces exact catalog role coverage, signal runtime contracts, approved method-card refs, empty package blockers, scalar strategy parameters, numeric bounds, fixed-quantity sizing, and no-live-trading execution assumptions; derives signal refs; writes a deterministic importable Python strategy source artifact implementing `trader.strategies.Strategy`; and records that source in data-free `strategy_candidate_manifest.json`. Generated source uses semantic template-derived class names rather than candidate-hash class names, while `candidate_id` remains the canonical metadata link. Symbols, asset class, timeframe, and date windows are backtest inputs for task 28, not strategy-candidate fields. |
| 27. Strategy Candidate Validation MCP Tools | Register strategy discovery, creation, and validation through MCP. | `src/trader_research/strategy_candidates/validation.py`, `src/trader_mcp/research_tools.py`, `src/trader_mcp/server.py`, `tests/test_strategy_validation.py`, `tests/test_mcp_strategy_tools.py` | Done. MCP exposes `research_list_strategy_templates`, `research_create_strategy_candidate`, and `research_validate_strategy_candidate` with `agent_owner="Quant Research Supervisor Agent"`. Validation resolves candidate manifests by ID, path, or inline payload; writes `strategy_candidate_validation_report.json`; verifies and loads the generated strategy source factory; instantiates the concrete `trader.strategies.Strategy` with an internal synthetic fixture context; runs deterministic synthetic-bar smoke checks; and blocks unsupported or unsafe candidates before any backtest. |
| 28. Baseline Backtest Service | Wrap `trader.backtest.BacktestRunner` for one reproducible Quant Research baseline run over a Data Agent scope. | `src/trader_research/backtests/`, `src/trader_research/domain.py`, `tests/test_research_backtests.py` | Done. Backtests require a strategy candidate ref, a passed validation report ref, and exactly one `dataset_manifest` ref or inline payload. Symbols, asset class, timeframe, window, source filter, row counts, and completeness come from the manifest and are recorded in `BacktestDataScope`, provenance, and `backtest_run_ref.json`; loose scope fields fail closed. A fixture/sample-data run produces result metrics, provenance, config hash, warnings, and artifact paths tied to dataset manifest and optional matching data-quality report refs. |
| 29. Backtest MCP Tools | Register the baseline backtest and result lookup path through MCP. | `src/trader_mcp/research_tools.py`, `src/trader_mcp/server.py`, `tests/test_mcp_backtest_tools.py`, `tests/test_agent_identities.py` | Done. MCP exposes `research_run_backtest` and `research_get_backtest_results`; runs are local-mutating, bounded, and gated by `TRADER_MCP_ALLOW_BACKTESTS=true`; result lookup is read-only; envelopes include `BacktestRunRef`, result bundle paths, summary metrics, data scope, warnings, blockers, provenance, and Quant Research Supervisor ownership. |
| 30. Backtest Result Query And Comparison | Add richer lookup and comparison over persisted task-28/29 bundles. | `src/trader_research/backtests/`, `src/trader_mcp/research_tools.py`, `src/trader_mcp/constants.py`, tests | Done. `research_compare_backtest_results` accepts 2-50 explicit refs by run ID, artifact directory, or inline `backtest_run_ref`; reads only task-28 bundle files; supports deterministic ranking by `sharpe`, `total_return`, `max_drawdown`, cost, count, and warning/failure metrics; warns when runs differ in comparable dimensions; writes supervisor-owned `comparison_report.json`; and is registered through MCP as local-mutating without the backtest execution gate. |
| 31. Performance Report Service | Produce the first practical Evaluation-owned performance report over backtest artifacts. | `src/trader_research/evaluation/performance.py`, `tests/test_performance_reports.py` | Done. `evaluation_generate_performance_report` resolves exactly one task-28 backtest bundle by run ID, artifact directory, or inline run ref; reads persisted metrics/result/provenance/trade evidence; consumes optional Data Agent quality evidence; writes deterministic `evaluation_report.json`; and marks reports blocked for missing/incomplete quality, mismatched quality scope, failed runs, run blockers, and zero-trade backtests. |
| 32. Performance Report MCP Tool | Register the first performance-report tool. | `src/trader_mcp/evaluation_tools.py`, `src/trader_mcp/server.py`, `tests/test_mcp_evaluation_tools.py`, `tests/test_agent_identities.py` | Done. MCP exposes `evaluation_generate_performance_report` with Evaluation Agent ownership, `local_mutating` side effect, config metadata, and no backtest execution gate. It returns a standard `ToolEnvelope` with `evaluation_report` data and artifact refs. |
| 33. End-to-End Research Toolchain Test | Prove the meaningful MCP suite before adding more agent orchestration. | `tests/test_mcp_research_toolchain.py` | Done. One deterministic sample flow runs through MCP: Data Agent inventory/quality evidence, source-backed signal method package, source-backed strategy candidate, strategy validation, baseline backtest, and Evaluation performance report. The test asserts artifact ownership, side-effect classes, required refs, persisted artifact paths, trade evidence, and fail-closed behavior for missing method provenance or unvalidated strategy candidates. |
| 33A. Multi-Asset And Risk Artifact Schemas | Add portfolio/risk artifact contracts before generating risk-aware research code. | `src/trader_research/domain.py`, `tests/test_research_domain.py`, docs | Done. JSON-safe schemas cover risk-manager candidates, risk-manager source refs, future risk-manager validation refs, strategy/risk stacks, stack validation reports, and portfolio/risk backtest refs. Schemas preserve owner boundaries, carry source hashes and validation refs, support multiple risk-manager refs, and represent multi-symbol data scopes without moving symbols/date windows into strategy or risk candidates. |
| 33B. Risk Manager Template Catalog And Builder | Add the supervisor-owned risk-manager generation surface. | `src/trader_research/risk_managers/`, `src/trader_mcp/research_tools.py`, tests | Done. MCP lists bounded risk-manager templates and creates source-backed `risk_manager_candidate_manifest.json` artifacts from approved templates, scalar parameters, and optional method-package refs. Templates cover exposure caps, per-symbol caps, concentration caps, drawdown controls, and VaR/CVaR-style risk filters as generation targets. Generated candidates implement `trader.risk.RiskManager`, record source hashes and no-live-trading assumptions, and remain validation-deferred/backtest-only. |
| 33C. Multi-Asset Strategy Candidate Generation | Extend source-backed strategy generation for portfolio construction after task 54. | `src/trader_research/strategy_candidates/`, tests | Done. Strategy templates declare portfolio construction mode, rebalance cadence, allocation bounds, and portfolio-state requirements. Existing templates are per-symbol independent multi-asset templates, a maintained cross-sectional momentum top-N template is registered, generated source metadata carries portfolio semantics while remaining data-free, and validation smoke tests use multiple symbols. |
| 33D. Strategy/Risk Stack Builder And Validation | Compose validated strategies with one or more risk managers before backtesting. | `src/trader_research/portfolio_stacks/`, `src/trader_mcp/research_tools.py`, tests | Done. Adds `research_validate_risk_manager_candidate`, `research_create_strategy_risk_stack`, and `research_validate_strategy_risk_stack`. Stack creation consumes passed strategy/risk-manager validation reports, records risk-manager order and priority, writes `strategy_risk_stack_manifest.json`, and validates the combined runtime against deterministic multi-asset fixture bars and `RiskPipeline` before portfolio backtests. |
| 33E. Risk-Scoped Portfolio Backtest Tools | Run backtests over a multi-asset data scope with a validated strategy/risk stack. | `src/trader_research/backtests/`, `src/trader_mcp/research_tools.py`, tests | Done. Adds `research_run_portfolio_backtest` with explicit stack-validation mode, Data Agent manifest scope, MCP backtest gate, stack/source revalidation, `BacktestRunner` execution through ordered risk managers, and portfolio sidecars for symbol metrics, exposure, risk decisions, limit breaches, risk-measure evidence, trades, positions, curves, and provenance. |
| 33F. Portfolio And Risk Evaluation Reports | Make Evaluation reports reflect strategy plus risk stack behavior. | `src/trader_research/evaluation/performance.py`, `tests/test_portfolio_backtests.py`, docs | Done. Evaluation reports now consume risk-scoped portfolio bundles, report stack refs, per-symbol metrics, exposure/concentration, costs, risk decisions, breach evidence, and risk-measure summaries, and block when portfolio sidecars or required telemetry are missing. |
| 33G. Multi-Asset Risk Toolchain Evidence | Prove the portfolio-construction MCP chain before expanding supervisor autonomy. | `tests/test_mcp_portfolio_risk_toolchain.py`, docs | Done. One deterministic MCP flow builds a source-backed multi-asset strategy from a method package, validates a source-backed risk manager, creates and validates a stack, runs a risk-scoped portfolio backtest, and generates an Evaluation report with fail-closed checks for unvalidated risk managers and non-passed stack validation. |
| 33H. Rich Methodology Candidate Schema | Add rich, nullable methodology artifacts before attempting automated extraction. | `src/trader_research/knowledge/domain.py`, `src/trader_research/domain.py`, `tests/test_knowledge_domain.py`, docs | Done. Defines `methodology_candidate` as a Quantitative Methods artifact and adds `EvidenceBackedField`, `MethodologyCandidate`, and `RichMethodCard` schemas. Core fields cover identity, scope, data requirements, method specification, signal/decision logic, portfolio/execution, risk/validation, and implementation notes. Extension blocks cover technical indicators, statistical arbitrage, options/derivatives, fundamental valuation, sentiment/alternative data, portfolio construction, risk models, and execution methods. Populated fields require field-level evidence refs; null fields remain valid. Rich cards preserve existing `method_card_draft` / `method_card` artifact types and support shallow `MethodCard` projection. |
| 33I. Methodology Candidate Discovery MCP Tools | Discover methodology candidates from ingested source chunks without approving them. | `src/trader_research/knowledge/methodology_candidates.py`, `src/trader_mcp/knowledge_tools.py`, `tests/test_methodology_candidates.py`, `tests/test_mcp_quant_methods_tools.py` | Done. Adds `knowledge_discover_methodology_candidates` over explicit source IDs, retrieval queries, or method families. The service combines retrieval, direct source chunk scans, neighboring chunk expansion, source metadata, locator grouping, and deterministic de-duplication to produce candidate spans. It writes DB-backed candidate refs through the research artifact store and must not create method cards, implementations, strategies, or approvals. |
| 33J. Evidence-Grounded Field Extraction And Validation | Populate rich methodology fields only when evidence supports them. | `src/trader_research/knowledge/methodology_extraction.py`, tests | Done. Adds `knowledge_extract_methodology_fields` and `knowledge_validate_methodology_candidate`. Extraction uses deterministic rules and every non-null core or extension-block field attaches field-level evidence refs. Unsupported fields remain null. Validation fails closed for invalid chunks/locators, unsupported claims, missing family-specific minimum fields, internal-note-only textbook-derived claims, excessive direct quotation, and insufficient high-risk family evidence. |
| 33K. Rich Method Card Draft And Approval Tools | Promote validated methodology candidates into rich method-card drafts. | `src/trader_research/knowledge/method_cards.py`, `src/trader_mcp/knowledge_tools.py`, tests | Done. `knowledge_create_rich_method_card_draft` loads a passed validation report and matching candidate from DB-backed research artifacts, revalidates source/chunk evidence through the knowledge store, derives required shallow fields, writes rich drafts through the method-card store, and `knowledge_publish_method_card` preserves rich payloads while shallow projections remain compatible. |
| 33L. Strategy Generation From Rich Method Cards | Generate implementable strategy/risk candidates from approved rich method cards. | `src/trader_research/strategy_candidates/`, `src/trader_research/risk_managers/`, `src/trader_standard/strategies/`, tests | Done. Strategy/risk manifests carry `methodology_refs`; `pairs_mean_reversion` uses approved rich statistical-arbitrage cards with required spread/relationship/entry/exit/input evidence; risk-manager candidates accept approved rich risk/portfolio cards and only map explicit numeric risk thresholds. Symbols, timeframes, and date windows remain Data Agent scope. |
| 33M. Rich Methodology Documentation And Operator Guide | Document the upgraded source-to-method-to-strategy behavior. | `docs/research_agents/architecture.md`, `docs/research_agents/agents.md`, `docs/research_agents/mcp_tools.md`, `docs/research_agents/tool_contracts.md`, `docs/research_agents/workflows.md`, `docs/research_agents/operations.md`, `tests/test_research_agent_docs.py` | Done. The active docs now explain source registration versus full-document ingestion, indexed retrieval and chunk dereferencing, candidate discovery, nullable core/extension fields, field-level citation semantics, draft versus approved rich-card behavior, validation blockers, source suitability policy, DB-first operation, and rich-card consumption by method packaging, strategy/risk generation, portfolio backtests, and Evaluation. Operator examples cover pairs/cointegration, options straddles, RSI-style technical indicators, and commodity sentiment/alternative-data indicators. |
| 33N. Rich Methodology End-To-End Evidence | Prove rich methodology extraction can produce strategy evidence. | `tests/test_mcp_rich_methodology_toolchain.py`, `src/trader_standard/strategies/policy_driven.py`, docs | Done. A deterministic MCP regression creates and ingests an `Algorithmic Trading and Quantitative Strategies` style PDF, discovers and extracts statistical-arbitrage methodology fields, validates the candidate, drafts and publishes a rich method card, generates and validates a rich-card-driven `pairs_mean_reversion` strategy, composes a validated risk stack, runs a risk-scoped portfolio backtest over two symbols, and produces an Evaluation report with trade evidence. The test also proves fail-closed behavior for thin/shallow cards, missing field evidence, internal-note-only methodology evidence, unapproved drafts, and unsupported rich-card families. The maintained pairs strategy now implements native per-symbol cycle behavior so streaming/backtest cycles execute and price both pair legs instead of getting stuck with a partial pair. |
| 33O. Canonical Method Card Architecture Review | Deep-dive the target architecture before the next methodology-extraction capability upgrade. | `docs/research_agents/architecture.md`, tracker | Done. The architecture now states that method cards are canonical evidence-backed methodology artifacts, shallow fields are derived projections, retrieval is not methodology understanding, method targets are discovered from source/query evidence rather than hardcoded, family-level evidence roles drive assembly, optional enrichment adapters remain bounded and validation-gated, semantic validation and strategy-grade readiness are distinct, and the next implementation work should retire shallow public methodology drafting while strengthening discovery, evidence assembly, extraction, and validation. |
| 33P. Canonical Method Card Workflow And Legacy Shallow Retirement | Remove the shallow card path as a first-class methodology workflow. | `src/trader_research/knowledge/method_cards.py`, `src/trader_research/knowledge/store.py`, `src/trader_mcp/knowledge_tools.py`, docs, tests | Done. Rich cards are now the strategy-grade method-card workflow. Existing shallow cards are explicit legacy/projection records; `knowledge_create_method_card_draft` returns a legacy warning; rich draft creation requires packet-backed validation readiness; search/list compatibility still returns derived shallow summaries, while strategy/risk generation and readiness checks reject shallow or non-rich cards. |
| 33Q. Family Evidence Role Ontology | Define the closed family-level evidence roles that drive open-world method understanding. | `src/trader_research/knowledge/evidence_profiles.py`, `src/trader_research/knowledge/domain.py`, docs, tests | Done. Adds versioned profiles for technical indicators, statistical arbitrage, options/derivatives, sentiment/alternative data, portfolio construction, risk models, fundamental valuation, and execution methods. Profiles define role IDs, descriptions, search hints, schema field mappings, and readiness requirements without enumerating known method targets. |
| 33R. Open-World Method Discovery And Diagnostics | Discover method-specific candidates without a maintained target registry. | `src/trader_research/knowledge/methodology_candidates.py`, `src/trader_mcp/knowledge_tools.py`, tests | Done. Discovery derives candidate names and spans from local source/query evidence and no longer turns source-level family metadata into candidate labels. Candidate artifacts include name evidence, family attribution evidence, span diagnostics, warnings, and duplicate decisions. |
| 33S. Methodology Evidence Assembly Packets | Add an inspectable evidence packet between candidate discovery and field extraction. | `src/trader_research/knowledge/evidence_assembly.py`, `src/trader_research/domain.py`, `src/trader_research/postgres_artifact_store.py`, `src/trader_mcp/knowledge_tools.py`, docs, tests | Done. Adds `methodology_evidence_packet` as a Quantitative Methods artifact with Postgres projection support plus `knowledge_assemble_methodology_evidence`, owned by Quantitative Methods and `local_mutating`. The service requires knowledge and research artifact stores, gathers role-labeled chunks from family profiles, records missing roles and diagnostics, and fails closed on missing dependencies or readiness roles. |
| 33T. Role-Grounded Field Extraction And Bounded Enrichment | Populate rich fields from assembled role evidence rather than generic keyword hits. | `src/trader_research/knowledge/methodology_extraction.py`, `src/trader_research/knowledge/evidence_assembly.py`, docs, tests | Done. `knowledge_extract_methodology_fields` accepts evidence packet refs and uses role-labeled chunks for field extraction. Populated fields carry role evidence refs, unsupported fields stay null, extraction reports link back to packet IDs, and deterministic validation remains the approval gate. |
| 33U. Semantic Validation And Readiness Gates | Validate source-supported meaning and downstream readiness, not only schema shape. | `src/trader_research/knowledge/methodology_extraction.py`, `src/trader_research/knowledge/method_cards.py`, `src/trader_research/strategy_candidates/`, `src/trader_research/risk_managers/`, docs, tests | Done. Validation checks field-to-role consistency and emits readiness statuses for descriptive, implementation, signal, strategy-template, and risk-manager use. Rich drafts require implementation readiness, rich cards preserve readiness in lineage, and strategy/risk candidate generation consumes strategy-template or risk-manager readiness gates. |
| 33V. Open-World Method Card Evidence Regression | Prove the target-agnostic method-card capability end to end with stable card-set lineage and target-bound evidence semantics. | `tests/test_mcp_open_world_method_cards.py`, `src/trader_research/knowledge/evidence_profiles.py`, docs | Done. MCP evidence ingests a source containing the unseen Aurora Pulse Oscillator, Boreal Envelope Trigger, Drift Prism Index, and Lattice Residual Coupling names; discovers method-specific candidates without target hardcoding; materializes approved canonical technical and statistical-arbitrage cards; preserves stable set/revision lineage; and proves rich-card strategy provenance. It blocks missing formula evidence, shallow-card strategy use, and cross-method field contamination. The regression also tightened technical implementation readiness so the generic word `indicator` cannot count as formula evidence. |
| 33W. Stable Method-Card Set Identity And Revision Lineage | Add stable aggregate identity for method cards before creating more canonical method-card evidence. | `src/trader_research/knowledge/domain.py`, `src/trader_research/knowledge/method_cards.py`, `src/trader_research/knowledge/store.py`, `src/trader/knowledge/schema.py`, `src/trader/knowledge/store.py`, `src/trader_mcp/knowledge_tools.py`, docs, tests | Done. Adds `method_card_set_id` and revision metadata to `MethodCard` and `RichMethodCard`; adds Postgres `knowledge_method_card_sets` plus `knowledge_method_cards.method_card_set_id`, `revision_number`, and `supersedes_method_card_id`; derives set IDs from stable logical identity and source fingerprints rather than volatile candidate/chunk IDs; allows explicit set IDs for intentional revisions; publishing within a set updates current approved/draft pointers and supersedes prior active approved revisions; lifecycle updates repair current pointers; MCP exposes read-only set listing/detail tools; pgAdmin views expose active cards, set summaries, and revision history. Legacy Postgres method-card rows without explicit lineage are unsupported and must be reset/recreated or migrated through an explicit operator-reviewed path; the code does not synthesize legacy set IDs or auto-backfill old payloads. Strategy/risk generation and future evidence regressions consume approved cards through set-aware lineage. |
| 33X. Target-Bound Evidence Units And Reingestion | Replace coarse chunks with smaller method-evidence units and reset incompatible knowledge data. | `src/trader_research/knowledge/chunking.py`, `src/trader_research/knowledge/ingestion.py`, `src/trader_research/knowledge/domain.py`, `src/trader_research/knowledge/store.py`, `src/trader_research/knowledge/postgres_store.py`, `src/trader/knowledge/schema.py`, `src/trader/knowledge/store.py`, `src/trader_mcp/knowledge_tools.py`, docs, tests | Done. Adds schema-v2 evidence units through the existing `KnowledgeChunk` retrieval API shape, with deterministic `knowledge_evidence_unit_*` IDs, `evidence_unit_id`, parent section IDs, paragraph/sentence indexes, method-label detection, neighbor refs, source locators, text hashes, and chunker version. Ingestion splits line/sentence/paragraph text into smaller method-aware units, writes `knowledge_evidence_unit_manifest`, indexes unit text lexically/vectorially, exposes evidence-unit metadata in retrieval/dereference results, and refuses legacy JSON chunk manifests. Postgres `knowledge_chunks` now stores evidence-unit metadata columns and schema-v2 payloads. Forced ingestion bypasses existing payload deserialization before source-scoped replacement, allowing incompatible evidence to be regenerated without a compatibility reader. |
| 33Y. Method Identity Discovery And Alias Binding | Group candidates by discovered method identity rather than heading/family proximity. | `src/trader_research/knowledge/methodology_candidates.py`, `src/trader_research/knowledge/evidence_profiles.py`, `src/trader_research/knowledge/domain.py`, `src/trader_mcp/knowledge_tools.py`, tests | Done. Discovery scans explicit source scopes directly, uses retrieval only for retrieval-backed discovery, extracts identities from local labels, abbreviations, title-like headings, query phrases, and detected labels, and groups candidates by method identity plus evidence-unit set. Candidate artifacts include canonical/source names, aliases, abbreviations, identity evidence-unit refs, query-alignment diagnostics, context refs, and competing-label diagnostics. Tests prove adjacent technical methods remain separate and the rich pairs methodology MCP chain still runs end to end. |
| 33Z. Target-Bound Evidence Packets And Extraction | Assemble and extract only evidence that is bound to the selected method identity. | `src/trader_research/knowledge/evidence_assembly.py`, `src/trader_research/knowledge/methodology_extraction.py`, docs, tests | Done. Evidence packets annotate role refs with `target_binding` (`direct_label`, `alias_label`, `same_sentence`, `same_paragraph`, `nearby_context`, `weak`, or `rejected`), binding terms, competing labels, acceptance flags, and reasons. Readiness roles count only accepted refs that contain role terms and are bound to the selected method. Packet-backed extraction and validation readiness ignore rejected/weak refs. Tests prove adjacent Bollinger signal evidence is rejected for an EWA candidate and cannot populate EWA signal fields, while EWA formula evidence remains usable. |
| 33AA. Semantic Method-Card Validation And Draft Gates | Block semantically contaminated method cards before canonical draft materialization or approval. | `src/trader_research/knowledge/methodology_extraction.py`, `src/trader_research/knowledge/method_cards.py`, docs, tests | Done. Validation enforces one source-backed target method identity per candidate, requires packet lineage for passed semantic validation, checks field refs against accepted target-bound packet refs, blocks fields sourced from rejected competing-method chunks, detects stale evidence-unit hashes/locators/source IDs, and reports target-bound readiness. Canonical method-card draft materialization rejects caller-provided `method_id`, `title`, or `family` overrides unless candidate identity, aliases, abbreviations, and validated families support them, and requires candidate lineage to match the validation packet. Direct and MCP tests cover unsupported overrides, packet-less validation, stale hashes, contaminated Bollinger->EWA evidence, internal-note source policy through the packet-backed path, and successful canonical rich-card publication/strategy use. |
| 33AB. Claim-Level Semantic Extraction And Ingestion Consistency | Close the semantic-attribution and transactional gaps exposed by a real technical-method source. | `src/trader_research/knowledge/claim_spans.py`, `src/trader_research/knowledge/domain.py`, `src/trader_research/knowledge/evidence_assembly.py`, `src/trader_research/knowledge/methodology_extraction.py`, `src/trader_research/knowledge/ingestion.py`, `src/trader_research/knowledge/index.py`, Postgres knowledge storage, `docs/research_agents/semantic_extraction.md`, tests | Done. Evidence units remain reusable and non-exclusive. `EvidenceClaimSpan` records stable IDs, exact offsets/text/hashes, roles, target methods, binding modes, matched terms, local labels, and engine versions. Packet assembly selects accepted/rejected spans within each unit and uses generic inline labels plus bounded source context without granting chunk ownership. Packet-backed extraction rebuilds derived fields, applies field-specific semantic filters, performs bounded multi-span synthesis, and preserves every contributing ref. Validation re-slices stored text and checks span hashes, packet roles, target identity, accepted binding, and specialized field semantics. Regressions cover one unit supporting Bollinger and Moving Average Oscillator independently, malformed real-PDF-style neighboring claims, stale re-extraction cleanup, and multi-unit synthesis. Embeddings are staged before replacement; Postgres publication wraps evidence replacement, vectors, manifest, and report in one transaction. The canonical semantic-extraction document is linked from active references. The live book rerun now fails closed on missing Moving Average Oscillator input evidence rather than publishing semantically contaminated fields. |
| 33AC. Composite Methodology Architecture | Generalize methodology representation beyond one primary family and locally identifiable method span. | `docs/research_agents/architecture.md`, methodology claim/relationship domain, MCP contracts, tests | Deferred. The architecture records source-backed claim graphs, typed relationships, inferred atomic/composite boundaries, ordered component refs, multi-valued post-assembly classification, and aggregated readiness as the future direction. Existing Postgres knowledge creation and bounded extraction remain maintained at the 33AB baseline; implementation is paused while tasks 56-57, 39, 44, and 46 build a more direct trading-evidence path. |
| 34. Supervisor Consumes Toolchain Artifacts | Add minimal supervisor consumption for the proven deterministic toolchain. | `src/trader_agents/quant_research.py`, `tests/test_supervisor_toolchain_handoff.py` | Implement after tasks 56-57. Supervisor accepts validated implementation-version, strategy/risk/backtest specification, run, and performance-report refs; rejects wrong owner, unresolved blockers, invalid versions/specifications, or failed runs; preserves refs and public status only. Method packages and method cards may be linked provenance but are never required execution handoffs. |
| 35. Quantitative Methods Agent Graph | Add knowledge-aware LangGraph identity, state, policy, and tool allowlist for the Quantitative Methods Agent after the method-to-backtest toolchain exists. | `src/trader_agents/quant_methods_agent.py`, `src/trader_agents/quant_methods_policy.py`, `src/trader_agents/state.py`, `tests/test_quant_methods_agent.py`, `tests/test_langgraph_agents.py` | Graph has distinct identity and state; may call only knowledge and Quantitative Methods MCP tools; cannot fetch data, create strategies, train models, run backtests, call evaluation tools, or promote strategies; returns method package refs, retrieval refs, citation-validation refs, and blockers; no raw prompts, hidden reasoning, or scratchpads are persisted. |
| 36. Supervisor LLM Control Loop | Add the LLM-backed supervisor policy node after implementation/specification, backtest, and performance-report tools are useful. | `src/trader_agents/supervisor_policy.py`, `src/trader_agents/quant_research.py`, tests | Supervisor assesses bounded state and artifact summaries, then emits typed decisions such as `request_specialist`, `call_tool`, `retry_with_changes`, `accept_artifact`, `block`, or `finish`. Deterministic routing validates schema, allowlist, ownership, side effects, loop budget, early block/finish behavior, and no raw prompt/scratchpad persistence. |
| 37. Hypothesis Card Service and MCP Tool | Implement `hypothesis_create_card` from structured inputs and available ingredient references after the basic toolchain works. | `src/trader_research/hypotheses.py`, `src/trader_mcp/server.py`, tests | Hypothesis cards require mechanism, data requirements, required features/method packages, strategy intent, falsification criteria, and known caveats. MCP returns a Hypothesis Agent envelope with `hypothesis_card.json` payload/path. |
| 38. Hypothesis Agent Graph and Handoff | Add Hypothesis Agent identity and supervisor handoff consumption once hypothesis cards are useful inputs. | `src/trader_agents/hypothesis_agent.py`, `src/trader_agents/quant_research.py`, tests | Hypothesis graph can read ingredient refs and produce hypothesis-card handoffs without running backtests. Supervisor can convert accepted hypothesis refs into planning state and reject incomplete cards. |
| 39. MLflow Predictive-Model Lifecycle Tool Universe | Coordinate engineering, fitting, recording, versioning, deployment evidence, and monitoring for time-series predictive models. | `src/trader_research/ml/`, optional MLflow integration package, core prediction contracts, `src/trader_standard/`, `src/trader_mcp/`, Postgres research artifacts, docs, tests | Planned umbrella after task 57H. MLflow owns ML training telemetry, model packages, registered model versions, tags, and aliases. Trader owns generic optimisation plans/trials/selections, backtests, dataset/feature/training/deployment specs, validation/promotion decisions, lineage, and immutable resolved model refs. Tasks 39A-39J must be complete before the ML Agent graph is considered useful. |
| 39A. MLflow Runtime Adapter And Mutation Policy | Establish the optional MLflow runtime and safe MCP side-effect model. | MLflow tracking sink, ML client adapter, MCP environment/config, tool contracts, tests | Reuse `ExperimentTrackingSink` for disposable generic run projections, then add configured training/registry URIs, authentication references, namespaces, timeouts, artifact access, and client/server compatibility checks. Add `ml_list_training_experiments` with no old-name alias. Keep projection writes, ML training writes, and alias promotion independently gated. |
| 39B. Feature-Set Engineering And Validation | Make feature definitions immutable, point-in-time aware, and reusable offline and online. | `src/trader_research/ml/features.py`, feature implementation refs, Postgres projections, MCP tools, tests | Add `ml_create_feature_set` and `ml_validate_feature_set`. Specifications record feature names/types, source implementations and hashes, parameters, lookbacks, event time, availability time, warmup, missing/stale policy, preprocessing fit scope, dependencies, output schema, and optional Quantitative Methods refs. Validation checks no-lookahead semantics, deterministic fixtures, schema stability, and online/offline computability without fetching undeclared data. |
| 39C. Point-In-Time Training Datasets And Split Plans | Bind feature/target construction to Data Agent evidence and trading-time chronology. | `src/trader_research/ml/datasets.py`, Data Agent manifests, Postgres projections, MCP tools, tests | Add `ml_create_training_dataset` and `ml_create_time_series_split_plan`. Consume exactly one or more explicit compatible Data Agent manifests, never loose hidden scope. Record point-in-time joins, target formula/horizon/availability, symbol-universe policy, training/validation/calibration/test windows, expanding/rolling/anchored folds, purge/embargo, cross-sectional holdouts, row/fold profiles, quality refs, and dataset digest. Random splitting is rejected by default. Emit leakage and sufficiency blockers before fitting. |
| 39D. Training Pipeline Registration And Fitting | Execute bounded, reproducible model training and record it in MLflow. | `src/trader_research/ml/training.py`, registered trainer implementations, MLflow adapter, MCP tools, tests | Add `ml_register_training_pipeline`, `ml_validate_training_pipeline`, `ml_create_training_spec`, and gated `ml_run_training`. Pipelines may be maintained, handwritten, or AI-produced but must be supplied as immutable validated source/package artifacts; prompt text is never executable. Specs bind dataset/split refs, framework and MLflow flavor, parameter schema, hyperparameters, resources, seeds, dependency lock/environment, code hash, experiment identity, timeout, and output contract. Fitting logs parameters, metrics, dataset inputs, source refs, artifacts, signature, input example, and packaged model to MLflow. |
| 39E. MLflow Run Reconciliation And Lineage | Make external run state inspectable and trustworthy inside Trader. | `src/trader_research/ml/tracking.py`, Postgres projections, MCP tools, tests | Add `ml_get_training_run` and `ml_reconcile_mlflow_run`. Persist `mlflow_run_ref` records containing tracking-server identity, experiment/run IDs, status, timestamps, dataset inputs/digests, logged model URI/digest, signature, parameters, metrics, tags, source and environment hashes, and client/server versions. Reconciliation verifies the run belongs to the configured namespace and expected training spec; partial, deleted, failed, foreign, or inconsistent runs block downstream registration. Retries are idempotent by training-spec and run identity. |
| 39F. Time-Series Model Evaluation And Comparison | Produce ML-owned evidence that a fitted model predicts as declared. | `src/trader_research/ml/evaluation.py`, MLflow evaluation adapter, prediction artifacts, MCP tools, tests | Add `ml_evaluate_model` and `ml_compare_model_versions`. Evaluate chronological fold and untouched holdout predictions, naive and incumbent baselines, task-appropriate predictive metrics, calibration, threshold stability, residual/autocorrelation diagnostics where relevant, cross-symbol/regime stability, uncertainty, and leakage audit results. Persist bounded predictions or refs with model/dataset/fold identity. A passed model evaluation does not claim trading profitability; strategy PnL remains Evaluation Agent evidence after backtesting. |
| 39G. Model Registry Versioning And Promotion Evidence | Reconcile MLflow Model Registry versions with Trader approval lineage. | `src/trader_research/ml/registry.py`, MLflow adapter, Postgres projections, MCP tools, tests | Add `ml_register_model_version`, `ml_get_model_version`, `ml_list_model_versions`, `ml_resolve_model_alias`, `ml_compare_model_versions`, and gated `ml_assign_model_alias`. Registration requires a reconciled successful run and passed model evaluation. Persist registered-model name, immutable version, source run, model URI/digest, signature, environment, tags, and observed aliases. Use tags and aliases rather than deprecated stages. Alias assignment requires an explicit `ml_model_promotion_report`, policy approval, and expected-current-version compare-and-set semantics to prevent races. Every consumer resolves aliases and pins the immutable version before use. |
| 39H. Runtime Prediction Contract And MLflow Adapter | Add prediction to the trading platform without coupling core runtime to MLflow. | core `trader` prediction protocol/events, optional MLflow integration adapter, `trader_standard` consumers, tests | Define dependency-free feature-batch, predictor, prediction-result, model-identity, timeout, and failure-policy contracts in `trader`. Keep MLflow/pandas/framework dependencies in an optional adapter that loads a pinned MLflow model version or calls an approved serving endpoint. Validate digest/signature/environment, input ordering/types/nullability, output shape/semantics, deterministic fixture parity, latency bounds, and stale/error behavior. Never dynamically follow an alias during a run and never call MCP from the hot path. |
| 39I. Model-Backed Strategy And Deployment Integration | Bind validated models to strategies and controlled runtime environments. | `src/trader_research/ml/deployment.py`, strategy implementation/versioning, `trader_standard` model-backed signals/strategies, backtest services, MCP tools, tests | Add `ml_create_deployment_manifest` and `ml_validate_deployment`. A manifest pins model version, feature-set version, inference adapter, prediction semantics/horizon, strategy consumers, thresholds, latency/failure policy, environment, and eligibility. Strategy validation proves offline/online feature and prediction parity; backtests use the same inference adapter as the trading loop. Initial eligibility is `backtest` or `paper`. The ML Agent cannot restart services, change runtime config, mutate broker state, or grant live eligibility; those remain explicit operator/promotion controls. |
| 39J. Prediction Monitoring And Drift | Close the lifecycle with version-aware runtime evidence. | core prediction event schema, `src/trader_research/ml/monitoring.py`, Postgres projections, MCP tools, tests | Runtime code emits bounded prediction events containing decision/as-of timestamps, feature-set/model versions, prediction semantics, latency, status, and safe feature/payload hashes or summaries. Add `ml_summarize_predictions` and `ml_compute_drift_report` to join predictions with realized targets and compute input/output drift, calibration/performance decay, coverage, latency, stale features/models, and version changes. Monitoring runs outside the hot path and does not copy unrestricted feature matrices or call MLflow once per prediction. |
| 40. ML Agent Graph and Handoff | Coordinate the proven deterministic ML lifecycle tools. | `src/trader_agents/ml_agent.py`, ML policy/state, `src/trader_agents/quant_research.py`, tests | Deferred until 39A-39J pass end-to-end evidence. The graph can route feature, dataset, training, evaluation, registry, deployment, prediction, and drift refs; retry bounded failed research steps; and stop on blockers. It cannot select undeclared Data Agent scope, execute arbitrary prompt code, forge evaluation/promotion, mutate live trading, or assign an alias unless the explicitly gated deterministic tool accepts a passed promotion report. |
| 41. Attribution Service and MCP Tool | Add return attribution after baseline backtest artifacts exist. | `src/trader_research/attribution.py`, `src/trader_mcp/server.py`, tests | `research_analyze_return_attribution` summarizes PnL by symbol, period, side if available, and top trades using trade/equity artifacts without LLM interpretation. |
| 42. Evaluation Critique Logic and MCP Tool | Extend performance reporting into stronger skeptical evaluation. | `src/trader_research/evaluation/performance.py`, `src/trader_mcp/server.py`, tests | `evaluation_generate_report` consumes data quality, backtest, performance, attribution, warning, cost, and sample-size evidence; weak baselines, missing data-quality reports, unexplained warnings, destroyed edge under costs, or thin samples produce blockers in `evaluation_report.json`. |
| 43. Evaluation Agent Graph and Handoff | Add Evaluation Agent identity and supervisor handoff consumption once Evaluation-owned MCP reports are useful. | `src/trader_agents/evaluation_agent.py`, `src/trader_agents/quant_research.py`, tests | Evaluation graph consumes evidence artifacts and cannot create hypotheses, mutate data, or run backtests. Supervisor preserves blockers, caveats, and verdicts before recommendation synthesis. |
| 44. Adversarial Robustness Core and MCP Tool | Produce skeptical, reproducible attacks against immutable baseline backtests. | `src/trader_research/robustness/`, `src/trader_mcp/`, Postgres research artifacts, docs, tests | Optimisation-specific audit planning/judgment now exists in 57F. Generalise it so Adversarial declares attacks and judges immutable evidence while Supervisor executes variants. Cover fee/slippage, chronology/regimes, parameter/provider/seed/budget/objective sensitivity, concentration, missing data, and multiple-testing risk. |
| 45. Adversarial Agent Graph and Handoff | Add Adversarial Agent identity and supervisor handoff consumption after robustness tools exist. | `src/trader_agents/adversarial_agent.py`, `src/trader_agents/quant_research.py`, tests | Adversarial graph can call robustness tools but cannot produce recommendations or promotion decisions. Supervisor can block promotion readiness on robustness failures without modifying Adversarial artifacts. |
| 46. Robustness Backtest Variants | Add explicit Supervisor-executed variants for cost, parameter, scope, provider, and data perturbations. | `src/trader_research/robustness/`, canonical optimisation/backtest services, tests | Planned with task 44 using `research_run_parameter_optimization_variants` as the first delivered pattern. Variants are immutable child plans/specifications/runs linked to one baseline and change only declared dimensions. Variant generation cannot mutate implementation source, baseline artifacts, selections, or Adversarial reports. |
| 47. Recommendation Renderer and MCP Tool | Generate Quant Research recommendation reports after performance, critique, and robustness artifacts exist. | `src/trader_research/reports.py`, `src/trader_mcp/server.py`, tests | `research_generate_recommendation` consumes experiment, performance, evaluation, and robustness artifacts when available; paper-promotion readiness is blocked without required critique artifacts. |
| 48. Quant Research Supervisor Synthesis Graph | Extend the supervisor graph to synthesize specialist artifacts into recommendation state. | `src/trader_agents/quant_research.py`, tests | Supervisor synthesizes Data, Quantitative Methods, Hypothesis, optional ML, Evaluation, and Adversarial artifacts without bypassing specialist graphs or MCP tools. |
| 49. Experiment Runner and MCP Tool | Implement the high-level experiment runner last. | `src/trader_research/runner.py`, `src/trader_mcp/server.py`, tests | `research_run_experiment` composes earlier tools and returns recommendation paths, verdict, and warnings. It must not be the first proof of strategy, backtest, performance, or agent correctness. |
| 50. Compiled Kernel Conformance and Runtime Acceleration | Revisit compiled kernels only after profiling shows value. | `src/trader_research/methods/kernels.py`, tests | Replace exact Python/C++ output replication as the goal with contract-first C++ conformance/equivalence: independently check Python and C++ against the method contract, report bounded implementation deltas, and integrate runtime acceleration only when safe and worthwhile. |
| 51. Import Boundary Tests | Add tests that assert `trader` does not import `trader_research`, `trader_mcp`, `trader_agents`, or other agent/tool packages, and that dependencies flow one way. | `tests/test_package_boundaries.py` | The architectural separation remains executable as method packages, strategies, backtests, reports, and later agents are added. |
| 52. MCP, Toolchain, and LangGraph Contract Tests | Add tests that call MCP tool functions directly, exercise the end-to-end toolchain, and later exercise LangGraph agent allowlists/state transitions. | `tests/test_mcp_tools.py`, `tests/test_mcp_research_toolchain.py`, `tests/test_langgraph_agents.py` | Tool names, required schemas, side effects, envelope shapes, agent owners, artifact refs, toolchain ordering, and graph boundaries are stable incrementally. |
| 53. Iterative Documentation | Update bounded-context docs in the same change as each implementation slice. | `docs/research_agents/architecture.md`, `docs/research_agents/agents.md`, `docs/research_agents/mcp_tools.md`, `docs/research_agents/workflows.md`, `docs/research_agents/operations.md`, `tests/test_research_agent_docs.py` | Done for the research-agent/MCP documentation restructure. Current docs describe architecture, agent identities, MCP tools, workflows, operations, detailed contracts, safe usage boundaries, and package-boundary rules; historical notes live under `docs/research_agents/history/`. |
| 54. `trader_research` Capability Packaging And Docstring Standardization | Move broad research services into bounded packages and enforce canonical imports. | `src/trader_research/data/`, `src/trader_research/methods/`, `src/trader_research/strategy_candidates/`, `src/trader_research/risk_managers/`, `src/trader_research/backtests/`, `src/trader_research/evaluation/`, `tests/test_package_boundaries.py`, docs | Package-level public surfaces are canonical. Old flat modules such as `math_tools.py`, `strategies.py`, `strategy_validation.py`, and `method_packages.py` are removed; no compatibility shims are added. Boundary tests assert the broad flat modules no longer exist and repo code uses canonical capability packages. |
| 56. Implementation Registry And Method-Card Decoupling | Invert the current dependency so methodology extraction is an encapsulated optional producer, not an execution prerequisite. | `src/trader_research/implementations/`, Postgres research artifacts/projections, producer-neutral lineage, `src/trader_mcp/`, docs, tests | Done. The canonical downstream input is immutable `implementation_version`; rich cards, packages, candidates, templates, and authoring workflows are not execution identities. Optional generic provenance records origin without changing eligibility. |
| 56A. Canonical Implementation-Version Domain | Define the stable boundary consumed by every later strategy, risk, ML, robustness, and backtest service. | `src/trader_research/implementations/domain.py`, storage adapters, Postgres schema/projections, artifact registry, package-boundary tests | Add immutable `implementation_version` and `implementation_validation_report` schemas for `indicator`, `signal`, `strategy`, and `risk_manager` kinds. Record version ID, kind, authoring origin, canonical source/package payload and SHA-256, entrypoint, platform interface, parameter schema, dependency lock/environment, declared capabilities, portfolio/runtime requirements, resource bounds, source/repository metadata, optional generic provenance refs, and no-live-trading policy. Canonical source and manifests live in Postgres; validation may materialize bounded temporary files but no filesystem path is product identity or durable authority. The domain must not import `trader_research.knowledge`, rich method cards, strategy candidates, or risk-manager candidates. Quantitative Methods retains ownership of indicator/signal evidence; the Supervisor owns strategy/risk implementation versions. |
| 56B. Strategy And Risk Implementation Registration And Validation | Make independently authored executable research code a first-class MCP input. | `src/trader_research/implementations/registration.py`, `validation.py`, MCP adapters/constants/config, Postgres projections, docs, tests | Add `research_register_strategy_implementation`, `research_validate_strategy_implementation`, `research_register_risk_manager_implementation`, and `research_validate_risk_manager_implementation`. Registration accepts explicit bounded source/package content or an approved content-addressed source ref, never prompt text or arbitrary server filesystem paths. Validation checks source hash, imports, dependency declarations, platform interface, entrypoint/factory, parameter schema, deterministic fixture behavior, order/risk bounds, timeout/resource policy, and no broker/raw-SQL/live mutation. A strategy or risk implementation with no methodology, method-card, or method-package refs must be fully valid and backtest-eligible. AI-produced code receives no weaker trust treatment than handwritten code. |
| 56C. Maintained And Method-Generated Producer Adapters | Make every existing producer terminate at the same registration boundary. | maintained strategy/risk catalogs, Quant Methods packaging/generation, implementation registration service, lineage tests | Maintained template builders, validated Quant Methods packages, and method-card-generated code submit source plus metadata through the implementation registration/validation services and receive normal implementation-version refs. Method-card IDs, evidence refs, package refs, template identity, generator/model metadata, and prompts hashes where applicable are optional generic provenance only. Downstream behavior cannot vary by producer origin. Retiring or superseding a method card does not mutate an already registered immutable implementation version; consumers may report provenance status separately. No adapter exposes rich-card fields to the implementation domain. |
| 56D. Remove Method-Card Execution Coupling | Delete the candidate-centric admission model once implementation registration and the 57A specification replacement land. | MCP registration/constants, artifact registry, Postgres cleanup/reset, boundary tests | Done without aliases, compatibility readers, schema translation, or dual writes. Candidate tools and artifact types are retired from canonical surfaces; old development rows/tables are reset rather than translated. |
| 57. Reproducible Strategy, Risk, Backtest, And Optimisation Specifications | Separate executable code identity, configured behavior, experimental scope, provider operation, and evidence. | specification/backtest/optimisation/tracking domains, Postgres projections, `src/trader_mcp/`, docs, tests | Implementation is done through 57H. Tasks 57I-S qualify the complete 56/57 cutover before task 57 is marked done. |
| 57A. Strategy And Risk Specifications | Bind validated code versions to explicit configured behavior without binding market-data scope. | `src/trader_research/specifications/strategy.py`, `risk.py`, Postgres projections, MCP tools, docs, tests | Add `research_create_strategy_specification`, `research_validate_strategy_specification`, `research_create_risk_stack_specification`, and `research_validate_risk_stack_specification`. A strategy specification pins one passed strategy implementation version, scalar parameters, portfolio mode, sizing/allocation policy, required runtime context, and execution assumptions. A risk-stack specification pins ordered passed risk-manager implementation versions and explicit thresholds/parameters. Symbols, timeframe, source, and date windows are forbidden. Deterministic IDs include immutable version refs and normalized configuration. These tools replace candidate and candidate-stack contracts; no old request form remains registered. |
| 57B. Reproducible Backtest Specifications | Make the complete experimental configuration immutable before execution. | `src/trader_research/specifications/backtest.py`, Data Agent artifact resolution, Postgres projections, MCP tools, docs, tests | Add `research_create_backtest_specification` and `research_validate_backtest_specification`. Bind exactly one passed strategy specification, optional passed ordered risk-stack specification, exactly one Data Agent dataset manifest, matching quality evidence, initial portfolio state, fees/slippage, benchmark, execution assumptions, deterministic seeds where relevant, runtime limits, and logging policy. Reject loose symbols/timeframes/windows/source filters, unresolved or mutable refs, missing quality evidence, implementation hash drift, parameter grids, and hidden defaults that affect results. Persist the normalized specification before any runner invocation; its ID is the parent for baseline, robustness, ML, and walk-forward child runs. |
| 57C. DB-First Specification Execution And Evaluation | Run only validated specifications and make structured storage the complete research authority. | `src/trader_research/backtests/`, Evaluation/comparison services, MCP tools, ResearchArtifactStore/Postgres schema, docs, tests | Done. `research_run_backtest_specification` writes complete baseline/portfolio evidence to `backtest_run`; lookup/comparison consume canonical refs; candidate request forms and canonical filesystem bundles are gone. |
| 57D. Provider-Neutral Optimisation Ledger And Protocols | Separate canonical experiment evidence from proposal and projection providers. | `src/trader_research/optimization/contracts.py`, artifact registry, Postgres projections, tests | Done. Defines `OptimizationEngine`, `OptimizationTrialExecutor`, and `ExperimentTrackingSink`; plans/runs/trials pin the resolved provider profile, version, configuration digest, capabilities, and seed. No core optimisation module imports Optuna, MLflow, knowledge, method cards, or ML packages. |
| 57E. Validated Optimisation Objectives | Admit custom scalar objectives through the same implementation boundary. | implementation registry, closed observation contract, Quant Methods MCP tools, tests | Done. `research_register_optimization_objective` and `research_validate_optimization_objective` bind hash-validated code to `OptimizationObservation`; code receives bounded plain data and cannot access stores, files, networks, events, or tools. |
| 57F. Deterministic Optimisation Execution And Independent Review | Execute bounded studies while retaining complete trial and review evidence. | grid/random engines, executor/services, Evaluation, Adversarial, MCP, Postgres projections, tests | Done. Adds runtime/create/run/get/variant tools, deterministic resume/tie-breaks, complete failed-attempt evidence, sealed holdout Evaluation, and Adversarial plan/judgment. Promotion readiness requires both independent reports. |
| 57G. Optional Optuna Adapter | Add adaptive sampling without making Optuna a platform dependency or evidence store. | optional adapter, environment/config health, dedicated Postgres schema/role, conformance tests | Done. Optuna loads lazily, uses seeded sequential TPE with no pruning, authenticates to a non-public dedicated schema/role, and reconciles terminal provider state against Trader trials before resume. Provider loss leaves canonical evidence readable and the run partial/blocked. |
| 57H. Provider-Neutral Experiment Tracking Projection | Project completed canonical evidence to optional analytical tracking systems. | `src/trader_research/tracking/`, MCP/config gates, optional MLflow sink, tests | Done. `research_project_experiment_tracking` derives an idempotent payload from canonical run/trials; callers cannot submit metrics/tags. Projection writes require generic external-research and sink-specific gates and are explicitly non-authoritative. |
| 57I. Freeze Revision And Build Acceptance Matrix | Establish exactly what is being tested and prevent a moving worktree from invalidating conclusions. | Git checkpoint, `git status --short`, `git diff --stat`, registered-tool/config/artifact/projection inventories, invariant-to-test matrix | In progress. The invalid first freeze is superseded; `verification-57i-freeze-v2` will identify the cleaned checkpoint after 57K-R verification. Any later product change invalidates its phase and downstream evidence. |
| 57J. Provision Isolated Verification Runtime | Make destructive and external integration tests safe, repeatable, and visibly separate from operator state. | `tests/conftest.py`, dedicated Trader verification DB, optional dedicated Optuna schema/role, disposable tracking experiment, environment manifest | Require `PG_TEST_DB` ending `_test` or `_testing`; never fall back to `PG_DB`; use a least-privilege verification role where practical; pin locale/timezone/dependency versions/seeds and record credential-free config digests. Capture operator DB table counts and stable content fingerprints before and after every Postgres phase. Default all mutation gates off and enable only the gate needed by the current profile. A guard failure or operator fingerprint change is an immediate stop condition. |
| 57K. Static, Contract, And Regression Gate | Establish that the frozen revision is internally consistent before spending time on integration evidence. | Ruff, compileall, mypy, non-Postgres pytest, MCP/docs/domain/package/SQL boundary suites, `git diff --check` | Run `uv run ruff check src tests`, `python -m compileall -q src/trader_research src/trader_mcp src/trader_agents src/trader_standard src/trader`, `uv run mypy`, `uv run pytest -m 'not postgres' -q`, focused MCP/docs/domain/package/SQL suites, and `git diff --check`. Inventory deleted candidate-era tests against replacement coverage. Treat unexpected skips, collection warnings, import-time optional-provider failures, stale registered tools, compatibility aliases/readers, and package-boundary regressions as blockers. Save exact commands and summaries against the frozen revision. |
| 57L. Realistic Deterministic Evidence Fixture | Replace the toy empty-strategy smoke graph as the acceptance fixture while keeping it bounded and reproducible. | `tests/support/` fixture builder or checked-in fixture data, realistic strategy/risk/objective sources, fixture assertions | Use at least three symbols and enough chronological bars for warm-up, multiple entries/exits, selection, and untouched holdout. Pin timestamps, prices, source hashes, quality snapshots, costs, seed, and expected scope. The handwritten strategy must place both buy and sell orders and produce parameter-sensitive outcomes; the risk manager must approve and reject observable orders; fees/slippage and final exposure must be nonzero where expected. Selection and holdout windows must be disjoint with different manifest/content hashes. Assert fixture semantics directly so a no-trade or constant-objective run cannot pass the graph accidentally. |
| 57M. Postgres-Native MCP Evidence Graph | Prove the public tool boundary produces complete, visible, realistic product evidence. | `tests/test_postgres_optimization_evidence_graph.py`, `PostgresResearchArtifactStore`, typed projections | Call MCP tools, not service internals, for strategy/risk implementation registration and validation; strategy/risk/backtest specification creation and validation; selection backtest; objective registration/validation; plan creation; built-in-grid execution/results; selected holdout specification/run; Evaluation report; Adversarial plan; Supervisor variants; and Adversarial report. Require real trades, nonzero exposure/costs, risk decisions, 4-8 materially distinct trials, and a deterministic selection. Every durable ref must be `research://postgres/{artifact_type}/{id}` and every canonical artifact must be visible through both `research_artifacts` and its typed pgAdmin projection. Evaluation and Adversarial must not mutate the selected trial/specification. No canonical filesystem path may appear in a response or row. |
| 57N. Determinism, Integrity, And Leakage Tests | Prove that reproducibility and holdout claims survive independent repetition and hostile state changes. | Repeated clean-DB graph runs, mutation/tamper cases, lineage assertions | Run the same graph twice from clean verification databases and compare IDs, trial sequence, suggestions, observations, objective values, tie-break diagnostics, selection, and report lineage. Verify seeded-random order independently. Persist every rejected/failed attempt and exception. Tamper with implementation source/hash, validation payload, parameters, dataset/quality snapshot, costs, provider digest, trial order, and selected ref; loaders must fail closed. Instrument the trial executor/artifact reads to prove holdout rows and metrics are never read during proposal, child execution, objective evaluation, or selection. Evaluation may access the holdout only after selection is immutable. |
| 57O. Restart, Resume, And Fault-Injection Tests | Verify canonical Postgres state is sufficient for recovery and that partial work is never misrepresented as complete. | Subprocess/service-recreation tests, injected executor/provider/store failures, resume assertions | Stop after plan persistence, after suggestions, after a child backtest, after a failed objective, and before final selection; recreate MCP/services with only canonical configuration and resume. Confirm completed trials are not duplicated, sequence numbers remain stable, retries are bounded and fully recorded, and deterministic selection matches an uninterrupted run. Exercise child timeout, invalid objective result, unavailable metric, artifact-store write failure, Optuna loss, and provider/configuration drift. Terminal evidence remains readable; unsafe resume yields explicit partial/blocked status and requires a new run rather than engine switching or state repair. |
| 57P. Provider Independence And Adapter Qualification | Separate proof of the core product from proof of optional provider adapters. | Core no-provider environment, Optuna conformance/integration profile, tracking-sink profile | In a minimal environment where importing Optuna and MLflow fails, start MCP, run grid and seeded-random optimisation, resume, and read all canonical results. For Optuna qualification, use its dedicated non-`public` schema and writer role, seeded sequential TPE, no pruning, and reconcile provider terminal states to canonical Trader trials; test package absence, DB loss, stale/mismatched study state, and forbidden public-schema credentials. For each tracking sink, project only completed supported canonical runs, call twice to prove idempotence, reject caller metrics/tags/URIs, delete or disable the external record, and prove Trader plans/trials/selections/reports remain readable and unchanged. Optional profile failure does not fail core acceptance but leaves that profile not qualified and gated off. |
| 57Q. Policy, Security, And Resource-Boundary Tests | Challenge the admission and execution boundaries directly rather than inferring safety from happy paths. | MCP gate matrix, malicious objective/implementation fixtures, limit tests, SQL/package-boundary tests | Exercise backtest, optimisation, generic external-write, Optuna-write, and tracking-write gates independently and inspect `mcp_get_config`. Reject objective code attempting direct or indirect filesystem, network, database, subprocess, import, builtin, raw-event, artifact-store, or tool access. Reject undeclared observation fields/metrics, non-finite scores, dataset/implementation/cost/provider/holdout/fold changes, loose data scope, and undeclared tunables. Enforce trial/retry/time/resource limits and bounded error payloads. Confirm agents have no direct SQL or broker mutation path, core packages do not import research/provider packages, and temporary validation materialization is cleaned without becoming product identity. |
| 57R. Projection, Operator, And Bounded-Scale Checks | Prove that operators can inspect and operate the feature without relying on test-only internals. | SQL reconciliation queries, pgAdmin-visible row checks, bounded load profile, cleanup log | For each artifact in the graph, reconcile ID, type, status, parent/child lineage, selected refs, trial counts, and payload hashes between canonical JSONB and typed projections. Run a declared bounded profile such as 3-10 symbols, 1,000-10,000 bars per symbol, 64 grid trials, and 100 seeded-random trials; record wall time, peak memory where available, database growth, and result-query timing against declared run resource limits rather than a machine-specific universal threshold. Verify sequential execution/no pruning assumptions, deterministic cleanup, indexes used for principal lookup paths, and unchanged operator DB/knowledge corpus/provider namespaces. |
| 57S. Acceptance Record And Release Decision | Make the outcome auditable and prevent a partial green run from being described as system verification. | Tracker evidence update plus CI/test logs and DB evidence-ref inventory | Record the exact Git revision, UTC time, dependency lock hash, environment/profile digests, test database and provider namespaces, commands/results/durations, skips, warnings, evidence refs, projection row counts, operator before/after fingerprints, discovered defects/fixes, rerun scope, and residual risks. Core acceptance requires 57I-57O and 57Q-57R with zero blockers. Optuna and each tracking sink have separate qualified/not-qualified decisions from 57P. After any fix, rerun that phase and all dependent phases before marking task 57 done. Do not copy verification-database rows into the operator database or treat disposable provider state as canonical evidence. |
| 58. Walk-Forward Optimisation Core | Run a reproducible sequence of in-sample selection and locked out-of-sample strategy/model tests. | `src/trader_research/optimization/`, task 57 backtest specifications, `src/trader_research/ml/`, Postgres research artifacts, `src/trader_mcp/`, docs, tests | Deferred until 39I, 44, and 46 are proven. Compose the existing `OptimizationEngine` and `OptimizationTrialExecutor` protocols inside each fold; do not create a WFO-specific optimiser/provider contract. A plan pins implementation/deployment version, base specification, Data Agent scope, fold boundaries, purge/embargo, objective, costs, seed, budget, and stop/resume policy. Each fold locks its selected parameter/model before untouched out-of-sample execution and preserves the complete child ledger without producing a promotion verdict. |
| 59. Walk-Forward Evaluation And Adversarial Audit | Separate out-of-sample interpretation from attacks on the optimisation procedure. | `src/trader_research/evaluation/`, `src/trader_research/robustness/`, Postgres research artifacts, `src/trader_mcp/`, docs, tests | Deferred until task 58. Add `evaluation_generate_walk_forward_report` and `adversarial_audit_walk_forward`. Evaluation stitches out-of-sample fold returns without in-sample contamination and reports aggregate performance, coverage, turnover, costs, fold dispersion, and blockers. Adversarial tests fold-boundary/window sensitivity, objective changes, neighboring parameters/models, selection instability, in-sample to out-of-sample degradation, fee/slippage stress, symbol/period concentration, search-budget sensitivity, multiple-testing/selection-bias evidence, and nested-procedure risk. Reports preserve the baseline plan/run and variant refs, cannot rewrite selections, and cannot promote a strategy or model. |

## Incremental Build Slices

### Slice 1: First MCP Tool Evidence

Implement chunks 0-7 first. This slice intentionally avoids broad research-domain schemas, strategy work, backtests, robustness, and report generation. Its purpose is to prove the new package boundary, MCP transport, shared envelope, and one real Data Agent tool.

Evidence target:

```text
MCP server starts
  -> client lists tools
  -> client calls data_get_inventory
  -> client receives a valid ToolEnvelope
```

### Slice 2: First LangGraph Agent Identity

Implement chunks 8-9 next. This proves that a distinct LangGraph Data Agent identity can use the MCP tool to perform its own purpose and produce its owned artifact.

Evidence target:

```text
Data Agent graph starts
  -> graph state includes Data Agent identity
  -> graph calls data_get_inventory through MCP client
  -> graph returns dataset manifest payload/reference
```

### Slice 3: Data Tool Workflow and Data Agent Graph

Implement chunks 10-16 next. This builds out the data-quality and data-loading capabilities while the MCP surface and Data Agent LangGraph identity are already live.

Use `plans/mcp_trading_research_tools_slice3_test_conditions.md` as the intermediate acceptance contract for the full slice before marking chunks 10-16 `Done`.

Evidence target:

```text
health/config
data_get_inventory
data_summarize_quality
data_ensure_loaded
data_summarize_quality
Data Agent graph completes the same workflow with allowed MCP tools only
```

### Slice 4: Research Foundations and Supervisor Skeleton

Implement chunks 17-22 after the Data Agent MCP and LangGraph workflow is proven. This is where broader migration,
shared schemas, and the Quant Research Supervisor identity belong. The supervisor starts early, but only as an
orchestrator over Data Agent artifacts and explicit missing-specialist blockers.

Use `plans/mcp_trading_research_tools_slice4_test_conditions.md` as the intermediate acceptance contract for the full
slice before marking chunks 17-22 `Done`.

Evidence target:

```text
Quant Research Supervisor graph starts
  -> consumes Data Agent manifest/quality references
  -> records missing Quantitative Methods, ML, Hypothesis, Evaluation, and Adversarial artifacts as blockers
```

### Slice 4A: Data Agent LLM Control Loop

Implement chunk 22H after the provider-aware Data Agent tools, symbol discovery preflight, and supervisor handoff are
proven, and before starting new specialist tool families. This is the first LLM integration point because the Data
Agent now has a complete bounded action surface: symbol discovery, inventory, quality, and explicit loading. It does
not replace the later supervisor LLM loop; it proves the specialist-agent LLM pattern in the narrowest complete domain.

The LLM belongs inside a Data Agent control-policy node, not inside the Data Agent MCP tools. It should turn
natural-language data requests into typed action proposals such as `discover_symbols`, `inspect_inventory`,
`summarize_quality`, `ensure_loaded`, `retry_with_changes`, `block`, or `finish`. A deterministic router validates the
proposal before any MCP tool call.

The policy node should use a provider-neutral LLM client selected by runtime configuration. `22H` should include the
interface and fake test implementation first, then add adapters for the configured external model backend. Hosted
gateways such as OpenRouter-style APIs and local servers such as Ollama are runtime backends; they must not leak into
Data Agent tool schemas or deterministic MCP services.

Evidence target:

```text
natural-language bounded data request
  -> runtime LLM backend is configured and reachable, or the graph fails fast with a structured blocker
  -> Data Agent LLM policy node emits typed action proposal
  -> deterministic router validates provider context, mandatory discovery, allowlist, side-effect policy, and loop budget
  -> graph calls existing Data Agent MCP tools, blocks early, or finishes
```

Required guardrails:

- MCP tools remain deterministic and provider-aware
- symbol discovery cannot be skipped before inventory, quality, or loading
- provider, instrument type, and bar type are validated before any data-source query
- local-mutating loading remains policy-gated and bounded
- no SQL, broker mutation, strategy, backtest, or supervisor tools are available to the Data Agent LLM
- missing or unsupported LLM provider configuration fails fast before tool execution
- invalid structured output fails closed or enters a bounded repair path
- no raw prompt, hidden reasoning, or scratchpad persistence

### Slice 5: Knowledge-Backed Quantitative Methods MCP Tool Creation

Implement chunks 23A-24. This creates the Quant Methods Knowledge Base ingestion/retrieval layer, then proves the first
Quantitative Methods MCP tools before the Quantitative Methods LangGraph identity exists.

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
knowledge_update_method_card_status
knowledge_validate_citations
math_list_method_contracts
math_validate_method_contract
math_register_method_implementation
math_run_indicator_fixtures
math_run_signal_fixtures
math_generate_python_method
  -> Postgres-backed source/chunk/embedding/index state, ingestion reports, hybrid retrieved refs, dereferenced chunk text, approved method cards, citation validation, method metadata, Python implementation manifests, quarantined generated Python, and fixture reports
  -> declares agent_owner = Quantitative Methods Agent
  -> records source IDs, locators, embedding provider/model/index version, lexical/vector/combined retrieval scores, assumptions, implementation hashes, fixture status, and failure modes
```

Implemented 23L evidence:

```text
math_run_signal_diagnostics
math_run_multiple_testing_report
  -> approved method cards validate rank_ic and benjamini_hochberg contracts
  -> records signal candidate family size, tested parameter grid, raw p-values, adjusted p-values, accepted/rejected candidates, warnings, and blockers
```

### Slice 6: Method Package Handoff

Implement chunk 23N. This turns source-backed, fixture-validated Python indicator and signal implementations into
portable method packages that strategy tooling can consume without needing to understand the full knowledge-store or
fixture-runner internals. C++ artifacts may be referenced as optional metadata only; they do not gate packaging.

Evidence target:

```text
validated method_implementation_manifest.json
  -> indicator_validation_report.json or signal_implementation_validation_report.json
  -> math_package_method_artifact
  -> method_package_manifest.json
```

### Slice 7: Strategy Candidate Tools

Implement chunks 25-27. Strategy work moves before new specialist agent graphs because it is the next link in the
meaningful MCP chain. The first strategy surface is template-backed and source-backed: it writes deterministic Python
strategy code implementing `trader.strategies.Strategy`, not arbitrary user-supplied runtime code.

Evidence target:

```text
method_package_manifest.json
  -> research_list_strategy_templates
  -> research_create_strategy_candidate
  -> strategy_implementation.py
  -> strategy_candidate_manifest.json
  -> research_validate_strategy_candidate
```

### Slice 8: Baseline Backtest Tools

Chunks 28-30 are implemented. They wrap the existing `trader.backtest.BacktestRunner` only after strategy candidates
are explicit and validated, keep the first backtest service narrow, expose one minimal single-run lookup path, and add a
persisted comparison layer over explicit run refs.

Current status:

- Task 28: Done. `research_run_backtest` consumes a passed strategy validation report and exactly one Data Agent
  `dataset_manifest`; symbols, asset class, timeframe, source filter, row counts, and window are derived from that
  manifest and persisted as `BacktestDataScope`.
- Task 29: Done. MCP registers `research_run_backtest` and `research_get_backtest_results`; run execution is gated by
  `TRADER_MCP_ALLOW_BACKTESTS=true`, while result lookup is read-only.
- Task 30: Done. MCP registers `research_compare_backtest_results` as a Quant Research Supervisor local-mutating tool
  that compares persisted task-28/29 bundles by explicit refs, ranks numeric metrics, warns for non-like-for-like runs,
  and writes `comparison_report.json` without running backtests.

Evidence target:

```text
strategy_candidate_manifest.json + dataset/data-quality refs
  -> research_run_backtest
  -> BacktestRunRef + result bundle
  -> research_get_backtest_results
  -> research_compare_backtest_results
  -> comparison_report.json
```

### Slice 9: Performance Reporting

Chunks 31-32 are implemented. The first Evaluation-owned tool reports what happened in one persisted backtest with
concrete metrics, data-quality blockers, costs, benchmark evidence, warnings, and caveats. Broader skeptical critique,
attribution, robustness, and recommendation synthesis come later.

Evidence target:

```text
BacktestRunRef + result bundle + data-quality refs
  -> evaluation_generate_performance_report
  -> evaluation_report.json
```

### Slice 10: Meaningful MCP Toolchain Evidence

Chunk 33 is implemented. This is the next major product checkpoint: a user can build a source-backed method, create a
strategy, run a backtest, and inspect performance through MCP tools. The evidence test uses a deterministic Bollinger
fixture that emits real trade evidence, then verifies the Evaluation report is passed and linked back to the method,
strategy, validation, dataset, and backtest refs.

Evidence target:

```text
source-backed method package
  -> strategy candidate
  -> validated strategy
  -> baseline backtest
  -> performance report
```

### Slice 10A: Multi-Asset Portfolio And Risk Stack Tools

Implement chunks 33A-33G before expanding supervisor autonomy. The baseline method-to-backtest chain proves transport,
artifact ownership, and strategy source generation, but meaningful portfolio research needs the next layer: source-backed
strategies over multiple assets, source-backed risk managers, validated strategy/risk stacks, and portfolio/risk
evaluation evidence. Do not implement live risk controls here; these tools are for deterministic research/backtesting
artifacts only.

Evidence target:

```text
method packages
  -> multi-asset strategy candidate
  -> risk-manager candidate(s)
  -> strategy/risk stack
  -> risk-scoped portfolio backtest
  -> portfolio/risk evaluation report
```

### Slice 11: Rich Methodology Extraction And Strategy Generation

Implement chunks 33H-33N before expanding supervisor autonomy. Full-document ingestion and retrieval are now proven, but
shallow method cards are not sufficient for realistic strategy generation. This slice adds methodology candidates,
nullable field extraction with field-level citations, rich method-card drafts/approvals, documentation, and an
end-to-end pairs/cointegration-style chain that turns rich source-backed methodology evidence into strategy, portfolio
backtest, and Evaluation artifacts.

Evidence target:

```text
book source
  -> full-document ingestion
  -> methodology candidates
  -> rich field extraction
  -> rich method card
  -> generated strategy/risk candidate
  -> risk-scoped portfolio backtest
  -> Evaluation report
```

### Slice 11B: Open-World Canonical Method Cards

Implement chunks 33P-33W before the 33V evidence regression and before expanding supervisor autonomy. The 33H-33N chain proved the artifact skeleton and one
bounded pairs-style route, but real methodology discovery cannot depend on hardcoded known targets or shallow card
summaries, and method-card rows must not rely on volatile revision IDs for aggregation. This slice makes method cards
canonical evidence-backed artifacts, moves shallow cards to legacy/projection status, adds family-level evidence role
profiles, introduces inspectable evidence packets, upgrades extraction to use role-labeled evidence, adds semantic
readiness gates for implementation, signal, strategy, and risk use, and requires stable method-card set lineage before
new canonical evidence cards are generated.

Evidence target:

```text
ingested source
  -> open-world method-specific candidate
  -> family-role evidence packet
  -> role-grounded field extraction
  -> semantic readiness validation
  -> stable method-card set and canonical card revision
  -> readiness-gated method package, strategy, or risk candidate
```

### Slice 11C: Target-Bound Evidence Units And Semantic Method Cards

Implement chunks 33X-33AA before 33V. The live EMA dry run against the `Algorithmic Trading and Quantitative
Strategies` book exposed the first real semantic failure in the current chain: lineage and storage worked, but the tool
chain lost method identity before draft creation. A broad chunk covering adjacent SMA/EWA/BWMA/Bollinger/RSI material
was grouped as an SMA candidate, family-role evidence then pulled in nearby technical-indicator passages, extraction
used generic role matches, and draft creation allowed an EMA title override even though the underlying candidate
identity was not EMA-bound. Validation checked refs and readiness shape, but not whether the evidence described one
coherent target method.

This is a data-model and evidence-binding problem, not just a drafting problem. The next implementation must make the
retrieval/extraction substrate smaller and more explicit, then require every downstream claim to prove how it is bound
to the discovered method identity.

Non-compatibility rule:

- Old knowledge chunks, embeddings, methodology candidates, evidence packets, extraction reports, validation reports,
  and method-card drafts are not preserved.
- No automatic backfill, compatibility reads, legacy chunk-ref translation, synthetic set IDs, or silent migration
  paths should be added for this slice.
- Operators should truncate/recreate the affected knowledge and methodology tables, reingest approved sources, and
  rebuild evidence units, embeddings, candidates, packets, reports, and cards from the new schema.

Implementation phases:

1. `33X` creates method-evidence units as the canonical extraction/indexing surface. Evidence units are smaller than
   current coarse chunks and preserve source ordering, locator fidelity, parent section/heading, local sentence or
   paragraph indexes, text hashes, source file hashes, detected local method labels, and neighboring unit refs. The
   system must still support multi-unit reasoning by walking ordered neighbors, but no extraction field should depend on
   a broad mixed-method chunk as its atomic proof.
2. `33Y` discovers method identities before candidate grouping. Candidate artifacts should carry source-backed
   canonical/source names, aliases, abbreviations, identity evidence unit refs, query-alignment diagnostics, competing
   method labels, and identity blockers. Heading or family proximity can provide context, but must not collapse adjacent
   methods into one candidate.
3. `33Z` assembles target-bound evidence packets. Each role evidence item records whether it is bound by direct label,
   alias, same sentence, same paragraph, accepted nearby context, weak context, or rejected competing context. Readiness
   roles only count accepted target-bound evidence, and extraction may populate rich fields only from those accepted
   evidence items.
4. `33AA` validates semantic coherence before canonical method-card draft materialization. Validation blocks cross-method field contamination,
   unsupported title/method/family overrides, weak identity evidence, stale evidence-unit hashes, missing target-bound
   readiness roles, and any draft whose populated fields do not describe one coherent target method.

Evidence target:

```text
approved source
  -> evidence-unit ingestion and embeddings
  -> method identity discovery with aliases and competing-label diagnostics
  -> target-bound family-role evidence packet
  -> target-bound rich field extraction
  -> semantic validation and readiness gates
  -> stable method-card set and canonical rich card revision
```

Representative acceptance checks:

- The Algorithmic Trading technical-indicator section discovers SMA, EWA/EMA, BWMA, Bollinger Bands, and RSI as distinct
  method identities even when their evidence overlaps or shares evidence units.
- An EMA/EWA request cannot produce a card whose candidate identity is SMA or whose signal logic is sourced from
  Bollinger Bands unless the cited claim span genuinely supports both methods.
- A shared evidence unit can support fields on more than one method card through distinct claim spans; co-residence with
  another method is never, by itself, a blocker.
- Multi-unit method descriptions pass when formula, input, signal, and limitation evidence must be synthesized across
  neighboring claim spans and evidence units.
- Validation rejects a field only when its cited spans fail to entail the field for the selected method, not merely
  because the surrounding unit contains competing concepts.
- Method-card draft creation rejects caller-provided `method_id`, `title`, or `family` overrides unless the candidate
  identity and alias evidence support the override.
- 33V is rerun only after these gates exist, using stable method-card set lineage and target-bound evidence diagnostics.

#### 33AB Canonical Semantic-Extraction Document Plan

Create `docs/research_agents/semantic_extraction.md` as the single conceptual specification for the enriched semantic
extraction subsystem. Keep it bounded to methodology evidence interpretation: it must not duplicate the MCP catalog,
request/response schemas, operator setup, general agent ownership, strategy generation, or backtest design already owned
by other canonical documents.

The document should contain:

1. Purpose, scope, non-goals, and invariants, including non-exclusive chunks, nullable unsupported fields, no maintained
   method-target registry, no invented evidence, and no persisted hidden reasoning.
2. The evidence hierarchy from source and evidence unit through addressable claim span, discovered method identity,
   role evidence, synthesized field claim, validation result, and canonical method-card revision.
3. The semantic execution graph: high-recall retrieval, identity discovery, role-guided evidence assembly,
   target-conditioned span selection, multi-span synthesis, field-level citation, semantic validation, readiness gates,
   draft materialization, and explicit publication.
4. Tool responsibilities and artifact handoffs for the existing MCP chain, including which stages read or mutate the
   knowledge and research artifact stores and where fail-closed behavior applies.
5. Claim-span provenance requirements: source/evidence-unit IDs, stable locators or offsets, hashes, selected text,
   evidence role, target binding, concise supported claim, extraction mechanism/version, and synthesis lineage.
6. Validation semantics for identity binding, field-to-span entailment, cross-method reuse, contradiction, stale
   evidence, quotation limits, source suitability, missing evidence, and readiness without treating concept overlap as
   contamination.
7. One worked target-agnostic example where a shared multi-concept unit supports separate method claims and one field is
   synthesized from multiple units, followed by an explicit failure example for incorrect attribution.
8. Determinism and bounded semantic-enrichment policy: deterministic orchestration and validation around any bounded
   model adapter, closed output schemas, versioned prompts/models, reproducible inputs, and no uncited generated fields.
9. Observability and test strategy, including Postgres lineage, real-source fixtures, overlapping-context cases,
   adversarial attribution cases, timeout/retry behavior, and acceptance evidence.

Acceptance requires links from `docs/research_agents/README.md`, `architecture.md`, `workflows.md`, and the relevant
contract appendix; terminology must match the implemented artifacts; and docs tests must fail when the canonical link or
required invariants disappear.

### Slice 11D: Canonical Implementation-To-Evidence Decoupling

Implement tasks 56A-56C first, then land 56D and 57A-57C as one cutover. This slice replaces the candidate-centric
execution boundary; it does not add a parallel route. Immutable strategy and risk implementations written by a human,
produced by an external AI workflow, supplied by maintained code, or generated from Quant Methods evidence all enter
the same registration and validation services. Knowledge extraction, method cards, method packages, template identity,
and generator metadata are optional provenance and are never required for technical backtest eligibility.

The cutover order is:

1. Define the knowledge-independent implementation-version domain and Postgres storage.
2. Register and validate independently authored strategy and risk implementations.
3. Route maintained and method-generated producers through the same registration boundary.
4. Add strategy/risk specifications over validated implementation versions.
5. Add immutable backtest specifications over strategy/risk and Data Agent refs.
6. Switch execution, retrieval, comparison, and Evaluation to specification/run refs stored in Postgres.
7. Remove candidate-based MCP contracts, readers, artifact types, filesystem authorities, and obsolete development rows.

There is no compatibility interval in which canonical consumers accept both candidate refs and implementation/spec refs.
The branch may build the replacement incrementally, but the merged cutover must expose one contract.

Evidence target:

```text
supplied strategy implementation source with no methodology refs
  -> immutable implementation version and source hash
  -> interface, dependency, fixture, and safety validation
  -> immutable strategy specification
  -> validated backtest specification
  -> Data Agent dataset and quality refs
  -> DB-backed baseline backtest
  -> Evaluation report
```

Additional mandatory evidence targets are:

```text
independently supplied strategy + independently supplied risk manager
  -> separate implementation versions and validations
  -> strategy specification + ordered risk-stack specification
  -> validated backtest specification
  -> DB-backed risk-scoped portfolio run and Evaluation report
```

```text
approved method card or maintained template
  -> optional generated implementation producer
  -> normal implementation registration and validation
  -> the identical strategy/backtest specification path
```

This becomes the foundation for model-version lineage and robustness variants. AI-produced source is never executed
from prompt text and receives no weaker trust treatment than handwritten source. A later method-card status change may
be reported as provenance state but cannot mutate an immutable implementation, specification, or completed run.

### Slice 11E: Provider-Neutral Optimisation And Independent Audit

Tasks 57D-57H build on Slice 11D without changing its implementation, specification, or backtest contracts. Trader
Postgres is the only product authority. Built-in grid/random and optional Optuna engines propose parameters through the
same protocol; tracking systems receive only explicit derived projections; Evaluation judges sealed holdout results;
and Adversarial independently plans and judges attacks that the Supervisor executes as immutable variants.

Evidence target:

```text
validated implementation and selection-region backtest specification
  -> validated closed-input objective
  -> provider-neutral optimisation plan with sealed chronological holdout
  -> deterministic grid/random or optional Optuna trial ledger
  -> exploratory selected child specification
  -> untouched holdout backtest
  -> Evaluation holdout report
  -> Adversarial attack plan
  -> Supervisor-executed immutable variants
  -> Adversarial robustness report
  -> optional idempotent non-authoritative tracking projection
```

Optuna and MLflow may both be absent without affecting built-in execution, MCP startup, or canonical result reads.
Optuna may use only its dedicated schema/role for sampler resumability, and MLflow remains authoritative only for the
ML training/model-registry responsibilities introduced by task 39.

### Slice 11F: Controlled 56/57 Verification And Acceptance

Tasks 57I-57S qualify Slice 11D/11E before further architecture is built on it. Verification is a phased procedure over
one frozen Git revision, not an informal collection of commands. Each phase records its inputs and evidence. A code,
fixture, schema, dependency-lock, or policy change invalidates that phase and every downstream phase that consumed it.

#### 57I Frozen Surface Inventory

The replacement checkpoint revision is identified by the annotated Git tag `verification-57i-freeze-v2` on branch
`experiment/agentic-build`. The tag is created only after the inventory, matrix, documentation regression, and
checkpoint commit are complete. Later verification records use the commit resolved by that tag, not a moving branch
name. The pre-cutover parent is `40ade24` (`Complete semantic extraction and research roadmap`).

Every changed or untracked path at the freeze belongs to one of these declared surfaces:

| Surface | Paths and disposition |
|---|---|
| Implementation registry | `src/trader_research/implementations/`, generic implementation artifacts/domain ownership, registration/validation MCP adapters; canonical new execution intake |
| Specifications and execution | `src/trader_research/specifications/`, `src/trader_research/backtests/execution.py`, backtest result lookup/comparison, MCP adapters; canonical replacement for candidate requests and filesystem bundles |
| Optimisation, tracking, and independent review | `src/trader_research/optimization/`, `tracking/`, `evaluation/optimization.py`, `adversarial/`, and corresponding MCP adapters; provider-neutral new surface |
| Structured persistence | `artifact_store.py`, `postgres_artifact_store.py`, research domain/contracts; canonical JSONB and typed projections |
| Ownership, configuration, and documentation | agent identities, MCP constants/environment/server, README, active research-agent docs, tracker, dependency extras/lock |
| Verification tests | new optimisation, MCP graph, gate, Postgres projection, package/SQL/domain/docs tests and the destructive-test database suffix guard |
| Retired candidate test surface | Deleted candidate, candidate-validation, candidate-stack, candidate-backtest, portfolio-sidecar, and old performance-report tests; replaced by canonical implementation/specification/optimisation tests, not retained as compatibility tests |
| Knowledge recovery hardening | Batched embedding, extractor/index normalization, and their tests; retained because they were required to restore the operator knowledge corpus after the Postgres test-isolation incident |

No `local.env`, credentials, operator database contents, generated research artifacts, or unrelated application changes
are part of the checkpoint.

The complete 56/57 MCP surface under test is:

| Owner / side effect | Tools |
|---|---|
| Quantitative Methods / `local_mutating` | `research_register_optimization_objective`, `research_validate_optimization_objective` |
| Supervisor implementation intake / `local_mutating` | `research_register_strategy_implementation`, `research_validate_strategy_implementation`, `research_register_risk_manager_implementation`, `research_validate_risk_manager_implementation` |
| Supervisor specification / `local_mutating` | `research_create_strategy_specification`, `research_validate_strategy_specification`, `research_create_risk_stack_specification`, `research_validate_risk_stack_specification`, `research_create_backtest_specification`, `research_validate_backtest_specification` |
| Supervisor execution / `local_mutating` | `research_run_backtest_specification`, `research_compare_backtest_results`, `research_create_parameter_optimization_plan`, `research_run_parameter_optimization`, `research_run_parameter_optimization_variants` |
| Supervisor reads / `read_only` | `research_get_backtest_results`, `research_get_optimizer_runtime`, `research_get_parameter_optimization_results` |
| Supervisor projection / `external_research_mutating` | `research_project_experiment_tracking` |
| Evaluation / `local_mutating` | `evaluation_generate_parameter_optimization_report` |
| Adversarial / `local_mutating` | `adversarial_create_parameter_optimization_audit_plan`, `adversarial_generate_parameter_optimization_audit` |

Maintained strategy/risk template listing remains a read-only producer helper and is not a canonical execution identity.
The artifact/projection inventory is closed for this slice:

| Owner | Canonical artifact types | Typed Postgres projections |
|---|---|---|
| Supervisor or kind-specific Quant Methods implementation owner | `implementation_version`, `implementation_validation_report` | `research_implementation_versions`, `research_implementation_validations` |
| Supervisor | `strategy_specification`, `strategy_specification_validation_report` | `research_strategy_specifications`, `research_strategy_specification_validations` |
| Supervisor | `risk_stack_specification`, `risk_stack_specification_validation_report` | `research_risk_stack_specifications`, `research_risk_stack_specification_validations` |
| Supervisor | `backtest_specification`, `backtest_specification_validation_report`, `backtest_run` | `research_backtest_specifications`, `research_backtest_specification_validations`, `research_backtest_runs` |
| Supervisor | `parameter_optimization_plan`, `parameter_optimization_run`, `parameter_optimization_trial` | `research_parameter_optimization_plans`, `research_parameter_optimization_runs`, `research_parameter_optimization_trials` |
| Supervisor | `experiment_tracking_projection_report` | `research_experiment_tracking_projections` |
| Evaluation | `parameter_optimization_evaluation_report` | `research_parameter_optimization_evaluations` |
| Adversarial | `parameter_optimization_audit_plan`, `parameter_optimization_robustness_report` | `research_parameter_optimization_audit_plans`, `research_parameter_optimization_robustness_reports` |

All rows also exist in canonical `research_artifacts`; a typed projection is inspectable metadata, not a second
authority. The provider protocols are `OptimizationEngine`, `OptimizationTrialExecutor`, and
`ExperimentTrackingSink`. Built-in profiles are `builtin_grid` and `builtin_random`; optional profiles are
`optuna_tpe` and the configured MLflow backtest-optimisation projection sink.

The independent policy gates under test are:

| Gate | Required relationship |
|---|---|
| `TRADER_MCP_ALLOW_BACKTESTS` | Required for canonical backtest execution and any optimisation trial execution |
| `TRADER_MCP_ALLOW_OPTIMIZATION` | Additionally required for optimisation and variant execution |
| `TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES` | Master gate for any optional external provider mutation |
| `TRADER_MCP_ALLOW_OPTUNA_WRITES` | Additionally required only for Optuna sampler-state writes |
| `TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES` | Additionally required only for tracking projections |
| `TRADER_MCP_ALLOW_BROKER_MUTATION`, `TRADER_MCP_ALLOW_RAW_SQL` | Remain false and have no registered 56/57 tools |

Retired canonical inputs are strategy/risk candidates and validations, strategy/risk stack manifests and validations,
`backtest_run_ref`, `portfolio_backtest_run_ref`, and candidate-era Evaluation sidecars. Retired MCP names include
`research_create_strategy_candidate`, `research_validate_strategy_candidate`,
`research_create_risk_manager_candidate`, `research_validate_risk_manager_candidate`,
`research_create_strategy_risk_stack`, `research_validate_strategy_risk_stack`, `research_run_backtest`,
`research_run_portfolio_backtest`, and `evaluation_generate_performance_report`. Retired projection tables are
`research_strategy_candidates`, `research_strategy_validations`, `research_risk_manager_candidates`,
`research_risk_manager_validations`, `research_strategy_risk_stacks`, `research_stack_validations`,
`research_backtest_sidecars`, and `research_evaluation_reports`. Core runtime `experiments`/`experiment_runs` tables may
still support unrelated operator workflows, but no 56/57 research service may use them as canonical study state.

#### 57I Acceptance Matrix

Profile codes are **C** core, **P** Trader Postgres, **O** Optuna, and **T** tracking sink. `Existing` means a named test
is present at the freeze; it does not pre-judge the controlled run. `Partial` identifies evidence that must be expanded
by the named downstream task. `Planned` means no acceptance-grade test exists yet.

| Invariant | Profile | Acceptance assertion | Named evidence at freeze | Status / completing task |
|---|---|---|---|---|
| 36 | C | Canonical experiment packages do not import knowledge/candidate domains; package direction remains one-way. | `test_canonical_experiment_packages_do_not_import_knowledge_or_candidate_domains`, `test_trader_package_does_not_depend_on_research_agent_packages` | Passed / 57K |
| 37 | C,P | Handwritten, AI, maintained, and method-generated origins enter one immutable implementation contract with equal eligibility. | `test_mcp_optimization_holdout_and_adversarial_evidence_graph` proves handwritten intake only. | Partial / 57M adds origin-equivalence cases |
| 38 | C | Candidate IDs/cards/packages are rejected as canonical strategy/risk/backtest inputs. | `test_mcp_exposes_decoupled_tools_and_independent_write_gates`, canonical package-boundary test | Existing / 57K rerun and 57M fail-closed calls |
| 39 | C,P | Candidate MCP schemas, aliases, compatibility readers, and dual writes are absent. | MCP registration and retired-table assertions passed, but candidate-era domain models, direct services/readers, and current docs remain. | Blocked / 57K |
| 40 | P | Retired development projections are absent and no legacy rows are translated. | `test_research_schema_has_canonical_optimization_tables_without_retired_projections` | Existing schema evidence / 57J clean DB and 57R inspection |
| 41 | P | Backtests, comparisons, sidecars, and Evaluation are complete Postgres artifacts with no durable filesystem authority. | In-memory MCP graph plus `test_optimization_artifacts_have_typed_pgadmin_visible_projections` | Partial / 57M canonical graph and 57R reconciliation |
| 42 | C,P | Methodology provenance status cannot mutate completed implementations/specifications/runs. | Content-addressed loaders exist; no direct immutable-lineage attack test. | Partial / 57N |
| 43 | C | Core imports provider-neutral contracts; MCP/grid/random work with Optuna and MLflow unavailable. | Package-boundary test and built-in engine unit tests; optional packages are installed in the current environment. | Partial / 57P minimal-environment profile |
| 44 | C,P | Runs pin engine identity/version/configuration/capabilities/seed/executor and never switch engines. | `test_grid_resume_selection_projection_evaluation_and_audit_are_separate`, `test_seeded_random_retry_evidence_and_base_snapshot_drift_are_deterministic` | Existing / 57N and 57O restart expansion |
| 45 | C | Objectives are content-addressed, closed-input, finite scalar implementations with no ambient capabilities. | `test_closed_observation_and_plan_reject_undeclared_inputs`, `test_objective_validation_rejects_filesystem_and_indirect_builtin_access` | Existing / 57Q attack expansion |
| 46 | C,P | Plans seal selection/holdout/quality/objective/search/constraint/seed/budget/resource inputs. | Closed-plan unit test and MCP smoke graph | Partial / 57M real scopes and 57N tamper matrix |
| 47 | C,P | Every suggestion, attempt, failure, child ref, observation, score, and tie-break is canonical evidence. | Grid/resume and seeded-random/retry unit tests | Partial / 57M Postgres ledger and 57O failures |
| 48 | O,P | Optuna uses only isolated sampler state; loss/mismatch cannot replace Trader evidence. | `test_optuna_adapter_requires_isolated_postgres_and_reconciles_canonical_trials` | Partial / 57P live adapter profile |
| 49 | C,T | Tracking projection is explicit/idempotent/derived/non-authoritative; MLflow deletion cannot affect Trader reads. | Recording/failing sink cases in `test_grid_resume_selection_projection_evaluation_and_audit_are_separate` | Partial / 57P real sink deletion/unavailability profile |
| 50 | C,P | Holdout Evaluation and Adversarial audit are separately owned and cannot rewrite selection. | Direct grid test and `test_mcp_optimization_holdout_and_adversarial_evidence_graph` | Existing smoke evidence / 57M and 57N immutable-selection proof |
| 51 | C,O,T | Backtest, optimisation, external, Optuna, and tracking gates are independent and reported by config. | All three tests in `test_mcp_optimization_tools.py` | Existing / 57Q full gate matrix |
| 52 | C,P | Canonical loaders recompute identities and fail closed on source/config/snapshot/lineage drift. | Seeded-random/base-snapshot drift test and content-addressed service loaders | Partial / 57N full tamper matrix |
| 53 | C | Evidence is tied to one frozen revision and downstream phases rerun after changes. | This inventory/matrix, checkpoint commit, annotated `verification-57i-freeze-v2` tag | Pending replacement 57I freeze and rerun |
| 54 | P | Tests require explicit `*_test` DB and leave operator runtime/research/knowledge unchanged. | Server/marker/role/locale checks before store construction and every truncate; `verification_control.operator_fingerprints`; 57J before/after digest match. | Existing / 57J complete |
| 55 | P | Mandatory graph is multi-asset and produces parameter-sensitive trades, costs, exposure, approvals, and rejections. | Current graph is one-symbol, twelve-bar, empty-strategy smoke coverage. | Planned / 57L fixture and 57M graph |
| 56 | P | Selection and holdout are disjoint by time/hash and holdout is unread before selection. | Current smoke graph separates times but has no access instrumentation. | Planned / 57N |
| 57 | C,P | Two clean runs reproduce IDs/order/observations/scores/tie-break/selection/reports. | Component-level deterministic tests only. | Planned / 57N |
| 58 | P,O | Process restart/faults preserve partial evidence, avoid duplicates, and reject changed-config resume. | Same-process partial resume and Optuna count mismatch unit cases only. | Planned / 57O |
| 59 | C,O,T | Built-ins/startup/reads survive missing optional packages; each adapter is separately qualified. | Lazy runtime profile and unit adapters exist; no package-absent execution profile. | Planned / 57P |
| 60 | P | Every acceptance artifact reconciles between canonical JSONB and its typed projection. | Schema test and plan/run/trial projection integration test only. | Partial / 57M graph and 57R full reconciliation |
| 61 | C,P,O,T | Final record separates pass/fail/not-run/not-qualified and never promotes disposable evidence. | Acceptance record contract only. | Planned / 57S |

#### 57J Isolated Runtime Contract

Verification commits after `verification-57i-freeze-v2` may change only tests, active docs, and the tracker. The controlled
runtime records both the frozen product SHA and current harness SHA; any change under `src/`, `pyproject.toml`, `uv.lock`,
or `env.template` blocks execution and requires a new 57I freeze.

Destructive tests use only `PG_TEST_HOST`, `PG_TEST_PORT`, `PG_TEST_DB`, `PG_TEST_USER`, and `PG_TEST_PASSWORD`. They do
not read `PG_HOST`, `PG_USER`, or other operator variables. `PG_TEST_DB` must end `_test` or `_testing`, differ from
`PG_OPERATOR_DB`, be owned by a distinct non-superuser role, report the expected database/role from the server, use UTC,
pin UTF-8 `LC_COLLATE`/`LC_CTYPE` from explicit `PG_TEST_LOCALE`, and contain a
`verification_control.runtime_marker` row pinned to the frozen SHA. The guard runs before any store constructor and
again immediately before every `TRUNCATE`.

The test database contains a separate `verification_control` schema with the marker, credential-free runtime manifests,
phase status, and before/after operator fingerprints. Fingerprints are computed through an explicit read-only,
repeatable-read operator connection over runtime row hashes, knowledge source/chunk/embedding identities and content
hashes, and canonical/projection research rows. Raw source text, vectors, payloads, and credentials are never stored in
verification evidence. A mismatch records a blocked phase and stops execution.

Optuna receives a separate non-superuser role and non-`public` schema in the verification database. The MLflow profile
receives only a disposable experiment name at this stage. All broker, SQL, data-loading, backtest, optimisation,
external-write, Optuna-write, and tracking-write gates remain false during 57J. Provider mutation remains deferred to
57P.

The test-only command surface is:

```bash
uv run python -m tests.support.postgres_verification provision --reset
uv run python -m tests.support.postgres_verification begin --phase 57J
TRADER_VERIFICATION_MODE=true uv run pytest tests/test_postgres_verification_runtime.py -m postgres -q
uv run python -m tests.support.postgres_verification end --phase 57J --outcome passed
```

#### Superseded 57J Execution Evidence

- Executed 2026-07-18 14:28:30-14:28:33 UTC against frozen product revision
  `09b0b5ebf538d80de935bde52bebf77a099d2449` (`verification-57i-freeze`) and harness revision
  `fd4b3848443fa8ee38860fbdd7b7a10fc713bc67`. Product paths were byte-identical to the freeze and the worktree was
  clean.
- Provisioned `trader_verification_test` on Postgres 16.11 with UTC, UTF-8, `LC_COLLATE=en_US.utf8`, and
  `LC_CTYPE=en_US.utf8`. `trader_verification_runner` and `trader_verification_optuna_writer` were distinct
  non-superuser roles without create-database or create-role authority.
- `trader_verification_optuna_writer` owns only the isolated `trader_optuna_verification` provider schema in the test
  database. The disposable tracking namespace was `trader-verification-09b0b5e`; no Optuna or tracking write was
  attempted.
- The credential-free configuration digest was
  `2c0d93f78b1c643ffa7487d0e9f9076955b4b3cfeed4b5485bc7b89be1ffe56a`; all eight mutation gates in the runtime
  manifest were false.
- `uv run pytest tests/test_postgres_verification_runtime.py -m postgres -q` passed all 4 tests. The suite verified the
  server marker and manifest, role separation/operator-table DML denial, Optuna schema ownership, and a destructive
  fixture round trip confined to the verification database.
- The read-only operator fingerprint was
  `73c3e970eca95f589c71ac477a2e1f3db9b48ede0c0b3c16c2ee161add498190` before and after. Its count evidence remained
  16 knowledge sources, 43,039 chunks, 43,039 embeddings, 16 embedding indexes, 17 ingestion runs, 1 method-card set,
  0 method cards, 9 method contracts, 0 canonical research artifacts, and 0 runtime rows. Only hashes and counts were
  stored in `verification_control`; source text, vectors, payloads, and credentials were not copied.
- One third-party `websockets.legacy` deprecation warning was observed. It does not affect the isolation result and is
  carried into 57K's warnings review rather than being silently discarded.

#### Initial 57K Execution Evidence And Blockers

- Executed the fingerprinted phase from 2026-07-18 14:46:58-14:48:20 UTC against product freeze
  `09b0b5ebf538d80de935bde52bebf77a099d2449` and harness revision
  `697452f957d28aff62682078377ed1b4c1db4535`. The credential-free configuration digest was
  `f7b485ec5afa2f53556ac25df33f6b0c923f909c0bd355a10ad530ad302ea2a8`.
- `uv run ruff check src tests`, compileall over all five source packages, `uv run mypy`, and `git diff --check` passed.
  Mypy checked its configured 22-source-file surface with no issues.
- `uv run pytest -o addopts='' -m 'not postgres' -q -ra` passed 691 tests with 18 intentionally deselected Postgres
  tests, zero skips, and 12 warnings in 64.55 seconds. A separate collection audit confirmed that all 18 deselections
  were tests explicitly marked `postgres`; the complete collection contained 709 tests.
- The focused MCP registration, MCP optimisation, evidence-graph, docs, research-domain, agent-identity,
  package-boundary, and SQL-boundary command passed 60 tests with one warning in 9.12 seconds. Public MCP assertions
  confirmed that retired candidate/backtest/Evaluation tool names are not registered, and the schema assertion
  confirmed that retired research projection tables are not recreated.
- The read-only operator fingerprint remained
  `73c3e970eca95f589c71ac477a2e1f3db9b48ede0c0b3c16c2ee161add498190` before and after. The control-schema
  `isolation_status=passed` means the command phase did not mutate operator state; it does not override the blocked
  release-gate verdict below.

57K is blocked by two independent defect groups:

1. **The candidate-era retirement is incomplete.** `src/trader_research/domain.py` still defines the retired candidate,
   candidate-validation, strategy/risk-stack, `backtest_run_ref`, and `portfolio_backtest_run_ref` constants and models.
   Old creation/validation/read paths remain in `strategy_candidates/services.py`,
   `strategy_candidates/validation.py`, `risk_managers/services.py`, `risk_managers/validation.py`,
   `portfolio_stacks/services.py`, `backtests/services.py`, and `evaluation/performance.py`; `portfolio_stacks/__init__.py`
   still exports the retired stack services. Active `tool_contracts.md` and `mcp_tools.md` still describe retired request
   forms. Candidate-named test files were deleted, but `test_research_domain.py` still positively tests retired schemas,
   and the current boundary test checks only that new canonical packages do not import them. This contradicts 56D and
   the 57I retired-surface inventory even though MCP registration and Postgres projection cutover tests pass.
2. **Warnings-as-errors does not collect the suite.** Unfiltered `pytest --collect-only -W error` exits 4 while importing
   Alpaca because `websockets.legacy` is deprecated. Allowing only that third-party warning reaches a second collection
   failure at `src/trader/web/api.py:145`, where `FastAPI.on_event` is deprecated. The normal regression run also emits
   a direct Pydantic V2 warning at `src/trader/web/api.py:178` for `request.dict()`. The product API must use a lifespan
   handler and `model_dump()`; the dependency/import warning must be upgraded, isolated, or narrowly justified before
   strict warning qualification can pass.

Required remediation is a product change and therefore invalidates the current freeze. Remove the retired code,
models, readers, active documentation, and positive compatibility tests; add explicit absence/boundary regressions;
resolve the warning failures; then create a new 57I freeze, reprovision/re-run 57J, and rerun all of 57K. Do not start
57L from the current revision.

#### 57K-R Candidate Retirement And Warning Remediation

This phase replaces the failed candidate-era cutover with a hard deletion. It removes candidate, candidate-validation,
stack, filesystem backtest-bundle, and legacy performance-report services and domain models. The only retained template
surface is the neutral read-only maintained implementation catalog under `trader_research.implementations`; catalog
rows point to real `trader_standard` entrypoints and carry no method-card, candidate, source-generator, or filesystem
requirements.

The verification control schema is also replaced rather than migrated. `phase_runs` records environmental isolation
and qualification outcome independently through `isolation_status`, `qualification_status`, explicit blockers,
`executed_harness_revision`, and `verdict_revision`. FastAPI startup uses lifespan, Pydantic requests use `model_dump`,
and Alpaca live websocket imports are lazy with an exact adapter-scoped suppression for the upstream deprecation.
Completion requires a clean `verification-57i-freeze-v2`, a reset disposable verification database, and fresh passing
57J and 57K evidence.

Execution profiles are independent:

| Profile | Required evidence | Release effect |
|---|---|---|
| Core | Static/type/contract/non-Postgres regression, realistic deterministic fixture, grid/random behavior, security boundaries | Mandatory |
| Trader Postgres | Real MCP graph, canonical/projection reconciliation, restart/resume, operator isolation, bounded scale | Mandatory |
| Optuna | Optional-package conformance plus dedicated-schema integration, loss/reconciliation/resume behavior | Required only before `optuna_tpe` is enabled |
| Tracking sink | Explicit projection, idempotence, input closure, external deletion/unavailability, canonical-read independence | Required separately for each configured sink before writes are enabled |

The phase dependency graph is:

```text
57I frozen revision and matrix
  -> 57J isolated runtime
  -> 57K static/regression gate
  -> 57L realistic fixture
  -> 57M Postgres MCP evidence graph
  -> 57N determinism/integrity/leakage
  -> 57O restart/resume/fault injection
       -> 57P optional-provider profiles
       -> 57Q policy/security/resource boundaries
  -> 57R projections/operator/scale
  -> 57S acceptance record
```

The mandatory evidence graph is deliberately more demanding than
`tests/test_mcp_optimization_evidence_graph.py`, which remains a fast transport/orchestration smoke test. Acceptance
uses `PostgresResearchArtifactStore`, a multi-asset fixture, order-producing strategy code, observable risk approvals
and rejections, nonzero costs/exposure, materially different trial outcomes, disjoint selection and holdout content,
and public MCP calls throughout:

```text
handwritten strategy and risk implementation versions
  -> passed implementation validations
  -> passed strategy/risk/backtest specifications over selection data
  -> real selection backtest evidence
  -> validated closed-input objective
  -> provider-neutral optimisation plan with sealed holdout
  -> complete built-in-grid trial ledger and immutable selected specification
  -> untouched holdout backtest
  -> Evaluation report
  -> Adversarial audit plan
  -> Supervisor-executed immutable variants
  -> Adversarial report
```

Mandatory graph assertions:

1. Every durable identity is a `research://postgres/{artifact_type}/{artifact_id}` ref and has canonical JSONB plus a
   matching typed projection; no canonical filesystem path is returned or stored.
2. The strategy executes buys and sells, final/intermediate exposure is nonzero, transaction costs are observable, and
   the risk stack records at least one approval and one rejection.
3. The optimisation ledger contains every suggestion, attempt, exception, child ref, observation, objective result,
   and tie-break diagnostic. Parameter changes produce materially different evidence rather than constant no-trade
   scores.
4. Selection and holdout manifests/content hashes differ and their time ranges do not overlap. Instrumented reads show
   no holdout access before the selected specification is immutable.
5. Two clean executions produce the same content-addressed IDs, trial order, selected trial, and reports. Evaluation,
   Adversarial, tracking, and provider reconciliation cannot rewrite the selection.
6. The operator database and knowledge corpus have identical before/after fingerprints. Destructive cleanup is confined
   to the explicit verification database and optional-provider namespace.

Suggested command order for the frozen revision is:

```bash
git status --short
git diff --check
uv run ruff check src tests
python -m compileall -q src/trader_research src/trader_mcp src/trader_agents src/trader_standard src/trader
uv run mypy
uv run pytest -m 'not postgres' -q
PG_TEST_DB=trader_verification_test uv run pytest -m postgres -q
PG_TEST_DB=trader_verification_test uv run pytest tests/test_postgres_optimization_evidence_graph.py -q
```

The last command is planned by 57M and does not exist until that task is implemented. Provider-profile commands must
name their isolated schema/namespace explicitly and run only after the core/Postgres graph passes. The acceptance record
must distinguish a test that passed, an optional integration that was not run, and an integration that failed; these are
not interchangeable outcomes.

### Slice 12: Minimal Supervisor Toolchain Handoff

Keep chunk 34 deferred until Slice 11D, model versioning, and robustness reports provide the direct artifacts the
supervisor must consume. The supervisor must not become the mechanism that compensates for missing implementation,
backtest-specification, ML-lineage, or robustness tools.

### Slice 13: Agent Graphs and Supervisor LLM Control

Implement chunks 35-36 after the meaningful toolchain exists. The Quantitative Methods graph and supervisor LLM policy
then orchestrate useful MCP tools rather than driving the architecture ahead of working services.

### Slice 14: ML Model Versioning

Implement tasks 39A-39J after Slice 11D. The sequence is MLflow configuration and side-effect policy; point-in-time
feature sets and training datasets; registered training pipelines and gated fitting; MLflow run reconciliation;
time-series evaluation; immutable registry versions and explicit alias promotion; runtime prediction contracts;
model-backed strategy/deployment integration; and prediction/drift monitoring. Task 40 adds the ML Agent graph only
after this deterministic chain is proven. Hypothesis tasks 37-38 are not on the current critical path.

Evidence target:

```text
Data Agent dataset and quality refs
  -> point-in-time feature set and training dataset
  -> chronological split plan and leakage report
  -> validated training pipeline and bounded training spec
  -> MLflow experiment run and logged model
  -> reconciled run and time-series model evaluation
  -> immutable registered-model version
  -> version-pinned deployment manifest
  -> model-backed strategy backtest
  -> prediction and drift evidence
```

### Slice 15: Attribution, Critique, Robustness, and Recommendations

Implement tasks 44 and 46 after Slice 11D, then deepen attribution and Evaluation through 41-42. Adversarial graph,
recommendation, and supervisor synthesis tasks remain deferred until direct robustness artifacts are proven. Every
variant must preserve baseline implementation, data, specification, and changed-assumption lineage.

### Slice 15A: Walk-Forward Optimisation And Independent Audit

Implement tasks 58-59 only after reproducible external-strategy backtest specifications, ML model-backed strategy
integration through 39I, and robustness primitives 44/46 are proven. Chronological walk-forward validation remains part
of the earlier ML foundation; this slice adds repeated optimisation, locked out-of-sample execution, and independent
critique of the selection procedure.

Evidence target:

```text
immutable implementation or model-backed deployment
  -> base reproducible backtest specification
  -> declared folds, search space, objective, costs, and compute budget
  -> per-fold in-sample fitting/selection
  -> locked parameters or immutable model version
  -> untouched out-of-sample child backtest
  -> stitched out-of-sample Evaluation report
  -> independent Adversarial walk-forward audit
```

The optimisation engine is Supervisor-owned procedural evidence. It does not judge its own robustness. Evaluation owns
out-of-sample interpretation, while Adversarial owns attacks on fold boundaries, parameter/model stability, costs,
concentration, and selection bias. No stage grants paper/live promotion or mutates an active deployment.

### Slice 16: Orchestration and Acceleration

Implement chunks 49-50 later. The experiment runner composes proven tools; compiled-kernel conformance and runtime
acceleration are performance optimizations to revisit after profiling shows value.

### Ongoing Validation

Implement chunks 51-54 alongside the slices. Import-boundary tests, MCP/toolchain/LangGraph contract tests, docs, and
verification should be updated at every evidence checkpoint rather than saved for the end.

## First Release Acceptance Criteria

1. The MCP server exposes data inventory, data quality, bounded data-loading, source-backed method, rich methodology,
   method-package, implementation registration/validation, strategy/risk specification, backtest specification/run,
   result-lookup, comparison, and performance-report tools through shared envelopes.
2. The Data Agent workflow can be exercised against sample or existing data: health -> discovery -> inventory -> quality -> ensure/load -> quality.
3. Quant Methods Knowledge Base ingestion produces source, evidence-unit, embedding, lexical-index, vector-index, ingestion, retrieval, evidence-packet, method-card, and citation-validation artifacts before method contracts depend on retrieved evidence; coarse legacy chunks are not sufficient for methodology extraction after 33X.
4. Ingestion does not imply approval: draft method cards are not executable, shallow cards are legacy/projection records, and sophisticated methods require approved canonical method-card references plus passing citation/readiness validation.
5. Methodology candidates can be discovered from ingested sources without hardcoded known targets, and can populate nullable method fields only when each populated field has target-bound source/evidence-unit evidence tied to a family-level evidence role.
6. Canonical method cards can represent technical, statistical, options/derivatives, portfolio, risk, sentiment/alternative-data, and fundamental methodologies with field-level citations, validation blockers, explicit draft/approval lineage, and derived shallow summaries for compatibility.
7. Rich methodology schemas use common core fields plus nullable domain extension blocks, while family evidence profiles define role contracts and readiness requirements for technical indicators, statistical arbitrage, options/derivatives, fundamental valuation, sentiment/alternative data, portfolio construction, risk models, and execution methods.
8. Method-card or maintained-template generation may produce strategy/risk source only through the canonical
   implementation registration boundary. Readiness gates protect provenance claims but never make a method card a
   prerequisite for registering independently authored code.
9. Documentation explains the upgraded source registration, full-document ingestion, retrieval, open-world methodology discovery, evidence assembly, rich field extraction, canonical method-card approval, domain extension blocks, readiness gates, and strategy-generation flow with operator examples.
10. Validated Python indicator/signal implementations can be packaged into `method_package_manifest.json` without requiring compiled kernels.
11. Immutable strategy implementation versions contain importable source/packages implementing
   `trader.strategies.Strategy`, pass source/interface/fixture/safety validation, and require no methodology refs.
12. Strategy specifications pin one validated implementation version and explicit parameters without baking symbols,
   timeframe, source, or date windows into code or configuration; the Data Agent manifest remains scope authority.
13. Immutable risk-manager implementation versions implement `trader.risk.RiskManager`, pass independent validation,
   and require no method-card, method-package, or maintained-template provenance.
14. Risk-stack specifications compose ordered validated risk implementation versions with explicit parameters and
   thresholds while preserving source hashes, validation refs, and no-live-trading constraints.
15. Validated backtest specifications bind strategy/risk specifications, Data Agent and quality refs, initial state,
   costs, assumptions, seeds, and runtime policy before execution. Baseline and risk-scoped runs persist results,
   curves, trades, positions, symbol metrics, exposure, risk decisions/breaches, and provenance canonically in Postgres.
16. Performance reports include practical metrics, assumptions, warnings, blockers, caveats, multi-asset attribution summaries where available, exposure/concentration evidence, and risk-manager evidence linked to the backtest and data-quality artifacts.
17. One end-to-end MCP test proves: handwritten strategy with no methodology refs -> implementation registration ->
   validation -> strategy/backtest specifications -> DB-backed baseline run -> performance report.
18. A second end-to-end MCP test proves: independently supplied strategy and risk manager -> separate implementation
   versions/validations -> strategy and ordered risk-stack specifications -> DB-backed risk-scoped run -> Evaluation.
19. A rich-methodology MCP test proves: full-document ingestion -> rich card -> optional generated implementation ->
   normal implementation registration/validation -> the identical specification/run path used by handwritten code.
20. The Quant Research Supervisor consumes implementation, strategy/risk specification, backtest specification/run,
   and performance-report refs without requiring or forging specialist methodology artifacts.
21. LangGraph agent identities and supervisor LLM control are follow-on orchestration layers over the deterministic toolchain, not prerequisites for the first meaningful suite.
22. Every tool returns the shared JSON envelope and declares its side-effect class.
23. Every tool declares the owning agent and returns/links the artifact owned by that agent.
24. Missing/incomplete data fails closed or produces Data Agent warnings and downstream Evaluation blockers.
25. `src/trader/` contains no research experiment, agent-tool, MCP schema/definition, or LangGraph agent modules.
26. No MCP tool or LangGraph agent can place live orders, mutate broker state, run raw SQL, bypass existing platform validation, or execute arbitrary strategy code from prompts.
27. MLflow integration uses one configured tracking/registry authority, reconciles external records into Trader
    Postgres lineage, and never accepts caller-supplied tracking URIs or persisted credentials.
28. Time-series training requires point-in-time feature/target semantics, chronological fold plans, purge/embargo where
    needed, preprocessing fit scope, dataset digests, and explicit leakage checks before fitting.
29. Every model-backed backtest, deployment, session, prediction, and drift artifact pins an immutable MLflow registered-
    model version; mutable aliases are resolved only at controlled planning/promotion boundaries.
30. The core trading runtime depends on a provider-neutral prediction contract, not MLflow. The same validated feature
    and inference adapter is used in backtests and the trading loop, which never calls MCP in the hot path.
31. One end-to-end ML MCP test proves: Data Agent refs -> feature set -> point-in-time training dataset/folds -> validated
    trainer -> MLflow run -> reconciled/evaluated model -> immutable registry version -> deployment manifest -> model-
    backed strategy backtest -> prediction/drift evidence.
32. MLflow writes, fitting, alias promotion, and runtime deployment have distinct declared side effects and default-off
    policy gates; the ML Agent graph is added only after the deterministic 39A-39J services pass this evidence chain.
33. Walk-forward validation for ML fitting remains part of 39C/39F, while full walk-forward optimisation is a later
    Supervisor-owned experiment that requires task 57, model-backed strategy integration, and robustness primitives.
34. Every walk-forward fold locks its selected parameters or immutable model version before untouched out-of-sample
    execution, records all searched candidates and child runs, and never uses out-of-sample results to revise that fold.
35. Walk-forward optimisation, stitched out-of-sample Evaluation, and Adversarial audit are separate artifacts with
    separate owners; the optimiser cannot produce its own robustness verdict or promote a strategy/model.
36. Canonical implementation, strategy/risk specification, backtest, Evaluation, ML, and robustness packages have no
    imports from knowledge or method-card domain modules; package-boundary tests enforce this dependency direction.
37. Maintained, handwritten, AI-produced, and method-generated source converge on the same immutable implementation
    schema and validation services. Producer origin changes provenance only, never execution eligibility or contracts.
38. Candidate IDs, candidate validation refs, method-package refs, and rich method cards are rejected as canonical
    strategy/risk/backtest execution inputs after the task-57 cutover.
39. Candidate-based MCP tools and request schemas are removed when specification tools register. No aliases,
    compatibility readers, dual writes, or inferred legacy implementation versions remain.
40. Obsolete development candidate/validation/stack rows are explicitly reset at cutover; canonical Postgres rows are
    never silently translated from old payloads.
41. Baseline and portfolio runs, sidecars, comparisons, and Evaluation reports use structured Postgres artifacts as
    canonical state. Durable filesystem bundle paths are neither required nor returned.
42. Retiring or superseding optional methodology provenance cannot mutate an immutable implementation version,
    specification, or completed run; downstream reports may expose provenance status as separate evidence.
43. Core optimisation imports only provider-neutral contracts; grid/random execution and MCP startup work with Optuna
    and MLflow uninstalled.
44. Every optimisation run pins engine profile/provider/algorithm version, credential-free configuration digest,
    capabilities, seed, and executor kind; one run cannot switch engines or provider authority.
45. Custom objectives are content-addressed, Quantitative Methods-owned implementations that receive only a validated
    `OptimizationObservation` and return finite scalar evidence without file, network, database, tool, or raw-event
    access.
46. Optimisation plans seal the selection specification, chronological holdout and quality snapshots, objective,
    direction, explicitly tunable dimensions, constraints, seed, budget, retries, and resource bounds before execution.
47. Every suggestion, attempt, exception, rejected/failed/passed trial, child specification/run ref, closed observation,
    objective diagnostic/value, and deterministic tie-break remains canonical Trader evidence.
48. Optuna is a lazy optional adapter using a dedicated non-`public` PostgreSQL schema and writer role only for sampler
    state; provider loss or reconciliation mismatch cannot invalidate or replace Trader evidence.
49. Experiment tracking is an explicit idempotent derived projection. MLflow is non-authoritative for backtest
    optimisation and remains authoritative only for the planned ML training/model-registry lifecycle.
50. Untouched-holdout Evaluation and Adversarial optimisation audit are separate owner artifacts, cannot rewrite the
    selected trial, and are both required before promotion readiness.
51. Backtest, generic optimisation, external research writes, Optuna writes, and tracking projections have independent
    default-off gates reported by `mcp_get_config`.
52. Canonical loaders recompute content-addressed implementation/specification/validation/plan IDs and fail closed on
    source, parameter, order, snapshot, lineage, or provider-configuration drift.
53. Acceptance evidence is generated from one frozen Git revision in an explicit isolated environment; any defect fix
    reruns its phase and all downstream phases that consumed the changed behavior.
54. Postgres verification requires an explicit database name ending `_test` or `_testing`, never falls back to the
    operator `PG_DB`, and leaves operator runtime, research, and knowledge fingerprints unchanged.
55. The mandatory MCP graph uses Postgres canonical storage and a deterministic multi-asset fixture whose strategy
    trades, incurs costs, carries exposure, responds to tuned parameters, and produces risk approvals and rejections.
56. Selection and holdout scopes are chronologically disjoint with different content hashes, and instrumented access
    proves holdout data/evidence is unavailable to trials, objectives, and selection.
57. Repeated clean executions preserve content-addressed IDs, suggestions, trial order, observations, objective values,
    deterministic tie-breaks, selected refs, and report lineage.
58. Process restart and injected failures preserve complete partial evidence, do not duplicate terminal trials, and
    never switch engines, repair provider state silently, or resume under a changed configuration identity.
59. Built-in grid/random execution, MCP startup, resume, and canonical reads pass without Optuna or MLflow installed;
    each optional adapter is independently qualified before its write gates may be enabled.
60. Typed Postgres projections reconcile to canonical JSONB for every implementation, validation, specification,
    backtest, optimisation, Evaluation, Adversarial, and tracking artifact produced by the acceptance graph.
61. The final acceptance record distinguishes mandatory pass/fail, optional profile not-run, and optional profile
    failed/not-qualified; no skipped or disposable-provider evidence is represented as canonical product success.

## Open Decisions

- MCP SDK dependency and version pin: resolved for the server skeleton as `mcp>=1.27.1,<2`.
- LangGraph dependency/version and persistence choice: choose the smallest graph/checkpoint setup that supports agent identity and state without persisting hidden reasoning.
- Persistence shape for first release: `trader.data.EventStore` may provide platform persistence primitives, but research-specific persistence adapters and artifact policies belong in `trader_research`.
- Quant Methods Knowledge Base backend: use Postgres-backed source/evidence-unit/method metadata, PostgreSQL full-text search for
  lexical retrieval, and pgvector or a backend-neutral vector adapter for dense retrieval in the first durable
  implementation. Deterministic embeddings are test doubles only; runtime ingestion requires explicit embedding-provider
  configuration. JSON artifacts remain audit/export records, while approved source registry records and approved method
  cards remain the authority.
- MLflow deployment topology: choose the initial approved tracking/registry server, database-backed metadata store,
  artifact store, authentication mechanism, namespace policy, retention/backup policy, and client/server compatibility
  range before task 39A implementation.
- Initial model flavors and trainer execution: choose a deliberately small supported set, likely beginning with
  `python_function` plus one maintained tabular framework, and define process/container isolation and resource controls
  for supplied training pipelines. Do not support arbitrary pickle execution.
- Runtime inference mode: decide whether the first paper-trading adapter loads a pinned model locally or calls an
  approved serving endpoint. The core prediction protocol and deployment manifest must support either without coupling
  `trader` to MLflow, and backtest/runtime parity remains mandatory.
- Natural-language planning: both the Data Agent and Quant Research Supervisor need real LLM-backed control. Add the Data
  Agent LLM loop first because its provider-aware tool surface is already complete and bounded. Add the Quant Research
  Supervisor LLM loop later after implementation/specification, backtest-run, and performance-report refs exist,
  because its job is to orchestrate useful artifacts rather than compensate for missing deterministic tools. Both must
  use structured output, deterministic routing validation, allowlists, and loop limits; MCP tools remain deterministic.
- Supplied strategy and risk-manager code: independently authored, AI-produced, maintained, and method-generated source
  all enter the task-56 implementation registry. Do not execute prompt text, accept unvalidated runtime code, or expose
  live risk controls. Producer origin is provenance, not a separate execution contract.
- Transport: stdio for the server skeleton; HTTP/SSE later only if another client requires it.
