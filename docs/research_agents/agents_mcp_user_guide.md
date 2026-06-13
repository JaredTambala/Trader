# Agents and MCP User Guide

This guide explains the current research-agent MCP surface, how to run it locally, what each available tool does,
and which agent features are planned next. It is a user-facing companion to the implementation notes in
[mcp_trading_research_tools.md](mcp_trading_research_tools.md).

## Current Scope

The current MCP server is a deterministic local research-tool server. It exposes support tools plus a Data Agent
workflow for bounded market-data inspection and explicit data loading. The LangGraph layer also includes a deterministic
Quant Research Supervisor skeleton that consumes Data Agent artifact handoffs and records missing specialist evidence
as blockers; it does not expose new MCP tools yet.

Available tools:

| Tool | Owner | Side effect | Purpose |
| --- | --- | --- | --- |
| `mcp_health` | MCP Server | `read_only` | Confirm the server is running and list registered tools. |
| `mcp_get_config` | MCP Server | `read_only` | Return server settings, registered tool metadata, and safety policy. |
| `data_discover_symbols` | Data Agent | `read_only` | Discover or validate provider-scoped market-data symbols. |
| `data_get_inventory` | Data Agent | `read_only` | Return a dataset manifest for bounded bar data. |
| `data_summarize_quality` | Data Agent | `read_only` | Return a quality report with bar counts, missing gaps, and completeness. |
| `data_ensure_loaded` | Data Agent | `local_mutating` | Inspect existing data, sample-load checked-in data, or run/plan bounded backfill. |

Current safety boundaries:

- No raw SQL tool is exposed.
- No broker-mutating or live-trading tool is exposed.
- No backtest tool is exposed through MCP yet.
- No LLM call is made by the MCP server. The optional Data Agent LLM policy graph runs outside MCP and calls only
  validated Data Agent MCP tools.
- `TRADER_MCP_ALLOW_DATA_LOADING=false` is the default policy, so sample-loading requests are rejected unless
  explicitly enabled.

## Start The MCP Server

The MCP server runs over stdio and reads local defaults from an ignored `local.env` file. Create it from the tracked
[../../env.template](../../env.template):

```bash
cp env.template local.env
```

See [../../README_ENV.md](../../README_ENV.md) for the full local environment setup, including Data Agent LLM provider
configuration.

```bash
uv run python -m trader_mcp.server
```

For an MCP client, configure a stdio server with:

```text
command: uv
args: ["run", "python", "-m", "trader_mcp.server"]
cwd: /home/jared/Trader
```

The MCP server is the control plane. It must be able to start, list tools, and return health/config without a valid
database, broker credential, or trader runtime YAML. Tool execution is the execution plane. Execution is lazy and should
know only typed requests, injected dependencies, explicit policy, and runtime config needed to perform the tool call.

Local MCP control-plane policy and tool execution wiring are controlled by environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `TRADER_MCP_TRANSPORT` | `stdio` | Only stdio is supported right now. |
| `TRADER_MCP_ARTIFACT_ROOT` | `artifacts/research` | Reserved root for future artifacts. |
| `TRADER_MCP_TRADER_CONFIG_PATH` | empty | Optional execution-plane trader YAML config used by data tools to build an event store. |
| `TRADER_MCP_TOOL_ENV_PATH` | `.env` | Optional execution-plane dotenv file loaded lazily before the trader YAML is built. |
| `TRADER_MCP_ALLOW_DATA_LOADING` | `false` | Enables local sample-load and non-dry-run loading behavior when true. |
| `TRADER_MCP_ALLOW_BROKER_MUTATION` | `false` | Must stay false; broker-mutating tools are not registered. |
| `TRADER_MCP_ALLOW_RAW_SQL` | `false` | Must stay false; raw SQL tools are not registered. |
| `TRADER_MCP_ALLOW_BACKTESTS` | `false` | Backtest tools are not registered yet. |

If `TRADER_MCP_TRADER_CONFIG_PATH` is empty, production server calls use `NoOpEventStore`. Data tools still return
normal envelopes, but inventory and quality calls fail with `event_store_connection_unavailable` because there is no
queryable store. Tests inject DuckDB stores for reproducible evidence.

If `TRADER_MCP_TRADER_CONFIG_PATH` points at a YAML containing placeholders such as `${PG_PORT}` or
`${ALPACA_API_KEY}`, set `TRADER_MCP_TOOL_ENV_PATH` to the runtime dotenv file that supplies those values. A missing or
invalid execution-plane config should appear only as a failed Data Agent envelope from the affected tool. It should not
break `mcp_health`, `mcp_get_config`, or tool listing.

## Envelope Format

Every tool returns the shared `ToolEnvelope` through the MCP `CallToolResult` fields:

- `content[0].text`: pretty JSON text for clients that only read text content.
- `structuredContent`: the same envelope as structured JSON.
- `isError`: `true` when `structuredContent.ok` is false.

Important envelope fields:

| Field | Meaning |
| --- | --- |
| `ok` | Whether the tool completed successfully. |
| `command` | Stable tool name, such as `data_get_inventory`. |
| `agent_owner` | Owning agent or support boundary. |
| `side_effect` | Declared side-effect class. |
| `data` | Tool-specific structured payload. |
| `warnings` | Non-fatal quality or coverage warnings. |
| `errors` | Structured fatal errors when `ok=false`. |

## Data Agent Workflow

The intended current workflow is:

```text
mcp_health
mcp_get_config
data_get_inventory
data_summarize_quality
data_ensure_loaded
data_summarize_quality
```

Use `mcp_health` first to confirm the server is reachable. Use `mcp_get_config` next to inspect registered tools and
runtime policy. Then run inventory and quality before attempting `data_ensure_loaded`.

### Inventory Request

`data_get_inventory` accepts bounded market-data inputs:

```json
{
  "symbols": ["DEMO"],
  "asset_class": "stocks",
  "timeframe": "1Min",
  "start": "2026-01-20T12:00:00Z",
  "end": "2026-01-20T12:11:00Z"
}
```

Optional field:

```json
{
  "source": "sample"
}
```

Successful output includes `data.dataset_manifest` with:

- stable `dataset_id`
- normalized `asset_class`, `symbols`, `timeframe`, and requested window
- `source_filter`
- `total_rows`
- report-level `complete`
- per-symbol row counts, first/last timestamps, and source counts

### Quality Request

`data_summarize_quality` uses the same request shape as inventory. Successful output includes
`data.data_quality_report` with:

- stable `report_id`
- normalized request fields
- total bars
- per-symbol bar counts
- missing gap counts
- expected/session gap counts when classified
- max gap seconds
- report-level `complete`
- warnings for missing rows or detected gaps

The quality tool is read-only and does not write `data_quality_report.json`.

### Ensure Loaded Request

`data_ensure_loaded` uses the same bounded fields plus `mode` and optional `dry_run`:

```json
{
  "symbols": ["DEMO"],
  "asset_class": "stocks",
  "timeframe": "1Min",
  "start": "2026-01-20T12:00:00Z",
  "end": "2026-01-20T12:11:00Z",
  "mode": "existing",
  "dry_run": true
}
```

Supported modes:

| Mode | Behavior |
| --- | --- |
| `existing` | Inspect only. Succeeds only if the requested data is already complete. |
| `sample` | Load `examples/data/demo_stock_1min.csv` into the supplied event store when data loading is allowed. |
| `backfill` | Return a bounded dry-run plan by default, or run platform backfill when loading is allowed and a bounded config path or injected runner is available. |

Even though `data_ensure_loaded` is always declared `local_mutating`, runtime mutation is separately controlled by
policy. With default local settings, `mode="sample"` returns a failed envelope with `code="data_loading_not_allowed"`.
Non-dry-run `mode="backfill"` is also rejected unless `TRADER_MCP_ALLOW_DATA_LOADING=true`.

For real external stock backfill through MCP:

1. Set `TRADER_MCP_TRADER_CONFIG_PATH` to a trader YAML config that contains the event-store and Alpaca settings.
2. Set `TRADER_MCP_TOOL_ENV_PATH` to the runtime dotenv file that supplies any YAML substitutions.
3. Set `TRADER_MCP_ALLOW_DATA_LOADING=true`.
4. Call `data_ensure_loaded` with `mode="backfill"` and `dry_run=false`.
5. Call `data_summarize_quality` again on the same bounded request.

The tool runs the core `MarketDataBackfillRunner` through the Data Agent service boundary and returns load evidence
including `rows_loaded`, `runner_result`, `pre_load_manifest`, `post_load_manifest`, and `post_load_quality_report`.
This is the preferred path; do not bypass MCP with a direct backfill call when using the agent workflow.

## Data Agent Graphs

The `trader_agents` package currently provides deterministic LangGraph Data Agent graphs that call MCP tools rather
than importing platform data modules directly.

Current graph builders:

| Builder | Workflow |
| --- | --- |
| `build_data_agent_inventory_graph` | `data_get_inventory` |
| `build_data_agent_quality_graph` | `data_get_inventory -> data_summarize_quality` |
| `build_data_agent_workflow_graph` | `data_get_inventory -> data_summarize_quality -> data_ensure_loaded -> data_summarize_quality` |

The graph state preserves:

- Data Agent identity and MCP tool allowlist
- initial inventory request
- quality and ensure-loaded requests
- data-loading policy
- last MCP result and envelope
- dataset manifest
- initial/final quality reports
- load result
- warnings, structured errors, and ordered `called_tools`

The full workflow graph refuses to call `data_ensure_loaded` unless state policy has `allow_data_loading=true`.

## Quant Research Supervisor Skeleton

The initial supervisor graph is available through:

```python
from trader_agents.quant_research import build_quant_research_supervisor_graph, data_agent_handoffs_from_state
from trader_agents.state import build_quant_research_supervisor_initial_state
```

Current behavior:

- records a bounded research request
- accepts Data Agent `dataset_manifest` and `data_quality_report` handoffs
- preserves Data Agent ownership and provenance
- stores a handoff ledger and specialist artifact slots
- marks missing required specialist artifacts as structured blockers
- keeps `called_tools` empty because supervisor MCP tool calls are not part of this slice

The supervisor consumes artifact references or structured summaries only. It does not fetch raw market data, call Data
Agent MCP tools directly, run backtests, call an LLM, or mutate broker state.

## Reproducible Evidence

Run the current MCP and LangGraph evidence tests with:

```bash
uv run pytest tests/test_data_quality_service.py tests/test_data_ensure_loaded.py tests/test_mcp_data_workflow.py tests/test_langgraph_data_workflow.py tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py
uv run pytest tests/test_research_contracts.py tests/test_tool_contracts.py tests/test_research.py tests/test_research_tools.py tests/test_research_domain.py tests/test_quant_research_supervisor.py tests/test_supervisor_data_handoff.py tests/test_package_boundaries.py
```

Useful focused checks:

```bash
uv run pytest tests/test_mcp_data_workflow.py
uv run pytest tests/test_langgraph_data_workflow.py
uv run pytest tests/test_quant_research_supervisor.py tests/test_supervisor_data_handoff.py
uv run python -c "import trader_mcp; import trader_mcp.server as s; s.create_server()"
uv run python -c "from trader_agents.data_agent import build_data_agent_inventory_graph"
uv run python -c "from trader_agents.quant_research import build_quant_research_supervisor_graph"
```

## Current Limitations

The current user-facing workflow is intentionally narrow:

- Data tools operate on bounded bar requests only.
- Automated evidence uses DuckDB and checked-in sample CSV data.
- Real Postgres-backed data inspection requires a valid trader config path and reachable event store.
- Backfill mode is dry-run planning unless `TRADER_MCP_ALLOW_DATA_LOADING=true` and a bounded config path or injected
  runner is provided.
- Data Agent outputs are embedded in envelopes; persisted research artifacts are planned but not part of the current
  MCP workflow.
- The Quant Research Supervisor is an orchestration skeleton only. Math Coder, ML, Hypothesis, Evaluation, and
  Adversarial graphs are not implemented yet.

## Upcoming Features

Planned work after the current Data Agent slice:

| Area | Planned capability |
| --- | --- |
| Shared contracts | Move remaining legacy tool contracts into the research package boundary. |
| Research helpers | Move research helper modules out of the core runtime package where appropriate. |
| Quant Research Supervisor | Extend the skeleton to request specialist work and later synthesize evidenced recommendations. |
| Math Coder Agent | List and validate indicator/stat-test contracts. |
| ML Agent | Register and summarize feature, model, prediction, and drift artifacts. |
| Hypothesis Agent | Create explicit hypothesis-card artifacts from known ingredients. |
| Strategy research | List templates and validate strategy candidates before backtesting. |
| Backtest tools | Add bounded research backtest/result lookup tools when allowed by policy. |
| Evaluation Agent | Produce skeptical review reports from data and research evidence. |
| Adversarial Agent | Run robustness and stress-test workflows for candidate strategies. |
| Recommendations | Render conservative recommendation reports for human review. |

Broker mutation and live trading controls remain out of scope for the research-agent MCP surface.
