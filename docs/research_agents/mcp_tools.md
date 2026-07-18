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
| Implementation registry | `trader_research.implementations` |
| Immutable specifications | `trader_research.specifications` |
| Backtest/result/comparison tools | `trader_research.backtests` |
| Optimisation engines and ledger | `trader_research.optimization` |
| Tracking projections | `trader_research.tracking` |
| Evaluation tools | `trader_research.evaluation` |
| Adversarial tools | `trader_research.adversarial` |
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
| `research_register_optimization_objective` | `local_mutating` | Content-addressed closed-input objective implementation. |
| `research_validate_optimization_objective` | `local_mutating` | Objective source/fixture validation report. |

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
| `research_list_risk_manager_templates` | `read_only` | Risk-manager template catalog. | Metadata for optional code producers; not an execution identity. |
| `research_register_strategy_implementation` | `local_mutating` | `implementation_version`. | Content-addressed source; methodology provenance is optional. |
| `research_validate_strategy_implementation` | `local_mutating` | `implementation_validation_report`. | Static safety, interface, parameters, and deterministic fixture. |
| `research_register_risk_manager_implementation` | `local_mutating` | `implementation_version`. | Same intake for supplied or produced risk code. |
| `research_validate_risk_manager_implementation` | `local_mutating` | `implementation_validation_report`. | Backtest-only deterministic risk fixture. |
| `research_create_strategy_specification` | `local_mutating` | `strategy_specification`. | Binds validated code and tunable parameters; forbids data scope. |
| `research_validate_strategy_specification` | `local_mutating` | Strategy-spec validation report. | Rechecks version and source hash. |
| `research_create_risk_stack_specification` | `local_mutating` | Ordered `risk_stack_specification`. | Pins explicit validated managers and thresholds. |
| `research_validate_risk_stack_specification` | `local_mutating` | Risk-stack validation report. | Rechecks order, parameters, and hashes. |
| `research_create_backtest_specification` | `local_mutating` | `backtest_specification`. | Binds one Data Agent scope, quality snapshot, costs, initial state, and seed. |
| `research_validate_backtest_specification` | `local_mutating` | Backtest-spec validation report. | Fails closed on snapshot/upstream drift. |
| `research_run_backtest_specification` | `local_mutating` | Canonical DB-backed `backtest_run`. | Requires `TRADER_MCP_ALLOW_BACKTESTS=true`. |
| `research_get_backtest_results` | `read_only` | Canonical run payload and bundle. | Requires a DB run ID/URI; no path lookup. |
| `research_compare_backtest_results` | `local_mutating` | `comparison_report`. | Compares explicit canonical run refs. |
| `research_get_optimizer_runtime` | `read_only` | Built-in/optional engine profiles and health. | Does not initialize provider state. |
| `research_create_parameter_optimization_plan` | `local_mutating` | Provider-neutral plan. | Pins selection spec, sealed holdout, objective, dimensions, constraints, seed, budget. |
| `research_run_parameter_optimization` | `local_mutating` | Run plus complete trial ledger. | Requires backtest and optimisation gates; Optuna has additional gates. |
| `research_get_parameter_optimization_results` | `read_only` | Canonical run and trials. | Works when optional provider is absent. |
| `research_run_parameter_optimization_variants` | `local_mutating` | Immutable child optimisation runs. | Executes only Adversarial-requested optimisation variants. |
| `research_project_experiment_tracking` | `external_research_mutating` | Non-authoritative projection report. | Derived, idempotent, and separately gated. |

Candidate/stack creation and loose `research_run_backtest` / `research_run_portfolio_backtest` request forms are not
registered. Maintained or method-generated source is a producer input to the same implementation registry.

## Evaluation Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `evaluation_generate_parameter_optimization_report` | `local_mutating` | Untouched-holdout optimisation Evaluation report. | Verifies selected specification, sealed holdout hash, and risk evidence. |

## Adversarial Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `adversarial_create_parameter_optimization_audit_plan` | `local_mutating` | Immutable attack plan. | Declares attacks without executing or changing the baseline. |
| `adversarial_generate_parameter_optimization_audit` | `local_mutating` | Robustness report. | Judges supplied variant/stress refs and cannot rewrite selection. |

## Capability Flags And Gates

The config envelope reports static registration flags plus runtime policy:

- Broker-mutating and raw SQL tools are not registered.
- Data, knowledge, math, implementation, specification, canonical backtest, optimisation, Evaluation, and Adversarial
  tool families are registered.
- Backtest execution is separately gated by `TRADER_MCP_ALLOW_BACKTESTS`.
- Optimisation execution additionally requires `TRADER_MCP_ALLOW_OPTIMIZATION`.
- Optuna writes require `TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES` and `TRADER_MCP_ALLOW_OPTUNA_WRITES`.
- Tracking projection requires `TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES` and
  `TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES`.
- Data loading mutation is separately gated by `TRADER_MCP_ALLOW_DATA_LOADING`.
- Provider-catalog symbol discovery is separately gated by symbol-provider discovery policy.
- Mutating method/strategy/risk/portfolio/evaluation MCP flows require a configured or injected research artifact store.
  Production refs use `research://postgres/{artifact_type}/{artifact_id}`.

## Planned Tool Ownership

The agent registry contains planned allowlist entries that are not all registered MCP tools yet, including hypothesis,
ML, broader robustness, attribution, recommendation, and broader Evaluation critique
surfaces. Treat this file's registered catalog as the
current MCP availability source.

The next planned tool work is not additional knowledge extraction. It is:

- ML model-version lineage, including model hashes, feature/data refs, training-code and environment provenance,
  evaluation evidence, and lifecycle state
- broader robustness variants linked to immutable baseline backtests, including cost, perturbation, split, and
  concentration attacks

None of those future surfaces should execute prompt text directly. AI-produced code is supplied as an explicit source
artifact and passes the same validation and backtest-only restrictions as handwritten code.

## Planned MLflow Tool Universe

No tool in this section is registered yet. Tracker tasks 39A-39J define the intended deterministic services; task 40
adds agent orchestration only after they are proven.

| Phase | Planned tools | Intended side effect and gate |
| --- | --- | --- |
| MLflow runtime | `ml_get_runtime`, `ml_health`, `ml_list_training_experiments` | `read_only`; one configured ML training/registry authority, no caller-supplied URI. |
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

The side-effect vocabulary now includes `external_research_mutating`. `local_mutating` is accurate for Trader Postgres
records but not for creating runs, model versions, tags, or aliases on an external MLflow instance. The planned ML
contract uses that external class and separate default-off policy for MLflow writes,
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
