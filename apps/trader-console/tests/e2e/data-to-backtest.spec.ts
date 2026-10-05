import { test, expect, type Page } from "@playwright/test";

/**
 * Subject: Complete Console data-to-backtest handoff.
 * Level: Browser integration with deterministic HTTP fixtures.
 * Collaborators: Market-data, authoring, durable execution, and review workspaces.
 * Guarantees: Scope and Data evidence identity survive each user-facing boundary; stale evidence blocks authoring.
 * Non-goals: Producer worker execution, broker mutation, and replay-bar hashing.
 */

test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

const scopeFingerprint = "f".repeat(64);
const scopeId = "scope-1";
const manifestId = "manifest-1";
const qualityId = "quality-1";

const savedScope = {
  saved_scope_id: scopeId,
  scope_id: "console-local",
  revision: 1,
  fingerprint: scopeFingerprint,
  name: "Qualified BTC scope",
  asset_class: "crypto",
  symbols: ["BTC/USD"],
  universe: null,
  timeframe: "1Min",
  interval: "1Min",
  start: "2026-06-21T00:00:00Z",
  end: "2026-06-21T00:30:00Z",
  source_policy: { provider: "fixture", source: "fixture", allow_fallback: false },
  research_role: "backtest_authoring",
  manifest_artifact_id: manifestId,
  quality_artifact_id: qualityId,
  evidence_status: "active",
  evidence_reason: null,
  created_by: "console-operator",
  idempotency_key: "scope-key-1",
  created_at: "2026-06-21T00:00:00Z",
  updated_at: "2026-06-21T00:00:00Z",
};

const scopeHandoff = {
  saved_scope_id: scopeId,
  fingerprint: scopeFingerprint,
  asset_class: "crypto",
  symbols: ["BTC/USD"],
  universe: null,
  timeframe: "1Min",
  interval: "1Min",
  start: savedScope.start,
  end: savedScope.end,
  source_policy: savedScope.source_policy,
  manifest_artifact_id: manifestId,
  quality_artifact_id: qualityId,
  evidence_status: "active",
  evidence_reason: null,
};

const strategyLineage = {
  profile_id: "bollinger_band",
  implementation_version_id: "implementation-strategy",
  implementation_kind: "strategy",
  implementation_name: "bollinger_band implementation",
  implementation_version: "1.0.0",
  source_hash: "a".repeat(64),
  implementation_validation_id: "validation-strategy",
  specification_id: "specification-strategy",
  decision: "exact_reuse",
  validation_report: {
    validation_id: "validation-strategy",
    implementation_version_id: "implementation-strategy",
    implementation_kind: "strategy",
    source_hash: "a".repeat(64),
    status: "passed",
    valid: true,
    blockers: [],
  },
};

const riskLineage = {
  profile_id: "max_orders_per_run",
  implementation_version_id: "implementation-risk",
  implementation_kind: "risk_manager",
  implementation_name: "max_orders_per_run implementation",
  implementation_version: "1.0.0",
  source_hash: "b".repeat(64),
  implementation_validation_id: "validation-risk",
  specification_id: "specification-risk",
  decision: "exact_reuse",
  validation_report: {
    validation_id: "validation-risk",
    implementation_version_id: "implementation-risk",
    implementation_kind: "risk_manager",
    source_hash: "b".repeat(64),
    status: "passed",
    valid: true,
    blockers: [],
  },
};

const catalogue = {
  catalogue_version: "standard-1",
  strategy_profiles: [{
    kind: "strategy",
    profile_id: "bollinger_band",
    version: "standard-1",
    name: "Bollinger Band re-entry",
    description: "Maintained strategy.",
    parameters: [{ name: "period", type: "integer", default: 20, required: false, minimum: 2, maximum: 500, description: "Window." }],
    supported_asset_classes: ["crypto"],
    supported_timeframes: ["1Min"],
    lookback_bars: 21,
    evidence_requirements: ["signals"],
    manager_ids: [],
    reason_codes: [],
  }],
  risk_profiles: [{
    kind: "risk",
    profile_id: "max_orders_per_run",
    version: "standard-1",
    name: "Maximum orders",
    description: "Blocks after a limit.",
    parameters: [{ name: "limit", type: "integer", default: 100, required: false, minimum: 0, maximum: 1000, description: "Order limit." }],
    supported_asset_classes: ["crypto"],
    supported_timeframes: ["1Min"],
    lookback_bars: 0,
    evidence_requirements: ["risk_decisions"],
    manager_ids: ["max_orders_per_run"],
    reason_codes: ["approved", "max_orders_per_run"],
  }],
};

const normalizedDefinition = {
  symbols: savedScope.symbols,
  start: savedScope.start,
  end: savedScope.end,
  strategy_profile_id: "bollinger_band",
  strategy_catalogue_version: "standard-1",
  strategy_parameters: { period: 20 },
  strategy_implementation_lineage: strategyLineage,
  risk_profile_id: "max_orders_per_run",
  risk_catalogue_version: "standard-1",
  risk_parameters: { limit: 100 },
  risk_implementation_lineage: riskLineage,
  asset_class: "crypto",
  timeframe: "1Min",
  display_name: "Local backtest",
  initial_cash: 100000,
  initial_positions: [],
  assumptions: { fill_model: "full_fill", latency_ms: 0, fee_fixed_per_order: 0, fee_bps: 0, fee_minimum: 0, slippage_bps: 0, allow_latest_prior_bar: true, allow_price_carry_forward: true },
  resource_limits: { max_cycles: 1000000, max_bars: 5000000, timeout_seconds: 3600 },
  benchmark_id: "buy_hold",
  data_scope: scopeHandoff,
};

const definition = {
  definition_id: "definition-1",
  scope_id: "console-local",
  definition_version: 1,
  revision: 1,
  fingerprint: "d".repeat(64),
  definition: normalizedDefinition,
  created_at: "2026-06-21T00:00:00Z",
  updated_at: "2026-06-21T00:00:00Z",
};

const queuedExecution = {
  execution_id: "execution-1",
  scope_id: "console-local",
  definition_id: definition.definition_id,
  definition_revision: 1,
  definition_fingerprint: definition.fingerprint,
  idempotency_key: "execution-key-1",
  status: "completed",
  attempt: 1,
  worker_id: "worker-1",
  run_id: "run-1",
  processed_cycles: 31,
  total_cycles: 31,
  last_decision_at: "2026-06-21T00:31:00Z",
  heartbeat_at: "2026-06-21T00:31:00Z",
  lease_expires_at: null,
  created_at: "2026-06-21T00:30:00Z",
  started_at: "2026-06-21T00:30:01Z",
  finished_at: "2026-06-21T00:31:00Z",
  warning_summary: [],
  terminal_error_code: null,
  terminal_error_message: null,
};

function evidenceArtifact(artifactId: string) {
  return {
    artifact_id: artifactId,
    uri: `research://fixture/${artifactId}`,
    status: "available",
    schema_version: "1",
    source_hash: `${artifactId}-hash`,
    created_at: "2026-06-21T00:00:00Z",
    updated_at: "2026-06-21T00:00:00Z",
    payload: {},
  };
}

function reviewDetail() {
  return {
    run: {
      experiment_run_id: "run-1",
      experiment_id: "standalone_backtests",
      run_id: "run-1",
      status: "completed",
      mode: "backtest",
      created_at: "2026-06-21T00:30:00Z",
      finished_at: "2026-06-21T00:31:00Z",
      strategy_id: "bollinger_band",
      strategy_name: "Bollinger Band re-entry",
      strategy_version: "standard-1",
      symbols: savedScope.symbols,
      asset_class: savedScope.asset_class,
      timeframe: savedScope.timeframe,
      start_ts: savedScope.start,
      end_ts: savedScope.end,
      scope_fingerprint: scopeFingerprint,
      data_scope_id: scopeId,
      benchmark_id: "buy_hold",
      variant_fingerprint: null,
      variant_strategy_id: null,
      variant_strategy_version: null,
      comparison_projection_available: false,
      comparison_eligible: false,
      comparison_exclusion_reason: "Standalone fixture",
    },
    scope: {
      scope_fingerprint: scopeFingerprint,
      data_scope_id: scopeId,
      benchmark_id: "buy_hold",
      replay_start: savedScope.start,
      replay_end: savedScope.end,
      initial_cash: 100000,
    },
    performance: {
      observed_at: savedScope.end,
      strategy_total_return: 0.12,
      benchmark_total_return: 0.08,
      realized_pnl: 1200,
      strategy_max_drawdown: -0.04,
      strategy_sharpe: 1.3,
      strategy_trade_count: 1,
      strategy_hit_rate: 1,
      total_fees: 1,
    },
    equity_curve: [
      { ts: savedScope.start, strategy_equity: 100000, benchmark_equity: 100000 },
      { ts: savedScope.end, strategy_equity: 112000, benchmark_equity: 108000 },
    ],
    comparison_curves: [
      { ts: savedScope.start, strategy_drawdown: 0, benchmark_drawdown: 0 },
      { ts: savedScope.end, strategy_drawdown: -0.04, benchmark_drawdown: -0.02 },
    ],
    trades: [],
    positions: [],
    warnings: [],
    provenance: [{ provenance_key: "data_scope", provenance_value: scopeId, observed_at: savedScope.end }],
    indicator_series: [],
    signal_markers: [],
    risk_composition: [],
    risk_summary: null,
    risk_decisions: [],
    review_evidence: [],
    signals: [],
    orders: [],
    fills: [],
  };
}

async function installJourneyRoutes(page: Page, options: { stale?: boolean } = {}) {
  const requests: { scope?: Record<string, unknown>; preflight?: Record<string, unknown>; definition?: Record<string, unknown> } = {};
  const currentScope = options.stale ? { ...savedScope, evidence_status: "stale", evidence_reason: "The qualified evidence has expired." } : savedScope;

  await page.route("**/api/market-data/datasets**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ asset_class: "crypto", symbol: "BTC/USD", timeframe: "1Min", source: "fixture", first_ts: savedScope.start, last_ts: savedScope.end, bar_count: 31 }], page: { limit: 500, offset: 0, total: 1, has_more: false }, discovery: { provider: "fixture", catalogue_completeness: "complete", catalogue_freshness: "fresh", can_discover: true, can_load: true, load_capability: "load_capable", reason: "Fixture provider receipt." } }) }));
  await page.route("**/api/market-data/bars**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ symbol: "BTC/USD", timeframe: "1Min", ts: savedScope.start, open: 100, high: 101, low: 99, close: 100.5, volume: 10, source: "fixture" }], page: { limit: 50000, offset: 0, total: 31, has_more: false } }) }));
  await page.route("**/api/market-data/evidence**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ scope: { asset_class: "crypto", symbols: savedScope.symbols, timeframe: "1Min", interval: "1Min", bar_type: "trade_bar", start: savedScope.start, end: savedScope.end, provider: "fixture", source_policy: "fixture" }, state: options.stale ? "stale" : "complete", evidence_reason: options.stale ? "The qualified evidence has expired." : "Manifest and quality evidence match the exact requested scope.", provider: "fixture", source_policy: "fixture", coverage: { total_rows: 31, total_bars: 31 }, findings: [], warnings: [], provenance: [`research://fixture/${manifestId}`, `research://fixture/${qualityId}`], manifest: evidenceArtifact(manifestId), quality: evidenceArtifact(qualityId) }) }));
  await page.route("**/api/data-scopes**", (route) => {
    if (route.request().method() === "POST") {
      requests.scope = route.request().postDataJSON() as Record<string, unknown>;
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(currentScope) });
    }
    const url = new URL(route.request().url());
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(url.pathname.endsWith(scopeId) ? currentScope : { items: [], page: { limit: 100, offset: 0, total: 0, has_more: false } }) });
  });
  await page.route("**/api/backtests/catalogue**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalogue) }));
  await page.route(`**/api/data-scopes/${scopeId}`, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentScope) }));
  await page.route("**/api/backtests/preflight", (route) => {
    requests.preflight = route.request().postDataJSON() as Record<string, unknown>;
    const response = options.stale
      ? { valid: false, catalogue_version: "standard-1", definition_fingerprint: null, normalized_definition: null, coverage: [], issues: [{ severity: "error", code: "data_scope_stale", path: "data_scope.evidence_status", message: "The saved data scope evidence is stale; revalidate it before authoring." }] }
      : { valid: true, catalogue_version: "standard-1", definition_fingerprint: definition.fingerprint, normalized_definition: normalizedDefinition, coverage: [{ symbol: "BTC/USD", asset_class: "crypto", timeframe: "1Min", first_ts: savedScope.start, last_ts: savedScope.end, bar_count: 31, required_start: "2026-06-20T23:39:00Z", requested_end: savedScope.end, warmup_bars: 21, available: true, warmup_satisfied: true }], issues: [] };
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(response) });
  });
  await page.route("**/api/backtests/definitions", (route) => {
    requests.definition = route.request().postDataJSON() as Record<string, unknown>;
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(definition) });
  });
  await page.route("**/api/backtests/executions", (route) => route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(queuedExecution) }));
  await page.route("**/api/backtests/executions/execution-1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(queuedExecution) }));
  await page.route("**/api/experiments?**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [{ experiment_id: "standalone_backtests", run_count: 1, latest_created_at: savedScope.end, statuses: ["completed"], metadata_available: false }], page: { limit: 100, offset: 0, total: 1, has_more: false } }) }));
  await page.route("**/api/experiments/standalone_backtests/runs**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [reviewDetail().run], page: { limit: 100, offset: 0, total: 1, has_more: false } }) }));
  await page.route("**/api/runs/run-1**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(reviewDetail()) }));
  return { requests };
}

test("qualifies the data selection, exact handoff, execution, and review journey", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const { requests } = await installJourneyRoutes(page);

  await page.goto("/data");
  await expect(page.getByText("Data evidence")).toBeVisible();
  await expect(page.getByText(/Provenance: .*manifest-1/)).toBeVisible();
  await page.getByLabel("Manifest artifact reference").fill(manifestId);
  await page.getByLabel("Quality artifact reference").fill(qualityId);
  await page.getByRole("button", { name: "Save exact scope" }).click();
  await expect(page.getByText(`Saved exact scope ${scopeId}.`, { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Author backtest with this scope" }).click();

  await expect(page).toHaveURL(new RegExp(`/backtests/new\\?saved_scope_id=${scopeId}`));
  await expect(page.getByRole("heading", { name: "Define and run a local backtest" })).toBeVisible();
  await expect(page.getByLabel("Symbols")).toHaveAttribute("readonly", "");
  await expect(page.getByLabel("Asset class")).toBeDisabled();
  const scopeStatus = page.getByRole("region", { name: "Replay scope" }).getByRole("status");
  await expect(scopeStatus).toContainText(`manifest ${manifestId}`);
  await expect(scopeStatus).toContainText(`quality ${qualityId}`);
  await page.getByLabel("Strategy implementation lineage JSON").fill(JSON.stringify(strategyLineage));
  await page.getByLabel("Risk implementation lineage JSON").fill(JSON.stringify(riskLineage));
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByText("Preflight passed. The definition is ready to save.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Save immutable definition" }).click();
  await expect(page.getByRole("button", { name: "Saved revision 1" })).toBeVisible();
  await page.getByRole("button", { name: "Submit execution" }).click();
  await expect(page.getByRole("heading", { name: "Completed" })).toBeVisible();
  await page.getByRole("link", { name: "Open run review" }).click();

  await expect(page).toHaveURL(/\/backtests\?run_id=run-1/);
  await expect(page.getByRole("heading", { name: "Bollinger Band re-entry" })).toBeVisible();
  await expect(page.getByText(scopeFingerprint, { exact: true })).toBeVisible();
  await expect(page.getByText(scopeId, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Showing the available evidence for run-1.", { exact: true })).toBeVisible();

  expect(requests.scope?.manifest_artifact_id).toBe(manifestId);
  expect(requests.scope?.quality_artifact_id).toBe(qualityId);
  expect(requests.preflight?.data_scope).toEqual(scopeHandoff);
  expect(requests.definition?.data_scope).toEqual(scopeHandoff);
  expect(reviewDetail().scope.scope_fingerprint).toBe(scopeFingerprint);
  expect(reviewDetail().scope.data_scope_id).toBe(scopeId);
});

test("surfaces stale qualified evidence as an actionable authoring blocker", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const { requests } = await installJourneyRoutes(page, { stale: true });

  await page.goto(`/backtests/new?saved_scope_id=${scopeId}`);
  await expect(page.getByRole("heading", { name: "Define and run a local backtest" })).toBeVisible();
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByText("Error: data_scope.evidence_status", { exact: true })).toBeVisible();
  await expect(page.getByText("The saved data scope evidence is stale; revalidate it before authoring.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save immutable definition" })).toBeDisabled();
  expect(requests.preflight?.data_scope).toMatchObject({ saved_scope_id: scopeId, fingerprint: scopeFingerprint, evidence_status: "stale" });
  expect(requests.definition).toBeUndefined();
});
