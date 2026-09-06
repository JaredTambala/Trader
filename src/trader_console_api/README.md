# Trader Console API

`trader_console_api` is Trader's outward-facing HTTP application boundary, initially serving the Trader Console and
intended to grow into the primary human-facing way to interact with Trader. One process currently serves one
server-configured `ConsoleScope` and owns one bounded Psycopg connection pool.

The current scaffold provides:

- immutable scope and process configuration;
- injectable database-connection and request-principal composition points;
- read-only transactions for the currently implemented schema queries;
- startup admission against database compatibility metadata and exact relation shape;
- separate `/health/live` and `/health/ready` endpoints; and
- permanent dependency checks excluding Trader execution, event-store, broker, research, MCP, Agent, and MLflow code.

Request handling follows an explicit `routers` → `services` → `repositories` direction. Routers translate HTTP,
services orchestrate application outcomes, and repositories own persistence and transaction policy.

The current slice exposes health and database compatibility only. It does not yet expose operational queries,
commands, authentication, or principal authorization. Those omissions are current implementation state, not a
permanent read-only definition of the API.

## Documentation

- [Architecture](docs/architecture.md)
- [Tutorial](docs/tutorial.md)
- [Usage reference](docs/usage.md)
