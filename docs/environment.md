# Environment And Local Services

This repository uses local env files for machine-specific runtime settings. Do not commit populated env files.

## `local.env`

`local.env` is read by the local MCP research server and Data Agent LLM policy runtime. It is ignored by git.

Treat `local.env` as control-plane configuration. It should contain MCP transport, tool registration policy, runtime
permission gates, and agent/LLM settings. It should not contain broker, Postgres, or Alpaca secrets that are consumed
by trader runtime YAML files.

Do not try to make `local.env` and `.env` share responsibility for the same runtime. Duplicated-looking values are fine
when they preserve separation of concerns. Prefer explicit duplication over hidden coupling between MCP startup and
tool execution.

Create it from the tracked template:

<!-- verified: integration:configuration tests/test_config.py tests/test_agent_runtime_foundation.py -->
```bash
cp env.template local.env
```

Then edit `local.env` for your machine.

## Safe Defaults

The template keeps mutating or external capabilities disabled:

- `TRADER_MCP_ALLOW_BROKER_MUTATION=false`
- `TRADER_MCP_ALLOW_RAW_SQL=false`
- `TRADER_MCP_ALLOW_SYMBOL_PROVIDER_DISCOVERY=false`
- `TRADER_MCP_ALLOW_DATA_LOADING=false`
- `TRADER_MCP_ALLOW_BACKTESTS=false`

Keep broker mutation and raw SQL disabled. Enable provider symbol discovery or data loading only for a bounded local workflow where you understand the side effects.

## Agent LLM

The active development profile uses an exact digest of local Ollama `lfm2.5:8b`. The package profile, environment, and
served model must agree. `local.env` may contain:

<!-- verified: integration:local-model tests/test_agentic_qualification.py -->
```bash
TRADER_AGENTS_LLM_PROVIDER=ollama
TRADER_AGENTS_LLM_MODEL=lfm2.5:8b
TRADER_AGENTS_LLM_BASE_URL=http://localhost:11434
TRADER_AGENTS_LLM_TIMEOUT_SECONDS=120
```

Runtime composition fails before checkpoint execution if the required values or exact served digest do not match the
admitted profile. Credentials stay in the provider client and are not persisted in checkpoints or traces.

## MCP Data Config

The MCP server configuration is separate from the tool execution configuration.

The MCP server itself owns only:

- transport and environment label
- registered tool names and descriptions
- artifact root
- safety gates for disabled capabilities

Data tools may also need a trader runtime YAML when they execute. `TRADER_MCP_TRADER_CONFIG_PATH` points to that YAML when MCP data tools should use a real configured event store:

<!-- verified: integration:configuration tests/test_config.py tests/test_agent_runtime_foundation.py -->
```bash
TRADER_MCP_TRADER_CONFIG_PATH=configs/example.yaml
```

Leave it empty for tests or no-op local MCP behavior. Tests may override these values in their process environment.

If that YAML contains substitutions such as `${PG_PORT}` or `${ALPACA_API_KEY}`, set `TRADER_MCP_TOOL_ENV_PATH` to the
runtime dotenv file used to expand those values:

<!-- verified: integration:configuration tests/test_config.py tests/test_agent_runtime_foundation.py -->
```bash
TRADER_MCP_TOOL_ENV_PATH=.env
```

That file is loaded only when an affected tool builds the trader YAML. It is not required for MCP server startup,
tool registration, `mcp_health`, or `mcp_get_config`.

Execution code should not know whether it was called by MCP, a script, a test, or an agent graph. It should receive
typed inputs, explicit dependencies, and explicit policy. The caller may prepare those dependencies differently, but
the execution service should not read control-plane settings such as `TRADER_MCP_TRANSPORT`.

A bad trader YAML must not prevent the MCP server from starting, listing tools, or returning `mcp_health` / `mcp_get_config`. It should fail only when an affected tool executes, and that failure should be returned as a structured tool envelope.

## Runtime `.env`

The core trading runtime also supports a separate `.env` for values expanded by YAML configs, such as Postgres and Alpaca credentials. `.env` is also ignored by git and should not be confused with `local.env`.

## Verification isolation

Guarded Postgres verification uses the explicit `PG_TEST_*`, `PG_OPERATOR_*`, `PG_OPTUNA_TEST_*`, and
`PG_CHECKPOINT_TEST_*` families documented by the qualification procedure. Those tests never read the legacy/operator
`PG_HOST` family as a fallback. Locale and exact role/database ownership are part of the verification profile.
