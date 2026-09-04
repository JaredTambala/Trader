# Trader Documentation

Documentation is owned at the same boundary as the code it explains. Package internals live beside and ship with their
package; repository docs cover only relationships and workflows that cross package boundaries.

## Planning and delivery

Notion is the source of truth for development work intake, assignment, priority, dependencies, and progress. Trader
uses continuous flow rather than required sprints:

- [Trader Development Hub](https://app.notion.com/p/3d0e5fade83181129bdcd5d08f1e3e1b)
- [Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84)
- [Trader Work Items](https://app.notion.com/p/31131085ffc54c329f25445843e9ac52)

The repository remains authoritative for architecture, technical design, functional behavior, contracts,
implementation documentation, tests, and executable evidence. Notion records the work and its delivery state without
replacing those technical sources.

## Package documentation

- [`trader`](../src/trader/README.md): core platform and runtime
- [`trader_standard`](../src/trader_standard/README.md): maintained implementations
- [`trader_research`](../src/trader_research/README.md): deterministic research capabilities
- [`trader_mcp`](../src/trader_mcp/README.md): MCP tools and contracts
- [`trader_agents`](../src/trader_agents/README.md): multi-agent coordination
- [`trader_mlflow`](../src/trader_mlflow/README.md): MLflow inference adapter

Each package provides a README, architecture, tutorial, and usage reference. Focused pages are linked from its README.
Python examples use doctest-compatible form; executable shell fences name their verifier; selected notebooks are
output-free and executed in temporary copies during documentation tests.

## Cross-package documentation

- [System architecture](system_architecture.md)
- [Product state](product_state.md)
- [Environment and local services](environment.md)
- [Getting started workflow](workflows/getting_started.md)
- [Research workflows](workflows/research.md)
- [Research and agent operations](workflows/research_operations.md)
- [Python code quality](python_code_quality.md)
- [Functional refactoring control](functional_refactoring_control_document.md)
- [History](history/README.md)

## Ownership rule

A topic has one canonical owner. Root pages link to package details instead of copying them. New behavior is incomplete
until its owning usage guide and executable examples are updated, its tutorial reflects changes to the normal user
journey, and its architecture records changes to boundaries, dependencies, state, persistence, or control flow.
Architectural elements are named by responsibility, never by delivery checkpoint codes.
