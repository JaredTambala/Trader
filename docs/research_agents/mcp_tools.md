# MCP Tool Catalog

This is the canonical catalog for the currently registered research-agent MCP tools. Tool names, descriptions, groups,
and capability flags are defined in `src/trader_mcp/constants.py`; owner lookup is defined in
`src/trader_research/agents.py`.

Every tool returns a shared `ToolEnvelope` through MCP `structuredContent` and text content. See
[tool_contracts.md](tool_contracts.md) for detailed request and artifact schemas.

## Backing Service Packages

MCP adapters live in `trader_mcp`; deterministic tool behavior lives in bounded `trader_research` packages.

| MCP family | Backing service package |
| --- | --- |
| Data Agent tools | `trader_research.data` |
| Knowledge tools | `trader_research.knowledge` |
| Quantitative Methods math tools | `trader_research.methods` |
| Strategy candidate tools | `trader_research.strategy_candidates` |
| Risk-manager candidate tools | `trader_research.risk_managers` |
| Backtest/result/comparison tools | `trader_research.backtests` |
| Evaluation tools | `trader_research.evaluation` |

## Support Tools

| Tool | Owner | Side effect | Purpose |
| --- | --- | --- | --- |
| `mcp_health` | MCP Server | `read_only` | Return MCP server health and registered tool names. |
| `mcp_get_config` | MCP Server | `read_only` | Return server policy, capability flags, artifact root, and tool metadata. |

## Data Agent Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `data_discover_symbols` | `read_only` | Symbol discovery report payload. | Provider-catalog discovery requires explicit policy. |
| `data_get_inventory` | `read_only` | `dataset_manifest` payload. | Reads bounded local/event-store inventory only. |
| `data_summarize_quality` | `read_only` | `data_quality_report` payload. | Reports gaps, coverage, and completeness. |
| `data_ensure_loaded` | `local_mutating` | Load/backfill evidence plus dataset/quality payloads. | Actual sample/backfill mutation requires `TRADER_MCP_ALLOW_DATA_LOADING=true`. |

## Quantitative Methods Tools

| Tool | Side effect | Primary output |
| --- | --- | --- |
| `knowledge_register_source` | `local_mutating` | `knowledge_source_manifest` or knowledge-store ref. |
| `knowledge_ingest_documents` | `local_mutating` | Ingestion report, chunk refs, embedding refs. |
| `knowledge_get_ingestion_status` | `read_only` | Source and ingestion status summary. |
| `knowledge_list_sources` | `read_only` | Registered source listing. |
| `knowledge_search_methods` | `read_only` | Approved method-card search results. |
| `knowledge_retrieve_evidence` | `read_only` | Evidence retrieval report with lexical/vector metadata. |
| `knowledge_get_evidence_chunks` | `read_only` | Bounded dereferenced evidence chunk text. |
| `knowledge_create_method_card_draft` | `local_mutating` | Draft method card. |
| `knowledge_publish_method_card` | `local_mutating` | Approved method card. |
| `knowledge_validate_citations` | `read_only` | Citation validation report. |
| `math_list_method_contracts` | `read_only` | Maintained method contract catalog. |
| `math_validate_method_contract` | `read_only` | Method contract validation result. |
| `math_register_method_implementation` | `local_mutating` | `method_implementation_manifest`. |
| `math_run_indicator_fixtures` | `local_mutating` | Indicator validation report. |
| `math_run_signal_fixtures` | `local_mutating` | Signal validation report. |
| `math_generate_python_method` | `local_mutating` | Quarantined generated source plus registration/validation artifacts. |
| `math_run_signal_diagnostics` | `local_mutating` | Signal diagnostic report. |
| `math_run_multiple_testing_report` | `local_mutating` | Multiple-testing report. |
| `math_generate_cpp_kernel` | `local_mutating` | C++ kernel manifest. |
| `math_compile_kernel` | `local_mutating` | Compile/build evidence. |
| `math_package_method_artifact` | `local_mutating` | Validated `method_package_manifest`. |

Quantitative Methods tools do not fetch market data, create strategies, run backtests, or promote strategies.

## Quant Research Supervisor Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `research_list_strategy_templates` | `read_only` | Strategy template catalog. | Maintained template metadata only. |
| `research_create_strategy_candidate` | `local_mutating` | Strategy candidate manifest and generated source. | Consumes validated signal method packages. |
| `research_validate_strategy_candidate` | `local_mutating` | Strategy candidate validation report. | Runs deterministic source/runtime smoke validation. |
| `research_run_backtest` | `local_mutating` | Backtest run bundle and `backtest_run_ref`. | Execution requires `TRADER_MCP_ALLOW_BACKTESTS=true`. |
| `research_get_backtest_results` | `read_only` | Backtest result summary and artifact paths. | Reads persisted run bundles only. |
| `research_compare_backtest_results` | `local_mutating` | `comparison_report`. | Compares explicit persisted run refs; does not execute backtests. |
| `research_list_risk_manager_templates` | `read_only` | Risk-manager template catalog. | Generation targets for backtest-only risk managers. |
| `research_create_risk_manager_candidate` | `local_mutating` | Risk-manager candidate manifest and generated source. | Validation and stack use are later tasks. |

Supervisor tools consume specialist-owned artifacts but must not forge them. Portfolio/risk stack validation and
risk-scoped portfolio backtests are planned follow-ons.

## Evaluation Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `evaluation_generate_performance_report` | `local_mutating` | `evaluation_report` with `report_kind="performance_report"`. | Reads persisted backtest bundles and optional data-quality evidence. |

## Capability Flags And Gates

The config envelope reports static registration flags plus runtime policy:

- Broker-mutating and raw SQL tools are not registered.
- Data, knowledge, math, strategy, risk-manager, backtest, and evaluation tool families are registered.
- Backtest execution is separately gated by `TRADER_MCP_ALLOW_BACKTESTS`.
- Data loading mutation is separately gated by `TRADER_MCP_ALLOW_DATA_LOADING`.
- Provider-catalog symbol discovery is separately gated by symbol-provider discovery policy.

## Planned Tool Ownership

The agent registry contains planned allowlist entries that are not all registered MCP tools yet, including hypothesis,
ML, adversarial, attribution, recommendation, experiment-runner, broader evaluation critique, risk-manager validation,
strategy/risk stack validation, and portfolio/risk backtest surfaces. Treat this file's registered catalog as the
current MCP availability source.
