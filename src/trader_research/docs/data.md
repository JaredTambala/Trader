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
