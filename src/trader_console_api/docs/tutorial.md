# Trader Console API Tutorial

The API requires the producer-owned `console_read` schema in a local isolated database. It starts no trading runtime
and performs no schema migration. For the first Console screen, start with the dedicated
[demo walkthrough](../../../examples/console_demo/README.md), then the
[frontend instructions](../../../apps/trader-console/README.md). The steps below cover independent API configuration.

## 1. Describe the isolated scope

The safe scope contract contains presentation and evidence-binding metadata, never database connection details:

<!-- verified: doctest -->
```pycon
>>> from trader_console_api import BrokerAccountBinding, ConsoleEnvironment, ConsoleScope
>>> scope = ConsoleScope(
...     scope_id="paper-primary",
...     display_name="Primary paper account",
...     environment=ConsoleEnvironment.PAPER,
...     broker_account_display_label="Paper A",
...     broker_account_binding=BrokerAccountBinding.CONFIGURED,
... )
>>> scope.scope_id
'paper-primary'
>>> "database_url" in scope.model_dump()
False
```

## 2. Configure one local process

Set the database URL and safe scope identity on the server. The browser never sends these values.

<!-- verified: integration:console tests/trader_console_api/application/test_lifecycle_and_health.py -->
```bash
export TRADER_CONSOLE_DATABASE_URL='postgresql://developer:secret@127.0.0.1:5432/trader'
export TRADER_CONSOLE_SCOPE_ID='paper-primary'
export TRADER_CONSOLE_SCOPE_DISPLAY_NAME='Primary paper account'
export TRADER_CONSOLE_SCOPE_ENVIRONMENT='paper'
export TRADER_CONSOLE_BROKER_ACCOUNT_DISPLAY_LABEL='Paper A'
```

## 3. Start and inspect the service

The default host is loopback and the default port is 8001.

<!-- verified: integration:console tests/trader_console_api/application/test_lifecycle_and_health.py -->
```bash
uv run trader-console-api
curl --fail http://127.0.0.1:8001/health/live
curl --fail http://127.0.0.1:8001/health/ready
curl --fail http://127.0.0.1:8001/api/context
```

Liveness reports only process availability. Readiness rechecks database compatibility inside a new read-only
transaction. That is the current query policy, not a restriction on future API command features. Startup fails clearly
when the producer schema was not installed or is incompatible.

The context endpoint returns the configured environment and optional account label. It does not verify the account
or contact a broker. For a synthetic demo, the environment is explicitly `synthetic_demo` and the broker binding is
`not_applicable`. No label is required. If the database becomes unavailable after startup, context remains available
while readiness returns HTTP 503; retry readiness after recovery. If startup itself fails, the API is unavailable and
cannot supply context. See the [first-screen contract](usage.md#first-screen-contract) for the UI state mapping.

The frontend displays these three endpoints through same-origin Next.js rewrites. Refresh is manual; database
failures do not erase configured context or imply trading health. Its generated types consume the checked
[OpenAPI export](usage.md#openapi-export), which can be produced without installing a database.

To inspect the available data slices and their capability boundary, query the dataset resource:

<!-- verified: integration:console tests/trader_console_api/application/test_lifecycle_and_health.py -->
```bash
curl --fail 'http://127.0.0.1:8001/api/market-data/datasets?limit=100&offset=0'
```

The response's `discovery` object distinguishes catalogue completeness (`complete`, `partial`, `stale`, or
`unavailable`) from `load_capability` (`load_capable`, `discover_only`, or `unavailable`). Existing Console rows prove
stored coverage only; they do not prove that the provider catalogue is complete or that a backfill can run.

## 4. Preflight and persist a definition

Discover the maintained profiles, submit a typed draft to preflight, then persist it only after the response is valid:

<!-- verified: integration:console tests/trader_console_api/services/test_definition_service.py -->
```bash
curl --fail http://127.0.0.1:8001/api/backtests/catalogue
curl --fail -X POST http://127.0.0.1:8001/api/backtests/preflight \
  -H 'content-type: application/json' \
  -d '{"strategy_profile_id":"noop","risk_profile_id":"noop","asset_class":"stock","symbols":["AAPL"],"timeframe":"1Min","start":"2026-01-01T00:00:00Z","end":"2026-01-01T01:00:00Z"}'
```

Install the Console-owned definition table explicitly before using persistence routes:

<!-- verified: integration:console tests/trader_console_api/repositories/test_backtest_definitions_schema.py -->
```bash
TRADER_CONSOLE_DATABASE_URL="$TRADER_CONSOLE_DATABASE_URL" \
  uv run python -m trader_console_api.repositories.backtest_definitions_schema install
```

Then `POST /api/backtests/definitions` creates the first immutable revision. Use the returned definition ID with
`GET /api/backtests/definitions/{definition_id}` or append a new preflighted revision at
`POST /api/backtests/definitions/{definition_id}/revisions`. The worker/execution command is intentionally not part
of this step.

The durable command record is installed separately after definition storage and can then be submitted with an
idempotency key:

<!-- verified: integration:console tests/trader_console_api/repositories/test_backtest_executions_schema.py -->
```bash
TRADER_CONSOLE_DATABASE_URL="$TRADER_CONSOLE_DATABASE_URL" \
  uv run python -m trader_console_api.repositories.backtest_executions_schema install
curl --fail -X POST http://127.0.0.1:8001/api/backtests/executions \
  -H 'content-type: application/json' \
  -d '{"definition_id":"00000000-0000-0000-0000-000000000000","idempotency_key":"local-demo-1"}'
```

The command remains `queued` until the local worker tranche is delivered; poll
`GET /api/backtests/executions/{execution_id}` for the durable record.

When the core YAML configuration is available, start the local worker in a separate process:

<!-- verified: integration:console tests/trader_console_api/application/test_worker_entrypoint.py -->
```bash
export TRADER_CONSOLE_BACKTEST_CONFIG_PATH=./config/local.yaml
uv run trader-console-worker
```

The worker resolves exact catalogue versions and invokes the canonical internal-broker runner through its injected
adapter. `uv run trader-console-worker --once` is useful for one-command recovery checks.

## 5. Install saved comparison storage when needed

Comparison views are an additive Console-owned feature. Install their table as an explicit operator action after the
producer `console_read` contract is ready:

<!-- verified: integration:console tests/trader_console_api/repositories/test_comparison_schema.py -->
```bash
TRADER_CONSOLE_DATABASE_URL="$TRADER_CONSOLE_DATABASE_URL" \
  uv run python -m trader_console_api.repositories.comparison_schema install
```

Use the API's comparison-view endpoints from [the usage reference](usage.md#saved-comparison-views). The API stores
the definition only and evaluates selected runs from current published evidence whenever it previews or loads a view.

## 6. Shut down and clear local secrets

Stopping the process closes its one connection pool. Clear the local DSN from the shell afterward:

<!-- verified: integration:console tests/trader_console_api/application/test_lifecycle_and_health.py -->
```bash
unset TRADER_CONSOLE_DATABASE_URL
```
