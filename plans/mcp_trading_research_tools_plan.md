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

- `docs/research_agents/agent_operating_model.md` defines a supervisor hierarchy. This plan should preserve that boundary: Data Agent tools produce dataset manifests and data-quality reports; Math Coder tools produce indicator/stat-test artifacts; ML tools produce feature/model/prediction artifacts; Hypothesis tools produce hypothesis cards; Quant Research Supervisor tools consume those artifacts and produce experiment/comparison/recommendation artifacts; Evaluation and Adversarial tools produce critique and robustness reports.
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
| Data Agent | Data inventory, data quality, explicit load/backfill | `dataset_manifest.json`, `data_quality_report.json`, load result envelopes |
| Math Coder Agent | Indicator/stat-test contract listing and validation | indicator metadata, indicator test reports, statistical-test reports |
| ML Agent | Feature/model artifact registration and summary | feature manifests, model cards, prediction artifacts, drift reports |
| Hypothesis Agent | Hypothesis-card creation from available ingredients | `hypothesis_card.json` |
| Evaluation Agent | Skeptical review of data and research evidence | `evaluation_report.json` |
| Adversarial Agent | Stress tests and robustness attacks | `robustness_report.json` |

No research agent controls the live trading hot path. Promotion remains a human-reviewed proposal.

## LangGraph Identity Model

LangGraph is the identity and orchestration layer for agents. MCP is the tool boundary. The same MCP tool can be callable by multiple agents, but each agent's graph decides whether it is allowed, how inputs are formed, what state is retained, and which artifact must be produced.

| Agent | LangGraph identity requirement | MCP tool access pattern |
| --- | --- | --- |
| Data Agent | Owns `DataAgentState`, dataset-manifest state, quality status, and load policy. | May call only Data Agent MCP tools plus read-only health/config tools. |
| Quant Research Supervisor Agent | Owns `QuantResearchSupervisorState`, request decomposition, handoff ledger, experiment plan state, comparison state, and recommendation synthesis. | May consume specialist artifact references and call Quant Research MCP tools; may request specialist reports through graph handoffs. |
| Evaluation Agent | Owns `EvaluationState` and skeptical critique policy. | May read data/backtest artifacts and call evaluation tools; cannot create new hypotheses or mutate data. |
| Adversarial Agent | Owns `AdversarialState` and robustness attack policy. | May call robustness tools against supplied baseline artifacts; cannot recommend promotion. |
| Hypothesis Agent | Owns `HypothesisState` and hypothesis-card generation policy. | May read known ingredients and prior results; cannot run backtests or make verdicts. |
| Math Coder Agent | Owns `MathCoderState` and indicator/stat-test implementation policy. | May call Math Coder tools for indicator/stat-test artifacts; cannot fetch data or promote strategies. |
| ML Agent | Owns `MLAgentState` and model-artifact policy. | May call ML tools for feature/model/prediction/drift artifacts; cannot produce final trading recommendations. |

The first LangGraph evidence should be the Data Agent graph calling `data_get_inventory` through the MCP client and returning a dataset manifest-style artifact reference or envelope. Do not wait for all planned MCP tools before creating the first LangGraph identity.

## Delivery Principle

Build MCP evidence in thin vertical slices. The first shippable slice is not a full Quant Research runner; it is a working Data Agent MCP surface that can answer data inventory, data quality, and bounded data-loading requests through the same envelope clients will use later.

The intended progression is:

```text
MCP server boots
  -> health/config tool works
  -> Data Agent inventory tool works
  -> Data Agent LangGraph identity uses the inventory tool
  -> Data Agent quality tool works
  -> Data Agent explicit loading/backfill tool works
  -> Quant Research Supervisor identity consumes Data Agent artifacts
  -> Math Coder tool and identity produce indicator/stat-test artifacts
  -> ML tool and identity produce model-artifact references
  -> Hypothesis tool and identity produce hypothesis cards
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
| 5. Data Inventory Service | Not started |  |  |
| 6. Register Data Inventory MCP Tool | Not started |  |  |
| 7. First MCP Tool Evidence | Not started |  |  |
| 8. LangGraph Agent Identity Skeleton | Not started |  |  |
| 9. Data Agent Inventory Graph | Not started |  |  |
| 10. Data Quality Service | Not started |  |  |
| 11. Register Data Quality MCP Tool | Not started |  |  |
| 12. Extend Data Agent Graph for Quality | Not started |  |  |
| 13. Data Ensure/Loading Service | Not started |  |  |
| 14. Register Data Loading MCP Tool | Not started |  |  |
| 15. Extend Data Agent Graph for Loading | Not started |  |  |
| 16. Data MCP and LangGraph Workflow Evidence | Not started |  |  |
| 17. Move Shared Tool Contracts | Not started |  |  |
| 18. Move Research Helpers | Not started |  |  |
| 19. Move Research Tool Modules | Not started |  |  |
| 20. Research Domain Schemas | Not started |  |  |
| 21. Quant Research Supervisor Graph Skeleton | Not started |  |  |
| 22. Supervisor Consumes Data Agent Handoff | Not started |  |  |
| 23. Math Coder Tool Contracts | Not started |  |  |
| 24. Register Math Coder MCP Tools | Not started |  |  |
| 25. Math Coder Agent Graph | Not started |  |  |
| 26. Supervisor Consumes Math Coder Handoff | Not started |  |  |
| 27. ML Artifact Tool Contracts | Not started |  |  |
| 28. Register ML MCP Tools | Not started |  |  |
| 29. ML Agent Graph | Not started |  |  |
| 30. Supervisor Consumes ML Handoff | Not started |  |  |
| 31. Hypothesis Card Service | Not started |  |  |
| 32. Register Hypothesis MCP Tool | Not started |  |  |
| 33. Hypothesis Agent Graph | Not started |  |  |
| 34. Supervisor Consumes Hypothesis Handoff | Not started |  |  |
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

## Proposed Package Shape

```text
src/trader_research/
  __init__.py
  agents.py             # Agent/tool ownership metadata from agent_operating_model.md
  domain.py              # ExperimentPlan, Experiment, StrategyCandidate, reports, verdicts
  contracts.py           # ToolEnvelope, side-effect declarations, shared JSON helpers
  data.py                # Data Agent inventory, manifests, quality, and loading wrappers
  math_tools.py          # Math Coder indicator/stat-test contracts and validation
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
  schemas.py             # MCP-facing request/response models if needed
  adapters.py            # ToolEnvelope <-> MCP response helpers
  settings.py            # Config path, artifact root, read/write policy

src/trader_agents/
  __init__.py
  identities.py          # Agent identities, role policies, and tool allowlists
  state.py               # LangGraph state schemas per agent
  tool_client.py         # MCP client wrappers used by LangGraph nodes
  data_agent.py          # Data Agent graph
  quant_research.py      # Quant Research graph and handoffs
  evaluation_agent.py    # Evaluation Agent graph
  adversarial_agent.py   # Adversarial Agent graph
  hypothesis_agent.py    # Hypothesis-card graph
  math_coder_agent.py    # Math Coder graph
  ml_agent.py            # ML graph

tests/
  test_research_domain.py
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
| `math_list_indicator_contracts` | Math Coder Agent | `read_only` | Return maintained indicator/stat-test contracts and metadata requirements. |
| `math_validate_indicator_contract` | Math Coder Agent | `read_only` | Validate indicator/stat-test parameters and fixture behavior. |
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
| 20. Research Domain Schemas | Define schemas for specialist artifacts and supervisor handoffs: `hypothesis_card.json`, indicator metadata, statistical-test reports, feature manifests, model cards, `ExperimentPlan`, `DataRequirement`, `StrategyCandidate`, `BacktestRunRef`, `evaluation_report.json`, `robustness_report.json`, recommendation reports, and `ResearchVerdict`. Prefer stdlib dataclasses unless validation complexity justifies Pydantic. | `src/trader_research/domain.py`, tests | Schemas serialize to JSON-compatible dicts and preserve agent-owned artifact boundaries. |
| 21. Quant Research Supervisor Graph Skeleton | Add the supervisor LangGraph identity, state, handoff ledger, and empty specialist artifact slots before broad Quant Research tools exist. | `src/trader_agents/quant_research.py`, tests | Supervisor graph can start, record a bounded research request, consume Data Agent artifact references, and mark missing specialist artifacts as blockers. |
| 22. Supervisor Consumes Data Agent Handoff | Add a supervisor node that accepts Data Agent manifest/quality references produced by the Data Agent graph. | `src/trader_agents/quant_research.py`, tests | Supervisor state preserves Data Agent ownership and does not fetch raw data directly. |
| 23. Math Coder Tool Contracts | Implement the first Math Coder service for maintained indicator/stat-test contract listing and validation. | `src/trader_research/math_tools.py`, tests | Unsupported indicators fail closed; maintained indicator metadata and fixture expectations are returned as structured artifacts. |
| 24. Register Math Coder MCP Tools | Expose `math_list_indicator_contracts` and `math_validate_indicator_contract`. | `src/trader_mcp/server.py`, tests | MCP returns Math Coder envelopes with indicator metadata or validation reports. |
| 25. Math Coder Agent Graph | Add LangGraph identity, state, and tool allowlist for the Math Coder Agent. | `src/trader_agents/math_coder_agent.py`, tests | Math Coder graph calls only Math Coder MCP tools and returns indicator/stat-test artifact references. |
| 26. Supervisor Consumes Math Coder Handoff | Add supervisor handoff consumption for Math Coder artifacts. | `src/trader_agents/quant_research.py`, tests | Supervisor state can require, accept, or block on indicator/stat-test evidence without rewriting it. |
| 27. ML Artifact Tool Contracts | Implement initial ML artifact services for feature manifests and model-card/prediction/drift summaries. Do not start with automated training. | `src/trader_research/ml.py`, tests | ML artifact references are validated for required provenance, data inputs, feature definitions, and metrics/warnings. |
| 28. Register ML MCP Tools | Expose `ml_create_feature_manifest` and `ml_summarize_model_artifact`. | `src/trader_mcp/server.py`, tests | MCP returns ML Agent envelopes for feature/model artifact references and rejects incomplete metadata. |
| 29. ML Agent Graph | Add LangGraph identity, state, and tool allowlist for the ML Agent. | `src/trader_agents/ml_agent.py`, tests | ML graph calls only ML MCP tools and returns feature/model/prediction/drift artifact references. |
| 30. Supervisor Consumes ML Handoff | Add supervisor handoff consumption for optional ML artifacts. | `src/trader_agents/quant_research.py`, tests | Supervisor can distinguish hypotheses that require model artifacts from those that do not. |
| 31. Hypothesis Card Service | Implement `hypothesis_create_card` from structured inputs and available ingredient references. | `src/trader_research/hypotheses.py`, tests | Hypothesis cards require mechanism, data requirements, required features, strategy intent, and falsification criteria. |
| 32. Register Hypothesis MCP Tool | Expose `hypothesis_create_card`. | `src/trader_mcp/server.py`, tests | MCP returns a Hypothesis Agent envelope with `hypothesis_card.json` payload/path. |
| 33. Hypothesis Agent Graph | Add LangGraph identity, state, and tool allowlist for the Hypothesis Agent. | `src/trader_agents/hypothesis_agent.py`, tests | Hypothesis graph can read ingredient references and produce hypothesis-card handoffs without running backtests. |
| 34. Supervisor Consumes Hypothesis Handoff | Add supervisor handoff consumption for hypothesis cards. | `src/trader_agents/quant_research.py`, tests | Supervisor can convert accepted hypothesis references into planning state and reject incomplete cards. |
| 35. Strategy Template Catalog | Expose Quant Research strategy-template discovery over maintained `trader_standard` families: `trend_following`, `mean_reversion`, and `bollinger_band` initially. | `src/trader_research/strategies.py`, tests | Tool returns family names, required/optional parameters, defaults, and known constraints. |
| 36. Register Strategy Catalog MCP Tool | Expose `research_list_strategy_templates`. | `src/trader_mcp/server.py`, tests | MCP returns maintained strategy templates with `agent_owner=Quant Research Supervisor Agent` and without importing arbitrary strategy code. |
| 37. Strategy Candidate Validation | Implement Quant Research validation for existing maintained strategies first. Defer generated-code candidates until the maintained strategy path is stable. | `src/trader_research/strategies.py`, tests | Unsupported strategy families fail closed; maintained strategies can be instantiated on deterministic fixtures. |
| 38. Register Strategy Validation MCP Tool | Expose `research_validate_strategy_candidate`. | `src/trader_mcp/server.py`, tests | MCP validation fails closed for unsupported families and returns fixture validation evidence for maintained strategies. |
| 39. Supervisor Strategy Planning Graph | Extend the supervisor graph to call strategy catalog/validation tools through MCP using Data, Math Coder, ML, and Hypothesis handoffs. | `src/trader_agents/quant_research.py`, tests | Supervisor creates an experiment-plan state only from specialist artifact references and validated strategy candidates. |
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
| 54. Quant Research Supervisor Synthesis Graph | Extend the supervisor graph to synthesize Data, Math Coder, ML, Hypothesis, Evaluation, and Adversarial artifact handoffs into recommendation state. | `src/trader_agents/quant_research.py`, tests | Supervisor synthesizes artifacts but does not bypass specialist graphs or MCP tools. |
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

Evidence target:

```text
Quant Research Supervisor graph starts
  -> consumes Data Agent manifest/quality references
  -> records missing Math Coder, ML, Hypothesis, Evaluation, and Adversarial artifacts as blockers
```

### Slice 5: Math Coder MCP Tool Creation

Implement chunks 23-24. This creates and proves the first Math Coder MCP tools before the Math Coder LangGraph identity
exists.

Evidence target:

```text
math_list_indicator_contracts
math_validate_indicator_contract
  -> returns indicator metadata or validation report
  -> declares agent_owner = Math Coder Agent
```

### Slice 6: Math Coder Agent Identity and Handoff

Implement chunks 25-26. This proves that the Math Coder graph has its own identity and that the supervisor consumes,
but does not rewrite, Math Coder artifacts.

### Slice 7: ML MCP Tool Creation

Implement chunks 27-28. This creates feature/model artifact tools before any ML graph exists. Training is deliberately
not the first ML capability; artifact contracts and provenance come first.

### Slice 8: ML Agent Identity and Handoff

Implement chunks 29-30. This proves that the ML graph has its own identity and that the supervisor can track optional
model dependencies separately from non-ML hypotheses.

### Slice 9: Hypothesis MCP Tool Creation

Implement chunks 31-32 after Data, Math Coder, and optional ML ingredient contracts are explicit. The first hypothesis
tool produces structured, falsifiable `hypothesis_card.json` artifacts.

### Slice 10: Hypothesis Agent Identity and Handoff

Implement chunks 33-34. This proves that the Hypothesis Agent can produce candidate ideas while the supervisor retains
responsibility for planning, validation, and verdicts.

### Slice 11: Quant Research Strategy Planning Tools

Implement chunks 35-39. Strategy template discovery, candidate validation, and supervisor planning occur only after
specialist artifact handoffs exist.

Evidence target:

```text
hypothesis_card.json + Data/Math/ML artifact references
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
synthesizes Data, Math Coder, ML, Hypothesis, Evaluation, and Adversarial artifacts without bypassing the specialist
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
6. Math Coder, ML, Hypothesis, Evaluation, and Adversarial capabilities are each introduced as MCP tool evidence first, then as separate LangGraph identities, then as supervisor handoffs.
7. Every tool returns the shared JSON envelope and declares its side-effect class.
8. Every tool declares the owning agent and returns/links the artifact owned by that agent.
9. Every LangGraph agent has a distinct identity, state schema, role policy, output artifact contract, and MCP tool allowlist.
10. `src/trader/` contains no research experiment, agent-tool, MCP schema/definition, or LangGraph agent modules.
11. Missing/incomplete data fails closed or produces Data Agent warnings and downstream Evaluation blockers.
12. Strategy validation happens before any backtest run.
13. Baseline backtest artifacts include reproducible config/provenance, dataset manifest references, data-quality report references, and result summaries.
14. Robustness includes at least slippage sensitivity, fee sensitivity, chronological split, and one concentration check.
15. The final recommendation consumes Evaluation and Adversarial artifacts when available and includes a skeptical verdict with concrete failure analysis.
16. No MCP tool or LangGraph agent can place live orders, mutate broker state, run raw SQL, or bypass existing platform validation.

## Open Decisions

- MCP SDK dependency and version pin: resolved for the server skeleton as `mcp>=1.27.1,<2`.
- LangGraph dependency/version and persistence choice: choose the smallest graph/checkpoint setup that supports agent identity and state without persisting hidden reasoning.
- Persistence shape for first release: `trader.data.EventStore` may provide platform persistence primitives, but research-specific persistence adapters and artifact policies belong in `trader_research`.
- Natural-language planning: start with structured input and a narrow parser; add LLM structured-output planning only after deterministic services are tested.
- Generated strategy code: defer until maintained strategies plus validation/reporting are useful.
- Transport: stdio for the server skeleton; HTTP/SSE later only if another client requires it.
