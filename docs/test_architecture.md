# Repository And Test Architecture

This document defines the permanent ownership model for Trader's source and test directories. Directory structure
communicates ownership; test level, execution cost, and external-service requirements are expressed separately through
module narratives, fixtures, and pytest markers.

The repository completed its transition from 147 flat test modules containing 908 test functions. The flat layout and
its migration registers no longer exist. The final architecture is enforced directly from the checked-out tree.

## Source Hierarchy

Every source path follows the same decision sequence:

1. **Owning package:** the package accountable for the behavior or contract.
2. **Bounded context or control responsibility:** the domain capability or lifecycle responsibility within that
   package.
3. **Cohesive component:** a module or subpackage whose contents change for the same reason.

This is a placement rule, not a requirement that every package have the same depth. A small package should remain flat
while its modules share one responsibility. Empty taxonomic directories are not architecture.

### Package organizing principles

| Package | Internal organizing principle | Accepted dependency direction |
| --- | --- | --- |
| `trader` | Core platform contexts: backtesting, brokers, configuration, cycles, event storage, identifiers, market data, operators, portfolios, predictions, and runtime | Must not depend on maintained implementations, research, MCP, agents, or MLflow |
| `trader_standard` | Maintained prediction, risk, and strategy implementations | Depends on `trader` contracts |
| `trader_research` | Research contexts: foundation, governance, data, knowledge, methodology, coding, experiments, and research ML | Depends on `trader` and may compose `trader_standard` |
| `trader_mlflow` | Optional MLflow inference adapter | Depends on `trader` prediction contracts |
| `trader_mcp` | Protocol, catalogue/policy, capability tools, runtime composition, and observability | Adapts `trader_research`; its named composition root may construct documented providers |
| `trader_agents` | Contracts/state, model runtime, MCP policy and use, coordination, specialists, checkpointing, observability, and application runtime | Uses platform capabilities through `trader_mcp` |

Names describe enduring responsibilities. Work-item IDs, delivery checkpoints, dates, `new`, `legacy`, `misc`,
`common`, and undifferentiated `utils` are not bounded contexts.

## Dependency Direction

```text
trader_standard ------> trader <------ trader_mlflow
       ^                  ^
       |                  |
       +------ trader_research
                      ^
                      |
                  trader_mcp
                      ^
                      |
                 trader_agents
```

An outer application composition root may import concrete implementations to construct a process. That exception does
not authorize protocol adapters, domain services, or agent logic to import across arbitrary package boundaries. The
composition module must be identifiable, documented, and covered by a dependency test.

Three explicit boundaries deserve particular attention:

- Research knowledge persistence lives under `trader_research.infrastructure.postgres.knowledge`; core does not own
  or export its schema, records, or store.
- The provider-neutral inference adapter profile lives in `trader.predictions`; research and `trader_mlflow` both
  depend inward on it.
- Concrete MCP process construction lives in `trader_mcp.runtime.composition`. Protocol registration and capability
  adapters consume typed runtime dependencies and cannot import concrete providers directly.

An MCP-to-Agents dependency is prohibited. Agents call MCP; MCP never imports agent code.

## Test Ownership

A test belongs to the package whose behavior it asserts. Importing a lower-level dependency to construct inputs or
exercise a public contract does not transfer ownership to that dependency.

Use this placement procedure:

1. State the behavior or contract that would be broken if the test failed.
2. Name the package that owns that behavior.
3. Select the package's bounded context or control responsibility.
4. Name the cohesive subject in the module filename.
5. Record the test level and collaborator reality in the module narrative.
6. Apply markers for Postgres, local-model, container, compiler, notebook, or subprocess requirements.

Use `tests/cross_package` only when the seam itself is the subject and no single package owns the assertion. Calling
two packages in one test is not enough. Accepted cross-package contexts are:

- `boundaries`: dependency direction and repository architecture;
- `documentation`: executable learning material, links, and distribution contents;
- `workflows`: behavior whose subject is a complete multi-package flow; and
- `qualification`: explicitly guarded release and controlled-environment gates.

## Test Tree

```text
tests/
  trader/
    <core-context>/
  trader_standard/
    <implementation-family>/
  trader_research/
    <research-context>/
  trader_mlflow/
    inference/
  trader_mcp/
    <protocol-or-capability-context>/
  trader_agents/
    <control-responsibility>/
  cross_package/
    boundaries/
    documentation/
    workflows/
    qualification/
  support/
```

The approved top-level context vocabulary is:

| Owner | Contexts |
| --- | --- |
| `trader` | `backtest`, `broker`, `config`, `cycle`, `event_store`, `identifiers`, `market_data`, `operator`, `portfolio`, `predictions`, `runtime` |
| `trader_standard` | `predictions`, `risk`, `strategies` |
| `trader_research` | `coding`, `data`, `experiments`, `foundation`, `governance`, `knowledge`, `methodology`, `ml` |
| `trader_mlflow` | `inference` |
| `trader_mcp` | `catalogue_policy`, `observability`, `protocol`, `runtime`, and capability families below `tools/` |
| `trader_agents` | `application_runtime`, `checkpointing`, `contracts_state`, `coordination`, `mcp`, `model_runtime`, `observability`, `specialists` |
| `cross_package` | `boundaries`, `documentation`, `workflows`, `qualification` |

Package-specific helpers and fixture data live below their owning package and context. A support directory may sit
beside the tests that consume it. It is not itself a test-level or ownership axis.

### Root exceptions

The test root contains exactly four shared assets:

- `tests/__init__.py` enables explicit imports across the test tree;
- `tests/conftest.py` provides guarded fixtures used by multiple package owners;
- `tests/support/__init__.py` exposes the deliberately shared support namespace; and
- `tests/support/duckdb_store.py` provides the complete in-process EventStore double used by core, maintained
  implementations, research, MCP, agents, and cross-package workflows.

No root-level `test_*.py` module or `tests/fixtures` directory is permitted. A new root support asset requires evidence
of multiple independent package owners and a corresponding architecture change; convenience alone is insufficient.

## Narrative Contract

Every test module explains five facts in its module docstring:

- `Subject`: the production behavior and owning boundary;
- `Level`: unit, contract, adapter integration, workflow, or qualification;
- `Collaborators`: which collaborators are real, fake, stubbed, or external;
- `Guarantees`: the observable behavior protected by the module; and
- `Non-goals`: behavior the module deliberately does not prove.

A compact module narrative can use this form:

```text
"""Contract tests for coordinator routing to the Data specialist.

Subject: Coordinator ownership of one specialist handoff.
Level: In-process contract.
Collaborators: Real graph nodes with a fake MCP transport and fixed model output.
Guarantees: Correlated calls, returned evidence, and terminal status are observable.
Non-goals: Postgres recovery, live providers, parallel specialists, and model quality.
"""
```

Each test docstring states the causal scenario, observable result, and why the result matters to the contract. It must
add information beyond the function name. Test names use `test_<subject>_<condition>_<outcome>` when that reads
naturally.

Fixtures and helpers use domain names. Names such as `data`, `result`, and `helper` are acceptable only when their
scope makes their meaning unambiguous.

### Cohesion review

File size is a review signal, not a splitting algorithm. A module containing more than 20 tests or 800 lines requires
an explicit `Cohesion rationale:` in its module docstring. The rationale explains why the tests protect one contract
and benefit from remaining together. Mixed subjects split along production boundaries even when the file is smaller.

One deliberate large qualification split keeps the collected Postgres optimisation evidence-graph contract in
`tests/cross_package/qualification/test_postgres_optimization_evidence_graph.py` and its reusable graph builder in the
non-collected sibling `optimization_evidence_graph_support.py`. The helper is not a second owner; it supports the same
qualification context and is reused by determinism checks.

## Change Protocol

When adding or reorganizing tests:

1. Identify the owner and context from the asserted production contract.
2. Place the module directly under that owner/context, using a deeper responsibility subdirectory only when needed.
3. Keep assertion changes separate from physical relocation wherever practical.
4. Add the module narrative and contract-focused test docstrings before review.
5. Localize helpers and fixture data unless at least two package owners genuinely share them.
6. Update the owning package documentation when the work exposes or changes a boundary.
7. Update every active verifier, shell command, subprocess module path, and CI consumer in the same change.
8. Run the focused behavior, repository architecture, documentation, lint, and appropriately broader checks.

Execution requirements never determine directory placement. A Postgres test remains with the package contract it
protects; `pytest.mark.postgres` and its collaborator narrative state the environmental requirement.

## Permanent Enforcement

`tests/cross_package/boundaries/test_repository_test_architecture.py` enforces the checked-out architecture without a
legacy allowance or allocation manifest. It rejects:

- files or directories outside the closed root vocabulary;
- root-level tests and unapproved shared support;
- test modules without exactly one approved owner/context prefix;
- delivery-code directory names;
- missing module narrative fields or weak individual-test docstrings;
- oversized modules without a cohesion rationale;
- concrete-provider imports outside the MCP composition root; and
- Agent or MCP source modules outside their responsibility taxonomies.

The broader boundary suite verifies package dependency direction, core/maintained extension seams, SQL isolation, and
retired architecture surfaces. Documentation contracts verify package learning material, links, examples, notebooks,
and distribution contents.

Generic CI runs `pytest -m 'not postgres'`. Postgres cases require the guarded `PG_TEST_*` identity and are executed
explicitly against package/workflow paths or through their controlled qualification profile; a convenience CI database
with legacy `PG_*` variables is not a valid substitute.

This architecture governs ownership and verification structure. It does not change product behavior, public APIs, or
the meaning of test assertions.
