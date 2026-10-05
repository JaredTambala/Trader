import { afterEach, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

async function withCommandResponse() {
  const fetchMock = vi.fn().mockResolvedValue(
    Response.json({
      command_id: "command-1",
      session_id: "session-1",
      command: "resume",
      status: "requested",
      requested_by: "operator-1",
      requested_at: "2026-10-05T12:00:00Z",
      idempotency_key: "idempotency-1",
      reason: null,
      operator_answer: "continue",
      approved: true,
      outcome_code: null,
      outcome_message: null,
      completed_at: null,
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  vi.resetModules();
  return { fetchMock, submitAgentSessionCommand: (await import("../src/features/agent-sessions/client")).submitAgentSessionCommand };
}

async function requestBody(fetchMock: ReturnType<typeof vi.fn>) {
  const request = fetchMock.mock.calls[0]?.[0];
  if (!(request instanceof Request)) throw new Error("expected openapi-fetch to issue a Request");
  return JSON.parse(await request.text()) as Record<string, unknown>;
}

it("sends an explicit approval decision when resuming a session", async () => {
  const { fetchMock, submitAgentSessionCommand } = await withCommandResponse();

  await submitAgentSessionCommand("session-1", "resume", "reviewed", "continue", true);

  await expect(requestBody(fetchMock)).resolves.toMatchObject({
    command: "resume",
    operator_answer: "continue",
    approved: true,
  });
});

it("omits resume approval for commands that cannot apply it", async () => {
  const { fetchMock, submitAgentSessionCommand } = await withCommandResponse();

  await submitAgentSessionCommand("session-1", "interrupt", "pause", "", false);

  const body = await requestBody(fetchMock);
  expect(body.command).toBe("interrupt");
  expect(body).not.toHaveProperty("approved");
});
