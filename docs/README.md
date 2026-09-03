# Trader Documentation

Documentation is owned at the same boundary as the code it explains. Package internals live beside and ship with their
package; repository docs cover only relationships and workflows that cross package boundaries.

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
