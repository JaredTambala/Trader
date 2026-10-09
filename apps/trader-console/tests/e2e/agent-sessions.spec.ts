import { test, expect } from "@playwright/test";

const initialSession = {
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
  available_commands: ["inspect", "interrupt", "cancel"],
  command_ids: [],
  hidden_prompt: "PRIVATE MODEL PROMPT MUST NOT RENDER",
  raw_tool_payload: "PRIVATE TOOL BODY MUST NOT RENDER",
};

test.beforeEach(() => {
  expect(process.env.CONSOLE_TEST_STACK).toBe("1");
});

test("agent workspace keeps lifecycle commands human-owned and typed", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const requests: Array<{ command: string; approved?: boolean }> = [];
  const session = structuredClone(initialSession);
  await page.route("**/api/agent-sessions/session-1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(session) }));
  await page.route("**/api/agent-sessions/session-1/commands", async (route) => {
    const body = route.request().postDataJSON() as { command: string; approved?: boolean };
    requests.push(body);
    if (body.command === "interrupt") {
      Object.assign(session, {
        status: "awaiting_operator",
        available_commands: ["inspect", "resume", "cancel"],
        pending_interrupt: { kind: "operator_pause", question: "Review the qualified evidence.", requested_action: "resume or cancel" },
      });
    }
    if (body.command === "resume") {
      Object.assign(session, {
        status: "completed",
        available_commands: ["inspect"],
        pending_interrupt: null,
        terminal_decision: {
          branch_id: "branch-1", sequence: 3, status: "completed", action: "conclude",
          summary: "Qualified evidence is complete.", blockers: [],
          evidence_refs: [{ artifact_type: "dataset_manifest", artifact_id: "manifest-1", domain_owner: "Data", uri: "research://postgres/dataset_manifest/manifest-1", source_hash: "b".repeat(64) }],
        },
      });
    }
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
  await expect(page.getByText("development-model-v1 · research-catalogue-v1")).toBeVisible();
  await expect(page.getByText("Review the qualified data alternatives.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Authority and recovery" })).toBeVisible();
  await expect(page.getByText("PRIVATE MODEL PROMPT MUST NOT RENDER")).toHaveCount(0);
  await expect(page.getByText("PRIVATE TOOL BODY MUST NOT RENDER")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "resume" })).toBeDisabled();
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByRole("status")).toContainText("interrupt");
  expect(requests[0]).toMatchObject({ command: "interrupt" });
  expect(requests[0]).not.toHaveProperty("approved");

  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(page.getByText("Operator input requested: Review the qualified evidence.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause" })).toBeDisabled();

  await page.getByLabel("Answer to pending interrupt (required for resume)").fill("Decline and review.");
  await page.getByRole("combobox", { name: "Resume decision" }).selectOption("false");
  await page.getByRole("button", { name: "resume" }).click();
  await expect(page.getByText("Command resume is")).toContainText("resume");
  expect(requests[1]).toMatchObject({ command: "resume", approved: false });
  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(page.getByRole("heading", { name: "Terminal lineage" })).toBeVisible();
  await expect(page.getByText("research://postgres/dataset_manifest/manifest-1")).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "cancel" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "inspect" })).toBeEnabled();
});

test("agent workspace keeps concurrent specialist outcomes and exact handoff revisions across refresh", async ({ page }) => {
  test.skip(process.env.CONSOLE_TEST_SCENARIO !== "healthy");
  const outcomes = ["complete", "partial", "failed", "blocked", "stale", "unavailable"];
  const delegation = (outcome: string, index: number) => ({
    branch_id: `branch-${index}`,
    delegation_id: `delegation-${index}`,
    attempt_id: `attempt-${index}`,
    role: "data_research",
    status: outcome === "complete" ? "completed" : "blocked",
    sequence: index,
    summary: `Branch ${outcome}`,
    evidence_refs: [{
      artifact_type: "dataset_manifest",
      artifact_id: `manifest-${index}`,
      domain_owner: "Data",
      uri: `research://postgres/dataset_manifest/manifest-${index}`,
      revision: index + 1,
      status: outcome === "complete" ? "available" : outcome === "stale" ? "stale" : "unavailable",
      source_hash: "b".repeat(64),
    }],
    blockers: ["Review specialist evidence."],
    next_actions: ["review"],
    specialist_status: outcome,
    handoff: {
      branch_id: `branch-${index}`,
      delegation_id: `delegation-${index}`,
      attempt_id: `attempt-${index}`,
      owner: "Data Specialist",
      status: outcome,
      digest: "c".repeat(64),
      artifact_refs: [{
        artifact_type: "dataset_manifest",
        artifact_id: `manifest-${index}`,
        domain_owner: "Data",
        uri: `research://postgres/dataset_manifest/manifest-${index}`,
        revision: index + 1,
        status: outcome === "complete" ? "available" : outcome === "stale" ? "stale" : "unavailable",
        source_hash: "b".repeat(64),
      }],
      blockers: ["Review specialist evidence."],
    },
  });
  const first = { ...structuredClone(initialSession), session_id: "session-uj07", delegations: outcomes.map(delegation) };
  const recovered = structuredClone(first);
  const recoveredUnavailable = recovered.delegations[5];
  if (!recoveredUnavailable || !recoveredUnavailable.handoff) throw new Error("missing unavailable branch fixture");
  const recoveredHandoffRef = recoveredUnavailable.handoff.artifact_refs[0];
  const recoveredEvidenceRef = recoveredUnavailable.evidence_refs[0];
  if (!recoveredHandoffRef || !recoveredEvidenceRef) throw new Error("missing unavailable artifact fixture");
  recoveredHandoffRef.status = "incompatible";
  recoveredEvidenceRef.status = "incompatible";
  let reads = 0;
  await page.route("**/api/agent-sessions/session-uj07", async (route) => {
    reads += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(reads > 1 ? recovered : first) });
  });

  await page.goto("/agents/session-uj07");
  await expect(page.getByText("Branch complete", { exact: true })).toBeVisible();
  await expect(page.getByText("Branch partial", { exact: true })).toBeVisible();
  await expect(page.getByText("Branch unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText("revision 1", { exact: false })).toBeVisible();
  await expect(page.getByText(/research:\/\/postgres\/dataset_manifest\/manifest-5/)).toBeVisible();

  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(page.getByText("incompatible", { exact: true }).last()).toBeVisible();
  await expect(page.getByText(/Handoff owner: Data Specialist/)).toHaveCount(6);
});
