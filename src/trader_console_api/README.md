# Trader Console API

`trader_console_api` is Trader's outward-facing HTTP application boundary, initially serving the Trader Console and
intended to grow into the primary human-facing way to interact with Trader. One process currently serves one
server-configured `ConsoleScope` and owns one bounded Psycopg connection pool.

The current application provides:

- immutable scope and process configuration;
- injectable database-connection and request-principal composition points;
- read-only transactions for the currently implemented schema queries;
- startup admission against database compatibility metadata and exact relation shape;
- separate `/health/live` and `/health/ready` endpoints;
- `/api/context` for the first screen's configured environment/account, with an offline OpenAPI export; and
- general data resources for OHLCV datasets/bars, experiment/run discovery, and bounded backtest evidence detail; and
- an allowlisted strategy/risk catalogue plus side-effect-free backtest preflight with normalized definitions,
  coverage, warmup, budget, and warning evidence; and
- explicit Console-owned immutable definition storage with bounded list/get/revision routes (installed separately); and
- durable execution command records with idempotent submit and bounded status/list reads (worker execution is next); and
- an injected worker seam with lease claims, deterministic run IDs, heartbeats, terminal outcomes and explicit ambiguity
  reconciliation (the concrete BacktestRunner adapter remains deployment composition); and
- a `trader-console-worker` entrypoint that binds the explicit core YAML config and polls the local queue; and
- saved comparison-view definitions bound to one experiment and scope, with live eligibility explanations; and
- saved data-scope alternative comparisons that retain independent evidence and explicit compatibility exclusions; and
- a read-only `/api/paper/runtime` projection for paper session, freshness, portfolio, orders, fills, risk, and
  explicitly unavailable reconciliation/halt evidence; and
- an authenticated `/api/paper/commands` boundary for human-authorized, admission-validated, idempotent paper
  start/pause/stop/halt/reconcile requests with durable audit receipts; and
- a redacted `/api/agent-sessions/{session_id}` workspace for human-owned session evidence and durable
  interrupt/resume/cancel/inspect intents, applied by the separately composed `trader-agent-session-worker`; and
- dependency checks keep resource/read paths free of Trader execution, broker, research, MCP, Agent, and MLflow code;
  the paper-command adapter imports only the typed core operator-control boundary and never constructs a broker.

Request handling follows an explicit `routers` → `services` → `repositories` direction. Routers translate HTTP,
services orchestrate application outcomes, and repositories own persistence and transaction policy.

The current slice exposes public configuration, health, database compatibility, local resource queries, the paper
operations read model, and Console-owned comparison-definition commands. Paper operator routes invoke the injected
authentication provider and require explicit human/operator principal namespaces; other public resource routes retain
their local-development behavior. The separate frontend consumes the comparison, evidence, and paper operations APIs.

## Documentation

- [Run the dedicated demo](../../examples/console_demo/README.md)
- [Console frontend](../../apps/trader-console/README.md)
- [Architecture](docs/architecture.md)
- [Tutorial](docs/tutorial.md)
- [Usage reference](docs/usage.md)
