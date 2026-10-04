# Research Capability Usage Reference

## Import by bounded context

`trader_research` intentionally has no broad root re-export. Import from a public context facade:

<!-- verified: doctest -->
```pycon
>>> from trader_research.data import DATA_GET_INVENTORY
>>> from trader_research.foundation import stable_research_id
>>> from trader_research.governance import DATASET_MANIFEST
>>> DATA_GET_INVENTORY
'data_get_inventory'
>>> DATASET_MANIFEST
'dataset_manifest'
>>> stable_research_id("scope", {"symbols": ["AAPL", "MSFT"]}).startswith("scope_")
True
```

Choose the facade that owns the question. This keeps dependencies visible and makes the resulting artifact authority
unambiguous:

| Question | Start here | Durable evidence commonly returned |
| --- | --- | --- |
| Is a symbol or dataset available? | `trader_research.data` | dataset manifest, quality report, load evidence |
| What source-backed method claims exist? | `trader_research.knowledge` | source, evidence-unit, claim-span, or method-card refs |
| Does an implementation satisfy its contract? | `trader_research.methodology` or `experiments` | validation report and implementation version |
| What did a declared strategy/risk/backtest run do? | `trader_research.experiments` | immutable specifications and backtest run |
| What weakens the result? | `trader_research.review` | Evaluation or Adversarial report |
| Can a model identity be resolved for runtime use? | `trader_research.ml` | deployment manifest and validation report |

The root package intentionally has no broad re-export. Importing from a context facade makes it clear which context
owns the operation and which package must change when its contract changes.

## Common service shape

Application operations validate a typed request or normalized mapping, call injected ports, persist canonical evidence
when required, and return `ApplicationResult`. Check `ok` before consuming data. Treat warnings as part of the evidence,
not console decoration. On failure, inspect structured error codes and any bounded partial artifacts before deciding
whether a retry is safe.

The normal call sequence is:

1. Build a typed request or normalized mapping at the boundary.
2. Pass explicit stores, provider ports, policies, and clocks where the service requires them.
3. Inspect `ok`, `warnings`, and `errors` before following an artifact reference.
4. Re-read and validate canonical references before using them as input to a mutation or conclusion.

Context services return transport-neutral results. MCP ownership, side-effect classification, schema metadata, and
JSON-RPC conversion are added only by `trader_mcp`.

## Persistence choices

`InMemoryResearchArtifactStore` is appropriate for deterministic unit tests. `PostgresResearchArtifactStore` in the
infrastructure layer is the canonical runtime adapter. `UnavailableResearchArtifactStore` makes an absent dependency
explicit and prevents accidental fallback to memory in a production workflow.

Knowledge services accept the `KnowledgeStore` port from `trader_research.knowledge`. Runtime composition uses the
concrete adapter from the outer infrastructure package:

<!-- verified: doctest -->
```pycon
>>> from trader_research.infrastructure.postgres import PostgresKnowledgeStore
>>> PostgresKnowledgeStore.__name__
'PostgresKnowledgeStore'
```

Constructing this adapter opens a Postgres connection and may initialize the knowledge schema and pgvector extension;
the executable example therefore verifies the import boundary without constructing it. Inject the adapter into
knowledge services or the MCP composition root and close it with the owning process. Do not import it from
`trader_research.knowledge` or `trader`.

Research persistence is explicit. An unavailable store is a visible dependency failure; it is never silently replaced
with an in-memory store. This matters for reproducibility: an in-memory result can support a unit test, while a durable
artifact is required for a cross-process workflow or later review.

## Provider choices

Provider adapters are optional and injected. Alpaca symbol discovery/data loading, embedding providers, Optuna, and
MLflow projections are not activated merely by importing the package. Environment policy and the MCP composition root
must both admit their side effects.

## Error and retry rules

- Validation errors require a changed request, not repetition.
- Read-only operations may be retried within their deadline.
- A provider-backed mutation with ambiguous terminal state must be reconciled by its stable operation identity.
- A canonical record with the same identity and different content is an integrity error.
- Missing protected evidence or authority blocks the workflow; it is never converted to a warning-only success.
- If a mutating response is lost, reconcile by stable operation or artifact identity before retrying.
- A provider or Postgres failure that leaves terminal state unknown returns a reconciliation-required outcome.
