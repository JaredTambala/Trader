# Research Agents and MCP Documentation

This context is bounded to research-agent identities, deterministic research tools, MCP tool contracts, LangGraph
orchestration, and agent-owned artifacts.

It covers:

- Quant Research Supervisor, Data, Hypothesis, Evaluation, Adversarial, Math Coder, and ML agent identities
- MCP tool envelopes, side-effect boundaries, and agent-owned artifact references
- LangGraph state, role policy, tool allowlists, and graph orchestration
- data-quality, dataset, hypothesis, experiment, evaluation, robustness, and recommendation artifacts
- implementation plans for agent-facing tools

It does not own core runtime behavior such as broker execution, `TraderService`, event-store schema, or strategy/risk
interfaces. Those belong in [../core/README.md](../core/README.md).

## Start Here

- [agent_operating_model.md](agent_operating_model.md)
- [tool_contracts.md](tool_contracts.md)
- [ai_tool_workflows.md](ai_tool_workflows.md)
- [codex_trading_research_framework_brief.md](codex_trading_research_framework_brief.md)
- [mcp_trading_research_tools.md](mcp_trading_research_tools.md)
