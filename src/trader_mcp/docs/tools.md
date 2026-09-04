# MCP Tool Catalogue

This is the canonical catalog for the currently registered research-agent MCP tools. Tool names, descriptions, groups,
and capability flags are defined in `src/trader_mcp/constants.py`; owner lookup is defined in
`src/trader_research/governance/ownership.py`.

Every tool returns a shared `ToolEnvelope` through MCP `structuredContent` and text content. See
[contracts](contracts.md) for detailed request and artifact schemas.

Owner labels in this catalog describe executable tool allowlists/stewardship only. The governance model separates canonical
artifact authority into `domain_owner`, `producer_tool`, `requested_by` and `actor`; these catalog labels do not replace
that provenance and do not authenticate the caller. Approved target decisions are defined in
[agent roles and authority](../../trader_agents/docs/roles_and_authority.md#approved-decision-boundaries).

## Backing Service Packages

MCP adapters live in `trader_mcp`; deterministic tool behavior lives in bounded `trader_research` packages.

| MCP family | Backing service package |
| --- | --- |
| Research Coordinator session and decision evidence | `trader_research.governance.agentic` |
| Data Agent tools | `trader_research.data` |
| Knowledge tools | `trader_research.knowledge` |
| Quantitative Methods math tools | `trader_research.methodology` |
| Implementation registry | `trader_research.experiments` |
| Coding Workspace | `trader_research.coding` |
| Immutable specifications | `trader_research.experiments` |
| Backtest/result/comparison tools | `trader_research.experiments` |
| Optimisation engines and ledger | `trader_research.experiments` |
| Tracking projections | `trader_research.experiments` |
| Experiment protocol proposals | `trader_research.governance.orchestration` over the canonical Experiments store |
| Evaluation tools | `trader_research.review` |
| Adversarial tools | `trader_research.review` |
| ML Agent deployment tools | `trader_research.ml` plus the optional lazy `trader_mlflow` inference adapter |

## Support Tools

| Tool | Owner | Side effect | Purpose |
| --- | --- | --- | --- |
| `mcp_health` | MCP Server | `read_only` | Return MCP server health and registered tool names. |
| `mcp_get_config` | MCP Server | `read_only` | Return server policy, capability flags, artifact root, research artifact store runtime, and tool metadata. |

## Orchestration Surface

There is no registered high-level agent or workflow-execution tool. The model-backed runtime is a Python boundary in
`trader_agents.runtime`; its Coordinator, Data Research, and Strategy Engineering loops each receive an isolated MCP
client dynamically narrowed by role, phase, immutable session scope, approval policy, mutation lifecycle, and budget.
This keeps every deterministic Data, implementation, Coding Workspace, admission, and evidence contract visible.

The agentic slice has a narrow Research Coordinator evidence surface. These operations create and
resolve the immutable operator-approved session boundary, append public coordinator decisions, and dereference exact
canonical evidence. They do not themselves run a model, dispatch a specialist, approve mutations, or persist prompts,
hidden reasoning, raw messages, or complete tool transcripts. Resume state belongs to the separately configured
LangGraph checkpointer, not to MCP or the canonical research store.

## Research Coordinator Evidence Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `research_create_agent_session` | `local_mutating` | Canonical `research_session` ref. | Exact replay is idempotent; conflicting content under the same session ID fails closed. |
| `research_get_agent_session` | `read_only` | Validated session payload and canonical ref. | Resolves an exact ID or canonical URI. |
| `research_record_agent_decision` | `local_mutating` | Canonical `agent_decision_receipt` ref. | Enforces admitted program/model identities, cumulative budgets, canonical evidence, append-only branch sequence, and terminal-stop rules. |
| `research_get_agent_decision` | `read_only` | Validated public decision receipt and canonical ref. | Returns public evidence only, never private model state. |
| `research_read_artifact` | `read_only` | Governed record metadata, payload hash, bounded payload, and canonical ref. | Requires an exact registered artifact type and rejects owner drift or payloads above the requested bound. |

## Data Agent Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `data_discover_symbols` | `read_only` | Symbol discovery report payload. | Provider-catalog discovery requires explicit policy. |
| `data_get_inventory` | `read_only` | `dataset_manifest` payload. | Reads bounded local/event-store inventory only. |
| `data_summarize_quality` | `read_only` | `data_quality_report` payload. | Reports gaps, coverage, and completeness. |
| `data_create_research_snapshot` | `local_mutating` | Canonical `dataset_manifest` and `data_quality_report` refs. | Runs the same exact inventory/quality scope and persists both Data-domain records for resumable workflows. |
| `data_ensure_loaded` | `local_mutating` | Costed acquisition plan or canonical `data_load_evidence` plus dataset/quality payloads. | Provider backfill requires a matching prior dry-run `acquisition_plan_id`, an estimate within the session `max_loading_cost`, and runtime-bound operation/requester/actor lineage. Actual sample/backfill mutation also requires `TRADER_MCP_ALLOW_DATA_LOADING=true` and a canonical artifact store. Prepared operations never automatically repeat a provider call: complete post-load evidence recovers a missing terminal receipt, while ambiguous state fails closed for reconciliation. |

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
| `knowledge_create_method_card_draft` | `local_mutating` | DB-backed canonical method-card draft preserving field-level methodology evidence and validation lineage. |
| `knowledge_publish_method_card` | `local_mutating` | Approved method card. |
| `knowledge_update_method_card_status` | `local_mutating` | Retired method-card status update. |
| `knowledge_validate_citations` | `read_only` | Citation validation report. |
| `math_list_method_contracts` | `read_only` | Maintained method contract catalog. |
| `math_validate_method_contract` | `read_only` | Method contract validation result. |
| `math_register_method_implementation` | `local_mutating` | `method_implementation_manifest` or `research://postgres/...` ref. |
| `math_run_indicator_fixtures` | `local_mutating` | Indicator validation report. |
| `math_run_signal_fixtures` | `local_mutating` | Signal validation report. |
| `math_run_signal_diagnostics` | `local_mutating` | Signal diagnostic report. |
| `math_run_multiple_testing_report` | `local_mutating` | Multiple-testing report. |
| `math_generate_cpp_kernel` | `local_mutating` | C++ kernel manifest. |
| `math_compile_kernel` | `local_mutating` | Compile/build evidence. |
| `math_package_method_artifact` | `local_mutating` | Validated `method_package_manifest` or `research://postgres/...` ref. |
| `research_register_optimization_objective` | `local_mutating` | Content-addressed closed-input objective implementation. |
| `research_validate_optimization_objective` | `local_mutating` | Objective source/fixture validation report. |

Quantitative Methods tools do not fetch market data, create strategies, run backtests, or promote strategies.
They also do not invoke a model or author Python. A Quantitative Methods agent produces an accepted implementation
brief; Strategy Engineering performs model-directed source authoring through the isolated Coding Workspace surface and
submits the resulting inert package to the independent Experiments admission tools.

Methodology work uses the knowledge tool family as a staged review path: register a source reference, ingest and
index the whole document into schema-v2 evidence units, retrieve or scan source units, discover methodology candidates,
assemble target-conditioned claim spans into family-role evidence packets, synthesize nullable methodology fields from
one or more cited spans, validate field attribution and readiness, create a canonical draft card, and
publish only after explicit approval. Candidate, evidence-packet, extraction, and validation artifacts are
research-artifact-store records; complete method-card payloads are knowledge-store records with compact derived search
summaries. Persisted method cards can be marked `rejected` or `superseded` through
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
- Composite claim-graph methodology work remains in Notion's
  [Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84). Maintenance continues for
  correctness, persistence integrity, citation validity, security, and regressions affecting existing supported
  workflows.

## ML Agent Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `ml_create_deployment_manifest` | `local_mutating` | `ml_deployment_manifest`. | Pins passed model/feature evidence, adapter identity, raw output contract, inference policy/scope, parity fixture, and backtest/paper eligibility. It contains no trading thresholds or sizing policy. |
| `ml_validate_deployment` | `local_mutating` | `ml_deployment_validation_report`. | Rechecks immutable lineage and adapter configuration, loads the pinned model, and executes parity. Requires `TRADER_MCP_ALLOW_ML_RUNTIME=true`. |

Both tools require a configured `ResearchArtifactStore`; no filesystem fallback exists. The first tool does not load a
model, but it rejects unknown or unavailable adapter profiles. The second is the controlled model-loading boundary.
Neither tool writes to MLflow, changes an alias, starts a service, grants live eligibility, or mutates broker state.

## Experiment Design Agent Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `research_create_experiment_protocol_proposal` | `local_mutating` | Canonical Experiments-owned `experiment_protocol_proposal` ref. | Requires an approved objective, a complete structured design, exact canonical implementation/Data inputs, explicit requester and the registered Experiment Design actor. It persists requested approvals only and is idempotent for exact replay. |

The operation validates canonical types, ownership, producer metadata, status, payload hashes, implementation kind,
Data scope/quality agreement and optional optimisation validation before saving. It cannot approve a material
assumption, register the approved protocol, execute an experiment or overwrite conflicting proposal evidence.

## Strategy Engineering Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
| `research_list_strategy_templates` | `read_only` | Strategy template catalog. | Maintained template metadata only. |
| `research_list_risk_manager_templates` | `read_only` | Risk-manager template catalog. | Real maintained entrypoints and parameter metadata; not an execution identity. |
| `research_search_implementations` | `read_only` | Bounded implementation summaries. | Searches maintained metadata plus canonical admitted versions; source is never returned. |
| `research_get_implementation` | `read_only` | Exact implementation metadata and admission evidence. | Source is returned only when the request explicitly enables the bounded coding context. |
| `research_compare_implementation` | `read_only` | Field-level compatibility evidence. | Reports matches, differences, and unknowns; Strategy Engineering retains the reuse/adapt/author decision. |
| `coding_create_workspace` | `local_mutating` | Exact workspace identity and policy. | Creates or reopens the content-addressed workspace for one attempt and build contract. |
| `coding_get_workspace` | `read_only` | Bounded workspace status. | Returns policy, files, checks, and lifecycle state without exposing host paths. |
| `coding_search_repository` | `read_only` | Bounded text matches. | Searches only approved roots in the pinned repository snapshot. |
| `coding_read_repository_file` | `read_only` | Bounded repository text. | Rejects path escape, unsupported file types, and oversized reads. |
| `coding_write_candidate_file` | `local_mutating` | Candidate file hash, size, and replay status. | Replaces one complete bounded file inside the candidate directory; a trusted or content-derived operation identity makes exact lost-response replay idempotent and rejects conflicting reuse. |
| `coding_read_candidate_file` | `read_only` | Bounded candidate text. | Reads only supported files inside the exact workspace. |
| `coding_resolve_dependencies` | `read_only` | Dependency-policy verdict. | Validates against the pinned image allowlist and never installs packages. |
| `coding_run_check` | `local_mutating` | Bounded check receipt. | Runs only named compile, Ruff, or pytest commands in a networkless, resource-bounded container; no host fallback exists. |
| `coding_package_candidate` | `read_only` | Inert candidate package identity, lineage, source hash, and file manifest. | Retains complete source in the immutable service-owned package without returning it through the model-facing envelope or importing/executing it. |
| `coding_destroy_workspace` | `local_mutating` | Destruction receipt and replay status. | Removes only the exact disposable workspace and retains a source-free tombstone so exact cleanup replay is safe. |
| `research_register_strategy_implementation` | `local_mutating` | `implementation_version`. | General callers provide direct source or a candidate package ID. Strategy Engineering may provide only the exact package ID; MCP resolves source internally and returns a source-free result. |
| `research_validate_strategy_implementation` | `local_mutating` | `implementation_validation_report`. | Static safety, interface, parameters, and deterministic fixture. |
| `research_register_risk_manager_implementation` | `local_mutating` | `implementation_version`. | Same direct-source or deterministic package-resolution intake for supplied or produced risk code. |
| `research_validate_risk_manager_implementation` | `local_mutating` | `implementation_validation_report`. | Backtest-only deterministic risk fixture. |

Maintained-template rows are discovery hints and are never directly reusable. Canonical versions become direct-reuse
candidates only when exact implementation evidence has a matching passed validation report. Compatibility comparison
is deterministic evidence for the model-backed specialist; it does not decide semantic equivalence or efficacy.

Coding Workspace tools are registered but fail closed until `TRADER_MCP_ALLOW_CODING_WORKSPACE=true` and the dedicated
workspace root, pinned repository revision, and pinned container image are configured. Repository reads are
read-only. Candidate writes are separate. Checks use no network, capabilities, privilege escalation, secrets, or
arbitrary shell, and candidate packaging is inert. The runner uses an exact Docker container identity and verifies its
removal after normal exit, failure, timeout, or output cutoff; unavailable or failed container execution never falls
back to the host. Registration and validation remain the independent admission boundary after packaging.

## Quant Research Supervisor Tools

| Tool | Side effect | Primary output | Notes |
| --- | --- | --- | --- |
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
| `research_register_experiment_workflow` | `local_mutating` | Canonical `research_objective`, `experiment_protocol` and `workflow_plan` refs. | Requires an approved objective/protocol, a ready matching plan and explicit workflow requester/actor. |
| `research_record_workflow_outcome` | `local_mutating` | Canonical terminal `workflow_outcome` ref. | Requires a resolvable registered plan, matching objective/protocol lineage, resolving pinned evidence refs and explicit workflow requester/actor. |

The specification and execution tools consume independently admitted implementation versions; they do not provide a
coding identity or transfer the reuse/adapt/author decision to the Supervisor. Candidate/stack creation and loose
`research_run_backtest` / `research_run_portfolio_backtest` request forms are not registered or implemented.

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
- Data, knowledge, math, implementation-catalogue, Coding Workspace, admission, specification, canonical backtest,
  optimisation, Experiment Design, Evaluation, Adversarial and orchestration-record tool families are registered.
- Backtest execution is separately gated by `TRADER_MCP_ALLOW_BACKTESTS`.
- Optimisation execution additionally requires `TRADER_MCP_ALLOW_OPTIMIZATION`.
- Optuna writes require `TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES` and `TRADER_MCP_ALLOW_OPTUNA_WRITES`.
- Tracking projection requires `TRADER_MCP_ALLOW_EXTERNAL_RESEARCH_WRITES` and
  `TRADER_MCP_ALLOW_EXPERIMENT_TRACKING_WRITES`.
- Deployment parity and model-backed backtest inference require `TRADER_MCP_ALLOW_ML_RUNTIME`; manifest creation is a
  DB-only operation and remains callable with that gate false.
- Data loading mutation is separately gated by `TRADER_MCP_ALLOW_DATA_LOADING`.
- Coding Workspace mutation and isolated checks are separately gated by `TRADER_MCP_ALLOW_CODING_WORKSPACE`; the
  configured container runtime must also be available for checks.
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

Higher-level orchestration composes the registered tools in this catalog through a fixed compiler/executor; it is not a
new generic MCP tool that bypasses their contracts. The Experiment Design operation persists proposal evidence; the
two workflow MCP tools persist approved governance records and do not execute the graph. Current implemented
orchestration state is recorded in [Product State](../../../docs/product_state.md#implemented-orchestration-at-a-glance);
remaining delivery dependencies are recorded in Notion's
[Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84).

None of those future surfaces should execute prompt text directly. AI-produced code is supplied as an explicit source
artifact and passes the same validation and backtest-only restrictions as handwritten code.

## Remaining Planned MLflow Tool Universe

The deployment tools above are registered. The tools in this section remain planned; agent orchestration must consume
only deterministic lifecycle capabilities that have been implemented and qualified.

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
| Monitoring | `ml_summarize_predictions`, `ml_compute_drift_report` | Reads persisted prediction events and writes bounded ML-owned reports outside the hot path. |

The side-effect vocabulary now includes `external_research_mutating`. `local_mutating` is accurate for Trader Postgres
records but not for creating runs, model versions, tags, or aliases on an external MLflow instance. The planned ML
contract uses that external class and separate default-off policy for MLflow writes,
training execution, and alias promotion. Runtime deployment remains outside agent mutation authority.

## Deferred Walk-Forward Tool Universe

No tool in this section is registered. These tools depend on the prospective experiment loop, model-backed strategy
integration, and the robustness evidence boundary.

| Planned tool | Owner | Intended side effect | Purpose |
| --- | --- | --- | --- |
| `research_create_walk_forward_plan` | Quant Research Supervisor Agent | `local_mutating` | Persist immutable folds, implementation/deployment ref, base backtest spec, search space, objective, costs, seeds, and compute budget. |
| `research_run_walk_forward_optimization` | Quant Research Supervisor Agent | Conservatively `external_research_mutating` | Execute bounded candidate selection and locked out-of-sample child runs; ML folds may create gated MLflow runs/model versions. |
| `research_get_walk_forward_results` | Quant Research Supervisor Agent | `read_only` | Return plan, fold, candidate, selection, child specification/run, and status refs without recomputation. |
| `evaluation_generate_walk_forward_report` | Evaluation Agent | `local_mutating` | Stitch untouched out-of-sample fold evidence and report performance, costs, coverage, dispersion, and blockers. |
| `adversarial_audit_walk_forward` | Adversarial Agent | `local_mutating` | Attack fold/window boundaries, neighboring selections, stability, costs, concentration, degradation, search budget, and selection bias. |

The optimiser records procedural evidence but does not evaluate its own robustness. Evaluation and Adversarial tools
consume the immutable run independently, cannot rewrite selections, and cannot promote a strategy/model. Chronological
walk-forward validation used for ML correctness is not deferred; repeated optimisation and its independent audit remain
planned capabilities.
