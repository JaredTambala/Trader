# Research Agent Architecture

Trader separates core trading runtime code from research tooling, MCP transport, and LangGraph agent orchestration.
Research agents produce deterministic artifacts for inspection and backtesting; they do not control live trading.

## Layer Model

| Package | Responsibility | Must not own |
| --- | --- | --- |
| `trader` | Core runtime platform: market data, event store, brokers, portfolio, strategy/risk interfaces, runtime service, backtesting, metrics, operator primitives. | Research services, MCP schemas, LangGraph agents. |
| `trader_standard` | Maintained implementations of core interfaces: indicators, signals, strategies, and risk managers. | Experiment orchestration, MCP adapters, agent state. |
| `trader_research` | Deterministic research services, tool envelopes, domain schemas, artifact contracts, method packages, strategy/risk candidates, diagnostics, backtests, reports. | MCP transport, live broker control. |
| `trader_mcp` | MCP server, tool registration, JSON adapters, server policy/config metadata, dependency injection into research services. | Research business logic, agent decision state. |
| `trader_agents` | LangGraph identities, state schemas, policy routing, tool allowlists, and handoff wiring over MCP tools. | Direct platform mutation or bypassing MCP when a tool exists. |

## `trader_research` Capability Packages

`trader_research` mirrors the bounded capability style used by the core `trader` package. Stable package-level exports
are canonical public surfaces; broad top-level service modules are not compatibility shims and should not be
reintroduced.

| Package | Responsibility |
| --- | --- |
| `trader_research.data` | Data Agent discovery, inventory, quality, provider context, and explicit loading services. |
| `trader_research.methods` | Quantitative Methods contracts, registry access, fixtures, diagnostics, multiple testing, kernels, and method-package handoffs. |
| `trader_research.strategy_candidates` | Maintained strategy template catalog, source-backed and rich-card-backed candidate generation, and candidate validation. |
| `trader_research.risk_managers` | Risk-manager template catalog and source-backed/rich-card-provenanced candidate generation. |
| `trader_research.backtests` | Data-scoped baseline backtest execution, result lookup, and comparison reports. |
| `trader_research.evaluation` | Evaluation-owned report services over persisted research evidence. |
| `trader_research.knowledge` | Knowledge-source registration, ingestion, indexing, retrieval, methodology candidates, method cards, and citation validation. |
| `trader_research.method_implementations` | Python method implementation registration, quarantine generation, and deterministic fixtures. |

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

MCP research artifact persistence is DB-first. Mutating methodology, method, strategy, risk-manager, portfolio-backtest,
and evaluation tools store canonical records in the configured Postgres research artifact store and return
`research://postgres/{artifact_type}/{artifact_id}` refs. Rich method cards are persisted as canonical knowledge-store
method-card payloads with shallow projections for older method-card search and citation paths. Filesystem exports remain
only for legacy direct-service fallbacks and backtest result artifacts that have not yet moved into structured storage.

LangGraph is the agent identity and orchestration layer. Agent graphs decide which MCP tools are allowed, how state is
retained, how specialist handoffs are routed, and which artifact must be produced. Agent code should call MCP tools
rather than core platform internals when a tool exists.

## Canonical Method Card Architecture

The target architecture treats a method card as the canonical, evidence-backed representation of a trading or research
methodology. A method card is not a lightweight note and it is not a prompt artifact. It is the structured object that
answers: what is the method, what evidence supports each part of it, what data does it require, how is it computed, how
does it produce decisions, what assumptions make it valid, what can break it, and what downstream generation is allowed
to do with it.

Older shallow method-card fields such as assumptions, inputs, outputs, and failure modes remain useful as projections,
but they should not be a parallel product surface. They are summary fields derived from the canonical method card so
search, citation, method-contract, and older packaging workflows can continue to operate. Strategy-grade workflows
should consume the canonical evidence-backed card or a projection that is known to be derived from it, not a hand-filled
summary record.

Conceptually, the Quantitative Methods layer contains a pipeline of specialist capabilities:

| Capability | Question answered | Primary owner |
| --- | --- | --- |
| Source registrar | What source did the operator approve for ingestion, and what is its identity, type, hash, and access policy? | Quantitative Methods Agent |
| Ingestion/indexing | What complete source text is citeable, chunked, embedded, and searchable? | Quantitative Methods Agent |
| Retrieval | Which chunks are relevant to a query, method family, or discovered source term? | Quantitative Methods Agent |
| Candidate discovery | Where in the source is a candidate methodology described? | Quantitative Methods Agent |
| Evidence assembly | Do we have enough definition, formula, parameter, signal, assumption, validation, and failure evidence to understand the method? | Quantitative Methods Agent |
| Field extraction | Which closed schema fields can be populated from the assembled evidence? | Quantitative Methods Agent |
| Methodology validation | Are the populated fields source-backed, internally coherent, and sufficient for the stated family? | Quantitative Methods Agent |
| Curated method-card approval | Has a human or allowed policy explicitly accepted this method card for downstream use? | Quantitative Methods Agent |
| Strategy/risk generation | Can an approved method card drive a maintained bounded template? | Quant Research Supervisor Agent |
| Backtest and evaluation | What happened when a validated strategy/risk artifact was run over a Data Agent scope? | Quant Research Supervisor Agent and Evaluation Agent |

This separation matters because retrieval alone is not methodology understanding. Retrieval can say that a chunk mentions
some named method, model, indicator, rule, or instrument structure. It cannot by itself say that the source provides
enough formula, threshold, input, assumption, and failure-mode evidence to create a strategy-grade method card. Candidate
discovery and evidence assembly are the bridge between search and structured understanding.

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
  -> citeable chunks and embeddings
  -> methodology candidate
  -> assembled evidence packet
  -> field extraction report
  -> methodology validation report
  -> method-card draft
  -> approved method card
  -> method package, strategy candidate, or risk-manager candidate
  -> validation and backtest evidence
```

Each stage records a different kind of truth.

- A source record proves that a source reference exists and has operator metadata. It does not prove the document was
  ingested.
- An ingestion run proves that the source text was processed into chunks and indexes. It does not prove a method was
  found.
- A methodology candidate proves that some span of chunks may describe a method. It does not approve the method.
- An assembled evidence packet proves that the system found field-role evidence, such as definition, formula, entry
  rule, exit rule, assumption, validation, or limitation chunks. It does not assert every field is populated.
- A field extraction report proves that closed schema fields were populated from specific chunks. Unsupported fields
  stay null.
- A validation report proves that the candidate satisfies source, citation, family, and readiness checks, or records why
  it does not.
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

- The adapter receives only citeable chunks and the closed output schema.
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

- consume approved method cards and validated method packages
- create bounded strategy/risk candidates from maintained templates
- validate strategy/risk candidates and stacks
- run gated backtests over Data Agent scopes
- pass backtest evidence to Evaluation
- preserve specialist artifact ownership in handoffs

The Quant Research Supervisor cannot:

- rewrite Quantitative Methods evidence
- forge method-card approval
- move symbols or date windows into method cards
- bypass strategy/risk validation
- treat a failed validation report as sufficient evidence

The Data Agent owns market-data scope. It is the only agent that should produce dataset manifests and data-quality
evidence. Method cards describe a methodology's data requirements, not the concrete data scope for a run.

The Evaluation Agent owns skeptical interpretation. It consumes backtest, risk, method, and data-quality evidence and
reports blockers, caveats, and performance conclusions. It should not repair missing methodology or rerun generation.

### Current Gap And Implementation Direction

The current 33H-33N implementation has the right artifact skeleton and one constrained evidence chain, but the
methodology-understanding capability is not yet strong enough. In particular, the current extraction layer is too
generic, and the public shallow method-card workflow can still be confused with the canonical method-card concept.

The next implementation direction should close these gaps in this order:

1. Retire shallow method cards as a public methodology workflow. Keep summary fields only as projections from canonical
   method cards or as explicitly legacy records.
2. Add diagnostics that explain candidate family attribution, field population rules, missing evidence roles, and
   validation blockers.
3. Make candidate discovery method-specific without hardcoding method targets: query terms, headings, definitions,
   equations, and repeated local phrases should produce named candidates, while source-level families remain scope hints
   rather than candidate labels.
4. Add family-level evidence assembly with role labels and missing-role reporting.
5. Replace generic keyword extraction with field-specific extractors and a bounded enrichment adapter interface.
6. Strengthen semantic validation and strategy-grade readiness checks.
7. Update strategy/risk generation to consume canonical readiness rather than accepting thin summary cards.

The desired end state is that an operator can ask for source-backed methodologies, the Quantitative Methods Agent can
show exactly what the source supports and what it does not, and downstream strategy generation can proceed only when the
method card is rich enough for the maintained template being used.

## Rich Methodology Flow

Rich methodology work is a DB-backed evidence pipeline, not an agent scratchpad. Source registration records the
reference, source type, file hash, and operator metadata. Full-document ingestion is the step that extracts text,
chunks the whole source, creates lexical/vector indexes, and makes every chunk citeable by source ID, chunk ID, locator,
and text hash.

Methodology candidate discovery and field extraction write Quantitative Methods artifacts in the research artifact
store. They are evidence-gathering steps only: candidates, extraction reports, and validation reports do not approve a
method or create executable strategy code. Rich method-card draft creation consumes only passed validation reports,
revalidates the cited chunks through the knowledge store, and persists a canonical evidence-backed `method_card_draft`
payload. Publishing a draft preserves the full payload while exposing summary projections used by existing method
search, citation validation, method contracts, implementation registration, and method packaging.

Approved rich cards can become provenance for maintained strategy and risk templates. The Quant Research Supervisor
still owns strategy and risk candidates, and Data Agent manifests still own symbols, timeframes, date windows, source
filters, and market-data quality. Rich methodology cards describe how a method works; they do not define a backtest data
scope or grant live-trading authority.

## Safety Boundaries

- Research-agent tools do not submit broker orders, clear halt state, reconcile broker state, start live trading, or
  expose raw SQL.
- Backtest execution is local-mutating and policy-gated by `TRADER_MCP_ALLOW_BACKTESTS=true`.
- Data loading is local-mutating and policy-gated by `TRADER_MCP_ALLOW_DATA_LOADING=true`.
- Provider-catalog symbol discovery requires explicit provider discovery policy.
- Generated code is source-backed and validation-gated before use in later workflows.
- Supervisor state stores public artifact refs, decisions, blockers, warnings, and tool evidence, not hidden reasoning
  traces or raw scratchpads.

## Artifact Ownership

Agents are separated by the artifacts they own. Ownership lives in `src/trader_research/domain.py` and
`src/trader_research/agents.py`. The Quant Research Supervisor may coordinate workflows and consume specialist outputs,
but it must preserve specialist ownership and must not forge Data, Quantitative Methods, ML, Hypothesis, Evaluation, or
Adversarial artifacts.
