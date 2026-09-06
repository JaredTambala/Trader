# Trader Console API Tutorial

This scaffold is useful once the producer-owned `console_read` schema has been installed in a local isolated
database. It starts no trading runtime and performs no schema migration.

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
```

Liveness reports only process availability. Readiness rechecks database compatibility inside a new read-only
transaction. That is the current query policy, not a restriction on future API command features. Startup fails clearly
when the producer schema was not installed or is incompatible.

## 4. Shut down and clear local secrets

Stopping the process closes its one connection pool. Clear the local DSN from the shell afterward:

<!-- verified: integration:console tests/trader_console_api/application/test_lifecycle_and_health.py -->
```bash
unset TRADER_CONSOLE_DATABASE_URL
```
