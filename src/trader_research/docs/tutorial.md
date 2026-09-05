# Research Capability Tutorial

This tutorial uses dependency-light values to explain how research work becomes evidence. It does not require
Postgres, MCP, an LLM, or a broker.

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

## 4. Choose the public context

- Need usable market data? Start with `trader_research.data`.
- Need source-backed claims? Start with `trader_research.knowledge`.
- Need a strategy implementation? Search and compare the experiment catalogue, then use `trader_research.coding` only
  when authoring or adaptation is required.
- Need a run? Create and validate specifications through `trader_research.experiments` before execution.
- Need a scientific conclusion? Use `trader_research.review`; do not infer it from a run's headline metric.

## 5. Move to integration

Direct service integration requires explicit stores and adapters. Agentic use should instead follow the
[`trader_mcp` tutorial](../../trader_mcp/docs/tutorial.md), because that path adds role ownership, side-effect policy,
and a stable wire envelope. The repository [research workflow](../../../docs/workflows/research.md) walks through the
cross-package sequence.

## 6. Inspect outcomes and stop on invalid evidence

Check `ok`, errors, warnings, artifact references, scope, status, and lineage on every result. A successful service call
does not make its scientific conclusion valid. Missing citations, stale or partial data, failed admission, contaminated
evaluation, and unresolved canonical references must remain blockers.

Use [Artifacts And Persistence](artifacts_and_persistence.md) for the evidence contract, then continue to the focused
Data, Knowledge, Methodology, Experiments, Review, Coding, or ML guide linked from the package README.
