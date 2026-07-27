# Research Agent Architecture

Trader separates core trading runtime code from research tooling, MCP transport, and LangGraph agent orchestration.
Research agents produce deterministic artifacts for inspection and backtesting; they do not control live trading.

## Layer Model

| Package | Responsibility | Must not own |
| --- | --- | --- |
| `trader` | Core runtime platform: market data, event store, brokers, portfolio, strategy/risk interfaces, runtime service, backtesting, metrics, operator primitives. | Research services, MCP schemas, LangGraph agents. |
| `trader_standard` | Maintained implementations of core interfaces: indicators, signals, strategies, and risk managers. | Experiment orchestration, MCP adapters, agent state. |
| `trader_research` | Deterministic research services, implementation/specification registries, canonical backtests, optimisation ledgers, tracking projections, diagnostics, and reports. | MCP transport, live broker control. |
| `trader_mcp` | MCP server, tool registration, JSON adapters, server policy/config metadata, dependency injection into research services. | Research business logic, agent decision state. |
| `trader_agents` | LangGraph identities, state schemas, policy routing, tool allowlists, and handoff wiring over MCP tools. | Direct platform mutation or bypassing MCP when a tool exists. |

## `trader_research` Capability Packages

`trader_research` mirrors the bounded capability style used by the core `trader` package. Stable package-level exports
are canonical public surfaces; broad top-level service modules are not compatibility shims and should not be
reintroduced.

| Package | Responsibility |
| --- | --- |
| `trader_research.foundation` | Dependency-light identity/digest helpers, typed application outcomes and failures, artifact values, and persistence ports. |
| `trader_research.governance` | Agent tool allowlists, decision authorities, artifact-domain authority, and typed cross-agent handoffs. |
| `trader_research.infrastructure.postgres` | Canonical Postgres artifact adapter plus registered context-owned projection writers. |
| `trader_research.infrastructure.providers` | Optional provider SDK adapters for Alpaca, Optuna, and MLflow. |
| `trader_research.data` | Data Agent discovery, inventory, quality, provider context, and explicit loading services. |
| `trader_research.methodology` | Quantitative Methods contracts, registry access, fixtures, diagnostics, multiple testing, kernels, and method-package handoffs. |
| `trader_research.experiments` | Public facade for content-addressed implementations, immutable specifications, canonical backtests, provider-neutral optimization, and non-authoritative tracking projections. |
| `trader_research.review` | Evaluation reports plus independent Adversarial audit planning and robustness judgments over immutable Experiment reads. |
| `trader_research.knowledge` | Knowledge-source registration, ingestion, indexing, retrieval, methodology candidates, method cards, and citation validation. |
| `trader_research.methodology.implementation` | Python method implementation registration, quarantine generation, and deterministic fixtures. |

## Bounded Context Architecture

`trader_research` contains five domain contexts, a narrow Foundation/Governance kernel, and an outer Infrastructure
layer. The current package structure is a hard-cutover architecture: deleted root hubs and former top-level context
paths have no compatibility aliases or fallback readers.

The pre-refactor inventory, dependency findings, migration sequence and qualification evidence remain available in the
[deprecated tracker snapshot](../../plans/mcp_trading_research_tools_plan.md) and Git history. The
[active capability roadmap](../../plans/research_capability_roadmap.md) maps TRR-1 through TRR-12 to the accepted
bounded-context baseline without repeating the historical migration narrative here.

### Context Map

```text
src/trader_research/
  foundation/
    identity.py                 # Stable IDs and content digests only
    errors.py                   # Typed application failures and blockers
    results.py                  # Typed application outcomes
    artifacts/
      domain.py                 # Artifact refs and immutable records
      store.py                  # Store protocol and in-memory test adapter
  governance/
    ownership.py                # Agent allowlists and decision-authority declarations
    artifacts.py                # Artifact-type domain-authority declarations
    handoffs.py                 # Cross-agent request/handoff value objects
  data/
    domain.py                   # Inventory, manifest, quality, and load models
    inventory.py
    quality.py
    loading.py
    catalog.py
  knowledge/
    sources.py
    chunking.py
    ingestion.py
    retrieval.py
    evidence_assembly.py
    methodology_candidates.py
    methodology_extraction.py
    methodology_validation.py
    method_card_drafting.py
    method_card_sets.py
    method_card_catalog.py
    domain/                     # Source, chunk, evidence, candidate, and card models
    store.py                    # KnowledgeStore port and in-memory adapter
    postgres_store.py           # Postgres knowledge adapter
  methodology/
    contracts.py                # Computational method contracts and registry entries
    registry.py
    diagnostics.py
    multiple_testing.py
    implementation/
      manifest.py
      registration.py
      fixtures.py
      generation.py
      io.py
    kernels.py
    packaging.py
  experiments/
    implementations/            # Generic executable implementation versions
    specifications/             # Strategy, risk-stack, and backtest specifications
    backtests/                  # Canonical execution and result queries
    optimization/               # Provider-neutral plans, engines, ledger, execution
    tracking/                   # Non-authoritative projection application service
  review/
    evaluation/                 # Independent evidence interpretation
    adversarial/                # Independent attack planning and judgment
  infrastructure/
    postgres/
      artifact_store.py
      projections/              # Projection writers grouped by owning context
    providers/
      alpaca.py
      optuna.py
      mlflow.py
```

This tree is directional architecture, not a requirement to create one file for every label. Module creation is justified
by a cohesive responsibility and an enforceable import rule, not by line-count targets alone.

| Context | Owns | May depend on | Must not depend on |
| --- | --- | --- | --- |
| Foundation | Stable identity, typed failures, artifact refs/records, store ports. | Python standard library. | Data, knowledge, methodology, experiments, review, MCP, agents, optional providers. |
| Governance | Tool allowlists, decision authority, artifact-domain mapping, and cross-agent handoff values. | Foundation. | Service implementations, stores, platform runtime, MCP transport. |
| Data | Dataset discovery, manifests, quality, bounded loading application services. | Foundation and core `trader` data ports. | Knowledge, methodology, experiments, review, MCP. |
| Knowledge | Sources, evidence units, retrieval, evidence assembly, candidate validation, and the single canonical method-card lifecycle. | Foundation. | Method implementation registries, experiments, review, MCP. |
| Methodology engineering | Computational method contracts, diagnostics, fixtures, and optional source-backed code producers. | Foundation and the public approved-card read port from Knowledge. | Knowledge storage internals, experiment internals, MCP. |
| Experiments | Generic implementation admission, immutable specifications, backtests, optimization, and tracking projection requests. | Foundation, core `trader` runtime ports, and immutable Data artifact contracts where required. | Knowledge and methodology implementation internals, Evaluation, Adversarial, MCP, Optuna, MLflow. |
| Review | Evaluation and Adversarial plans/reports over immutable experiment evidence. | Foundation and public Experiment query ports. | Experiment mutation internals, Knowledge, optional providers, MCP. |
| Infrastructure | Postgres stores/projections and Alpaca, Optuna, and MLflow adapters. | The ports and domain payloads it implements. | MCP registration and agent policy. |

The allowed high-level import graph is:

```text
trader_mcp / trader_agents
  -> context application facades
  -> foundation ports and values

review -> experiments public read API -> foundation
methodology -> knowledge approved-card read API -> foundation
data -> foundation
knowledge -> foundation
experiments -> data public artifact API -> foundation
infrastructure -> context ports
```

No context may import another context's private module. `__init__.py` files expose small, explicit application facades
and value objects; they do not eagerly import optional providers or use lazy loading to mask a cycle.

### Public And Transport Boundaries

Business operations return typed application results or raise typed boundary errors carrying stable codes, blockers,
and warnings. `trader_mcp` owns conversion to `ToolEnvelope`, side-effect metadata, and transport JSON.
This preserves deterministic direct services while making MCP presentation an adapter concern.

Canonical MCP tool names and canonical Postgres artifact payloads are product contracts, not Python import
compatibility surfaces. There are no old-to-new Python modules, aliases, dual writes, fallback readers, translated
development rows, or canonical filesystem authority.

Postgres persistence uses a registry of typed projection writers. The generic artifact store saves the canonical record
and invokes only registered projection writers. Projection modules know their context's payload, while the generic store
does not contain an `if/elif` list of every artifact type. The MCP composition root assembles the store, context
services, provider adapters, and projection registry.

### Canonical Vocabulary

Code and active documentation use these naming rules:

- **Methodology**: a source-backed description of a computational or trading idea before executable code exists.
- **Method card**: the one evidence-backed, citeable methodology record. "Rich method card" is retired because richness
  is no longer a variant. A compact summary is a derived read model, never another writable card.
- **Method implementation**: a computational indicator/signal implementation and its deterministic fixtures. It is not
  a strategy implementation version unless admitted through the generic implementation registry.
- **Implementation version**: content-addressed executable strategy, risk-manager, or optimization-objective code.
- **Specification**: immutable configured behavior that references validated implementation versions.
- **Run**: execution of a validated specification or optimization plan.
- **Report**: an immutable interpretation or validation result; it does not mutate the artifact it reviews.
- **Candidate**: used only for a discovered methodology candidate. Retired strategy/risk candidate terminology must not
  return.
- **Optimization**: canonical spelling in Python, MCP tools, artifact types, and SQL. Prose may use "optimisation", but
  must quote executable names exactly.

### Boundary Enforcement

The current package structure is protected by executable constraints:

- the changed context has a documented public facade and owner
- new cross-context imports follow the allowed graph and are covered by AST boundary tests
- domain/application code does not import MCP, LangGraph, Postgres, Optuna, MLflow, or provider SDKs
- direct behavior tests pass before MCP adapter and Postgres integration tests
- canonical writes remain Postgres-first and reconcile with typed projections
- no compatibility module, alias, dual write, fallback reader, or data migration is introduced
- deleted behavior is removed from root scripts, active docs, tests, tool catalogs, and operations guidance together
- `ruff`, `compileall`, `mypy`, targeted tests, package boundaries, docs tests, and `git diff --check` pass

A contributor should be able to start from this context map, enter through a public facade, and follow one-way
dependencies to domain logic and outward ports without reading MCP registration or a central orchestration module.

### Data Context Boundary

`trader_research.data` is the sole application facade for Data Agent callers. Its internal modules have cohesive
responsibilities: `domain` owns request, provider-context, policy, and catalog-port values; `catalog` resolves provider
semantics and builds symbol-discovery reports; `inventory` builds deterministic dataset manifests; `quality` wraps
read-only quality evidence; and `loading` coordinates policy-gated inspection, sample loading, and bounded backfill
through core platform APIs. The retired `data/services.py` module has no alias or reader.

Provider SDK code does not belong to the Data context. The read-only Alpaca symbol catalog implementation lives at
`trader_research.infrastructure.providers.alpaca`, imports the Data port values, and loads the Alpaca SDK lazily. MCP
constructs that adapter at the composition root and injects it through `DataSymbolDiscoveryPolicy`. Data domain and
application modules do not import Alpaca, MCP, agents, Knowledge, Methodology, Experiments, or Review.

### Experiments Context Boundary

`trader_research.experiments` is the single outer application facade for implementation admission, immutable strategy,
risk-stack and backtest specifications, canonical backtest execution and lookup, provider-neutral parameter
optimization, and explicit experiment-tracking projection. The internal `implementations`, `specifications`,
`backtests`, `optimization`, and `tracking` packages express lifecycle ownership without becoming separate outer
contexts. Their former top-level package paths are deleted and have no aliases.

Optimization separates provider protocols and built-in grid/random engines from plan construction, sequential
orchestration, ledger validation, result queries, trial execution, and Adversarial-requested variants. Canonical plans,
runs, trials, selections, and projection reports remain Postgres artifacts with unchanged payloads and deterministic
identities. `trader_research.infrastructure.providers.optuna` implements the optimization engine protocol;
`trader_research.infrastructure.providers.mlflow` implements the tracking sink protocol. Neither adapter is imported by
the Experiments context, and canonical reads continue to work without either optional package or provider state.

### Review Context Boundary

`trader_research.review` contains separate `evaluation` and `adversarial` specialist facades behind one package entry
point. Review services persist only Review-owned audit plans and reports. The former top-level `evaluation` and
`adversarial` package paths are deleted without aliases.

Review imports only `trader_research.experiments.reads`. Its `ExperimentEvidenceReader` exposes immutable canonical
backtest evidence plus revalidated optimization plans, runs, and complete trial ledgers. It exposes no implementation
registration, specification creation, backtest execution, optimization execution, selection mutation, or tracking
projection operation. Static mutation-boundary tests also reject any Review `save_artifact` call targeting an
Experiment-owned artifact type.

### Composition Roots

`trader_mcp` composes every domain operation through the public `data`, `knowledge`, `methodology`, `experiments`, and
`review` facades. It obtains persistence and provider implementations from `infrastructure.postgres` and explicit
`infrastructure.providers` modules, then injects those adapters through public protocols. `trader_agents` imports only
Foundation and Governance contracts; it does not import domain service implementations or bypass MCP tools.

Knowledge and Methodology facades explicitly export their application operations and composition ports, so MCP no
longer imports lifecycle, storage, extraction, or implementation internals. Foundation and Governance likewise expose
their public result, artifact-store, ownership, and handoff contracts at package level. AST tests prohibit deep bounded-
context imports from MCP and agents, prohibit undeclared context edges and cycles, and keep retired package paths absent.

MCP construction does not import the optional Optuna or MLflow packages. Their adapter modules inspect configuration and
package metadata without loading provider SDKs; SDK imports occur only when a gated provider operation actually needs
them. A clean-interpreter regression forcibly rejects every `optuna` and `mlflow` import while importing and constructing
the complete MCP server. Alpaca remains a core platform dependency through `trader.timeframes`; changing that core
boundary is outside this research-layer refactor.

### Refactor Record

The [research product state](product_state.md) records the accepted bounded-context baseline and the passed
`verification-57i-freeze-v6` Core/Trader-Postgres qualification. The
[active capability roadmap](../../plans/research_capability_roadmap.md) preserves compact legacy-task lineage. The
complete historical sequence remains available from the deprecated tracker's pinned Git snapshot.

## Control Plane And Execution Plane

The MCP server is the control plane. It starts over stdio, lists tools, exposes health/config metadata, declares
side-effect classes, and enforces coarse policy gates. It must be able to start without a valid trader runtime config,
Postgres connection, broker credential, or LLM configuration.

Tool execution is the execution plane. Tool calls lazily build or receive dependencies such as event stores, knowledge
stores, configs, backtest runners, and catalog providers. Execution failures return structured `ToolEnvelope` errors and
must not prevent MCP server startup.

## MCP And LangGraph Responsibilities

MCP is the deterministic tool boundary. MCP tools accept bounded JSON-compatible inputs, call deterministic services,
and return stable envelopes plus artifact refs.

MCP research artifact persistence is DB-first. Mutating methodology, implementation, specification, backtest,
optimisation, Evaluation, and Adversarial tools store canonical records in the configured Postgres research artifact
store and return `research://postgres/{artifact_type}/{artifact_id}` refs. Method cards are persisted as canonical
evidence-backed knowledge-store payloads. Canonical execution has no filesystem fallback and never uses a path as
product identity.

LangGraph is the agent identity and orchestration layer. Agent graphs decide which MCP tools are allowed, how state is
retained, how specialist handoffs are routed, and which artifact must be produced. Agent code should call MCP tools
rather than core platform internals when a tool exists.

## Higher-Level Orchestration Architecture

Orchestration is a cross-cutting control capability over deterministic tools, not the final step of a linear delivery
plan. It can coordinate capabilities that are already implemented while additional ML, robustness, review and
methodology tools develop independently.

The current operational baseline is deliberately limited:

- The Data Agent has bounded deterministic and LLM-policy tool-calling graphs.
- The Quant Research Supervisor graph validates a bounded request and supplied Data Agent handoffs, but does not call
  the registered implementation, specification, backtest, optimisation or review MCP tools.
- Quantitative Methods, ML, Evaluation, Adversarial and Hypothesis identity/allowlist definitions exist without
  complete specialist execution graphs.

ORCH-GOV removed the old artifact `agent_owner` map. Canonical records now carry bounded-context authority separately
from producer operation, requesting workflow and actor. MCP still exposes `agent_owner` as the intended tool allowlist
label; it is not canonical artifact provenance and is never used to infer caller identity.

### Decision Authority Model

Agents own bounded decisions. Domain contexts own canonical artifacts. Deterministic services execute approved inputs.

| Role | Exclusive decision authority | Explicit exclusion |
| --- | --- | --- |
| Research Coordinator | Which bounded workflow and prerequisites should happen next? | Experiment parameters, data fitness, variant findings and strategy-quality verdicts. |
| Data Agent | Is the explicit data scope available and fit for the proposed experiment? | Strategy logic, optimisation design and performance conclusions. |
| Experiment Design Agent | What fair, reproducible protocol should test the supplied strategy and risk stack? | Running the experiment, changing the protocol after results or judging quality. |
| Robustness Agent | Which assumptions and claims should be attacked, and what sensitivity did executed variants reveal? | Executing variants, mutating the baseline or issuing the overall quality verdict. |
| Evaluation Agent | What does the complete evidence support after data, costs, holdout, risk and robustness are considered? | Protocol repair, parameter selection, variant execution and workflow routing. |
| Quantitative Methods Agent | What optional source-backed or computational-method evidence can be supplied? | Concrete data scope, experiment execution and quality verdicts. |
| ML Agent | What optional model lifecycle and predictive evidence can be supplied? | Trading policy, risk approval and final strategy quality. |

No Backtest Agent, Optimisation Agent, Strategy Agent or Risk Agent is required for the supplied-implementation
workflow. Validators, runners, engines and risk pipelines are deterministic services. A separate Hypothesis Agent is
not on the core path while the experiment protocol can carry the explicit research question and falsification criteria.

The target control flow is:

```text
operator research brief with supplied strategy/risk refs
  -> Research Coordinator resolves prerequisites
  -> Data Agent produces scope and quality evidence
  -> deterministic services validate supplied implementations
  -> Experiment Design Agent proposes an experiment protocol
  -> operator approves material assumptions
  -> deterministic compiler creates immutable specifications
  -> workflow executor runs baseline, optimisation and sealed holdout
  -> Robustness Agent declares attacks
  -> workflow executor runs immutable variants
  -> Robustness Agent reports sensitivity findings
  -> Evaluation Agent issues the final research-quality assessment
  -> Research Coordinator reports refs, blockers and permitted next actions
```

ORCH-1 implements the provider-neutral orchestration contracts:

- `ResearchObjective`: the operator's bounded desired outcome and declared constraints.
- `ExperimentProtocol`: the proposed strategy/risk refs, Data requirements, baseline assumptions, costs, initial state,
  selection/holdout policy, tunable dimensions, objective, constraints, robustness requirements, evaluation questions
  and material approvals. It is immutable after approval.
- `CapabilityDefinition`: one registered action's domain, producer tool, required inputs, produced artifact types, side
  effects and policy gates.
- `WorkflowPlan`: a content-addressed graph of required capabilities, artifact slots, dependencies and approval points.
- `WorkflowStepResult`: the public tool envelope, produced artifact refs, warnings, blockers and retry classification.
- `SpecialistHandoff`: a domain-authority-preserving transfer of immutable artifact refs and bounded issues.
- `WorkflowOutcome`: a public summary of satisfied goals, unresolved blockers, review verdict refs and next permitted
  actions.

The implementation lives in `trader_research.governance.orchestration` and imports no service contexts. Contract
construction is deliberately fail closed:

- approved protocols require an approved decision for every material assumption;
- optimisation requires role-labelled selection data and a sealed holdout;
- capability snapshots declare domain, producer tool, side effect, artifact inputs/outputs, policy gates and accepted
  configuration keys, with no callable or provider object;
- artifact slots validate canonical artifact type, bounded-context owner and cardinality;
- workflow plans reject unknown capabilities, invented configuration, bad slot bindings, unresolved readiness gates
  and dependency cycles; and
- step results expose bounded public data, canonical artifact refs, issues, idempotency and retry classification rather
  than raw execution state.

`ResearchObjective`, `ExperimentProtocol`, `WorkflowPlan` and approval records have canonical artifact-type
declarations in the authority registry. ORCH-1 deliberately provides no persistence operation or MCP tool for them.
It also provides no capability registry, protocol compiler, executor or checkpointer. `WorkflowOutcome` remains a
target execution summary for ORCH-3; the ORCH-1 acceptance boundary ends at typed step results.

ORCH-2 implements the checkpointer without expanding that declaration layer into an executor. The
`trader_agents.checkpointing` package compiles one ready plan into a deterministic shell, interrupts at each ordered
step and accepts a validated external `WorkflowStepResult` on resume. It imports governance contracts but no MCP,
Data, Experiment, ML or Review implementation. ORCH-3 will supply the registry and executor that actually turn an
interrupt request into an MCP call.

The experiment protocol is a proposal until material assumptions are explicitly approved. The Experiment Design Agent
must not silently invent transaction costs, risk limits, optimisation dimensions, search budgets, data boundaries or
holdout policy. Missing choices become approval requirements or blockers. A deterministic compiler, not the agent,
turns the approved protocol into existing strategy, risk-stack, backtest and optimisation specifications.

Planning is target-artifact driven. A workflow asks which validated artifacts must exist to satisfy an objective, then
selects only registered capabilities that can produce them. It does not plan from legacy task numbers, invent tool
names, move Data Agent scope into another domain, override the approved experiment protocol or use prose to repair
failed evidence.

Reusable workflow templates provide the safe initial execution boundary. Examples include supplied implementation to
backtest evidence, parameter selection to sealed-holdout review, and immutable model deployment to model-backed
backtest. A bounded policy planner may later choose a template, resolve optional branches and request missing
specialist evidence. It cannot construct an unrestricted arbitrary graph or bypass a template's mandatory validation,
approval, Evaluation or Adversarial nodes.

### Domain Authority And Actor Identity

Canonical provenance must distinguish four concepts:

| Field | Meaning |
| --- | --- |
| `domain_owner` | The bounded context authoritative for the artifact contract and lifecycle. |
| `producer_tool` | The deterministic tool/service operation that created the artifact. |
| `requested_by` | The operator request or workflow-plan/run ref that required the operation. |
| `actor` | The operator or agent identity that proposed or routed the action. |

An agent may request or route an artifact without becoming its owner. The approved authority map is:

| Domain | Canonical artifacts |
| --- | --- |
| Data | Dataset manifests, quality reports and load evidence. |
| Knowledge/Methodology | Sources, evidence, method cards and method-validation artifacts. |
| Experiments | Implementations, validations, specifications, backtests, comparisons, optimisation plans/runs/trials and tracking projections. |
| ML | Feature, training, model-version, deployment and drift artifacts. |
| Review | Attribution, Evaluation, attack-plan and robustness artifacts. |
| Orchestration | Research objectives, workflow plans, approval requests, bounded handoff summaries and workflow outcomes only. |

`domain_owner` and `producer_tool` are required on every canonical `ResearchArtifactRecord`. `requested_by` and `actor`
are nullable for current direct service calls because MCP does not yet authenticate a workflow/caller. Typed
cross-agent handoffs require all four fields. ORCH-1 requires requester and actor in its orchestration values; ORCH-2
retains them in operational state, and ORCH-3 must carry them into orchestrated writes rather than infer either value
from MCP tool stewardship.

### Checkpoints And Evidence

Operational graph state and product evidence have separate authority:

| State | Purpose | Authority |
| --- | --- | --- |
| LangGraph checkpoint | Resume node position, bounded pending actions and retry state after interruption. | Operational only; replaceable and not evidence for a research claim. |
| Workflow plan/outcome summary | Expose the declared procedure, public decisions, blockers and terminal status. | Orchestration-domain bounded record, persisted only through an approved service boundary. |
| Tool-produced research artifact | Establish implementation, data, run, trial, evaluation or robustness evidence. | Canonical owning context and Trader Postgres. |
| Specialist handoff | Preserve artifact identity, domain authority, producer/request/actor provenance, warnings and blockers across graphs. | Governance contract; cannot change artifact authority. |

Checkpoints must not contain hidden reasoning, unrestricted prompts, credentials, feature matrices or copies of complete
artifact payloads. Resumption revalidates referenced product artifacts and capability configuration before continuing.
An idempotent tool result may be reused only when its canonical request identity and upstream hashes still match.

The implemented ORCH-2 checkpoint state is a strict whitelist: workflow/plan identity, plan digest, cursor, next
attempt, pending step, bounded attempt summaries, canonical handoff/artifact refs, bounded issues and result-content
digests. `WorkflowStepResult.public_data` is deliberately discarded before persistence. Public state is a second,
smaller projection that omits plan and idempotency digests. Plan digest is rechecked on every node; exact duplicate
result keys are ignored, while key reuse with different content and plan drift fail closed.

Persistence uses the maintained asynchronous LangGraph Postgres saver through the dedicated
`TRADER_AGENTS_CHECKPOINT_DSN`. Its checkpoint tables are operational infrastructure, may be deleted under an
operator retention policy, and must never be joined or projected as Trader research evidence. The saver performs its
own idempotent setup when explicitly requested. There is no fallback to the research artifact store, filesystem or
in-memory persistence in the configured product path.

### Composition Shape

Trader should not build one graph containing every possible research activity. The Research Coordinator composes small
specialist subgraphs and deterministic workflow templates through typed artifact slots:

```text
Data Agent ─────────────────────┐
validated supplied code ────────┼──> Experiment Design ──> approved protocol
optional Quant Methods/ML ──────┘                           │
                                                           v
                                                 deterministic execution
                                                           │
                                             Robustness findings ──> Evaluation
```

Adding a specialist capability extends the capability registry and one or more workflow templates. It does not require
rewriting a universal state machine. The active dependency graph and delivery status live in the
[capability roadmap](../../plans/research_capability_roadmap.md); current agent maturity lives in
[product_state.md](product_state.md).

## Canonical Method Card Architecture

The target architecture treats a method card as the canonical, evidence-backed representation of a trading or research
methodology. A method card is not a lightweight note and it is not a prompt artifact. It is the structured object that
answers: what is the method, what evidence supports each part of it, what data does it require, how is it computed, how
does it produce decisions, what assumptions make it valid, what can break it, and what downstream generation is allowed
to do with it.

Compact fields such as assumptions, inputs, outputs, and failure modes are derived from the canonical method card for
bounded search and citation responses. `MethodCardSummary` is a non-writable read model with no approval lifecycle,
persistence API, or independent identity. Any workflow requiring methodology evidence consumes the canonical card;
the summary cannot satisfy an evidence or provenance gate by itself.

Conceptually, the Quantitative Methods layer contains a pipeline of specialist capabilities:

| Capability | Question answered | Primary owner |
| --- | --- | --- |
| Source registrar | What source did the operator approve for ingestion, and what is its identity, type, hash, and access policy? | Quantitative Methods Agent |
| Ingestion/indexing | What complete source text is citeable, split into evidence units, embedded, and searchable? | Quantitative Methods Agent |
| Retrieval | Which evidence units are relevant to a query, method family, or discovered source term? | Quantitative Methods Agent |
| Candidate discovery | Where in the source is a candidate methodology described? | Quantitative Methods Agent |
| Evidence assembly | Do we have enough definition, formula, parameter, signal, assumption, validation, and failure evidence to understand the method? | Quantitative Methods Agent |
| Field extraction | Which closed schema fields can be populated from the assembled evidence? | Quantitative Methods Agent |
| Methodology validation | Are the populated fields source-backed, internally coherent, and sufficient for the stated family? | Quantitative Methods Agent |
| Curated method-card approval | Has a human or allowed policy explicitly accepted this method card for downstream use? | Quantitative Methods Agent |
| Strategy/risk generation | Can an approved method card drive a maintained bounded template? | Quant Research Supervisor Agent |
| Backtest and evaluation | What happened when a validated strategy/risk artifact was run over a Data Agent scope? | Quant Research Supervisor Agent and Evaluation Agent |

This separation matters because retrieval alone is not methodology understanding. Retrieval can say that an evidence
unit mentions some named method, model, indicator, rule, or instrument structure. It cannot by itself say that the source
provides enough formula, threshold, input, assumption, and failure-mode evidence to create a strategy-grade method card.
Candidate discovery and evidence assembly are the bridge between search and structured understanding.

The architecture is open-world for method targets and closed-world for evidence roles. Trader should not require a
registry entry for every named technique before it can understand a source. The system can discover a method name from a
heading, definition, equation label, table caption, query term, or repeated local phrase. What remains predefined is the
family-level evidence ontology: the kinds of source support that are needed to describe, implement, validate, or use a
method. A newly discovered technical indicator, statistical-arbitrage variant, options structure, sentiment feature, or
risk model is therefore processed through family evidence roles rather than a hardcoded target profile.

### Method Card State Model

The state model is intentionally staged:

```text
knowledge source
  -> full-document ingestion
  -> citeable evidence units and embeddings
  -> methodology candidate
  -> assembled evidence packet
  -> field extraction report
  -> methodology validation report
  -> method-card draft
  -> approved method card
  -> optional implementation producer
  -> content-addressed implementation registration and validation
  -> immutable strategy/risk/backtest specifications
  -> canonical backtest evidence
```

Each stage records a different kind of truth.

- A source record proves that a source reference exists and has operator metadata. It does not prove the document was
  ingested.
- An ingestion run proves that the source text was processed into schema-v2 evidence units and indexes. It does not
  prove a method was found. Legacy broad chunk artifacts are not translated and must be regenerated by reingestion.
- A methodology candidate proves that some span of evidence units may describe a method identity. It does not approve
  the method.
- An assembled evidence packet proves that the system found target-bound field-role evidence, such as definition,
  formula, entry rule, exit rule, assumption, validation, or limitation units. Role refs must contain role terms and an
  accepted binding to the discovered method identity; adjacent evidence from competing method labels remains visible as
  rejected diagnostics. It does not assert every field is populated.
- A field extraction report proves that closed schema fields were populated from specific evidence units. Unsupported
  fields stay null.
- A validation report proves that the candidate satisfies source, citation, family, target-bound evidence,
  source-backed identity, hash consistency, and readiness checks, or records why it does not.
- A draft method card is a review artifact. It is still not approved for strategy/risk generation.
- An approved method card is the durable methodology artifact that downstream tools may cite, package, or use to drive
  maintained templates.

The pipeline must fail closed at every boundary. If a tool cannot prove its own stage, it should write blockers and
stop the downstream transition rather than manufacturing a plausible card.

### Canonical Payload And Projections

The canonical method-card payload should be the full evidence-backed methodology model:

- identity and source context
- method family and supported domain extension blocks
- data requirements and required input series or entities
- formula, algorithm, model, or decision procedure
- parameters, defaults, thresholds, and warmup requirements when supported by evidence
- signal, entry, exit, ranking, sizing, or portfolio decision logic
- assumptions, limitations, failure modes, and monitoring requirements
- validation and backtest expectations
- implementation notes and edge cases
- field-level evidence refs for every populated claim
- source, chunk, locator, file-hash, and text-hash lineage
- validation lineage and approval status

Search-facing and compatibility-facing records are projections over that payload. For example, a method-card summary can
expose title, family, status, assumptions, inputs, outputs, failure modes, and evidence refs, but those fields should be
derived from populated canonical fields. A summary projection is not sufficient proof that a method can be implemented or
used in a strategy.

This is the durable storage shape:

```text
Postgres JSONB canonical method_card payload
  -> indexed projection columns for pgAdmin and search
  -> derived shallow summary for older APIs
  -> artifact refs for MCP/tool handoff
```

Filesystem artifacts are acceptable only as legacy exports or compatibility bundles. The canonical method-card record is
structured DB state.

### Evidence Assembly

Evidence assembly is the capability that the current architecture needs before extraction can be considered strong. It
should not merely take the top semantic matches. It should build a source-backed packet organized by field role.

The evidence assembler starts from a discovered method candidate, not from a prewritten target profile. It should infer
the candidate's likely family from local source evidence and then use that family's role ontology to search within the
ingested source. Method-specific labels are values found in the source; they are not required to exist in a maintained
catalog before the method can be described.

For a technical-indicator family candidate, useful evidence roles include:

- method definition and source-observed names or aliases
- input series, such as close price, return, volume, or high/low/close fields
- formula or algorithm
- lookback window, smoothing, normalization, warmup, and default parameters
- signal semantics, such as crossover, threshold, overbought, oversold, or band breach behavior
- failure modes, such as lag, whipsaw, non-stationarity, microstructure noise, or regime sensitivity
- validation requirements, such as no-lookahead, prefix behavior, fixture parity, or parameter sensitivity

For a statistical-arbitrage family candidate, useful evidence roles include:

- leg universe and pair or basket construction
- spread definition and hedge-ratio estimation
- relationship test, such as correlation, cointegration, stationarity, or residual diagnostics
- formation window and trading window
- entry and exit logic, including z-score or mean-reversion thresholds when present
- risk controls, such as stop loss, spread breakdown, concentration, liquidity, or borrow/cost assumptions
- failure modes, such as structural breaks, unstable hedge ratios, crowding, or transaction-cost erosion
- validation requirements, such as out-of-sample tests, walk-forward checks, residual stationarity, or turnover limits

Other families use the same pattern but different roles: options methods need instrument, legs, payoff, strike, expiry,
volatility and Greek evidence; sentiment methods need source, raw signal, entity mapping, aggregation, scoring, and bias
evidence; risk models need measure definition, data inputs, estimator, confidence/threshold semantics, and breach
handling evidence.

The assembled packet should record both found evidence and missing evidence. Missing evidence is useful product state:
it explains why a candidate cannot yet become a method card and guides retrieval, source ingestion, or human review.
The assembler can use deterministic lexical patterns, vector retrieval, headings, ordinals, equations, tables, and
citations to find role evidence, but it should not require or consult a hardcoded list of known method targets.

### Extraction And Enrichment

Extraction is allowed to populate only closed schema fields. It should be field-specific rather than generic. A
technical-indicator extractor should not write "technical indicator calculation evidence" into a formula field. It
should extract the actual formula or a concise source-backed formulation, attach the formula-bearing chunk, and leave the
field null when the formula is not present.

The architecture allows two extraction modes:

- deterministic extractors for high-confidence patterns, equations, tables, headings, aliases, and common method
  structures
- bounded enrichment adapters for harder source text, optionally using an LLM over the assembled evidence packet

Bounded enrichment is not autonomous method creation. It must follow these rules:

- The adapter receives only citeable evidence units and the closed output schema.
- It cannot request market data, strategy scopes, broker state, raw SQL, or hidden context.
- It must output field values with chunk IDs and concise claims.
- It must preserve nulls for unsupported fields.
- It must not invent numeric thresholds, formulas, validation requirements, or risk limits.
- It must not require the method name to be present in a maintained target registry.
- It must not approve the card or bypass validation.
- Its output is treated as untrusted until deterministic validation passes.

This makes the LLM, if used, an extraction assistant inside a deterministic evidence boundary. The product state is the
validated structured output, not the prompt, raw model response, or hidden reasoning.

### Validation And Readiness

Validation has two layers.

Structural validation checks the mechanics:

- artifact type and status
- known source and chunk IDs
- chunk-source consistency
- locator and text-hash consistency
- closed field groups and field names
- field-level refs for populated values
- quote limits and source suitability
- family minimums and high-risk family evidence counts

Semantic validation checks whether fields are useful and source-supported:

- formula fields cite formula-bearing chunks
- threshold fields cite threshold-bearing chunks
- entry and exit fields cite decision-rule chunks
- assumption and failure-mode fields cite limitation, caveat, risk, or monitoring chunks
- parameter defaults are explicit or are marked as maintained-template defaults, not source claims
- relationship-test fields for statistical arbitrage cite test or diagnostic evidence
- risk-limit fields cite explicit limit values and do not turn prose into numeric controls

Strategy-grade readiness is a separate conclusion inside validation. A card can be a valid descriptive method card but
still not be ready for strategy generation. For example, a source may describe an indicator formula and threshold
semantics but provide no source-backed trading rule, or a relationship-testing section may describe a statistical test
but not a spread trading policy. The validation report should distinguish:

- valid descriptive methodology
- valid implementation evidence
- valid signal-generation evidence
- valid strategy-template evidence
- blocked because required roles are absent

Downstream tools should consume the most restrictive relevant readiness flag. A strategy template should not accept a
card just because it is approved if the card lacks the readiness required by that template.

### Agentic Orchestration Model

The agentic part of the architecture is the policy and handoff layer over deterministic tools. Agents should not be
allowed to compensate for missing evidence by writing better prose. Their job is to decide what tool to call next, route
the resulting artifact refs, and stop when the artifact state says the workflow is unsafe.

The Quantitative Methods Agent can:

- register and ingest approved knowledge sources
- search, retrieve, and dereference evidence
- discover methodology candidates
- assemble candidate evidence
- extract closed methodology fields
- validate candidates
- create method-card drafts from passed validation reports
- publish method cards only through explicit approval policy
- validate or package method implementations when a method card supports that contract

The Quantitative Methods Agent cannot:

- choose symbols, date windows, or live data scope for a strategy
- run backtests
- approve performance conclusions
- place orders or mutate broker state
- write raw SQL outside configured persistence adapters
- create arbitrary executable code from prose without method implementation gates

The Quant Research Supervisor can:

- register and validate independently authored, maintained, AI-produced, or method-generated strategy/risk source
- create immutable strategy, risk-stack, and backtest specifications
- run gated canonical backtests over Data Agent scopes
- create and execute provider-neutral optimisation plans and Adversarial-requested immutable variants
- project completed canonical evidence to configured analytical tracking sinks
- pass untouched-holdout evidence to Evaluation and variant evidence to Adversarial
- preserve domain authority and producer/request/actor provenance in handoffs

The Quant Research Supervisor cannot:

- rewrite Quantitative Methods evidence
- forge method-card approval
- move symbols or date windows into method cards
- bypass strategy/risk validation
- treat a failed validation report as sufficient evidence

The Data Agent decides whether explicit market-data scope is fit. Data tools produce the authoritative manifests and quality
evidence. Method cards describe a methodology's data requirements, not the concrete data scope for a run.

The Evaluation Agent owns skeptical interpretation. It consumes backtest, risk, method, and data-quality evidence and
reports blockers, caveats, and performance conclusions. It should not repair missing methodology or rerun generation.

### Current Method-Card Baseline And Remaining Work

The 33P-33AB implementation and 33V evidence regression prove the canonical method-card architecture across controlled
sources containing previously unseen method names. Source-backed identity discovery, target-bound evidence packets,
deterministic field extraction, semantic validation, stable method-card sets, explicit publication, and
readiness-gated strategy use all run through MCP without a maintained registry of method targets. Shallow records remain
legacy/projection artifacts and cannot satisfy rich strategy or risk generation.

The proof deliberately distinguishes target openness from evidence-role discipline. New method names are open-world,
while family evidence roles and downstream readiness requirements remain maintained contracts. A definition-only
technical method cannot reach implementation readiness merely because its passage contains the word `indicator`, and
evidence attached to an adjacent named method cannot populate or validate the selected target.

The live Moving Average Oscillator run against `Algorithmic Trading and Quantitative Strategies` establishes a stricter
production baseline. Real PDF extraction produced one evidence unit containing a Bollinger passage tail followed by the
oscillator method label. That overlap is legitimate: evidence units are retrieval/context containers and are not owned
exclusively by one method. The defect was that extraction assigned the wrong local band/RSI semantics to crossover
fields, while validation still reported implementation readiness. Draft creation ultimately failed closed because the
source-backed candidate did not provide assumptions and failure modes, but that final gate does not make the earlier
field values semantically sound.

Remaining capability work therefore includes addressable claim spans, target-conditioned span selection, multi-span
synthesis, field-to-span entailment validation, and generation-consistent full-source ingestion. The same evidence unit
may support multiple methods through different or shared spans; competing concepts are context, not automatic blockers.
Deterministic extraction must continue to leave unsupported fields null. More precise parsers or a bounded enrichment
adapter may improve formulas, parameter structures, and decision rules only while preserving the evidence-packet
boundary, field-level citations, semantic validation, readiness gates, and explicit approval model. Tracker item 33AB
adds this claim-level hardening and its bounded canonical design document. Its live book evidence correctly removes
neighbor-method attribution and then blocks when target-bound implementation inputs remain missing; passing controlled
33V fixtures still must not be interpreted as evidence that every arbitrary book passage is method-card ready.

## Next Steps

The current methodology pipeline is flexible in the fields it can store, but it is still too rigid in how it discovers
and bounds a methodology. It assumes that one candidate has one primary family, that the relevant meaning can be
assembled around a locally identifiable method span, and that a maintained family evidence profile can determine which
roles must be retrieved before extraction. These assumptions work for bounded methods such as a moving average,
oscillator, or spread rule. They do not adequately represent a book-scale framework whose meaning is distributed across
forecast construction, forecast combination, volatility targeting, position sizing, portfolio construction, costs,
and execution.

The live extraction attempt against Robert Carver's *Systematic Trading* is the motivating diagnostic. The source is
fully indexed and substantive evidence is retrievable for the framework's individual stages. Candidate discovery,
however, either selected title/front-matter evidence for the overall identity or produced isolated
`portfolio_construction` fragments without preserving the enclosing systematic-trading process. Creating a card from
either result would have produced false semantic confidence. This is an assembly and representation limitation, not an
ingestion failure and not a reason to add a Carver-specific method target.

The longer-term methodology architecture should therefore become claim- and relationship-first:

- discover citeable claims and concepts before requiring a single method family or fixed card boundary
- connect claims through typed relationships such as `depends_on`, `produces`, `combines`, `scales`, `constrains`,
  `evaluates`, and `executes`
- infer atomic or composite methodology boundaries from the connected evidence while preserving every source span
- allow a composite methodology to reference ordered component methodologies with independent evidence and readiness
- derive multi-valued family classification after evidence assembly instead of using one family to control discovery
- retain a small stable card envelope for identity, lineage, evidence, assumptions, inputs, outputs, constraints, and
  failure conditions while allowing source-discovered component structure
- apply determinism to evidence IDs, source hashes, transformations, relationship assertions, validation, and revision
  lineage rather than requiring the source's semantic ontology to be known in advance

This direction must remain bounded. An enrichment model may propose claims, relationships, or candidate boundaries, but
each accepted value must resolve to stored evidence spans and pass deterministic structural and semantic validation.
The system must not solve the flexibility problem by inventing unsupported structure, adding known-method registries,
or weakening readiness gates.

### Near-Term Trading Evidence

Open-world composite extraction is significant capability work and should not block production of useful trading
evidence. That work is deferred after 33AB; the existing knowledge-base creation, retrieval, lineage, and bounded-method
extraction tools remain maintained capabilities. The nearer-term path should prioritize direct, maintained indicator,
strategy, and risk-manager methods plus first-class intake for externally authored implementations over source-code
generation as the default handoff:

1. Capture a citeable, parameterized method specification for a bounded indicator, trading rule, portfolio rule, or
   risk control.
2. Map that specification to a maintained runtime implementation or declarative builder with an explicit parameter
   contract, or register a supplied handwritten or AI-produced implementation as an immutable versioned artifact.
   Unsupported semantics must block rather than being translated into generated code.
3. Validate mathematical behavior, required inputs, warmup, state transitions, order semantics, risk thresholds, and
   source-to-parameter provenance with deterministic fixtures.
4. Compose validated strategy and risk-manager versions through immutable strategy and ordered risk-stack specifications.
5. Run canonical backtest specifications over Data Agent scopes and pass the resulting implementation, risk-decision, and
   performance evidence to Evaluation.

This route is intentionally narrower than arbitrary prompt-to-code generation, but it produces stronger evidence
sooner. A maintained or explicitly registered implementation gives backtests a stable behavioral target, makes strategy
and risk interactions directly testable, and separates methodology evidence from implementation creativity. Supplied
AI code is untrusted input and must pass the same source hashing, import restrictions, interface checks, deterministic
fixtures, and backtest-only safety gates as handwritten code. Its provenance should identify the generator and inputs
that may be persisted safely, but must not store hidden reasoning. A method-card reference is useful provenance when a
validated card exists; it is not required to pretend that the paused knowledge subsystem can describe every bespoke
implementation.

Code generation may remain an optional, quarantined adapter for methods that cannot be represented by maintained
contracts; it should not be the primary path from a method specification to a trading conclusion. The next active
architecture work is therefore strategy/risk implementation intake and versioning, reproducible backtest
specifications, ML model versioning, and robustness/adversarial evaluation over immutable baseline runs.

Tracker item 33AC records composite methodology representation as a deferred architectural follow-on. Tracker items
56-57 and the reprioritized 39, 44, and 46 items record the active implementation-to-evidence work.

## ML Lifecycle Architecture

The ML Agent target is broader than model-card storage. It coordinates the research lifecycle for predictive
time-series models: feature engineering, point-in-time dataset construction, fitting, experiment recording, evaluation,
model registration, version selection, deployment evidence, prediction monitoring, and drift analysis. MLflow is the
configured ML-training telemetry and model-registry service. Trader remains authoritative for generic research plans,
trials, selections, backtests, trading-specific lineage, safety decisions, and runtime configuration.

### Implemented Runtime Slice

Tasks 39H-I implement the execution-side boundary while 39A-G/J remain planned. Core `trader.predictions` defines
dependency-neutral feature batches, immutable model identity, requests, raw observations/batches, inference policy,
runtime binding, and failure evidence. `trader_mlflow` supplies a lazy local `python_function` adapter;
`trader_standard` supplies point-in-time bar features, maintained mappers, and a model-driven strategy. No core module
imports MLflow, pandas, research services, MCP, or agents.

The ML Agent now owns DB-backed deployment manifests and validation reports through
`ml_create_deployment_manifest` and `ml_validate_deployment`. The Supervisor binds a passed deployment to a strategy
requirement and owns mapper parameters and trading interpretation. Backtests resolve and load the predictor once,
record raw prediction events before mapped signals/orders, and include complete binding evidence in canonical run
identity. The runtime supports independent per-symbol decisions and exact synchronized-universe decisions. This slice
does not create feature sets, train models, register model versions, monitor drift, or grant live eligibility.

### Authority Boundary

MLflow and Trader must not become competing stores for the same responsibility.

MLflow is authoritative for ML lifecycle records only:

- ML training experiments and training runs
- training parameters, predictive metrics, tags, and logged training artifacts
- packaged MLflow models, model signatures, and environment metadata
- registered-model names and immutable model versions
- model-version tags and mutable aliases used to identify candidates such as `champion` or `challenger`

Trader Postgres research artifacts are authoritative for:

- Data Agent dataset and quality refs used for training, validation, backtests, and monitoring
- feature, target, split, training, evaluation, and deployment specifications
- source, dependency, environment, and configuration hashes needed to reproduce a run
- resolved MLflow experiment, run, artifact, registered-model, and immutable model-version refs
- validation, promotion, strategy-integration, backtest, robustness, and Evaluation evidence
- the exact model version used by each strategy run and prediction event

Trader should store MLflow references and independently verifiable hashes, not copy model binaries into generic research
JSON payloads. MLflow should receive Trader dataset IDs, feature-set IDs, training-spec IDs, and source hashes as tags or
dataset lineage, not become the authority for market-data scope or trading approvals.

Backtest optimisation may be projected to MLflow for exploratory charts. Such runs are disposable analytical mirrors:
deleting MLflow must not prevent Trader from reading the canonical plan, trial ledger, selected specification, or
reports, and an MLflow record can never repair or override missing Trader evidence.

Model aliases are mutable control-plane pointers. Any alias accepted by a planning or deployment request must be
resolved to an immutable registered-model version before validation, backtesting, or runtime startup. The resolved
version, source run, model URI, model digest, signature, and environment fingerprint are pinned in the Trader artifact.
A running backtest or trading session must never change model behavior merely because an MLflow alias was reassigned.

### Time-Series Research Invariants

Generic tabular-ML experiment tracking is not enough for trading data. The ML tools must make the following concepts
explicit and validate them before fitting:

- feature event time, feature availability time, decision time, target horizon, and label availability time
- symbol universe, timeframe, source, start/end bounds, and market-data quality through Data Agent refs
- training, validation, calibration, and test windows expressed as chronological folds
- expanding, rolling, or anchored walk-forward policy
- purge and embargo intervals where labels or windows overlap fold boundaries
- cross-sectional holdouts and universe membership policy where models span symbols
- fitting scope for scalers, encoders, imputers, feature selection, and dimensionality reduction
- warmup, missing-value, stale-feature, and outlier policy
- random seeds and deterministic settings where the selected framework supports them
- target construction, class/return horizon, prediction semantics, and decision threshold provenance

Random train/test splitting must not be the default for time-series models. Feature code must be point-in-time correct:
no feature may observe data unavailable at its declared decision timestamp, and every learned preprocessing step must be
fit only on the applicable training fold. Training and evaluation reports must carry leakage-audit results rather than
assuming chronological ordering is sufficient.

### Lifecycle Artifacts

The ML Agent should own immutable, DB-visible Trader artifacts that reference MLflow records:

1. `ml_feature_set_spec`: feature names, source implementations, lookbacks, availability rules, schemas, and hashes.
2. `ml_training_dataset_manifest`: Data Agent refs, feature-set ref, target definition, point-in-time joins, row/fold
   summaries, and a reproducible dataset digest.
3. `ml_training_pipeline_manifest`: validated trainer entrypoint, framework/flavor, dependencies, source hash, and
   parameter schema for maintained, handwritten, or AI-produced training code.
4. `ml_training_spec`: dataset, pipeline, split plan, hyperparameters, seeds, resource bounds, and MLflow experiment.
5. `mlflow_run_ref`: tracking-server identity, experiment/run IDs, run status, dataset inputs, logged model path,
   metrics, parameters, tags, source hashes, and client/server versions.
6. `ml_model_evaluation_report`: fold and holdout metrics, calibration, stability, leakage checks, baseline comparisons,
   prediction artifacts, blockers, and model-readiness status.
7. `ml_model_version_ref`: registered-model name, immutable version, source run, model URI/digest, signature,
   environment, tags, aliases observed at resolution time, and evaluation refs.
8. `ml_model_promotion_report`: explicit policy decision and evidence for assigning or moving an approved alias. Alias
   mutation is never implied by a successful evaluation.
9. `ml_deployment_manifest`: pinned model version, inference adapter, feature contract, raw output semantics, latency
   and failure policy, environment, and backtest/paper eligibility. Strategy consumers and trading policy are excluded.
10. `ml_prediction_artifact` and `ml_drift_report`: bounded prediction summaries, realized-target joins, input/output
    drift, calibration/performance decay, latency, stale-feature evidence, and exact deployed version.

MLflow run and registry records may be created before every Trader artifact is complete, but no model is strategy-ready
until Trader has reconciled those records into passed validation and deployment artifacts.

### Runtime Integration

The core `trader` package remains independent of MLflow. It defines stable prediction-domain contracts,
including a predictor interface, feature batch, prediction result, model identity, and inference failure policy. A model-
backed signal or strategy consumes those contracts in the same cycle path used by backtests and paper trading.

The MLflow-specific client and model loader belong in an optional integration adapter, not in `trader`. Research
training/orchestration belongs in `trader_research.ml`; MCP transport belongs in `trader_mcp`; maintained model-backed
signals or strategies may live in `trader_standard` while depending only on the core prediction protocol. This keeps
MLflow, pandas, scikit-learn, PyTorch, and similar dependencies out of the platform core.

Before a model-backed strategy runs, validation proves:

- the pinned model can be resolved and its digest, signature, and environment match the deployment manifest
- offline and runtime feature calculation produce parity on deterministic fixtures
- feature names, types, ordering, nullability, lookbacks, and timestamps match the model signature
- prediction outputs have declared shapes and semantics, including horizon, units, classes/probabilities, and optional
  uncertainty
- inference is deterministic where promised, bounded by a latency timeout, and subject to an explicit failure policy
- strategy thresholds, sizing, and risk logic consume declared prediction fields without hidden transformations
- backtest inference and trading-loop inference use the same adapter and feature contract

The trading hot path must not call MCP and should not log one MLflow API request per prediction. The runtime loads or
connects to the pinned model at a controlled lifecycle boundary, emits bounded prediction events through platform
persistence, and continues according to its declared stale-model, stale-feature, timeout, and inference-error policy.
The ML Agent later reads those public events to compute monitoring artifacts.

### Deployment And Promotion Safety

"Deploy" means producing and validating a version-pinned inference configuration for a target environment. It does not
grant the ML Agent authority to mutate broker state, restart the trading service, rewrite a live strategy, or silently
move a production alias.

Initial implementation should support backtest and paper deployment manifests. Live eligibility requires a separate
operator-controlled promotion path after strategy backtests, Evaluation, and Adversarial evidence exist. Model alias
assignment is an explicit MLflow mutation with its own approval record and policy gate; runtime configuration changes
remain operator actions outside agent autonomy.

MLflow reads, MLflow writes, training execution, alias promotion, and trading-runtime deployment are different side
effects. The existing `local_mutating` label is not sufficient for all of them. The MCP contract must add an external
research mutation class and independent policy gates before tools can create MLflow runs, fit models, register versions,
or move aliases.

### Agent Boundary

The ML Agent may coordinate deterministic ML tools, compare returned artifacts, request another bounded training run,
and produce ML-owned handoffs. It cannot choose undeclared market-data scope, forge Data Agent manifests, approve final
strategy performance, run arbitrary prompt text as training code, mutate live trading, or decide final promotion.

The Data Agent owns raw dataset scope and quality. Quantitative Methods may own reusable mathematical feature
implementations. The ML Agent owns feature-set composition, training datasets, fitting, model evaluation, MLflow refs,
model versions, deployment candidates, predictions, and drift. The Quant Research Supervisor binds a passed deployment
manifest into strategy/backtest artifacts. Evaluation and Adversarial agents judge trading and robustness evidence.

Tracker tasks 39A-39J implement this deterministic tool universe before task 40 adds an ML Agent graph.

## Experiment Tracking And Optimisation Architecture

Parameter optimisation is a procedure for proposing configured child specifications and observing their completed
evidence. It is not a database, an Evaluation report, or a robustness verdict. Three provider-neutral contracts enforce
that separation:

- `OptimizationEngine` owns deterministic `ask`/`tell` parameter proposals and a bounded provider-state snapshot.
- `OptimizationTrialExecutor` materializes each proposal through an owning domain service. The current executor creates
  immutable strategy/risk/backtest child specifications and canonical backtest runs; later ML execution can implement
  the same protocol while preserving ML Agent ownership of training artifacts.
- `ExperimentTrackingSink` receives a derived snapshot of an already persisted canonical run. It cannot accept caller
  metrics/tags, propose parameters, rewrite a trial, or become promotion evidence.

The authority matrix is intentionally asymmetric:

| State | Canonical authority | Optional operational/projection state |
| --- | --- | --- |
| Plan, search space, constraints, seed, budget | Trader `research_artifacts` and typed projections | None |
| Suggestions, rejected/failed/passed trials, child refs, observations, objective values | Trader | Optuna study state may support sampler resumability only |
| Selected exploratory specification | Trader | Tracking projections may visualize it |
| Backtest results, holdout Evaluation, audit plans/reports | Trader | No provider may override these records |
| ML training telemetry, logged model package, Model Registry version | MLflow for the ML lifecycle | Trader stores reconciled immutable refs and trading lineage |

Canonical optimisation never writes to or reads from the legacy `experiments` or `experiment_runs` research path. A
plan pins one passed selection-region backtest specification, a sealed later chronological holdout manifest and quality
snapshot, one passed objective implementation, typed search dimensions, constraints, seed, budget, and resource limits.
Dataset identity, implementation identity, costs, provider settings, holdout boundaries, and fold boundaries are not
tunable decision dimensions. Explicit strategy parameters, risk thresholds, sizing fields, and later model-training
parameters are tunable only when their owning specification declares them.

The objective receives a versioned `OptimizationObservation`, not a store or runtime object. Its top-level fields are
closed to scalar metrics, counts, costs, exposure/risk summaries, quality, constraints, and lineage labels. Registration
blocks filesystem/network/database imports and unsafe dynamic calls; validation executes a deterministic fixture. An
unavailable requested metric blocks that trial rather than becoming zero, `NaN`, or an invented substitute.

Every run pins the resolved engine profile name, provider/algorithm version, configuration digest, capabilities, seed,
and executor kind. `builtin_grid` and `builtin_random` are maintained, deterministic, and require no optional packages.
Grid enumerates a finite declared space; random uses a seeded duplicate-free permutation. Optuna TPE is a lazy optional
adapter implementing the same protocol: sequential, seeded, single-objective, bounded, and without pruning in its first
slice. Its PostgreSQL study uses a dedicated non-`public` schema and dedicated writer role. Trader never queries that
schema as product evidence. Provider loss leaves a canonical run partial/blocked; canonical results remain readable,
and a separate built-in run may consume the same provider-neutral plan. An engine profile never changes inside one run.
Provider configuration digests include credential-free endpoint/database identity, schema, role, and namespace data so
changing an Optuna or tracking authority cannot masquerade as the same configured profile.

Content-addressed implementation, specification, validation, snapshot, and optimisation-plan loaders recompute their
stable IDs before use. A persisted payload cannot retain an earlier validation merely by keeping its old ID; source,
parameter, ordering, dataset, quality, or lineage drift fails closed before a trial or backtest starts.

The same rule applies after execution. A canonical optimisation-run loader reconstructs trust from the sealed plan and
trial artifacts rather than trusting the run summary: it reevaluates objective results from closed observations,
recomputes trial counts and deterministic selection, and checks selected child lineage. Results, tracking projection,
holdout Evaluation, variant execution, and Adversarial audit all use this loader. Typed projections remain queryable
views of canonical JSONB and are never a shortcut around these checks.

Determinism qualification compares all canonical research identities and payload evidence from two clean database
runs. The only excluded backtest-result fields are `finished_at` and `duration_seconds`, which measure wall-clock
execution and do not affect research semantics. Dataset timestamps, events, trades, metrics, observations, objective
values, provider configuration, suggestions, trial order, tie-breaks, selections, and report lineage remain in the
digest. A test-only audited event-store proxy records bounded bar-table reads by phase; a database selection seal proves
that optimisation reads stop at the selection boundary and holdout reads begin only after immutable selection.

The execution graph is:

```text
validated implementation -> immutable strategy/risk specification
  -> passed selection backtest specification + sealed chronological holdout
  -> validated closed-input objective -> provider-neutral optimisation plan
  -> engine suggestion -> immutable child specification -> canonical selection backtest
  -> closed observation -> objective result -> complete canonical trial ledger
  -> deterministically selected exploratory specification
  -> separately created sealed-holdout backtest
  -> Evaluation-owned holdout report
  -> Adversarial-owned audit plan
  -> Supervisor-executed immutable variants/stresses
  -> Adversarial-owned robustness report
```

Selection tie-breaking is deterministic and every suggestion, retry attempt, exception, rejection, child ref, and
objective diagnostic remains visible. The optimiser cannot issue a recommendation or deployment decision. Promotion
readiness requires both a matching passed untouched-holdout Evaluation report and a passed Adversarial report.

Adversarial ownership is procedural, not an embedded optimiser option. Adversarial declares attacks over seed/provider,
budget, search boundaries, alternate validated objectives, neighboring parameters, costs, windows, concentration, and
multiple-testing risk. The Supervisor executes only the immutable variants requested by that plan. Adversarial then
judges supplied evidence and cannot alter the baseline run or its selection.

Tracking projection is explicit and independently gated. `research_project_experiment_tracking` derives its complete
payload from a supported canonical run, uses a configured sink profile, and writes an idempotent
`experiment_tracking_projection_report` with `authoritative=false`. If the sink is unavailable or deleted, the report
blocks without damaging canonical evidence. The optional MLflow sink is therefore an analytical convenience for
backtest optimisation, separate from MLflow's authoritative role for ML training telemetry and model packages.

Walk-forward optimisation in task 58 composes these same contracts inside each immutable fold. It does not introduce a
second optimiser abstraction or fold robustness attacks into selection. Task 59 remains the separate stitched
out-of-sample Evaluation and Adversarial audit layer.

## Walk-Forward Validation And Optimisation

Walk-forward validation and walk-forward optimisation are related but belong at different delivery stages.

Chronological walk-forward validation is foundational model-fitting correctness. Tasks 39C and 39F must support rolling,
expanding, or anchored folds, target horizons, purge/embargo, preprocessing fit scope, and untouched holdouts before the
ML Agent can claim that a model evaluation is time-series valid. This does not require searching strategy parameters or
selecting a winning model on every fold.

Full walk-forward optimisation is a later orchestration capability. It repeatedly searches a bounded strategy-parameter
or model-choice space on declared in-sample/validation windows, locks the selected parameters or immutable model version,
and runs an untouched out-of-sample backtest. It depends on capabilities that must exist first:

- immutable handwritten/AI-produced strategy and risk implementation versions from task 56
- reproducible, parameterized backtest specifications and child-run lineage from task 57
- point-in-time ML training/evaluation and version-pinned model-backed strategy integration through task 39I
- cost, parameter, scope, and data perturbation primitives from tasks 44 and 46

Assigning the complete process to the Robustness Agent would let the same decision-maker create selected evidence and
judge its robustness. Decision authority and artifact authority are therefore split:

- `walk_forward_optimization_plan` and `walk_forward_optimization_run` are Experiments-domain procedural artifacts.
  Experiment Design declares folds, search space, objective, constraints, costs, seeds and budgets before deterministic
  services produce child-run refs.
- Data-domain dataset and quality refs are consumed by each fold. The optimiser cannot manufacture or widen
  market-data scope.
- ML-domain records cover per-fold training specs, reconciled MLflow runs, predictive evaluations and immutable model
  versions when a fold fits a predictive model.
- Quantitative Methods decides reusable objective/statistical contracts and multiple-testing evidence where
  requested; it does not choose the final trading verdict.
- Evaluation decides the conclusion in `walk_forward_evaluation_report`, built only from stitched untouched
  out-of-sample fold evidence.
- Robustness decides the findings in `walk_forward_robustness_report`, which attacks the optimisation procedure and its
  apparent stability without changing the selected parameters/models. Both reports have Review domain authority.

Every plan must be immutable before execution and record training, selection, and test boundaries separately. Selection
may use only declared in-sample or inner-validation evidence. The out-of-sample result for a fold cannot be fed back into
that fold's search. All evaluated candidates, rejected candidates, scores, seeds, exceptions, selected refs, and child
backtests remain visible so the result cannot hide the search path that produced it.

The Adversarial audit should include fold-boundary and window-length sensitivity, neighboring parameter/model choices,
selection instability, objective changes, in-sample to out-of-sample degradation, fee/slippage stress, symbol/period
concentration, search-budget sensitivity, multiple-testing/selection-bias evidence, and the risk that the walk-forward
procedure itself was tuned against final results. Nested walk-forward analysis may be required when procedure-level
choices were optimized.

Tasks 58-59 are deliberately deferred until the prerequisites above are proven. Neither optimisation success nor a
passed audit grants paper/live promotion or permits an agent to mutate a running deployment.

## Methodology Evidence Flow

The claim-level evidence model, target-conditioned extraction process, semantic validation rules, and bounded enrichment
policy are specified in [semantic_extraction.md](semantic_extraction.md). This architecture document retains package and
agent boundaries rather than duplicating that subsystem design.

Methodology work is a DB-backed evidence pipeline, not an agent scratchpad. Source registration records the
reference, source type, file hash, and operator metadata. Full-document ingestion is the step that extracts text,
chunks the whole source, creates lexical/vector indexes, and makes every chunk citeable by source ID, chunk ID, locator,
and text hash.

Methodology candidate discovery and field extraction write Quantitative Methods artifacts in the research artifact
store. They are evidence-gathering steps only: candidates, extraction reports, and validation reports do not approve a
method or create executable strategy code. Canonical method-card draft materialization consumes only passed
packet-backed validation reports, revalidates the cited chunks through the knowledge store, and persists a canonical
evidence-backed `method_card_draft` payload. Caller-provided method IDs, titles, or families are accepted only when the
candidate identity, aliases, abbreviations, and validated families support them. Publishing a draft preserves the full
payload while deriving compact summaries for bounded method search and citation responses. The summary is not a second
card representation and cannot be written, approved, or used as independent provenance.

Approved method cards can remain provenance for source-backed implementation producers. Maintained computational
contracts and maintained implementations do not acquire an artificial method-card prerequisite. Produced source
receives no special eligibility: it must enter the same content-addressed implementation registration, validation,
specification, and backtest path as handwritten source. Data Agent manifests still own symbols, timeframes, date
windows, source filters, and market-data quality. Method cards do not define execution identity or a concrete backtest
scope.

## Safety Boundaries

- Research-agent tools do not submit broker orders, clear halt state, reconcile broker state, start live trading, or
  expose raw SQL.
- Backtest execution is local-mutating and policy-gated by `TRADER_MCP_ALLOW_BACKTESTS=true`.
- Optimisation execution additionally requires `TRADER_MCP_ALLOW_OPTIMIZATION=true`.
- Optuna sampler writes require the generic external-research-write gate and the separate Optuna write gate.
- Experiment-tracking projections require the generic external-research-write gate and tracking write gate.
- Model loading for deployment parity and backtest inference requires `TRADER_MCP_ALLOW_ML_RUNTIME=true`.
- Data loading is local-mutating and policy-gated by `TRADER_MCP_ALLOW_DATA_LOADING=true`.
- Provider-catalog symbol discovery requires explicit provider discovery policy.
- Generated code is source-backed and validation-gated before use in later workflows.
- Supervisor state stores public artifact refs, decisions, blockers, warnings, and tool evidence, not hidden reasoning
  traces or raw scratchpads.

## Authority Enforcement

Domain contexts are separated by the artifacts for which they are authoritative. The closed domain vocabulary lives
in `trader_research.foundation.artifacts`; artifact-type mapping lives in
`src/trader_research/governance/artifacts.py`; tool allowlists and approved target decisions live in
`src/trader_research/governance/ownership.py`. The Research Coordinator may route workflows and consume canonical refs,
but it cannot change Data, Knowledge/Methodology, Experiments, ML or Review authority, rewrite specialist findings, or
claim deterministic execution as its own research judgment.
