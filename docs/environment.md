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

<!-- verified: integration:configuration tests/trader/config/test_config.py tests/trader_agents/application_runtime/test_session_pins.py -->
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

<!-- verified: integration:local-model tests/trader_agents/model_runtime/test_local_model_behavior.py -->
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

<!-- verified: integration:configuration tests/trader/config/test_config.py tests/trader_agents/application_runtime/test_session_pins.py -->
```bash
TRADER_MCP_TRADER_CONFIG_PATH=configs/example.yaml
```

Leave it empty for tests or no-op local MCP behavior. Tests may override these values in their process environment.

If that YAML contains substitutions such as `${PG_PORT}` or `${ALPACA_API_KEY}`, set `TRADER_MCP_TOOL_ENV_PATH` to the
runtime dotenv file used to expand those values:

<!-- verified: integration:configuration tests/trader/config/test_config.py tests/trader_agents/application_runtime/test_session_pins.py -->
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

Provisioning is an explicit operator action. From the repository root, run
`uv run python -m tests.cross_package.qualification.support.postgres_verification provision --reset` only against the
dedicated verification database named by the complete guarded profile.

## Console database access

The Console read contract does not provision a service principal, PostgreSQL roles, grants, credentials, or
database-wide access policy. During local development, its migration DSN may use the existing developer database
identity. Run installation explicitly; API startup never runs it:

<!-- verified: integration:postgres tests/trader/event_store/test_console_read_contract.py -->
```bash
export TRADER_CONSOLE_MIGRATION_DSN='postgresql://migration-owner:secret@127.0.0.1:5432/trader'
uv run trader-console-read-contract install
unset TRADER_CONSOLE_MIGRATION_DSN
```

`TRADER_CONSOLE_DATABASE_URL` is the API/deployment extension point. It may initially contain a local DSN. A later
deployment can resolve it from a secret manager, managed identity, database proxy, or environment-specific IAM adapter
without changing repository queries or the producer-owned schema. The current compatibility queries use short
read-only transactions regardless of how the connection is authenticated. This is not a package-wide restriction on
future command operations.

Verify the installed relation shapes and compatibility metadata with any identity intended to perform Console reads:

<!-- verified: integration:postgres tests/trader/event_store/test_console_read_contract.py -->
```bash
export TRADER_CONSOLE_DATABASE_URL='postgresql://developer:secret@127.0.0.1:5432/trader'
uv run trader-console-read-contract verify
unset TRADER_CONSOLE_DATABASE_URL
```

Verification reads catalogs and contract metadata only. It does not assess roles or claim that production IAM exists.
It fails on missing relations, column drift, or an incompatible contract version.

Start one local API process for one isolated scope after verification succeeds:

<!-- verified: integration:console tests/trader_console_api/application/test_lifecycle_and_health.py -->
```bash
export TRADER_CONSOLE_SCOPE_ID='paper-primary'
export TRADER_CONSOLE_SCOPE_DISPLAY_NAME='Primary paper account'
export TRADER_CONSOLE_SCOPE_ENVIRONMENT='paper'
export TRADER_CONSOLE_BROKER_ACCOUNT_DISPLAY_LABEL='Paper A'
uv run trader-console-api
```

The default listener is `127.0.0.1:8001`. Startup opens one bounded pool and admits only a compatible database schema.
`/health/live` reports process liveness; `/health/ready` rechecks schema compatibility in a fresh read-only
transaction. Neither route claims trading health, brokerage-account verification, or production authorization. Pool
size, acquisition/open/close timeouts, statement timeout, and presentation timezone are listed in the Console API
[usage reference](../src/trader_console_api/docs/usage.md).

Rollback is an owner action and removes only the Console schema. It refuses to cross an unknown version boundary:

<!-- verified: integration:postgres tests/trader/event_store/test_console_read_contract.py -->
```bash
export TRADER_CONSOLE_MIGRATION_DSN='postgresql://migration-owner:secret@127.0.0.1:5432/trader'
uv run trader-console-read-contract rollback --confirm-version 1
unset TRADER_CONSOLE_MIGRATION_DSN
```
