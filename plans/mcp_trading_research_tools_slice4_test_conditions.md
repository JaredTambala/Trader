# Slice 4 Test Conditions: Research Foundations and Supervisor Skeleton

## Purpose

Slice 4 covers chunks 17-22 of the MCP trading research tools plan. It establishes the research package boundary,
typed research-domain handoff contracts, and the first Quant Research Supervisor LangGraph identity:

```text
research contracts move out of trader.*
research helpers/tool modules move under trader_research
research-domain schemas serialize stable specialist handoffs
Quant Research Supervisor graph starts
Data Agent artifact references are consumed without raw data access
missing specialist artifacts become explicit blockers
```

This document is the intermediate acceptance contract for the slice. Do not mark a Slice 4 chunk `Done` in
`plans/mcp_trading_research_tools_plan.md` unless the relevant conditions below are covered by tests, docs, or
reproducible command output.

## Pre-Slice Checkpoint

- Verify the completed Slice 3 work before adding Slice 4 behavior:
  - `uv run pytest tests/test_data_quality_service.py tests/test_data_ensure_loaded.py tests/test_mcp_data_workflow.py tests/test_langgraph_data_workflow.py tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py`
  - `uv run ruff check src/trader/market_data_queries.py src/trader/data_quality.py src/trader_research src/trader_mcp src/trader_agents tests/test_data_quality_service.py tests/test_data_ensure_loaded.py tests/test_mcp_data_workflow.py tests/test_langgraph_data_workflow.py tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_market_data_queries.py tests/test_data_inventory.py tests/test_sql_boundaries.py tests/test_agent_identities.py tests/test_research_contracts.py tests/test_mcp_adapters.py tests/support`
  - `uv run python -c "import trader_mcp; import trader_mcp.server as s; s.create_server()"`
  - `uv run python -c "from trader_agents.data_agent import build_data_agent_inventory_graph, build_data_agent_workflow_graph"`
  - `git diff --check`
- Commit Slice 3 as its own checkpoint before implementing Slice 4.
  - Suggested commit message: `Complete Data Agent MCP workflow`

## Global Slice Conditions

- No Slice 4 production code may expose raw SQL, arbitrary code execution, broker mutation, live trading, backtests,
  strategy execution, or LLM calls.
- Do not register broad Quant Research, Math Coder, ML, Hypothesis, Evaluation, or Adversarial MCP tools in this slice.
  `server.list_tools()` should remain limited to support tools and Data Agent tools unless a compatibility test proves a
  temporary legacy command is intentionally outside the MCP surface.
- `trader_agents` must not import `trader.data`, `trader.market_data_queries`, `trader_research.data`, or
  `trader_mcp.server`.
- `trader_research` may depend on platform primitives in `trader`, but `trader` must not depend on `trader_research`,
  `trader_mcp`, or `trader_agents` except for explicitly documented temporary compatibility shims.
- Legacy `trader.research` and `trader.tools.*` modules must be deleted, moved, or reduced to thin compatibility shims
  with tests that make the temporary nature explicit.
- All new source functions and classes must use Google-style docstrings.
- Tests must use DuckDB, in-memory state, checked-in sample data, or pure dataclass fixtures. Real Postgres data is
  optional manual evidence only and must not be required for automated tests.
- Prompt-injection defense is enforced by typed schemas, allowlisted artifact types, bounded research requests,
  structured handoff records, and treating all symbols, artifact paths, user text, and specialist outputs as data.

## Chunk 17 Conditions: Move Shared Tool Contracts

- `src/trader_research/contracts.py` is the canonical home for `ToolEnvelope`, `SideEffect`, agent ownership metadata,
  artifact references, error helpers, and JSON serialization helpers used by research tools.
- `src/trader/tools/contracts.py` is deleted or reduced to a compatibility shim that imports from
  `trader_research.contracts`; it must not contain duplicated contract logic.
- Existing CLIs and tests that should remain active import the canonical research contracts directly unless a temporary
  shim is intentionally being tested.
- Envelope JSON produced by migrated legacy CLIs still parses and preserves:
  - `ok`
  - `command`
  - `agent_owner`
  - `side_effect`
  - `schema_version`
  - `generated_at`
  - `data`
  - `artifacts`
  - `warnings`
  - `errors`
- Required tests:
  - contract serialization round-trips through `dict` and JSON without losing agent ownership or side-effect class
  - failed envelopes contain structured errors and `ok=false`
  - any temporary `trader.tools.contracts` shim returns the same objects as `trader_research.contracts`
  - package-boundary tests prove the canonical contract implementation no longer lives under `src/trader/`

## Chunk 18 Conditions: Move Research Helpers

- Useful parts of `src/trader/research.py` are moved or re-created under `src/trader_research/` with imports pointed at
  platform primitives rather than MCP or LangGraph code.
- `src/trader/research.py` is deleted or reduced to a compatibility shim that is explicitly tested and documented as
  temporary.
- Research helper behavior that existed before the move remains stable for supported CLIs and tests:
  - experiment IDs and run IDs remain deterministic where they were previously deterministic
  - artifact path conventions remain compatible or migration notes identify the change
  - JSON output from CLIs remains machine-readable
- Required tests:
  - migrated helper tests pass through the new `trader_research` import path
  - compatibility-shim tests, if any, prove old imports forward to the new implementation
  - CLI smoke tests still parse arguments and produce valid JSON for non-network, fixture-backed paths
  - package-boundary tests prove helpers do not import `trader_mcp` or `trader_agents`

## Chunk 19 Conditions: Move Research Tool Modules

- Move or re-home the still-useful portions of `trader.tools.artifacts`, `trader.tools.discovery`,
  `trader.tools.promotion`, `trader.tools.recommendations`, and `trader.tools.suites` under `trader_research`.
- Keep MCP-specific request parsing, server registration, transport details, and LangGraph state out of these migrated
  modules.
- `src/trader/tools/` is deleted when feasible. If any module remains, it must be a tested compatibility shim with no
  independent business logic.
- Existing research CLIs import from `trader_research` and keep returning deterministic JSON envelopes or reports for
  fixture-backed paths.
- Required tests:
  - legacy research-tool behavior that remains in scope passes through the new import path
  - old import shims, if any, are parity-tested and documented as temporary
  - discovery, promotion, recommendation, and suite helpers do not register MCP tools as import side effects
  - package-boundary tests prove no migrated research module imports `trader_mcp.server` or LangGraph agent modules

## Chunk 20 Conditions: Research Domain Schemas

- Add schemas, expected as `src/trader_research/domain.py`, for specialist artifacts and supervisor handoffs.
- Prefer stdlib dataclasses unless validation complexity justifies Pydantic. Regardless of implementation, schemas must
  serialize to JSON-compatible dictionaries without non-deterministic or unserializable fields.
- Minimum Slice 4 schema coverage:
  - bounded research request
  - data requirement
  - specialist handoff record
  - specialist artifact slot/status
  - experiment plan skeleton
  - strategy candidate skeleton
  - backtest run reference
  - evaluation report reference
  - robustness report reference
  - recommendation report reference
  - research verdict
  - placeholders or reference types for hypothesis cards, indicator metadata/statistical reports, feature manifests,
    model cards, prediction artifacts, and drift reports
- Every handoff record must preserve:
  - producing `agent_owner`
  - artifact type
  - artifact path or embedded structured payload
  - source request or parameters
  - provenance references
  - warnings
  - blockers
  - side-effect class, when derived from a tool envelope
- Required tests:
  - every schema serializes to JSON-compatible data and round-trips from that data where supported
  - missing agent owner, missing artifact type, missing request bounds, and unsupported artifact types fail validation
  - Data Agent dataset manifest and data-quality handoffs can be represented without copying raw bars into supervisor
    state
  - blocker and warning lists preserve structured codes/messages rather than free-form-only text

## Chunk 21 Conditions: Quant Research Supervisor Graph Skeleton

- Add a Quant Research Supervisor LangGraph identity, expected as `src/trader_agents/quant_research.py`.
- Supervisor identity metadata must be distinct from the Data Agent and use the ownership label
  `Quant Research Supervisor Agent`.
- Supervisor state must include:
  - bounded research request
  - supervisor identity
  - handoff ledger
  - specialist artifact slots
  - blockers
  - warnings
  - errors
  - ordered called-tool list, even if empty in this slice
  - public status suitable for docs/tests
- The graph can start and record a bounded research request without invoking LLMs, MCP tools, backtests, or specialist
  graphs.
- Missing required specialist artifacts must be explicit blockers, not silent `None` values or optimistic pass states.
- Required tests:
  - graph construction imports cleanly
  - initial invocation records the bounded request and supervisor identity
  - invocation with no specialist artifacts returns blockers for missing Data, Math Coder, Hypothesis, Evaluation, and
    Adversarial evidence as appropriate for the request
  - optional ML artifacts are represented distinctly from required artifacts
  - `called_tools` remains empty unless a future slice intentionally adds allowed supervisor MCP calls
  - boundary scan proves `src/trader_agents/quant_research.py` does not import platform data/query modules or
    `trader_mcp.server`

## Chunk 22 Conditions: Supervisor Consumes Data Agent Handoff

- Add a supervisor node or deterministic state update path that accepts Data Agent manifest and quality references
  produced by the Data Agent graph.
- The supervisor must consume artifact references or structured summaries only. It must not fetch raw bars, call
  `data_get_inventory`, call `data_summarize_quality`, query the event store, or import core market-data query helpers.
- Accepted Data Agent handoffs must preserve:
  - `agent_owner="Data Agent"`
  - dataset manifest ID or artifact reference
  - data-quality report ID or artifact reference
  - requested symbols, asset class, timeframe, and window
  - completeness status
  - warnings and blockers from the Data Agent result
  - provenance back to the Data Agent envelope or graph state
- Required tests:
  - a valid Data Agent manifest and quality handoff populates the supervisor Data slot and handoff ledger
  - incomplete data quality creates a supervisor blocker instead of being treated as ready data
  - missing manifest, missing quality report, mismatched windows, unsupported artifact types, or forged non-Data-Agent
    owners are rejected with structured errors or blockers
  - Data Agent warnings are preserved in supervisor state
  - supervisor still records missing Math Coder, Hypothesis, Evaluation, and Adversarial artifacts as blockers after
    accepting the Data Agent handoff

## Full Slice 4 Evidence

- Add a reproducible evidence test that:
  - runs the Data Agent graph against the test-only stdio MCP sample server or an equivalent fixture-backed MCP client
  - obtains a dataset manifest and data-quality report through the Data Agent path
  - converts those outputs into typed Data Agent handoff records
  - invokes the Quant Research Supervisor graph with a bounded research request and those handoffs
  - verifies the supervisor state preserves Data Agent ownership and artifact references
  - verifies missing specialist artifacts become structured blockers
  - verifies no raw bars are present in supervisor state
  - verifies no MCP tools, backtests, LLMs, broker mutations, or raw SQL paths are invoked by the supervisor
- Add import-boundary evidence that:
  - `trader` does not import `trader_research`, `trader_mcp`, or `trader_agents`, except for any explicitly temporary
    compatibility shims under test
  - `trader_research` does not import `trader_mcp` or `trader_agents`
  - `trader_agents` does not import platform data/query internals when an MCP/Data Agent handoff exists
- Update `docs/research_agents/mcp_trading_research_tools.md` and
  `docs/research_agents/agents_mcp_user_guide.md` with the exact pytest command and the asserted supervisor handoff
  fields.
- Mark chunks 17-22 `Done` only when the migration, schema, graph, handoff, and boundary tests are all in place.

## Final Slice Verification

Run these commands before considering Slice 4 complete:

```bash
uv run pytest tests/test_research_contracts.py tests/test_tool_contracts.py tests/test_research.py tests/test_research_tools.py tests/test_research_domain.py tests/test_quant_research_supervisor.py tests/test_supervisor_data_handoff.py tests/test_langgraph_data_workflow.py tests/test_mcp_data_workflow.py tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_agent_identities.py tests/test_mcp_adapters.py tests/test_sql_boundaries.py tests/test_package_boundaries.py
uv run ruff check src/trader_research src/trader_mcp src/trader_agents run_compare_results.py run_research_recommendations.py run_research_discovery.py run_prepare_paper_promotion.py run_research_experiment.py run_data_quality.py run_market_data_backfill.py tests/test_research_contracts.py tests/test_tool_contracts.py tests/test_research.py tests/test_research_tools.py tests/test_research_domain.py tests/test_quant_research_supervisor.py tests/test_supervisor_data_handoff.py tests/test_langgraph_data_workflow.py tests/test_mcp_data_workflow.py tests/test_mcp_first_tool_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_agent_identities.py tests/test_mcp_adapters.py tests/test_sql_boundaries.py tests/test_package_boundaries.py tests/support
uv run python -c "import trader_research, trader_mcp, trader_agents"
uv run python -c "from trader_agents.quant_research import build_quant_research_supervisor_graph"
uv run python -c "import trader_mcp; import trader_mcp.server as s; s.create_server()"
git diff --check
```

## Out of Scope for Slice 4

- New Math Coder, ML, Hypothesis, Evaluation, or Adversarial MCP tools.
- Strategy catalog, strategy candidate validation, backtest execution, attribution, evaluation reports, robustness
  reports, recommendations, or full experiment running.
- LLM-backed planning, hidden scratchpads, or autonomous prompt routing.
- Live trading, broker mutation, raw SQL tools, user-provided SQL, or direct data fetching by the supervisor.
- Requiring the developer's real Postgres database for automated tests.
- Calendar-aware data-quality classification; this remains a later backlog item.
