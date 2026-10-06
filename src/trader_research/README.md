# `trader_research`

`trader_research` is Trader's deterministic research capability layer. It turns a bounded request into normalized
service results and canonical, inspectable evidence. It owns the research domain values, artifact contracts, persistence
ports and adapters, data readiness, knowledge evidence, computational methodology, implementation admission,
experiment specifications and execution, optimisation, evaluation, adversarial review, coding workspaces, and ML
deployment records.

The package is deliberately a library rather than an autonomous researcher. A caller supplies a request and injected
ports; the service validates the request, performs one bounded operation, and returns an `ApplicationResult`. When the
operation creates evidence, the result carries a stable `research://...` reference that later operations can resolve
and validate. This makes a research run inspectable without requiring MCP, an LLM, or a broker.

Research does not expose transport, choose the next model-directed action, own LangGraph checkpoints, or place broker
orders. Agents reach these same capabilities through the role-scoped [`trader_mcp`](../trader_mcp/README.md) boundary;
the MCP layer adds wire metadata and policy without changing deterministic service semantics.

## Product boundary

The package sits between the core platform and model-facing tools:

```text
Trader core data/events        trader_research                 MCP and agents
      (runtime truth)  ->  normalize -> validate -> persist  ->  discover -> decide
                                |                 |
                                +-- ApplicationResult
                                +-- research:// artifact refs
```

Core owns market-data and execution truth. Research may read bounded core evidence and run explicitly enabled
backtests, but it does not make the live runtime depend on research. Research artifacts are evidence for comparison and
review; they are not approval to promote a strategy or submit an order.

The main boundary rules are:

- context services communicate with typed values and artifact references, never another context's database rows;
- provider, filesystem, Postgres, clock, Docker, and tracking effects enter through injected ports or outer adapters;
- canonical records are append-only and content-addressed where the contract requires it;
- model-facing callers receive bounded summaries and references, not hidden reasoning, credentials, arbitrary SQL, or
  unbounded source payloads.

Governance also owns the human next-decision artifact. An agent-session decision may bind a typed retained-graph
identity and named review revisions; canonical review hashes and session/revision metadata are checked before its
immutable revision is recorded.

## Bounded contexts

Each context has one job and a public facade. The facade is the supported import boundary; implementation modules and
concrete adapters remain behind it.

| Context | Owns | Typical question |
| --- | --- | --- |
| `foundation` | identities, results, artifact references, and persistence ports | “What stable value or reference crosses this boundary?” |
| `governance` | ownership, authority, handoffs, sessions, approvals, and protocol values | “Who may create or consume this artifact?” |
| `data` | symbol discovery, inventory, quality, bounded loading, and dataset evidence | “Is the requested market data complete and fit?” |
| `knowledge` | registered sources, chunks, retrieval, claim spans, citations, and method-card state | “Which source-backed claims support this method?” |
| `methodology` | method contracts, implementation validation, diagnostics, kernels, and packages | “Does this supplied method satisfy its declared contract?” |
| `coding` | isolated candidate workspaces, bounded checks, and inert packages | “Can this candidate be inspected and admitted safely?” |
| `experiments` | implementation admission, specifications, backtests, optimisation, and projections | “What exactly was run, under which assumptions?” |
| `review` | independent evaluation and adversarial evidence | “What could invalidate or weaken the result?” |
| `ml` | deployment manifests, adapter registries, and provider-neutral runtime resolution | “Can this exact model identity be resolved for a run?” |
| `infrastructure` | Postgres and optional provider implementations | “How does an outer effect implement the inner port?” |

The supported Postgres knowledge adapter is imported from
`trader_research.infrastructure.postgres.PostgresKnowledgeStore`. The `knowledge` facade owns the domain port and
application behavior; it does not re-export its concrete persistence implementation. The same direction applies to
the research artifact store and provider adapters: composition selects them at the edge, while deterministic contexts
remain usable with in-memory or unavailable stores in tests.

## Evidence lifecycle

The normal path is a chain of explicit evidence decisions rather than a single “run research” call:

1. Normalize the requested scope, identities, and assumptions at a context facade.
2. Discover or load bounded inputs, retaining data quality and provenance evidence.
3. Admit exact implementations and create immutable strategy, risk, and backtest specifications.
4. Execute the declared specification and persist a canonical run record.
5. Compare, optimise, and project results only through the contracts that own those actions.
6. Generate independent Evaluation and Adversarial reports before drawing a conclusion.

Knowledge can supply source-backed method evidence to the authoring path, but citations do not replace implementation
admission or demonstrate trading efficacy. A missing, stale, restricted, or mismatched reference remains a blocker.

## Learning path

1. Follow the [tutorial](docs/tutorial.md) to learn the result and artifact-reference vocabulary.
2. Read [architecture](docs/architecture.md) for context ownership and dependency direction.
3. Use the [usage reference](docs/usage.md) to choose a public facade.
4. Continue into [artifacts and persistence](docs/artifacts_and_persistence.md), [data](docs/data.md),
   [knowledge](docs/knowledge.md), [methodology](docs/methodology.md), [coding](docs/coding.md),
   [experiments](docs/experiments.md), [review](docs/review.md), and [ML](docs/ml.md).
5. Execute the [research evidence notebook](docs/research_evidence_tutorial.ipynb) for an offline example.

For a cross-package workflow, read the repository [research workflow](../../docs/workflows/research.md) after the
tutorial. It shows how the same deterministic services are reached through MCP and how evidence moves between Data,
Strategy Engineering, Experiments, Evaluation, and Adversarial review.

Current availability and qualification are recorded centrally in [Product State](../../docs/product_state.md). The MCP
surface is documented by [`trader_mcp`](../trader_mcp/README.md); the model-backed coordinator is documented by
[`trader_agents`](../trader_agents/README.md).
