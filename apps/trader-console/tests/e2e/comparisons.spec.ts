import { test, expect } from "@playwright/test";

test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

test("comparison workspace selects runs, explains eligibility, and renders shared evidence", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const experiment = { experiment_id: "exp-bollinger", run_count: 2, latest_created_at: "2026-09-21T21:25:00Z", statuses: ["completed"], metadata_available: false };
  const runs = [
    { experiment_run_id: "exp:run-a", experiment_id: "exp-bollinger", run_id: "run-a", status: "completed", strategy_name: "Bollinger 20", strategy_id: "bollinger", symbols: ["BTC/USD"], asset_class: "crypto", timeframe: "1Min", scope_fingerprint: "scope-1", comparison_projection_available: true, comparison_eligible: true },
    { experiment_run_id: "exp:run-b", experiment_id: "exp-bollinger", run_id: "run-b", status: "completed", strategy_name: "Bollinger 30", strategy_id: "bollinger", symbols: ["BTC/USD"], asset_class: "crypto", timeframe: "1Min", scope_fingerprint: "scope-1", comparison_projection_available: true, comparison_eligible: true },
  ];
  const detail = (run: typeof runs[number]) => ({
    run,
    scope: { run_id: run.run_id, scope_fingerprint: "scope-1", data_scope_id: "btc-3m", benchmark_id: "buy_hold" },
    comparison_summary: { run_id: run.run_id, scope_fingerprint: "scope-1", strategy_total_return: run.run_id === "run-a" ? 0.12 : 0.1, strategy_max_drawdown: -0.04, strategy_sharpe: 1.2, strategy_trade_count: 4, warnings_count: 0 },
    comparison_curves: [{ run_id: run.run_id, scope_fingerprint: "scope-1", ts: "2026-09-01T00:00:00Z", strategy_normalized: 1, benchmark_normalized: 1, strategy_drawdown: 0, benchmark_drawdown: 0 }, { run_id: run.run_id, scope_fingerprint: "scope-1", ts: "2026-09-01T00:01:00Z", strategy_normalized: 1.1, benchmark_normalized: 1.04, strategy_drawdown: -0.04, benchmark_drawdown: -0.02 }],
    review_evidence: [
      { evidence_kind: "evaluation", status: "available", reason: "Independent evaluation is available for this run.", claim_scope: { run_id: run.run_id, scope_fingerprint: "scope-1" }, data_roles: ["evaluation"], limitations: [], blockers: [], independent_confirmation: true, origin_kind: "independent_review" },
      { evidence_kind: "multiple_testing", status: "blocked", reason: "Multiple-testing report is blocked by missing family definition.", claim_scope: { run_id: run.run_id, scope_fingerprint: "scope-1" }, data_roles: ["multiple_testing"], limitations: ["Optimisation output remains exploratory."], blockers: ["Family definition is missing."], independent_confirmation: false, origin_kind: "optimization" },
      { evidence_kind: "adversarial", status: "missing", reason: "No Adversarial/robustness artifact is linked to this run.", claim_scope: { run_id: run.run_id, scope_fingerprint: "scope-1" }, data_roles: [], limitations: [], blockers: [], independent_confirmation: false, origin_kind: null },
    ],
  });
  await page.route("**/api/experiments?**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [experiment], page: { limit: 50, offset: 0, total: 1, has_more: false } }) }));
  await page.route("**/api/experiments/exp-bollinger/runs**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: runs, page: { limit: 50, offset: 0, total: 2, has_more: false } }) }));
  await page.route("**/api/experiments/exp-bollinger/comparison-views**", async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], page: { limit: 50, offset: 0, total: 0, has_more: false } }) });
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ view: { view_id: "view-1", scope_id: "scope", experiment_id: "exp-bollinger", definition_version: 1, definition: { name: "Untitled comparison", run_ids: ["run-a", "run-b"], reference_run_id: "run-a", metric_keys: ["strategy_total_return", "strategy_max_drawdown", "strategy_sharpe"], series_keys: ["strategy_normalized", "strategy_drawdown"] }, revision: 1, created_at: "2026-09-21T21:25:00Z", updated_at: "2026-09-21T21:25:00Z" }, evaluation: { state: "ready", eligible_run_ids: ["run-a", "run-b"], runs: [{ run_id: "run-a", eligible: true, exclusion_reason: null, scope_fingerprint: "scope-1" }, { run_id: "run-b", eligible: true, exclusion_reason: null, scope_fingerprint: "scope-1" }] } }) });
  });
  await page.route("**/api/experiments/exp-bollinger/comparison-views/view-1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ view: { view_id: "view-1", scope_id: "scope", experiment_id: "exp-bollinger", definition_version: 1, definition: { name: "Untitled comparison", run_ids: ["run-a", "run-b"], reference_run_id: "run-a", metric_keys: ["strategy_total_return", "strategy_max_drawdown", "strategy_sharpe"], series_keys: ["strategy_normalized", "strategy_drawdown"] }, revision: 1, created_at: "2026-09-21T21:25:00Z", updated_at: "2026-09-21T21:25:00Z" }, evaluation: { state: "ready", eligible_run_ids: ["run-a", "run-b"], runs: [{ run_id: "run-a", eligible: true, exclusion_reason: null, scope_fingerprint: "scope-1" }, { run_id: "run-b", eligible: true, exclusion_reason: null, scope_fingerprint: "scope-1" }] } }) }));
  await page.route("**/api/experiments/exp-bollinger/comparison-views/preview", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ state: "ready", eligible_run_ids: ["run-a", "run-b"], runs: [{ run_id: "run-a", eligible: true, exclusion_reason: null, scope_fingerprint: "scope-1" }, { run_id: "run-b", eligible: true, exclusion_reason: null, scope_fingerprint: "scope-1" }] }) }));
  await page.route("**/api/runs/*", (route) => { const runId = new URL(route.request().url()).pathname.split("/").at(-1); const selected = runs.find((run) => run.run_id === runId); return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail(selected ?? runs[0]!)) }); });

  await page.goto("/comparisons");
  await expect(page.getByRole("heading", { name: "Compare related runs" })).toBeVisible();
  const checkboxes = page.getByRole("checkbox");
  await checkboxes.nth(0).check();
  await checkboxes.nth(1).check();
  await page.getByRole("button", { name: "Preview eligibility" }).click();
  await expect(page.getByText("Eligible", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("img", { name: "Comparison performance curves on a shared UTC timeline" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Comparison metrics" })).toBeVisible();
  await page.getByRole("button", { name: "Save view" }).click();
  await expect(page.getByText("Saved comparison view.", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
