import { test, expect } from "@playwright/test";

/**
 * Qualification against a caller-provided, isolated clone of a real Trader database.
 * This is deliberately not part of the synthetic Console demo workflow.
 */
test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

test("the workspace renders real Alpaca-backed rows through the API", async ({ page }) => {
  test.skip(process.env.CONSOLE_REAL_DATA_TESTS !== "1");
  const realExpect = expect.configure({ timeout: 15_000 });
  const responses = new Map<string, number>();
  page.on("response", (response) => {
    const pathname = new URL(response.url()).pathname;
    if (pathname === "/api/market-data/datasets" || pathname === "/api/market-data/bars") responses.set(pathname, response.status());
  });

  await page.goto("/data");
  const dataset = page.getByRole("combobox", { name: "Market dataset" });
  await realExpect(dataset).toHaveValue(/\|alpaca$/);
  await realExpect(page.getByRole("img", { name: "OHLC candlestick and volume chart" })).toBeVisible();
  await realExpect(page.getByText(/matching bars$/)).toBeVisible();
  await realExpect(page.getByRole("heading", { name: "Loaded bar sample" })).toBeVisible();
  await realExpect.poll(() => responses.get("/api/market-data/datasets")).toBe(200);
  await realExpect.poll(() => responses.get("/api/market-data/bars")).toBe(200);
});
