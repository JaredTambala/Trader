import { test, expect } from "@playwright/test";

test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

test("the real worker result is reviewable and records a human decision", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "execution");
  const runId = process.env.CONSOLE_TEST_EXECUTION_RUN_ID;
  expect(runId).toBeTruthy();

  await page.goto(`/backtests?experiment_id=standalone_backtests&run_id=${encodeURIComponent(runId ?? "")}`);
  await expect(page.getByRole("heading", { name: "Understand one run" })).toBeVisible();
  await expect(page.getByText("Completed", { exact: true })).toBeVisible();
  await expect(page.getByText(runId ?? "", { exact: true })).toBeVisible();
  await expect(page.getByText("Scope fingerprint", { exact: true })).toBeVisible();
  await expect(page.getByText("full_fill", { exact: true })).toBeVisible();
  await expect(page.getByText("Executed trades", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Claims and limitations" })).toBeVisible();
  await expect(page.getByText("available", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose what happens next" })).toBeVisible();

  await page.getByRole("textbox", { name: "Qualified data artifact ID" }).fill("qualification-manifest");
  await page.getByRole("textbox", { name: "Implementation artifact ID" }).fill("qualification-implementation");
  await page.getByRole("textbox", { name: "Decision rationale" }).fill("The bounded fixture is useful evidence but does not support advancement.");
  await page.getByRole("textbox", { name: "Decision limitations" }).fill("Single deterministic fixture window");
  await page.getByRole("button", { name: "Record decision" }).click();
  await expect(page.getByText("Revision 1", { exact: true })).toBeVisible();
  await expect(page.getByText("The bounded fixture is useful evidence but does not support advancement.", { exact: true })).toBeVisible();
});
