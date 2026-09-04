# Agent Instructions

This file is the repo-level operating guide for AI coding agents working in Trader. It is an instruction router and
checklist, not a replacement for the project documentation.

## System Purpose

Trader is a Postgres-first trading platform for market-data ingestion, strategy/risk execution, backtesting, research
experiments, AI/tool-facing signal discovery, and Alpaca paper-trading operations. Research-agent work is deliberately
outside the live trading hot path: agents produce deterministic, inspectable artifacts and must not place live orders.

Use the existing documentation as the source of truth:

- Product and setup overview: [README.md](README.md)
- Documentation index: [docs/README.md](docs/README.md)
- Cross-package architecture: [docs/system_architecture.md](docs/system_architecture.md)
- Repository and test ownership: [docs/test_architecture.md](docs/test_architecture.md)
- Current product state: [docs/product_state.md](docs/product_state.md)
- Package documentation: the owning package's `README.md` and `docs/` directory under `src/`
- Target model-backed agent designs: [plans/agent_designs.md](plans/agent_designs.md)
- Research-agent architecture: [src/trader_agents/docs/architecture.md](src/trader_agents/docs/architecture.md)
- Agent identities and authority: [src/trader_agents/docs/roles_and_authority.md](src/trader_agents/docs/roles_and_authority.md)
- Current MCP tool catalog: [src/trader_mcp/docs/tools.md](src/trader_mcp/docs/tools.md)
- MCP/tool envelope contracts: [src/trader_mcp/docs/contracts.md](src/trader_mcp/docs/contracts.md)
- Research capability architecture and migration snapshot:
  [plans/research_capability_roadmap.md](plans/research_capability_roadmap.md)
- Python contributor standard: [docs/python_code_quality.md](docs/python_code_quality.md)

Use Notion as the source of truth for development planning and progress:

- Portfolio initiatives and capability status:
  [Trader Development Roadmap](https://app.notion.com/p/d1453b7a4da6468babead2a5cda7ef84)
- Atomic tasks, bugs, issues, spikes, chores, assignment, priority, and dependency state:
  [Trader Work Items](https://app.notion.com/p/31131085ffc54c329f25445843e9ac52)
- Planning entry point and operating policy:
  [Trader Development Hub](https://app.notion.com/p/3d0e5fade83181129bdcd5d08f1e3e1b)

## Package Architecture

- `trader`: core platform only. Market data, event store, brokers, runtime orchestration, strategy/risk interfaces,
  backtesting, metrics, and operator primitives live here. It must not depend on research, MCP, or agent packages.
- `trader_standard`: maintained first-party implementations of platform interfaces, including indicators, signals,
  strategies, and risk managers. It should not own experiment orchestration, MCP schemas, or agent tooling.
- `trader_research`: deterministic research services, research domain models, tool envelopes, data-quality wrappers,
  strategy validation, recommendations, knowledge/method artifacts, diagnostics, and reports.
- `trader_mcp`: MCP server and adapters over `trader_research` services. Keep transport concerns here.
- `trader_agents`: LangGraph identities, state schemas, policy routers, tool allowlists, and graph wiring over MCP
  tools. Agent code should call MCP tools, not platform internals, when a tool exists.
- `trader_mlflow`: optional MLflow pyfunc loading and prediction normalization over core prediction contracts. It does
  not own training governance, strategy mapping, or agent decisions.

## Agent Definitions

Follow [roles_and_authority.md](src/trader_agents/docs/roles_and_authority.md) for the authoritative boundaries.

- Data Agent: owns symbol discovery, dataset manifests, data inventory, quality reports, and explicit bounded loading
  evidence.
- Quantitative Methods Agent: owns knowledge sources, method cards, method contracts, implementation validation,
  signal diagnostics, multiple-testing reports, and optional kernel/parity artifacts.
- Quant Research Supervisor Agent: coordinates research workflow, consumes specialist artifacts, creates experiment
  plans and recommendations, and preserves specialist ownership.
- ML Agent: owns feature, model, prediction, and drift artifacts.
- Hypothesis Agent: owns hypothesis cards from available ingredients.
- Evaluation Agent: owns skeptical critique and evaluation reports.
- Adversarial Agent: owns robustness and stress-test reports.

No research agent may control live trading, broker mutation, halt clearing, order reconciliation, direct SQL writes, or
raw hidden scratchpad persistence.

## Planning And Delivery Authority

- Notion is authoritative for work intake, assignment, priority, status, dependencies, and delivery progress.
- The Git repository is authoritative for architecture, technical design, functional behavior, contracts,
  implementation documentation, tests, and executable evidence.
- Trader uses continuous flow. Do not require a sprint or iteration assignment before work can proceed.
- Every independently assignable task, bug, issue, spike, or chore has its own Trader Work Item. Link it to the Trader
  project and the narrowest applicable roadmap initiative.
- Before implementation, find the applicable work item. If the requested repository change is not represented, create
  a work item before editing. Move it to `In progress` only when work begins, to `Blocked` only with a named blocker or
  dependency, and to `Done` only after implementation, documentation, and required verification are complete.
- Architecture and design decisions remain in their canonical repository documents. Reflect their implementation work
  and progress in Notion without moving the technical authority into a ticket description.
- If Notion is unavailable, do not substitute a repository planning file as the live tracker. Report the access
  problem and keep the work item status unchanged until it can be reconciled.

## Mandatory SDLC Loop

For every task, do this in order:

1. Read the relevant Trader Work Item and linked roadmap initiative in Notion first. Create an atomic work item when the
   requested change is not represented, then set it to `In progress` when implementation begins.
2. Identify its acceptance criteria, dependencies, current status, and repository documentation authority. For
   research-agent/MCP work, confirm the implemented baseline in [docs/product_state.md](docs/product_state.md) and use
   [plans/research_capability_roadmap.md](plans/research_capability_roadmap.md) only as an architecture and migration
   reference.
3. Inspect the change surface with repo searches and nearby code reads. Prefer `rg` and targeted file reads.
4. Plan narrowly around the package boundary and existing patterns.
5. Implement the smallest coherent change. Do not create compatibility layers unless the Notion work item, canonical
   technical design, or user explicitly requires them.
6. Test the direct behavior first, then broaden tests when touching shared contracts, MCP registration, agent identity,
   persistence, or package boundaries.
7. Update active repository documentation when behavior, APIs, artifacts, architecture, or design changes. Update the
   Notion work item and roadmap initiative when assignment, dependencies, progress, or delivery status changes.
8. Treat package documentation as part of feature completion: update usage and executable examples when a public
   surface changes, extend the tutorial when the normal user journey changes, and update architecture when boundaries,
   dependencies, state, persistence, or control flow change. If none applies, state why in the final response.
9. Run the owning package's documentation and example checks before completion.
10. Reconcile the Notion work item with the delivered evidence and mark it `Done` only when its acceptance criteria are
    satisfied.
11. Review `git status --short` before staging. Stage only intended files.
12. Commit only when the user asks for a commit, or when an agreed workflow explicitly requires one.

## Python Code Quality

Apply [docs/python_code_quality.md](docs/python_code_quality.md) to all Python changes.

- Normalize request payloads, config, rows, and external responses at boundaries before passing data deeper.
- Use typed value objects or stable plain-data shapes instead of passing partially-normalized dictionaries through core
  logic.
- Keep orchestration functions readable: validate early, name intermediate domain concepts, and move focused behavior
  into small helpers.
- Keep deterministic core logic separate from adapters, persistence, clocks, network calls, brokers, and LLM clients.
- Make failures actionable with clear blockers, warnings, or explicit exceptions carrying useful context.
- Use Google-style docstrings for new or changed public modules, classes, and functions.
- Add comments only for non-obvious invariants, external contracts, or deliberate tradeoffs.
- Scale tests to risk: focused tests for narrow changes; broader suites for shared contracts, package boundaries, MCP,
  persistence, or runtime behavior.

## Documentation And Planning Rules

- Feature work is not complete until active repository docs reflect the implementation and the Notion work item
  reflects its verified delivery state.
- Before implementing a feature, read the owning package's `README.md` and relevant documents in its `docs/`
  directory.
- Public features must update their usage reference and executable examples. Extend a package tutorial whenever the
  normal learning path or user workflow changes.
- Boundary, dependency, state, persistence, and control-flow changes must update the owning package's architecture
  documentation.
- Python and shell snippets that claim to run must name and pass their documentation test. Unverified executable
  fences are not allowed.
- Package internals have one canonical owner under that package. Root documentation describes only cross-package
  architecture, product state, environment, end-to-end workflows, contributor standards, and history.
- Never name an architectural element after an implementation checkpoint code.
- Do not use [plans/research_capability_roadmap.md](plans/research_capability_roadmap.md) for live work status or
  assignments. It retains technical dependencies, acceptance concepts, and the 2026-09-03 migration snapshot; Notion
  owns subsequent delivery state.
- Update the general principles in [plans/agent_designs.md](plans/agent_designs.md), plus the owning record under
  `plans/agent_designs/`, when a target model-backed agent's mission, authority, entry or context boundary, model/tool
  loop, state, evidence return, termination, evaluation, concurrency, or design-review decision changes. Track the
  work and its delivery status in Notion.
- Update [src/trader_mcp/docs/contracts.md](src/trader_mcp/docs/contracts.md) when tool inputs, outputs,
  envelopes, side effects, or artifact contracts change.
- Update [src/trader_agents/docs/roles_and_authority.md](src/trader_agents/docs/roles_and_authority.md) when agent ownership, boundaries, or
  allowlists change.
- Update [src/trader_mcp/docs/tools.md](src/trader_mcp/docs/tools.md) when MCP registration, tool ownership,
  side effects, or capability flags change.
- Update the relevant `src/trader/docs/` document when runtime, storage, strategy/risk, market-data, backtest, or
  operator behavior changes.
- Do not create new documents when an existing canonical document can be updated.

## Verification Policy

Use the narrowest checks that prove the change, then broaden when shared surfaces are touched.

- Place new tests under `tests/<owning-package>/<bounded-context>/`. Use `tests/cross_package/` only when the package
  seam, complete workflow, documentation distribution, or release qualification is itself the subject. External
  execution requirements belong in markers and explicit module names, not directory axes.
- New and migrated test modules must follow [docs/test_architecture.md](docs/test_architecture.md): document subject,
  level, collaborator reality, guarantees, and non-goals; give every test a contract-focused docstring; and record a
  cohesion rationale when a module exceeds the review threshold.
- Documentation changes: run `uv run pytest tests/cross_package/documentation/test_package_documentation.py tests/cross_package/documentation/test_agent_orchestration_docs.py tests/cross_package/documentation/test_controlled_qualification_docs.py tests/cross_package/documentation/test_research_capability_docs.py tests/cross_package/documentation/test_research_roadmap_docs.py -q`.
- Notebook changes: also run `uv run pytest tests/cross_package/documentation/test_tutorial_notebooks.py -q`.
- Packaging changes: build to a temporary directory and run `tests/cross_package/documentation/support/verify_wheel_documentation.py` against the
  wheel.
- Python changes: run targeted tests for the changed behavior and `uv run ruff check` on touched Python paths.
- Shared contracts, MCP registration, agent identity, persistence, or package-boundary changes: run the relevant targeted
  suites and consider `uv run pytest -m 'not postgres' -q`.
- Postgres-backed changes: run the relevant `pytest.mark.postgres` tests when local Postgres is available.
- Before final response, report the exact checks run and any checks intentionally skipped.

## Do Not

- Do not implement before checking or creating the atomic Notion work item and reading nearby repository docs.
- Do not commit feature work without required repository documentation and Notion status updates, unless the final
  response explicitly explains why one of them was not applicable or could not be reached.
- Do not create legacy compatibility imports, shims, or aliases unless explicitly planned.
- Do not bypass MCP/tool boundaries from agent code when a tool exists.
- Do not give agents direct SQL write access, broker mutation, live trading controls, or raw scratchpad persistence.
- Do not persist every LLM message, hidden reasoning trace, or tool-call payload as product state.
- Do not stage or commit unrelated untracked files.
- Do not rewrite or revert user changes unless explicitly requested.

## Before Final Response

Confirm and report:

- The Notion work item and roadmap initiative were checked and updated, or why that was not applicable or possible.
- Active docs were updated, or why no docs change was needed.
- Tests/checks were run with exact commands and results.
- `git status --short` was reviewed.
- Remaining untracked or modified files are identified.
