# Getting Started Workflow

This workflow links package tutorials into one safe progression.

1. Install the repository and start local Postgres using [Environment](../environment.md).
2. Learn core configuration and assumptions in the [`trader` tutorial](../../src/trader/docs/tutorial.md).
3. Compose a maintained strategy and risk pipeline in the
   [`trader_standard` tutorial](../../src/trader_standard/docs/tutorial.md).
4. Load the checked-in sample data and run the Postgres-backed reproducible backtest.
5. Inspect the exported result and the canonical event evidence before changing assumptions.
6. Learn the research artifact vocabulary in the
   [`trader_research` tutorial](../../src/trader_research/docs/tutorial.md).
7. If tool integration is required, configure the read-only MCP server and follow the
   [`trader_mcp` tutorial](../../src/trader_mcp/docs/tutorial.md).
8. If evaluating model-backed orchestration, read the qualification status before following the
   [`trader_agents` tutorial](../../src/trader_agents/docs/tutorial.md).

Do not begin with paper trading. Historical success is followed by prospective experiment design, robustness,
walk-forward evaluation, independent review, and a separate operator-controlled paper-candidate process. Several of
those agentic stages remain planned rather than qualified; the [Product State](../product_state.md) is authoritative.
