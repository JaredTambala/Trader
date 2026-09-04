# Agentic Research Orchestration Redesign

Design status: architecture and design authority for the target agentic research system. Work authorization,
assignment, and delivery progress are maintained in Notion's
[Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84) and
[Trader Work Items](https://app.notion.com/p/31131085ffc54c329f25445843e9ac52).

Last reviewed: 2026-08-28.

## Purpose

Trader needs a real model-driven research system, not a deterministic workflow presented through agent terminology.
The target product accepts a natural-language research objective, delegates work among specialist agents, uses MCP
tools to create and test research artifacts, revises its approach when evidence changes, and returns a grounded view of
whether a strategy is worth considering for paper-trade review.

This is a clean redesign of `trader_agents`. No source, state, graph, checkpoint, prompt, or import compatibility with
the existing implementation is required. Existing deterministic research services and MCP tools may be retained only
where they are good target capabilities; their reuse is not a compatibility requirement.

This plan defines the target and the evidence needed before implementation begins. It does not change current runtime
behavior.

## Active Implementation Focus

The selected first production slice is the non-ML Coordinator–Data–Strategy path. It ends provisionally at an admitted
strategy/risk candidate and must prove real-model planning, role-scoped MCP tool choice, observation-driven revision,
multi-asset Data readiness, implementation comparison, isolated coding, failed-admission repair, canonical handoff,
interrupt/restart behavior, and bounded fail-closed termination across repeated runs.

Only the complete architecture and shared pattern decisions required by this slice gate its framework spike and
implementation. Knowledge-backed authoring, Experiment Design/execution, RWFO, and Evaluation remain later extensions.
The ML Signal Research Agent and new ML lifecycle capability work are parked until this first slice is qualified;
existing controlled ML behavior is not removed.

## Decision Summary

- Replace the current deterministic coordinator, fixed workflow compiler, composition runner, and specialist policy
  shells with model-backed agents coordinated by a supervisor.
- Return every specialist result to the Research Coordinator. The coordinator reviews the cited evidence, updates the
  agenda, and explicitly chooses whether to advance, request revision, revisit an earlier responsibility, fork a new
  research branch, seek approval, conclude, or fail closed.
- Keep deterministic behavior where it belongs: market-data ingestion, code admission, backtest execution, accounting,
  optimisation engines, robustness calculations, artifact validation, policy enforcement, and broker isolation.
- Treat LangChain agents plus LangGraph as the leading candidate for model/tool loops, durable coordination,
  specialist isolation, parallel delegation, persistence, and human interrupts. Accept the production pattern only
  after the first-slice agent boundaries are complete and the focused framework spike supplies comparative evidence.
  Later specialist identities still require their own complete records and pattern review before implementation.
- Keep MCP as the model-facing capability boundary. Split capabilities by operational trust boundary instead of
  exposing one undifferentiated tool catalog to every agent.
- Introduce a Knowledge Research Agent and a source-backed research dossier. The agent may iteratively navigate
  approved sources, but exact source elements and claim spans remain the only citeable evidence; model summaries are
  derived navigation aids.
- Require a Quantitative Methods implementation brief between the research dossier and Strategy Engineering. The
  brief separates source-backed method claims from explicit engineering decisions and must be independently validated
  before code authoring.
- Use MLflow for both complex-signal/model lifecycle and agent engineering telemetry: traces, evaluations, prompt or
  program versions, model configuration, cost, and latency. Trader Postgres remains authoritative for financial
  research evidence and recommendation inputs.
- Introduce DSPy only after representative evaluation datasets exist. Use it to optimize measurable specialist
  programs; do not create a second orchestration runtime inside LangGraph.
- Evaluate PydanticAI in a short architecture spike as the strongest typed alternative. Do not run two primary agent
  frameworks in the product.
- Preserve explicit human authority for material research assumptions, costly or external mutations, model promotion,
  and any paper-trade handoff. Research agents never place orders or mutate a live or paper broker session.
- Name architecture by responsibility. Delivery labels and historical commit names are never component names.

## Why The Existing Layer Is Not The Target

The orchestration lineage from `e3f7d85` through the controlled freeze at
`b1f49bd2e8f71bedc4bd66724df756a5935f3eca` established useful contracts, checkpoint isolation, MCP execution,
approval handling, and recovery evidence. It also progressively removed model-selected planning, model-selected tools,
free-form task interpretation, and result-driven replanning. The finished surface accepts caller-built tasks and moves
them through code-owned routes and one fixed workflow.

That is a qualified deterministic control plane. It is not a multi-agent research system. Adding an LLM call to its
existing decision node would leave the important decisions encoded in catalogs, task shapes, and fixed graph flow.
The redesign must replace the control model rather than decorate it.

The earlier product brief in
[codex_trading_research_framework_brief.md](../docs/history/research_agents/codex_trading_research_framework_brief.md)
contains the product behavior still wanted: the model plans, proposes code, chooses relevant tests, and interprets
evidence while the platform owns execution and safety. The earlier
[agent operating model](../docs/history/research_agents/agent_operating_model.md) also contains a useful supervised
specialist hierarchy. This plan restores those ideas without restoring obsolete schemas or compatibility surfaces.

### Retain, replace, and reject

| Treatment | Surface | Reason |
| --- | --- | --- |
| Retain by fitness | `trader`, `trader_standard`, canonical research artifacts, Postgres evidence, deterministic research services, MCP tool envelopes, execution gates, and provider-maintained LangGraph checkpoint storage | These are the capability and evidence plane that agents should use. Individual contracts may still be redesigned. |
| Replace | Everything under `trader_agents`, including current coordinator decisions, specialist task catalogs, fixed composition state, workflow compiler ownership, prompts, checkpoints, and public imports | The present control plane prevents the model from planning, choosing tools, and replanning. |
| Reassess | MCP tool granularity, agent ownership metadata, orchestration artifacts, workflow outcome records, and the current single-server catalog | These were designed for fixed execution and may not provide good model affordances or trust separation. |
| Reject | Compatibility shims, checkpoint migration, fixed task-number graphs, architecture names derived from roadmap codes, raw SQL access, raw chain-of-thought persistence, and agent-controlled broker mutation | They either preserve the wrong design or violate platform safety. |

## What Counts As An Agent

A Trader component is an agent only when all of these are true:

1. A configured language model is invoked as part of its decision policy.
2. The model can choose between at least two meaningful next actions, including tools, delegation, clarification, or
   termination.
3. It observes action results and can revise its plan rather than following a fully encoded path.
4. It has a bounded mission, instructions, context, tools, budget, and output contract distinct from other agents.
5. Its decisions and trajectory can be traced and evaluated independently.
6. It returns structured findings and canonical evidence references; it does not claim authority merely because it
   produced prose.

A validator, executor, router with fixed rules, retry loop, backtest runner, or checkpoint shell is not an agent. Those
components remain valuable services.

“Move away from determinism” applies to research planning, delegation, tool choice, synthesis, and replanning. It does
not mean making fills, metrics, validation, persistence, permissions, or safety nondeterministic.

## Target Product Experience

```text
operator research brief
  -> Research Coordinator clarifies only material ambiguity
  -> Coordinator creates and revises a visible research agenda
  -> specialist agents investigate in parallel where dependencies permit
       Data Research
       Knowledge Research
       Quantitative Methods
       Strategy Engineering
       Experiment Design
       ML Signal Research
  -> each specialist returns structured findings and canonical evidence to Coordinator
  -> operator approves material assumptions and bounded execution budget
  -> Coordinator invokes deterministic MCP execution for baseline and comparative evidence
  -> Coordinator reviews results and advances, revises, forks, asks, or stops
  -> if warranted, Robustness and Walk-Forward attacks the claims and requests further evidence
  -> Coordinator reviews stability evidence and commissions any permitted follow-up
  -> Evaluation independently assesses the complete evidence when the research branch is ready
  -> Coordinator synthesizes cited findings, uncertainty, blockers, and next actions
  -> optional operator-approved paper-trade candidate handoff
```

The sequence is not a fixed graph template. The coordinator may omit irrelevant specialists, revisit earlier work,
run independent investigations concurrently, request clarification, commission a revised strategy, stop an unpromising
path early, or compare multiple candidates. The durable graph provides a generic coordination loop; the model creates
and revises the agenda.

## Coordinator Multi-Agent Pattern

The Research Coordinator is the only default user-facing agent. Specialist agents are invoked as tools or subgraphs
and return control to it. This creates a clear supervisor pattern with isolated specialist context and one coherent
conversation.

```text
                               +----------------------+
operator <-> Research Coordinator <-> approval interrupt
                    |
                    +--> Data Research Agent -----------+
                    +--> Knowledge Research Agent ------+
                    +--> Quantitative Methods Agent ----+
                    +--> Strategy Engineering Agent ----+--> structured findings + artifact refs
                    +--> Experiment Design Agent -------+
                    +--> deterministic experiment execution MCP
                    +--> Robustness & WFO Agent --------+
                    +--> ML Signal Research Agent ------+
                    +--> Evaluation Agent --------------+
                    |
                    +--> revised agenda or final synthesis
```

Specialists do not call peers directly in the initial architecture. They ask the coordinator for additional work. This
keeps delegation, budgets, approvals, and cross-domain synthesis visible in one place. Direct handoffs may be added only
for a demonstrated conversational need, such as an extended operator/Strategy Engineering session.

Independent specialist calls may execute in parallel. Work with data or artifact dependencies waits for the referenced
outputs, not for a hard-coded predecessor name.

### Evidence return contract

Every specialist invocation terminates at the coordinator, including partial, blocked, failed, and cancelled work. No
specialist may silently pass work directly to the next specialist or convert its own output into a final conclusion.
The coordinator receives a structured return containing at least:

- delegation, specialist, research-branch, parent-attempt, and agent-program identities;
- completion status and the exact questions answered or left unresolved;
- bounded findings that state direction, magnitude, uncertainty, assumptions, and caveats;
- canonical artifact references supporting each material finding;
- explicit blockers, contradictions, and approval needs;
- proposed follow-up work, labelled as advice rather than authority;
- tool/compute/token budget consumed and whether any result is exploratory or confirmatory.

The return is an index into evidence, not a trusted narrative. The coordinator must be able to dereference canonical
artifacts through read-only resources or comparison tools and check that cited identity, status, scope, partition, and
metrics match the summary. A specialist recommendation can inform routing but cannot grant itself more scope, budget,
or authority.

### Coordinator decisions after every return

The coordinator is an evidence-aware research supervisor, not a message router. After reviewing a return it emits one
structured, externally validated decision:

| Decision | Meaning |
| --- | --- |
| Advance | Evidence satisfies the brief-defined readiness criteria for a downstream specialist. |
| Request revision | Send a bounded correction or missing-evidence request to the same specialist without changing the research question. |
| Revisit earlier work | Send new evidence back to an earlier responsibility, creating a new attempt linked to the prior artifacts. |
| Fork research branch | Create a new candidate, protocol, asset scope, or model lineage while preserving the unsuccessful branch. |
| Request operator decision | Pause because the proposed change exceeds approved scope, assumptions, budget, or mutation authority. |
| Conclude | Produce the current grounded answer because the brief is satisfied and required independent review is complete. |
| Stop fail-closed | End the branch because evidence is terminally adverse, authority is missing, the action would contaminate evaluation, or loop/budget guards are reached. |

Each decision records a concise public rationale, the evidence refs and brief criteria used, the intended information
gain, the affected branch/attempt, and the remaining budget. This is inspectable decision evidence, not hidden chain of
thought. Deterministic guards validate the decision against scope, approval, lineage, partition, and loop policy before
dispatch.

The coordinator may make a routing assessment such as `weak`, `promising`, `contradictory`, or `insufficient` when the
meaning of those terms is tied to the operator brief or an approved protocol and cited metrics. Evaluation retains
authority for the independent research-quality verdict. The coordinator cannot erase, soften, or relabel a specialist
finding merely to keep a branch alive.

### Evidence-driven iteration examples

| Evidence returned | Permitted coordinator response | Required scientific treatment |
| --- | --- | --- |
| A baseline is clearly poor | Stop; request diagnosis; commission a code correction; or explore pre-authorized alternatives. | A bug fix may preserve the question but creates a new implementation version. Performance-driven changes create a new attempt and remain visible. |
| Initial hyperparameters are poor | Invoke further deterministic optimisation only inside an already approved search space and budget, or return to Experiment Design for a successor protocol. | Every trial remains in the ledger. Parameters outside the prospective space require a new protocol/approval and cannot reuse the same sealed holdout claim. |
| An asset pair is unsuitable | Ask Data Research and Experiment Design to investigate another pair only when the brief authorizes universe exploration. | The new pair is a new research branch, expands the multiplicity record, and requires fresh Data evidence. Otherwise the coordinator interrupts for operator scope. |
| Initial evidence is reasonably promising | Delegate robustness and walk-forward work when prerequisites, budget, and brief criteria are satisfied. | “Promising” is provisional. It grants no promotion and does not bypass independent Evaluation. |
| Walk-forward results are stable | Send the full branch to Evaluation or request a targeted robustness gap identified in the return. | The coordinator cites fold-level and stitched out-of-sample evidence; it does not infer stability from an aggregate alone. |
| Walk-forward results are unstable | Stop, ask Evaluation for a failure assessment, or fork a successor hypothesis through Design/Strategy Engineering. | The failed walk-forward remains canonical. Retuning from it starts a new exploratory lineage and cannot be reported as the original confirmation. |
| A specialist asks for an action outside coordinator authority | Delegate to the owning specialist if already in scope, otherwise ask the operator or stop. | The coordinator cannot manufacture approval, widen scope, or substitute its judgment for the owning authority. |

## Agent Responsibilities

| Agent | Model-owned decisions | Primary capabilities | Hard boundary |
| --- | --- | --- | --- |
| Research Coordinator | Interpret the brief, build and revise the agenda, review every specialist return against cited evidence, choose specialists, advance/revise/fork/stop branches, invoke approved main-protocol execution, allocate bounded work, ask for approvals, reconcile disagreements, and synthesize the final answer. | Specialist delegation, read-only artifact/resource and comparison tools, plan-pinned main-protocol execution/job capability, research-branch/session state, loop/budget inspection, and approval tools. | Does not forge or override specialist evidence, construct granular execution mutations, silently alter an approved protocol, expand scope, reuse confirmatory evidence for tuning, admit code, promote models, or execute trades. |
| Data Research Agent | Determine the data investigation needed, choose discovery/quality/ingestion tools, assess fitness, and propose remediation. | Symbol discovery, inventory, ingestion, dataset manifests, calendar-aware quality, bounded data summaries. | Does not decide strategy merit or hide quality failures. External acquisition remains gated. |
| Knowledge Research Agent | Translate a research question into evidence obligations; inspect source structure; iteratively retrieve and expand exact evidence across approved sources; reconcile support, complementarity, conflict, and gaps; and produce a cited research dossier. | Source registration and ingestion requests, source maps, hybrid and structural retrieval, bounded evidence resources, exact claim spans, dossier creation and validation. | Does not invent missing method detail, treat a generated summary as evidence, choose a trading candidate from performance, author code, approve its own dossier, or acquire an unapproved source. |
| Quantitative Methods Agent | Before code or backtests exist, turn an accepted research dossier into a source-faithful implementation brief and state necessary engineering decisions separately. | Validated research dossiers, method contracts, formal/reference checks, Trader interface constraints, and implementation-brief validation. | Does not inspect outcomes, select experiment statistics, silently fill source gaps, hide conflicts, or author executable code. |
| Strategy Engineering Agent | Decide whether to reuse, adapt, or author a candidate from an accepted source-backed or operator-specified build contract; inspect failures; revise code; and submit an implementation for admission. | Typed build contracts, implementation catalogue/comparison evidence, isolated coding workspace, repository search, file editing, tests, strategy/risk admission and validation. | Generated code is untrusted until admitted. It cannot fill missing behavioral semantics, reinterpret research evidence, write the product repository, or execute outside its sandbox without explicit developer authority. |
| Experiment Design Agent | Turn the question, exact candidate, and Data slice into a prospective experiment charter: hypotheses, baseline/selection protocol, evidence partitions, protected-stage envelopes, criteria, overall budgets, confounders, and approvals. When new evidence warrants scope-level redesign, propose a separately identified successor protocol. | Artifact reads, protocol proposal, power/sample checks, experiment-cost estimation, evidence-stage and authority-envelope validation. | Cannot revise the protocol after observing protected results under the same identity, design detailed specialist attacks/folds, hide predecessor evidence, or approve its own assumptions. |
| Robustness & Walk-Forward Agent | Synthesize coordinator-supplied canonical outputs from relevant specialists into a staged robustness/WFO plan; after validation and approval, operate specialist tools, recover jobs, inspect sensitivity and stitched out-of-sample behavior, and identify gaps. | Experiment charter, Data/method/implementation/execution/ML/review refs, immutable plan/variant/fold operations, attack and walk-forward execution/stitching, robustness reports. | Cannot expand the charter, approve its own material assumptions, hide which evidence informed its plan, mutate an approved plan after seeing results, or issue the final recommendation. |
| ML Signal Research Agent | Choose point-in-time features, training/evaluation approach, model family, tuning protocol, and drift investigation for complex signals. | Feature/training artifacts, MLflow experiments and registry, predictive evaluation, deployment parity, prediction and drift evidence. | Cannot promote a model or treat training metrics as trading evidence. Backtests and independent review remain required. |
| Evaluation Agent | Challenge evidence completeness, leakage, selection bias, costs, robustness, and alternative explanations; issue an independent verdict. | Read-only access to canonical evidence, attribution, evaluation reports, requested follow-up tasks through the coordinator. | Cannot mutate experiments, create a better-looking result, or approve paper trading. |

A validated robustness/WFO plan may proceed without another operator decision only when every material field remains
inside the already approved Experiment Design envelope. New material assumptions, scope, protected-data access,
cost/compute exposure, external mutation, or model-training policy interrupt through the coordinator for explicit
authority; splitting work cannot evade the envelope.

Experiment execution is a deterministic MCP capability, not an agent. The coordinator invokes main-protocol
compilation/execution for baseline, comparison, and optimisation work; RWFO invokes a plan-pinned specialist execution
surface for variants and folds. Code owns scheduling, resource enforcement, idempotent recovery, reconciliation, and
canonical persistence. Semantic blockers return to the invoking agent rather than being resolved inside execution.

Hypothesis generation is initially a responsibility of Experiment Design, assisted by Strategy Engineering and
Quantitative Methods. It becomes a separate agent only if evaluation shows that an isolated divergent-ideation context
improves outcomes. Final recommendation synthesis initially belongs to the coordinator, but it must preserve the
Evaluation verdict and cited dissent rather than averaging it away.

## Per-Agent Design Authority

Complete per-agent architecture records, review status, and shared pattern-review gates are maintained in
[Agent Designs](agent_designs.md). This redesign document defines the system-level direction and does not duplicate
those build-lifecycle records.

## Runtime Architecture

### Primary framework candidate

The current recommendation to test is LangChain and LangGraph as one stack. This is not an accepted production pattern
until the agent-boundary review and subsequent pattern/framework spike are complete:

- LangChain `create_agent` would supply each model/tool loop, structured responses, model abstraction, and middleware.
- LangGraph would supply the durable supervisor graph, specialist subgraphs, checkpoint persistence, parallel delegation,
  streaming, retries, and human interrupts.
- Under this candidate, specialist agents would be per-invocation subgraphs by default while the coordinator thread is
  persistent. A specialist would get durable per-thread memory only when its product role genuinely spans multiple
  operator turns.
- The graph would have generic nodes for coordinator inference, specialist dispatch/join, tool execution, approval, and
  completion. Product research sequences live in the model-maintained agenda, not in topology named after delivery
  checkpoints.
- Every specialist dispatch edge must rejoin the coordinator. A downstream delegation is a new coordinator decision over
  the returned evidence, never a fixed specialist-to-specialist edge.

Official LangChain guidance distinguishes a multi-turn supervisor from a one-shot router and recommends subagents for
centralized control and context isolation. LangGraph persistence and interrupts provide the required long-running and
human-in-the-loop behavior. See the official
[multi-agent patterns](https://docs.langchain.com/oss/python/langchain/multi-agent/index),
[subagent pattern](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents),
[subgraph persistence](https://docs.langchain.com/oss/python/langgraph/use-subgraphs), and
[interrupt semantics](https://docs.langchain.com/oss/python/langgraph/interrupts).

### Framework spike before commitment

The first implementation activity must be a disposable spike, not production scaffolding. It must connect one real
model-backed coordinator to two specialists, at least two MCP servers, a Postgres checkpointer, one operator interrupt,
and MLflow tracing. The model must choose a different delegation/tool sequence for materially different requests and
must replan after a tool returns a blocker.

Run the same bounded scenarios through PydanticAI as a typed alternative. Compare:

- MCP integration and session handling;
- subagent context isolation and parallel calls;
- structured-output reliability;
- durable resume and approval ergonomics;
- framework observability and MLflow trace quality;
- provider portability, testing ergonomics, and dependency cost.

Proceed with LangChain/LangGraph unless the spike finds a concrete blocking failure. Do not preserve the losing spike
behind an abstraction layer. PydanticAI's official
[multi-agent](https://pydantic.dev/docs/ai/guides/multi-agent-applications/) and
[MCP client](https://pydantic.dev/docs/ai/mcp/client/) capabilities make it a credible comparison, not a required runtime
dependency.

### DSPy position

DSPy is an optimization layer, not the durable coordinator. After baseline agent scenarios and metrics exist, express
selected high-value decisions as DSPy signatures/modules and optimize them offline against held-out evaluation sets.
Initial candidates are protocol proposals, robustness plans, and evidence-grounded Evaluation reports.

DSPy-optimized instructions and demonstrations must be versioned as agent program artifacts and loaded by the relevant
LangChain agent. Do not nest a DSPy ReAct loop inside a LangChain agent unless a measured experiment proves that the
double loop improves quality enough to justify its complexity. Optimizer development and evaluation datasets must be
separated to avoid optimizing the reported benchmark. See DSPy's official
[programming and optimization model](https://dspy.ai/) and
[GEPA documentation](https://dspy.ai/api/optimizers/GEPA/overview/).

### Provider and model policy

No agent is hard-coded to one model provider. A versioned model profile records provider, model, sampling/reasoning
settings, tool/structured-output capabilities, timeout, retry policy, token budget, and cost budget. Each agent may use
a different profile. Dynamic model selection is policy-controlled and included in traces and evaluation.

Model upgrades are product changes. They require replay over the behavioral evaluation suite before promotion.

The repository currently has LangGraph and MCP runtime dependencies, but no direct LangChain agent, MCP adapter, DSPy,
or model-provider dependency. Transitive packages do not constitute an agent stack. The framework spike must select and
record explicit compatible versions, provider extras, transport adapters, tracing integrations, and upgrade policy
before the production dependency set changes. Version choice should be based on exercised capabilities rather than a
framework name or an untested “latest” constraint.

## MCP Capability Architecture

MCP remains the only normal route from agent code to Trader research capabilities. LangChain's official
[MCP adapters](https://docs.langchain.com/oss/python/langchain/mcp) can load tools across multiple servers. Tools are
model-controlled capabilities, so exposure and approval must be deliberate, consistent with the MCP
[tool safety model](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

The target separates servers or logical façades by trust and lifecycle boundary:

| Capability boundary | Examples | Mutation posture |
| --- | --- | --- |
| Trader Data MCP | Symbol discovery, inventory, quality, ingestion planning, approved backfill, dataset snapshots. | Reads open; external/local data mutation separately gated. |
| Trader Knowledge MCP | Approved-source metadata, ingestion/quality, source maps, hybrid/structural retrieval, exact evidence resources, research dossiers, implementation briefs, and validation. | Evidence reads bounded; source ingestion and immutable dossier/brief writes gated separately. No arbitrary filesystem or unapproved-source access. |
| Trader Research MCP | Implementations, specifications, backtests, comparisons, optimisation, robustness, walk-forward, attribution, evaluations, recommendation artifacts. | Canonical writes and costly execution gated by role, session, and budget. |
| Coding Workspace MCP | Search/read a pinned repository snapshot, edit a disposable workspace, run allowlisted tests/scripts, package a candidate, request admission. | Containerized and isolated; no production credentials, broker access, or direct repository merge. |
| MLflow MCP or typed adapter | Experiments, runs, datasets, traces, registered model versions, evaluation, and bounded promotion requests. | Read and run creation gated separately from model-version promotion. |
| Research Session MCP | Agenda, approvals, artifact references, public summaries, budgets, and candidate paper-trade handoff. | Session mutations audited; paper candidate creation requires operator approval. |

Tools should be task-level capabilities with typed inputs and bounded outputs, not thin wrappers around arbitrary SQL,
shell, or internal services. Large immutable evidence should be exposed as MCP resources or bounded artifact reads rather
than copied into every prompt. Tool descriptions and schemas are part of the agent program and therefore versioned and
evaluated.

Each agent receives a small role- and phase-specific toolset. Middleware may narrow tools further using current state,
permissions, and budget. Credentials and database handles remain runtime context and are never inserted into model
messages.

## Research-Backed Implementation Architecture

### Problem and design position

The current knowledge subsystem proves source identity, full-document ingestion, hybrid retrieval, neighboring-context
expansion, exact claim spans, and method-card publication. Its book-scale limitation is not simply that chunks are too
small. It asks mostly deterministic local span assembly to discover a distributed method, decide which remote passages
belong together, reconcile several sources, and determine whether enough detail exists to write code. A larger top-k or
one larger prompt would move the boundary without solving those decisions.

LLM reasoning should therefore control an iterative research process over bounded retrieval tools. It must not replace
the evidence model. The design separates three units that the current flow partly conflates:

- **Retrieval unit**: a bounded exact source element or text window optimized for search and prompt size.
- **Understanding unit**: a model-assembled set of definitions, equations, algorithm stages, tables, examples, and
  cross-references needed to answer one evidence obligation. It may span chapters and sources.
- **Citation unit**: an exact immutable source element or claim span whose text, locator, offsets, and hash can be
  revalidated independently.

A source-backed implementation is produced only through a research dossier and an implementation brief. It is never
generated directly from retrieved chunks.

```text
approved source set + implementation question
  -> structure-preserving ingestion and source-quality report
  -> source maps and derived navigation summaries
  -> Knowledge Research Agent decomposes evidence obligations
  -> iterative global discovery, local retrieval, and structural expansion
  -> exact claim spans and cross-source claim matrix
  -> validated research dossier
  -> Quantitative Methods Agent creates an implementation brief
  -> independent evidence and brief validation
  -> Strategy Engineering Agent authors in an isolated workspace
  -> ordinary implementation admission, tests, experiments, and Evaluation
```

This is a hybrid RAG workflow: deterministic retrieval and validation surround model-owned query decomposition,
navigation, synthesis, and gap analysis. LangChain's current retrieval guidance explicitly distinguishes agentic and
hybrid RAG, including query rewriting, retrieval validation, and repeated retrieval for multi-source work. The
[LangChain retrieval architecture](https://docs.langchain.com/oss/python/langchain/retrieval) is a useful runtime
pattern, not the product evidence contract.

### Structure-preserving ingestion

Textbook ingestion must preserve more than page text. A source generation should retain, where the source supports it:

- edition, file hash, approval, licence/access, citation, parser, parser version, and ingestion configuration;
- chapter and section hierarchy, reading order, page and bounding-box provenance;
- paragraphs, lists, code or pseudocode, equations, tables, figures, captions, footnotes, and cross-references as typed
  source elements;
- exact normalized text plus a link to the immutable original representation;
- parser warnings, OCR confidence, dropped/ambiguous elements, and a source-quality/readiness assessment.

Leaf evidence units remain bounded and independently addressable, but they inherit structural paths and typed-element
metadata. Section, chapter, and source nodes provide larger navigation scopes without pretending that a whole chapter
is one citation.

The architecture spike should compare the current `pypdf` page-text extractor with a layout-aware parser. Docling is
the leading candidate because its document model represents hierarchy, reading order, layout provenance, equations,
tables, and pictures, and its hierarchical/hybrid chunkers retain headings and captions while applying token bounds.
See the official [Docling document model](https://docling-project.github.io/docling/concepts/docling_document/) and
[chunking model](https://docling-project.github.io/docling/concepts/chunking/). Adoption is conditional on Trader's
real textbook fixtures, deterministic export stability, licence review, operational cost, and materially better
evidence recovery; the plan does not select a parser by feature list alone.

### Index and embedding policy

Canonical source content and retrieval serialization are different records. Each typed source element retains exact
normalized text and provenance. A derived embedding input may prepend the source title, edition, heading path, element
type, table headers, or figure caption so that an otherwise shallow leaf remains semantically findable. That
contextualized serialization is hashed and versioned, but a retrieval hit always resolves back to the exact canonical
element or claim span for citation.

The initial index design has two explicit namespaces:

- the **evidence index** contains exact leaf elements and bounded text windows with lexical terms, vectors, structural
  metadata, and stable source-element refs;
- the **navigation index** contains source/section map nodes and any derived summaries used to discover where evidence
  may exist. Its results are non-citeable and must trigger evidence-index retrieval or structural dereferencing.

An index generation records source generation, parser/configuration, normalization, contextualizer, embedding provider,
model, dimensions, distance metric, and index schema. All elements and embeddings are staged and atomically published,
preserving the current all-or-previous-generation invariant. Parser, contextualizer, or embedding changes create a new
generation rather than mixing vectors. Formula, table, and figure serialization quality is evaluated separately;
multimodal embeddings are not required unless they outperform typed textual representations on the benchmark.

### Hierarchical navigation without synthetic evidence

For each successful source generation, Trader may derive a versioned source map containing the heading tree, typed
element inventory, named concepts, equation/table references, cross-references, and bounded section/chapter summaries.
These maps help a model decide where to look next. They are derived indexes with parser, model, prompt/program, and
source-generation identities. They are not source claims and may never satisfy a citation requirement.

Two external designs justify evaluating hierarchy beyond flat vector search:

- RAPTOR recursively organizes and summarizes retrieved text at multiple abstraction levels to address questions that
  need broader document context. Its motivation and evaluation are described in the
  [ICLR 2024 paper](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8a2acd174940dbca361a6398a4f9df91-Abstract-Conference.html).
- GraphRAG addresses corpus-level questions by deriving entity/relationship and community summaries, while DRIFT adds
  local follow-up exploration. See the official
  [GraphRAG paper](https://www.microsoft.com/en-us/research/publication/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization/)
  and [DRIFT description](https://www.microsoft.com/en-us/research/blog/introducing-drift-search-combining-global-and-local-search-methods-to-improve-quality-and-efficiency/).

Trader should not adopt either architecture wholesale before measurement. The first candidate is the smallest useful
extension: typed document hierarchy plus agent-controlled iterative use of the existing Postgres hybrid retrieval.
Recursive summaries, a claim/concept graph, or graph-community search are added only if the evaluation corpus shows a
material gain that simpler structural retrieval cannot provide.

### Bounded iterative research loop

The Knowledge Research Agent operates one dossier attempt under cumulative source, retrieval-round, evidence-element,
character/token, elapsed-time, and cost budgets. Each tool call remains bounded, and the session budget prevents the
agent from evading limits through many individually legal calls.

1. **Define obligations.** Convert the implementation goal into answerable evidence obligations: identity and scope,
   definitions, inputs/outputs and units, equations, ordered algorithm stages, state and initialization, parameters,
   signal/decision semantics, failure modes, validation expectations, and source-specific unknowns.
2. **Assess sources.** Confirm approval, edition, suitability, parsing quality, topical coverage, and whether a source
   is primary, explanatory, corroborating, or unsuitable for the requested claim.
3. **Map globally.** Inspect source outlines and derived source maps to locate likely chapters, remote dependencies, and
   terminology variants. A generated summary proposes search directions only.
4. **Retrieve locally.** Run lexical/vector searches for each obligation, using source, section, element-type,
   equation/table, and structural-path filters where useful.
5. **Expand structurally.** Dereference exact hits and expand by neighbors, containing section, referenced equation or
   table, definition site, and explicit cross-reference. Expansion is driven by the unresolved obligation rather than
   a fixed neighbor radius alone.
6. **Extract claims.** Select exact claim spans, bind them to an obligation and method/component identity, and retain
   rejected candidates with concise public reasons.
7. **Compare sources.** Classify support as corroborating, complementary, conflicting, edition-dependent, or absent.
   Generate targeted follow-up queries for unresolved terms and disagreements.
8. **Audit coverage.** A separate validator checks every dossier statement against the exact evidence, identifies
   unsupported synthesis, and decides whether the attempt is implementation-ready, descriptive-only, or blocked.

The agent may repeat steps 3-7 only when it states the unresolved obligation and expected information gain. Equivalent
queries or expansions without new evidence are rejected by the ordinary loop guard. Exhausted budgets or a material
gap produce a blocked dossier, not a guessed completion.

### Research dossier contract

The research dossier is the durable handoff from source investigation to quantitative method design. It contains no
executable code and includes at least:

- dossier, source-generation, research-branch, attempt, agent-program, model-profile, and query-budget identities;
- the implementation question, permitted source set, suitability decisions, and parsing-quality warnings;
- a method/component graph showing stages, dependencies, terminology aliases, and unresolved component boundaries;
- an obligation matrix for definitions, mathematics, data, algorithm order, parameters, state, edge cases, failure
  modes, and validation;
- one or more exact claim-span refs for every source-backed statement, plus the source locator and relationship to the
  obligation;
- cross-source status for each claim: single-source support, corroborated, complementary, conflicting, superseded by
  edition, or unresolved;
- derived synthesis that explicitly lists all supporting and contradicting refs;
- gaps, rejected interpretations, uncertainty, and an implementation-readiness verdict.

Sources do not vote by count. A later edition may supersede an earlier definition; a primary mathematical source may
define a formula while a textbook explains implementation; two credible sources may describe genuinely different
variants. Source suitability and declared precedence resolve compatible cases. A material conflict remains visible and
either branches the method variant or blocks the brief.

### Implementation brief contract

The Quantitative Methods Agent consumes a validated dossier and produces a separate implementation brief. This keeps
source research out of the coding agent's context and makes the handoff reviewable before any code exists. The brief
contains:

- method/variant identity and component dependency order;
- typed inputs, outputs, units, timing assumptions, and data-frequency constraints;
- normalized equations and symbol definitions linked to the exact supporting source elements;
- ordered algorithm or pseudocode, state transitions, initialization/warmup, missing-value behavior, and termination;
- parameter meanings, bounds, and defaults only where evidence supports them;
- invariants such as no-lookahead timing, numerical constraints, and expected relationships;
- test obligations, reference examples where licensed and available, edge cases, and failure behavior;
- explicit **source-backed decisions**, **Trader engineering decisions**, and **unresolved decisions** in separate
  fields;
- the research-dossier identity, validation outcome, and required human approvals.

An engineering decision can be legitimate without being quoted from a textbook—for example, a stable internal type or
error-handling convention. Behaviorally material Trader adaptations—such as timing, warmup, state, missing-value, unit,
or input-role decisions—belong explicitly in the brief and require their own rationale and approval when they are not
source-backed. Non-semantic code organization belongs to Strategy Engineering. Neither category may alter sourced
method semantics silently. A missing equation, ambiguous execution timing, unknown initialization, or unsupported
parameter default is a blocker when it could materially change behavior.

Only an accepted brief reaches Strategy Engineering. The generated implementation then follows the same independent
admission, deterministic tests, prospective experiment, robustness, and Evaluation path as any other candidate.
“Source-backed” describes provenance and fidelity; it is not evidence of profitability or production fitness.

### LLM authority and validation boundary

The Knowledge Research and Quantitative Methods models may:

- decompose questions, propose terminology and component relationships, choose retrieval tools, and refine queries;
- summarize source structure for navigation, synthesize claims across exact spans, and identify coverage gaps;
- propose a dossier, normalized mathematics, pseudocode, tests, and implementation decisions in typed output.

They may not:

- cite a model-generated summary, embedding, retrieval score, memory, or hidden reasoning as source evidence;
- fabricate missing equations, defaults, timing, assumptions, references, or source agreement;
- make an unsuitable or unapproved source authoritative;
- approve their own evidence, erase a conflict, write implementation code in the knowledge context, or expose hidden
  chain of thought.

Deterministic validators re-resolve source generation, structural element, offsets, hashes, quotation bounds, dossier
lineage, claim coverage, and brief/dossier consistency. A context-isolated evidence review should evaluate semantic
entailment and completeness without seeing persuasive hidden reasoning from the authoring agent. Model, program,
schema, retrieval-index, embedding, parser, and source identities are all traceable.

### Target MCP affordances

The capability inventory should judge the current knowledge tools against the tasks below. These are responsibility
names, not settled tool names or a demand for one tool per row.

The provisional disposition of the existing knowledge surface is:

| Current surface | Design disposition | Reason |
| --- | --- | --- |
| `knowledge_register_source`, `knowledge_list_sources`, `knowledge_get_ingestion_status` | Retain by fitness, extending metadata/quality where required. | Approved source identity, status, and audit remain valid boundaries. |
| `knowledge_ingest_documents` | Redesign internally and extend its output contract. | Atomic full-document generation is sound; page-text extraction lacks the typed layout/hierarchy needed for textbooks. |
| `knowledge_retrieve_evidence` | Retain the hybrid baseline and extend or complement it with structural filters and source-map navigation. | Lexical/vector search is useful local discovery, but one top-k result set is not an understanding workflow. |
| `knowledge_get_evidence_chunks` | Retain bounded exact dereferencing, generalized to typed elements/resources and structural expansion. | Exact immutable text and hashes remain the citation foundation; large evidence should not be copied into tool envelopes. |
| Candidate discovery, evidence assembly, field extraction, and candidate validation tools | Retain for bounded method-card work only if benchmarked useful; replace as the composite implementation path with dossier/brief contracts. | Their deterministic local role assembly is the observed book-scale bottleneck and should not constrain the clean redesign. |
| Method-card search, draft/publication, and citation validation | Retain by fitness, but do not force a dossier or implementation brief into one card. | Approved method descriptions remain reusable; cross-source research and coding handoff have different responsibilities. |
| `math_generate_python_method` | Removed from the registered MCP surface. | Knowledge/Quantitative Methods produce evidence and a brief; Strategy Engineering owns code in the isolated workspace. MCP must not own a model loop or import the agent package. |

The Python generation removal is reflected in the active tool catalog. The remaining rows are design recommendations,
not implicit tool-catalog changes; each formal MCP change must still confirm side effects, role exposure, resource
shapes, idempotency, approval, and removal before implementation.

| Agent task | Target affordance | Output posture |
| --- | --- | --- |
| Inspect a source | Read source metadata, quality report, typed outline, element inventory, and derived source map. | Small typed result plus resource links. |
| Search evidence | Hybrid search across approved sources with structural, type, locator, and terminology filters. | Ranked evidence refs and diagnostics, never truth labels. |
| Expand context | Fetch bounded neighbors, containing sections, definitions, equations, tables, figures/captions, and cross-references. | Exact immutable elements through paginated/bounded resources. |
| Compare claims | Resolve exact spans for several sources and record support/conflict relationships. | Claim matrix with refs and explicit uncertainty. |
| Build a dossier | Create or revise an immutable dossier attempt from structured claims and gaps. | Canonical artifact ref; mutation is idempotent and policy-gated. |
| Validate a dossier | Recheck provenance, support, coverage, source suitability, conflicts, and budgets. | Passed, descriptive-only, or blocked report with issues. |
| Build a brief | Transform a passed dossier into a structured implementation proposal. | Proposed brief; no code or implicit approval. |
| Validate/accept a brief | Recheck dossier consistency, source/engineering separation, completeness, and operator decisions. | Accepted or blocked brief ref. |

MCP tools perform deterministic reads, writes, validation, and execution. The model-controlled research loop belongs to
the agent runtime, not inside one opaque `research_everything` tool. Conversely, the model should not juggle arbitrary
SQL-shaped primitives. MCP resources are the preferred delivery mechanism for large immutable evidence because the
protocol distinguishes application-controlled resources from model-controlled tools; see the MCP
[server primitive model](https://modelcontextprotocol.io/specification/2025-06-18/server/index).

### Qualification and staged decision

Before implementation, build a reviewed textbook corpus containing at least:

- one bounded indicator whose evidence is locally complete;
- one composite multi-stage framework distributed across a book;
- one method whose formula, initialization, and execution rule occur in different sections;
- equations, tables, figures, pseudocode, and cross-references that stress parsing and retrieval;
- multiple sources that corroborate, complement, conflict, and differ by edition;
- an intentionally absent parameter or timing rule that must produce a blocker;
- adversarial instructions embedded in source text.

Compare the current deterministic top-k/span-assembly baseline with structure-aware iterative retrieval. Measure
claim-level retrieval recall, citation precision and entailment, obligation coverage, conflict detection, unsupported
fact rate, dossier/brief reviewer agreement, implementation fidelity, downstream deterministic test results, tool
calls, tokens, latency, and cost. Use ablations for layout-aware parsing, document hierarchy, derived summaries,
reranking, and any graph layer.

The initial architecture decision should choose the simplest measured design that meets reviewed thresholds. DSPy may
later optimize query generation, claim extraction, dossier synthesis, or evidence review against this labelled corpus;
its structured signatures and optimizers make it suitable for measurable programs, as described in the official
[DSPy documentation](https://dspy.ai/). It remains an offline program-optimization layer, not a competing coordinator
or a substitute for source provenance.

### Coding authority

Research strategy creation and product-repository maintenance are different authorities:

- A Strategy Engineering Agent may author candidate strategy, risk, feature, or evaluation code in an isolated
  workspace. It submits a content-addressed package to the normal validation and admission path.
- Before authoring, it must use bounded MCP catalogue capabilities to discover and compare relevant maintained and
  previously admitted implementations against the accepted build contract. It explicitly chooses reuse, adaptation,
  or new authorship; similarity rankings are not proof of behavioral compatibility.
- Adapted code creates a new content-addressed version with parent lineage and passes full admission. The target MCP
  inventory must add versioned implementation indexing, typed/semantic search, bounded source/evidence retrieval, and
  brief-compatibility support beyond today's maintained-template lists.
- Only exact maintained or previously admitted versions are eligible for direct reuse. External, legacy, failed, or
  otherwise unadmitted code is explicitly untrusted reference material; any candidate derived from it, and every
  modified admitted version, creates new lineage and passes the complete current admission path.
- It may run only allowlisted commands in an ephemeral container with explicit CPU, memory, wall-time, filesystem, and
  network bounds.
- The container receives a pinned read-only Trader snapshot and separate candidate workspace, no general network or
  credentials, and dependency resolution only through a deterministic MCP operation over approved, version-and-hash-
  pinned repositories or mirrors. Disallowed dependencies interrupt for authority rather than being fetched or
  substituted by the model.
- Passing self-authored tests is not admission. Independent deterministic validation and, where useful, an Evaluation
  review are required.
- Normal coding attempts are outcome-blind. A coordinator-authorized defect investigation may expose only bounded
  execution traces needed to test an implementation fault. Performance-driven or behavior-changing revision requires
  a successor build contract and branch; sealed evidence cannot tune the candidate it evaluated.
- Admission repair is bounded by candidate-attempt, tool, time, and compute budgets. Each revision requires an
  actionable finding, stated defect hypothesis, and materially changed content-addressed candidate; equivalent
  failures or contract/policy problems terminate or escalate rather than looping.
- Editing Trader itself, committing, pushing, opening pull requests, or running general infrastructure scripts belongs
  to an explicitly entered developer workflow. A research request never grants that authority implicitly.
- A future coding-agent service, including Codex exposed through MCP, may implement the workspace contract. The
  orchestration design must not depend on one coding vendor.

## State, Memory, And Evidence

### Research session state

The coordinator's durable state contains only information needed to continue the product interaction:

- session, user, thread, and model-profile identities;
- the current brief, constraints, success criteria, and bounded budgets;
- a model-authored agenda with task status and dependency references;
- specialist delegation summaries and structured return values;
- immutable research-branch, parent-attempt, successor-protocol, and candidate lineage;
- coordinator decision receipts, transition fingerprints, expected information gain, and loop counters;
- canonical artifact references and immutable content identities;
- approval requests and decisions;
- blockers, warnings, uncertainty, and public conversation summaries;
- trace, prompt/program, tool-catalog, and evaluation-version references.

It does not contain hidden chain of thought, raw credentials, full market datasets, complete source corpora, feature
matrices, arbitrary shell output, or an unbounded copy of every tool payload.

### Context policy

- The coordinator sees the operator conversation, agenda, approval state, and bounded specialist summaries.
- A specialist sees one delegation brief, relevant artifact refs/resources, its own instructions and tools, its budget,
  and only the conversation excerpts needed for its decision.
- Evaluation gets evidence and declared claims, but not persuasive private summaries from the strategy author when the
  underlying artifact is available.
- Tool and artifact content is untrusted data, not instruction. Retrieved documents, strategy comments, datasets, and
  model metadata cannot grant tools or change role policy.
- Context is summarized deliberately when it grows. Summaries state provenance and may not replace canonical evidence.

LangChain middleware is the leading mechanism to test for dynamic prompts, tool selection, guardrails, summarization,
model selection, and lifecycle instrumentation. Structured outputs must use provider-native schemas where supported
and a validated tool strategy otherwise. See the official
[context engineering](https://docs.langchain.com/oss/python/langchain/context-engineering),
[middleware](https://docs.langchain.com/oss/python/langchain/middleware/overview), and
[structured output](https://docs.langchain.com/oss/python/langchain/structured-output) guidance.

### Authority split

| Store | Authoritative for | Not authoritative for |
| --- | --- | --- |
| Trader Postgres | Source/evidence identity, research dossiers, implementation briefs, dataset identity/quality, implementations, specifications, executions, ledgers, robustness evidence, evaluations, recommendation inputs, approvals, and paper-candidate records. | Hidden reasoning or raw agent transcripts. |
| LangGraph checkpointer/store | Recoverable session state, messages, agenda, delegation state, and explicit curated memory. | Financial claims or completed experiment evidence. |
| MLflow | Signal/model runs and packages; agent traces, prompt/program versions, evaluation datasets/results, latency, token/cost, and model configuration. | The truth of a trading recommendation or permission to trade. |
| Coding workspace | Ephemeral candidate source, tests, and build output before admission. | Canonical implementation identity after the workspace is destroyed. |

Every final claim must cite canonical artifacts. An MLflow trace can explain how an agent reached a conclusion but is
not evidence that the strategy performs.

## MLflow For Complex Signals And Agent Quality

MLflow has two related roles.

### Signal and model lifecycle

The ML Signal Research Agent should be able to create point-in-time feature definitions, training datasets, split
plans, model runs, predictive evaluations, immutable model versions, and drift reports. Trader artifacts cross-reference
the MLflow experiment/run/model-version identities and content digests. A model becomes usable in a strategy only after
promotion approval, package validation, runtime parity, and point-in-time evidence.

Model selection remains inside a prospective protocol. Training metrics, registry status, or a compelling feature
importance plot cannot substitute for costs, sealed trading backtests, walk-forward evidence, robustness, and independent
Evaluation.

### Agent engineering lifecycle

Instrument coordinator, model, delegation, and tool spans with MLflow tracing. Record model and agent program versions,
structured outcomes, tool-call names and status, latency, tokens/cost, feedback, and links to Trader artifacts. Build
offline evaluation datasets from reviewed scenarios and production traces only after privacy and provenance review.

Use trajectory scorers for delegation, tool-call correctness and efficiency, grounding, approval behavior, and safe
termination. Use human and LLM judges only for declared subjective criteria, calibrated against expert labels. MLflow's
official documentation supports
[agent evaluation](https://mlflow.org/docs/latest/genai/eval-monitor/running-evaluation/agents/),
[trace evaluation](https://mlflow.org/docs/latest/genai/eval-monitor/running-evaluation/traces/), and
[DSPy optimizer tracking](https://mlflow.org/docs/latest/genai/flavors/dspy/optimizer/).

Avoid two observability systems in the initial product. LangSmith may be used temporarily during the framework spike if
it resolves a LangGraph-specific debugging problem, but MLflow is the planned durable evaluation and tracing surface.

## Human Authority And Safety

The coordinator may act autonomously only inside a configured research envelope. Approval is required for:

- ambiguous or material experiment assumptions;
- external data acquisition or mutations above configured bounds;
- non-sandboxed code execution or any product-repository mutation;
- expensive backtest, optimisation, walk-forward, or model-training work above session budgets;
- use of a new external provider or credential scope;
- MLflow model-version promotion or deployment-manifest activation;
- creation of a paper-trade candidate handoff.

Approval is never inferred from silence or from an earlier unrelated session. LangGraph interrupts persist a typed
request and resume against the same thread. Because an interrupted node can restart, side effects before an interrupt
must be absent or idempotent.

Research agents may recommend a strategy for paper-trade review. They cannot deploy it, start a session, submit an
order, clear a halt, reconcile a broker, or weaken core risk policy. A separate deterministic operator workflow owns
those actions.

Additional controls include:

- maximum model turns, delegation depth, concurrent tasks, tool calls, elapsed time, token cost, and compute cost;
- tool-level idempotency keys and canonical argument/result digests;
- fail-closed role and side-effect policy checked outside model output;
- sandbox and network policy for generated code;
- explicit treatment of MCP/resource content as untrusted data;
- complete public audit of approvals and externally visible actions without hidden-reasoning retention;
- provider outage, partial result, timeout, retry, cancellation, and resume behavior.

### Loop and scope guards

Returning to an earlier responsibility is valid research iteration, but the recorded work graph remains acyclic. A
revision, new parameter search, asset change, or redesigned protocol creates a new attempt or branch with immutable
parent lineage; it never rewrites a completed node or points execution back into an old mutable state.

Before dispatch, deterministic policy evaluates:

- whether the proposed action is inside the operator brief, approved protocol, agent authority, and remaining budget;
- whether the same specialist, objective, input refs, requested output, and constraints have already been dispatched;
- whether the prior return added material evidence or changed a declared assumption;
- per-task revision, per-branch fork, repeated-transition, total-turn, elapsed-time, token, and compute limits;
- whether the action would tune against a sealed holdout, walk-forward result, or independent Evaluation evidence while
  retaining the same confirmatory claim;
- whether the coordinator is attempting to decide something reserved for an operator or specialist authority.

An exact or materially equivalent transition without new evidence is rejected. Repeated low-information transitions,
exhausted limits, evaluation contamination, and out-of-scope decisions produce a fail-closed terminal return or an
operator interrupt when the brief permits escalation. The model may explain why more work could be useful, but it
cannot override these guards or reset counters by paraphrasing the task.

## Evaluation Strategy

Agent correctness is behavioral and statistical, not byte-for-byte deterministic. Deterministic tool tests continue,
while agent qualification uses repeatable scenarios, trajectory constraints, and distributions over multiple runs.

### Evaluation dimensions

| Dimension | Example evidence |
| --- | --- |
| Brief interpretation | Required constraints captured; material ambiguity clarified; no invented scope. |
| Delegation | Correct specialist selected; irrelevant specialists avoided; safe parallel work used. |
| Coordinator evidence review | Every specialist return is checked against canonical refs and brief criteria; routing rationale matches the evidence rather than the specialist's preferred next step. |
| Tool use | Correct MCP tool and arguments; bounded retries; no forbidden capability attempt. |
| Replanning | A blocker, quality failure, invalid implementation, or weak result produces an appropriate revised agenda or stop. |
| Iteration discipline | Revisions and forks preserve lineage, multiplicity, partitions, prior failures, and budgets; equivalent low-information loops fail closed. |
| Scientific quality | Prospective protocol, leakage control, costs, sealed evidence, multiple-testing awareness, and falsification behavior. |
| Grounding | Claims cite matching canonical refs; artifact status and caveats are represented faithfully. |
| Independence | Evaluation and robustness findings are not overwritten by coordinator or strategy-author preference. |
| Human authority | Every material gate interrupts; rejection is respected; resume does not replay mutations. |
| Safety and security | Prompt injection in artifacts fails; secrets stay out of context; broker/live tools are unreachable. |
| Operational quality | Fresh-process recovery, cancellation, timeouts, provider failure, bounded concurrency, latency, and cost. |

### Required scenario families

- Existing-data strategy research with no ingestion.
- Missing-data request with allowed and denied acquisition variants.
- Reuse of a maintained strategy versus authoring a new candidate.
- Research-backed implementation from several approved textbook sources, including distributed definitions,
  equations, state, and algorithm stages.
- Conflicting textbook variants and a materially missing implementation detail that must block rather than be guessed.
- Candidate code that fails admission and is revised or abandoned.
- Baseline failure that should stop further search.
- Poor baseline with separately tested in-scope hyperparameter, out-of-scope hyperparameter, and asset-pair change
  responses.
- Several-comparison scenario that requires multiple-testing control.
- Robustness failure that contradicts a strong baseline.
- Promising baseline that is correctly advanced to walk-forward, followed by stable and unstable walk-forward variants.
- Strategy and model-signal variants using MLflow.
- Walk-forward analysis with fold failure and stitched out-of-sample review.
- Conflicting specialist conclusions requiring cited coordinator synthesis.
- Repeated specialist handoffs with no material new evidence, paraphrased duplicate work, exhausted branch limits, and
  a coordinator attempt to exceed its authority.
- Prompt injection embedded in source text, strategy code, artifact metadata, and MCP results.
- Approval rejection, model/provider outage, lost tool response, restart, cancellation, and exhausted budget.

### Agentic acceptance proof

The first accepted vertical slice must demonstrate all of the following against real Postgres, real MCP transport, a
real configured model, Postgres checkpoint persistence, and MLflow tracing:

1. A natural-language brief is converted into a visible agenda without a caller constructing specialist tasks.
2. Every specialist outcome, including partial and failed work, rejoins the coordinator through the evidence-return
   contract before another specialist is invoked.
3. Across the suite, the coordinator selects and invokes Data Research, Knowledge Research, Quantitative Methods,
   Strategy Engineering, Experiment Design, Robustness, and Evaluation agents as needed, while
   omitting at least one irrelevant specialist in another scenario.
4. At least one specialist chooses among multiple MCP tools and revises its action after an observation.
5. A knowledge-backed path uses source structure and iterative retrieval to produce a validated multi-source dossier
   and implementation brief whose material claims resolve to exact source elements; a missing-detail variant blocks
   before code authoring.
6. The coordinator independently dereferences returned evidence and makes materially different advance, revision,
   branch, approval, and stop decisions for poor, promising, stable, and unstable result scenarios.
7. In-scope hyperparameter exploration, successor-protocol design, and asset-scope changes retain correct trial,
   partition, approval, and branch lineage; prohibited result-chasing is rejected.
8. Equivalent repeated delegation, exhausted budgets, and an out-of-authority coordinator decision fail closed without
   a further specialist or MCP mutation.
9. An operator interrupt is persisted and respected across a fresh-process resume without replaying an accepted
   mutation.
10. Every research conclusion is grounded in matching canonical artifact refs and preserves dissent and uncertainty.
11. An adversarial scenario cannot obtain a forbidden tool, leak a credential, bypass approval, or trigger broker
   mutation.
12. Repeated runs meet agreed quality, safety, cost, and latency thresholds recorded in MLflow. A single successful demo
   is not acceptance.

Thresholds are set from the framework spike and reviewed scenario baseline; this plan does not invent arbitrary
numbers before measurements exist.

## Delivery Plan

These are capability milestones, not architecture names or fixed implementation checkpoint codes. No production agent
implementation begins until the design review and framework spike are accepted.

### Design and evaluation charter

- Approve agent responsibilities, authority boundaries, target experience, and paper-trading limit.
- Approve the evidence-return envelope, coordinator decision vocabulary, branch/attempt lineage, scope policy, and
  fail-closed loop semantics.
- Inventory existing MCP tools against agent tasks; retain, redesign, split, or remove each tool.
- Define scenario datasets, expert labels, trajectory constraints, cost/latency measures, and acceptance governance.
- Decide which current orchestration artifacts survive as product concepts rather than compatibility requirements.

### Framework and observability spike

- Run the LangChain/LangGraph and PydanticAI comparison described above.
- Exercise real MCP, a real model, Postgres resume, human approval, parallel specialists, structured outputs, and MLflow
  traces.
- Record the decision and remove the losing spike.

### Agent runtime foundation

- Establish model profiles, agent program identity/versioning, MCP adapters, context policy, role-aware dynamic tools,
  budgets, policy middleware, structured delegation/evidence-return/decision contracts, branch lineage, loop guards,
  checkpointing, interrupts, and trace correlation.
- Replace `trader_agents` in a clean cutover. Do not preserve old imports or checkpoint readers.
- Add explicit destructive reset instructions for development checkpoint state.

### First Coordinator–Data–Strategy slice

- Implement the coordinator, Data Research Agent, and Strategy Engineering Agent.
- Prove materially different natural-language agendas, multi-asset data fitness/backfill/revalidation, implementation-
  catalogue comparison, reuse/adapt/author decisions, isolated coding, admission failure/revision, canonical evidence
  handoff, interruption, restart, injection resistance, and bounded termination across repeated real-model runs.
- Stop at an admitted strategy/risk candidate for the initial qualification. Experiment Design and deterministic
  execution are the next extension rather than hidden first-slice scope.

### Research-backed implementation vertical slice

- Qualify structure-preserving ingestion and the simplest measured hierarchical retrieval design against the reviewed
  textbook corpus.
- Add the Knowledge Research and Quantitative Methods agents, source-map/evidence resources, dossier and implementation-
  brief artifacts, validation, and coordinator revision/stop behavior.
- Prove multi-source synthesis, exact claim-level provenance, conflict retention, blocked missing detail, isolated code
  authoring from an accepted brief, and ordinary implementation admission.
- Begin this slice only after the first Coordinator–Data–Strategy slice is qualified unless the roadmap is explicitly
  reprioritized.

### Prospective experiment loop

- Add the Experiment Design Agent and deterministic coordinator-invoked protocol execution/job MCP capabilities.
- Prove prospective design, material approval, baseline execution, bounded optimisation, result-driven but
  non-p-hacking replanning, successor protocols, permitted asset/candidate branches, and safe early termination.

### Robustness, walk-forward, and independent evaluation

- Complete deterministic robustness/WFO/attribution tools where gaps remain.
- Add the Robustness & Walk-Forward and Evaluation agents with intentionally isolated decision contexts.
- Prove that negative specialist findings survive final synthesis.

### Complex-signal lifecycle

- This lifecycle and the ML Signal Research Agent are parked until the first non-ML agentic slice is qualified and the
  roadmap explicitly reactivates them.
- Complete feature, training, model evaluation/versioning, runtime parity, monitoring, and drift capabilities.
- Add the ML Signal Research Agent and cross-reference MLflow lineage with Trader evidence.
- Qualify model-backed backtest, robustness, and walk-forward paths separately from conventional strategies.

### Recommendation and paper-candidate review

- Add grounded coordinator synthesis over complete Evaluation evidence.
- Create an operator-approved paper-candidate record and deterministic handoff to a separate paper-trading preparation
  workflow.
- Keep runtime deployment and broker mutation outside the research agent graph.

### Controlled agentic qualification

- Freeze an exact code, agent-program, tool-catalog, model-profile, evaluation-dataset, and environment identity.
- Run repeated behavioral, security, recovery, scale, cost, and latency evaluation against the same freeze.
- Record acceptance without claiming deterministic reproducibility of model wording or trajectories.

## Open Design Decisions

The following must be resolved during design review or the framework spike:

- Which model providers and model classes are required for the first supported profile?
- Which existing MCP tools are suitably task-level, and which should be merged, split, or replaced?
- Which layout-aware parser passes Trader's real textbook fixtures, and which source elements and hierarchy become
  canonical rather than derived?
- Does typed hierarchy plus iterative hybrid retrieval meet the dossier benchmark, or do recursive summaries or a
  claim/concept graph provide enough measured benefit to justify their complexity?
- What source-suitability and edition-precedence rules govern multi-source conflicts, and which conflicts always
  require an operator decision?
- Should long-running backtest/training operations use MCP jobs immediately or remain synchronous within initial
  bounds?
- What repository snapshot, network, package-install, and execution policies apply to Strategy Engineering sandboxes?
- Which research actions are pre-approved by environment, and which always interrupt?
- Which brief/protocol fields define poor, promising, and ready-for-walk-forward routing without turning those labels
  into universal performance claims?
- What material-change test and revision/fork budgets should trigger automatic loop termination versus operator
  escalation?
- Which agent program artifacts live in Git, Trader Postgres, or MLflow, and how are their identities linked?
- What expert-labeled scenarios and minimum quality/cost thresholds constitute promotion for each model profile?
- Does a separate recommendation agent improve independent judgment, or does it merely duplicate Evaluation and
  coordinator synthesis?

## Explicit Non-Goals

- Compatibility with the frozen deterministic orchestration layer.
- A generic autonomous company or unrestricted peer-to-peer agent society.
- Agent access to raw SQL, production credentials, or broker mutation.
- Persistence or exposure of hidden chain of thought.
- Automatic live or paper trading from a research conclusion.
- Unbounded strategy search until a favorable result appears.
- Framework accumulation without measured benefit.
- Treating an LLM-generated narrative, MLflow trace, or agent checkpoint as financial evidence.

## Documentation Cutover Rule

Until implementation starts, current-state documents continue to describe the frozen deterministic surface and link to
this plan as the target. During implementation, target behavior becomes current documentation only when it exists and
has direct evidence. The
[Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84) must mark old deterministic
agent expansion as superseded, while the repository preserves the controlled freeze as historical evidence.
