# Data Agent Symbol Discovery Tool Plan

## Goal

Add a read-only Data Agent MCP tool, tentatively named `data_discover_symbols`, that helps a research workflow discover
available provider-scoped instruments before a bounded data inventory or quality request exists.

The Data Agent should use this tool as a mandatory preflight before it decides to create inventory, quality, or loading
queries against a data source. If a requested symbol is not available from the configured source/catalog, the agent
should fail fast with a structured blocker instead of querying the data store or attempting a backfill.

The tool should also make provider context explicit. Today the Data Agent mostly sees symbols, a global-looking
`asset_class`, timeframe, and an optional local source filter; provider choice is inferred later from trader config and
backfill internals. Symbol discovery should introduce a small provider-resolution boundary so future providers can be
added without embedding Alpaca-specific behavior in Data Agent graphs.

Instrument and bar semantics are provider-scoped. "stocks" and "crypto" are not universal namespaces; they are current
platform labels for Alpaca-backed bar tables. A future provider may expose different instrument classes, symbol formats,
sessions, adjustments, or bar schemas. The Data Agent must resolve provider, instrument type, and bar type together
before creating local queries or loading requests.

Provider validation is part of the same preflight. If the configured provider is Alpaca and a request asks for Polygon,
the Data Agent must fail fast with a structured provider-mismatch blocker. It must not silently fall back to Alpaca,
local bars, configured symbols, or a backfill attempt.

This tool should answer questions like:

- "Which Alpaca stock symbols matching `AMD` are available?"
- "Which Alpaca crypto pairs matching `BTC` are available?"
- "Do these requested symbols exist before I ask for inventory, quality, or loading?"
- "Which symbols already have local bars in this store?"
- "Which active/tradable provider symbols can I choose from before requesting data?"

It must stay outside the live trading hot path. It must not place orders, mutate broker state, expose raw SQL, or run
backtests.

## Proposed Tool Contract

Tool name:

```text
data_discover_symbols
```

Owner:

```text
Data Agent
```

Side effect:

```text
read_only
```

Request shape:

```json
{
  "instrument_type": "stock",
  "bar_type": "trade_bar",
  "symbols": ["AMD", "MSFT"],
  "query": "AMD",
  "source": "local",
  "provider": "alpaca",
  "limit": 50,
  "active_only": true,
  "tradable_only": true,
  "include_local_coverage": false
}
```

Fields:

| Field | Required | Notes |
| --- | --- | --- |
| `instrument_type` | yes | Provider-scoped instrument class, such as Alpaca `stock` or `crypto`. |
| `bar_type` | no | Provider-scoped bar schema/type, such as `trade_bar`; defaults through provider capabilities. |
| `asset_class` | no | Backward-compatible alias for the current `stocks`/`crypto` platform labels. New code should resolve it into provider-scoped `instrument_type` and `bar_type`. |
| `symbols` | no | Optional exact symbols to validate. When present, the report must include per-symbol existence status. |
| `query` | no | Optional prefix or substring filter for exploratory search. Empty query is allowed only with a bounded `limit`. |
| `source` | no | `local`, `configured`, `configured_source`, `provider`, or `merged`; default should be `configured_source` in agent workflows and `local` in deterministic tests. |
| `provider` | no | Requested provider selector such as `configured`, `alpaca`, `polygon`, or a future provider key. In agent workflows, a concrete provider must match the configured provider before any data-source query is allowed. |
| `limit` | no | Default `50`; hard maximum such as `500` to avoid oversized responses. |
| `active_only` | no | Applies to provider/catalog results when status is available. |
| `tradable_only` | no | Applies to provider/catalog results when tradability is available. |
| `include_local_coverage` | no | Adds first/last timestamp and row counts from local bars for matched symbols. |

At least one of `symbols` or `query` should normally be supplied. A request with neither is allowed only for bounded
catalog browsing and must respect `limit`.

Successful response shape:

```json
{
  "symbol_discovery_report": {
    "report_id": "symbol_discovery_...",
    "instrument_type": "stock",
    "bar_type": "trade_bar",
    "legacy_asset_class": "stocks",
    "requested_symbols": ["AMD", "MSFT"],
    "query": "AMD",
    "source": "local",
    "requested_provider": "alpaca",
    "configured_provider": "alpaca",
    "resolved_provider": "alpaca",
    "provider_match": true,
    "limit": 50,
    "returned": 1,
    "truncated": false,
    "all_requested_symbols_exist": false,
    "missing_symbols": ["MSFT"],
    "symbols": [
      {
        "symbol": "AMD",
        "raw_symbol": "AMD",
        "instrument_type": "stock",
        "bar_type": "trade_bar",
        "legacy_asset_class": "stocks",
        "requested": true,
        "exists": true,
        "name": null,
        "exchange": null,
        "status": null,
        "tradable": null,
        "source": "local",
        "local_coverage": {
          "row_count": 1200,
          "first_ts": "2025-06-01T13:30:00+00:00",
          "last_ts": "2026-06-01T20:00:00+00:00",
          "timeframes": ["1Min"]
        }
      }
    ]
  }
}
```

Provider results may include `name`, `exchange`, `status`, and `tradable` when the upstream catalog supplies them. Local
results should omit unknown provider metadata rather than inventing it.

For exact-symbol validation, every requested symbol must be represented either in `symbols` with `exists=true` or in
`missing_symbols`. A missing requested symbol is not a transport/tool error; it is a successful read-only report with
`all_requested_symbols_exist=false`, unless the request itself is invalid or the selected source is unavailable.

A requested provider mismatch is different from a missing symbol. If `provider="polygon"` but the bounded trader config
resolves to `market_data.source="alpaca"`, the tool should return a failed Data Agent envelope with
`code="provider_not_configured"` and data such as:

```json
{
  "requested_provider": "polygon",
  "configured_provider": "alpaca",
  "resolved_provider": null,
  "provider_match": false
}
```

The Data Agent graph should convert that envelope into a structured blocker and must not call downstream data tools.

## Source Semantics

`local`
: Discover distinct symbols that already exist in local bar tables. This is the deterministic default and should work
with the same event-store abstraction used by inventory and quality tools.

`configured`
: Discover symbols from the currently loaded trader config, if `TRADER_MCP_TRADER_CONFIG_PATH` is set. This is useful
for explaining the current runtime universe even when bars have not been loaded yet.

`configured_source`
: Validate symbols against the data source implied by the bounded trader config. For an Alpaca-backed config, this
means read-only provider catalog validation behind explicit provider-discovery policy. For local/sample/noop configs,
this means the configured universe plus local availability where applicable. This is the default Data Agent preflight
source because it answers "can this configured source supply the requested symbols?"

`provider`
: Discover symbols from a read-only provider catalog, initially Alpaca asset metadata. This source requires explicit
runtime policy because it can make network calls and may need credentials, even though it is read-only.

`merged`
: Merge configured, local, and provider results by canonical symbol. Provider metadata can enrich local/configured
symbols, but local coverage must remain clearly labeled as local evidence.

## Provider Resolution

Provider awareness should be explicit at the Data Agent tool boundary, but provider-specific behavior should live behind
adapters.

Add a small provider-resolution model:

```text
DataSymbolDiscoveryRequest
  -> DataProviderContext(provider_key, instrument_type, bar_type, source_mode, capabilities, config_refs)
  -> SymbolCatalogProvider adapter
  -> symbol_discovery_report
```

Recommended provider fields:

| Field | Meaning |
| --- | --- |
| `requested_provider` | Provider requested by the user or upstream graph, such as `alpaca` or `polygon`. |
| `configured_provider` | Provider configured for the current bounded trader config, usually `market_data.source`. |
| `resolved_provider` | Provider actually validated after policy, config, aliases, and source mode are resolved. |
| `provider_match` | Whether a concrete requested provider matches the configured provider. |
| `provider_key` | Stable adapter identifier, such as `local`, `alpaca`, or future keys. |
| `configured_source` | The raw `market_data.source` value from trader config when available. |
| `instrument_type` | Provider-scoped instrument class requested or resolved for the provider. |
| `bar_type` | Provider-scoped bar schema/type requested or resolved for the provider. |
| `legacy_asset_class` | Optional compatibility label such as `stocks` or `crypto` for current local bar tables. |
| `supports_symbol_catalog` | Whether exact provider catalog validation is available. |
| `supported_instrument_types` | Instrument classes available from this provider adapter. |
| `supported_bar_types` | Bar schemas/types available from this provider adapter. |
| `requires_network` | Whether the provider lookup can make a network call. |
| `requires_credentials` | Whether provider credentials are required for this provider/instrument/bar request. |

Initial adapter interface:

```python
class SymbolCatalogProvider(Protocol):
    provider_key: str

    def discover_symbols(self, request: DataSymbolDiscoveryRequest, context: DataProviderContext) -> SymbolCatalogResult:
        ...
```

Provider implementation rules:

- Data Agent graphs should store and pass provider context, but should not import Alpaca clients or provider SDKs.
- `trader_research.data` may resolve configured provider metadata from the bounded trader config.
- Provider-specific code lives in outer adapter modules, currently
  `trader_research.infrastructure.providers.alpaca`; Data domain/application modules do not import provider SDKs.
- Concrete provider requests must match the configured provider before any provider catalog or data-source query is
attempted.
- Instrument type and bar type must be resolved through the provider adapter. The graph should not assume that
`stocks`, `crypto`, or any table-specific bar shape is universal.
- Provider aliases should be explicit and deterministic, for example `alpaca`, `alpaca_data`, and `configured` can
resolve through config; `polygon` must not resolve unless Polygon is registered and configured.
- Unknown providers should fail closed with a structured `unsupported_provider` envelope unless a local/configured-only
source can answer the request.
- Adding a new provider should require registering a new catalog adapter and tests, not changing Data Agent graph
control flow.

## Required Existing Tool Edits

Provider selection must not live only in the new discovery tool. Existing Data Agent tools also need provider-aware
contracts so direct MCP callers get the same fail-fast behavior as LangGraph workflows.

Update these tools:

| Tool | Required provider behavior |
| --- | --- |
| `data_get_inventory` | Accept optional `provider`, `instrument_type`, and `bar_type`; validate them against configured provider capabilities before local query construction; include provider context in `dataset_manifest`. |
| `data_summarize_quality` | Accept optional `provider`, `instrument_type`, and `bar_type`; validate them against configured provider capabilities before local quality query construction; include provider context in `data_quality_report`. |
| `data_ensure_loaded` | Accept optional `provider`, `instrument_type`, and `bar_type`; validate them before existing/sample/backfill branches; use the resolved provider's loading adapter for non-dry-run provider backfill. |

Provider field rules:

- `provider` defaults to `configured` for agent workflows.
- `instrument_type` and `bar_type` default through the configured provider only when unambiguous.
- Existing `asset_class` inputs remain supported as compatibility aliases, but the resolved artifacts should record the
provider-scoped `instrument_type` and `bar_type`.
- A concrete `provider`, such as `alpaca` or `polygon`, must match the configured provider before the tool builds a
query, checks quality, loads sample data, or runs backfill.
- The existing `source` field should remain a local bar-source filter, not the provider selector.
- When `source` is omitted, provider-aware local reads may use the provider adapter's canonical bar source, for example
`alpaca`, if the request is meant to inspect provider-loaded bars only.
- A provider mismatch returns `code="provider_not_configured"` from every Data Agent tool, not just
`data_discover_symbols`.
- Successful envelopes should include `requested_provider`, `configured_provider`, `resolved_provider`,
`instrument_type`, `bar_type`, `legacy_asset_class`, and `provider_match` in the returned artifact/report so downstream
agents can audit which provider and bar semantics were selected.

Provider-aware tool flow:

```text
request(provider="configured" or "alpaca")
  -> resolve configured provider from bounded config
  -> validate requested provider against configured provider
  -> resolve instrument_type and bar_type through provider adapter/capabilities
  -> build local read query or loading/backfill request
  -> return artifact with provider context
```

This also keeps provider extensibility concrete: implementing a new provider means adding a provider adapter and making
it selectable through config, not adding new agent graph branches or silently changing tool behavior.

## Adding Provider-Scoped Instrument Or Bar Types

New provider-scoped instrument or bar types should be enabled in this order:

1. Add ingestion/loading support for the provider instrument/bar type.
2. Add local storage and typed query support for the resulting bar/event schema.
3. Add inventory and quality support for that provider instrument/bar type.
4. Add symbol catalog support for the provider instrument namespace.
5. Register the instrument/bar type in the provider context capabilities.
6. Expose the new provider context through MCP config and Data Agent state.

For example, if Alpaca later exposes a new supported asset/instrument family, first extend the Alpaca loading adapter,
event schema, local query path, inventory, and quality reporting. Only after those paths work should the Alpaca provider
context advertise the new `instrument_type` or `bar_type` as supported. This prevents discovery from claiming a symbol
or bar type is usable when ingestion, inventory, or quality tooling cannot actually handle it.

For a new provider such as Polygon stocks, the sequence is similar but starts with a new provider adapter:

1. Add a Polygon provider adapter and configuration key, for example `market_data.source: polygon`.
2. Implement Polygon authentication/config resolution without exposing credentials through agent state.
3. Add Polygon stock ingestion/loading support using Polygon APIs.
4. Add or map local storage/query support for Polygon stock bars.
5. Add inventory and quality support for the Polygon stock bar type.
6. Add Polygon symbol catalog discovery for the Polygon stock namespace.
7. Register Polygon provider context capabilities, for example `provider=polygon`, `instrument_type=stock`,
   `bar_type=trade_bar`, only after the above paths work.
8. Add MCP and LangGraph tests that prove `provider=polygon` works only when Polygon is configured, while
   `provider=alpaca` fails with `provider_not_configured` under a Polygon config.

The provider context must own the instrument namespace. One provider may expose `stock`, another may expose `equity`,
`etf`, `option`, `commodity`, or more granular provider-specific labels. Do not force every provider into the current
Alpaca compatibility labels. Instead, map provider-specific instrument types to local storage/query capabilities only
where the platform has explicit support.

Capability registration rules:

- Do not register an instrument/bar type in provider context until ingestion and local query support exist.
- Do not expose provider capability through MCP until direct Data Agent tool tests prove inventory, quality, and loading
fail closed or succeed correctly for that type.
- Provider context should describe both catalog capabilities and data capabilities; a provider may support symbol
catalog lookup for an instrument before historical bars are supported, but the report must make that limitation explicit.
- Provider-specific instrument labels should remain provider-scoped; compatibility aliases like `stocks` are optional
translation layers, not the canonical provider model.
- Adding a new provider-scoped type should not require Data Agent graph control-flow changes.

## Policy

Default MCP behavior should remain deterministic and local:

- `source="local"` is allowed by default.
- `source="configured"` is allowed when a trader config path is present.
- Data Agent graph preflight should use `source="configured_source"` unless state explicitly narrows it.
- `source="provider"` and `source="merged"` with provider enrichment require an explicit read-only network policy flag,
  for example `TRADER_MCP_ALLOW_SYMBOL_PROVIDER_DISCOVERY=true`.
- `source="configured_source"` must fail closed if it resolves to a provider catalog but provider discovery policy is
  disabled.
- A concrete requested provider that does not match the configured provider must fail closed with
  `provider_not_configured`.
- Unsupported provider-scoped instrument types or bar types must fail closed with structured errors such as
  `unsupported_instrument_type` or `unsupported_bar_type`.
- Unknown configured providers must fail closed unless the selected source can be satisfied locally without provider
catalog access.
- Missing provider credentials or unavailable provider clients should return structured Data Agent error envelopes, not
  uncaught exceptions.

This is a read-only capability, so it should not be coupled to `TRADER_MCP_ALLOW_DATA_LOADING`. Data loading/backfill
permission should remain separate from symbol discovery permission.

## Implementation Slices

### Slice A: Shared Provider Context and Capability Resolver

- Add `DataProviderContext` and a shared provider-resolution helper under the research boundary.
- Resolve configured provider from bounded config, including `market_data.source`, current `market_data.asset_class`, and
future provider-scoped instrument/bar config.
- Resolve provider-scoped `instrument_type` and `bar_type`, while preserving `asset_class` as a compatibility alias.
- Add provider mismatch validation before any local query, discovery, quality, loading, or provider-catalog branch runs.
- Represent current Alpaca stock/crypto support as registered capabilities only for paths the platform can already
ingest, query, inventory, and quality-check.
- Keep provider-specific SDK clients out of Data Agent graph code.

Acceptance evidence:

- Direct resolver tests cover configured Alpaca, omitted provider, matching `provider="alpaca"`, mismatched
`provider="polygon"`, unsupported instrument types, unsupported bar types, and legacy asset-class aliases.
- Tests prove provider-scoped instrument/bar capabilities are not advertised unless the matching data capability is
registered.

### Slice B: Provider-Aware Existing Data Tool Edits

- Add optional `provider` inputs to `data_get_inventory`, `data_summarize_quality`, and `data_ensure_loaded`.
- Add optional `instrument_type` and `bar_type` inputs to those tools, with `asset_class` preserved as a compatibility
alias.
- Use the shared provider-resolution helper from Slice A.
- Ensure direct MCP calls fail fast with `provider_not_configured` before local query construction or loading/backfill
branches.
- Add provider, instrument type, and bar type context to `dataset_manifest`, `data_quality_report`, and `load_result`
payloads.
- Keep `source` as a bar-source filter and document how provider adapters map to canonical bar sources.
- For non-dry-run provider backfill, route through the resolved provider's loading adapter rather than hard-coding
Alpaca-specific runner behavior in the Data Agent service.

Acceptance evidence:

- Existing inventory, quality, and ensure-loaded tests still pass with `provider` omitted.
- New tests assert `provider="polygon"` against an Alpaca config fails in all three existing Data Agent tools.
- New tests assert `provider="alpaca"` against an Alpaca config reaches the normal inventory/quality/ensure path.
- New tests assert reports include provider, instrument type, and bar type context fields.
- New tests assert unsupported provider-scoped instrument/bar types fail before query construction.
- A fake second loading adapter test proves provider selection is registry/config driven.

### Slice C: Data Symbol Discovery Service With Local and Configured Sources

- Add `DataSymbolDiscoveryRequest` and a deterministic `discover_symbols(...)` service under `trader_research.data`.
- Use the shared provider resolver before local or configured discovery branches run.
- Add typed core query helpers for local symbol discovery, likely in `trader.market_data_queries`, rather than placing
raw SQL in the research or MCP layers.
- Add a configured-universe branch that reads configured symbols and provider-scoped instrument/bar metadata.
- Support `provider`, `instrument_type`, `bar_type`, compatibility `asset_class`, optional exact `symbols`, optional
`query`, `limit`, and `include_local_coverage`.
- Treat exact `symbols` as a validation request that returns `all_requested_symbols_exist` and `missing_symbols`.
- Return a Data Agent `ToolEnvelope` with `data.symbol_discovery_report`.
- Keep `source="provider"` and provider-enriched `source="merged"` fail-closed until Slice F registers catalog adapters
and explicit provider-discovery policy.

Acceptance evidence:

- Direct service tests cover Alpaca stock and crypto symbols from fixture stores and assert resolved instrument/bar
types.
- Direct service tests cover exact-symbol validation for present, missing, duplicate, and canonicalized crypto symbols.
- Direct service tests cover `provider="polygon"` against an Alpaca config and assert `provider_not_configured`.
- Direct service tests cover unsupported instrument/bar type failures.
- Tests cover matching config symbols, missing requested config symbols, instrument/bar mismatch, legacy asset-class
compatibility, missing config path, invalid limits, and unavailable event-store connections.
- Package-boundary tests continue to prove research/MCP code does not embed raw SQL.

### Slice D: MCP Registration

- Add `DATA_DISCOVER_SYMBOLS_TOOL = "data_discover_symbols"` to the Data Agent tool registry.
- Register `data_discover_symbols` in `trader_mcp.server`.
- Add MCP parsing for discovery request fields and for the new optional `provider`, `instrument_type`, and `bar_type`
fields on existing Data Agent tools.
- Include the tool in `mcp_get_config` with `agent_owner="Data Agent"` and `side_effect="read_only"`.
- Add safety metadata for provider discovery policy, even if provider-catalog discovery remains disabled until Slice F.

Acceptance evidence:

- MCP tests list the tool, call local discovery, and verify JSON text/structured content parity.
- MCP tests verify provider catalog discovery is rejected unless explicit policy and an adapter are enabled.
- MCP tests verify direct calls to existing Data Agent tools fail fast on provider mismatch.

### Slice E: Data Agent Graph

- Extend Data Agent state with `symbol_discovery_request` and `symbol_discovery_report`.
- Extend Data Agent state with provider context fields from the report, such as `resolved_provider`,
`instrument_type`, `bar_type`, and `provider_capabilities`.
- Add `build_data_agent_symbol_discovery_graph`.
- Add a mandatory preflight path that runs exact-symbol validation before inventory, quality, or ensure-loaded requests
when the state includes requested `symbols`.
- The preflight must run before the graph creates or calls downstream data-source query tools.
- If `all_requested_symbols_exist=false`, the graph must stop with a structured blocker and must not call
`data_get_inventory`, `data_summarize_quality`, or `data_ensure_loaded`.
- If discovery returns `provider_not_configured`, the graph must stop with a structured provider blocker and must not
call `data_get_inventory`, `data_summarize_quality`, or `data_ensure_loaded`.
- Agent workflows should default the preflight to `source="configured_source"` so missing symbols fail fast against the
source that would actually be queried.
- When preflight succeeds, the graph must pass the resolved provider, instrument type, and bar type context into
downstream Data Agent tool calls.
- Add `data_discover_symbols` to the Data Agent allowlist.
- Keep the graph deterministic and MCP-first; it must call the MCP tool rather than importing platform query helpers.
- Keep provider-specific branching out of the graph; the graph should react to generic report fields such as
`all_requested_symbols_exist`, `missing_symbols`, and `resolved_provider`.

Acceptance evidence:

- LangGraph tests prove the graph calls `data_discover_symbols` through the MCP client and preserves ordered
`called_tools`.
- LangGraph tests prove missing exact symbols block downstream inventory/loading in a structured way when the preflight
path is enabled.
- LangGraph tests prove provider mismatch, such as requested `polygon` against configured `alpaca`, blocks downstream
inventory/loading before data-source query construction.
- LangGraph tests prove a successful preflight passes `resolved_provider`, `instrument_type`, and `bar_type` into
downstream tool requests.
- LangGraph tests prove `called_tools` contains only `data_discover_symbols` when preflight fails.
- Allowlist tests fail closed if `data_discover_symbols` is removed from state.

### Slice F: Provider Catalog Adapters

- Add a provider-catalog adapter interface so tests can inject fake provider-scoped instrument catalogs.
- Add an Alpaca-backed adapter implementation only behind explicit read-only provider-discovery policy.
- Extend the Slice C discovery service to support `source="provider"` and provider-enriched `source="merged"` through
registered adapters.
- Normalize provider symbols into the provider's canonical form and the platform compatibility form where needed,
including Alpaca crypto pair spelling such as `BTC/USD`.
- Preserve raw provider symbol separately as `raw_symbol`.
- Filter by `active_only`, `tradable_only`, `query`, and `limit`.
- Support exact-symbol validation against provider catalogs without requiring the symbol to already have local bars.
- Add an unsupported-provider failure path so future provider work is explicit rather than silently falling back to
Alpaca or local data.
- Add provider mismatch tests before adapter lookup so unsupported-but-requested providers fail with
`provider_not_configured` when the configured provider is different.

Acceptance evidence:

- Tests use fake provider clients; no network calls in normal test runs.
- Missing credentials, disabled policy, and provider failures return structured Data Agent envelopes.
- Provider discovery does not use broker order APIs.
- A fake second provider test proves provider selection is driven by adapter registration, not Data Agent graph branches.

### Slice G: Workflow and Handoff Use

- Update Data Agent workflow docs to show exact-symbol discovery as mandatory preflight before inventory, quality, and
loading in composed Data Agent workflows.
- Do not make symbol discovery a required supervisor handoff yet. It is planning context for choosing bounded symbols,
not evidence that a selected data window is complete.
- Optionally add a future supervisor planning slot for `symbol_discovery_report` after the supervisor has a real planning
loop.

Acceptance evidence:

- Docs distinguish symbol discovery from data inventory and from research strategy discovery.
- The user guide documents example calls for provider-scoped Alpaca stock and crypto instruments.

## Non-Goals

- No backtests.
- No live broker mutation.
- No order placement.
- No raw SQL MCP tool.
- No unbounded full-exchange dumps by default.
- No guarantee that a discovered provider symbol has historical bars for a requested timeframe/window; users must still
run `data_get_inventory`, `data_summarize_quality`, and possibly `data_ensure_loaded`.

## Recommended Initial Vertical Slice

Build the provider-resolution spine and existing-tool validation first:

```text
DataProviderContext
  -> provider mismatch validation
  -> provider-aware inventory/quality/ensure validation
  -> DataSymbolDiscoveryRequest
  -> local/configured symbol query
  -> exact-symbol existence status when symbols are supplied
  -> symbol_discovery_report envelope
  -> MCP registration
  -> Data Agent mandatory preflight graph
```

Then add provider catalog adapters, starting with Alpaca, once the provider context and MCP shape are stable. A later
Polygon implementation should be exposed by registering and configuring a Polygon provider adapter; the Data Agent graph
should not need provider-specific branches.
