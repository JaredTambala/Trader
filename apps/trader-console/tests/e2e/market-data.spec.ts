import { test, expect } from "@playwright/test";

test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

test("the chart workspace selects a UTC range and exposes a bounded data window", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const barRequests: URL[] = [];
  await page.route("**/api/market-data/datasets**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      items: [
        { asset_class: "stock", symbol: "AAPL", timeframe: "1Min", source: "alpaca", first_ts: "2026-09-10T09:30:00Z", last_ts: "2026-09-10T16:00:00Z", bar_count: 60000 },
        { asset_class: "stock", symbol: "MSFT", timeframe: "1Min", source: "alpaca", first_ts: "2026-09-10T09:30:00Z", last_ts: "2026-09-10T16:00:00Z", bar_count: 60000 },
      ],
      page: { limit: 500, offset: 0, total: 2, has_more: false },
    }),
  }));
  await page.route("**/api/market-data/bars**", (route) => {
    const url = new URL(route.request().url());
    barRequests.push(url);
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [{ symbol: url.searchParams.get("symbol"), timeframe: "1Min", ts: "2026-09-10T09:30:00Z", open: 100, high: 102, low: 99, close: 101, volume: 500, source: "alpaca" }],
        page: { limit: 50000, offset: Number(url.searchParams.get("offset") ?? 0), total: 60000, has_more: true },
      }),
    });
  });

  await page.goto("/data");
  const dataset = page.getByRole("combobox", { name: "Market dataset" });
  await dataset.selectOption("stock|MSFT|1Min|alpaca");
  await expect(page.getByRole("heading", { name: "MSFT · 1Min" })).toBeVisible();
  await expect(page.getByRole("img", { name: "OHLC candlestick and volume chart" })).toBeVisible();
  await expect(page.getByText("2026-09-10 09:30:00 UTC")).toBeVisible();
  await expect(page.getByText("1 of 60,000 bars loaded")).toBeVisible();

  await page.getByLabel("From UTC").fill("2026-09-10T10:00");
  await page.getByRole("button", { name: "Apply range" }).click();
  await expect.poll(() => barRequests.at(-1)?.searchParams.get("start")).toBe("2026-09-10T10:00:00.000Z");
  await expect.poll(() => barRequests.at(-1)?.searchParams.get("limit")).toBe("50000");
  await page.getByRole("button", { name: "Next window" }).click();
  await expect.poll(() => barRequests.at(-1)?.searchParams.get("offset")).toBe("50000");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
