# Trader Product Intent

This is a human-review draft of Jared's 2 October 2026 vision. The journeys and requirements are an assistant
interpretation to refine together. They are desired product behavior, not claims about what the current repository
already delivers. [Product State](product_state.md) records implemented and qualified
behavior. The synchronized Notion copy is [Trader Product
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

## Candidate user journeys

The UJ records below are product features expressed as user journeys. Each feature defines an actor, trigger, behavior,
outcome, failure path, and evidence needed to judge whether the product serves the human purpose. Delivery slices implement
these features, but their planning records and status do not redefine the product intent.

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

### Repository audit — 5 October 2026

**Implemented:** `trader_research.data` provides symbol discovery, inventory manifests, quality reports, bounded
loading, matching canonical research snapshots, and the bar-content `replay_data_identity`. The Console `/data`
boundary resolves the matching Data manifest and quality report, including provider/source policy, coverage, findings,
warnings, provenance, and explicit complete, partial, stale, warning, empty, and unavailable states. Saved scopes
reopen with immutable evidence references; authoring carries the exact scope, provider policy, manifest, and quality
identity without re-entry; research backtest preflight revalidates replay identity before invoking `BacktestRunner`.
The integrated API and browser qualification now proves selection, evidence review, saved-scope handoff, authoring,
execution submission, review, and stale/mismatch blockers against isolated persistence.

**Remaining behavior:** bounded comparison of source or window alternatives is still a separate UJ-01 capability. The
successful data-to-review journey is qualified, while broader worker failure and ambiguous-outcome campaigns remain in
the UJ-03 execution boundary.

| Acceptance point | Evidence coverage | Repository evidence |
| --- | --- | --- |
| Discover bounded candidates | Implemented through Data/MCP and the Console evidence projection | `src/trader_research/data/catalog.py`, `src/trader_mcp/runtime/server.py`, `apps/trader-console/src/features/market-data/market-data-workspace.tsx` |
| Inspect per-item coverage and quality | Implemented in Data and rendered in the Console with explicit state/warning variants | `src/trader_research/data/{inventory.py,quality.py}`, `src/trader_console_api/repositories/resources.py` |
| Preserve matching Data evidence | Implemented in Data/MCP and the Console saved-scope/evidence projections | `src/trader_research/data/evidence.py`, `src/trader_mcp/docs/tools.md`, `src/trader_console_api/repositories/resources.py` |
| Carry the same scope into authoring | Implemented and integrated-qualified | `apps/trader-console/src/features/backtest-authoring/backtest-authoring-workspace.tsx`, `src/trader_console_api/contracts.py`, `tests/cross_package/workflows/test_console_data_to_backtest.py` |
| Verify replay data identity | Implemented and enforced before runner invocation | `src/trader_research/foundation/replay_identity.py`, `src/trader_research/experiments/backtests/execution.py` |
| Qualify the full human workflow | Integrated API/browser qualification covers success and stale/mismatch blockers | `tests/cross_package/workflows/test_console_data_to_backtest.py`, `apps/trader-console/tests/e2e/data-to-backtest.spec.ts` |

### Capability evidence and remaining behavior

- **GAP-06-01 — Console data evidence:** delivered through the producer-owned `console_read.data_scope_evidence`
  projection and `/data` states for coverage, quality, provider policy, provenance, and warnings.
- **GAP-06-02 — Exact scope handoff:** delivered through immutable saved-scope and authoring references that reject
  stale, unavailable, changed, or policy-mismatched evidence.
- **GAP-06-03 — Replay data identity:** delivered through the canonical bar-content digest, source semantics, and
  fail-closed preflight receipt.
- **GAP-06-04 — End-to-end qualification:** delivered through the isolated API/browser data-to-backtest fixture;
  broader worker failure campaigns remain part of UJ-03.

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

### Repository audit — 5 October 2026

**Implemented:** `trader_research.data` supports multi-asset symbol discovery, inventory, quality summarization,
bounded loading, revalidation, canonical research snapshots, and explicit catalogue/provider capability states. The
MCP catalogue exposes those operations with bounded scope and loading policy. The Console `/data` route now resolves
the matching Data manifest and quality report, renders coverage, completeness, findings, warnings, provider/source
policy, provenance, and explicit unavailable/partial/stale states, and saves an exact scope that can be reopened and
carried into authoring. The integrated data-to-backtest fixture proves the evidence identity survives authoring and
execution submission without re-entry.

**Remaining behavior:** the researcher still needs a bounded comparison of source or window alternatives, with each
alternative retaining its own quality and provenance limitations. This is the current UJ-01 next capability; the
discovery/load distinction is already explicit in the Data, MCP, and Console contracts.

| Acceptance point | Evidence coverage | Repository evidence |
| --- | --- | --- |
| Discover bounded datasets | Implemented in Data/MCP and the Console evidence projection | `src/trader_research/data/catalog.py`, `src/trader_mcp/docs/tools.md`, `src/trader_console_api/repositories/resources.py` |
| Inspect bars and bounded windows | Implemented and browser-tested | `apps/trader-console/src/features/market-data/market-data-workspace.tsx`, `apps/trader-console/tests/e2e/market-data.spec.ts` |
| Explain quality and provenance | Implemented in Data and rendered in the Console | `src/trader_research/data/{quality.py,evidence.py}`, `src/trader_console_api/repositories/resources.py` |
| Compare alternatives | Open bounded comparison capability | `src/trader_console_api/docs/usage.md`, `apps/trader-console/src/features/market-data/` |
| Preserve and reuse an exact snapshot | Implemented through saved-scope persistence and authoring handoff | `src/trader_research/data/evidence.py`, `src/trader_console_api/repositories/saved_data_scopes.py`, `apps/trader-console/src/features/market-data` |

### Capability evidence and remaining behavior

- **GAP-01-01 / GAP-06-01 — Data fitness readout:** delivered through the Console's matching quality, completeness,
  provider/source, provenance, and warning projection.
- **GAP-01-02 — Saved data scope:** delivered through immutable save/reopen and explicit active, stale, unavailable,
  and superseded evidence states.
- **GAP-01-03 — Data alternative comparison:** remains the next UJ-01 capability; alternatives must retain independent
  scope, coverage, quality, provenance, and compatibility findings.
- **GAP-01-04 — Discovery completeness contract:** delivered; catalogue completeness and discover-only/load-capable
  provider states remain distinct in Data, MCP, and Console responses.

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

### Repository audit — 5 October 2026

**Implemented:** `trader_standard` supplies maintained indicators, signals, strategies, and risk managers. The research
Experiments context provides bounded implementation search, exact resolution, comparison, source-free result rows,
independent validation/admission, immutable strategy and risk-stack specifications, and prediction-binding revalidation.
The Coding context defines an ephemeral, digest-pinned workspace with bounded checks and cleanup. The Strategy
Engineering agent is catalogue-first and can reuse, adapt, or author through MCP; it never self-approves admission. The
Console publishes a typed strategy/risk catalogue and performs side-effect-free parameter, coverage, warmup, and budget
preflight.

**Partial:** the Console authoring flow still starts from allowlisted profiles and parameters and does not yet own the
hypothesis card or complete hypothesis-to-candidate handoff. The authoring projection now carries implementation/version,
validation and admission reports, strategy/risk specification identity, source hash, provenance, and the explicit
reuse/adapt/author decision; preflight blocks missing or incompatible lineage. The agentic Strategy Engineering loop
is implemented but controlled third-party-model qualification remains outstanding, and the first agentic slice stops
at an admitted strategy/risk candidate rather than designing or executing an experiment.

| Acceptance point | Evidence coverage | Repository evidence |
| --- | --- | --- |
| Hypothesis and falsifier record | Partial in Experiment Design contracts; no complete Console authoring path | `src/trader_research/governance`, `src/trader_agents/docs/roles_and_authority.md` |
| Catalogue search and compatibility | Implemented and focused-tested | `src/trader_research/experiments/implementations/catalog.py`, `tests/trader_research/experiments/test_implementation_catalog.py` |
| Isolated authoring and admission | Implemented and controlled at deterministic boundary | `src/trader_research/docs/coding.md`, `src/trader_research/experiments/implementations` |
| Immutable strategy/risk specs | Implemented and controlled | `src/trader_research/experiments/specifications/strategy.py`, `src/trader_research/experiments/specifications/risk.py` |
| Human-facing lineage and agent qualification | Lineage implemented; controlled model qualification remains open | `apps/trader-console/src/features/backtest-authoring`, `src/trader_console_api/services/implementation_lineage.py`, `src/trader_agents/docs/qualification.md` |

### Capability evidence and remaining behavior

- **GAP-02-01 — Hypothesis and experiment brief:** settle the Experiment Design boundary and persist a typed,
  falsifiable brief that can be handed to Data, Strategy, and later Evaluation without losing the intended decision.
- **GAP-02-02 — Console implementation lineage:** delivered through the typed authoring projection, source/admission
  lineage checks, explicit reuse/adapt/author choice, and fail-closed preflight blockers.
- **GAP-02-03 — Controlled Strategy Engineering qualification:** execute the real MCP/model matrix against the pinned
  third-party model profile, including exact reuse, adaptation, new authorship, failed admission, repair, interruption,
  and restart evidence. Existing IMP-07 and the agentic implementation slice are design and implementation context, not controlled acceptance.
- **GAP-02-04 — Hypothesis-to-candidate handoff:** qualify one integrated path from a brief through catalogue
  comparison, isolated authoring or reuse, admission, and a reviewable candidate record.

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

### Repository audit — 5 October 2026

**Implemented:** the Experiments context validates immutable implementation, strategy, risk, and backtest
specifications, executes canonical Postgres runs, persists orders/fills/positions/metrics/warnings/provenance, and
supports deterministic grid/random optimisation, sealed holdout, Evaluation, and optimisation-specific Adversarial
reports. Core replay uses an internal deterministic paper broker and records cycle evidence. Console APIs expose run
scope, assumptions, performance, curves, trades, positions, risk composition and decisions, lifecycle, provenance,
indicator/signal evidence, and comparison eligibility. The Console has single-run review, saved comparison views,
durable definition/execution records, a local worker, bounded retries, and explicit ambiguous-outcome reconciliation.

**Partial:** the worker-to-canonical-BacktestRunner path is implemented and the successful execution-to-review path is
qualified against a fresh isolated database. Broader failed, ambiguous, outage, stale-worker, and reconciliation
campaigns remain open. Console review provides typed Evaluation/multiple-testing/Adversarial evidence and a first-class
human next-decision command/read path, but complete statistical inference, general robustness attacks, and walk-forward
optimization remain absent. Data scope handoff and replay-bar identity are now enforced before execution.

| Acceptance point | Evidence coverage | Repository evidence |
| --- | --- | --- |
| Immutable run inputs and deterministic execution | Implemented and controlled in research/core | `src/trader_research/docs/experiments.md`, `src/trader/docs/runtime.md` |
| Durable Console submission/lifecycle | Implemented; successful producer path qualified | `src/trader_console_api/docs/usage.md`, `src/trader_console_api/services/backtest_worker.py`, `tests/cross_package/workflows/test_console_execution_to_review.py` |
| Rich single-run review | Implemented and browser-qualified for published evidence | `apps/trader-console/src/features/backtest-review/backtest-review-workspace.tsx` |
| Compatible comparison | Implemented with explicit exclusions | `apps/trader-console/src/features/comparisons`, `src/trader_console_api/docs/usage.md` |
| Inference, robustness, and next decision | Review evidence and next-decision contracts implemented; independent inference/robustness producers remain partial | `src/trader_console_api/contracts.py`, `src/trader_research/governance/next_decisions.py`, `docs/product_state.md` capability matrix and known limits |

### Capability evidence and remaining behavior

- **GAP-03-01 — Producer-backed Console execution qualification:** finish the real worker-to-BacktestRunner path and
  qualify restart, stale-worker, partial, failed, outage, and reconciliation-required states against isolated Postgres.
  This narrows the existing TRD-273/TRD-274 work rather than replacing it.
- **GAP-03-02 — Review statistical and robustness evidence:** delivered through the typed producer-owned review
  projection, including claim scope, protected-data roles, limitations, and missing/incompatible/blocked states.
- **GAP-03-03 — Next-decision record:** delivered through the human-principal-only revisioned reject/refine/continue
  artifact, exact evidence references, bounded successor inputs, and fresh-process reopen path.
- **GAP-03-04 — Research execution journey qualification:** delivered for the successful data-to-definition-to-worker-
  to-review path with scope identity continuity. Broader worker failure and reconciliation campaigns remain under
  GAP-03-01.

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

### Repository audit — 5 October 2026

**Implemented:** `trader_agents` has typed session, agenda, delegation, checkpoint, and observability contracts; a
model-backed Coordinator graph; deterministic authority and budget policy; public redacted events; PostgreSQL
checkpoints; start/resume/inspect/cancel lifecycle; and focused security, recovery, isolation, interruption, and
evidence-reconciliation tests. The MCP server exposes governed research tools and prohibits broker mutation, raw SQL,
and hidden state.

**Partial:** the current LFM profile failed the material-ambiguity coordinator choice gate and a later diagnostic run
failed strict turn-schema validation before MCP calls. Controlled behavioral qualification has therefore not passed.
The runtime is CLI-oriented; the Console has no session agenda, public-event, checkpoint, interrupt, or terminal-decision
workspace. These are session-governance gaps, separate from the specialist and experiment journeys below.

| Acceptance point | Evidence coverage | Repository evidence |
| --- | --- | --- |
| Session identity, authority, and budgets | Implemented and focused-tested | `src/trader_agents/docs/architecture.md`, `tests/trader_agents/contracts_state` |
| Agenda, delegation, and lifecycle controls | Implemented in runtime; human Console surface absent | `src/trader_agents/coordination`, `src/trader_agents/application_runtime` |
| Public trace and checkpoint recovery | Implemented and focused-tested | `src/trader_agents/observability`, `src/trader_agents/checkpointing` |
| Controlled model qualification | Failed gate / not accepted | `src/trader_agents/docs/qualification.md`, `tests/cross_package/qualification/test_agentic_real_model_campaign.py` |
| Console intervention and terminal review | Absent | `apps/trader-console/src/features`, `docs/product_state.md` |

### Capability evidence and remaining behavior

- **GAP-04-01 — Controlled third-party model qualification:** complete the pinned model/provider/tool/environment
  campaign for Coordinator, Data, and Strategy, including ambiguity, denial, recovery, and repeatability gates. The
  result is controlled evidence only when every mandatory phase passes. Existing IMP-05 and IMP-07 provide campaign
  context rather than acceptance.
- **GAP-04-02 — Console agent session workspace:** expose session identity, agenda, progress, public events, evidence
  references, operator interrupts, resume/cancel actions, and terminal decisions without exposing hidden prompts or
  reasoning.
- **GAP-04-04 — Agent trajectory qualification:** delivered through the retained public trajectory sink and verifier,
  including model/program/catalogue identity, concurrent branch attribution, redaction, duplicate/sink-failure
  handling, fresh-process recovery, and terminal decision lineage. Durable product event persistence remains a separate
  future boundary.

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

### Repository audit — 5 October 2026

**Implemented:** Data Research and Strategy Engineering specialist loops, role-scoped MCP clients, catalogue-first
strategy reuse/adaptation/authorship, isolated Coding Workspace boundaries, independent admission, and canonical handoff
contracts exist and are focused-tested. The first slice reaches exact Data readiness and an admitted strategy/risk
candidate.

**Partial:** controlled third-party model qualification remains failed; the Console does not expose branch progress and
handoffs; and the current slice does not continue into Experiment Design or independent evaluation. The retained public
trajectory fixture now preserves concurrent branch attribution and fresh-process recovery, while Data evidence and
implementation lineage survive the human Console handoff through their delivered projections.

### Capability evidence and remaining behavior

- **GAP-02-03 — Controlled Strategy Engineering qualification:** qualify exact reuse, adaptation, new authorship,
  failed admission, repair, interruption, and restart against the pinned model/tool environment.
- **GAP-04-01 — Controlled third-party model qualification:** qualify Coordinator/Data/Strategy behavior and authority
  gates as one controlled campaign.
- **GAP-04-04 — Agent trajectory qualification:** delivered through the retained public trajectory fixture and verifier;
  branch identity and public handoff evidence remain queryable after recovery.
- **GAP-06-01/02 and GAP-02-02:** delivered shared boundaries preserve qualified Data evidence, exact scope, and
  implementation/admission lineage across the human Console handoff; they are not additional specialist gaps.

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

### Repository audit — 5 October 2026

**Implemented:** deterministic Experiment Design proposal services, canonical experiment specifications, backtest
execution, evaluation/optimisation artifacts, and robustness-related artifact contracts exist in research/core.

**Absent or partial:** no model-backed Experiment Design graph is in the clean runtime; the current agent slice does not
execute experiments, request independent Evaluation/Robustness work, or expose the full lifecycle in the Console. The
successful Console worker-to-review path, typed review evidence, next-decision record, and replay-bar identity are
qualified as separate deterministic boundaries; broader worker failure campaigns and agent-to-experiment integration
remain open.

### Capability evidence and remaining behavior

- **GAP-04-03 — Agent-to-experiment handoff:** add the approved proposal, deterministic execution request, evidence joins,
  and terminal outcome while preserving specialist ownership.
- **GAP-03-01:** qualify the remaining stale-worker, partial, failed, outage, and reconciliation-required worker
  outcomes against isolated Postgres.
- **GAP-03-02:** delivered the Evaluation, multiple-testing, and Adversarial projection with protected-data roles and
  claim blockers; independent producer maturity remains explicit.
- **GAP-03-04:** delivered the successful data-to-definition-to-worker-to-review qualification path.
- **GAP-06-03:** delivered the replay data identity contract and fail-closed enforcement before runner invocation.

## Detailed story audit — UJ-09 / US-09-01

**User story:** As a researcher, I can review an agent's evidence and record the next action, so automation informs my
research without silently becoming the decision-maker.

### Acceptance criteria

- The review surface resolves canonical artifacts and public trajectory evidence by exact session, branch, run, and
  evidence identity.
- Claims show uncertainty, limitations, comparison exclusions, statistical or robustness status, and unresolved
  blockers; a model conclusion is not presented as an independent quality verdict.
- Jared can reject, refine, continue, or request a bounded successor experiment and must record the rationale and exact
  evidence refs.
- The decision is append-only, attributable, resumable from a fresh process, and sufficient to reconstruct why the next
  action was chosen.

### Repository audit — 5 October 2026

**Implemented:** rich backtest review, compatible comparison exclusions, canonical artifact refs, producer-owned
Evaluation/multiple-testing/Adversarial readouts, human next-decision records, retained public trajectory evidence, and
bounded checkpoint recovery now exist as inspectable runtime slices.

**Partial:** the Console does not yet provide a unified agent evidence workspace, and independent review producer
maturity remains limited to the available artifacts. The next-decision contract and retained trajectory projection now
preserve exact refs, limitations, actor/time, bounded successor inputs, branch identity, and fresh-process lineage.

### Capability evidence and remaining behavior

- **GAP-03-02 — Review statistical and robustness evidence:** delivered as a typed review projection that preserves
  protected-data roles, claim scope, limitations, and missing/incompatible/blocked states.
- **GAP-03-03 — Next-decision record:** delivered as a human-owned revisioned artifact with exact evidence-chain refs
  and bounded successor inputs.
- **GAP-04-02 — Console agent session workspace:** remains the next human-surface capability for session identity,
  progress, public events, evidence refs, and operator actions.
- **GAP-04-04 — Agent trajectory qualification:** delivered; the retained public projection reconstructs branch identity
  and recovery without exposing hidden state.

## Agent-journey gap allocation

| Journey | Primary human decision | Current capability slices |
| --- | --- | --- |
| UJ-04 — Govern a delegated research session | May this bounded session run, continue, pause, resume, or stop? | GAP-04-01 and GAP-04-02 remain; GAP-04-04 trajectory evidence is delivered. |
| UJ-07 — Delegate specialist investigation | Are the requested data and strategy inputs qualified enough to design an experiment? | GAP-02-03, GAP-04-01, and GAP-04-02 remain; GAP-04-04, GAP-06-01/02, and GAP-02-02 provide delivered shared evidence. |
| UJ-08 — Run a governed agent-directed experiment | Should this approved protocol be executed and what evidence did it produce? | GAP-04-03 and GAP-03-01 remain; GAP-03-02/03/04 and GAP-06-03 provide delivered execution/review boundaries. |
| UJ-09 — Review agent evidence and choose the next action | What does the evidence support, and what should happen next? | GAP-04-02 and independent review maturity remain; GAP-03-02/03/04 and GAP-04-04 provide delivered evidence. |

## Agent-journey gap diagnosis and next-step orientation — 4 October 2026

The four product features share runtime components, but they do not share the same acceptance claim. A passing
specialist contract does not prove a governed session is usable; a deterministic protocol service does not prove an
agent can propose and hand it off; and a stored artifact does not prove that a human can review it and choose the next
action. The diagnosis therefore separates implementation, qualification, and human-surface gaps. The next-step notes below
describe the capability needed to qualify these features; they do not redefine the features or replace component work.

### Session-governance gap diagnosis (UJ-04)

**Baseline:** the runtime already creates pinned sessions, validates model/program/tool identities, proposes and
validates agendas, checkpoints state, emits redacted public events, supports inspect/resume/cancel, and has focused
security, interruption, recovery, and isolation tests. `tests/cross_package/qualification/test_agentic_real_model_campaign.py`
shows that the real-model gate is still failed, while the Console has no session workspace.

**Gaps to fill:**

| Gap | Diagnosis | Next product step | Closure evidence |
| --- | --- | --- | --- |
| Controlled real-model behavior | Qualification gap, not a missing deterministic contract. The active LFM profile failed material-ambiguity selection and strict turn-schema diagnostics. | Continue existing IMP-05 and GAP-04-01. Freeze model/provider, program, catalogue, environment, and fixture; repair or replace the model/profile through the qualification process; rerun ambiguity, denial, recovery, interruption, and repeatability phases. | A retained campaign result passes every mandatory gate with exact identities; until then the capability remains unqualified. |
| Human session control surface | Product-surface gap. Runtime methods exist, but no typed Console read/command projection exposes agenda, progress, public events, checkpoint state, or operator controls. | GAP-04-02 owns the public projection and Console router/service/repository/UI. Existing Console session discovery and exact-session-link work is supporting context; it must consume the agent projection rather than invent one. | API and browser fixture can inspect, interrupt, resume, cancel, and show terminal state without prompts, hidden reasoning, or raw payloads. |
| Retained public trajectory | Delivered qualification/evidence boundary. Public event and checkpoint projections are retained and verified with branch identity and fresh-process recovery. | The retained trajectory sink/verifier covers model/program/catalogue identity, redaction, duplicate/sink-failure handling, concurrent branches, recovery, and terminal lineage. | Queryable fixture reconstructs session lifecycle and branch ownership after restart while excluding hidden state; durable product event persistence remains separate. |
| Feature acceptance and implementation gap | No single acceptance item proves the human feature across those components. | The feature-qualification slice qualifies UJ-04 with an isolated Postgres/API/browser journey and records the model gate status. | One report covers create → inspect → interrupt/resume → cancel/terminal outcome, with explicit qualification exclusions. |

**Dependency order:** the public trajectory contract is qualified; next expose it through the Console session workspace,
then resolve the model gate and complete the UJ-04 feature-qualification slice. The UI can be developed against
deterministic fixtures while the real-model gate is blocked, but the journey cannot be described as controlled until the
campaign passes.

### Specialist-investigation gap diagnosis (UJ-07)

**Baseline:** Data Research and Strategy Engineering loops are implemented with role-scoped MCP clients, typed
delegations, catalogue-first reuse/adaptation/authorship, isolated Coding Workspace boundaries, independent admission,
and canonical handoffs. The guarded end-to-end fixture already exercises Data loading, adaptation, admission, and
synthesis, but the model campaign is blocked by the Coordinator gate and the Console does not show branch progress or
handoffs.

**Gaps to fill:**

| Gap | Diagnosis | Next product step | Closure evidence |
| --- | --- | --- | --- |
| Data and Strategy model qualification | Shared external qualification gap. IMP-06 is explicitly blocked by IMP-05; GAP-02-03 covers Strategy but not the shared Coordinator/Data gate. | Resolve GAP-04-01/IMP-05 first, then run IMP-06 and GAP-02-03 against one frozen profile and isolated MCP/Postgres/coding environment. | Campaign retains ready, backfill, out-of-envelope, unfit, reuse, adaptation, authorship, failed-admission, repair, interruption, and restart outcomes. |
| Concurrent branch and handoff proof | The retained trajectory fixture now proves branch attribution and recovery; specialist handoff acceptance remains a separate coordinator behavior. | Use the delivered retained projection when extending the guarded specialist fixture for disjoint branches, digest mismatch, lost responses, and fresh-process resume. | Coordinator accepts only matching owner/producer/requester/actor/type/digest and preserves separate branch evidence. |
| Human visibility and lineage | Console gap, shared with data and strategy journeys. A specialist return exists as an artifact, but the human cannot inspect its branch, blockers, admission, or exact Data lineage in one place. | GAP-04-02 provides the session projection; GAP-02-02 provides implementation/admission lineage; GAP-06-01/02 provide Data evidence and scope continuity. | Console review shows branch status and exact artifact refs, with actionable partial/blocked states and no silent scope changes. |
| Feature acceptance and implementation gap | Existing tests prove components, not a stable human outcome under the accepted qualification profile. | The feature-qualification slice qualifies UJ-07 with one pinned session and Data/Strategy branches, including concurrent attribution and recovery. | A retained handoff graph distinguishes ready, partial, blocked, reused, adapted, authored, and failed-admission results. |

**Dependency order:** unblock Coordinator qualification; run Data and Strategy qualification together; expose the
delivered public trajectory and lineage through the Console; then complete the UJ-07 feature-qualification slice. UJ-07
does not require Experiment Design or Evaluation to decide whether the specialist inputs are ready, but it must return
explicit blockers when those later stages are unavailable.

### Agent-directed experiment gap diagnosis (UJ-08)

**Baseline:** deterministic Experiment Design proposal/approval contracts, canonical specifications, workflow registration,
backtest execution, parameter-optimisation Evaluation, and parameter-optimisation Adversarial tools exist. The clean
agent runtime has no model-backed Experiment Design graph; broader Evaluation and Robustness graphs/tools are absent or
planned; and the successful Console worker/review and replay-identity paths are qualified while broader worker failure
and agent-to-experiment handoff remain incomplete.

**Gaps to fill:**

| Gap | Diagnosis | Next product step | Closure evidence |
| --- | --- | --- | --- |
| Experiment Design authority and graph | Architecture and implementation gap. The design is still in review; deterministic proposal services are not a model-backed specialist. | Complete the canonical `plans/agent_designs/experiment_design.md` review and its existing architecture decision; implement only the approved proposal loop and preserve human approval. GAP-04-03 owns the first bounded handoff. | A typed proposal contains claims, assumptions, protected-data roles, budgets, stage gates, and exact inputs; approval changes status without changing design identity. |
| Long-running execution boundary | Open platform decision. TRD-105 still leaves synchronous bounded calls versus MCP jobs unresolved, while this journey requires durable queued/running/partial/failed/reconciliation receipts. | Resolve TRD-105 before claiming general agent-directed execution; align GAP-04-03 with GAP-03-01 worker lifecycle and the chosen job contract. | A fresh process can inspect and recover a long operation without duplicate mutation; lifecycle and ambiguous-outcome receipts are durable. |
| Exact replay identity | Delivered core/research boundary. Qualified manifests carry bar-content digest and source semantics, and execution revalidates them before loading the runner. | Use the delivered identity receipt as an input to GAP-03-01 and the agent handoff. | Execution refuses changed bars/source or records the permitted environmental difference explicitly. |
| Independent Evaluation and Robustness | Producer capability gap, separate from the delivered GAP-03-02 Console projection. Parameter-optimisation reports exist, but general model-backed Evaluation and Robustness/WFO paths remain absent or under design. | Progress the independent Evaluation and Robustness producer paths; preserve absence/limitations in the existing projection. | Independent artifacts identify claim scope, protected data, limitations, negative findings, and dissent; no Coordinator verdict substitutes for either authority. |
| Agent-to-experiment integration | Cross-boundary gap. GAP-04-03 must join approved Data/Strategy returns to proposal, execution, review, and terminal outcome without granting the Coordinator experiment or quality authority. | Implement GAP-04-03 after the upstream model and protocol/job decisions; qualify denial, mismatch, retry, recovery, and approval paths. | Public trajectory ends in a reproducible experiment/evidence bundle or typed blocker, with canonical refs at every handoff. |
| Feature acceptance and implementation gap | No single acceptance item currently proves the complete agent-to-experiment path. | The feature-qualification slice qualifies UJ-08 by composing the remaining GAP-04-03/GAP-03-01 boundaries with delivered GAP-03-02/03/04 and GAP-06-03 evidence. | Isolated workflow fixture proves proposal → approval → job/run → independent evidence or blocker → terminal outcome. |

**Dependency order:** settle Experiment Design authority and TRD-105; resolve replay identity; implement the bounded
agent handoff; make independent review artifacts available; then complete the UJ-08 feature-qualification slice. Until independent Evaluation/Robustness
artifacts exist, the journey may prove deterministic execution and explicit absence, but cannot support a full research
quality claim.

### Evidence-review gap diagnosis (UJ-09)

**Baseline:** canonical artifact references, producer-owned review evidence, human next decisions, rich backtest review,
comparison exclusions, retained public trajectory evidence, and bounded checkpoint recovery exist as inspectable slices.
The Console has no unified agent evidence graph; independent review producer maturity and the agent session workspace
remain open.

**Gaps to fill:**

| Gap | Diagnosis | Next product step | Closure evidence |
| --- | --- | --- | --- |
| Evidence graph projection | Human-surface gap. Producer evidence and retained trajectory are queryable, but the reviewer needs one exact session/branch/run graph with claim scope and limitations. | GAP-04-02 supplies the session projection and Console workspace; keep producer calculations and the delivered trajectory verifier outside the Console. | API and UI resolve exact refs and preserve missing, incompatible, negative, and incomplete states with claim-level blockers. |
| Next-decision artifact | Delivered product contract. The human can record reject/refine/continue and bounded successor inputs against exact run/data/implementation/assumption/evidence refs. | Use the delivered revisioned command/read path as the input to the unified agent evidence workspace. | A fresh process reopens the decision, its rationale, actor/time, limitations, and bounded successor experiment. |
| Independent review boundary | Maturity dependency. A model conclusion or Coordinator receipt is not the Evaluation Agent's independent research-quality verdict. | Complete the existing Evaluation and Robustness architecture records and their producer paths before presenting stronger claims; GAP-03-02 must label unavailable maturity. | Review distinguishes agent recommendation, deterministic diagnostics, independent Evaluation, Robustness findings, and human decision. |
| Feature acceptance and implementation gap | The component contracts are delivered; no single human-surface acceptance item yet proves review after session recovery and evidence gaps. | The feature-qualification slice should compose the delivered GAP-03-02/03/04 and GAP-04-04 boundaries with GAP-04-02. | Browser/API fixture opens the evidence graph, records reject/refine/continue or successor, and reconstructs the decision after restart. |

**Dependency order:** expose the agent session projection through GAP-04-02; then compose the delivered review evidence,
next-decision, execution, and trajectory boundaries into the UJ-09 feature-qualification slice. Independent review
producer maturity remains its own gate. UJ-09 can be useful before all review agents exist if the UI explicitly labels
missing evidence; it must never convert absence into a positive verdict.

### Cross-journey delivery sequence

1. **Unblock qualification:** resolve the Coordinator model gate, then rerun Data and Strategy specialist campaigns.
2. **Fix public observability:** settle the session/trajectory projection and Console command boundary, including fresh
   process and concurrent branch identity.
3. **Close specialist investigation:** complete the UJ-04 and UJ-07 feature-qualification slices against the same pinned environment and record their
   exclusions.
4. **Settle experiment authority:** review Experiment Design and Robustness architecture, resolve TRD-105's job model,
   and enforce replay identity before expanding the agent loop.
5. **Build experiment/review path:** deliver GAP-04-03, GAP-03-01/02/03/04, and independent review artifacts; preserve
   explicit blockers where a producer is not yet available.
6. **Qualify the human outcomes:** complete the UJ-08 and UJ-09 feature-qualification slices, and link their retained evidence to Product State. A feature is complete only when its own decision can be made and reconstructed, even if the result is
   a justified stop.

## Detailed story audit — UJ-05 / US-05-01

**User story:** As a researcher, I can move an explicitly approved candidate into observable paper trading and stop or
reconcile it safely, so operational evidence remains attributable and reversible while funded live execution stays a
later decision.

### Acceptance criteria

- A human reviews the research evidence, risk limits, unresolved limitations, and exact strategy/risk/data versions, then
  creates an explicit paper-trading admission or rejection record.
- Deployment preparation pins the candidate, configuration, model/feature evidence where applicable, broker/account
  scope, data policy, and monitoring limits; agents cannot approve or perform this transition.
- Paper runtime startup recovers open orders, validates broker positions and universe, establishes a session identity,
  and fails closed on ambiguity or out-of-scope broker state.
- The operator can inspect health, market-data freshness, orders, fills, positions, risk decisions, portfolio state,
  reconciliation attempts, and incidents; controls can pause/stop and preserve the reason.
- Paper execution is qualified through representative stale-data, broker mismatch, duplicate-trigger, rejected-order,
  restart, and halt scenarios. Funded live brokerage execution is not required for the current horizon.

### Repository audit — 5 October 2026

**Implemented:** core `TraderService` supports `once`, loop, and Postgres-NOTIFY realtime modes; persistent broker
construction; startup recovery; Alpaca-backed portfolio synchronization and universe validation; stale-data checks;
single-flight cycle execution; deterministic client-order IDs; risk filtering; broker response/fill persistence; periodic
order reconciliation; metrics; health/status payloads; and operator commands for status, health, positions, open orders,
halt status/set/clear, and reconciliation. Backtests always force the internal paper broker. ML deployment manifests
and parity validation can produce bounded model paper eligibility, but do not grant trading authority.

**Implemented for the current paper horizon:** the Console exposes paper-runtime status and read-only operational
evidence, a human-owned candidate admission pins the strategy/risk/data and evidence versions, and the authorized
command path covers start, pause, stop, halt, and reconciliation with audited receipts. A retained deterministic
internal-paper campaign now exercises the runtime incident matrix and records the admission, exact configuration and
broker scope, runtime/session identities, broker and risk outcomes, reconciliation result, and incident receipt for
each phase. External Alpaca-paper checks remain explicitly optional, and funded-live execution still needs a separate
admission standard. Research agents and MCP tools remain prohibited from broker mutation.

| Acceptance point | Evidence coverage | Repository evidence |
| --- | --- | --- |
| Runtime safety and reconciliation | Implemented and covered by the retained paper incident campaign | `src/trader/docs/runtime.md`, `src/trader/docs/runtime_hot_path_and_reconciliation.md`, `src/trader/runtime`, `tests/cross_package/qualification/test_paper_trading_admission_campaign.py` |
| Paper broker and risk path | Implemented and tested through runtime contracts | `src/trader/docs/broker_and_portfolio.md`, `tests/trader/runtime` |
| Candidate/deployment admission | Human paper admission is implemented; funded-live admission remains future | `src/trader_research/governance/paper_admission.py`, `src/trader_console_api/services/paper_operator_commands.py` |
| Console operational observability/control | Implemented for the current read-only and authorized paper-command surface | `src/trader_console_api/docs/usage.md`, `apps/trader-console/src/features/paper-operations` |
| Controlled paper qualification | Deterministic internal-paper campaign retained; external Alpaca-paper checks are not part of the offline gate | `tests/cross_package/qualification/test_paper_trading_admission_campaign.py`, `src/trader/docs/runtime.md` |

### Capability evidence and remaining behavior

- **GAP-05-01 — Paper-candidate admission record:** delivered as the human decision, evidence refs, exact versions,
  risk limits, broker/account scope, monitoring policy, and explicit paper eligibility for a general strategy candidate.
- **GAP-05-02 — Console paper operations read model:** delivered for runtime heartbeat/health, data freshness, session,
  orders, fills, positions, risk outcomes, reconciliation, and incident history with unavailable/incomplete states preserved.
- **GAP-05-03 — Authorized paper controls:** delivered as the explicit API/service boundary for operator-owned start,
  pause, stop, and halt/reconcile actions with audit receipts and no agent/MCP access to broker mutation.
- **GAP-05-04 — Paper qualification campaign:** completed for the current paper horizon through a retained deterministic
  internal-paper campaign. The campaign covers startup recovery, stale data, mismatch, duplicate triggers, rejected
  orders, restart, halt, reconciliation, and operator intervention; its threshold and limits remain explicit.

## Functional requirement audit — FR-01 through FR-14

The journeys above are the user-facing order of work. This index checks the existing functional requirements against the
same repository evidence and prevents a journey gap from hiding a cross-cutting contract gap.

| Requirement | Evidence coverage | Evidence and remaining gap |
| --- | --- | --- |
| **FR-01 — Data identity and provenance** | Partial across the lifecycle | Data, Console, authoring, replay, and research persistence carry exact scope, evidence, and bar-content identity; a unified lifecycle reconstruction remains. |
| **FR-02 — Data exploration and fitness** | Partial | Console discovery, bars, windows, quality, completeness, provider capability, and provenance are exposed; bounded alternative comparison remains. |
| **FR-03 — Versioned strategy construction** | Partial | Admission, immutable specifications, isolated coding, catalogue discovery, and Console implementation lineage exist; the hypothesis brief, controlled model path, and integrated handoff remain. |
| **FR-04 — Reproducible backtest execution** | Partial at Console execution | Research/core execution, exact data handoff, replay identity, and successful worker/review qualification are controlled; broader lifecycle failure campaigns remain. |
| **FR-05 — Backtest evidence and limits** | Partial at review decision | Core and Console expose rich run evidence, review evidence, next decisions, and the successful worker journey; independent producer maturity and broader failure campaigns remain. |
| **FR-06 — Fair comparison and inference** | Partial | Compatible comparison and typed review evidence exist; general inference, robustness, and walk-forward producer paths remain incomplete. |
| **FR-07 — Bounded agent research** | Partial | Session, authority, budgets, specialist loops, and MCP policy exist; controlled third-party model acceptance and extension into experiment execution remain open. |
| **FR-08 — Governed MCP access** | Implemented for the registered research surface; qualification remains scoped | Typed registration, envelopes, ownership, side-effect policy, and research-agent prohibitions are documented and tested. Real-model campaign evidence remains part of GAP-04-01. |
| **FR-09 — Research trace and recoverability** | Partial as a human product surface | Redacted public events, bounded checkpoints, retained trajectory evidence, fresh-process recovery, and canonical receipts exist; the Console session/evidence workspace remains open. |
| **FR-10 — Console research workflow** | Partial | Data, authoring, execution, review, comparison, exact data/implementation handoffs, and next decisions exist as separate slices; agent session visibility and full operational continuity remain. |
| **FR-11 — Controlled deployment** | Implemented for the current paper horizon; funded-live admission remains future | Human paper admission records exact versions, evidence, limits, broker scope, monitoring policy, expiry, and human approval; the retained campaign supports paper admission without claiming funded-live readiness. |
| **FR-12 — Trading observability and intervention** | Implemented for core and Console paper operation; external broker qualification remains bounded | Runtime status, health, reconciliation, halt, read-only operational evidence, and authorized human commands are covered by the retained campaign's incident matrix. |
| **FR-13 — Auditability across the lifecycle** | Partial across seams | Domain artifacts, data/authoring continuity, next-decision records, retained trajectory, and paper admission lineage exist individually; they are not yet one inspectable cross-journey chain. |
| **FR-14 — Demonstrable quantitative development evidence** | Partial | The repository contains reproducible data, implementation, backtest, review, agent, trajectory, and paper-operation evidence; an integrated case study remains a product outcome. |

FR-08 is the only requirement whose registered deterministic contract is currently implemented without a new product
surface in this tranche. Its real-world utility still depends on the model qualification and human workflow gaps that
consume it. This audit therefore treats implementation, qualification, and human usability as separate claims.

## Capability gaps and next-step orientation

These are relative delivery sizes, not calendar promises. **S** is a bounded change inside one package with a known
contract and focused tests. **M** crosses a small number of package or persistence seams and needs an integration check.
**L** crosses several packages, introduces a new authority or evidence boundary, or requires controlled model/broker
qualification. The size includes implementation, documentation, and verification; it is not a measure of product value.

| Requirement | Gap size | Why the gap has this size | Capability steps and dependency |
| --- | --- | --- | --- |
| FR-01 — Data identity and provenance | **L** | Data, Console, authoring, replay, and research persistence now carry exact scope, evidence, and bar-content identity; a unified lifecycle reconstruction remains. | Delivered GAP-01-02, GAP-06-01/02/03/04 provide saved scope, quality/provenance, authoring continuity, replay identity, and integrated qualification. |
| FR-02 — Data exploration and fitness | **M** | Data services and the Console evidence projection are delivered; the remaining product behavior is bounded alternative comparison. | Delivered GAP-01-01/04 and GAP-06-01; **GAP-01-03 (M)** remains for source/window comparison. |
| FR-03 — Versioned strategy construction | **L** | Deterministic admission and Console implementation lineage are delivered; hypothesis capture, controlled model behavior, and integrated handoff remain separate boundaries. | Delivered GAP-02-02 provides admission/version/source lineage; **GAP-02-01/03/04** remain for brief, model qualification, and candidate handoff. |
| FR-04 — Reproducible backtest execution | **L** | Core/research execution, exact data handoff, replay identity, and successful Console worker/review qualification are delivered; failure-state campaigns remain. | Delivered GAP-06-02/03/04 and GAP-03-04 provide identity continuity and the successful path; **GAP-03-01** remains for broader lifecycle outcomes. |
| FR-05 — Backtest evidence and limits | **L** | Rich run evidence, Evaluation/Adversarial projection, next-decision capture, and the successful Console lifecycle are delivered; independent producer maturity and failure campaigns remain. | Delivered GAP-03-02/03/04; **GAP-03-01** and independent robustness/inference producers remain. |
| FR-06 — Fair comparison and inference | **M** | Compatibility rules and review evidence projection are delivered; general inference, robustness, and walk-forward producers remain incomplete. | Delivered GAP-03-02/03; independent producer paths remain larger roadmap capabilities. |
| FR-07 — Bounded agent research | **L** | Runtime contracts exist, but controlled model behavior and the handoff into experiment design/execution are unqualified external boundaries. | Existing IMP-05/IMP-07 plus **GAP-02-03 (L):** Strategy qualification; **GAP-04-01 (L):** Coordinator/Data/Strategy campaign; **GAP-04-03 (L):** experiment handoff. Controlled qualification gates any autonomy claim. |
| FR-08 — Governed MCP access | **L** | Registration, envelopes, ownership, and prohibitions are implemented; the remaining real-world claim requires controlled qualification across model, tool catalogue, transport, and failure behavior. | **GAP-04-01 (L):** qualification campaign is the material remaining task; no new MCP contract is required for the current deterministic surface. |
| FR-09 — Research trace and recoverability | **L** | Redacted events, bounded checkpoints, and retained concurrent trajectory evidence exist; the human Console session/evidence projection remains. | **GAP-04-02 (L):** Console session workspace; the delivered GAP-04-04 fixture supplies retained trajectory evidence. |
| FR-10 — Console research workflow | **L** | Data, authoring, execution, review, comparison, exact handoffs, next decisions, and paper operation are delivered as separate slices; preserving all of them in one agent-aware workflow remains. | **GAP-04-02 (L):** agent session workspace; broader worker failure and cross-journey qualification remain. GAP-06-02/04, GAP-02-02, GAP-03-02/03/04, and GAP-05-02/03 are delivered boundaries. |
| FR-11 — Controlled deployment | **L** | Human paper admission, authorized transition, and the current deterministic incident campaign are delivered; funded-live admission remains a future product decision. | Delivered GAP-05-01/02/03/04 provide the current paper horizon; model-specific ML eligibility remains a collaborator, not the general admission contract. |
| FR-12 — Trading observability and intervention | **L** | Core and Console paper read/command surfaces and the deterministic incident campaign are delivered; external broker qualification remains bounded. | Delivered GAP-05-02/03/04 cover the current paper horizon; funded-live operation is outside it. |
| FR-13 — Auditability across the lifecycle | **L** | Domain artifacts, data/authoring continuity, review decisions, retained trajectory, and paper admission now exist individually; one unified chain across all journeys remains. | Delivered GAP-01-02, GAP-03-03/04, GAP-04-04, and GAP-05-04 provide the component evidence; cross-journey reconstruction remains. |
| FR-14 — Demonstrable quantitative development evidence | **M** after the foundations | The repository now contains reproducible data, implementation, backtest, review, trajectory, and paper-operation evidence; the missing product outcome is a reviewed case study that explains choices, limitations, and revisions. | Delivered GAP-03-03/04, GAP-04-04, and GAP-05-04 supply evidence inputs; **GAP-02-04** and the human case-study outcome remain downstream. |

### Sequence implied by capability dependencies

1. **Complete the remaining identity seams:** refine the hypothesis brief, data alternative comparison, and Console
   session projection. Delivered scope, quality, implementation, replay, review, decision, and trajectory identities
   are inputs that later work must carry without re-entry.
2. **Prove remaining research execution states:** broaden worker failure/reconciliation qualification and make independent
   Evaluation/Robustness producer maturity explicit. The successful worker-to-review path, evidence projection, replay
   identity, and next-decision record are already qualified.
3. **Qualify bounded agent automation:** run the pinned third-party model campaign and extend the approved specialist
   return into Experiment Design and deterministic execution, using the delivered public trajectory evidence.
4. **Extend paper operation only if the horizon changes:** the current human admission, Console operations, authorized
   controls, and deterministic incident campaign are qualified; funded live execution remains outside this sequence.
5. **Assemble professional evidence:** use the accepted artifacts and decisions to produce a reproducible case study with
   explicit limitations and revisions, satisfying FR-14 without making an unsupported profitability claim.

## Next-step orientation for executable capability gaps

The audit above describes the product gap; this section records the next implementation steps. Every gap has a named
contract boundary, data flow, repository surface, verification fixture, documentation change, dependency, and completion
evidence. The paths below are the intended seams, not permission to bypass package ownership.
Each implementation should first align its contract and focused tests with this playbook, then add the next adapter
or UI projection. A gap closes only when the contract tests, package docs,
and the stated integrated evidence all pass.

### Data identity and exploration (UJ-06 / UJ-01)

#### GAP-06-01 / GAP-01-01 — Console data evidence

**Delivered boundary:** the producer-owned `console_read.data_scope_evidence` projection resolves the matching Data
manifest and quality report for a selected scope. The Console renders provider/source policy, coverage, completeness,
findings, warnings, provenance, and complete, partial, stale, warning, empty, and unavailable states without
recalculating Data quality.

**Evidence:** `src/trader_console_api/{contracts.py,repositories/resources.py,services/resources.py,routers/resources.py}`,
`apps/trader-console/src/features/market-data/`, and the API/browser fixtures covering the state matrix. The remaining
UJ-01 orientation is bounded comparison of independent source or window alternatives.

#### GAP-06-02 — Exact scope handoff

**Delivered boundary:** the typed saved-scope handoff carries symbols or universe, asset class, timeframe, interval,
UTC window, source/provider policy, manifest identity, quality identity, and freshness state into authoring. Immutable
persistence and preflight reject stale, unavailable, changed, or policy-mismatched evidence instead of replacing it
with aggregate coverage.

**Evidence:** `src/trader_console_api/{contracts.py,repositories/{saved_data_scopes.py,backtest_definitions.py},services,routers}`,
`apps/trader-console/src/features/{market-data,backtest-authoring}/`, and the integrated data-to-backtest API/browser
fixture.

#### GAP-06-03 — Replay data identity

**Delivered boundary:** qualified Data manifests carry a deterministic bar-content digest and source semantics distinct
from query-scope identity. Research backtest preflight re-reads the exact scope before invoking `BacktestRunner`, fails
closed on changed rows, partial reloads, source substitution, malformed identity, or scope mismatch, and records the
qualified/observed digests, row counts, source semantics, and validation timestamp in the receipt.

**Evidence:** `src/trader_research/foundation/replay_identity.py`, `src/trader_research/data/{inventory.py,evidence.py}`,
`src/trader_research/experiments/backtests/execution.py`, and the identity/inventory/backtest tests. Broader worker
failure and reconciliation campaigns remain in GAP-03-01.

#### GAP-06-04 — End-to-end data qualification

**Delivered boundary:** an instrument-agnostic isolated fixture selects a bounded scope, renders evidence, saves and
reopens it, carries the exact identity into authoring, persists a definition, submits execution, and opens review. It
also proves stale and mismatch blockers remain actionable and cannot create a definition.

**Evidence:** `tests/cross_package/workflows/test_console_data_to_backtest.py` and
`apps/trader-console/tests/e2e/data-to-backtest.spec.ts`, with the corresponding Console tutorial and Product State
record. Broader failed/ambiguous worker outcomes remain in the UJ-03 execution boundary.

#### GAP-01-02 — Saved data scope

**Delivered boundary:** immutable saved-scope records reference the exact manifest/quality evidence and preserve scope,
source policy, creator, and freshness. Reopen/revalidation returns explicit active, stale, unavailable, or superseded
states and never silently refreshes or widens the scope.

**Evidence:** `src/trader_console_api/repositories/{saved_data_scopes.py,saved_data_scopes_schema.py}`,
`src/trader_console_api/services/saved_data_scopes.py`, the market-data save/reopen feature, and its persistence/API
fixtures.

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

#### GAP-01-04 — Discovery completeness contract

**Delivered boundary:** Data, MCP, and Console responses distinguish complete, partial, stale, and unavailable
catalogues from discover-only, load-capable, and unavailable provider capability. Catalogue visibility is never treated
as proof that bounded loading will succeed.

**Evidence:** provider/catalogue normalization, MCP envelopes, Console resource projections, and the discovery state
fixtures/tutorial examples. GAP-01-03 remains the next UJ-01 capability for comparing saved alternatives.

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

#### GAP-02-02 — Console implementation lineage

**Delivered boundary:** authoring carries admitted implementation/version, validation and admission report references,
strategy/risk specification identity, source hash, provenance, and the explicit reuse/adapt/author decision. Resolution
and preflight fail closed on missing, changed, or incompatible lineage while retaining the allowlist authority.

**Evidence:** `src/trader_console_api/services/implementation_lineage.py`, Console authoring contracts/repositories/UI,
`src/trader_research/experiments/implementations/`, and lineage/preflight/API/browser fixtures. Hypothesis capture,
controlled model qualification, and integrated candidate handoff remain separate UJ-02 behavior.

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
   execution repositories, `src/trader/` runner contracts, and the TRD-273/TRD-274 scope.
3. **Verification:** isolated Postgres worker fixtures with restart, duplicate submission, lost response, partial
   persistence, and reconciliation cases; broaden `tests/trader_console_api/services/test_backtest_worker.py` and the
   cross-package qualification suite.
4. **Docs/evidence:** update Console architecture/usage and `src/trader/docs/runtime.md`. Completion is a producer
   backed receipt for every lifecycle state and an explicit reconciliation result.

#### GAP-03-02 — Review statistical and robustness evidence

**Delivered boundary:** run and comparison review now projects producer-owned Evaluation, multiple-testing, and
Adversarial/robustness evidence with exact identity, claim scope, protected-data roles, limitations, and explicit
available, missing, incompatible, and blocked states. Exploratory optimisation output cannot become independent
confirmation.

**Evidence:** `console_read.research_review_evidence`, typed Console contracts/repositories/services, review/comparison
panels, and the focused API/browser fixtures. General robustness/WFO producer maturity remains a separate capability.

#### GAP-03-03 — Next-decision record

**Delivered boundary:** a human-principal-only revisioned artifact records reject, refine, or continue, rationale,
actor/time, exact run/data/implementation/assumption/review references, limitations, and bounded successor inputs.
Canonical digests, idempotent replay, same-chain validation, and fresh-process reads preserve the decision without
starting execution or paper trading.

**Evidence:** `src/trader_research/governance/next_decisions.py`, Console next-decision contracts/repositories/services,
backtest-review panel, and API/browser/reopen fixtures.

#### GAP-03-04 — Research execution journey qualification

**Delivered boundary:** an isolated API/worker/browser fixture proves the successful data-to-definition-to-worker-to-review
path with exact scope identity, assumptions, benchmark/performance, risk, fills, warnings, typed review evidence, and a
human next decision. The worker uses the canonical `BacktestRunner` and persists the typed result snapshot.

**Evidence:** `tests/cross_package/workflows/test_console_execution_to_review.py`,
`tests/cross_package/workflows/test_console_execution_to_review_browser.py`, and
`apps/trader-console/tests/e2e/execution-to-review.spec.ts`. Broader stale-worker, partial, failed, outage, and
reconciliation-required campaigns remain in GAP-03-01.

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

#### GAP-04-04 — Agent trajectory qualification

**Delivered boundary:** the retained public trajectory sink/verifier preserves exact session/program/model/catalogue
identity, concurrent branch attribution, redacted public events, duplicate/sink-failure handling, fresh-process
checkpoint recovery, and terminal decision lineage. Query APIs keep this diagnostic projection separate from canonical
research artifacts; no new event or checkpoint schema was introduced.

**Evidence:** `src/trader_agents/observability/`, checkpoint projection, retained trajectory fixtures, and the focused
observability/qualification suites. Durable product event persistence and controlled third-party-model acceptance remain
separate boundaries.

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

#### GAP-05-04 — Paper qualification campaign

**Delivered boundary:** the retained deterministic internal-paper campaign exercises startup recovery, stale data,
broker/universe mismatch, duplicate triggers, risk and broker rejection, fresh-service restart, halt, reconciliation,
and operator intervention. Each phase records admission/configuration/broker scope, runtime/session identity, responses,
risk actions, reconciliation result, incident receipt, thresholds, and known limits; no funded-live claim follows.

**Evidence:** `tests/cross_package/qualification/test_paper_trading_admission_campaign.py`, runtime hot-path and
reconciliation documentation, and the paper-operations Console boundary. Alpaca-paper account checks remain opt-in and
outside the repeatable offline gate.

### Definition of a closed capability gap

A gap closes only after its focused tests, required cross-package or external qualification, documentation checks, and
evidence artifact are complete. This keeps a “partial” capability measurable: the remaining work is the unchecked steps
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
