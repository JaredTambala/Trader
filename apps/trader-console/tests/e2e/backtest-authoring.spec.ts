import { test, expect } from "@playwright/test";

test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

test("backtest authoring preflights, saves, submits and observes a run", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const catalogue = {
    catalogue_version: "standard-1",
    strategy_profiles: [{ kind: "strategy", profile_id: "bollinger_band", version: "standard-1", name: "Bollinger Band re-entry", description: "Maintained strategy.", parameters: [{ name: "period", type: "integer", default: 20, required: false, minimum: 2, maximum: 500, description: "Window." }], supported_asset_classes: ["crypto"], supported_timeframes: ["1Min"], lookback_bars: 21, evidence_requirements: ["signals"], manager_ids: [], reason_codes: [] }],
    risk_profiles: [{ kind: "risk", profile_id: "max_orders_per_run", version: "standard-1", name: "Maximum orders", description: "Blocks after a limit.", parameters: [{ name: "limit", type: "integer", default: 100, required: false, minimum: 0, maximum: 1000, description: "Order limit." }], supported_asset_classes: ["crypto"], supported_timeframes: ["1Min"], lookback_bars: 0, evidence_requirements: ["risk_decisions"], manager_ids: ["max_orders_per_run"], reason_codes: ["approved", "max_orders_per_run"] }],
  };
  const fingerprint = "a".repeat(64);
  const savedScope = {
    saved_scope_id: "scope-1",
    scope_id: "console-local",
    revision: 1,
    fingerprint,
    name: "Fixture scope",
    asset_class: "crypto",
    symbols: ["BTC/USD"],
    universe: null,
    timeframe: "1Min",
    interval: "1Min",
    start: "2026-06-21T00:00:00Z",
    end: "2026-06-21T00:30:00Z",
    source_policy: { provider: "fixture", source: "fixture", allow_fallback: false },
    research_role: "backtest_authoring",
    manifest_artifact_id: "manifest-1",
    quality_artifact_id: "quality-1",
    evidence_status: "active",
    evidence_reason: null,
    created_by: "fixture",
    idempotency_key: "fixture",
    created_at: "2026-06-21T00:00:00Z",
    updated_at: "2026-06-21T00:00:00Z",
  };
  const dataScopeHandoff = {
    saved_scope_id: savedScope.saved_scope_id,
    fingerprint: savedScope.fingerprint,
    asset_class: savedScope.asset_class,
    symbols: savedScope.symbols,
    universe: savedScope.universe,
    timeframe: savedScope.timeframe,
    interval: savedScope.interval,
    start: savedScope.start,
    end: savedScope.end,
    source_policy: savedScope.source_policy,
    manifest_artifact_id: savedScope.manifest_artifact_id,
    quality_artifact_id: savedScope.quality_artifact_id,
    evidence_status: savedScope.evidence_status,
    evidence_reason: savedScope.evidence_reason,
  };
  const normalizedDefinition = { symbols: ["BTC/USD"], start: "2026-06-21T00:00:00Z", end: "2026-06-21T00:30:00Z", strategy_profile_id: "bollinger_band", strategy_catalogue_version: "standard-1", strategy_parameters: { period: 20 }, risk_profile_id: "max_orders_per_run", risk_catalogue_version: "standard-1", risk_parameters: { limit: 100 }, asset_class: "crypto", timeframe: "1Min", display_name: "Local backtest", initial_cash: 100000, initial_positions: [], assumptions: { fill_model: "full_fill", latency_ms: 0, fee_fixed_per_order: 0, fee_bps: 0, fee_minimum: 0, slippage_bps: 0, allow_latest_prior_bar: true, allow_price_carry_forward: true }, resource_limits: { max_cycles: 1000000, max_bars: 5000000, timeout_seconds: 3600 }, benchmark_id: "buy_hold", data_scope: dataScopeHandoff };
  const definition = { definition_id: "definition-1", scope_id: "console-local", definition_version: 1, revision: 1, fingerprint, definition: normalizedDefinition, created_at: "2026-06-21T00:00:00Z", updated_at: "2026-06-21T00:00:00Z" };
  const queued = { execution_id: "execution-1", scope_id: "console-local", definition_id: "definition-1", definition_revision: 1, definition_fingerprint: fingerprint, idempotency_key: "key", status: "queued", attempt: 0, worker_id: null, run_id: null, processed_cycles: 0, total_cycles: 31, last_decision_at: null, heartbeat_at: null, lease_expires_at: null, created_at: "2026-06-21T00:00:00Z", started_at: null, finished_at: null, warning_summary: [], terminal_error_code: null, terminal_error_message: null };
  const completed = { ...queued, status: "completed", run_id: "run-1", processed_cycles: 31, heartbeat_at: "2026-06-21T00:01:00Z", finished_at: "2026-06-21T00:02:00Z" };
  await page.route("**/api/backtests/catalogue", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalogue) }));
  await page.route("**/api/data-scopes/scope-1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(savedScope) }));
  await page.route("**/api/backtests/preflight", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ valid: true, catalogue_version: "standard-1", definition_fingerprint: fingerprint, normalized_definition: normalizedDefinition, coverage: [{ symbol: "BTC/USD", asset_class: "crypto", timeframe: "1Min", first_ts: "2026-06-21T00:00:00Z", last_ts: "2026-06-21T00:30:00Z", bar_count: 31, required_start: "2026-06-20T23:39:00Z", requested_end: "2026-06-21T00:30:00Z", warmup_bars: 21, available: true, warmup_satisfied: true }], issues: [] }) }));
  await page.route("**/api/backtests/definitions", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(definition) }));
  await page.route("**/api/backtests/executions", (route) => route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(queued) }));
  await page.route("**/api/backtests/executions/execution-1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(completed) }));

  await page.goto("/backtests/new?saved_scope_id=scope-1");
  await expect(page.getByRole("heading", { name: "Define and run a local backtest" })).toBeVisible();
  await expect(page.getByRole("spinbutton", { name: "period" })).toHaveValue("20");
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByText("Preflight passed. The definition is ready to save.", { exact: true })).toBeVisible();
  await expect(page.getByText(fingerprint, { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Normalized definition" })).toBeVisible();
  await page.getByRole("button", { name: "Save immutable definition" }).click();
  await expect(page.getByRole("button", { name: "Saved revision 1" })).toBeVisible();
  await page.getByRole("button", { name: "Submit execution" }).click();
  await expect(page.getByRole("heading", { name: "Completed" })).toBeVisible();
  await expect(page.getByText("31 / 31 cycles", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open run review" })).toHaveAttribute("href", "/backtests?run_id=run-1");
  await expect(page).toHaveURL(/execution_id=execution-1/);
});
