# Deprecated: Linear MCP Trading Research Tools Plan

Status: deprecated on 2026-07-25.

Do not add tasks, completion evidence, architecture specifications or delivery slices to this file.

The former tracker mixed current product state, target architecture, remaining work, historical delivery narrative and
verification transcripts. Its linear slice structure no longer represents how Trader's independent research
capabilities and agents can evolve.

Use these canonical sources instead:

- [Product State](../docs/product_state.md): what works now, qualification strength,
  availability, current agent behavior and product limits.
- [Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84): current portfolio status
  and capability progress.
- [Trader Work Items](https://app.notion.com/p/31131085ffc54c329f25445843e9ac52): atomic assignments,
  priorities, dependencies, and delivery state.
- [Research Capability Roadmap](research_capability_roadmap.md): retained architecture, dependencies, acceptance
  conditions, and the migration snapshot.
- [Research Agent Architecture](../src/trader_agents/docs/architecture.md): package boundaries, authority and target
  orchestration principles.
- [Agent Ownership](../src/trader_agents/docs/roles_and_authority.md): agent missions, artifact ownership, allowlists and handoffs.
- [MCP Tool Catalogue](../src/trader_mcp/docs/tools.md): tools that are actually registered.
- [Research Workflows](../docs/workflows/research.md): currently supported deterministic tool chains.
- [Research Operations](../docs/workflows/research_operations.md): gates, Postgres operation and controlled qualification.

## Historical Snapshot

The final complete version of this tracker is retained by Git at commit `577c774`:

```bash
git show 577c774:plans/mcp_trading_research_tools_plan.md
```

Controlled 57I-S acceptance evidence remains canonical in `verification_control` Postgres records and at Git tag
`verification-57i-freeze-v6`. The new roadmap contains a compact immutable mapping from former task IDs to current
capability workstreams.

This file remains at its old path only to give existing links an explicit fail-safe migration target. Its presence is
not compatibility support for the former delivery model.
