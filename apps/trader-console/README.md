# Trader Console

A human-facing application for configured environment/account context, read-only evidence exploration, and bounded local
backtest authoring/execution. It is deliberately separate from the Python API package: the two share the checked
OpenAPI artifact and run as separate processes.

The root screen is a dark, responsive connection view. `/data` discovers the published datasets, selects a
symbol/timeframe/source slice, applies a UTC range, renders producer OHLC values as a candlestick chart with a linked
volume pane, shows a bounded source-row sample, and resolves exact manifest/quality evidence with coverage, findings,
warnings and provenance. It also saves or reopens an exact scope with its manifest and quality
artifact references. Reopening preserves the recorded UTC window and provider policy and displays active, stale, or
unavailable evidence without silently widening or replacing the scope. From a selected saved scope, “Author backtest with this scope”
opens `/backtests/new?saved_scope_id=…`; authoring carries the exact symbols/universe, asset class, timeframe, UTC window,
provider policy, and manifest/quality references into a typed preflight handoff. Stale, unavailable, missing, or changed
evidence remains an actionable blocker. `/backtests` selects an experiment and run, then renders run
identity, assumptions, SQL-derived strategy metrics and curves, drawdown, trades, positions, warnings, evidence
coverage, and the published risk-manager composition plus bounded per-manager decision trace. `/backtests/new`
provides the local catalogue-driven authoring flow: preflight a UTC replay, save an immutable definition, submit one
durable execution command, and observe bounded progress until the terminal state. `/comparisons` builds and loads named
views over runs in one experiment, keeps incompatible selections visible with server-provided reasons, and renders
only currently eligible evidence in synchronized UTC charts and metric tables. ECharts is used only as a generic
renderer; the review pages read persisted evidence and derive presentation from API responses.

The producer-backed execution qualification runs that authoring command through a separate local worker and reopens the
result on `/backtests` with the exact data-scope identity, persisted assumptions, fills, warnings, review artifacts,
and comparison state. The review panel records a human next decision through the same-origin API; missing or
incompatible evidence remains visible and blocks the command. Failed and ambiguous worker campaigns, plus replay-bar
identity, remain separate qualification boundaries.

`/paper` renders the current paper runtime evidence and a human operator command panel. Commands require an approved
admission ID and are queued through the API with an audit receipt; the workspace shows whether the running process has
accepted, completed, failed, or marked reconciliation ambiguous. The browser never supplies a database, broker, or
scope override.

The connection, market-data, backtest-review, backtest-authoring and comparison pages share one responsive `ConsoleShell` sidebar. It
provides the same keyboard-accessible routes and marks the active workflow with `aria-current="page"`; on narrow
screens the links become a horizontally scrollable navigation row without adding horizontal page overflow.

## Start the screen

First start the [dedicated demo database and API](../../examples/console_demo/README.md). Use Node **24.20.0** and
npm **11.19.0** from a user-local installation; do not replace system Node. From the app directory, `.nvmrc` supplies
the version to an existing nvm installation. Install the Node version with `nvm install` if necessary, then activate
it with `nvm use`. If necessary, run `npm install --global npm@11.19.0` **after** activating nvm; this updates only
that user-local Node installation. Verify `node --version` and `npm --version` before installing dependencies.

To explore the existing local Trader database instead, follow the [real-data API configuration](../../docs/environment.md#existing-local-trader-data)
before starting this frontend. The frontend remains unchanged; it consumes the API's published `console_read` views.

<!-- verified: integration:console tests/cross_package/workflows/test_console_browser.py -->
```bash
cd apps/trader-console
npm ci
npm run dev
```

Open `http://127.0.0.1:3000`. The frontend and API stay in separate foreground processes.
`npm run build` and `npm start` provide the production-build local check. Both development and start bind to loopback.
The committed app-local lockfile pins the tested dependencies. ESLint 9 is retained for compatibility with Next's
React lint plugin; moving to ESLint 10 currently requires compatible plugin updates.

## Configuration and architecture

The frontend is an independent npm package with its own lockfile/build/process; the API is a Python package under
`src/trader_console_api`, included in the Trader Python distribution. They share this repository and an OpenAPI
artifact, not application code or a runtime process. The Python package build does not include this frontend.

`TRADER_CONSOLE_API_ORIGIN` is a **server-only** HTTP(S) origin, default `http://127.0.0.1:8001` (see `.env.example`).
Next rewrites exactly `/api/context`, `/api/market-data/datasets`, `/api/market-data/bars`, `/api/market-data/evidence`, `/api/data-scopes`, `/api/agent-sessions/:session_id`, `/api/agent-sessions/:session_id/commands`, and `/api/paper/commands` plus its detail routes, and
its saved-scope/revalidation routes, the experiment/run review, next-decision,
and comparison-view resources, `/health/live`, and `/health/ready` to that origin. Restart development, or rebuild
the production app, after changing it. No browser-supplied upstream, wildcard proxy, extra gateway or CORS policy exists.
This unauthenticated setup is for local development, not remote exposure.

The root route renders `features/connection`; `/data` renders `features/market-data`; `/backtests` renders
`features/backtest-review`; `/comparisons` renders `features/comparisons`. CSS Modules and global CSS
variables provide the visual shell. Both features use `openapi-fetch` with generated types from the API's checked
schema; no response models are copied into the frontend. Console requests use independent ten-second deadlines,
abort stale work on unmount, and expose API errors without inventing values. Bars are loaded in bounded 50,000-row
windows: the chart's inside/slider data zoom works across the loaded window, while explicit previous/next controls
make the remaining dataset visible without pretending a large result is complete. Empty ranges, unavailable datasets,
and unavailable bars are explicit states. There is no polling or shared state framework.

`/agents/{session_id}` renders the API's redacted public session projection: identity and runtime pins, agenda,
budgets, specialist and blocker progress, recovery checkpoint, and terminal evidence lineage. Each specialist branch
also exposes a typed outcome and handoff artifact revisions, hashes, and availability states, so refresh and recovery
retain exact evidence identity. Its controls use the
API-provided `available_commands`; a missing inspection or terminal state disables invalid lifecycle actions. The
API independently enforces the same policy and the agent runtime rechecks state when consuming an intent.

`synthetic_demo` is explicitly labelled **Synthetic demo**; backtest and demo broker bindings show **Not applicable**.
A paper account with no display label shows **Not specified**, never a fabricated alias or verification claim.
Database errors retain configured context. If refreshing context fails, retained context is marked as last known.
A fresh page without API access shows unavailable context and unknown environment. Known schema issues have readable
guidance; unknown codes remain escaped text. A typed HTTP 503 is handled separately from a network/proxy failure.

## Contracts and checks

The API owns `contracts/trader-console/openapi.json`. `npm run generate` derives `src/generated/api.d.ts`; never
hand-edit it. `npm run check:contracts` generates in memory and compares without rewriting files. No duplicate API
schema or handwritten response catalogue exists. Changing API contracts requires exporting OpenAPI first.

The chart adapter maps each API bar to `[timestamp, open, close, low, high]` for the ECharts candlestick series and
`[timestamp, volume]` for its linked volume pane. Crosshair, UTC axis labels, horizontal inside zoom and the visible
slider are intentional exploration affordances. Zoom filters the visible window so the price and volume y-axes rescale
to the selected bars. A backtest review can pass the API's typed `indicator_series` and `signal_markers` into the same
adapter: producer-declared price series overlay OHLC, declared secondary series get separate scale groups, and markers
use recorded event timestamps. Unknown or missing display metadata is left out of plotted panes rather than inferred.

The backtest review's **Claims and limitations** panel presents producer-owned Evaluation, multiple-testing, and
Adversarial/robustness evidence with explicit available, missing, incompatible, and blocked states. It shows exact
artifact identity, claim scope, protected-data roles, limitations and blockers. Optimisation-derived reports remain
labelled as exploratory context and cannot be displayed as independent confirmation.

The backtest review keeps run identity, scope and replay dates visible above every metric and curve. Missing scope
identity remains visible in the run context, while metrics are shown when the persisted runtime evidence supports a
reconstructed result. Completed, partial, failed and zero-trade statuses remain distinct. Curve, trade and position
sections use the API's bounded projections; empty evidence is labelled instead of replaced with inferred values.
The Risk controls panel shows the ordered manager chain, typed parameters, a composition fingerprint, summary counts,
and a paged decision trace. Reviewers can filter by manager, outcome, cycle, and client order; each row keeps its manager
reason and before/after quantity. Cycle and client-order cells link back to the run with those filters selected, so a
decision can be shared as a stable review URL. The panel labels explicit risk blocks, broker rejections, no-signal runs,
and orders without fills separately. Older runs display an explicit unavailable state; a missing fill alone is never
labelled a risk block.

The comparison workspace stores only the saved definition through the API. It resets stale evidence when the draft
changes, requires a server preview before rendering, filters curves and metrics to eligible runs, and displays every
selected exclusion reason. Empty and one-run states remain usable while compatible runs are unavailable or incomplete.

<!-- verified: integration:console tests/cross_package/workflows/test_console_browser.py -->
```bash
npm run generate
npm run check:contracts
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
```

Vitest/Testing Library cover the component and HTTP adapter, including loading, missing labels, failure bodies,
manual retry, keyboard use, cancellation and timeout. Browser assertions live in `tests/e2e`: the market-data journey
and agent-session workspace have isolated route-mocked checks, while the connection journey and cross-package workflow
exercise the real API/database boundary. Their server/database orchestration belongs to the repository's cross-package
workflow. From the repository root, with the pinned Node toolchain on PATH:

<!-- verified: integration:console tests/cross_package/workflows/test_console_browser.py -->
```bash
CONSOLE_BROWSER_TESTS=1 uv run pytest tests/cross_package/workflows/test_console_browser.py -q
```

This workflow builds against temporary ports, provisions its own PostgreSQL container, and starts the actual API and
production Next server. Playwright checks healthy desktop/mobile pages, real schema/database failures and a stopped
API. It removes its own processes, container and volume afterward. It rebuilds `.next` for its temporary API origin;
run `npm run build` again before subsequently using `npm start` against your normal local API. `npm run dev` is unaffected.
Screenshots/traces under `test-results/` are ignored and supplement, rather than replace, assertions. CI runs this
workflow and the explicit database workflow in addition to lint, type checking, unit tests and contract checks.
