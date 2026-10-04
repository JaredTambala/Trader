import createClient from "openapi-fetch";
import type { components, paths } from "../../generated/api";

const client = createClient<paths>({ baseUrl: typeof window === "undefined" ? "" : window.location.origin, cache: "no-store" });

export type PaperRuntimeOperations = components["schemas"]["PaperRuntimeOperations"];

export async function loadPaperRuntime(signal: AbortSignal) {
  const result = await client.GET("/api/paper/runtime", { signal });
  if (!result.response.ok || !result.data) {
    throw new Error("Paper runtime evidence could not be loaded.");
  }
  return result.data;
}
