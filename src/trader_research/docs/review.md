# Independent Review

The Review context owns skeptical evaluation and adversarial evidence. It consumes immutable run, comparison,
robustness, and optimisation references and produces a separate verdict. It does not rewrite specialist artifacts or
selectively omit negative findings.

Evaluation checks evidence completeness, scope comparability, assumptions, data roles, multiplicity, uncertainty,
economic relevance, and unresolved warnings. Adversarial review tests declared variants and stress conditions rather
than changing the hypothesis after seeing protected outcomes.

A coordinator may use the verdict for routing or synthesis, but cannot override it. A promising result may justify the
next prospective stage; it is never itself paper-trading authorization.

## Review workflow

Review starts from exact canonical references rather than a prose summary:

```text
passed run + comparison + optimisation evidence
                  |
                  +-> Evaluation: completeness, comparability, uncertainty
                  +-> Adversarial: declared attacks, variants, stress cases
                                      |
                         separate review artifacts and findings
```

Evaluation asks whether the evidence supports the declared claim. It checks dataset and period roles, assumptions,
multiplicity, uncertainty, economic relevance, and unresolved warnings. Adversarial review asks how the result behaves
when declared assumptions or selected variants are stressed. Neither context edits the run, chooses a parameter, or
silently turns a missing artifact into a neutral finding.

Read the verdict together with its scope, sample size, attack plan, and blockers. “Passed review” means that the stated
review contract completed; it remains distinct from live deployment approval and from broker authority.


## Cross-context evidence join

`EvidenceJoinRef` and `EvidenceJoinResult` define the research-owned seam for a governed experiment. An adapter first
reads each exact canonical record and supplies its pinned hash, immutable revision, bounded lineage projection, status,
limitations, and review fields. `qualify_evidence_join` then checks the proposal, approval, Data scope, strategy
version, run, Evaluation, Robustness, and terminal decision roles against one experiment identity. Missing, stale,
incompatible, partial, and negative producer states remain explicit; a URI or a positive report cannot repair a
mismatched join.

The verifier is pure and does not load a latest record, persist payloads, or grant approval. Its JSON projection can be
retained and reopened by a fresh process, which qualifies lineage reconstruction separately from worker durability,
model behavior, independent producer maturity, and paper-trading admission.

## Decisions when scientific review is unavailable

Governance accepts `BlockedEvidenceBasis` as a distinct human decision basis. It is not a scientific-review report.
The canonical `WorkflowOutcome` must be blocked, have no review verdict refs, and identify the exact source run. The
decision retains its complete structured blockers and hashes, qualified protocol Data and quality references, and every
admitted strategy/risk implementation. Hash drift, unrelated canonical inputs, altered blocker details and agent writes
fail closed. `scientific_review_status` remains `not_assessed`; reject/refine/continue never grant scientific confidence,
deployment readiness or paper admission. Refine and continue retain the blocker basis and require a bounded successor.
