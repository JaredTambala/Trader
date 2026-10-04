import { afterEach, expect, it, vi } from "vitest";

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); });

async function withResponse(response: Response) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
  // openapi-fetch captures fetch at construction time.
  vi.resetModules();
  return import("../src/features/connection/client");
}

it("consumes the typed HTTP 503 body rather than replacing it with a generic failure", async () => {
  const payload = { status: "unavailable", scope_id: "console-demo", issues: ["database_unavailable"] };
  const { loadReadiness } = await withResponse(Response.json(payload, { status: 503 }));
  expect(await loadReadiness(new AbortController().signal)).toEqual(payload);
});

it("treats an HTML proxy failure as unavailable rather than successful readiness", async () => {
  const { loadReadiness } = await withResponse(new Response("Bad gateway", { status: 502 }));
  await expect(loadReadiness(new AbortController().signal)).rejects.toThrow();
});
