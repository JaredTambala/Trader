import createClient from "openapi-fetch";
import type { components, paths } from "../../generated/api";

const client = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "" : window.location.origin,
  cache: "no-store",
});

export type AgentSessionProjection = components["schemas"]["AgentSessionProjection"];
export type AgentSessionCommand = components["schemas"]["AgentSessionCommandRequest"]["command"];
export type AgentSessionCommandRecord = components["schemas"]["AgentSessionCommandRecord"];

export async function loadAgentSession(sessionId: string, signal?: AbortSignal) {
  const result = await client.GET("/api/agent-sessions/{session_id}", {
    params: { path: { session_id: sessionId } },
    signal,
  });
  if (!result.response.ok || !result.data) {
    throw new Error("Agent session evidence could not be loaded.");
  }
  return result.data;
}

export async function submitAgentSessionCommand(
  sessionId: string,
  command: AgentSessionCommand,
  reason: string,
  operatorAnswer: string,
  approved: boolean,
  signal?: AbortSignal,
) {
  const result = await client.POST("/api/agent-sessions/{session_id}/commands", {
    params: { path: { session_id: sessionId } },
    body: {
      command,
      idempotency_key: crypto.randomUUID(),
      reason: reason || null,
      operator_answer: operatorAnswer || null,
      approved: command === "resume" ? approved : undefined,
    },
    signal,
  });
  if (!result.response.ok || !result.data) {
    throw new Error("Agent session command could not be queued.");
  }
  return result.data;
}
