# MCP and LangGraph Research Tools

This document is the active, iterative implementation companion for the MCP/LangGraph research-agent work.

Update it in the same change as each tool or graph slice:

- first MCP tool evidence
- Data Agent inventory, quality, and loading workflows
- LangGraph agent identity evidence
- Quant Research Supervisor handoff and synthesis evidence
- Math Coder, ML, Hypothesis, Evaluation, and Adversarial tool/identity evidence
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

The server reads portable, non-secret local configuration from `local.env`: environment label, transport, artifact
root, and capability policy flags. Static identifiers such as server name, tool names, and tool descriptions stay in
Python metadata under `trader_mcp.constants`.

The server currently registers only read-only support tools:

- `mcp_health`
- `mcp_get_config`

Data Agent tools are intentionally not registered until chunks 5 and 6. No broker tools, raw SQL tools, data-loading
tools, backtest tools, resources, prompts, or LangGraph workflows are exposed by this skeleton server.

## Data Inventory Service

Chunk 5 adds the direct `trader_research.data.get_data_inventory` service only. It calls typed, validating core
market-data query helpers in `trader.market_data_queries`, which own the fixed table selection and parameterized SQL
against the platform `EventStore.connection()` read path. The research and MCP layers must not embed raw SQL, table
names, or direct `.execute(...)` calls. The service returns a Data Agent `ToolEnvelope` with an embedded
`dataset_manifest` payload. The manifest includes a stable dataset ID, asset class, symbols, timeframe, requested
window, source filter, total rows, completeness flag, and per-symbol row/source coverage.

`data_get_inventory` is not exposed over MCP until chunk 6. This chunk does not load data, backfill data, write
artifacts, run data-quality checks, run backtests, expose SQL tools, or add LangGraph workflows.
