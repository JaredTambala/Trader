# MCP Trading Research Tools Implementation Plan

## Overview

This plan translates `docs/research_agents/agent_operating_model.md` and `docs/research_agents/codex_trading_research_framework_brief.md` into an implementation backlog for a clean research-tool, MCP, and LangGraph agent layer. The goal is to expose deterministic, artifact-producing tools to Codex, ChatGPT, Claude, or other MCP clients while giving each research agent a distinct identity, tool allowlist, state model, and artifact contract. This must not rebuild the older over-scoped agent system or expand the core `trader` package beyond its runtime platform responsibilities.

The first useful product surface follows the Data Agent contract:

```text
Bounded data request
  -> dataset manifest
  -> data-quality report
  -> explicit load/backfill result, if permitted
  -> reproducible MCP evidence
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
  data-quality/tool wrappers, strategy-candidate validation, robustness,
  attribution, reports, and agent-owned research artifact handling.

trader_mcp
  MCP server and MCP-specific adapters over trader_research services.

trader_agents
  LangGraph agent identities, state schemas, tool allowlists, and graph wiring
  over MCP tools. No direct platform mutation and no direct SQL access.
```

## Current Repository Signals

- `docs/research_agents/agent_operating_model.md` defines a supervisor hierarchy. This plan should preserve that boundary: Data Agent tools produce dataset manifests and data-quality reports; Quantitative Methods tools produce deterministic method contracts, validation reports, signal diagnostics, multiple-testing reports, and optional parity-checked kernel artifacts; ML tools produce feature/model/prediction artifacts; Hypothesis tools produce hypothesis cards; Quant Research Supervisor tools consume those artifacts and produce experiment/comparison/recommendation artifacts; Evaluation and Adversarial tools produce critique and robustness reports.
- `src/trader/research.py` currently contains useful research helper behavior, but it is misplaced in the core platform package and should be moved or re-created under `src/trader_research/`.
- `src/trader/tools/` currently contains useful tool-facing behavior, but it is also misplaced in the core platform package and should be moved or re-created under `src/trader_research/` or `src/trader_mcp/` depending on whether the code is research-domain logic or MCP transport logic.
- Existing backtest entry points are centered on `trader.backtest.BacktestRunner`, `BacktestSpec`, `BacktestAssumptions`, and export helpers.
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

This plan follows `docs/research_agents/agent_operating_model.md`: agents are implemented as LangGraph identities that use deterministic MCP tools to produce inspectable artifacts. The plan does not require building every autonomous workflow before useful tools exist; it proves one tool, then wraps it with one agent identity, then repeats.

| Agent | First MCP responsibility in this plan | Owned artifacts |
| --- | --- | --- |
| Quant Research Supervisor Agent | Supervisor state, handoff ledger, strategy planning, validation, backtest orchestration, recommendations | experiment plans, suites, comparison reports, recommendation reports |
| Data Agent | Symbol discovery/preflight, data inventory, data quality, explicit load/backfill | `symbol_discovery_report.json`, `dataset_manifest.json`, `data_quality_report.json`, load result envelopes |
| Quantitative Methods Agent | Knowledge-backed method contract listing, validation, signal diagnostics, multiple-testing controls, and optional numerical kernel packaging | source manifests, method cards, retrieval/citation reports, method contracts, validation reports, signal diagnostics, multiple-testing reports, kernel manifests, parity reports |
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
| Quantitative Methods Agent | Owns `QuantMethodsState`, knowledge source/card/retrieval/citation state, method-contract state, validation status, diagnostic state, multiple-testing state, optional kernel/parity state, and optional bounded LLM control decisions. | May call only Quantitative Methods `knowledge_*` and `math_*` tools plus read-only health/config tools; cannot fetch data, create hypotheses, train models, run backtests, or promote strategies. |
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
  -> Quantitative Methods knowledge/method tools and identity produce source-backed deterministic method artifacts
  -> ML tool and identity produce model-artifact references
  -> Hypothesis tool and identity produce hypothesis cards
  -> Quant Research Supervisor LLM control loop assesses state and chooses validated next actions
  -> Quant Research Supervisor strategy and backtest tools
  -> Evaluation and Adversarial tool/identity checkpoints
  -> Quant Research Supervisor synthesis/runner tools
```

Every stage should leave behind a usable MCP tool, a direct service test, an MCP contract/smoke test, and an artifact that matches the owning agent's contract.

## Completion Status Register

Use this register as the source of truth for implementation status. Keep statuses to `Not started`, `In progress`, `Blocked`, or `Done`. A chunk should only move to `Done` when its acceptance criteria are met and the evidence column points to tests, docs, command output, or artifact paths that prove it.

| Chunk | Status | Evidence | Notes |
| --- | --- | --- | --- |
| 0. Boundary Recon | Done | `docs/research_agents/mcp_trading_research_tools.md` Boundary Recon notes | Smallest first MCP data slice and later migration candidates documented. |
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
| 16. Data MCP and LangGraph Workflow Evidence | Done | `tests/test_mcp_data_workflow.py`; `tests/test_langgraph_data_workflow.py`; `docs/research_agents/mcp_trading_research_tools.md` | Stdio MCP evidence covers health/config/inventory/quality/ensure/final quality with JSON text parity; LangGraph evidence completes the same workflow through the MCP client. |
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
| 22G. Symbol Discovery Documentation and Evidence | Done | `docs/research_agents/mcp_trading_research_tools.md`; `docs/research_agents/ai_tool_workflows.md`; `plans/data_agent_symbol_discovery_tool_plan.md`; `uv run pytest -m 'not postgres'` | Docs describe provider-scoped stock/crypto discovery, provider/instrument/bar selection, mandatory preflight, provider policy, and discovery versus inventory/loading/backtest behavior. |
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
| 23L. Signal Diagnostics and Multiple-Testing Reports | Not started |  | Produce signal diagnostics and family-level inference reports with approved method-card references and validated implementation refs where required. |
| 23M. C++ / Compiled Kernel Path | Not started |  | Add template-restricted local compiled-kernel generation/compile flow for approved deterministic transforms after Python references are validated. |
| 23N. Python/C++ Parity and Method Packaging | Not started |  | Compare optimized compiled implementations against approved Python references and package method contracts, implementation manifests, validation reports, and provenance. |
| 24. Register Quantitative Methods MCP Tools | Done | `tests/test_mcp_quant_methods_tools.py`; `tests/test_mcp_server.py`; `tests/test_agent_identities.py` | MCP registers the current `knowledge_*` and `math_*` Quantitative Methods tool surface with `agent_owner="Quantitative Methods Agent"`, correct side-effect metadata, config listing, and injectable fake stores/LLM clients for tests. |
| 25. Quantitative Methods Agent Graph | Not started |  |  |
| 26. Supervisor Consumes Quantitative Methods Handoff | Not started |  |  |
| 27. ML Artifact Tool Contracts | Not started |  |  |
| 28. Register ML MCP Tools | Not started |  |  |
| 29. ML Agent Graph | Not started |  |  |
| 30. Supervisor Consumes ML Handoff | Not started |  |  |
| 31. Hypothesis Card Service | Not started |  |  |
| 32. Register Hypothesis MCP Tool | Not started |  |  |
| 33. Hypothesis Agent Graph | Not started |  |  |
| 34. Supervisor Consumes Hypothesis Handoff | Not started |  |  |
| 34A. Supervisor LLM Control Loop | Not started |  |  |
| 35. Strategy Template Catalog | Not started |  |  |
| 36. Register Strategy Catalog MCP Tool | Not started |  |  |
| 37. Strategy Candidate Validation | Not started |  |  |
| 38. Register Strategy Validation MCP Tool | Not started |  |  |
| 39. Supervisor Strategy Planning Graph | Not started |  |  |
| 40. Baseline Backtest Service | Not started |  |  |
| 41. Register Backtest MCP Tools | Not started |  |  |
| 42. Result Lookup Service | Not started |  |  |
| 43. Attribution Service and MCP Tool | Not started |  |  |
| 44. Evaluation Report Logic | Not started |  |  |
| 45. Register Evaluation MCP Tool | Not started |  |  |
| 46. Evaluation Agent Graph | Not started |  |  |
| 47. Supervisor Consumes Evaluation Handoff | Not started |  |  |
| 48. Adversarial Robustness Core | Not started |  |  |
| 49. Register Adversarial Robustness MCP Tool | Not started |  |  |
| 50. Adversarial Agent Graph | Not started |  |  |
| 51. Robustness Backtest Variants | Not started |  |  |
| 52. Supervisor Consumes Adversarial Handoff | Not started |  |  |
| 53. Recommendation Renderer and MCP Tool | Not started |  |  |
| 54. Quant Research Supervisor Synthesis Graph | Not started |  |  |
| 55. Experiment Runner and MCP Tool | Not started |  |  |
| 56. Import Boundary Tests | Not started |  |  |
| 57. MCP and LangGraph Contract Tests | Not started |  |  |
| 58. Iterative Documentation | Not started |  |  |
| 59. Verification Pass | Not started |  |  |
| 60. Calendar-Aware Data Quality | Not started | AMD 12-month `1Min` MCP run exposed wall-clock gap overcounting in `artifacts/research/amd_12mo_1min_data_agent_quality_full_2026-05-28.json` | Later backlog item: add market-calendar/session-aware expected-bar and gap classification for stocks so nights, weekends, holidays, early closes, and feed/session windows are not reported as missing data. Preserve warnings for true intra-session gaps and coverage edges. |

## Proposed Package Shape

```text
src/trader_research/
  __init__.py
  agents.py             # Agent/tool ownership metadata from agent_operating_model.md
  domain.py              # ExperimentPlan, Experiment, StrategyCandidate, reports, verdicts
  contracts.py           # ToolEnvelope, side-effect declarations, shared JSON helpers
  data.py                # Data Agent inventory, manifests, quality, and loading wrappers
  math_domain.py         # Quantitative Methods artifact schemas and validation
  math_registry.py       # Maintained method registry and approved families
  math_tools.py          # Quantitative Methods service wrappers and envelopes
  method_implementations.py # Python implementation manifests, entrypoint allowlists, source hashes, and fixture validation
  signal_diagnostics.py  # IC, rank IC, hit-rate, quantile, decay, and breakdown reports
  multiple_testing.py    # Multiple-testing and data-snooping controls
  cpp_kernel_artifacts.py # Template-restricted compiled-kernel manifests and Python/C++ parity reports
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
  ml.py                  # ML feature/model/prediction/drift artifact contracts and summaries
  hypotheses.py          # Hypothesis-card creation and validation
  strategies.py          # Template listing and candidate validation
  backtests.py           # Baseline backtest wrapper and result lookup
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
| `knowledge_create_method_card_draft` | Quantitative Methods Agent | `local_mutating` | Create a non-approved draft method card from retrieved source evidence. |
| `knowledge_publish_method_card` | Quantitative Methods Agent | `local_mutating` | Promote a draft method card to approved status after explicit maintainer/operator approval. |
| `knowledge_validate_citations` | Quantitative Methods Agent | `read_only` | Validate source IDs, chunk IDs, locators, method-card approval, and claim coverage for a contract/report. |
| `math_list_method_contracts` | Quantitative Methods Agent | `read_only` | Return maintained indicators, transforms, statistical tests, diagnostics, multiple-testing methods, assumptions, and metadata requirements. |
| `math_validate_method_contract` | Quantitative Methods Agent | `read_only` | Validate method parameters, input schema, warmup behavior, assumptions, fixture expectations, and failure modes. |
| `math_register_method_implementation` | Quantitative Methods Agent | `local_mutating` | Register a Python reference implementation manifest with entrypoint, source hash, dependency allowlist, safety profile, method contract refs, and approved method-card refs. |
| `math_generate_python_method` | Quantitative Methods Agent | `local_mutating` | Create a quarantined Python reference artifact from an approved method card/contract and immediately require fixture validation before use. |
| `math_run_indicator_fixtures` | Quantitative Methods Agent | `local_mutating` | Run deterministic fixtures against a registered Python reference implementation and produce `indicator_validation_report.json`. |
| `math_run_signal_fixtures` | Quantitative Methods Agent | `local_mutating` | Run deterministic latest-first bar fixtures against a registered `trader.signals.Signal` implementation and produce a signal implementation validation report. |
| `math_run_signal_diagnostics` | Quantitative Methods Agent | `local_mutating` | Produce `signal_diagnostic_report.json` from method observations and forward-return labels. |
| `math_run_multiple_testing_report` | Quantitative Methods Agent | `local_mutating` | Produce `multiple_testing_report.json` for a declared candidate family and metric matrix. |
| `math_generate_cpp_kernel` | Quantitative Methods Agent | `local_mutating` | Generate C++ only from approved deterministic templates after a validated Python reference exists. |
| `math_compile_kernel` | Quantitative Methods Agent | `local_mutating` | Compile an approved kernel locally and return build evidence. |
| `math_run_python_cpp_parity` | Quantitative Methods Agent | `local_mutating` | Compare Python reference and C++ outputs and produce `python_cpp_parity_report.json`. |
| `math_package_method_artifact` | Quantitative Methods Agent | `local_mutating` | Bundle contracts, implementations, validation reports, parity reports, and provenance for handoff. |
| `ml_create_feature_manifest` | ML Agent | `local_mutating` | Produce `feature_dataset_manifest.json` from explicit data and feature inputs. |
| `ml_summarize_model_artifact` | ML Agent | `read_only` | Return or validate `model_card.json`, prediction, and drift artifact references. |
| `hypothesis_create_card` | Hypothesis Agent | `read_only` | Produce `hypothesis_card.json` from structured input. |
| `research_create_plan` | Quant Research Supervisor Agent | `read_only` | Convert a hypothesis card or structured request into an explicit experiment plan. |
| `research_list_strategy_templates` | Quant Research Supervisor Agent | `read_only` | Return supported maintained strategy families and parameter schemas. |
| `research_validate_strategy_candidate` | Quant Research Supervisor Agent | `read_only` | Validate an existing/generated candidate before any backtest. |
| `research_run_backtest` | Quant Research Supervisor Agent | `local_mutating` | Run one reproducible baseline backtest and export result artifacts. |
| `research_get_backtest_results` | Quant Research Supervisor Agent | `read_only` | Fetch summary metrics, warnings, and artifact paths for a backtest run. |
| `evaluation_generate_report` | Evaluation Agent | `local_mutating` | Produce `evaluation_report.json` from data quality, backtest, warning, and sample-size evidence. |
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
| 1. Clean Package Skeleton | Add tracked source files for `trader_research`, `trader_mcp`, and `trader_agents`. Include lightweight agent ownership metadata aligned with `agent_operating_model.md`. | `src/trader_research/*`, `src/trader_mcp/*`, `src/trader_agents/*` | Packages import cleanly; no behavior depends on untracked/generated files; Data Agent ownership can be represented in tool metadata and LangGraph identity metadata. |
| 2. Minimal Tool Contracts | Create the minimal `ToolEnvelope`, `SideEffect`, agent owner, artifact reference, and JSON helper surface needed for the first MCP data tool. Do not migrate every historical helper yet. | `src/trader_research/contracts.py`, tests | The first Data Agent tool can return a stable envelope from `trader_research.contracts`. |
| 3. MCP Envelope Adapter | Add small adapter helpers for converting `trader_research.contracts.ToolEnvelope` values into MCP tool responses. | `src/trader_mcp/adapters.py` | The adapter can return the envelope as MCP-compatible structured content. |
| 4. MCP Server Skeleton | Add MCP server startup with a stdio transport and register read-only health/config tools before any broad research schemas or backtest work. | `src/trader_mcp/server.py`, `pyproject.toml`, tests | `uv run python -m trader_mcp.server` starts; an MCP-capable client can list at least health/config tools. |
| 5. Data Inventory Service | Implement the smallest useful Data Agent `get_data_inventory` service against existing market-data/event-store interfaces. Start with symbol/timeframe/window validation, source metadata, bar counts, and dataset manifest payload. | `src/trader_research/data.py`, tests | Missing data produces warnings and does not silently pass as complete; output can be saved as or embedded in `dataset_manifest.json`. |
| 6. Register Data Inventory MCP Tool | Expose `data_get_inventory` immediately after the service exists. | `src/trader_mcp/server.py`, `tests/test_mcp_tools.py` | Tool inputs are validated; output uses the shared envelope and declares `agent_owner=Data Agent`. |
| 7. First MCP Tool Evidence | Run and document the first evidence loop: MCP server boots, client lists tools, client calls `data_get_inventory`, and receives a valid Data Agent envelope. | `docs/research_agents/mcp_trading_research_tools.md`, tests or command output | There is reproducible MCP evidence before data-quality, loading, strategy, backtest, or report work begins. |
| 8. LangGraph Agent Identity Skeleton | Add LangGraph identity scaffolding: agent registry, state base, MCP tool client wrapper, and per-agent tool allowlist model. | `src/trader_agents/*`, tests | A Data Agent graph can be instantiated with a distinct identity and only the allowed MCP tools. |
| 9. Data Agent Inventory Graph | Implement the first Data Agent LangGraph graph using `data_get_inventory` through the MCP client. | `src/trader_agents/data_agent.py`, tests | The graph returns Data Agent state with dataset manifest payload/artifact reference and does not call platform internals directly. |
| 10. Data Quality Service | Implement Data Agent `summarize_data_quality` as a wrapper around existing data-quality checks and report writing. | `src/trader_research/data.py`, tests | Tool can produce `data_quality_report.json` with missing bars, duplicate bars, suspicious prices, and symbol-level coverage when the underlying platform can detect them. |
| 11. Register Data Quality MCP Tool | Expose `data_summarize_quality` as soon as the service works. | `src/trader_mcp/server.py`, `tests/test_mcp_tools.py` | MCP smoke test returns a Data Agent quality envelope and optional `data_quality_report.json` artifact path for sample/existing data. |
| 12. Extend Data Agent Graph for Quality | Add a Data Agent LangGraph node that calls `data_summarize_quality` and updates quality state. | `src/trader_agents/data_agent.py`, tests | The Data Agent graph can run inventory -> quality through MCP and return both artifact references. |
| 13. Data Ensure/Loading Service | Implement Data Agent `ensure_market_data` as an explicit policy wrapper around existing sample/backfill/existing modes. Require bounded symbols, timeframe, and date window. | `src/trader_research/data.py`, tests | Backfill/sample modes are opt-in; unpermitted missing data returns a failed envelope; successful loads return dataset/load evidence. |
| 14. Register Data Loading MCP Tool | Expose `data_ensure_loaded` with clear side-effect metadata and bounded-write guardrails. | `src/trader_mcp/server.py`, `tests/test_mcp_tools.py` | MCP smoke test can run dry-run/plan mode and sample-load mode; live backfill remains explicit and bounded. |
| 15. Extend Data Agent Graph for Loading | Add a Data Agent LangGraph node that can call `data_ensure_loaded` only when policy permits mutation. | `src/trader_agents/data_agent.py`, tests | The Data Agent graph preserves load policy in state and refuses unbounded or unapproved writes. |
| 16. Data MCP and LangGraph Workflow Evidence | Run and document the complete Data Agent workflow: health -> inventory -> quality -> ensure/load -> quality, all through MCP tools and the Data Agent graph. | `docs/research_agents/mcp_trading_research_tools.md`, tests or command output | A developer can reproduce data-tool MCP evidence and Data Agent LangGraph identity evidence without strategy/backtest/report implementation. |
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
| 23H. Knowledge-Backed Math Method Domain Schemas | Define Quantitative Methods schemas that require knowledge provenance for non-trivial statistical methods. | `src/trader_research/math_domain.py`, `src/trader_research/domain.py`, `tests/test_math_domain.py` | `indicator_contract.json`, `statistical_test_contract.json`, `signal_diagnostic_report.json`, `multiple_testing_report.json`, `cxx_kernel_manifest.json`, `python_cpp_parity_report.json`, and `method_package_manifest.json` include optional/required `knowledge_evidence_refs` by method complexity; statistical-test and multiple-testing contracts require approved method cards; simple arithmetic transforms may use maintained registry entries; unknown or uncited sophisticated methods fail closed. |
| 23I. Knowledge-Backed Math Method Registry | Create the maintained registry of approved methods, linked to approved method cards where required. | `src/trader_research/math_registry.py`, `src/trader_research/math_tools.py`, `tests/test_math_registry.py` | Registry lists maintained methods by family; each non-trivial statistical method links to one or more approved method cards; unsupported methods fail closed; legacy indicator-only views remain filterable for compatibility. |
| 23J. Citation-Backed Python Implementation Validation | Implement the first real implementation gate for deterministic indicators/transforms. | `src/trader_research/method_implementations.py`, `src/trader_research/math_tools.py`, `src/trader_standard/indicators/*`, `tests/test_method_implementations.py`, `tests/test_mcp_quant_methods_tools.py` | Reuses `trader.indicators.Indicator` and `IndicatorObservation` as the runtime contract; validates that a Python reference implementation is tied to an approved method card and method contract; records entrypoint, source hash, source provenance docstring, implementation language, dependency allowlist, and safety profile; validates `sma`, `ema`, `rsi`, `rolling_volatility`, and `z_score`; checks warmup/null behavior, output length, default deterministic fixtures, and no-lookahead prefix behavior; unknown entrypoints, unsafe dependencies, missing provenance docstrings, unapproved method-card refs, hash mismatches, fixture mismatches, and non-`Indicator` classes fail closed. |
| 23K. Python Method Artifact Generation and Registration | Add the controlled Python implementation artifact path after the 23J validation gate exists. | `src/trader_research/method_implementations.py`, `src/trader_research/math_tools.py`, `src/trader_mcp/knowledge_tools.py`, `tests/test_method_implementations.py`, `tests/test_mcp_quant_methods_tools.py` | Existing maintained Python `Indicator` implementations can be registered as `method_implementation_manifest.json` records; LLM-authored Python drafts are written only to `artifacts/research/method_implementations/quarantine/`, never directly into runtime packages; generated artifacts must start with a source/provenance docstring, cite approved method cards, declare method contracts, pass static safety checks, record source hashes and dependency allowlists, and pass 23J fixtures before they are marked `validated`. |
| 23K-A. Citation-Backed Signal Method Vertical Slice | Prove a non-indicator code artifact through the full knowledge-backed process using the existing `trader.signals.Signal` interface. | `src/trader_research/method_implementations.py`, `src/trader_research/math_tools.py`, `src/trader_mcp/knowledge_tools.py`, `src/trader_standard/signals/*`, `src/trader_research/method_contracts_seed.json`, `tests/test_method_implementations.py`, `tests/test_mcp_quant_methods_tools.py` | Select one textbook-backed trading-rule method; retrieve and dereference evidence through `knowledge_retrieve_evidence` and `knowledge_get_evidence_chunks`; create and publish an approved method card; add a persisted/store-backed method contract with `runtime_contract="trader.signals.Signal"` or equivalent metadata; extend implementation registration to accept `Signal` subclasses without weakening the existing `Indicator` checks; add deterministic latest-first bar fixtures for `compute(bars) -> float`, warmup behavior, no-lookahead prefix checks, source hash, provenance docstring, and approved method-card refs; write `method_implementation_manifest.json` and a signal fixture validation report. Diagnostics and family-level inference remain 23L, not part of this vertical slice. |
| 23L. Signal Diagnostics and Multiple-Testing Reports | Implement first-pass signal diagnostics and family-level inference over declared candidate families. | `src/trader_research/signal_diagnostics.py`, `src/trader_research/multiple_testing.py`, `src/trader_research/math_tools.py`, `tests/test_signal_diagnostics.py`, `tests/test_multiple_testing.py` | Computes IC/rank IC, hit rate, quantile buckets, monotonicity, horizon decay, and symbol/session/regime breakdowns where inputs exist; requires candidate-family manifests for family inference; records raw p-values, adjusted p-values, correction method, tested grid, and candidate count; sophisticated procedures require approved method-card references and, where executable methods are used, validated implementation refs; outputs include warnings and blockers. |
| 23M. C++ / Compiled Kernel Path | Implement a controlled compiled-kernel path for approved deterministic transforms after Python references are validated. | `src/trader_research/cpp_kernel_artifacts.py`, `src/trader_research/math_tools.py`, `src/trader_standard/indicators/cpp/*`, `src/trader_standard/indicators/bindings/*`, `tests/test_cpp_kernel_artifacts.py` | C++ generation is template-based only and requires an approved Python reference implementation manifest plus passing fixture validation; compilation occurs in an isolated local build directory; manifests record build settings, ABI/binding info, source/template provenance, and benchmark summary; failed compile returns a blocking envelope; kernels cannot access broker mutation, SQL, network, filesystem mutation, or live trading controls. |
| 23N. Python/C++ Parity and Method Packaging | Compare optimized implementations against approved Python references and package validated method artifacts for handoff. | `src/trader_research/cpp_kernel_artifacts.py`, `src/trader_research/method_implementations.py`, `src/trader_research/math_tools.py`, `tests/test_python_cpp_parity.py`, `tests/test_method_package_artifacts.py` | Python/C++ parity tests run on deterministic fixtures and seeded generated cases; parity reports identify tolerances, mismatches, dtype/alignment assumptions, and blockers; packaging bundles method cards, contracts, Python implementation manifests, fixture reports, optional kernel manifests, parity reports, and citation-validation refs into `method_package_manifest.json`. |
| 24. Register Quantitative Methods MCP Tools | Expose the deterministic method surface through MCP after knowledge ingestion/retrieval tools exist. | `src/trader_mcp/server.py`, `src/trader_mcp/schemas.py`, `tests/test_mcp_math_tools.py`, `tests/test_mcp_server.py` | MCP exposes `math_list_method_contracts` and `math_validate_method_contract` first; backward-compatible indicator aliases may exist; follow-on tools register only after direct services pass tests; every tool returns a shared envelope with `agent_owner="Quantitative Methods Agent"`, declares side effect, rejects unbounded inputs or unknown methods, and requires approved method-card references for sophisticated statistical procedures where configured. |
| 25. Quantitative Methods Agent Graph | Add knowledge-aware LangGraph identity, state, policy, and tool allowlist for the Quantitative Methods Agent. | `src/trader_agents/quant_methods_agent.py`, `src/trader_agents/quant_methods_policy.py`, `src/trader_agents/state.py`, `tests/test_quant_methods_agent.py`, `tests/test_langgraph_agents.py` | Graph has distinct identity and state; may call only knowledge and Quantitative Methods MCP tools; cannot fetch data, create hypotheses, train models, run backtests, call evaluation tools, or promote strategies; blocks sophisticated methods without approved source-backed method cards; returns method artifact refs, retrieval refs, citation-validation refs, and blockers; no raw prompts, hidden reasoning, or scratchpads are persisted. |
| 26. Supervisor Consumes Quantitative Methods Handoff | Allow the Quant Research Supervisor to consume Quantitative Methods artifacts and knowledge provenance without rewriting them. | `src/trader_agents/quant_research.py`, `src/trader_research/domain.py`, `tests/test_supervisor_quant_methods_handoff.py` | Supervisor accepts valid Quantitative Methods handoffs with method artifacts and knowledge evidence refs; rejects wrong owner, missing provenance, missing artifact refs, unresolved blockers, or failed citation validation; can require method artifacts before strategy planning; stores refs, warnings, blockers, and public status only; does not modify method artifacts or knowledge evidence. |
| 27. ML Artifact Tool Contracts | Implement initial ML artifact services for feature manifests and model-card/prediction/drift summaries. Do not start with automated training. | `src/trader_research/ml.py`, tests | ML artifact references are validated for required provenance, data inputs, feature definitions, and metrics/warnings. |
| 28. Register ML MCP Tools | Expose `ml_create_feature_manifest` and `ml_summarize_model_artifact`. | `src/trader_mcp/server.py`, tests | MCP returns ML Agent envelopes for feature/model artifact references and rejects incomplete metadata. |
| 29. ML Agent Graph | Add LangGraph identity, state, and tool allowlist for the ML Agent. | `src/trader_agents/ml_agent.py`, tests | ML graph calls only ML MCP tools and returns feature/model/prediction/drift artifact references. |
| 30. Supervisor Consumes ML Handoff | Add supervisor handoff consumption for optional ML artifacts. | `src/trader_agents/quant_research.py`, tests | Supervisor can distinguish hypotheses that require model artifacts from those that do not. |
| 31. Hypothesis Card Service | Implement `hypothesis_create_card` from structured inputs and available ingredient references. | `src/trader_research/hypotheses.py`, tests | Hypothesis cards require mechanism, data requirements, required features, strategy intent, and falsification criteria. |
| 32. Register Hypothesis MCP Tool | Expose `hypothesis_create_card`. | `src/trader_mcp/server.py`, tests | MCP returns a Hypothesis Agent envelope with `hypothesis_card.json` payload/path. |
| 33. Hypothesis Agent Graph | Add LangGraph identity, state, and tool allowlist for the Hypothesis Agent. | `src/trader_agents/hypothesis_agent.py`, tests | Hypothesis graph can read ingredient references and produce hypothesis-card handoffs without running backtests. |
| 34. Supervisor Consumes Hypothesis Handoff | Add supervisor handoff consumption for hypothesis cards. | `src/trader_agents/quant_research.py`, tests | Supervisor can convert accepted hypothesis references into planning state and reject incomplete cards. |
| 34A. Supervisor LLM Control Loop | Add the LLM-backed supervisor policy node after Data, Quantitative Methods, ML, and Hypothesis artifact contracts exist. The LLM sees bounded state and artifact summaries, then emits a typed decision such as `request_specialist`, `call_tool`, `retry_with_changes`, `accept_artifact`, `block`, or `finish`. A deterministic router validates the proposal before any action is taken. | `src/trader_agents/supervisor_policy.py`, `src/trader_agents/quant_research.py`, tests | Supervisor can assess outputs, reuse allowed tools, request missing specialist work, stop early, or finish through typed actions only. Tests prove schema validation, allowlist enforcement, loop limits, early block/finish behavior, repair/fail-closed behavior for invalid LLM output, and no persistence of raw prompts, hidden reasoning, or scratchpads. |
| 35. Strategy Template Catalog | Expose Quant Research strategy-template discovery over maintained `trader_standard` families: `trend_following`, `mean_reversion`, and `bollinger_band` initially. | `src/trader_research/strategies.py`, tests | Tool returns family names, required/optional parameters, defaults, and known constraints. |
| 36. Register Strategy Catalog MCP Tool | Expose `research_list_strategy_templates`. | `src/trader_mcp/server.py`, tests | MCP returns maintained strategy templates with `agent_owner=Quant Research Supervisor Agent` and without importing arbitrary strategy code. |
| 37. Strategy Candidate Validation | Implement Quant Research validation for existing maintained strategies first. Defer generated-code candidates until the maintained strategy path is stable. | `src/trader_research/strategies.py`, tests | Unsupported strategy families fail closed; maintained strategies can be instantiated on deterministic fixtures. |
| 38. Register Strategy Validation MCP Tool | Expose `research_validate_strategy_candidate`. | `src/trader_mcp/server.py`, tests | MCP validation fails closed for unsupported families and returns fixture validation evidence for maintained strategies. |
| 39. Supervisor Strategy Planning Graph | Extend the supervisor graph to call strategy catalog/validation tools through MCP using Data, Quantitative Methods, ML, and Hypothesis handoffs. | `src/trader_agents/quant_research.py`, tests | Supervisor creates an experiment-plan state only from specialist artifact references and validated strategy candidates. |
| 40. Baseline Backtest Service | Wrap `trader.backtest.BacktestRunner` for Quant Research using explicit `BacktestSpec`, symbols, asset class, assumptions, strategy, event store, and artifact output directory. | `src/trader_research/backtests.py`, tests | A fixture-backed baseline run produces metrics, provenance, and artifact paths tied to dataset manifest and data-quality report references when available. |
| 41. Register Backtest MCP Tools | Expose `research_run_backtest` and `research_get_backtest_results`. | `src/trader_mcp/server.py`, tests | MCP can run one fixture/sample-data backtest and fetch its result envelope with `agent_owner=Quant Research Supervisor Agent`. |
| 42. Result Lookup Service | Load persisted or artifact-backed backtest summaries using existing `list_experiment_runs`, exported `metrics.json`, and result bundles. | `src/trader_research/backtests.py`, tests | Unknown IDs return structured errors; known runs return summary metrics and artifact references. |
| 43. Attribution Service and MCP Tool | Implement Quant Research return attribution from trade ledger/equity artifacts and expose `research_analyze_return_attribution`. | `src/trader_research/attribution.py`, `src/trader_mcp/server.py`, tests | Reportable attribution data can be produced through MCP without LLM interpretation. |
| 44. Evaluation Report Logic | Encode Evaluation Agent critique rules for data-quality blockers, warning counts, weak sample size, turnover, drawdown, and cost sensitivity. | `src/trader_research/evaluation.py`, tests | Weak baseline, missing data-quality reports, unexplained warnings, or destroyed edge under costs produces `evaluation_report.json` with skeptical findings. |
| 45. Register Evaluation MCP Tool | Expose `evaluation_generate_report`. | `src/trader_mcp/server.py`, tests | MCP returns Evaluation Agent envelopes linked to data, hypothesis, backtest, attribution, and warning evidence. |
| 46. Evaluation Agent Graph | Add LangGraph identity, state, and tool allowlist for the Evaluation Agent. | `src/trader_agents/evaluation_agent.py`, tests | Evaluation graph consumes evidence artifacts and cannot create hypotheses or mutate data. |
| 47. Supervisor Consumes Evaluation Handoff | Add supervisor handoff consumption for evaluation reports. | `src/trader_agents/quant_research.py`, tests | Supervisor state preserves blockers, caveats, and verdicts before recommendation synthesis. |
| 48. Adversarial Robustness Core | Implement Adversarial Agent robustness attacks: slippage sensitivity, fee sensitivity, chronological split, symbol concentration, trade concentration, and period concentration. | `src/trader_research/robustness.py`, tests | At least three attacks run in the first pass; output can be saved as `robustness_report.json`; concentration flags trigger on dominated PnL fixtures. |
| 49. Register Adversarial Robustness MCP Tool | Expose `adversarial_run_robustness` once core checks exist. | `src/trader_mcp/server.py`, tests | MCP returns `robustness_report.json` summaries linked to baseline run artifacts. |
| 50. Adversarial Agent Graph | Add LangGraph identity, state, and tool allowlist for the Adversarial Agent. | `src/trader_agents/adversarial_agent.py`, tests | Adversarial graph can call robustness tools but cannot produce recommendations or promotion decisions. |
| 51. Robustness Backtest Variants | Add backtest variants for 2x/5x slippage and elevated fees by modifying only explicit assumptions. | `src/trader_research/robustness.py`, tests | Higher-cost variants are linked to the baseline and exported as separate reproducible runs. |
| 52. Supervisor Consumes Adversarial Handoff | Add supervisor handoff consumption for robustness reports. | `src/trader_agents/quant_research.py`, tests | Supervisor state can block promotion readiness on robustness failures without modifying the Adversarial artifact. |
| 53. Recommendation Renderer and MCP Tool | Generate Quant Research recommendation reports and expose `research_generate_recommendation`; recommendations must consume evaluation and robustness artifacts when present. | `src/trader_research/reports.py`, `src/trader_mcp/server.py`, tests | MCP returns recommendation artifact paths and JSON summary; paper-promotion readiness is blocked without required critique artifacts. |
| 54. Quant Research Supervisor Synthesis Graph | Extend the supervisor graph to synthesize Data, Quantitative Methods, ML, Hypothesis, Evaluation, and Adversarial artifact handoffs into recommendation state. | `src/trader_agents/quant_research.py`, tests | Supervisor synthesizes artifacts but does not bypass specialist graphs or MCP tools. |
| 55. Experiment Runner and MCP Tool | Implement `ResearchExperimentRunner.run(plan_or_request)` and expose `research_run_experiment` last. | `src/trader_research/runner.py`, `src/trader_mcp/server.py`, tests | Full MCP experiment composes specialist artifacts and returns recommendation paths, verdict, and warnings. |
| 56. Import Boundary Tests | Add tests that assert `trader` does not import `trader_research`, `trader_mcp`, `trader_agents`, or other agent/tool packages, and that dependencies flow one way. | `tests/test_package_boundaries.py` | The architectural separation is executable, not just documented. |
| 57. MCP and LangGraph Contract Tests | Add tests that call MCP tool functions directly and exercise LangGraph agent allowlists/state transitions. Expand these tests at every tool/agent-registration chunk. | `tests/test_mcp_tools.py`, `tests/test_langgraph_agents.py` | Tool names, required schemas, side effects, envelope shapes, agent owners, and graph boundaries are stable incrementally. |
| 58. Iterative Documentation | Update bounded-context docs in the same change as each implementation slice. Document local MCP server installation, LangGraph agent usage, sample client config, safe usage boundaries, and the package-boundary contract. Start docs with first tool evidence, then Data Agent graph evidence. | `docs/research_agents/mcp_trading_research_tools.md`, `docs/research_agents/tool_contracts.md`, `docs/README.md`, bounded context READMEs | A developer can start the server and reproduce each MCP and LangGraph evidence checkpoint; docs stay in the correct bounded context. |
| 59. Verification Pass | Run focused tests, mypy for touched modules if configured, and a sample end-to-end experiment using checked-in sample data. | Test suite and sample artifacts | Relevant tests pass; any unavailable integration dependencies are called out. |

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

Stretch evidence:

```text
math_run_signal_diagnostics
math_run_multiple_testing_report
  -> approved method card used to validate a statistical-test or multiple-testing contract
  -> records candidate family size, tested parameter grid, raw p-values, adjusted p-values, warnings, and blockers
```

### Slice 6: Knowledge-Aware Quantitative Methods Agent Identity and Handoff

Implement chunks 25-26. This proves that the Quantitative Methods graph has its own identity and that the supervisor
can consume, but does not rewrite, Quantitative Methods artifacts or their knowledge provenance.

Evidence target:

```text
Quantitative Methods graph starts
  -> graph state includes Quantitative Methods identity
  -> graph calls only knowledge_* and math_* MCP tools
  -> graph blocks unsupported or uncited sophisticated methods
  -> graph returns method artifact refs plus retrieval/citation refs
  -> supervisor consumes Quantitative Methods handoff
  -> supervisor preserves ownership/provenance and blocks unresolved method warnings
```

### Slice 7: ML MCP Tool Creation

Implement chunks 27-28. This creates feature/model artifact tools before any ML graph exists. Training is deliberately
not the first ML capability; artifact contracts and provenance come first.

### Slice 8: ML Agent Identity and Handoff

Implement chunks 29-30. This proves that the ML graph has its own identity and that the supervisor can track optional
model dependencies separately from non-ML hypotheses.

### Slice 9: Hypothesis MCP Tool Creation

Implement chunks 31-32 after Data, Quantitative Methods, and optional ML ingredient contracts are explicit. The first
hypothesis tool produces structured, falsifiable `hypothesis_card.json` artifacts.

### Slice 10: Hypothesis Agent Identity and Handoff

Implement chunks 33-34. This proves that the Hypothesis Agent can produce candidate ideas while the supervisor retains
responsibility for planning, validation, and verdicts.

### Slice 10A: Supervisor LLM Control Loop

Implement chunk 34A after Data, Quantitative Methods, optional ML, and Hypothesis handoff contracts exist. The supervisor also
needs real LLM backing, but its action space is cross-agent and should wait until enough specialist artifact contracts
exist to make orchestration meaningful. The LLM belongs inside the Quant Research Supervisor as a bounded control-policy
node: it assesses artifact summaries and public state, then emits a typed action proposal. A deterministic router
validates that proposal before any specialist request, MCP tool call, retry, early block, or finish transition is
allowed.

Evidence target:

```text
supervisor state + artifact summaries
  -> LLM policy node emits typed action proposal
  -> deterministic router validates action, allowlist, ownership, and loop budget
  -> graph routes to next specialist/tool, blocks early, or finishes
```

Required guardrails:

- no raw prompt, hidden reasoning, or scratchpad persistence
- no arbitrary tool names or unbounded parameters from the LLM
- invalid structured output fails closed or enters a bounded repair path
- repeated tool use is allowed only through explicit loop limits and state diffs
- `block` and `finish` are first-class supervisor states, not exceptions

### Slice 11: Quant Research Strategy Planning Tools

Implement chunks 35-39. Strategy template discovery, candidate validation, and supervisor planning occur only after
specialist artifact handoffs and the supervisor control-policy loop exist.

Evidence target:

```text
hypothesis_card.json + Data/Quantitative Methods/ML artifact references
  -> research_list_strategy_templates
  -> research_validate_strategy_candidate
  -> supervisor experiment-plan state
```

### Slice 12: Quant Research Backtest and Attribution Tools

Implement chunks 40-43 incrementally. Each service gets registered through MCP as soon as it works; the supervisor graph
can then be extended to use each tool through its allowlist.

### Slice 13: Evaluation MCP Tool, Agent Identity, and Handoff

Implement chunks 44-47. Evaluation report generation is an MCP tool owned by the Evaluation Agent, and the Evaluation
Agent graph is a separate identity proof that consumes backtest/data/hypothesis evidence.

### Slice 14: Adversarial MCP Tool, Agent Identity, and Handoff

Implement chunks 48-52. First create and prove `adversarial_run_robustness`, then create the Adversarial Agent graph
that uses it, then have the supervisor consume the robustness handoff. Robustness variants remain explicit service/tool
work after the identity boundary is proven.

### Slice 15: Recommendation and Supervisor Synthesis

Implement chunks 53-54. First create the recommendation MCP tool, then extend the Quant Research Supervisor graph so it
synthesizes Data, Quantitative Methods, ML, Hypothesis, Evaluation, and Adversarial artifacts without bypassing the specialist
graphs.

### Slice 16: Supervised Experiment Runner

Implement chunk 55 last. The runner composes the earlier agent-owned artifacts and should not be the first proof of
MCP, LangGraph, any specialist identity, or supervisor correctness.

### Ongoing Validation

Implement chunks 56-59 alongside the slices. Import-boundary tests, MCP/LangGraph contract tests, docs, and
verification should be updated at every evidence checkpoint rather than saved for the end.

## First Release Acceptance Criteria

1. The MCP server exposes `data_get_inventory` and has reproducible first-tool evidence before data-quality/loading tools are complete.
2. The LangGraph Data Agent identity can call `data_get_inventory` through MCP and return a dataset manifest payload/reference before the full Data Agent workflow exists.
3. The MCP server exposes data inventory, data quality, and bounded data-loading tools before strategy/backtest/report tools are complete.
4. The Data Agent LangGraph workflow can be exercised against sample or existing data: health -> inventory -> quality -> ensure/load -> quality.
5. The Quant Research Supervisor identity exists before broad strategy/backtest work and consumes specialist handoffs rather than replacing them.
6. Quantitative Methods, ML, Hypothesis, Evaluation, and Adversarial capabilities are each introduced as MCP tool evidence first, then as separate LangGraph identities, then as supervisor handoffs.
7. Quant Methods Knowledge Base ingestion produces source, chunk, embedding, lexical-index, vector-index, ingestion, method-card, retrieval, and citation-validation artifacts before sophisticated method contracts depend on retrieved evidence.
8. Ingestion does not imply approval: draft method cards are not executable, and sophisticated statistical methods require approved method-card references plus passing citation validation.
9. Knowledge tools reject arbitrary filesystem access, unsupported source types, code execution from documents, and uncited/unsupported claims.
10. The Data Agent LLM control loop emits only typed Data Agent decisions and cannot bypass provider validation, mandatory symbol discovery, tool allowlists, side-effect policy, or loop limits.
11. The Quant Research Supervisor LLM control loop emits only typed supervisor decisions and can reuse allowed tools, request specialist work, block early, or finish through deterministic validation and loop limits.
12. Every tool returns the shared JSON envelope and declares its side-effect class.
13. Every tool declares the owning agent and returns/links the artifact owned by that agent.
14. Every LangGraph agent has a distinct identity, state schema, role policy, output artifact contract, and MCP tool allowlist.
15. `src/trader/` contains no research experiment, agent-tool, MCP schema/definition, or LangGraph agent modules.
16. Missing/incomplete data fails closed or produces Data Agent warnings and downstream Evaluation blockers.
17. Strategy validation happens before any backtest run.
18. Baseline backtest artifacts include reproducible config/provenance, dataset manifest references, data-quality report references, and result summaries.
19. Robustness includes at least slippage sensitivity, fee sensitivity, chronological split, and one concentration check.
20. The final recommendation consumes Evaluation and Adversarial artifacts when available and includes a skeptical verdict with concrete failure analysis.
21. No MCP tool or LangGraph agent can place live orders, mutate broker state, run raw SQL, or bypass existing platform validation.

## Open Decisions

- MCP SDK dependency and version pin: resolved for the server skeleton as `mcp>=1.27.1,<2`.
- LangGraph dependency/version and persistence choice: choose the smallest graph/checkpoint setup that supports agent identity and state without persisting hidden reasoning.
- Persistence shape for first release: `trader.data.EventStore` may provide platform persistence primitives, but research-specific persistence adapters and artifact policies belong in `trader_research`.
- Quant Methods Knowledge Base backend: use Postgres-backed source/chunk/method metadata, PostgreSQL full-text search for
  lexical retrieval, and pgvector or a backend-neutral vector adapter for dense retrieval in the first durable
  implementation. Deterministic embeddings are test doubles only; runtime ingestion requires explicit embedding-provider
  configuration. JSON artifacts remain audit/export records, while approved source registry records and approved method
  cards remain the authority.
- Natural-language planning: both the Data Agent and Quant Research Supervisor need real LLM-backed control. Add the Data
  Agent LLM loop first because its provider-aware tool surface is already complete and bounded. Add the Quant Research
  Supervisor LLM loop later after Data, Quantitative Methods, optional ML, and Hypothesis artifact contracts exist, because its
  job is cross-agent orchestration. Both must use structured output, deterministic routing validation, allowlists, and
  loop limits; MCP tools remain deterministic.
- Generated strategy code: defer until maintained strategies plus validation/reporting are useful.
- Transport: stdio for the server skeleton; HTTP/SSE later only if another client requires it.
