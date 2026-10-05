import createClient from "openapi-fetch";
import type { components, paths } from "../../generated/api";

const client = createClient<paths>({ baseUrl: typeof window === "undefined" ? "" : window.location.origin, cache: "no-store" });

export type PaperRuntimeOperations = components["schemas"]["PaperRuntimeOperations"];
export type PaperOperatorCommand = components["schemas"]["PaperOperatorCommandRequest"]["command"];
export type PaperOperatorCommandRecord = components["schemas"]["PaperOperatorCommandRecord"];

export async function loadPaperRuntime(signal: AbortSignal) {
  const result = await client.GET("/api/paper/runtime", { signal });
  if (!result.response.ok || !result.data) {
    throw new Error("Paper runtime evidence could not be loaded.");
  }
  return result.data;
}

export async function submitPaperCommand(
  command: PaperOperatorCommand,
  admissionId: string,
  reason: string,
  signal: AbortSignal,
) {
  const result = await client.POST("/api/paper/commands", {
    body: {
      command,
      admission_id: admissionId,
      idempotency_key: crypto.randomUUID(),
      reason: reason || null,
    },
    signal,
  });
  if (!result.response.ok || !result.data) {
    throw new Error("Paper command could not be queued.");
  }
  return result.data;
}
