# Trader Console API Usage Reference

## Entry point

`trader-console-api [--host HOST] [--port PORT]` launches Uvicorn with the `create_app` factory. It binds to
`127.0.0.1:8001` by default. Binding remotely does not add authentication or authorization.

## Required environment

| Variable | Meaning |
| --- | --- |
| `TRADER_CONSOLE_DATABASE_URL` | Local DSN baseline consumed by the default pool factory. |
| `TRADER_CONSOLE_SCOPE_ID` | Stable, server-owned scope identifier. |
| `TRADER_CONSOLE_SCOPE_ENVIRONMENT` | One of `paper`, `backtest`, or `synthetic_demo`. |

Optional values are `TRADER_CONSOLE_SCOPE_DISPLAY_NAME`, `TRADER_CONSOLE_BROKER_ACCOUNT_DISPLAY_LABEL`, and
`TRADER_CONSOLE_PRESENTATION_TIMEZONE`. The brokerage label applies only to paper scopes and is safe display text, not
a provider account reference.

Pool and query bounds may be adjusted server-side with:

| Variable | Default | Accepted bound |
| --- | ---: | ---: |
| `TRADER_CONSOLE_POOL_MIN_SIZE` | 1 | 1–16 |
| `TRADER_CONSOLE_POOL_MAX_SIZE` | 4 | 1–32 and not below the minimum |
| `TRADER_CONSOLE_POOL_TIMEOUT_SECONDS` | 3 | greater than 0, at most 60 |
| `TRADER_CONSOLE_POOL_OPEN_TIMEOUT_SECONDS` | 10 | greater than 0, at most 120 |
| `TRADER_CONSOLE_POOL_CLOSE_TIMEOUT_SECONDS` | 5 | greater than 0, at most 60 |
| `TRADER_CONSOLE_STATEMENT_TIMEOUT_MS` | 2000 | 100–60000 |

## Application factory

`create_app(settings=None, *, pool_factory=create_connection_pool, authentication_provider=None)` returns the FastAPI
application. Passing settings avoids process-environment access in tests and alternate composition roots. A custom pool
factory owns later connection authentication; an `AuthenticationProvider` will supply Trader principals to future
scoped routes. The current health routes intentionally do not invoke it.

The composition root wires `routers.health` to `services.HealthService`, which depends on
`repositories.SchemaCompatibilityRepository`. HTTP code does not execute SQL, and repository code does not construct HTTP
responses.

## Health endpoints

| Endpoint | Success | Failure meaning |
| --- | --- | --- |
| `GET /health/live` | HTTP 200, process is responding | No database or trading check is performed. |
| `GET /health/ready` | HTTP 200, database schema is reachable and compatible | HTTP 503 for database loss or incompatible metadata/catalog after startup. |

Responses are non-cacheable. No endpoint accepts a DSN, schema, table name, scope override, account mapping,
environment, or capability from the client.

## Startup behavior

The lifespan creates and opens exactly one bounded pool, then inspects the compatibility row and exact stable relation
columns in one short read-only transaction. Missing metadata, an older incompatible contract, or column drift aborts
startup. The API never installs or repairs `console_read`.

That transaction policy belongs to this compatibility query. It does not define the whole API as read-only; future
command services will have their own explicit authority and transaction contracts.
