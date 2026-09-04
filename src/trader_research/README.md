# `trader_research`

`trader_research` is Trader's deterministic research capability layer. It owns research domain values, canonical
artifact contracts, Postgres persistence ports/adapters, data readiness, knowledge evidence, computational methodology,
implementation admission, experiment specifications and execution, optimisation, evaluation, adversarial review,
coding workspaces, and ML deployment records.

It does not expose MCP transport, make model-directed decisions, own LangGraph checkpoints, or place broker orders.
Its functions are useful from tests and trusted application composition; agents reach the same capabilities through the
role-scoped `trader_mcp` boundary.

## Bounded contexts

- `foundation`: dependency-light identities, results, canonical artifact references, and persistence ports
- `governance`: artifact ownership, actor authority, handoffs, sessions, approvals, and protocol values
- `data`: multi-asset discovery, inventory, quality, loading policy, and dataset evidence
- `knowledge`: registered sources, structural chunks, retrieval, claim spans, citations, and method-card state
- `methodology`: typed method contracts, supplied implementation validation, diagnostics, kernels, and packaging
- `coding`: isolated strategy candidate workspaces and bounded checks
- `experiments`: implementation catalogue/admission, immutable specifications, backtests, optimisation, and projections
- `review`: independent evaluation and adversarial evidence
- `ml`: model/deployment artifact contracts, adapter registry, and provider-neutral runtime resolution over the core
  inference-adapter profile
- `infrastructure`: concrete Postgres and optional provider adapters

The supported Postgres knowledge adapter is imported from
`trader_research.infrastructure.postgres.PostgresKnowledgeStore`. The `knowledge` facade owns the domain port and
application behavior; it does not re-export its concrete persistence implementation.

## Learning path

1. Follow the [tutorial](docs/tutorial.md) to learn the result and artifact-reference vocabulary.
2. Read [architecture](docs/architecture.md) for context ownership and dependency direction.
3. Use the [usage reference](docs/usage.md) to choose a public facade.
4. Continue into [artifacts and persistence](docs/artifacts_and_persistence.md), [data](docs/data.md),
   [knowledge](docs/knowledge.md), [methodology](docs/methodology.md), [coding](docs/coding.md),
   [experiments](docs/experiments.md), [review](docs/review.md), and [ML](docs/ml.md).
5. Execute the [research evidence notebook](docs/research_evidence_tutorial.ipynb) for an offline example.

Current availability and qualification are recorded centrally in [Product State](../../docs/product_state.md). The MCP
surface is documented by [`trader_mcp`](../trader_mcp/README.md); the model-backed coordinator is documented by
[`trader_agents`](../trader_agents/README.md).
