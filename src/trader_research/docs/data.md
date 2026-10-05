# Data Research Capability

The Data context resolves a research brief into a multi-asset data scope. It can discover symbols through configured
catalogues, inspect available coverage, summarize quality, request bounded backfill, revalidate the result, and publish
dataset evidence.

The scope is not restricted to one symbol or pair. Every item carries asset class, symbol, timeframe, interval, source,
and research role. Readiness is assessed across the complete required set; a partially ready universe remains explicit.

Provider discovery and loading are separate gated capabilities. A provider may support a catalogue without supporting
backfill for the requested asset/timeframe. Loading uses cost/limit policy and durable operation identity. After an
interruption, the caller reconciles prepared or terminal evidence rather than blindly resubmitting.

Every `data_discover_symbols` report includes `discovery_capability` with four explicit decisions:
`completeness` is `complete`, `partial`, `stale`, or `unavailable`; `freshness` is `fresh`, `stale`, or `unknown`;
`can_discover` reports whether the catalogue query completed; and `load_capability` is `load_capable`,
`discover_only`, or `unavailable`. The root report repeats these fields as `catalogue_completeness`,
`catalogue_freshness`, `can_discover`, `can_load`, and `load_capability` for clients that do not want to unwrap the
grouped object. A visible symbol is therefore never evidence that the provider catalogue is complete or that a bounded
backfill can run. Provider adapters own the observed request state; static provider configuration only constrains the
maximum capability, so a catalogue adapter that has no load evidence remains `discover_only`.

## Data readiness lifecycle

The public operations form a deliberate sequence:

```text
discover symbols -> inspect inventory -> summarize quality
                                      |
                         missing coverage and quality gaps
                                      v
                       costed, approved bounded loading
                                      |
                         revalidate -> publish snapshot
```

Every step carries the complete composite scope: asset class, symbols, timeframe, interval, source, and research role.
Readiness is therefore a property of the requested universe, not a convenient answer for whichever symbol happened to
be available. A load operation must cite its matching plan and remains identifiable if the provider call is interrupted.

The resulting manifest and quality evidence describe what the next context may use. They do not claim that the data is
economically useful, and they do not authorize a backtest with a different scope.

## Qualified replay identity

An inventory manifest also carries `replay_data_identity` when rows are available. This is separate from `dataset_id`:
the dataset ID identifies the normalized query scope, while the replay identity is a `sha256:bar-content-v1` digest over
every returned symbol, timestamp, timeframe, source, and OHLCV field in canonical order. Its typed `source_semantics`
records the provider, requested source policy, observed sources, asset class, symbols, timeframe, and bar type, together
with the UTC `inspected_at` timestamp.

Research backtest execution re-reads the same bounded scope and recomputes this identity before loading the runner. A
changed row, partial reload, source substitution, malformed identity, or scope mismatch raises an explicit identity
failure and prevents execution. The inspection timestamp is evidence of when the rows were qualified; it is not folded
into the content digest, so equivalent reads remain deterministic.

## Failure and recovery

Malformed scope, unsupported provider capabilities, over-limit or over-cost requests, stale data, and incomplete
coverage are explicit outcomes. A read-only inventory or quality request may be retried against the same scope. A
prepared load is reconciled through its operation identity; if the store cannot establish a terminal result, the caller
receives `data_load_reconciliation_required` rather than a second provider mutation.

Public operations are exported from `trader_research.data`: discovery, inventory, quality, loading, and research
snapshot creation. MCP ownership and agent selection are outside this package.

## Verification ownership

Data-context tests live under `tests/trader_research/data/` and separate provider catalogue adaptation, provider-context
and symbol discovery, dataset inventory, quality summarization, readiness/loading, and fresh-connection recovery. The
offline suites use injected catalogues, the shared DuckDB test adapter, and the checked-in sample dataset; they make no
provider network calls. The Postgres recovery contract is separately marked and requires
`TRADER_AGENTS_ARTIFACT_TEST_DSN` to target an isolated test database. A skipped recovery test is not external evidence.

Core event-store behavior and core quality-report file export remain under `tests/trader/`, even when research services
consume those lower-level capabilities. Test ownership follows the asserted production contract, not a generic
historical filename or the presence of a lower-level collaborator.
