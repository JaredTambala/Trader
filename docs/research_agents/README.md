# Research Agents And MCP Documentation

This directory contains the current operating documentation for Trader research agents, MCP tools, and LangGraph
orchestration. It is intentionally split by concern so agents do not have to infer current behavior from old plans.

## Authoritative Current References

- [architecture.md](architecture.md): package boundaries, layer responsibilities, and safety model.
- [agents.md](agents.md): agent identities, owned artifacts, tool allowlists, and handoff rules.
- [mcp_tools.md](mcp_tools.md): current registered MCP tool catalog and planned tool ownership.
- [workflows.md](workflows.md): supported research workflows and near-term portfolio/risk workflow direction.
- [operations.md](operations.md): local MCP server startup, policy gates, persistence expectations, and verification.
- [tool_contracts.md](tool_contracts.md): detailed request/response and artifact contract appendix.

## Historical Context

Older briefs, implementation notes, and superseded user guides live under [history/](history/). They can be useful for
context, but they are not authoritative for current tool availability, agent boundaries, or operation.

## Sources Of Truth

When the docs and implementation disagree, resolve the docs from the implementation:

- Registered MCP tools and capability flags: `src/trader_mcp/constants.py`.
- Agent identities and allowlists: `src/trader_research/agents.py`.
- Artifact types and ownership: `src/trader_research/domain.py`.
- Implementation status and roadmap: `plans/mcp_trading_research_tools_plan.md`.
