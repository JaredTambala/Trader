import { test, expect } from "@playwright/test";

const session = {
  session_id: "session-1",
  session_digest: "a".repeat(64),
  operator_id: "human:jared",
  objective: "Compare qualified data alternatives.",
  success_definition: "A bounded evidence-backed decision.",
  status: "running",
  model_profile_id: "development-model-v1",
  agent_program_ids: ["research-coordinator-v1"],
  tool_catalog_id: "research-catalogue-v1",
  scope_summary: { scope_id: "scope-1", timeframe: "1Min" },
  budget_limits: { max_model_calls: 20, max_tool_calls: 40, max_tokens: 10000, max_duration_seconds: 600, max_mutations: 0, max_revisions: 2, concurrency_limit: 2 },
  budget_used: { model_calls: 1, tool_calls: 2, tokens: 120, duration_ms: 500, mutations: 0, revisions: 0 },
  agenda_summary: "Review the qualified data alternatives.",
  delegations: [],
  events: [],
  evidence_refs: [],
  pending_interrupt: null,
  terminal_decision: null,
  checkpoint_sequence: 2,
  command_ids: [],
};

test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

test("agent workspace keeps lifecycle commands human-owned and typed", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const requests: Array<{ command: string; approved?: boolean }> = [];
  await page.route("**/api/agent-sessions/session-1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(session) }));
  await page.route("**/api/agent-sessions/session-1/commands", async (route) => {
    const body = route.request().postDataJSON() as { command: string; approved?: boolean };
    requests.push(body);
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        command_id: `command-${requests.length}`,
        session_id: "session-1",
        command: body.command,
        idempotency_key: `intent-${requests.length}`,
        requested_by: "human:jared",
        status: "requested",
        reason: null,
        operator_answer: body.command === "resume" ? "Decline and review." : null,
        approved: body.approved ?? null,
        outcome_code: null,
        outcome_message: null,
        attempt: 0,
        worker_id: null,
        started_at: null,
        heartbeat_at: null,
        lease_expires_at: null,
        requested_at: "2026-10-05T00:00:00Z",
        completed_at: null,
      }),
    });
  });

  await page.goto("/agents/session-1");
  await expect(page.getByRole("heading", { name: "Research workspace" })).toBeVisible();
  await expect(page.getByText("Compare qualified data alternatives.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByRole("status")).toContainText("interrupt");
  expect(requests[0]).toMatchObject({ command: "interrupt" });
  expect(requests[0]).not.toHaveProperty("approved");

  await page.getByLabel("Answer to pending interrupt (required for resume)").fill("Decline and review.");
  await page.getByRole("combobox", { name: "Resume decision" }).selectOption("false");
  await page.getByRole("button", { name: "resume" }).click();
  await expect(page.getByRole("status")).toContainText("resume");
  expect(requests[1]).toMatchObject({ command: "resume", approved: false });
});
