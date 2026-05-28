# Slice 3 Test Conditions: Data Tool Workflow and Data Agent Graph

## Purpose

Slice 3 covers chunks 10-16 of the MCP trading research tools plan. It extends the proven inventory-only Data Agent path into a complete deterministic data workflow:

```text
mcp_health
mcp_get_config
data_get_inventory
data_summarize_quality
data_ensure_loaded
data_summarize_quality
Data Agent graph completes the same workflow through MCP tools only
```

This document is the intermediate acceptance contract for the slice. Do not mark a Slice 3 chunk `Done` in `plans/mcp_trading_research_tools_plan.md` unless the relevant conditions below are covered by tests, docs, or reproducible command output.

## Pre-Slice Checkpoint

- Verify the completed Slice 2 work before adding Slice 3 behavior:
  - `uv run pytest tests/test_langgraph_agents.py tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py`
  - `uv run ruff check src/trader/market_data_queries.py src/trader_research src/trader_mcp src/trader_agents tests/test_langgraph_agents.py tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py tests/support`
  - `uv run python -c "from trader_agents.data_agent import build_data_agent_inventory_graph"`
  - `git diff --check`
- Commit Slice 2 as its own checkpoint before implementing Slice 3.
  - Commit message: `Add Data Agent LangGraph inventory graph`

## Global Slice Conditions

- No Slice 3 production code may expose raw SQL, arbitrary code execution, broker mutation, live trading, backtests, or LLM calls.
- `trader_research`, `trader_mcp`, and `trader_agents` must not embed ad hoc SQL. SQL remains behind typed core platform helpers such as `trader.market_data_queries` or future typed functions in `trader.data_quality`.
- All MCP tool outputs must use the shared `ToolEnvelope` through `CallToolResult` fields: `content`, `structuredContent`, and `isError`.
- All new source functions and classes must use Google-style docstrings.
- Test fixtures use DuckDB and checked-in sample CSV data. Real Postgres data is optional manual evidence only and must not be required for automated tests.
- `TRADER_MCP_ALLOW_DATA_LOADING=false` remains the default local policy. Tests that exercise mutating sample-load behavior must construct an explicit environment with data loading allowed.
- Prompt-injection defense is enforced by typed inputs, allowlisted tool names, bounded requests, parameterized core queries, and treating all symbols, sources, paths, and config values as data.

## Chunk 10 Conditions: Data Quality Service

- Add a direct Data Agent service, expected as `data_summarize_quality`, that accepts bounded symbols, asset class, timeframe, start, end, and optional source.
- The service must return a read-only `ToolEnvelope` owned by Data Agent with embedded `data_quality_report` data. Because the tool is read-only, it must not write `data_quality_report.json` in this slice.
- The report must include stable identifiers and enough detail for later graph handoff:
  - `report_id`
  - normalized `asset_class`, `symbols`, `timeframe`, and requested window
  - per-symbol bar totals
  - missing gap counts
  - expected/session gap counts when the core platform can classify them
  - max gap seconds
  - report-level `complete`
  - warnings for missing rows or detected missing gaps
- Required service tests:
  - sample `DEMO` 1 minute data returns `ok=true`, `agent_owner="Data Agent"`, `side_effect="read_only"`, total bars `12`, and no missing gaps for the exact sample window
  - a fixture with a removed minute reports a missing gap and `complete=false`
  - missing symbol returns `ok=true`, `complete=false`, zero bars, and warnings
  - invalid symbols, unsupported asset class, invalid timeframe, and `end < start` return `ok=false` validation envelopes
  - `NoOpEventStore` returns `event_store_connection_unavailable`

## Chunk 11 Conditions: Register Data Quality MCP Tool

- Register exactly one new read-only MCP tool: `data_summarize_quality`.
- Tool arguments are JSON-native and follow the same parsing rules as `data_get_inventory`.
- Bad MCP inputs return Data Agent `validation_error` envelopes instead of escaping exceptions.
- `mcp_get_config` must include `data_summarize_quality` with `agent_owner="Data Agent"` and `side_effect="read_only"`.
- Required MCP tests:
  - `server.list_tools()` includes support tools, `data_get_inventory`, and `data_summarize_quality`
  - direct server call on sample data returns the embedded quality report
  - invalid datetime and invalid timeframe return `isError=true` with structured validation errors
  - config still excludes broker-mutating, raw SQL, backtest, and data-loading tools at this point

## Chunk 12 Conditions: Data Agent Quality Graph

- Extend the Data Agent graph layer without giving it direct imports from `trader.data`, `trader.market_data_queries`, `trader_research.data`, or `trader_mcp.server`.
- Add a quality workflow that calls MCP tools in this order:
  - `data_get_inventory`
  - `data_summarize_quality`
- Data Agent state must preserve:
  - dataset manifest
  - quality report
  - last MCP result or envelope for debugging
  - warnings
  - structured errors
  - ordered `called_tools`
- Required graph tests:
  - graph succeeds against the test-only stdio MCP sample server
  - graph refuses to call `data_summarize_quality` when it is removed from the allowlist
  - failed quality envelopes are preserved in state and stop the workflow
  - package boundary scan still finds no forbidden platform or MCP server imports in `src/trader_agents`

## Chunk 13 Conditions: Data Ensure/Loading Service

- Add a direct Data Agent service, expected as `data_ensure_loaded`, with explicit modes:
  - `existing`: inspect only and fail if the requested data is incomplete
  - `sample`: load a checked-in sample CSV into the supplied event store
  - `backfill`: plan or run bounded core backfill behavior through existing platform services
- The tool class is `local_mutating` because it can write data, even when a specific request is dry-run or inspect-only.
- Every request must be bounded by symbols, asset class, timeframe, start, and end. Empty symbols, more than 20 symbols, unsupported asset classes, invalid timeframes, and `end < start` must fail validation.
- Mutating modes must require an explicit `allow_data_loading=True` service policy. Without that policy, mutating modes return a failed envelope with code `data_loading_not_allowed`.
- Backfill mode must default to dry-run planning in automated tests. Non-dry-run backfill requires explicit permission and a bounded config path or injected runner.
- Required service tests:
  - `existing` succeeds when sample data already covers the requested window
  - `existing` fails with `data_missing` when rows or coverage are incomplete
  - `sample` refuses to run when loading is not allowed
  - `sample` loads `examples/data/demo_stock_1min.csv` when loading is allowed and returns load evidence plus a post-load manifest
  - `backfill` dry-run returns a bounded plan without network calls or writes
  - unavailable event store returns `event_store_connection_unavailable`

## Chunk 14 Conditions: Register Data Loading MCP Tool

- Register `data_ensure_loaded` after the service tests pass.
- `mcp_get_config` must include the tool with `agent_owner="Data Agent"` and `side_effect="local_mutating"`.
- Config safety output must distinguish registration from runtime permission:
  - data-loading tool registered: true
  - data-loading mutation allowed: value from `TRADER_MCP_ALLOW_DATA_LOADING`
  - broker-mutating tools registered: false
  - raw SQL tools registered: false
  - backtest tools registered: false
- Required MCP tests:
  - default local environment rejects mutating sample-load requests
  - explicit test environment with `allow_data_loading=True` can sample-load into an injected DuckDB store
  - dry-run backfill returns a plan envelope and does not write rows
  - invalid inputs return structured validation errors
  - no broker, raw SQL, or backtest tool names appear in `server.list_tools()`

## Chunk 15 Conditions: Data Agent Loading Graph

- Extend the Data Agent graph to support a full data workflow while preserving policy in state.
- The graph may call `data_ensure_loaded` only when state policy permits data loading.
- Required graph call order for the full workflow:
  - `data_get_inventory`
  - `data_summarize_quality`
  - `data_ensure_loaded`
  - `data_summarize_quality`
- Required graph tests:
  - graph refuses loading when state policy does not allow mutation and does not call `data_ensure_loaded`
  - graph succeeds with sample-load mode when policy allows mutation
  - final state includes initial inventory, initial quality report, load result, final quality report, warnings, errors, and ordered `called_tools`
  - graph still uses only MCP client calls and never imports platform data/query modules directly

## Chunk 16 Conditions: Full MCP and LangGraph Evidence

- Add test-only stdio evidence support for the complete workflow with DuckDB sample data.
- Add a reproducible evidence test that:
  - starts a test-only stdio MCP server
  - lists tools
  - calls `mcp_health`
  - calls `mcp_get_config`
  - calls `data_get_inventory`
  - calls `data_summarize_quality`
  - calls `data_ensure_loaded` in sample or dry-run mode
  - calls `data_summarize_quality` again
  - verifies every `content[0].text` JSON parses back to the same `structuredContent`
- Add a Data Agent graph evidence test that completes the same workflow through the MCP client and asserts final state artifacts.
- Update `docs/research_agents/mcp_trading_research_tools.md` with the exact pytest command and the asserted envelope fields.
- Mark chunks 10-16 `Done` only when the evidence tests and docs are in place.

## Final Slice Verification

Run these commands before considering Slice 3 complete:

```bash
uv run pytest tests/test_data_quality_service.py tests/test_data_ensure_loaded.py tests/test_mcp_data_workflow.py tests/test_langgraph_data_workflow.py tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py
uv run ruff check src/trader/market_data_queries.py src/trader/data_quality.py src/trader_research src/trader_mcp src/trader_agents tests/test_data_quality_service.py tests/test_data_ensure_loaded.py tests/test_mcp_data_workflow.py tests/test_langgraph_data_workflow.py tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py tests/support
uv run python -c "import trader_mcp; import trader_mcp.server as s; s.create_server()"
uv run python -c "from trader_agents.data_agent import build_data_agent_inventory_graph"
git diff --check
```

## Out of Scope for Slice 3

- LLM-backed planning or prompting.
- Quant Research Supervisor graph work.
- Strategy generation, strategy validation, backtests, evaluation reports, robustness reports, or recommendations.
- Broker-mutating tools or live trading controls.
- Raw SQL tools or user-provided SQL.
- Requiring the developer's real Postgres database for automated tests.
