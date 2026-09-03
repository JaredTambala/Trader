# Trader System Architecture

Trader is one Python distribution containing six bounded packages and repository-level application entrypoints.

## Dependency map

```text
trader_standard -----> trader <----- trader_mlflow
       ^                 ^                 ^
       |                 |                 |
       +------ trader_research ------------+
                       ^
                       |
                   trader_mcp
                       ^
                       |
                  trader_agents
```

`trader` is the core dependency root. `trader_standard` implements its extension contracts. `trader_research` composes
core and maintained behavior into deterministic evidence-producing services. `trader_mcp` adapts those services to a
policy-aware protocol boundary. `trader_agents` reaches platform capabilities only through MCP. `trader_mlflow` bridges
MLflow pyfunc inference into core prediction contracts and may be composed by research infrastructure.

## State authorities

| State | Authority |
| --- | --- |
| Runtime bars, runs, cycles, orders, fills, positions, metrics, and halts | Trader Postgres event store and broker truth where explicitly defined |
| Research artifacts, sessions, evidence, and accepted public decisions | canonical research Postgres store |
| In-progress agent execution position | separate LangGraph Postgres checkpoint store |
| Model and agent observation/evaluation projections | MLflow, non-authoritative unless a specific artifact contract says otherwise |
| Candidate source under construction | isolated disposable coding workspace until packaged/admitted |

An agent checkpoint is not research evidence. An MLflow trace is not a canonical decision. A filesystem export is not
the canonical backtest record. Every transition between these stores uses a typed identity and validation boundary.

## Execution paths

The trading hot path is market data to strategy, risk, broker, portfolio, and event evidence. It contains no LLM or
research agent. The research capability path may invoke deterministic backtests but cannot mutate a live/paper broker.
The agent path adds model interpretation and routing above role-scoped MCP tools; it never imports runtime internals.

## Safety and evidence principles

- Normalize configuration, provider payloads, database rows, MCP envelopes, and model JSON at their boundary.
- Keep deterministic decisions separate from effects such as clocks, persistence, network calls, Docker, and models.
- Preserve immutable input/output identity and append-only lineage.
- Fail closed on missing authority, evidence, state reconciliation, model validity, or budget.
- Keep protected evaluation data out of authoring and tuning context.
- Require operator action for scope expansion, approvals, and any future paper-candidate promotion.

For internal topology, use the owning package's architecture page. For what is currently implemented and qualified, use
[Product State](product_state.md).
