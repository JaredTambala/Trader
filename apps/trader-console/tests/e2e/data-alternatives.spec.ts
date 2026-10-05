import { test, expect } from "@playwright/test";

test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

test("the data workspace compares saved alternatives with explicit evidence", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const firstId = "00000000-0000-0000-0000-000000000001";
  const secondId = "00000000-0000-0000-0000-000000000002";
  const savedScope = (id: string, source: string) => ({
    saved_scope_id: id,
    scope_id: "browser-fixture",
    revision: 1,
    fingerprint: id.replaceAll("-", "").padEnd(64, "0"),
    name: `${source} exact scope`,
    asset_class: "stock",
    symbols: ["AAPL"],
    universe: null,
    timeframe: "1Min",
    interval: "1Min",
    start: "2026-09-10T09:30:00Z",
    end: "2026-09-10T16:00:00Z",
    source_policy: { provider: source, source, allow_fallback: false },
    research_role: "backtest_authoring",
    manifest_artifact_id: `manifest-${source}`,
    quality_artifact_id: `quality-${source}`,
    evidence_status: "active",
    evidence_reason: null,
    created_by: "browser-fixture",
    idempotency_key: `scope-${source}`,
    created_at: "2026-09-10T16:00:00Z",
    updated_at: "2026-09-10T16:00:00Z",
  });
  await page.route("**/api/context", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ scope: { scope_id: "browser-fixture", display_name: "Browser fixture", environment: "synthetic_demo", broker_account_binding: "not_applicable" }, health: { live: true, ready: true } }) }));
  await page.route("**/api/market-data/datasets**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      items: [{ asset_class: "stock", symbol: "AAPL", timeframe: "1Min", source: "alpaca", first_ts: "2026-09-10T09:30:00Z", last_ts: "2026-09-10T16:00:00Z", bar_count: 100 }],
      page: { limit: 500, offset: 0, total: 1, has_more: false },
      discovery: { provider: "alpaca", catalogue_completeness: "complete", catalogue_freshness: "fresh", can_discover: true, can_load: true, load_capability: "load_capable", reason: "Fixture evidence" },
    }),
  }));
  await page.route("**/api/market-data/evidence**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ scope: { asset_class: "stock", symbols: ["AAPL"], timeframe: "1Min", interval: "1Min", bar_type: "trade_bar", start: "2026-09-10T09:30:00Z", end: "2026-09-10T16:00:00Z", provider: "alpaca", source_policy: "alpaca" }, state: "complete", evidence_reason: "Fixture evidence", manifest: null, quality: null, coverage: { total_bars: 100 }, findings: [], warnings: [], provenance: ["research://fixture/manifest"] }),
  }));
  await page.route("**/api/market-data/bars**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [{ symbol: "AAPL", timeframe: "1Min", ts: "2026-09-10T09:30:00Z", open: 100, high: 101, low: 99, close: 100.5, volume: 10, source: "alpaca" }], page: { limit: 50000, offset: 0, total: 1, has_more: false } }),
  }));
  await page.route("**/api/data-scopes**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [savedScope(firstId, "alpaca"), savedScope(secondId, "polygon")], page: { limit: 100, offset: 0, total: 2, has_more: false } }),
  }));
  await page.route("**/api/data-scope-comparisons", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      state: "ready",
      comparison_dimensions: ["source", "window"],
      comparable_pair_count: 1,
      excluded_pair_count: 0,
      alternatives: [
        { scope: savedScope(firstId, "alpaca"), evidence: { state: "complete", evidence_reason: "Alpaca evidence", scope: {}, manifest: null, quality: null, coverage: { total_bars: 100 }, findings: [], warnings: [], provenance: ["research://fixture/alpaca"] }, eligible: true, exclusion_reasons: [] },
        { scope: savedScope(secondId, "polygon"), evidence: { state: "complete", evidence_reason: "Polygon evidence", scope: {}, manifest: null, quality: null, coverage: { total_bars: 90 }, findings: [], warnings: [], provenance: ["research://fixture/polygon"] }, eligible: true, exclusion_reasons: [] },
      ],
      pairs: [{ left_scope_id: firstId, right_scope_id: secondId, eligible: true, equal_dimensions: ["asset_class", "symbols", "universe", "timeframe", "interval", "research_role", "window"], varied_dimensions: ["source"], exclusion_reasons: [], differences: { source: { left: { provider: "alpaca" }, right: { provider: "polygon" } }, coverage: { total_bars: { left: 100, right: 90, delta: -10 } } } }],
    }),
  }));

  await page.goto("/data");
  await expect(page.getByRole("heading", { name: "Compare saved data scopes" })).toBeVisible();
  await expect(page.getByRole("checkbox")).toHaveCount(2);
  await page.getByRole("button", { name: "Compare selected scopes" }).click();
  await expect(page.getByText("Comparison state: ready")).toBeVisible();
  await expect(page.getByText("Comparable alternatives")).toBeVisible();
  await expect(page.getByRole("heading", { name: "alpaca exact scope" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "polygon exact scope" })).toBeVisible();
});
