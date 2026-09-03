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

## Common service shape

Application operations validate a typed request or normalized mapping, call injected ports, persist canonical evidence
when required, and return `ApplicationResult`. Check `ok` before consuming data. Treat warnings as part of the evidence,
not console decoration. On failure, inspect structured error codes and any bounded partial artifacts before deciding
whether a retry is safe.

## Persistence choices

`InMemoryResearchArtifactStore` is appropriate for deterministic unit tests. `PostgresResearchArtifactStore` in the
infrastructure layer is the canonical runtime adapter. `UnavailableResearchArtifactStore` makes an absent dependency
explicit and prevents accidental fallback to memory in a production workflow.

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
