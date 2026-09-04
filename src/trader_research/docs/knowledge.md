# Knowledge Ingestion And Semantic Methodology Extraction

## Purpose

Semantic methodology extraction turns citeable source text into validated, nullable method-card fields. It is the
interpretation layer between document retrieval and canonical method-card creation. Its output must explain both what a
methodology field means and exactly which source text supports that meaning.

This subsystem is deeper than retrieval-augmented summarization. Retrieval finds potentially relevant context. Semantic
extraction discovers a method identity, selects claims for that target, assembles meaning across claims, maps supported
meaning into the closed rich-methodology schema, and validates the attribution before a draft can exist.

This document is the conceptual specification for that process. Exact MCP request and response fields remain in
[MCP contracts](../../trader_mcp/docs/contracts.md); registered tool metadata remains in the
[MCP tool catalogue](../../trader_mcp/docs/tools.md); runtime setup and recovery remain in
[research operations](../../../docs/workflows/research_operations.md). Strategy generation and backtesting are downstream consumers and
are outside this document.

## Delivery Status

The implemented bounded methodology subsystem supports full-document ingestion, evidence units, embeddings,
retrieval, claim spans, target-bound evidence packets, field extraction, validation, stable method-card sets, and
publication remain supported and maintained. They are strongest for bounded methods whose identity and supporting
claims can be tied to local or deliberately assembled source spans.

The subsystem does not yet infer arbitrary source ontologies or faithfully represent every book-scale composite
framework. The Carver *Systematic Trading* diagnostic found substantive evidence for individual framework stages but
could not preserve those stages as one correctly classified composite methodology. Composite claim graphs and inferred
atomic/component boundaries remain in Notion's
[Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84). Until that work is implemented, a blocked candidate
or absent card is the correct result when the implemented evidence model cannot represent the source faithfully.

The active agentic redesign now includes a planning-only research-backed implementation path for this limitation. It
does not reactivate the old deterministic composite-card proposal as-is. It adds structure-preserving textbook
ingestion, iterative multi-source research, a cited research dossier, and a separately validated implementation brief
before code authoring. The target is specified in
[Agentic Research Orchestration Redesign](../../../plans/agentic_orchestration_redesign.md#research-backed-implementation-architecture).
This document remains the maintenance contract for implemented semantic extraction and clearly labels the target below;
no autonomous methodology research behavior is currently available.

## Invariants

- Evidence units are non-exclusive retrieval and context containers. One unit may support several methods.
- Concept overlap is normal. Co-residence with another method never makes evidence invalid by itself.
- Semantic attribution happens at an addressable claim span inside an evidence unit.
- A field may synthesize several claim spans from one or more evidence units.
- Every populated field requires source-backed claim-span references. Unsupported fields remain null or absent.
- Method identities are discovered from source and query evidence. There is no maintained method-target registry.
- Family evidence profiles define reusable evidence roles, not known methods or expected conclusions.
- No tool may invent assumptions, parameters, thresholds, failure modes, formulas, or validation requirements.
- Deterministic orchestration and validation surround any future bounded model adapter.
- Product artifacts persist public evidence and decisions, never hidden reasoning or unrestricted model transcripts.
- Draft creation and publication remain separate, explicit gates.

## Non-Goals

Semantic extraction does not:

- guarantee that every source contains implementation-ready evidence;
- assign one method as the exclusive owner of a chunk;
- convert proximity, embeddings, or role keywords directly into truth;
- infer concrete market-data scope such as symbols, dates, or timeframes;
- generate arbitrary executable code from prose;
- bypass method-card approval, strategy validation, risk validation, or backtest gates;
- estimate missing numeric values from vague prose;
- compensate for an incomplete source by silently adding general knowledge.

## Evidence Hierarchy

The evidence model is deliberately layered:

1. **Knowledge source**: registered document identity, source type, approval status, file hash, and citation metadata.
2. **Evidence unit**: ordered, hashed source text used for retrieval and neighboring-context navigation. The existing API
   field is `chunk_id`; schema-v2 values are `knowledge_evidence_unit_*` identifiers.
3. **Claim span**: exact character range within one evidence unit selected for one evidence role and target method.
4. **Method identity**: source-backed canonical/source name, aliases, abbreviations, and identity evidence refs.
5. **Role evidence**: accepted and rejected claim spans grouped under a family-level role such as definition, formula,
   input data, signal logic, limitations, or validation requirements.
6. **Synthesized field claim**: one nullable rich-schema field derived from one or more accepted role-compatible spans.
7. **Validation report**: checks existence, hashes, offsets, role consistency, target binding, field semantics, source
   suitability, quotation bounds, and requested readiness.
8. **Canonical card revision**: immutable draft or approved method-card revision retaining candidate, packet,
   extraction, validation, source, evidence-unit, and claim-span lineage.

The hierarchy prevents a retrieval score from being mistaken for field evidence. A high-ranking evidence unit is only a
candidate container until target-conditioned spans have been selected and validated.

## Claim-Span Provenance

Each methodology claim span records:

- stable `span_id`;
- parent `source_id`, `chunk_id`, and locator through its evidence reference;
- `start_char` and `end_char` offsets into exact stored evidence-unit text;
- selected `text` and SHA-256 `text_hash`;
- `evidence_role`;
- `target_method`;
- `target_binding` such as direct label, alias label, same sentence, same paragraph, or nearby context;
- matched role terms and local method labels;
- extraction engine and version.

Offsets address the exact support while the evidence-unit reference preserves retrieval context. Validation re-slices
the stored unit at those offsets and recomputes the hash. A stale unit, changed offset, altered span, mismatched role, or
wrong target blocks validation.

One field carries one evidence reference per contributing span. This makes multi-span synthesis explicit rather than
hiding several passages behind one chunk citation.

## Execution Graph

```text
knowledge source
  -> full-document evidence-unit ingestion and indexing
  -> high-recall retrieval or source-scoped scan
  -> open-world method identity discovery
  -> family-role search space and neighboring context
  -> target-conditioned claim-span selection
  -> role evidence packet
  -> field-specific span filtering
  -> bounded multi-span field synthesis
  -> semantic and provenance validation
  -> canonical evidence-backed method-card draft
  -> explicit publication
```

### Ingestion And Retrieval

`knowledge_ingest_documents` extracts the complete registered document, creates ordered evidence units, stages all
embeddings, and publishes a successful Postgres generation atomically with its ingestion report. Provider failure before
publication leaves the previous active evidence generation visible.

`knowledge_retrieve_evidence` provides high-recall lexical/vector candidates. Explicit source-scoped discovery may scan
the active source directly. Neither path assigns semantic ownership.

### Identity Discovery

`knowledge_discover_methodology_candidates` derives identities from local source labels, headings, aliases,
abbreviations, query alignment, and repeated evidence. It writes `methodology_candidate` artifacts. Candidate context may
overlap between identities and may cite the same evidence units.

Discovery answers “what method may this evidence discuss?” It does not populate canonical fields or approve the method.

### Role Assembly And Span Selection

`knowledge_assemble_methodology_evidence` selects the family evidence profile and searches candidate and neighboring
evidence for each role. Within each matching unit, deterministic span selection:

1. identifies local sentence/claim ranges and method labels;
2. finds ranges containing role terms;
3. binds each range to the selected method identity using local labels, aliases, sentence evidence, or bounded context;
4. retains accepted and rejected ranges separately;
5. allows the same unit to contribute different accepted spans to different method packets.

The packet is inspectable evidence inventory. Missing required roles block the requested readiness goal.

### Field Extraction And Synthesis

`knowledge_extract_methodology_fields` consumes accepted packet spans. It first applies field-specific semantic filters.
For example:

- `overbought_threshold` requires an overbought claim;
- `oversold_threshold` requires an oversold claim;
- `exit_rules` require exit, close, liquidation, or mean-reversion semantics;
- `warmup_period` requires warmup or minimum-observation semantics;
- `failure_modes` require risk, failure, whipsaw, noise, or breakdown evidence.

A generic `cross` claim can support signal or entry semantics, but cannot populate overbought, oversold, or exit fields
without those meanings appearing in an accepted span.

When one field requires several passages, deterministic synthesis combines a bounded number of role-compatible spans and
retains every contributing reference. It does not introduce uncited facts. Unsupported schema fields remain null or
absent.

### Validation And Readiness

`knowledge_validate_methodology_candidate` validates the extracted candidate and writes a
`methodology_candidate_validation_report`. Validation checks:

- source, evidence-unit, and locator existence;
- exact span offsets, text, and hashes;
- candidate and packet lineage;
- target method identity binding;
- evidence-role compatibility;
- field-specific semantic entailment;
- references outside accepted packet spans;
- stale source or packet evidence;
- family minimum evidence and high-risk-family breadth;
- source suitability and internal-note restrictions;
- quotation limits;
- descriptive, implementation, signal, strategy-template, or risk-manager readiness.

Another method appearing elsewhere in a cited evidence unit is not a blocker. A blocker occurs when the selected span
does not support the populated field for the selected target.

### Draft And Publication

`knowledge_create_method_card_draft` consumes only a passed, packet-backed validation report with implementation
readiness. It revalidates evidence and derives required card summaries. Missing assumptions, inputs, outputs, or failure
modes block draft creation rather than being supplied by the caller.

`knowledge_publish_method_card` creates an immutable approved revision only after explicit approval. Stable
`method_card_set_id` lineage groups revisions without changing evidence identity.

## Worked Overlap Example

Suppose one evidence unit contains:

```text
Bollinger Bands: compute bands around a moving average from a price series;
buy when price crosses the lower band and sell at the upper band.
Moving Average Oscillator: compute short and long moving averages from a price series;
buy when the short average crosses the long average from below.
```

The unit is valid evidence for both methods.

For a Bollinger Bands candidate, accepted spans include the band calculation and lower/upper-band signal claims. For a
Moving Average Oscillator candidate, accepted spans include the short/long-average calculation and crossover signal.
Both packets cite the same `chunk_id`, but their `span_id`, offsets, text, role, and target differ.

Incorrect attribution occurs if the oscillator candidate populates `overbought_threshold` from the Bollinger passage or
uses the lower-band signal as its crossover rule. Validation blocks the field-to-span relationship. It does not reject
the evidence unit.

## Bounded Semantic Enrichment

Deterministic span selection and schema validation are the current execution engine. A future model adapter may improve
open-ended interpretation only behind the same boundary:

- input is limited to selected citeable evidence units/spans and the closed output schema;
- output must contain structured field values and exact supporting span refs;
- model, prompt, schema, and adapter versions are recorded;
- temperature and request bounds are explicit;
- uncited fields are rejected;
- deterministic validators recheck offsets, hashes, roles, target identity, field semantics, and readiness;
- raw chain-of-thought and unrestricted transcripts are not persisted;
- failure leaves fields null and produces blockers or warnings.

The adapter may propose an interpretation. It cannot approve evidence or create a canonical card by itself.

## Planned Agentic Knowledge-To-Implementation Path

This section defines the intended evolution of the evidence model. It is design only. Current MCP tools, schemas,
method-card gates, and agent ownership do not change until implementation and qualification are documented elsewhere.

### Why bounded model completion is not enough

The existing future-adapter boundary assumes that the relevant evidence has already been selected. That is suitable for
interpreting one bounded method, but it cannot solve a textbook framework whose identity, equations, stages,
initialization, parameters, examples, and caveats are distributed across chapters or complementary sources. Supplying
larger chunks also weakens precision without proving that the necessary remote context was found.

The target keeps exact evidence units and claim spans, then adds model-owned navigation and synthesis around them. A
retrieval unit remains a search container; an understanding unit is the agent's bounded assembly for one question; a
citation unit remains an exact source element or claim span. Only the final category is evidence.

### Target evidence hierarchy

The current hierarchy remains valid and is extended by planning concepts rather than replaced:

1. A **typed source element** preserves paragraph, heading, equation, table, figure/caption, list, code, footnote, or
   cross-reference identity plus structural path and page/layout provenance.
2. A **source map** exposes hierarchy, element inventory, terminology, and derived section/chapter summaries for
   navigation. Every derived field is versioned and explicitly non-citeable.
3. An **evidence obligation** names one question that must be resolved for implementation, such as formula semantics,
   timing, initialization, parameter meaning, failure behavior, or validation.
4. A **cross-source claim record** associates exact claim spans with one obligation and labels them as corroborating,
   complementary, conflicting, edition-dependent, or unresolved.
5. A **research dossier** assembles the method/component graph, obligation coverage, exact citations, conflicts, gaps,
   rejected interpretations, and an implementation-readiness verdict.
6. An **implementation brief** converts a passed dossier into typed interfaces, normalized mathematics, ordered
   pseudocode, state and warmup behavior, parameter semantics, invariants, edge cases, and tests. It records
   source-backed and Trader engineering decisions separately.

The method card can remain a useful published description, but it is not forced to carry the entire multi-source
research session or coding handoff. The redesign must decide whether an accepted brief references one or several method
cards, or whether the dossier supersedes a card for composite implementation work.

Exact source text and embedding input are separate. A contextualized embedding serialization may add title, edition,
heading path, element type, table header, or caption to improve retrieval, but it is derived and versioned. Evidence
hits must resolve to the exact canonical source element. Derived source-map summaries use a separate navigation index
and can only lead to evidence retrieval; they cannot satisfy a citation.

### Target retrieval behavior

A Knowledge Research Agent works inside cumulative source, retrieval, context, token, cost, and time budgets. It:

1. decomposes the implementation question into evidence obligations;
2. inspects approved-source quality, structure, terminology, and likely coverage;
3. uses source maps for global navigation and hybrid search for local discovery;
4. expands exact hits by structural context, including containing sections, definitions, equations, tables, captions,
   and explicit cross-references;
5. selects exact claim spans and generates gap-specific follow-up queries;
6. compares sources without treating source count as a vote;
7. proposes a dossier only after every material obligation is supported, explicitly unresolved, or blocked.

Repeated retrieval requires an unresolved obligation and expected information gain. Equivalent searches without new
evidence, budget exhaustion, material conflict, unsuitable sources, or missing implementation detail stop the attempt.
The model cannot fill the gap from prior knowledge.

### Validation and downstream handoff

Deterministic validators continue to resolve source generations, structural elements, offsets, hashes, roles, target
bindings, suitability, and quotation bounds. A context-isolated semantic review checks entailment, cross-source
coverage, conflict handling, and whether dossier synthesis overstates its citations. Generated source maps and model
reasoning are never accepted as support.

The Quantitative Methods Agent, not the coding agent, turns a validated dossier into the implementation brief. Strategy
Engineering sees that accepted brief and bounded supporting resources, authors code in an isolated workspace, and
submits it to ordinary independent admission. Source fidelity does not imply trading efficacy: backtests, prospective
comparison, robustness, walk-forward analysis, and Evaluation remain separate downstream evidence.

Notion's [Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84)
treats structure-aware ingestion, multi-source dossier research, brief validation, and research-backed implementation
qualification as separate frontiers. Exact MCP requests, persistence, and artifact schemas will be added to current
contract documents only when implementation begins.

## Persistence And Observability

Canonical runtime state is Postgres-backed:

- source and active evidence generations live in the knowledge store;
- methodology candidates, packets, extraction reports, and validation reports live in the research artifact store;
- rich drafts, approved revisions, and method-card sets live in the knowledge store;
- JSONB payloads preserve complete claim-span and synthesis lineage;
- projections expose stable artifact IDs, statuses, source IDs, chunk IDs, and candidate/card lineage for pgAdmin.

Successful Postgres ingestion publishes replacement evidence units, embeddings, and the ingestion report within one
transaction. Failed embedding generation records a blocked attempt where possible without replacing the previous active
evidence generation.

## Testing Standard

Semantic extraction changes require tests at increasing scope:

1. Domain round trips and exact span-hash validation.
2. Span selection with several methods in one evidence unit.
3. Reuse of one evidence unit by multiple candidates through distinct spans.
4. Multi-span and multi-unit field synthesis with complete references.
5. Rejection of wrong-target and wrong-field attribution.
6. Stale offset, text, hash, locator, role, and packet lineage failures.
7. Null preservation when evidence is missing.
8. Real-source fixtures covering PDF extraction artifacts and overlapping concepts.
9. MCP execution from registration through validation and canonical draft gates.
10. Postgres tests proving atomic successful publication and preservation of the prior active generation on failure.

Passing synthetic fixtures demonstrates contract behavior. Production readiness additionally requires representative
real-source evidence, because PDF layout, formulas, headings, and multi-concept prose create failure modes that clean
fixtures do not reproduce.
