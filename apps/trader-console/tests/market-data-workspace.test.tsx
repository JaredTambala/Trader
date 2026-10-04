import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BarsResponse, MarketDataset, SavedDataScope } from "../src/features/market-data/client";
import { MarketDataWorkspace } from "../src/features/market-data/market-data-workspace";
import { loadMarketBars, loadMarketDataEvidence, loadMarketDatasets, loadSavedDataScope, loadSavedDataScopes, revalidateSavedDataScope, saveDataScope } from "../src/features/market-data/client";

vi.mock("../src/features/market-data/chart", () => ({
  MarketChart: ({ bars }: { bars: unknown[] }) => <div data-testid="market-chart">chart ({bars.length} bars)</div>,
}));
vi.mock("../src/features/market-data/client", () => ({
  loadMarketDatasets: vi.fn(),
  loadMarketBars: vi.fn(),
  loadMarketDataEvidence: vi.fn(),
  loadSavedDataScope: vi.fn(),
  loadSavedDataScopes: vi.fn(),
  revalidateSavedDataScope: vi.fn(),
  saveDataScope: vi.fn(),
  datasetKey: (dataset: MarketDataset) => [dataset.asset_class, dataset.symbol, dataset.timeframe, dataset.source ?? ""].join("|"),
}));

const dataset: MarketDataset = {
  asset_class: "stock", symbol: "AAPL", timeframe: "1Min", source: "alpaca",
  first_ts: "2026-09-10T09:30:00Z", last_ts: "2026-09-10T16:00:00Z", bar_count: 2,
};
const bars: BarsResponse = {
  items: [
    { symbol: "AAPL", timeframe: "1Min", ts: "2026-09-10T09:30:00Z", open: 100, high: 102, low: 99, close: 101, volume: 500, source: "alpaca" },
    { symbol: "AAPL", timeframe: "1Min", ts: "2026-09-10T09:31:00Z", open: 101, high: 103, low: 100, close: 102, volume: 600, source: "alpaca" },
  ],
  page: { limit: 50000, offset: 0, total: 2, has_more: false },
};

beforeEach(() => {
  vi.mocked(loadMarketDatasets).mockReset().mockResolvedValue({ items: [dataset], page: { limit: 500, offset: 0, total: 1, has_more: false } });
  vi.mocked(loadMarketBars).mockReset().mockResolvedValue(bars);
  vi.mocked(loadMarketDataEvidence).mockReset().mockResolvedValue({ state: "complete", evidence_reason: "Evidence matches.", scope: { asset_class: "stock", symbols: ["AAPL"], timeframe: "1Min", interval: "1Min", bar_type: "trade_bar", start: "2026-09-10T09:30:00Z", end: "2026-09-10T16:00:00Z" }, warnings: [], findings: [], provenance: [], coverage: {}, manifest: null, quality: null, provider: "alpaca", source_policy: "alpaca" });
  vi.mocked(loadSavedDataScope).mockReset();
  vi.mocked(loadSavedDataScopes).mockReset().mockResolvedValue({ items: [], page: { limit: 100, offset: 0, total: 0, has_more: false } });
  vi.mocked(revalidateSavedDataScope).mockReset();
  vi.mocked(saveDataScope).mockReset();
});

describe("market data exploration workflow", () => {
  it("discovers a dataset, requests its UTC range, and exposes chart plus source rows", async () => {
    render(<MarketDataWorkspace />);
    expect(screen.getByRole("heading", { name: "Market data" })).toBeVisible();
    expect(screen.getByText(/stocks and crypto in OHLCV format/)).toBeVisible();
    expect(await screen.findByRole("heading", { name: "AAPL · 1Min" })).toBeVisible();
    expect(await screen.findByTestId("market-chart")).toHaveTextContent("2 bars");
    expect(screen.getByText("2026-09-10 09:30:00 UTC")).toBeVisible();
    expect(screen.getByText("500")).toBeVisible();
    expect(vi.mocked(loadMarketBars).mock.calls[0]?.[1]).toMatchObject({ asset_class: "stock", symbol: "AAPL", timeframe: "1Min", source: "alpaca" });
  });

  it("shows a truthful empty result when the selected range has no rows", async () => {
    vi.mocked(loadMarketBars).mockResolvedValue({ items: [], page: { limit: 50000, offset: 0, total: 0, has_more: false } });
    render(<MarketDataWorkspace />);
    expect(await screen.findByText(/No bars match this symbol/)).toBeVisible();
    expect(screen.queryByTestId("market-chart")).not.toBeInTheDocument();
  });

  it("shows unavailable discovery evidence when the database has no datasets", async () => {
    vi.mocked(loadMarketDatasets).mockResolvedValue({
      items: [],
      page: { limit: 500, offset: 0, total: 0, has_more: false },
      discovery: {
        provider: "alpaca",
        catalogue_completeness: "unavailable",
        catalogue_freshness: "unknown",
        can_discover: false,
        can_load: false,
        load_capability: "unavailable",
        reason: "No stored dataset slices are available for this Console scope.",
      },
    });

    render(<MarketDataWorkspace />);

    expect(await screen.findByText("Catalogue: unavailable")).toBeVisible();
    expect(screen.getByText("Discovery: unavailable")).toBeVisible();
    expect(screen.getByText("Loading: unavailable")).toBeVisible();
    expect(screen.getByText("No stored dataset slices are available for this Console scope.")).toBeVisible();
  });

  it("keeps complete catalogue and load capability as separate visible states", async () => {
    vi.mocked(loadMarketDatasets).mockResolvedValue({
      items: [dataset],
      page: { limit: 500, offset: 0, total: 1, has_more: false },
      discovery: {
        provider: "alpaca",
        catalogue_completeness: "complete",
        catalogue_freshness: "fresh",
        can_discover: true,
        can_load: true,
        load_capability: "load_capable",
        reason: "Provider receipt covers the requested scope.",
      },
    });

    render(<MarketDataWorkspace />);

    expect(await screen.findByText("Catalogue: complete")).toBeVisible();
    expect(screen.getByText("Freshness: fresh")).toBeVisible();
    expect(screen.getByText("Discovery: available")).toBeVisible();
    expect(screen.getByText("Loading: capable")).toBeVisible();
    expect(screen.getByText("Provider receipt covers the requested scope.")).toBeVisible();
  });

  it("applies a range and retries a failed bars request", async () => {
    vi.mocked(loadMarketBars).mockRejectedValueOnce(new Error("Console database is unavailable")).mockResolvedValueOnce(bars);
    const user = userEvent.setup();
    render(<MarketDataWorkspace />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Console database is unavailable");
    await user.click(screen.getByRole("button", { name: "Retry bars" }));
    expect(await screen.findByTestId("market-chart")).toBeVisible();
    const from = screen.getByLabelText("From UTC");
    await user.clear(from);
    await user.type(from, "2026-09-10T10:00");
    await user.click(screen.getByRole("button", { name: "Apply range" }));
    await waitFor(() => expect(vi.mocked(loadMarketBars).mock.calls.at(-1)?.[1]).toMatchObject({ start: "2026-09-10T10:00:00.000Z" }));
  });

  it("cancels discovery when the workspace unmounts", async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(loadMarketDatasets).mockImplementation((_requestSignal) => {
      signal = _requestSignal;
      return new Promise<never>(() => {});
    });
    const view = render(<MarketDataWorkspace />);
    await waitFor(() => expect(loadMarketDatasets).toHaveBeenCalled());
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("saves and reopens the exact selected scope with its evidence state", async () => {
    const saved: SavedDataScope = {
      saved_scope_id: "11111111-1111-4111-8111-111111111111",
      scope_id: "paper-primary",
      revision: 1,
      fingerprint: "a".repeat(64),
      name: "AAPL research slice",
      asset_class: "stock",
      symbols: ["AAPL"],
      universe: null,
      timeframe: "1Min",
      interval: "1Min",
      start: "2026-09-10T09:30:00Z",
      end: "2026-09-10T16:00:00Z",
      source_policy: { provider: "alpaca", source: "alpaca", allow_fallback: false },
      research_role: "backtest_authoring",
      manifest_artifact_id: "manifest-1",
      quality_artifact_id: "quality-1",
      evidence_status: "active",
      evidence_reason: null,
      created_by: "console-operator",
      idempotency_key: "key-1",
      created_at: "2026-09-10T16:01:00Z",
      updated_at: "2026-09-10T16:01:00Z",
    };
    vi.mocked(saveDataScope).mockResolvedValue(saved);
    vi.mocked(loadSavedDataScope).mockResolvedValue(saved);
    const user = userEvent.setup();
    render(<MarketDataWorkspace />);
    await screen.findByRole("heading", { name: "AAPL · 1Min" });
    await user.type(screen.getByLabelText("Manifest artifact reference"), "manifest-1");
    await user.type(screen.getByLabelText("Quality artifact reference"), "quality-1");
    await user.click(screen.getByRole("button", { name: "Save exact scope" }));
    expect(await screen.findByText(/Saved exact scope/)).toBeVisible();
    expect(vi.mocked(saveDataScope)).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
      manifest_artifact_id: "manifest-1",
      quality_artifact_id: "quality-1",
      start: "2026-09-10T09:30:00.000Z",
      end: "2026-09-10T16:00:00.000Z",
    }));
    await user.selectOptions(screen.getByLabelText("Reopen saved scope"), saved.saved_scope_id);
    expect(await screen.findByText("Reopened exact scope (active).")).toBeVisible();
    expect(vi.mocked(loadSavedDataScope)).toHaveBeenCalledWith(expect.anything(), saved.saved_scope_id);
  });
});
