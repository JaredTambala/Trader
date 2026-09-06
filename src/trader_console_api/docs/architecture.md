# Trader Console API Architecture

## Responsibility

`trader_console_api` is Trader's outward-facing HTTP application boundary. It is independently startable and is
intended to grow into the primary human-facing interface for Trader queries and commands. Its current implementation
is deliberately small: server-owned scope configuration, pooled PostgreSQL access, database-schema compatibility,
application lifecycle, and health responses.

The current health and compatibility slice imports FastAPI, Pydantic, Psycopg, and Psycopg Pool directly and imports
no `trader` package. It does not construct `PostgresEventStore`, run producer migrations, create a broker, execute a
strategy, or reach research, MCP, Agent, or MLflow behavior. This protects the implemented slice without defining a
permanent ban on future API application services.

## Router-service-repository direction

The source tree makes the application flow explicit:

```text
application composition
  -> routers
       -> services
            -> repositories
                 -> console_read
```

- `routers/` owns FastAPI paths, dependency resolution, response status codes, and HTTP headers. It performs no
  database inspection or application orchestration.
- `services/` converts repository evidence and failures into application outcomes, including readiness and startup
  admission.
- `repositories/` owns persistence access, parameterized SQL, catalog normalization, pool protocols, and transaction
  policy.
- `application.py` is only the composition root and lifespan owner. It wires the pool, repository, service, and router.

## Process and scope boundary

One API process serves one `ConsoleScope` backed by one isolated PostgreSQL database and one bounded connection pool.
Paper, backtest, and synthetic-demo scopes run as separate process deployments. A same-origin gateway may later
present several authorised deployments as one product surface without giving this process a multi-database registry.

`ConsoleScope` separates three concepts:

- the Trader principal, supplied by an authentication gateway when remote access is introduced;
- the external brokerage account represented by a paper database; and
- the safe public scope binding exposed to Console consumers.

Connection details and brokerage provider references are not members of the public scope. The current paper binding
status is `configured`, not verified. Backtest and demo scopes use `not_applicable`.

## Lifecycle and database compatibility

The FastAPI lifespan creates one pool through an injected factory, opens it with a finite timeout, checks database
compatibility, and closes it during shutdown. API startup fails before serving when the compatibility record is missing or
the catalog does not exactly match the expected allowlisted projections.

The current compatibility repository enters through `repositories.ConsoleDatabase.transaction()`. It acquires one
pooled connection, starts one transaction, applies `SET TRANSACTION READ ONLY`, sets a transaction-local statement
timeout, performs the query, and releases the connection. Repositories never receive client-supplied SQL identifiers.

The Console duplicates the consumer-side catalog expectation intentionally. It does not import the producer migration
module from `trader`; this keeps deployment and schema mutation outside API startup.

## Capability growth

Read-only is a property of the currently implemented schema queries, not the API's identity. Future operational
queries and mutations belong in dedicated routers, services, and repositories. Each command path must declare its
authority, validation, idempotency, transaction, and failure semantics; it is not routed through the compatibility
repository or inferred from the current health behavior.

## IAM extension points

Local development supplies `TRADER_CONSOLE_DATABASE_URL`. The app factory accepts a pool factory so later deployment
composition can resolve credentials through a secret manager, managed identity, database proxy, or another IAM
mechanism without changing repositories. It also accepts an `AuthenticationProvider` for future Trader-principal
resolution.

The scaffold stores but does not invoke the authentication provider because it exposes only health routes. It creates
no service principal, role, grant, credential, middleware policy, or application RBAC. Remote authentication and scope
authorization become required when scoped evidence routes are exposed and a deployment threat model exists.

## Health semantics

`/health/live` means only that the HTTP process is responding. `/health/ready` means the configured PostgreSQL database
is reachable and its `console_read` metadata and relation shapes are compatible. Neither endpoint claims broker
connectivity, trading-session health, evidence freshness, broker-account attestation, or production authorization.

Both endpoints return `Cache-Control: no-store`. An incompatible contract blocks startup; loss of compatibility or
database access after startup makes readiness return HTTP 503 while liveness remains HTTP 200.
