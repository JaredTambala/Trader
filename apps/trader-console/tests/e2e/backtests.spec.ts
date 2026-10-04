import { test, expect } from "@playwright/test";

test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

test("backtest review shows scoped metrics, curves, and execution evidence", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const experiment = {
    experiment_id: "exp-bollinger",
    run_count: 1,
    latest_created_at: "2026-09-21T21:25:00Z",
    statuses: ["completed"],
    metadata_available: false,
  };
  const run = {
    experiment_run_id: "exp-run-1",
    experiment_id: "exp-bollinger",
    run_id: "run-1",
    status: "completed",
    mode: "backtest",
    created_at: "2026-09-21T21:25:00Z",
    finished_at: "2026-09-21T21:26:00Z",
    strategy_id: "bollinger_band",
    strategy_name: "BTC/USD Bollinger Bands",
    strategy_version: "1",
    symbols: ["BTC/USD"],
    asset_class: "crypto",
    timeframe: "1Min",
    start_ts: "2026-06-21T00:00:00Z",
    end_ts: "2026-09-21T21:25:00Z",
    scope_fingerprint: "scope-1",
    data_scope_id: "btc-3m",
    benchmark_id: "buy_hold",
    variant_fingerprint: "variant-1",
    variant_strategy_id: "bollinger_band",
    variant_strategy_version: "1",
    comparison_projection_available: true,
    comparison_eligible: true,
    comparison_exclusion_reason: null,
  };
  const detail = {
    run,
    scope: {
      run_id: "run-1",
      scope_fingerprint: "scope-1",
      data_scope_id: "btc-3m",
      benchmark_id: "buy_hold",
      replay_start: run.start_ts,
      replay_end: run.end_ts,
      initial_cash: 100_000,
    },
    performance: {
      run_id: "run-1",
      observed_at: run.end_ts,
      strategy_total_return: 0.12,
      benchmark_total_return: 0.08,
      realized_pnl: 1200,
      strategy_max_drawdown: -0.04,
      strategy_sharpe: 1.3,
      strategy_trade_count: 4,
      strategy_hit_rate: 0.5,
      total_fees: 12,
    },
    equity_curve: [
      { run_id: "run-1", ts: run.start_ts, strategy_equity: 100_000, benchmark_equity: 100_000 },
      { run_id: "run-1", ts: run.end_ts, strategy_equity: 112_000, benchmark_equity: 108_000 },
    ],
    comparison_curves: [
      { run_id: "run-1", ts: run.start_ts, strategy_drawdown: 0, benchmark_drawdown: 0 },
      { run_id: "run-1", ts: run.end_ts, strategy_drawdown: -0.04, benchmark_drawdown: -0.06 },
    ],
    trades: [{ run_id: "run-1", fill_ts: run.end_ts, symbol: "BTC/USD", side: "buy", fill_qty: 0.1, fill_price: 60_000, realized_pnl: 0 }],
    positions: [],
    warnings: [],
    provenance: [{ run_id: "run-1", provenance_key: "source", provenance_value: "fixture", observed_at: run.end_ts }],
    indicator_series: [{ run_id: "run-1", symbol: "BTC/USD", indicator_name: "middle", series_id: "middle", series_label: "Middle", pane: "price", scale_group: "price", unit: "price", series_kind: "line", bar_ts: run.end_ts, value: 60_000 }],
    signal_markers: [],
    signals: [{ run_id: "run-1", generated_at: run.end_ts, symbol: "BTC/USD", signal_name: "bollinger", signal_value: 1, target_qty: 0.1 }],
    orders: [{ run_id: "run-1", created_at: run.end_ts, symbol: "BTC/USD", side: "buy", qty: 0.1, status: "accepted" }],
    fills: [{ run_id: "run-1", fill_ts: run.end_ts, symbol: "BTC/USD", fill_qty: 0.1, fill_price: 60_000, fee_amount: 1 }],
    assumptions: { run_id: "run-1", fill_model: "next_bar", latency_ms: 0, fee_bps: 1, fee_fixed_per_order: 0, slippage_bps: 2 },
    exposure: { run_id: "run-1", avg_net_exposure: 0.5, avg_invested_pct: 0.5, final_gross_notional: 6_000, position_count: 1 },
    evidence_coverage: null,
    comparison_summary: null,
    risk_composition: [{ run_id: "run-1", session_id: "session-1", catalogue_version: "standard-1", composition_fingerprint: "risk-fingerprint", manager_position: 0, manager_id: "max_orders_per_run", manager_type: "trader_standard.risk.MaxOrdersPerRunRiskManager", parameters: { limit: 0 } }],
    risk_summary: { run_id: "run-1", composition_fingerprint: "risk-fingerprint", risk_evidence_status: "recorded", evaluated_count: 1, approved_count: 0, transformed_count: 0, rejected_count: 1, blocked_count: 1 },
    risk_decisions: [{ risk_decision_id: "riskdec-1", composition_fingerprint: "risk-fingerprint", run_id: "run-1", session_id: "session-1", cycle_id: "cycle-1", client_order_id: "order-1", decision_ts: run.end_ts, manager_id: "max_orders_per_run", manager_type: "trader_standard.risk.MaxOrdersPerRunRiskManager", manager_position: 0, outcome: "rejected", reason_code: "limit_exceeded", before_qty: 0.1, after_qty: null, before_order: { qty: 0.1 }, after_order: null }],
  };
  await page.route("**/api/experiments?**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [experiment], page: { limit: 100, offset: 0, total: 1, has_more: false } }) }));
  await page.route("**/api/experiments/exp-bollinger/runs**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [run], page: { limit: 100, offset: 0, total: 1, has_more: false } }) }));
  await page.route("**/api/runs/run-1**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(detail) }));
  await page.route("**/api/runs/run-1/risk-decisions?**", (route) => {
    const outcome = new URL(route.request().url()).searchParams.get("outcome");
    const items = outcome === "approved" ? [] : detail.risk_decisions;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items, page: { limit: 25, offset: 0, total: items.length, has_more: false } }) });
  });

  await page.goto("/backtests");
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Backtest review/ })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "BTC/USD Bollinger Bands" })).toBeVisible();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible();
  await expect(page.getByText("12%", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "Strategy and benchmark equity chart" })).toBeVisible();
  await expect(page.getByText("Executed trades", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Composition and decisions" })).toBeVisible();
  await expect(page.getByText("Risk block recorded", { exact: true })).toBeVisible();
  await expect(page.getByText('{"limit":0}', { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open risk decision for cycle cycle-1" })).toHaveAttribute("href", "/backtests?experiment_id=exp-bollinger&run_id=run-1&cycle_id=cycle-1&client_order_id=order-1");
  await page.getByRole("link", { name: "Open risk decision for cycle cycle-1" }).click();
  await expect(page).toHaveURL(/cycle_id=cycle-1/);
  await expect(page.getByRole("textbox", { name: "Risk cycle filter" })).toHaveValue("cycle-1");
  await expect(page.getByRole("textbox", { name: "Risk order filter" })).toHaveValue("order-1");
  await page.getByRole("combobox", { name: "Risk outcome filter" }).selectOption("approved");
  await expect(page.getByText("No risk decision trace were published for this run.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Lifecycle events" }).click();
  await expect(page.getByText("Signal lifecycle", { exact: true })).toBeVisible();
  await expect(page.getByText("Order lifecycle", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
