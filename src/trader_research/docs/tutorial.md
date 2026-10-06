# Research Capability Tutorial

This tutorial uses dependency-light values to explain how research work becomes evidence. It does not require
Postgres, MCP, an LLM, or a broker. The same sequence applies when a service is later reached through an MCP tool.

The important distinction is between an operation result and the evidence it names:

```text
request -> normalize and validate -> bounded service operation
                                      |              |
                           ApplicationResult   canonical artifact ref
```

The result tells the caller what happened now. The artifact reference tells a later caller which durable record to
re-read and verify.

## 1. Produce a transport-neutral outcome

A research application service reports normal data separately from durable artifact references and retains warnings.

<!-- verified: doctest -->
```pycon
>>> from trader_research.foundation import success_result
>>> result = success_result(
...     command="tutorial_inspect_scope",
...     data={"symbols": ["AAPL", "MSFT"]},
...     artifacts={"dataset_manifest": "research://postgres/dataset_manifest/example"},
...     warnings=["illustrative record; no data was loaded"],
... )
>>> result.ok
True
>>> result.to_dict()["operation"]
'tutorial_inspect_scope'
>>> result.to_dict()["data"]["symbols"]
['AAPL', 'MSFT']
```

The result is not an MCP response and does not imply that the reference exists. The concrete service and artifact store
are responsible for canonical persistence.

An application result has five useful questions: did the operation succeed (`ok`), which operation ran, what data was
returned, which durable artifacts were created, and which warnings or structured errors need attention. A successful
result can still carry warnings, and a failed result can carry bounded partial evidence for diagnosis.

## 2. Use stable evidence references

<!-- verified: doctest -->
```pycon
>>> from trader_research.foundation import research_artifact_uri, parse_research_artifact_uri
>>> uri = research_artifact_uri("dataset_manifest", "manifest_aapl_msft")
>>> uri
'research://postgres/dataset_manifest/manifest_aapl_msft'
>>> parse_research_artifact_uri(uri)
('dataset_manifest', 'manifest_aapl_msft')
```

Pass this bounded reference between contexts. The receiver loads the exact artifact from its trusted store and verifies
type, status, scope, and lineage before acting.

## 3. Follow the evidence graph

A typical supplied-strategy workflow is:

```text
implementation version + validation
        + dataset manifest + quality evidence
        + strategy/risk/backtest specifications + validation
        -> canonical backtest run
        -> comparison/optimisation evidence
        -> independent evaluation
```

Knowledge-backed authoring adds registered sources, retrieved evidence, exact claim spans, a validated dossier/brief,
and then the normal coding and admission path. Citations can support implementation intent; they cannot establish
trading efficacy.

The graph is deliberately append-only. If an assumption, implementation, or source changes, create a new identity or
successor artifact. Reusing an identity with different content is an integrity failure, which keeps comparisons
reproducible.

After reviewing an agent session, the human can record a `NextResearchDecision` with a typed `SessionReviewLink`
pointing to the retained session graph digest and exact named review revisions. The cited canonical review records
must carry matching session/revision metadata and a pinned hash. A later refinement appends a new decision revision
and names its immediate predecessor; reopening the old artifact preserves the original rationale and successor scope.

## 4. Choose the public context

- Need usable market data? Start with `trader_research.data`.
- Need source-backed claims? Start with `trader_research.knowledge`.
- Need a strategy implementation? Search and compare the experiment catalogue, then use `trader_research.coding` only
  when authoring or adaptation is required.
- Need a run? Create and validate specifications through `trader_research.experiments` before execution.
- Need a scientific conclusion? Use `trader_research.review`; do not infer it from a run's headline metric.

The contexts compose through stable values and references. For example, Data produces a dataset manifest and quality
report; Experiments consumes those references to create a specification; Review consumes the resulting run without
becoming a second execution engine.

## 5. Move to integration

Direct service integration requires explicit stores and adapters. Agentic use should instead follow the
[`trader_mcp` tutorial](../../trader_mcp/docs/tutorial.md), because that path adds role ownership, side-effect policy,
and a stable wire envelope. The repository [research workflow](../../../docs/workflows/research.md) walks through the
cross-package sequence.

## 6. Inspect outcomes and stop on invalid evidence

Check `ok`, errors, warnings, artifact references, scope, status, and lineage on every result. A successful service call
does not make its scientific conclusion valid. Missing citations, stale or partial data, failed admission, contaminated
evaluation, and unresolved canonical references must remain blockers.

For a read-only operation, retry only within its stated deadline. For a mutation whose response is lost, resolve the
stable operation or artifact identity first. If the store cannot establish whether the mutation was accepted, preserve
the reconciliation-required error instead of issuing a blind second mutation.

Use [Artifacts And Persistence](artifacts_and_persistence.md) for the evidence contract, then continue to the focused
Data, Knowledge, Methodology, Experiments, Review, Coding, or ML guide linked from the package README.
