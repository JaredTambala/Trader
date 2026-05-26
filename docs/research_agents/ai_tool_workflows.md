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
Math Coder, ML, Hypothesis, Evaluation, or Adversarial artifacts.

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

## Slice 5: Math Coder MCP Tool Creation

Goal: define and prove the first deterministic Math Coder tool surface before building its graph.

Expected flow:

```text
dataset manifest or fixture reference
  -> math_list_indicator_contracts
  -> math_validate_indicator_contract
```

Owned artifacts:

- indicator metadata
- indicator test report
- statistical-test report, when applicable

Evidence:

- MCP returns maintained indicator contracts without importing arbitrary code.
- Validation fails closed for unsupported indicators or parameter shapes.

## Slice 6: Math Coder Agent Identity

Goal: create the Math Coder LangGraph identity after the first Math Coder MCP tools exist.

Expected flow:

```text
Math Coder graph starts
  -> graph calls allowed Math Coder MCP tools
  -> graph returns indicator metadata/test report artifact references
  -> supervisor records the handoff
```

The Math Coder Agent cannot fetch market data directly or make research verdicts.

## Slice 7: ML MCP Tool Creation

Goal: define model-artifact and feature-artifact contracts before any ML graph tries to plan with them.

Expected flow:

```text
dataset manifest + data-quality report + indicator artifacts
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

Goal: create the first Hypothesis Agent tool after Data, Math Coder, and optional ML ingredient contracts are explicit.

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
