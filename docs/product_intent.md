Warning: truncated output (original token count: 26807)
Total output lines: 1195

# Trader Product Intent

Status: **Draft for human review**. The vision below is Jared's statement on 2 October 2026. The journeys and
requirements are an assistant interpretation to refine together. They are desired product behavior, not claims about
what the current repository already delivers. [Product State](product_state.md) records implemented and qualified
behavior; Notion owns work priority and delivery status. The synchronized Notion copy is [Trader Product
Intent](https://app.notion.com/p/3ede5fad-e831-815a-a559-e89534eefe62).

## Human-authored vision

> Trader is ultimately serving multiple purposes. It is supposed to be a functional, traceable, auditable, platform
> for exploring financial data, building trading strategies, and ultimately, deploying them to a real trading
> environment. That's what the platform is at its core. On top of this, we have three high-value components: a
> console to enable interaction with data, and the construction, execution, and review of both backtests and live
> trading; an multi-agent system enabling powerful workflows for this research process, enabling me to automate
> significant parts of the process of ideating strategies, executing them, comparing them, and testing them for
> statistical signficance and robustness as necessary; an MCP server which enables these agents to interact with
> the core platform.
>
> Trader is being built for multiple reasons. I have graduated MSc Mathematical Finance and want to explore
> real-world trading. I am an experienced software engineer, and so want to use my education and experience to build
> real evidence of my ability to work in quantitative development.

The core platform supplies the data, strategy, execution, and evidence foundations. The Console is the human-facing
interface; the agent system carries out bounded research workflows; MCP gives those agents governed access to the
platform. The personal outcome is substantive evidence of quantitative development ability and a way to explore
real-world trading. These are distinct reasons for building Trader, and both should influence what is worth doing.

## Current product-state reconciliation — 5 October 2026

The Product Intent remains **Draft for human review**. The human-authored vision and user journeys remain the product
authority; the entries below reconcile the implementation state against that intent.

**Delivered and merged into `main` through [PR #13](https://github.com/JaredTambala/Trader/pull/13), merge commit
`b9d475e7fb39140094c69d4b87d6a25ebb92bde4`:**

- **GAP-06-01:** Console data evidence now exposes exact scope, provider/source, coverage, quality findings,
  provenance, and explicit incomplete states.
- **GAP-01-02:** Console can save, reopen, and revalidate an exact data scope without silently widening or replacing it.
- **GAP-03-02:** Review surfaces resolve Evaluation, multiple-testing, and robustness evidence with explicit missing,
  incompatible, and blocked states.
- **GAP-05-02:** Paper runtime operations are exposed as a typed, read-only Console projection with explicit freshness,
  identity, reconciliation, and limitation states.

These deliveries close the corresponding implementation gaps; they do not by themselves qualify the complete user
journeys.

**Next independently buildable tranche:**

- **GAP-06-02:** carry the exact qualified data scope into backtest authoring.
- **GAP-06-03:** prove replay/bar identity against qualified data.
- **GAP-02-02:** carry implementation admission and source-hash lineage into authoring.
- **GAP-05-03:** add audited operator-only paper controls.

**Sequencing constraints:** GAP-06-04 remains downstream of GAP-06-02 and GAP-06-03. The full execution-to-review and
paper qualification journeys remain later qualification work. UJ-04, UJ-07, UJ-08, and UJ-09 remain product features;
their composite qualification records must continue to be decomposed into executable work items before implementation.

## Candidate user journeys

The UJ records below are product features expressed as user journeys. Each feature defines an actor, trigger, behavior,
outcome, failure path, and evidence needed to judge whether the product serves the human purpose. A Notion work item is
a delivery unit that implements a component, closes a gap, updates documentation, or qualifies one or more features. It
must link back to the feature(s) it serves, but its title and status do not redefine the feature.

### UJ-01 — Explore financial data

**Actor and trigger:** Jared has a market question or a candidate asset and opens the Console to investigate available
data. **Path:** find a source and instrument; select a timeframe and bounded window; inspect coverage, prices, gaps,
quality findings, and provenance; compare available sources or windows; save an exact data scope for later research.
**Successful outcome:** Jared can say whether the data is fit for the question and point to the rows and limitations
behind that judgment. **Failure path:** absent, stale, partial, or inconsistent data is explicit; the Console does not
turn it into an apparently complete series. **Evidence:** source identity, scope, coverage, quality report, and exact
snapshot or query lineage.

### UJ-02 — Construct a trading strategy

**Actor and trigger:** Jared has a trading idea or wants to evaluate an agent-proposed hypothesis. **Path:** express the
hypothesis and expected mechanism; choose data, indicators/signals, strategy logic, risk controls, and parameters;
inspect or edit a versioned implementation; validate inputs and deterministic behavior; identify what result would
falsify the idea before looking at the final result. **Successful outcome:** a runnable, inspectable strategy definition
with explicit assumptions and reproducible version identity. **Failure path:** invalid interfaces, missing evidence,
or unsupported assumptions block execution with actionable reasons. **Evidence:** hypothesis, implementation version,
configuration, validation, and lineage.

### UJ-03 — Execute and review a backtest

**Actor and trigger:** Jared has a validated strategy and wants to learn what its historical behavior supports.
**Path:** select exact data and simulation assumptions; run a bounded backtest; inspect decisions, orders, fills,
positions, risk actions, performance, and failures in the Console; compare only compatible runs; examine statistical
uncertainty and robustness where the claim warrants it. **Successful outcome:** Jared can decide the next research
step without confusing simulation evidence with live performance. **Failure path:** incomplete runs, incompatible
comparisons, missing marks, and unrealistic assumptions stay visible. **Evidence:** immutable run identity, replay
inputs, accounting, execution semantics, diagnostics, and comparison exclusions.

### UJ-04 — Govern a delegated research session

**Actor and trigger:** Jared has a research objective and wants bounded automation without giving away decision
authority. **Path:** create a session with the operator, objective, exact scope, approvals, budget, model profile,
agent programs, and tool catalogue pinned; inspect the proposed agenda and specialist assignments; approve, redirect,
interrupt, resume, cancel, or stop the session. **Successful outcome:** the session lifecycle, authority decisions,
budgets, blockers, and terminal outcome are visible and recoverable. **Failure path:** invalid agenda, policy denial,
model/schema failure, budget exhaustion, lost response, or ambiguous recovery produces an explicit stop or request for
human direction. **Evidence:** session identity, agenda, policy receipts, public events, checkpoint identity, and
terminal decision.

### UJ-07 — Delegate specialist investigation

**Actor and trigger:** An approved session needs bounded Data or Strategy investigation before an experiment can be
planned. **Path:** the Coordinator delegates owned tasks; Data and Strategy specialists use only their role-scoped MCP
capabilities; independent branches run concurrently when safe; each branch returns canonical artifact references,
findings, warnings, and unresolved blockers; the Coordinator verifies and joins the returns. **Successful outcome:** the
session has qualified data readiness and/or an admitted strategy candidate with explicit lineage. **Failure path:**
unavailable data, out-of-scope loading, incompatible implementation, failed admission, or authority conflict stops the
branch or requests a revised task. **Evidence:** delegation and branch identity, MCP receipts, canonical artifacts,
compatibility/admission evidence, handoff summaries, and branch attribution.

### UJ-08 — Run a governed agent-directed experiment

**Actor and trigger:** A session has accepted data and strategy inputs and needs a reproducible test of a stated
question. **Path:** Experiment Design proposes a prospective protocol with claims, assumptions, protected-data roles,
budget, and stage gates; Jared approves or revises it; deterministic services execute the approved protocol; Evaluation
and Robustness work is requested only through their own authorities; the Coordinator joins the resulting evidence.
**Successful outcome:** the session returns a reproducible run, evaluation/robustness findings where required, and
explicit evidence of what the protocol supports. **Failure path:** missing approval, invalid protocol, worker failure,
replay mismatch, incompatible evidence, or exceeded authority blocks execution or requests human direction. **Evidence:**
protocol proposal and approval, execution receipt, run lineage, evaluation and robustness artifacts, limitations, and
public decision receipt.

### UJ-09 — Review agent evidence and choose the next action

**Actor and trigger:** Jared receives a completed or blocked agent branch and needs to decide what to do next. **Path:**
inspect canonical artifacts and public trajectory evidence; review uncertainty, limitations, comparison eligibility,
statistical and robustness findings; reject, refine, continue, or request a bounded successor experiment; record the
choice against the exact session, run, data, implementation, and evidence. **Successful outcome:** the next action is
explicit, attributable, and reproducible without treating an agent conclusion as an approval or profitability claim.
**Failure path:** missing evidence, incompatible references, unresolved blockers, or unsupported claims keep the
session in review or request human clarification. **Evidence:** evidence graph, claim-level limitations, operator
choice, successor inputs, and append-only decision receipt.

### UJ-05 — Move from research to trading operation

**Actor and trigger:** Jared decides a strategy may be ready for an operational environment. **Path:** review the
research evidence and risk limits; explicitly authorize a versioned deployment; qualify it in paper trading; inspect
live observations, orders, fills, positions, risk events, and drift in the Console; pause, stop, or revise it under a
controlled process. Paper trading is the meaningful operational destination for the current product horizon; funded
live execution remains a later decision that needs its own admission standard. **Successful outcome:** a deployment is
observable, attributable, and reversible within defined controls. **Failure path:** missing qualification, stale data,
unreconciled broker state, or breached risk limits block or halt operation. **Evidence:** deployment identity,
approval, configuration, broker reconciliation, risk actions, monitoring, and incident history.

### UJ-06 — Take a data question to a backtest

**Actor and trigger:** Jared has a market question and wants to determine whether it is worth developing into a
strategy. **Path:** state the question and falsifiable hypothesis; discover and qualify a bounded dataset; choose the
timeframe, universe, and evaluation window; construct the smallest versioned strategy and risk configuration; run a
reproducible backtest; inspect assumptions, diagnostics, uncertainty, and robustness; record the decision to reject,
refine, or continue. **Successful outcome:** one linked evidence trail connects the original question to the exact
data, implementation, run, result, limitation, and next action. **Failure path:** the flow stops with an actionable
data, validation, execution, or evidence blocker instead of encouraging an unsupported conclusion. **Evidence:**
hypothesis card, data scope and quality report, strategy identity, backtest receipt, review artifacts, and decision
record.

## Detailed story audit — UJ-06 / US-06-01

**User story:** As a researcher, I can qualify an exact, bounded data scope before a backtest uses it, so the run is
traceable to the data I actually inspected.

### Acceptance criteria

- The scope identifies symbols or universe, asset class, timeframe, UTC start and end, and the source/provider policy.
  A research role and interval are retained where a research protocol uses them; the current inventory request does
  not itself carry these fields.
- Discovery makes partial catalogues explicit rather than implying that the visible candidates are complete.
- Coverage is inspectable for every requested item, including first and last timestamps, row counts, missing or
  incomplete coverage, and source identity.
- Quality evidence covers the same scope, including missing gaps, session gaps, completeness, and warnings.
- A matching dataset manifest and quality report can be preserved as canonical evidence.
- Backtest creation and validation retain the exact Data evidence identity, reject scope mismatches, and establish
  whether the underlying bars still match the qualified data.
- The Console carries the selected scope and evidence into backtest authoring without silent changes or re-entry.

### Repository audit — 2 October 2026

**Implemented:** `trader_research.data` provides symbol discovery, inventory manifests, quality reports, bounded
loading, and matching canonical research snapshots. MCP exposes those operations with ownership and side-effect policy.
The Console provides read-only dataset discovery and bounded OHLCV exploration at `/data`. Its backtest authoring flow
accepts symbols, timeframe, UTC window, strategy/risk profiles, assumptions, resource limits, and benchmark; preflight
returns normalized input, fingerprints, coverage/warmup checks, and issues before persistence. Canonical research
backtest specifications embed hashed copies of a complete manifest and quality report and reject changed embedded
payloads. These separate slices have unit, MCP, API, frontend, and cross-package tests.

**Partial:** The Console dataset view currently shows aggregate coverage and source rows, but not the Data quality
report, quality warnings, provider resolution, ingestion lineage, or a persisted dataset/quality snapshot. Backtest
authoring asks for the data scope again, and its coverage preflight is not the Data context's quality snapshot. Its
definition has no source field, while canonical research backtest specifications reject source-filtered manifests.
The research specification snapshots manifest/report payloads rather than requiring canonical Data artifact references;
its hash checks detect changed snapshots, not changes to the underlying bar rows after inspection. The research
inventory `dataset_id` is derived from the query scope, not bar content. Current frontend/API tests qualify individual
boundaries; they do not prove the complete Console handoff against real services.

| Acceptance point | Current status | Repository evidence |
| --- | --- | --- |
| Discover bounded candidates | Implemented through Data/MCP; partial in Console | `src/trader_research/data/catalog.py`, `src/trader_mcp/runtime/server.py`, `apps/trader-console/src/features/market-data/market-data-workspace.tsx` |
| Inspect per-item coverage and quality | Implemented in Data; aggregate coverage only in Console | `src/trader_research/data/inventory.py`, `src/trader_research/data/quality.py`, `src/trader_console_api/repositories/resources.py` |
| Preserve matching Data evidence | Implemented in Data/MCP; absent in Console | `src/trader_research/data/evidence.py`, `src/trader_mcp/docs/tools.md` |
| Carry the same scope into authoring | Absent in Console | `apps/trader-console/src/features/backtest-authoring/backtest-authoring-workspace.tsx`, `src/trader_console_api/contracts.py` |
| Verify replay data identity | Partial | `src/trader_research/experiments/specifications/common.py`, `src/trader_research/experiments/specifications/backtest.py` |
| Qualify the full human workflow | Absent | `apps/trader-console/tests/e2e/market-data.spec.ts`, `apps/trader-console/tests/e2e/backtest-authoring.spec.ts` are separate mocked journeys |

### Executable gaps

- **GAP-06-01 — Console data evidence:** expose quality, completeness, provider/source, and provenance evidence for the
  selected dataset. [Notion work item](https://app.notion.com/p/3ede5fade831813493e9f5c3dae8d403).
- **GAP-06-02 — Exact scope handoff:** carry a typed scope and source policy from `/data` to authoring; resolve matching
  manifest/quality evidence rather than silently replacing it with aggregate coverage. [Notion work item](https://app.notion.com/p/3ede5fade8318102abbade7d1545fd95).
- **GAP-06-03 — Replay data identity:** define and enforce how a backtest proves that the bars it runs over still match
  the qualified dataset, including source semantics and post-inspection changes. [Notion work item](https://app.notion.com/p/3ede5fade83181b7bb99cd42dce2dabb).
- **GAP-06-04 — End-to-end qualification:** add an integrated fixture journey covering selection, evidence review,
  preflight, persistence, execution submission, and failure states. [Notion work item](https://app.notion.com/p/3ede5fade83181e6b44ee332bdfa6975).

## Detailed story audit — UJ-01 / US-01-01

**User story:** As a researcher, I can discover, inspect, compare, and preserve a bounded data scope, so I can decide
whether it is fit for a market question before downstream work uses it.

### Acceptance criteria

- The query fixes asset class, symbols or universe, timeframe, interval, UTC window, source/provider policy, and the
  purpose or research role of the data.
- Discovery states whether the catalogue is complete, partial, stale, or unavailable; visible symbols are not presented
  as proof that the universe is complete.
- Every selected item exposes first/last timestamps, row counts, source identity, coverage gaps, session gaps,
  completeness, and quality warnings for the same scope.
- The researcher can inspect bounded bars and compare source or window alternatives without losing the identity of each
  alternative.
- A matching manifest and quality report can be saved as a reusable snapshot and handed to strategy or backtest work
  without re-entry or silent scope changes.
- Missing data, provider errors, stale results, and quality warnings are actionable states rather than hidden fallbacks.

### Repository audit — 2 October 2026

**Implemented:** `trader_research.data` supports multi-asset symbol discovery, inventory, quality summarization,
bounded loading, revalidation, and canonical research snapshots. The MCP catalogue exposes those operations with
bounded scope and loading policy. The Console `/data` route lists stock/crypto symbol-timeframe-source slices,
retrieves bounded OHLCV bars, renders a candlestick/volume chart, supports UTC windows and pagination, and shows empty,
loading, retry, and error states. Its API queries producer-owned `console_read` projections and does not mutate Trader
state.

**Partial:** the Console does not expose the Data quality report, session-gap/completeness findings, provider
resolution, ingestion lineage, catalogue completeness, or canonical snapshot identity. It cannot compare two source or
window selections as evidence, and it does not save a selected scope for later authoring. The same missing evidence
continuity is captured by the UJ-06 audit where this journey feeds a backtest.

| Acceptance point | Current status | Repository evidence |
| --- | --- | --- |
| Discover bounded datasets | Implemented in Data/MCP; implemented as aggregate slices in Console | `src/trader_research/data/catalog.py`, `src/trader_mcp/docs/tools.md`, `src/trader_console_api/repositories/resources.py` |
| Inspect bars and bounded windows | Implemented and browser-tested | `apps/trader-console/src/features/market-data/market-data-workspace.tsx`, `apps/trader-console/tests/e2e/market-data.spec.ts` |
| Explain quality and provenance | Implemented in Data; absent from Console | `src/trader_research/data/quality.py`, `src/trader_research/data/evidence.py` |
| Compare alternatives | Absent as a product workflow | `src/trader_console_api/docs/usage.md` has no comparison resource for data scopes |
| Preserve and reuse an exact snapshot | Implemented as a research service; absent from Console handoff | `src/trader_research/data/evidence.py`, `apps/trader-console/src/features/market-data` |

### Executable gaps

- **GAP-01-01 — Data fitness readout:** expose matching quality, completeness, provider/source, and provenance evidence
  in the Console. This is shared with GAP-06-01 rather than a second implementation.
- **GAP-01-02 — Saved data scope:** let a researcher persist and reopen an exact scope/snapshot, with immutable identity
  and explicit stale or unavailable states, before handing it to authoring. [Notion work item](https://app.notion.com/p/3ede5fad-e831-81f0-89d3-d95664c5654a).
- **GAP-01-03 — Data alternative comparison:** provide a bounded comparison of source or window alternatives that keeps
  coverage, quality, and provenance evidence separate and explains why an alternative is or is not comparable. [Notion work item](https://app.notion.com/p/3ede5fad-e831-8197-bfad-efec589cfb90).
- **GAP-01-04 — Discovery completeness contract:** make provider/catalogue completeness and source capability explicit
  in the Console response and tutorial, including the distinction between catalogue discovery and load capability. [Notion work item](https://app.notion.com/p/3ede5fad-e831-8187-ab3c-c59b4cf35e37).

## Detailed story audit — UJ-02 / US-02-01

**User story:** As a researcher, I can turn a falsifiable hypothesis into a versioned strategy and risk configuration,
so I can inspect its assumptions and validation evidence before running it.

### Acceptance criteria

- A hypothesis or research brief records the question, mechanism, falsifier, intended universe and timeframe, expected
  evidence, assumptions, and the decision that would follow each outcome.
- The workflow searches maintained and admitted implementations before authoring, records field-level compatibility,
  and distinguishes exact reuse, bounded adaptation, and new authorship.
- New code is written only in an isolated Coding Workspace, packaged with source hash and lineage, independently
  validated, and registered as an immutable implementation version.
- Strategy and ordered risk specifications pin implementation versions, parameters, sizing, runtime requirements,
  execution assumptions, provenance, and tunable fields; invalid or live-authority inputs fail closed.
- The human can inspect the implementation/admission lineage and the reason for every blocker before a backtest is
  submitted. Arbitrary Python imports or opaque serialized callables are not accepted by the Console.

### Repository audit — 2 October 2026

**Implemented:** `trader_standard` supplies maintained indicators, signals, strategies, and risk managers. The research
Experiments context provides bounded implementation search, exact resolution, comparison, source-free result rows,
independent validation/admission, immutable strategy and risk-stack specifications, and prediction-binding revalidation.
The Coding context defines an ephemeral, digest-pinned workspace with bounded checks and cleanup. The Strategy
Engineering agent is catalogue-first and can reuse, adapt, or author through MCP; it never self-approves admission. The
Console publishes a typed strategy/risk catalogue and performs side-effect-free parameter, coverage, warmup, and budget
preflight.

**Partial:** the Console authoring flow starts from allowlisted profiles and parameters; it has no hypothesis card,
research brief, implementation comparison, source/admission lineage, or explicit reuse/adapt/author decision. The
agentic Strategy Engineering loop is implemented but controlled third-party-model qualification remains outstanding.
The current first agentic slice stops at an admitted strategy/risk candidate and does not design or execute an
experiment.

| Acceptance point | Current status | Repository evidence |
| --- | --- | --- |
| Hypothesis and falsifier record | Partial in Experiment Design contracts; no complete Console authoring path | `src/trader_research/governance`, `src/trader_agents/docs/roles_and_authority.md` |
| Catalogue search and compatibility | Implemented and focused-tested | `src/trader_research/experiments/implementations/catalog.py`, `tests/trader_research/experiments/test_implementation_catalog.py` |
| Isolated authoring and admission | Implemented and controlled at deterministic boundary | `src/trader_research/docs/coding.md`, `src/trader_research/experiments/implementations` |
| Immutable strategy/risk specs | Implemented and controlled | `src/trader_research/experiments/specifications/strategy.py`, `src/trader_research/experiments/specifications/risk.py` |
| Human-facing lineage and agent qualification | Absent/partial | `apps/trader-console/src/features/backtest-authoring`, `src/trader_agents/docs/qualification.md` |

### Executable gaps

- **GAP-02-01 — Hypothesis and experiment brief:** settle the Experiment Design boundary and persist a typed,
  falsifiable brief that can be handed to Data, Strategy, and later Evaluation without losing the intended decision. [Notion work item](https://app.notion.com/p/3ede5fad-e831-81f0-aa8d-fece8b2bd5f0).
- **GAP-02-02 — Console implementation lineage:** carry an admitted implementation/version, validation report,
  strategy/risk specification, and provenance into authoring and display their blockers; keep the existing allowlist and
  preflight authority intact. [Notion work item](https://app.notion.com/p/3ede5fad-e831-8112-9365-cc4c2788d08e).
- **GAP-02-03 — Controlled Strategy Engineering qualification:** execute the real MCP/model matrix against the pinned
  third-party model profile, including exact reuse, adaptation, new authorship, failed admission, repair, interruption,
  and restart evidence. Existing [IMP-07](https://app.notion.com/p/3d0e5fade83181debc89d6222479f75a) and the agentic implementation slice are design and implementation context, not controlled acceptance. [Notion work item](https://app.notion.com/p/3ede5fad-e831-81c6-b550-dc5bc151e3b8).
- **GAP-02-04 — Hypothesis-to-candidate handoff:** qualify one integrated path from a brief through catalogue
  comparison, isolated authoring or reuse, admission, and a reviewable candidate record. [Notion work item](https://app.notion.com/p/3ede5fad-e831-81e1-a348-c5c953304284).

## Detailed story audit — UJ-03 / US-03-01

**User story:** As a researcher, I can execute and review a bounded backtest with its assumptions and evidence, so I can
decide what the result supports and what experiment should happen next.

### Acceptance criteria

- A run fixes exact data identity, strategy/risk versions, initial state, costs, execution/fill assumptions, benchmark,
  code identity, and evaluation boundaries before execution.
- Submission is bounded, idempotent, observable, and explicit about queued, running, completed, partial, failed, and
  reconciliation-required outcomes.
- Review exposes scope, assumptions, signals, orders, fills, positions, risk decisions, performance, curves, warnings,
  lifecycle, provenance, and evidence coverage without recomputing producer evidence.
- Comparisons admit only compatible runs and keep exclusions and reasons visible.
- Evaluation, statistical uncertainty, multiple-testing, and robustness evidence are shown when a claim requires them;
  a successful simulation is not presented as live or deployment evidence.
- The human can record a rejection, refinement, or next experiment linked to the exact run and its limitations.

### Repository audit — 2 October 2026

**Implemented:** the Experiments context validates immutable implementation, strategy, risk, and backtest
specifications, executes canonical Postgres runs, persists orders/fills/positions/metrics/warnings/provenance, and
supports deterministic grid/random optimisation, sealed holdout, Evaluation, and optimisation-specific Adversarial
reports. Core replay uses an internal deterministic paper broker and records cycle evidence. Console APIs expose run
scope, assumptions, performance, curves, trades, positions, risk composition and decisions, lifecycle, provenance,
indicator/signal evidence, and comparison eligibility. The Console has single-run review, saved comparison views,
durable definition/execution records, a local worker, bounded retries, and explicit ambiguous-outcome reconciliation.

**Partial:** the worker-to-canonical-BacktestRunner path and live producer qualification remain incomplete for the
Console authoring slice. Console review does not yet provide a complete Evaluation/Adversarial/statistical inference
readout or a first-class next-decision record. General robustness attacks and walk-forward optimization remain absent.
The data identity handoff and replay-bar identity are covered by GAP-06-02 and GAP-06-03.

| Acceptance point | Current status | Repository evidence |
| --- | --- | --- |
| Immutable run inputs and deterministic execution | Implemented and controlled in research/core | `src/trader_research/docs/experiments.md`, `src/trader/docs/runtime.md` |
| Durable Console submission/lifecycle | Implemented; end-to-end producer qualification pending | `src/trader_console_api/docs/usage.md`, `src/trader_console_api/services/backtest_worker.py` |
| Rich single-run review | Implemented and browser-qualified for published evidence | `apps/trader-console/src/features/backtest-review/backtest-review-workspace.tsx` |
| Compatible comparison | Implemented with explicit exclusions | `apps/trader-console/src/features/comparisons`, `src/trader_console_api/docs/usage.md` |
| Inference, robustness, and next decision | Partial/absent in Console | `docs/product_state.md` capability matrix and known limits |

### Executable gaps

- **GAP-03-01 — Producer-backed Console execution qualification:** finish the real worker-to-BacktestRunner path and
  qualify restart, stale-worker, partial, failed, outage, and reconciliation-required states against isolated Postgres.
  This narrows the existing [TRD-273](https://app.notion.com/p/3ebe5fade83181a48eb8ec296c9d71e1)/[TRD-274](https://app.notion.com/p/3ebe5fade831814c93adfe68fe401894) work rather than replacing it.
- **GAP-03-02 — Review statistical and robustness evidence:** expose Evaluation, multiple-testing, and Adversarial
  artifacts with their protected-data roles, limitations, and claim-level blockers in run/comparison review. [Notion work item](https://app.notion.com/p/3ede5fad-e831-81b5-bca0-d0db1c47e09e).
- **GAP-03-03 — Next-decision record:** let the researcher record reject/refine/continue and the next bounded experiment,
  linked to exact run, data, implementation, assumptions, and review artifacts. [Notion work item](https://app.notion.com/p/3ede5fad-e831-8185-b650-c982315ae1c9).
- **GAP-03-04 — Research execution journey qualification:** prove one integrated data-to-definition-to-worker-to-review
  path with evidence identity continuity, including the data handoff tasks already listed under UJ-06. [Notion work item](https://app.notion.com/p/3ede5fad-e831-813c-8f09-f9112b203ac6).

## Detailed story audit — UJ-04 / US-04-01

**User story:** As a researcher, I can start and govern a bounded agent session, so I can use automation while keeping
scope, authority, intervention, and recovery under human control.

### Acceptance criteria

- Session creation pins the operator, objective, exact scope, approvals, budgets, model profile, agent programs, tool
  catalogue, and implementation inputs.
- The Coordinator forms a typed agenda and delegates only owned specialist work; dependency-ready branches can run
  concurrently when their mutation keys do not conflict.
- Public session state shows agenda, progress, policy decisions, blockers, checkpoint identity, and terminal outcome
  without exposing prompts, hidden reasoning, or raw tool payloads.
- Interrupt, cancel, fresh-process resume, lost-response recovery, budget exhaustion, policy denial, and model/schema
  failure are explicit fail-closed states.
- The exact third-party model/runtime/tool identities and repeatable behavioral qualification evidence are available
  before the session is described as a controlled research service.

### Repository audit — 3 October 2026

**Implemented:** `trader_agents` has typed session, agenda, delegation, checkpoint, and observability contracts; a
model-backed Coordinator graph; deterministic authority and budget policy; public redacted events; PostgreSQL
checkpoints; start/resume/inspect/cancel lifecycle; and focused security, recovery, isolation, interruption, and
evidence-reconciliation tests. The MCP server exposes governed research tools and prohibits broker mutation, raw SQL,
and hidden state.

**Partial:** the current LFM profile failed the material-ambiguity coordinator choice gate and a later diagnostic run
failed strict turn-schema validation before MCP calls. Controlled behavioral qualification has therefore not passed.
The runtime is CLI-oriented; the Console has no session agenda, public-event, checkpoint, interrupt, or terminal-decision
workspace. These are session-governance gaps, separate from the specialist and experiment journeys below.

| Acceptance point | Current status | Repository evidence |
| --- | --- | --- |
| Session identity, authority, and budgets | Implemented and focused-tested | `src/trader_agents/docs/architecture.md`, `tests/trader_agents/contracts_state` |
| Agenda, delegation, and lifecycle controls | Implemented in runtime; human Console surface absent | `src/trader_agents/coordination`, `src/trader_agents/application_runtime` |
| Public trace and checkpoint recovery | Implemented and focused-tested | `src/trader_agents/observability`, `src/trader_agents/checkpointing` |
| Controlled model qualification | Failed gate / not accepted | `src/trader_agents/docs/qualification.md`, `tests/cross_package/qualification/test_agentic_real_model_campaign.py` |
| Console intervention and terminal review | Absent | `apps/trader-console/src/features`, `docs/product_state.md` |

### Executable gaps

- **GAP-04-01 — Controlled third-party model qualification:** complete the pinned model/provider/tool/environment
  campaign for Coordinator, Data, and Strategy, including ambiguity, denial, recovery, and repeatability gates. The
  result is controlled evidence only when every mandatory phase passes. Existing IMP-05 and IMP-07 provide campaign
  context rather than acceptance.
- **GAP-04-02 — Console agent session workspace:** expose session identity, agenda, progress, public events, evidence
  references, operator interrupts, resume/cancel actions, and terminal decisions without exposing hidden prompts or
  reasoning.
- **GAP-04-04 — Agent trajectory qualification:** prove fresh-process recovery and concurrent branch attribution in a
  retained, queryable public trajectory fixture with model/program/catalogue identities and redaction guarantees.

## Detailed story audit — UJ-07 / US-07-01

**User story:** As a researcher, I can delegate bounded Data and Strategy investigation, so a session returns qualified
inputs for experiment design with ownership and lineage intact.

### Acceptance criteria

- The Coordinator delegates only registered Data or Strategy responsibilities with typed scope, inputs, limits, and
  branch/attempt identity.
- Specialists call MCP tools through role-scoped clients and return canonical artifacts, bounded findings, warnings,
  and blockers; they cannot write directly to platform services or approve their own output.
- Independent investigation branches may run concurrently while their identity, budgets, and evidence remain separate.
- The Coordinator rereads exact artifact refs and accepts a handoff only when domain owner, producer, requester, actor,
  artifact type, and digest agree.
- The human can distinguish data readiness, exact reuse, adaptation, new authorship, failed admission, and unresolved
  scope before an experiment is proposed.

### Repository audit — 3 October 2026

**Implemented:** Data Research and Strategy Engineering specialist loops, role-scoped MCP clients, catalogue-first
strategy reuse/adaptation/authorship, isolated Coding Workspace boundaries, independent admission, and canonical handoff
contracts exist and are focused-tested. The first slice reaches exact Data readiness and an admitted strategy/risk
candidate.

**Partial:** controlled third-party model qualification remains failed; the Console does not expose branch progress and
handoffs; the current slice does not continue into Experiment Design or independent evaluation. Data evidence continuity
is shared with UJ-01/UJ-06 rather than duplicated here.

### Executable gaps and existing work

- **GAP-02-03 — Controlled Strategy Engineering qualification:** qualify exact reuse, adaptation, new authorship,
  failed admission, repair, interruption, and restart against the pinned model/tool environment.
- **GAP-04-01 — Controlled third-party model qualification:** qualify Coordinator/Data/Strategy behavior and authority
  gates as one controlled campaign.
- **GAP-04-04 — Agent trajectory qualification:** retain concurrent branch attribution and public handoff evidence.
- **GAP-06-01/02 and GAP-02-02:** preserve qualified Data evidence and implementation lineage across the human Console
  handoff; these are shared boundaries rather than new specialist-specific tasks.

## Detailed story audit — UJ-08 / US-08-01

**User story:** As a researcher, I can approve and run an agent-proposed experiment protocol, so execution and review
remain deterministic, attributable, and bounded by the agreed scientific design.

### Acceptance criteria

- Experiment Design produces a prospective protocol with claims, assumptions, protected-data roles, budgets, stage gates,
  and explicit approval requirements.
- A human approval is required before execution; the Coordinator cannot execute, mutate the protocol after results, or
  issue an overall quality verdict.
- Deterministic execution uses exact data, strategy/risk, replay identity, and environment inputs and returns a durable
  receipt for queued, running, completed, partial, failed, or reconciliation-required states.
- Evaluation and Robustness authorities receive the immutable run and return independent artifacts with claim-level
  limitations; missing or incompatible evidence remains visible.
- The agent path terminates with a reproducible evidence bundle or a typed blocker/request for human direction.

### Repository audit — 3 October 2026

**Implemented:** deterministic Experiment Design proposal services, canonical experiment specifications, backtest
execution, evaluation/optimisation artifacts, and robustness-related artifact contracts exist in research/core.

**Absent or partial:** no model-backed Experiment Design graph is in the clean runtime; the current agent slice does not
execute experiments, request independent Evaluation/Robustness work, or expose the full lifecycle in the Console. The
Console worker-to-runner qualification and replay-bar identity are also incomplete.

###…6807 tokens truncated…re relative delivery sizes, not calendar promises. **S** is a bounded change inside one package with a known
contract and focused tests. **M** crosses a small number of package or persistence seams and needs an integration check.
**L** crosses several packages, introduces a new authority or evidence boundary, or requires controlled model/broker
qualification. The size includes implementation, documentation, and verification; it is not a measure of product value.

| Requirement | Gap size | Why the gap has this size | Required delivery units and dependency gate |
| --- | --- | --- | --- |
| FR-01 — Data identity and provenance | **L** | Identity must survive Data, Console, authoring, replay, and research persistence; the current query-scope ID is not bar-content identity. | **GAP-01-02 (M):** persist/reopen exact snapshot; **GAP-06-01 (M):** expose quality/provenance; **GAP-06-02 (M):** typed authoring handoff; **GAP-06-03 (L):** define/enforce replay identity; **GAP-06-04 (L):** qualify the chain. The replay decision gates execution qualification. |
| FR-02 — Data exploration and fitness | **M** | Data services are strong; the missing work is a Console evidence projection, provider capability state, and bounded alternative comparison. | **GAP-01-01 / GAP-06-01 (M):** quality readout; **GAP-01-03 (M):** alternative comparison; **GAP-01-04 (S):** discovery/load capability contract. Browser qualification follows the response contract. |
| FR-03 — Versioned strategy construction | **L** | The deterministic admission path exists, but a hypothesis contract, Console lineage, model qualification, and integrated handoff are separate boundaries. | **GAP-02-01 (M):** typed brief; **GAP-02-02 (M):** Console admission lineage; **GAP-02-03 (L):** controlled Strategy model campaign; **GAP-02-04 (L):** integrated candidate handoff. The brief and lineage contracts precede the integrated path. |
| FR-04 — Reproducible backtest execution | **L** | Core/research execution is controlled, but Console execution, exact data handoff, replay identity, and failure qualification are cross-package. | Existing TRD-273/TRD-274 plus **GAP-03-04 (L)** for the integrated worker path, and **GAP-06-03 (L)** for replay identity. The data identity decision gates the end-to-end test. |
| FR-05 — Backtest evidence and limits | **L** | Rich evidence exists, but claim-level Evaluation/Adversarial evidence, next decisions, and a qualified Console lifecycle are distinct product surfaces. | **GAP-03-02 (M):** evidence projection; **GAP-03-03 (M):** next-decision artifact; **GAP-03-04 (L):** execution-to-review qualification. Evidence projection precedes the integrated journey. |
| FR-06 — Fair comparison and inference | **M** | Compatibility rules and optimisation ledgers exist; the missing slice is presenting inference/robustness limits alongside comparisons. | **GAP-03-02 (M):** Evaluation/Adversarial readout and claim blockers; **GAP-03-03 (M):** decision record. General robustness and walk-forward remain separate larger roadmap capabilities. |
| FR-07 — Bounded agent research | **L** | Runtime contracts exist, but controlled model behavior and the handoff into experiment design/execution are unqualified external boundaries. | Existing IMP-05/IMP-07 plus **GAP-02-03 (L):** Strategy qualification; **GAP-04-01 (L):** Coordinator/Data/Strategy campaign; **GAP-04-03 (L):** experiment handoff. Controlled qualification gates any autonomy claim. |
| FR-08 — Governed MCP access | **L** | Registration, envelopes, ownership, and prohibitions are implemented; the remaining real-world claim requires controlled qualification across model, tool catalogue, transport, and failure behavior. | **GAP-04-01 (L):** qualification campaign is the material remaining task; no new MCP contract is required for the current deterministic surface. |
| FR-09 — Research trace and recoverability | **L** | Redacted events and checkpoints exist, but a human-readable Console projection and retained concurrent trajectory evidence are new seams. | **GAP-04-02 (L):** Console session workspace; **GAP-04-04 (M):** retained trajectory fixture. The public projection contract must be fixed before the UI. |
| FR-10 — Console research workflow | **L** | Existing screens are separate vertical slices; preserving context from data through strategy, agents, execution, review, and next decision is a multi-seam integration. | **GAP-06-02/04 (M/L):** data handoff; **GAP-02-02 (M):** strategy lineage; **GAP-03-03/04 (M/L):** decision and review; **GAP-04-02 (L):** agent workspace; **GAP-05-02/03 (L):** paper operations. Each boundary must be qualified before the whole journey. |
| FR-11 — Controlled deployment | **L** | A new human authority and evidence artifact must connect research to paper operation while keeping agents outside approval. | **GAP-05-01 (L):** admission artifact; **GAP-05-04 (L):** paper admission campaign. Model-specific ML eligibility remains a collaborator, not the general admission contract. |
| FR-12 — Trading observability and intervention | **L** | Core/operator CLI behavior exists, but Console read models and authorized command boundaries require transport, persistence, authority, and failure qualification. | **GAP-05-02 (L):** operational read model; **GAP-05-03 (L):** start/pause/stop/reconcile controls; **GAP-05-04 (L):** incident campaign. Read evidence should land before mutating controls. |
| FR-13 — Auditability across the lifecycle | **L** | Each domain has artifacts, but one inspectable chain across data, strategy, agent, experiment, review, decision, and paper admission is not yet preserved. | **GAP-01-02 (M):** saved data identity; **GAP-03-03 (M):** decision artifact; **GAP-04-04 (M):** trajectory evidence; **GAP-05-01 (L):** admission lineage; then **GAP-03-04 (L)** for integrated reconstruction. |
| FR-14 — Demonstrable quantitative development evidence | **M** after the foundations | The raw evidence exists; the missing product outcome is a reproducible case study that explains choices, tests, limitations, and revisions. | **GAP-02-04 (L):** candidate handoff; **GAP-03-03/04 (M/L):** reviewed decision and integrated run; **GAP-04-04 (M):** public trajectory evidence; **GAP-05-04 (L):** paper qualification case. This is downstream of the preceding evidence chain. |

### Delivery sequence implied by the sizes

1. **Fix identity contracts:** complete the data snapshot, quality projection, hypothesis brief, implementation lineage,
   and public agent-event projections. These are the inputs that later work must carry without re-entry.
2. **Prove research execution:** resolve replay identity, complete the worker qualification, expose Evaluation/Adversarial
   evidence, and record next decisions. This produces a trustworthy research loop before operational work begins.
3. **Qualify bounded agent automation:** run the pinned third-party model campaign, retain public trajectories, and extend
   the approved specialist return into Experiment Design and deterministic execution.
4. **Build paper operation:** create human paper admission, expose runtime evidence, add authorized intervention, and run
   the incident campaign. Funded live execution remains outside this sequence.
5. **Assemble professional evidence:** use the accepted artifacts and decisions to produce a reproducible case study with
   explicit limitations and revisions, satisfying FR-14 without making an unsupported profitability claim.

## Implementation playbook for executable gaps

The audit above describes the product gap; this section describes how to close it. Every gap is implementation-ready
when its contract owner, data flow, repository surfaces, verification fixtures, documentation changes, dependencies,
and completion evidence are known. The paths below are the intended seams, not permission to bypass package ownership.
Each implementation should first create or update its linked Notion work item, then land the smallest contract and
focused tests before adding the next adapter or UI projection. A gap closes only when the contract tests, package docs,
and the stated integrated evidence all pass.

### Data identity and exploration (UJ-06 / UJ-01)

#### GAP-06-01 / GAP-01-01 — Console data evidence (M)

1. **Contract and flow:** extend the Console resource read contract so a selected scope returns the normalized Data
   manifest, quality report, completeness/coverage findings, provider/source resolution, ingestion/provenance refs,
   and explicit `complete`, `partial`, `stale`, or `unavailable` state. The repository reads producer-owned evidence;
   `ResourceService` maps missing or incompatible evidence to typed warnings; the resources router exposes it; the
   market-data workspace renders evidence beside the chart. No Console code recreates quality calculations.
2. **Owning surfaces:** `src/trader_research/data/{inventory.py,quality.py,evidence.py}` remain the producer;
   `src/trader_console_api/{contracts.py,repositories/resources.py,services/resources.py,routers/resources.py}` own
   the projection; `apps/trader-console/src/features/market-data/` owns the display.
3. **Verification:** add repository/service/router contract cases for complete, partial, stale, unavailable, and
   mismatched evidence; add a cross-package fixture with one manifest and quality report; extend
   `apps/trader-console/tests/e2e/market-data.spec.ts` for each visible state and provenance link. Reuse existing
   `tests/trader_console_api/{repositories,services,routers}` patterns rather than testing SQL through the browser.
4. **Docs and completion evidence:** update `src/trader_console_api/docs/{usage.md,architecture.md}` and the Console
   tutorial. Completion is an API response plus browser fixture that lets a reviewer identify the exact evidence and
   see a warning when it is absent; update `docs/product_state.md` with the qualified boundary.

#### GAP-06-02 — Exact scope handoff (M)

1. **Contract and flow:** define a typed scope/snapshot handoff containing symbols or universe, asset class,
   timeframe, interval, UTC window, source policy, manifest identity, quality identity, and freshness state. The Data
   selection emits it; Console persistence stores the immutable handoff; authoring loads it by identity; preflight
   rejects scope or evidence mismatches instead of replacing them with aggregate coverage.
2. **Owning surfaces:** add the value object at the Console/research boundary (with normalization at the API edge),
   persistence beside `src/trader_console_api/repositories/{resources.py,backtest_definitions.py}`, and mapping in
   `src/trader_console_api/{services,routers}`. Update
   `apps/trader-console/src/features/{market-data,backtest-authoring}/` to pass the saved identity.
3. **Verification:** repository migration/schema compatibility, API round-trip, stale snapshot, changed scope,
   source-policy mismatch, and reopen tests; browser test selects data, opens authoring, and asserts no re-entry. Add a
   cross-package fixture proving the same manifest/report IDs reach the persisted definition.
4. **Docs/dependencies/evidence:** depends on GAP-06-01's evidence contract and GAP-01-02's saved-scope behavior.
   Update Console usage/architecture and `src/trader_research/docs/{data.md,experiments.md}`. Completion is a persisted
   definition whose evidence refs match the selected Data fixture and whose mismatch response is actionable.

#### GAP-06-03 — Replay data identity (L)

1. **Decision and flow:** choose and document the bar-content identity (canonical manifest plus deterministic content
   digest, source semantics, and inspection timestamp policy), then add it to the backtest specification and execution
   receipt. At load and run time, resolve the qualified evidence and fail closed when bars, source policy, or digest
   differ; record an explicit environmental-difference outcome when policy permits a revalidation.
2. **Owning surfaces:** Data identity calculation belongs in `src/trader_research/data/evidence.py`; specification and
   validation changes belong in `src/trader_research/experiments/specifications/{common.py,backtest.py}` and
   `src/trader_research/experiments/backtests/`; core replay records the result under `src/trader/`. Do not make the
   Console a second identity authority.
3. **Verification:** deterministic digest fixtures, unchanged replay, changed bar, changed source, partial reload,
   and post-inspection mutation cases; Postgres execution tests assert the receipt and failure state. Extend the
   existing research specification hash tests and add one cross-package qualification with a mutated fixture.
4. **Docs/dependencies/evidence:** depends on GAP-06-01/02 and gates GAP-03-01/04. Update
   `src/trader_research/docs/{data.md,experiments.md,artifacts_and_persistence.md}` and `src/trader/docs/runtime.md`.
   Completion is a run receipt that proves the bars match the qualified identity or clearly records why execution was
   refused.

#### GAP-06-04 — End-to-end data qualification (L)

1. **Scenario and flow:** build one isolated fixture that selects a bounded scope, displays evidence, saves/reopens
   it, creates an authoring definition, runs preflight, persists a submission, and exercises missing, stale, mismatch,
   and failed states. Keep the fixture instrument-agnostic and use the same IDs through every boundary.
2. **Owning surfaces:** compose existing Data, Console API, worker, and browser boundaries; the qualification harness
   lives under `tests/cross_package/qualification/` or `tests/cross_package/workflows/`, with no production shortcut.
3. **Verification:** use an isolated Postgres schema/database and deterministic fixture rows; add API-to-worker and
   Playwright coverage for success and each stop condition. Assert evidence IDs, scope fields, and final receipts,
   rather than only HTTP status or rendered text.
4. **Docs/dependencies/evidence:** depends on GAP-06-01 through GAP-06-03. Update `docs/product_state.md`,
   `src/trader_console_api/docs/tutorial.md`, and the qualification documentation. Completion is a repeatable command
   that reconstructs the full data-to-definition evidence chain from a fresh database.

#### GAP-01-02 — Saved data scope (M)

1. **Contract and flow:** persist an immutable saved-scope record that references the exact manifest/report and records
   scope, source policy, created-by, and freshness. Reopen must return `active`, `stale`, or `unavailable` explicitly;
   it must never silently refresh or widen the scope.
2. **Owning surfaces:** add the repository schema and typed service under `src/trader_console_api/repositories/` and
   `src/trader_console_api/services/`; expose create/read/revalidate routes; add save/reopen actions in the market-data
   feature. Use Data artifacts as references, not copied quality logic.
3. **Verification:** persistence, idempotency, authorization, stale/unavailable, and schema-compatibility tests plus a
   browser reopen test. Include a fixture where the referenced artifact has been superseded.
4. **Docs/evidence:** update Console usage/tutorial and `docs/product_state.md`. Completion is a saved record that can
   be reopened after a fresh process with immutable evidence references.

#### GAP-01-03 — Data alternative comparison (M)

1. **Contract and flow:** create a comparison read model for two or more saved scopes with independent coverage,
   quality, provenance, and compatibility findings. Require equal comparison dimensions before calculating a difference
   and report excluded dimensions/reasons instead of collapsing them.
2. **Owning surfaces:** add a Console comparison contract/service/repository alongside existing comparison views;
   reuse Data evidence references; render a bounded alternative panel in `apps/trader-console/src/features/market-data/`
   (or the existing comparisons feature when the comparison is run-level).
3. **Verification:** equal source/window, different source, different window, missing evidence, and incompatible
   timeframe fixtures; API contract and browser tests assert every exclusion reason.
4. **Docs/evidence:** update `src/trader_console_api/docs/usage.md`, tutorial, and Product State. Completion is a
   reviewable comparison in which each alternative retains its own identity and limitations.

#### GAP-01-04 — Discovery completeness contract (S)

1. **Contract and flow:** normalize provider/catalogue response fields for completeness, freshness, capability to
   discover, and capability to load. Keep catalogue visibility separate from successful bounded loading; map provider
   errors to an explicit state.
2. **Owning surfaces:** producer normalization in `src/trader_research/data/catalog.py` and MCP envelope/docs;
   Console mapping in `src/trader_console_api/contracts.py` and resource service; display in the market-data workspace.
3. **Verification:** complete, partial, stale, unavailable, discover-only, and load-capable fixtures across Data,
   MCP, API, and browser layers.
4. **Docs/evidence:** update `src/trader_research/docs/data.md`, `src/trader_mcp/docs/{contracts.md,tools.md}`, and
   Console tutorial. Completion is an example response and test proving the UI never treats visible symbols as a
   complete universe.

### Strategy construction (UJ-02)

#### GAP-02-01 — Hypothesis and experiment brief (M)

1. **Contract and flow:** settle the Experiment Design owner and define a typed brief containing question, mechanism,
   falsifier, intended universe/timeframe, bounded data requirements, strategy intent, risk intent, assumptions,
   expected evidence, and outcome-to-decision rules. Persist a revisioned brief and expose references that Data,
   Strategy, and Evaluation can consume without copying intent.
2. **Owning surfaces:** extend `src/trader_research/governance/` (or its agreed Experiment Design module), its
   artifact store/projection, and MCP registration only if agents need to create proposals. Console reads and edits go
   through `src/trader_console_api/` and a dedicated feature; agents never write the human decision directly.
3. **Verification:** contract validation, revision/idempotency, missing falsifier, incompatible scope, authorization,
   and serialization tests; one cross-package fixture passes the same brief into Data and Strategy planning.
4. **Docs/evidence:** update governance architecture, MCP contracts/tools if exposed, Console usage, and Product State.
   Completion is a durable brief with a visible revision and a downstream handoff that preserves the intended decision.

#### GAP-02-02 — Console implementation lineage (M)

1. **Contract and flow:** extend the authoring read model with implementation/version, admission and validation report
   refs, strategy/risk spec identity, source hash, and reuse/adapt/author decision. Resolve lineage through the research
   boundary and render blockers before allowing submission.
2. **Owning surfaces:** `src/trader_research/experiments/implementations/` remains authoritative; Console contracts,
   repository/service/router and `apps/trader-console/src/features/backtest-authoring/` provide the projection.
3. **Verification:** exact reuse, adaptation, new authoring, missing admission, changed source hash, and incompatible
   risk-stack fixtures; API and browser tests assert that allowlists and preflight still fail closed.
4. **Docs/evidence:** update `src/trader_research/docs/{coding.md,experiments.md}`, Console usage/architecture, and
   Product State. Completion is a definition review showing complete lineage and actionable blocker text.

#### GAP-02-03 — Controlled Strategy Engineering qualification (L)

1. **Qualification flow:** pin the third-party model/provider profile, agent program, MCP catalogue, environment,
   budgets, and fixture inputs. Run exact reuse, adaptation, new authorship, failed admission, repair, interruption,
   and fresh-process restart cases; retain only public inputs, decisions, artifacts, and receipts.
2. **Owning surfaces:** use `src/trader_agents/` model/runtime and Strategy specialist boundaries plus existing
   `tests/cross_package/qualification/test_agentic_real_model_campaign.py`; do not modify qualification results into
   deterministic mocks.
3. **Verification:** mandatory gates for tool selection, authority denial, schema validity, admission independence,
   repeatability, and recovery. A failed gate remains a failed qualification with diagnostic evidence.
4. **Docs/evidence:** update `src/trader_agents/docs/{qualification.md,architecture.md}` and the linked IMP-07/
   Product State record. Completion requires a retained campaign report naming the exact profile and passing every
   mandatory phase.

#### GAP-02-04 — Hypothesis-to-candidate handoff (L)

1. **Scenario and flow:** compose a fixture from brief revision to catalogue search, compatibility decision, isolated
   Coding Workspace or maintained reuse, independent admission, strategy/risk specs, and a candidate record. Preserve
   every upstream artifact reference and stop on any authority or validation failure.
2. **Owning surfaces:** existing `src/trader_research/{governance,coding,experiments}/`, Strategy MCP tools, and a
   Console candidate read model; no direct agent access to persistence internals.
3. **Verification:** cross-package Postgres fixture, agent policy tests, browser review, and restart/idempotency cases.
   Assert the candidate cannot exist without admission and lineage.
4. **Docs/evidence:** update research coding/experiments docs, agent roles/tools/contracts, Console tutorial, and
   Product State. Completion is one reconstructable candidate record linked to its brief, source, admission, and specs.

### Backtest execution and review (UJ-03)

#### GAP-03-01 — Producer-backed Console execution qualification (existing TRD-273/TRD-274) (L)

1. **Contract and flow:** finish the real Console worker-to-`BacktestRunner` path using the persisted definition and
   exact evidence handoff; map queued, running, completed, partial, failed, stale-worker, outage, and
   reconciliation-required outcomes without inventing a second execution engine.
2. **Owning surfaces:** existing `src/trader_console_api/services/{backtest_worker.py,backtest_executor.py}` and
   execution repositories, `src/trader/` runner contracts, and the TRD-273/TRD-274 work items.
3. **Verification:** isolated Postgres worker fixtures with restart, duplicate submission, lost response, partial
   persistence, and reconciliation cases; broaden `tests/trader_console_api/services/test_backtest_worker.py` and the
   cross-package qualification suite.
4. **Docs/evidence:** update Console architecture/usage and `src/trader/docs/runtime.md`. Completion is a producer
   backed receipt for every lifecycle state and an explicit reconciliation result.

#### GAP-03-02 — Review statistical and robustness evidence (M)

1. **Contract and flow:** add a read model that joins Evaluation, multiple-testing, and Adversarial artifacts by run
   identity, protected-data role, claim, limitation, and status. The Console must label unavailable or incompatible
   evidence and never recompute producer statistics.
2. **Owning surfaces:** artifact producers in `src/trader_research/experiments/` and methodology services; Console
   repository/service/router and backtest-review/comparisons components for the projection.
3. **Verification:** complete, missing, incompatible protected-set, failed robustness, and comparison-excluded
   fixtures; API contract tests and browser review assertions cover claim-level blockers.
4. **Docs/evidence:** update `src/trader_research/docs/experiments.md`, Console usage, and Product State. Completion is
   a review screen where a claim can be traced to the exact evaluation/robustness artifact and limitation.

#### GAP-03-03 — Next-decision record (M)

1. **Contract and flow:** define a revisioned decision artifact with reject/refine/continue outcome, rationale,
   operator, source run, exact data/implementation/assumptions, evidence refs, and an optional bounded next experiment.
   Validate that referenced artifacts exist and belong to the same evidence chain.
2. **Owning surfaces:** research governance/artifact store and projection; Console command route/service/repository and
   backtest-review UI. Agents may propose a decision but the human-owned command records approval.
3. **Verification:** idempotent create, revision, incompatible reference, missing evidence, and authorization tests;
   browser test records and reopens a decision.
4. **Docs/evidence:** update governance/artifact docs, Console tutorial, and Product State. Completion is a durable
   decision receipt that a fresh process can use to locate the next experiment inputs.

#### GAP-03-04 — Research execution journey qualification (L)

1. **Scenario and flow:** compose the full data-to-definition-to-worker-to-review path with identity continuity,
   failure handling, Evaluation/Adversarial readout, and next-decision capture. Keep orchestration in application
   services and use isolated schemas for parallel qualification.
2. **Owning surfaces:** `tests/cross_package/qualification/` harness, existing Console worker/review boundaries, and
   canonical research/core execution services.
3. **Verification:** fresh Postgres schema per case, deterministic fixture dataset, browser/API/worker assertions,
   restart and mismatch scenarios, and evidence graph reconstruction from the final decision.
4. **Docs/evidence:** update `docs/product_state.md`, Console tutorial, experiment docs, and qualification docs.
   Completion is a single command producing a reviewable run, limitations, and next action from a fresh environment.

### Agent research journeys (UJ-04, UJ-07, UJ-08, UJ-09)

#### GAP-04-01 — Controlled third-party model qualification (existing IMP-05/IMP-07 context) (L)

1. **Qualification flow:** pin model/runtime/provider, prompts or public program inputs, tool catalogue version,
   environment, budgets, and fixture data; run Coordinator/Data/Strategy ambiguity, denial, recovery, interruption,
   and repeatability phases. Treat the current LFM failure and strict turn-schema failure as diagnostic states, not
   acceptance.
2. **Owning surfaces:** `src/trader_agents/{model_runtime,coordination,specialists,mcp,observability}/` and the
   existing IMP-05/IMP-07 records; MCP remains the only agent-facing platform boundary.
3. **Verification:** retain redacted public trajectory, canonical artifact receipts, policy decisions, and failure
   diagnostics; require every mandatory gate in the controlled qualification suite to pass.
4. **Docs/evidence:** update `src/trader_agents/docs/{qualification.md,roles_and_authority.md,architecture.md}` and
   Product State. Completion is a signed campaign result with exact identities and no unresolved mandatory gate.

#### GAP-04-02 — Console agent session workspace (L)

1. **Contract and flow:** project session identity, agenda, scope/budget, specialist progress, public events, evidence
   refs, terminal outcome, and operator actions. Add commands for interrupt, resume, cancel, and inspect with explicit
   authority; exclude prompts, hidden reasoning, and raw tool payloads.
2. **Owning surfaces:** public event/checkpoint projections in `src/trader_agents/observability` and checkpointing;
   Console read repository/service/router; new feature under `apps/trader-console/src/features/`.
3. **Verification:** API contract, authorization, redaction, fresh-process resume, lost-response, and concurrent
   session attribution tests; browser fixtures cover progress and operator actions.
4. **Docs/evidence:** update agent architecture, Console architecture/usage/tutorial, MCP contracts only if a new
   tool is exposed, and Product State. Completion is a browser-visible session that reconstructs its public evidence
   after restart without exposing hidden state.

#### GAP-04-03 — Agent-to-experiment handoff (L)

1. **Contract and flow:** extend Coordinator agenda and specialist returns with an Experiment Design proposal, explicit
   human approval, deterministic execution request, review artifact joins, and terminal decision. Keep each specialist's
   ownership and use MCP tool calls where registered.
2. **Owning surfaces:** `src/trader_agents/coordination/`, governance orchestration/proposals, MCP registration in
   `src/trader_mcp/`, and existing experiment services. Update allowlists only with an authority review.
3. **Verification:** policy/authority denial, proposal revision, approval, deterministic execution, timeout/retry,
   recovery, and evidence reconciliation tests across fresh Postgres schemas.
4. **Docs/evidence:** update `src/trader_agents/docs/{architecture.md,roles_and_authority.md}`,
   `src/trader_mcp/docs/{tools.md,contracts.md}`, research experiment docs, and Product State. Completion is a public
   trajectory ending in a reviewable experiment and decision receipt.

#### GAP-04-04 — Agent trajectory qualification (M)

1. **Contract and flow:** define a retained public trajectory fixture containing session/program/model/catalogue
   identities, redacted events, branch IDs, checkpoints, recovery markers, and artifact receipts. Persist only the
   approved public projection and redact at the sink.
2. **Owning surfaces:** `src/trader_agents/observability/`, checkpoint projection, and qualification support fixtures;
   no raw hidden scratchpad persistence.
3. **Verification:** fresh-process recovery, concurrent branch attribution, redaction, duplicate event, and sink
   outage cases; run the fixture under isolated schemas and compare the reconstructed evidence graph.
4. **Docs/evidence:** update agent observability/qualification docs and Product State. Completion is a queryable
   retained fixture that proves branch ownership and recovery without hidden messages.

### Paper operation (UJ-05)

#### GAP-05-01 — Paper-candidate admission record (L)

1. **Contract and flow:** define a human-owned admission artifact with candidate/evidence refs, exact strategy/risk/data
   versions, risk limits, broker/account scope, monitoring policy, decision, approver, timestamp, and expiry/revocation.
   Admission is a prerequisite for paper startup; agents and MCP cannot create or approve it.
2. **Owning surfaces:** governance/artifact store and projection in `src/trader_research/` or the agreed core boundary;
   Console command repository/service/router; core runtime consumes a read-only admission reference.
3. **Verification:** approval/rejection, expired/revoked, missing evidence, version mismatch, duplicate command, and
   unauthorized agent/MCP cases; Postgres schema compatibility and audit receipt tests.
4. **Docs/evidence:** update `src/trader/docs/{runtime.md,broker_and_portfolio.md}`, governance docs, Console usage,
   agent roles/tools, and Product State. Completion is a paper startup that refuses a candidate without a valid record.

#### GAP-05-02 — Console paper operations read model (L)

1. **Contract and flow:** map core/operator status into a read-only Console projection for heartbeat/health, freshness,
   session, orders, fills, positions, risk outcomes, reconciliation, and incidents. Preserve unavailable, stale, and
   incomplete states and timestamps; do not infer them from a green health check.
2. **Owning surfaces:** core payloads under `src/trader/`, projection/repository/service/router under
   `src/trader_console_api/`, and a paper-operations feature under `apps/trader-console/src/features/`.
3. **Verification:** contract mapping, stale feed, broker outage, mismatch, partial history, and reconciliation cases;
   API and browser tests use a deterministic runtime fixture.
4. **Docs/evidence:** update Console architecture/usage/tutorial, `src/trader/docs/runtime_hot_path_and_reconciliation.md`,
   and Product State. Completion is a read-only operational screen whose timestamps and source identities are visible.

#### GAP-05-03 — Authorized paper controls (L)

1. **Contract and flow:** add explicit operator-principal authorization for start, pause, stop, halt, and reconcile;
   route commands through a Console application service to existing core operator functions, record idempotent audit
   receipts, and return ambiguous outcomes for reconciliation. Keep MCP/agent tool policy read-only for broker state.
2. **Owning surfaces:** `src/trader_console_api/{contracts.py,services,routers,repositories}` and core operator
   primitives under `src/trader/`; UI controls follow the paper operations feature.
3. **Verification:** authority matrix, duplicate command, timeout, stale operator session, halt clearing, broker outage,
   and audit persistence tests. Add a boundary test proving agents/MCP cannot invoke mutation routes.
4. **Docs/evidence:** update Console API/architecture, `src/trader/docs/runtime.md`, `src/trader_mcp/docs/{tools.md,contracts.md}`
   if policy text changes, and Product State. Completion is an audited operator action with a deterministic failure path.

#### GAP-05-04 — Paper qualification campaign (L)

1. **Scenario and flow:** define a deterministic campaign matrix for startup recovery, stale data, broker mismatch,
   duplicate trigger, rejected order, restart, halt, and reconciliation. Use Alpaca paper only where the environment is
   explicitly available; local fixtures remain the repeatable gate.
2. **Owning surfaces:** runtime qualification helpers under `tests/cross_package/qualification/`, paper markers and
   support fixtures, isolated database/worktree setup, and the documented operator runbook.
3. **Verification:** every scenario records admission ID, runtime/session ID, broker responses, reconciliation result,
   risk action, and incident receipt. Parallel cases use separate schemas and do not share mutable broker fixtures.
4. **Docs/evidence:** update `src/trader/docs/{runtime.md,runtime_hot_path_and_reconciliation.md}` and Product State
   with thresholds, environment markers, and known limits. Completion is a retained campaign report that supports or
   rejects paper admission; it does not claim funded-live readiness.

### Definition of implementation-ready

Before a gap moves from Ready to In progress, its Notion work item must link this playbook and name the applicable
contract owner, dependency gate, test module or fixture, documentation authority, and completion evidence. During
implementation, the work item records the actual module paths and any contract decision that changes the playbook. It
can move to Done only after focused tests, required cross-package or external qualification, documentation checks, and
the evidence artifact are linked. This keeps a “partial” status measurable: the remaining work is the unchecked steps
above, not an unbounded feeling that the feature is incomplete.

## Candidate functional requirements

Each requirement describes observable behavior and names the journey it supports. The exact thresholds, instruments,
brokers, timeframes, and first-release scope remain open until reviewed.

### FR-01 — Data identity and provenance

Trader identifies each data source, instrument, timeframe, time window, ingestion operation, and resulting dataset or
snapshot so a research result can be traced to the data actually used. Supports UJ-01, UJ-02, UJ-03, UJ-06, UJ-07, and UJ-08.

### FR-02 — Data exploration and fitness

The Console exposes bounded data discovery, visualization, coverage, quality, and missing-data states; Jared can judge
fitness for a question before a strategy or backtest uses the data. Supports UJ-01, UJ-03, UJ-06, and UJ-07.

### FR-03 — Versioned strategy construction

Trader accepts a hypothesis, strategy logic, parameters, and risk controls as inspectable versioned inputs, validates
their interfaces, and reports failures before execution. Supports UJ-02, UJ-07, and UJ-08.

### FR-04 — Reproducible backtest execution

A backtest fixes its strategy and risk versions, data scope, initial state, costs, execution assumptions, and code
identity; repeating the same inputs yields the same deterministic result or an explicit environmental difference.
Supports UJ-03, UJ-08, and UJ-09.

### FR-05 — Backtest evidence and limits

Trader records decisions, orders, fills, positions, risk actions, accounting, warnings, and incomplete states so the
Console can show what a run supports and what simulation cannot establish. Supports UJ-03, UJ-08, and UJ-09.

### FR-06 — Fair comparison and inference

The Console and research services compare compatible runs, identify exclusions, and present appropriate statistical
significance, multiple-testing, and robustness evidence before a stronger claim is made. Supports UJ-03, UJ-08, and UJ-09.

### FR-07 — Bounded agent research

Jared can give the agent system an objective, scope, budget, and authority envelope; agents can propose and conduct
permitted research steps, return evidence, and ask for direction when the next step exceeds that envelope. Supports
UJ-04, UJ-07, and UJ-08.

### FR-08 — Governed MCP access

MCP exposes typed, discoverable research capabilities with explicit ownership, side effects, input bounds, output
envelopes, errors, and artifact references. Agent authority is checked before a tool acts. Supports UJ-04, UJ-07, and UJ-08.

### FR-09 — Research trace and recoverability

Agent and platform actions preserve public decisions, exact artifact lineage, and enough bounded state to inspect or
resume interrupted research without repeating accepted mutations or persisting hidden reasoning. Supports UJ-04 and UJ-09.

### FR-10 — Console research workflow

The Console lets Jared move from data to strategy definition, backtest submission, run review, comparison, and a
documented next decision without losing scope or evidence links. Supports UJ-01, UJ-02, UJ-03, UJ-04, UJ-08, and UJ-09.

### FR-11 — Controlled deployment

Trader requires an explicit human decision, pinned strategy/risk configuration, qualification evidence, and declared
limits before moving a candidate into paper or eventual real trading. Research agents do not directly place orders or
change broker state. Supports UJ-05.

### FR-12 — Trading observability and intervention

The Console shows operational health, broker reconciliation, orders, fills, positions, risk events, and strategy state;
Jared can inspect, pause, stop, and respond to failures through authorized controls. Supports UJ-05.

### FR-13 — Auditability across the lifecycle

Data, strategy, experiment, agent, deployment, and trading records retain stable identity, actor or requester, inputs,
decisions, timestamps, and evidence references sufficient to reconstruct an outcome. Supports UJ-01 through UJ-09.

### FR-14 — Demonstrable quantitative development evidence

Trader can present reproducible examples of quantitative reasoning and engineering work, including hypotheses,
implementation choices, tests, results, limitations, and revisions, without relying on an unsupported profitability
claim. This serves Jared's professional goal across UJ-02 through UJ-09.

## Questions for joint refinement

1. Which data-scope fields and evidence must always be fixed before an instrument-agnostic UJ-06 run can begin?
2. How much of strategy ideation and experiment design should agents do autonomously inside an approved envelope?
3. Which claims must be statistically tested, and what level of robustness evidence is sufficient to advance a
   candidate rather than merely explore it?
4. What form of professional evidence would be most useful to you: reproducible case studies, a public portfolio,
   demonstrations, or something else?

The intent is ready for revision, not acceptance. We should refine the journeys and requirements against Jared's
answers and real examples, then record an explicit human review of the resulting version.
