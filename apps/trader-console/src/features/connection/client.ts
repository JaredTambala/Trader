import createClient from "openapi-fetch";
import type { paths } from "../../generated/api";

// Relative URLs keep the browser on the frontend origin; Next proxies to the API.
export const client = createClient<paths>({ baseUrl: typeof window === "undefined" ? "" : window.location.origin, cache: "no-store" });

export type Context = NonNullable<Awaited<ReturnType<typeof loadContext>>>;

export async function loadContext(signal: AbortSignal) {
  const { data } = await client.GET("/api/context", { signal });
  if (!data) throw new Error("Configured context is unavailable.");
  return data;
}

export async function loadLiveness(signal: AbortSignal) {
  const { data } = await client.GET("/health/live", { signal });
  if (data?.status !== "alive") throw new Error("API is unavailable.");
  return data;
}

export async function loadReadiness(signal: AbortSignal) {
  const { data, error, response } = await client.GET("/health/ready", { signal });
  if (response.status === 200 && data?.status === "ready") return data;
  if (response.status === 503 && error?.status === "unavailable") return error;
  throw new Error("Database status could not be checked.");
}
