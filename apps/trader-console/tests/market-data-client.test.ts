import { afterEach, expect, it, vi } from "vitest";

function requestUrl(call: unknown) {
  return new URL(typeof call === "string" ? call : (call as Request).url);
}

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); });

it("requests dataset discovery through the generated OpenAPI path", async () => {
  const payload = { items: [], page: { limit: 500, offset: 0, total: 0, has_more: false } };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(payload)));
  vi.resetModules();
  const { loadMarketDatasets } = await import("../src/features/market-data/client");
  await loadMarketDatasets(new AbortController().signal);
  const url = requestUrl(vi.mocked(fetch).mock.calls[0]?.[0]);
  expect(url.pathname).toBe("/api/market-data/datasets");
  expect(url.search).toContain("limit=500");
});

it("passes the selected slice and UTC range to the bars endpoint", async () => {
  const payload = { items: [], page: { limit: 50000, offset: 0, total: 0, has_more: false } };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(payload)));
  vi.resetModules();
  const { loadMarketBars } = await import("../src/features/market-data/client");
  await loadMarketBars(new AbortController().signal, {
    asset_class: "stock", symbol: "AAPL", timeframe: "1Min", source: "alpaca",
    start: "2026-09-10T09:30:00.000Z", end: "2026-09-10T16:00:00.000Z",
  });
  const url = requestUrl(vi.mocked(fetch).mock.calls[0]?.[0]);
  expect(url.pathname).toBe("/api/market-data/bars");
  expect(url.searchParams.get("asset_class")).toBe("stock");
  expect(url.searchParams.get("symbol")).toBe("AAPL");
  expect(url.searchParams.get("timeframe")).toBe("1Min");
  expect(url.searchParams.get("source")).toBe("alpaca");
  expect(url.searchParams.get("start")).toBe("2026-09-10T09:30:00.000Z");
  expect(url.searchParams.get("limit")).toBe("50000");
});

it("requests exact Data evidence through the generated OpenAPI path", async () => {
  const payload = { state: "unavailable", evidence_reason: "missing", scope: { asset_class: "stock", symbols: ["AAPL"], timeframe: "1Min", interval: "1Min", bar_type: "trade_bar", start: "2026-01-01T00:00:00Z", end: "2026-01-02T00:00:00Z" }, warnings: ["missing"], findings: [], provenance: [], coverage: {} };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(payload)));
  vi.resetModules();
  const { loadMarketDataEvidence } = await import("../src/features/market-data/client");
  await loadMarketDataEvidence(new AbortController().signal, {
    asset_class: "stock", symbols: ["AAPL", "MSFT"], timeframe: "1Min", interval: "1Min",
    bar_type: "trade_bar", provider: "alpaca", source_policy: "alpaca",
    start: "2026-01-01T00:00:00.000Z", end: "2026-01-02T00:00:00.000Z",
  });
  const url = requestUrl(vi.mocked(fetch).mock.calls[0]?.[0]);
  expect(url.pathname).toBe("/api/market-data/evidence");
  expect(url.searchParams.get("symbols")).toBe("AAPL,MSFT");
  expect(url.searchParams.get("bar_type")).toBe("trade_bar");
});

it("keeps typed service-unavailable failures retryable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ code: "database_unavailable", message: "Console database is unavailable" }, { status: 503 })));
  vi.resetModules();
  const { loadMarketBars, MarketDataRequestError } = await import("../src/features/market-data/client");
  await expect(loadMarketBars(new AbortController().signal, { asset_class: "stock", symbol: "AAPL", timeframe: "1Min" })).rejects.toBeInstanceOf(MarketDataRequestError);
});
