# Research MCP Operations

This document covers local operation for the research MCP server and related verification commands.

## Start The Server

The MCP server uses stdio:

```bash
uv run python -m trader_mcp.server
```

For an MCP client, configure:

```text
command: uv
args: ["run", "python", "-m", "trader_mcp.server"]
cwd: /home/jared/Trader
```

The server should start and list tools without a valid database, broker credential, trader runtime YAML, or LLM
configuration. Runtime failures belong inside the affected tool envelope.

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `TRADER_MCP_TRANSPORT` | `stdio` | MCP transport. Only stdio is supported. |
| `TRADER_MCP_ARTIFACT_ROOT` | `artifacts/research` | Root for local research artifacts. |
| `TRADER_MCP_TRADER_CONFIG_PATH` | empty | Optional trader YAML for execution-plane dependencies. |
| `TRADER_MCP_TOOL_ENV_PATH` | `.env` | Optional dotenv file loaded lazily for trader YAML expansion. |
| `TRADER_MCP_ALLOW_DATA_LOADING` | `false` | Enables explicit sample/backfill mutation. |
| `TRADER_MCP_ALLOW_BACKTESTS` | `false` | Enables `research_run_backtest` execution. |
| `TRADER_MCP_ALLOW_BROKER_MUTATION` | `false` | Must remain false for research MCP tools. |
| `TRADER_MCP_ALLOW_RAW_SQL` | `false` | Must remain false for research MCP tools. |

Quantitative Methods knowledge tools expect a configured knowledge store for production use. Postgres-backed knowledge
storage is the normal runtime path; tests may inject compatibility stores.

## Typical Local Checks

Use focused checks after changing docs, MCP registrations, agent identities, or artifact contracts:

```bash
uv run pytest tests/test_agent_identities.py tests/test_mcp_server.py tests/test_research_domain.py -q
uv run pytest tests/test_research_agent_docs.py -q
uv run ruff check tests
python -m compileall -q src/trader_research src/trader_mcp src/trader_agents
```

For a broader MCP registration check:

```bash
uv run pytest tests/test_mcp_tools.py tests/test_mcp_data_workflow.py tests/test_mcp_quant_methods_tools.py tests/test_mcp_strategy_tools.py tests/test_mcp_backtest_tools.py tests/test_mcp_evaluation_tools.py -q
```

## Operational Safety

- Inspect `mcp_get_config` before running local-mutating tools.
- Keep `TRADER_MCP_ALLOW_BACKTESTS=false` unless intentionally running local backtests.
- Keep `TRADER_MCP_ALLOW_DATA_LOADING=false` unless intentionally loading sample or backfilled data.
- Do not expose raw SQL or broker-mutating operations through research MCP.
- Treat artifacts under `artifacts/research/` as research evidence, not as live trading controls.
