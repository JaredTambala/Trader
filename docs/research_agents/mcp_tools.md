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
| ML Agent tools (planned, not registered) | `trader_research.ml` plus an optional `trader_mlflow` integration adapter |

## Support Tools

| Tool | Owner | Side effect | Purpose |
| --- | --- | --- | --- |
| `mcp_health` | MCP Server | `read_only` | Return MCP server health and registered tool names. |
| `mcp_get_config` | MCP Server | `read_only` | Return server policy, capability flags, artifact root, research artifact store runtime, and tool metadata. |

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
| `knowledge_ingest_documents` | `local_mutating` | Ingestion report, schema-v2 evidence-unit refs, embedding refs. |
| `knowledge_get_ingestion_status` | `read_only` | Source and ingestion status summary. |
| `knowledge_list_sources` | `read_only` | Registered source listing. |
| `knowledge_search_methods` | `read_only` | Approved method-card search results. |
| `knowledge_list_method_card_sets` | `read_only` | Stable method-card set summaries. |
| `knowledge_get_method_card_set` | `read_only` | Method-card set revision history. |
| `knowledge_retrieve_evidence` | `read_only` | Evidence retrieval report with lexical/vector metadata. |
| `knowledge_get_evidence_chunks` | `read_only` | Bounded dereferenced evidence-unit text. |
| `knowledge_discover_methodology_candidates` | `local_mutating` | DB-backed methodology candidate refs. |
| `knowledge_assemble_methodology_evidence` | `local_mutating` | DB-backed role-labeled methodology evidence packet. |
| `knowledge_extract_methodology_fields` | `local_mutating` | DB-backed methodology field-extraction report. |
| `knowledge_validate_methodology_candidate` | `local_mutating` | DB-backed methodology candidate validation report. |
| `knowledge_create_method_card_draft` | `local_mutating` | Draft method card. |
| `knowledge_create_rich_method_card_draft` | `local_mutating` | DB-backed rich method-card draft preserving field-level methodology evidence. |
| `knowledge_publish_method_card` | `local_mutating` | Approved method card. |
| `knowledge_update_method_card_status` | `local_mutating` | Retired method-card status update. |
| `knowledge_validate_citations` | `read_only` | Citation validation report. |
| `math_list_method_contracts` | `read_only` | Maintained method contract catalog. |
| `math_validate_method_contract` | `read_only` | Method contract validation result. |
| `math_register_method_implementation` | `local_mutating` | `method_implementation_manifest` or `research://postgres/...` ref. |
| `math_run_indicator_fixtures` | `local_mutating` | Indicator validation report. |
| `math_run_signal_fixtures` | `local_mutating` | Signal validation report. |
| `math_generate_python_method` | `local_mutating` | Quarantined generated source plus registration/validation artifacts. |
| `math_run_signal_diagnostics` | `local_mutating` | Signal diagnostic report. |
| `math_run_multiple_testing_report` | `local_mutating` | Multiple-testing report. |
| `math_generate_cpp_kernel` | `local_mutating` | C++ kernel manifest. |
| `math_compile_kernel` | `local_mutating` | Compile/build evidence. |
| `math_package_method_artifact` | `local_mutating` | Validated `method_package_manifest` or `research://postgres/...` ref. |

Quantitative Methods tools do not fetch market data, create strategies, run backtests, or promote strategies.

Rich methodology work uses the knowledge tool family as a staged review path: register a source reference, ingest and
index the whole document into schema-v2 evidence units, retrieve or scan source units, discover methodology candidates,
assemble target-conditioned claim spans into family-role evidence packets, synthesize nullable rich fields from one or
more cited spans, validate field attribution and readiness, create a rich draft card, and
publish only after explicit approval. Candidate, evidence-packet, extraction, and validation artifacts are
research-artifact-store records; rich method-card payloads are knowledge-store method-card records with shallow
projections for existing method-card consumers. Persisted method cards can be marked `rejected` or `superseded` through
the lifecycle status tool; retired records remain auditable in storage but are hidden from normal method search and
approved-card checks. Stable method-card sets group immutable draft and approved revision rows so operators can inspect
current approved cards and revision history without aggregating by volatile card IDs. Legacy method-card rows without
explicit set lineage are invalid; the tools do not synthesize compatibility set IDs for old Postgres payloads.

### Knowledge Tool Functional Position

The registered knowledge tools are supported and remain the canonical way to create and query the Postgres-backed
knowledge base. They are not currently being expanded toward autonomous book-scale methodology interpretation.

- Source registration, complete-document ingestion, evidence-unit embeddings, lexical/vector retrieval, bounded text
  dereferencing, and source/ingestion inspection are operational maintenance surfaces.
- Candidate, packet, claim-span, extraction, validation, method-card set, draft, publication, and lifecycle tools are
  operational for bounded methodologies when the source provides sufficient target-bound evidence.
- A passed controlled regression does not imply that an arbitrary book can be reduced to one method card. Composite
  frameworks spanning multiple chapters, method families, or ordered components remain a documented limitation.
- Blocked extraction is valid output. Operators must not repair missing evidence through title overrides, invented
  fields, publication, or generated code.
- Composite claim-graph methodology work is deferred under tracker item 33AC. Maintenance continues for correctness,
  persistence integrity, citation validity, security, and regressions affecting existing supported workflows.

## Quant Research Supervisor Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `research_list_strategy_templates` | `read_only` | Strategy template catalog. | Maintained template metadata only. |
| `research_create_strategy_candidate` | `local_mutating` | Strategy candidate manifest and generated source refs. | Consumes validated signal method packages or, for bounded maintained templates such as `pairs_mean_reversion`, approved rich method cards. |
| `research_validate_strategy_candidate` | `local_mutating` | Strategy candidate validation report. | Runs deterministic source/runtime smoke validation. |
| `research_run_backtest` | `local_mutating` | Backtest run bundle and `backtest_run_ref`. | Execution requires `TRADER_MCP_ALLOW_BACKTESTS=true`. |
| `research_run_portfolio_backtest` | `local_mutating` | Structured portfolio bundle and `portfolio_backtest_run_ref`. | Requires a passed strategy/risk stack validation report, configured research artifact store, and `TRADER_MCP_ALLOW_BACKTESTS=true`. |
| `research_get_backtest_results` | `read_only` | Backtest result summary and artifact paths. | Reads persisted run bundles only. |
| `research_compare_backtest_results` | `local_mutating` | `comparison_report`. | Compares explicit persisted run refs; does not execute backtests. |
| `research_list_risk_manager_templates` | `read_only` | Risk-manager template catalog. | Generation targets for backtest-only risk managers. |
| `research_create_risk_manager_candidate` | `local_mutating` | Risk-manager candidate manifest and generated source refs. | Backtest-only source artifact; approved rich risk cards may supply explicit threshold provenance. |
| `research_validate_risk_manager_candidate` | `local_mutating` | Risk-manager candidate validation report. | Runs deterministic source/runtime smoke validation. |
| `research_create_strategy_risk_stack` | `local_mutating` | Strategy/risk stack manifest. | Requires passed strategy and risk-manager validation reports. |
| `research_validate_strategy_risk_stack` | `local_mutating` | Strategy/risk stack validation report. | Runs deterministic multi-asset fixture validation before portfolio backtests. |

Supervisor tools consume specialist-owned artifacts but must not forge them. Portfolio backtests remain deterministic
research artifacts and do not control brokers or live trading.

## Evaluation Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `evaluation_generate_performance_report` | `local_mutating` | `evaluation_report` with `report_kind="performance_report"`. | Reads persisted backtest bundles and optional data-quality evidence. |

## Capability Flags And Gates

The config envelope reports static registration flags plus runtime policy:

- Broker-mutating and raw SQL tools are not registered.
- Data, knowledge, math, strategy, risk-manager, strategy/risk stack, backtest, and evaluation tool families are
  registered.
- Backtest execution is separately gated by `TRADER_MCP_ALLOW_BACKTESTS`.
- Data loading mutation is separately gated by `TRADER_MCP_ALLOW_DATA_LOADING`.
- Provider-catalog symbol discovery is separately gated by symbol-provider discovery policy.
- Mutating method/strategy/risk/portfolio/evaluation MCP flows require a configured or injected research artifact store.
  Production refs use `research://postgres/{artifact_type}/{artifact_id}`.

## Planned Tool Ownership

The agent registry contains planned allowlist entries that are not all registered MCP tools yet, including hypothesis,
ML, adversarial, attribution, recommendation, experiment-runner, broader evaluation critique, and portfolio/risk backtest
surfaces. Treat this file's registered catalog as the
current MCP availability source.

The next planned tool work is not additional knowledge extraction. It is:

- immutable registration and validation of handwritten or AI-produced strategy and risk-manager implementations
- reproducible backtest specifications that consume validated implementation versions and Data Agent manifests
- ML model-version lineage, including model hashes, feature/data refs, training-code and environment provenance,
  evaluation evidence, and lifecycle state
- robustness/adversarial reports linked to immutable baseline backtests, including cost, perturbation, split, and
  concentration attacks

None of those future surfaces should execute prompt text directly. AI-produced code is supplied as an explicit source
artifact and passes the same validation and backtest-only restrictions as handwritten code.

## Planned MLflow Tool Universe

No tool in this section is registered yet. Tracker tasks 39A-39J define the intended deterministic services; task 40
adds agent orchestration only after they are proven.

| Phase | Planned tools | Intended side effect and gate |
| --- | --- | --- |
| MLflow runtime | `ml_get_runtime`, `ml_health`, `ml_list_experiments` | `read_only`; one configured tracking/registry authority, no caller-supplied URI. |
| Feature engineering | `ml_create_feature_set`, `ml_validate_feature_set` | Trader DB mutation only; writes immutable feature specs and validation. |
| Training data | `ml_create_training_dataset`, `ml_create_time_series_split_plan` | Trader DB mutation and bounded materialization; consumes explicit Data Agent refs. |
| Training pipeline | `ml_register_training_pipeline`, `ml_validate_training_pipeline`, `ml_create_training_spec` | Trader DB mutation; source/package registration never executes prompt text. |
| Fitting | `ml_run_training` | External research mutation plus bounded compute; requires separate MLflow-write and training gates. |
| Run lineage | `ml_get_training_run`, `ml_reconcile_mlflow_run` | Read-only MLflow access plus Trader DB reconciliation. |
| Model evaluation | `ml_evaluate_model`, `ml_compare_model_versions` | Bounded compute plus Trader/MLflow evaluation artifacts; no trading-profitability verdict. |
| Registry | `ml_register_model_version`, `ml_get_model_version`, `ml_list_model_versions`, `ml_resolve_model_alias` | Registry writes use the external research mutation class; reads are read-only. |
| Promotion | `ml_assign_model_alias` | External research mutation with an independent default-off promotion gate and passed promotion report. |
| Deployment evidence | `ml_create_deployment_manifest`, `ml_validate_deployment` | Trader DB mutation; creates version-pinned backtest/paper configuration, not a live service change. |
| Monitoring | `ml_summarize_predictions`, `ml_compute_drift_report` | Reads persisted prediction events and writes bounded ML-owned reports outside the hot path. |

The side-effect vocabulary must be extended before MLflow-mutating tools are registered. `local_mutating` is accurate
for Trader Postgres records but not for creating runs, model versions, tags, or aliases on an external MLflow instance.
The planned contract uses an external research mutation class and separate default-off policy for MLflow writes,
training execution, and alias promotion. Runtime deployment remains outside agent mutation authority.

## Deferred Walk-Forward Tool Universe

No tool in this section is registered. Tasks 58-59 follow task 57, ML model-backed strategy integration through 39I,
and robustness tasks 44/46.

| Planned tool | Owner | Intended side effect | Purpose |
| --- | --- | --- | --- |
| `research_create_walk_forward_plan` | Quant Research Supervisor Agent | `local_mutating` | Persist immutable folds, implementation/deployment ref, base backtest spec, search space, objective, costs, seeds, and compute budget. |
| `research_run_walk_forward_optimization` | Quant Research Supervisor Agent | Conservatively `external_research_mutating` | Execute bounded candidate selection and locked out-of-sample child runs; ML folds may create gated MLflow runs/model versions. |
| `research_get_walk_forward_results` | Quant Research Supervisor Agent | `read_only` | Return plan, fold, candidate, selection, child specification/run, and status refs without recomputation. |
| `evaluation_generate_walk_forward_report` | Evaluation Agent | `local_mutating` | Stitch untouched out-of-sample fold evidence and report performance, costs, coverage, dispersion, and blockers. |
| `adversarial_audit_walk_forward` | Adversarial Agent | `local_mutating` | Attack fold/window boundaries, neighboring selections, stability, costs, concentration, degradation, search budget, and selection bias. |

The optimiser records procedural evidence but does not evaluate its own robustness. Evaluation and Adversarial tools
consume the immutable run independently, cannot rewrite selections, and cannot promote a strategy/model. Chronological
walk-forward validation inside 39C/39F is not deferred; only repeated optimisation and its audit are tasks 58-59.
