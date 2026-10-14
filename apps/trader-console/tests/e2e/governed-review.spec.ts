import { readFileSync, writeFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

test.skip(
  process.env.UJ09_BROWSER_CAMPAIGN !== "1" && process.env.UJ09_REQUIRED !== "1",
  "The isolated UJ-09 campaign owns this browser scenario.",
);

test("governed blocked evidence supports a durable human choice", async ({ page }) => {
  // A selected or required campaign must fail when its fixture configuration is missing.
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
  const runId = process.env.UJ09_RUN_ID;
  const receiptPath = process.env.UJ09_BROWSER_RECEIPT;
  const phase = process.env.UJ09_BROWSER_PHASE;
  expect(runId).toBeTruthy();
  expect(receiptPath).toBeTruthy();
  expect(["create", "reopen"]).toContain(phase);

  const basisPromise = page.waitForResponse((response) =>
    new URL(response.url()).pathname === `/api/runs/${runId}/decision-basis`);
  await page.goto(`/backtests?experiment_id=standalone_backtests&run_id=${encodeURIComponent(runId ?? "")}`);
  const basisResponse = await basisPromise;
  expect(basisResponse.status()).toBe(200);
  const basis = await basisResponse.json();
  expect(basis.status).toBe("available");
  expect(basis.evidence.review_refs).toEqual([]);
  expect(basis.evidence.blocked_evidence.scientific_review_status).toBe("not_assessed");
  expect(basis.evidence.blocked_evidence.blockers).toHaveLength(2);
  await expect(page.getByText("Verified persisted evidence", { exact: true })).toBeVisible();
  await expect(page.getByText("Independent scientific review: Not assessed", { exact: true })).toBeVisible();
  const decisionPanel = page.getByRole("region", { name: "Choose what happens next" });
  await expect(decisionPanel.getByText(basis.evidence.source_run_ref.artifact_id, { exact: true })).toBeVisible();
  await expect(decisionPanel.getByText(basis.evidence.data_ref.artifact_id, { exact: true })).toBeVisible();
  await expect(decisionPanel.getByText(`Blocked outcome: ${basis.evidence.blocked_evidence.outcome_ref.artifact_id}`, { exact: true })).toBeVisible();
  await expect(decisionPanel.getByText("Unavailable — no canonical session link", { exact: true })).toBeVisible();
  await expect(decisionPanel.getByText("Unavailable — no retained graph link", { exact: true })).toBeVisible();
  await decisionPanel.getByText("Exact artifact hashes and revisions", { exact: true }).click();
  const visibleEvidence = decisionPanel.locator("pre");
  await expect(visibleEvidence).toBeVisible();
  expect(JSON.parse(await visibleEvidence.innerText())).toEqual(basis.evidence);
  await expect(page.getByRole("textbox", { name: "Qualified data artifact ID" })).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Run source hash" })).toHaveCount(0);

  if (phase === "create") {
    await page.getByRole("textbox", { name: "Decision rationale" }).fill("Reject advancement while independent scientific reviews remain unavailable.");
    await page.getByRole("textbox", { name: "Decision limitations" }).fill("Deterministic qualification does not assess scientific validity.");
    const createdPromise = page.waitForResponse((response) =>
      new URL(response.url()).pathname === `/api/runs/${runId}/next-decisions`
      && response.request().method() === "POST");
    await page.getByRole("button", { name: "Record decision", exact: true }).click();
    const response = await createdPromise;
    expect(response.status()).toBe(201);
    const request = response.request().postDataJSON();
    const record = await response.json();
    expect(record.blocked_evidence).toEqual(basis.evidence.blocked_evidence);
    expect(record.source_run_ref).toEqual(basis.evidence.source_run_ref);
    expect(record.data_ref).toEqual(basis.evidence.data_ref);
    expect(record.implementation_refs).toEqual(basis.evidence.implementation_refs);
    expect(record.revision).toBe(1);
    await expect(page.getByText("Revision 1", { exact: true })).toBeVisible();
    writeFileSync(receiptPath ?? "", JSON.stringify({ request, record, browser_version: page.context().browser()?.version() }));
  } else {
    const saved = JSON.parse(readFileSync(receiptPath ?? "", "utf8"));
    expect(basis.evidence.source_run_ref).toEqual(saved.record.source_run_ref);
    expect(basis.evidence.blocked_evidence).toEqual(saved.record.blocked_evidence);
    await expect(page.getByText("Revision 2", { exact: true })).toBeVisible();
    await expect(page.getByText("Retain the missing reviews and bound the next research attempt.", { exact: true })).toBeVisible();
  }
});
