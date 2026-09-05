# Knowledge Research Agent Design

Design status: architecture review in progress; this document does not authorize implementation.

Last reviewed: 2026-08-24.

This document is the canonical build-lifecycle architecture record for the Knowledge Research Agent. Review status and
shared principles are maintained in the parent [Agent Designs](../agent_designs.md) workbook. System-level direction
remains in [Agentic Research Orchestration Redesign](../agentic_orchestration_redesign.md). Work assignment and delivery
progress are maintained in Notion's
[Trader Work Items](https://app.notion.com/p/31131085ffc54c329f25445843e9ac52).

## Established design constraints

The system-level research-backed implementation review already established the following constraints. They are the
starting point for this agent review, not a claim that the complete architecture record has been accepted:

- The agent investigates an implementation question across one or more suitable textbook or other approved knowledge
  sources and produces a canonical cross-source research dossier.
- It decomposes the question into explicit evidence obligations, navigates source structure, performs iterative hybrid
  retrieval and structural expansion, extracts exact claim spans, compares sources, records conflicts and gaps, and
  judges dossier readiness.
- Retrieval units are bounded search material, model-assembled understanding units collect the material required to
  answer one obligation, and exact immutable source elements or claim spans are the only citation units.
- Source maps, embeddings, rankings, and model-generated summaries are navigation aids. They are never source evidence.
- Sources do not vote by count. Suitability, edition, authority, complementarity, and material disagreement remain
  explicit in the dossier.
- Material missing or conflicting implementation detail blocks or branches the work. The model cannot repair it from
  memory or hide it in a confident synthesis.
- Knowledge Research owns the dossier. Quantitative Methods owns the implementation brief, and Strategy Engineering
  owns executable code.
- The agent works through a role-scoped MCP capability catalogue, including source registration and ingestion, and
  never receives raw database, filesystem, provider credential, or unrestricted network access.

## Provisional mission

Given a bounded research question and permitted source scope, build a traceable account of what the sources actually
support: the relevant method or component structure, obligation-by-obligation findings, exact citations, differences
between sources or editions, gaps, rejected interpretations, uncertainty, and an implementation-readiness verdict.

The mission is source investigation and evidence synthesis. It does not select a profitable strategy, design an
experiment, invent method semantics, write an implementation brief or executable code, or decide that sourced ideas
are empirically effective.

## Evidence hierarchy

The working evidence model contains:

1. typed source elements preserving structure and exact provenance;
2. versioned, non-citeable source maps for global navigation;
3. evidence obligations naming the questions material to implementation;
4. cross-source claim records binding exact spans to an obligation and relationship; and
5. a research dossier containing the component graph, obligation coverage, citations, conflicts, gaps, rejected
   interpretations, and readiness verdict.

A method card may remain a reusable published description, but it is not automatically the research-session record or
the downstream coding handoff. Its exact relationship to dossiers and implementation briefs remains a separate design
decision.

## Provisional internal loop

One bounded dossier attempt follows this model-owned loop:

1. define evidence obligations;
2. assess source approval, quality, edition, authority, and likely coverage;
3. inspect source maps and structural navigation metadata;
4. search exact evidence using lexical, vector, metadata, and structural filters;
5. expand promising hits through bounded neighbors, containing sections, definitions, equations, tables, figures, and
   cross-references;
6. bind exact claim spans to obligations and retain concise reasons for rejected candidates;
7. compare sources as corroborating, complementary, conflicting, edition-dependent, or absent; and
8. audit coverage and propose a passed, descriptive-only, or blocked dossier for independent validation.

Repeated retrieval requires an unresolved obligation and an explicit expectation of new information. Equivalent
searches without new evidence, cumulative budget exhaustion, unsuitable sources, and material gaps stop the attempt.

## MCP ingestion capability

Knowledge-source ingestion is part of the agent's capability surface, not an operator-only prerequisite. When a
delegation identifies source material that is permitted by the active policy, the model may choose the registered MCP
operations needed to:

1. inspect the source catalogue and ingestion status;
2. register an approved source reference when it is not already represented;
3. request deterministic full-document ingestion, structural parsing, evidence-unit creation, embedding, indexing, and
   atomic generation publication;
4. observe ingestion status, quality findings, warnings, and failures;
5. retry or revise an idempotent ingestion request when policy and operation contracts permit; and
6. continue evidence investigation only against the exact published source generation.

The current catalogue includes `knowledge_register_source`, `knowledge_ingest_documents`,
`knowledge_get_ingestion_status`, and `knowledge_list_sources`. These names describe today's baseline, not a permanent
hard-coded workflow. Future parser, provider, data-type, source-map, or re-indexing capabilities become available
through the same role-scoped catalogue only after their schemas, side effects, permissions, outputs, recovery behavior,
and evaluation coverage are accepted.

The agent chooses whether and when these MCP capabilities are useful. Deterministic knowledge services perform the
actual file access, validation, parsing, normalization, chunking, embedding, persistence, and generation publication.
The agent cannot bypass MCP, supply arbitrary filesystem paths, run its own parser, write embeddings directly, or treat
successful ingestion as proof that a source is suitable for a claim.

## Source-set and acquisition authority

The accepted boundary separates permission to possess and process a source from the agent's judgment that it is
suitable evidence:

- The agent may autonomously select, prioritise, register, and ingest material from the session-approved corpus or an
  operator-approved library/import location, subject to the active MCP ingestion envelope and budgets.
- It may discover potentially useful sources outside that scope and return candidate metadata, but external
  acquisition, licensing, and admission to the approved corpus require operator authority through the coordinator.
- Successful registration or ingestion does not make a source authoritative. The agent must assess suitability,
  edition, relevance, likely coverage, and relationship to each evidence obligation.
- Deterministic checks establish source identity, integrity, approval metadata, parsing and embedding status, and
  provenance. Independent dossier validation checks whether exact citations support the agent's claims.
- If the permitted corpus cannot resolve material detail, the dossier remains descriptive-only or blocked. The agent
  cannot complete it from model memory.

All source registration and ingestion still occurs through bounded MCP capabilities. Corpus approval never grants raw
filesystem, network, credential, or licensing authority to the model.

## Remaining architecture record

The following sections remain pending structured review:

- exclusive decisions and final hard boundaries;
- complete entry and readiness contracts;
- context and trust boundary, including prompt injection in source text;
- model-program and structured-output requirements;
- final role-scoped MCP/resource surface;
- durable dossier-attempt state and recovery;
- evidence-return contract;
- termination and escalation;
- evaluation scenarios and promotion evidence; and
- concurrency, source fan-out, synthesis, and handoff rules.
