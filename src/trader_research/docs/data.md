# Data Research Capability

The Data context resolves a research brief into a multi-asset data scope. It can discover symbols through configured
catalogues, inspect available coverage, summarize quality, request bounded backfill, revalidate the result, and publish
dataset evidence.

The scope is not restricted to one symbol or pair. Every item carries asset class, symbol, timeframe, interval, source,
and research role. Readiness is assessed across the complete required set; a partially ready universe remains explicit.

Provider discovery and loading are separate gated capabilities. A provider may support a catalogue without supporting
backfill for the requested asset/timeframe. Loading uses cost/limit policy and durable operation identity. After an
interruption, the caller reconciles prepared or terminal evidence rather than blindly resubmitting.

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
