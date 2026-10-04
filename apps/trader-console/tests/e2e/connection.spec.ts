import { test, expect } from "@playwright/test";

// This suite is launched by the test-owned Python stack, never against arbitrary servers.
test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

test("a reviewer sees the real synthetic context and database compatibility", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const apiResponses: number[] = [];
  page.on("response", response => {
    if (["/api/context", "/health/live", "/health/ready"].includes(new URL(response.url()).pathname)) apiResponses.push(response.status());
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Local Console demo" })).toBeVisible();
  await expect(page.getByText("Synthetic demo", { exact: true })).toBeVisible();
  await expect(page.getByText("Compatible", { exact: true })).toBeVisible();
  await expect(page.getByText("Not applicable", { exact: true })).toBeVisible();
  expect(apiResponses).toEqual([200, 200, 200]);
  const refresh = page.getByRole("button", { name: /Refresh/ });
  for (let index = 0; index < 10 && !(await refresh.evaluate((element) => document.activeElement === element)); index += 1) await page.keyboard.press("Tab");
  await expect(refresh).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: /Refresh/ })).toBeEnabled();
  await page.screenshot({ path: "test-results/connection-desktop.png", fullPage: true });
});

test("the same real journey works on a narrow screen", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("Compatible", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/connection-mobile.png", fullPage: true });
});

test("real schema or database failure retains context and explains the problem", async ({ page }) => {
  const scenario = process.env.CONSOLE_TEST_SCENARIO;
  test.skip(scenario !== "schema" && scenario !== "database");
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Retry/ })).toBeEnabled({ timeout: 15_000 });
  await expect(page.getByText("Local Console demo", { exact: true })).toBeVisible();
  await expect(page.getByText("Available", { exact: true })).toBeVisible();
  await expect(page.getByText("Unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText(scenario === "schema" ? /missing its Console schema metadata/ : /cannot reach the database/)).toBeVisible();
  await page.getByRole("button", { name: /Retry/ }).click();
  await expect(page.getByRole("button", { name: /Retry/ })).toBeEnabled({ timeout: 15_000 });
});

test("a stopped API cannot invent context or successful readiness", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "api");
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Retry/ })).toBeEnabled({ timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Context unavailable" })).toBeVisible();
  await expect(page.getByText("Unknown environment", { exact: true })).toBeVisible();
  await expect(page.getByText("Compatible", { exact: true })).toHaveCount(0);
});
