import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BacktestAuthoringWorkspace } from "../src/features/backtest-authoring/backtest-authoring-workspace";
import { createDefinition, loadCatalogue, loadExecution, loadSavedDataScope, preflight, submitExecution } from "../src/features/backtest-authoring/client";

vi.mock("../src/features/backtest-authoring/client", () => ({
  createDefinition: vi.fn(),
  loadCatalogue: vi.fn(),
  loadSavedDataScope: vi.fn(),
  loadExecution: vi.fn(),
  preflight: vi.fn(),
  submitExecution: vi.fn(),
}));

const catalogue = {
  catalogue_version: "standard-1",
  strategy_profiles: [{
    kind: "strategy", profile_id: "bollinger_band", version: "standard-1", name: "Bollinger Band re-entry", description: "Maintained strategy.",
    parameters: [{ name: "period", type: "integer", default: 20, required: false, minimum: 2, maximum: 500, description: "Window." }],
    supported_asset_classes: ["crypto"], supported_timeframes: ["1Min"], lookback_bars: 21, evidence_requirements: ["signals"], manager_ids: [], reason_codes: [],
  }],
  risk_profiles: [{
    kind: "risk", profile_id: "max_orders_per_run", version: "standard-1", name: "Maximum orders", description: "Blocks after a limit.",
    parameters: [{ name: "limit", type: "integer", default: 100, required: false, minimum: 0, maximum: 1000, description: "Order limit." }],
    supported_asset_classes: ["crypto"], supported_timeframes: ["1Min"], lookback_bars: 0, evidence_requirements: ["risk_decisions"], manager_ids: ["max_orders_per_run"], reason_codes: ["approved", "max_orders_per_run"],
  }],
};

const preflightResponse = {
  valid: true,
  catalogue_version: "standard-1",
  definition_fingerprint: "a".repeat(64),
  normalized_definition: { symbols: ["BTC/USD"], start: "2026-06-21T00:00:00Z", end: "2026-06-21T00:30:00Z", strategy_profile_id: "bollinger_band", strategy_catalogue_version: "standard-1", strategy_parameters: { period: 20 }, risk_profile_id: "max_orders_per_run", risk_catalogue_version: "standard-1", risk_parameters: { limit: 100 }, asset_class: "crypto", timeframe: "1Min", display_name: "Local backtest", initial_cash: 100000, initial_positions: [], assumptions: { fill_model: "full_fill", latency_ms: 0, fee_fixed_per_order: 0, fee_bps: 0, fee_minimum: 0, slippage_bps: 0, allow_latest_prior_bar: true, allow_price_carry_forward: true }, resource_limits: { max_cycles: 1000000, max_bars: 5000000, timeout_seconds: 3600 }, benchmark_id: "buy_hold" },
  coverage: [{ symbol: "BTC/USD", asset_class: "crypto", timeframe: "1Min", first_ts: "2026-06-21T00:00:00Z", last_ts: "2026-06-21T00:30:00Z", bar_count: 31, required_start: "2026-06-20T23:39:00Z", requested_end: "2026-06-21T00:30:00Z", warmup_bars: 21, available: true, warmup_satisfied: true }],
  issues: [],
};
const savedScope = { saved_scope_id: "scope-1", scope_id: "console-local", revision: 1, fingerprint: "a".repeat(64), name: "Fixture scope", asset_class: "crypto", symbols: ["BTC/USD"], universe: null, timeframe: "1Min", interval: "1Min", start: "2026-06-21T00:00:00Z", end: "2026-06-21T00:30:00Z", source_policy: { provider: "fixture", source: "fixture", allow_fallback: false }, research_role: "backtest_authoring", manifest_artifact_id: "manifest-1", quality_artifact_id: "quality-1", evidence_status: "active", evidence_reason: null, created_by: "fixture", idempotency_key: "fixture", created_at: "2026-06-21T00:00:00Z", updated_at: "2026-06-21T00:00:00Z" };

const definition = { definition_id: "definition-1", scope_id: "console-local", definition_version: 1, revision: 1, fingerprint: "a".repeat(64), definition: {}, created_at: "2026-06-21T00:00:00Z", updated_at: "2026-06-21T00:00:00Z" };
const queued = { execution_id: "execution-1", scope_id: "console-local", definition_id: "definition-1", definition_revision: 1, definition_fingerprint: "a".repeat(64), idempotency_key: "key", status: "queued", attempt: 0, worker_id: null, run_id: null, processed_cycles: 0, total_cycles: 31, last_decision_at: null, heartbeat_at: null, lease_expires_at: null, created_at: "2026-06-21T00:00:00Z", started_at: null, finished_at: null, warning_summary: [], terminal_error_code: null, terminal_error_message: null };
const completed = { ...queued, status: "completed", run_id: "run-1", processed_cycles: 31, heartbeat_at: "2026-06-21T00:01:00Z", finished_at: "2026-06-21T00:02:00Z" };

beforeEach(() => {
  vi.mocked(loadCatalogue).mockResolvedValue(catalogue as never);
  vi.mocked(loadSavedDataScope).mockResolvedValue(savedScope as never);
  vi.mocked(preflight).mockResolvedValue(preflightResponse as never);
  vi.mocked(createDefinition).mockResolvedValue(definition as never);
  vi.mocked(submitExecution).mockResolvedValue(queued as never);
  vi.mocked(loadExecution).mockResolvedValue(completed as never);
});

afterEach(() => {
  window.history.replaceState(null, "", "/backtests/new");
});

describe("backtest authoring workflow", () => {
  it("preflights, saves, submits and observes terminal execution state", async () => {
    window.history.replaceState(null, "", "/backtests/new?saved_scope_id=scope-1");
    render(<BacktestAuthoringWorkspace />);
    expect(await screen.findByRole("heading", { name: "Define and run a local backtest" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Strategy profile" })).toBeVisible();
    expect(screen.getByRole("spinbutton", { name: "period" })).toHaveValue(20);

    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    expect(await screen.findByText("Preflight passed. The definition is ready to save.")).toBeVisible();
    expect(screen.getByText("a".repeat(64))).toBeVisible();
    expect(screen.getByRole("heading", { name: "Normalized definition" })).toBeVisible();
    expect(screen.getByText("Risk composition")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Save immutable definition" }));
    await waitFor(() => expect(createDefinition).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Saved revision 1" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Submit execution" }));
    expect(await screen.findByRole("heading", { name: "Completed" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open run review" })).toHaveAttribute("href", "/backtests?run_id=run-1");
    expect(loadExecution).toHaveBeenCalledWith(expect.anything(), "execution-1");
  });

  it("keeps invalid preflight explicit and does not enable persistence", async () => {
    window.history.replaceState(null, "", "/backtests/new?saved_scope_id=scope-1");
    vi.mocked(preflight).mockResolvedValue({ ...preflightResponse, valid: false, definition_fingerprint: null, issues: [{ severity: "error", code: "invalid_window", path: "end", message: "end must be after start" }], coverage: [] } as never);
    render(<BacktestAuthoringWorkspace />);
    await screen.findByRole("heading", { name: "Define and run a local backtest" });
    fireEvent.click(screen.getByRole("button", { name: "Run preflight" }));
    expect(await screen.findByText("Error: end")).toBeVisible();
    expect(screen.getByRole("button", { name: "Save immutable definition" })).toBeDisabled();
    expect(createDefinition).not.toHaveBeenCalled();
  });

  it("retries a catalogue outage without a full page reload", async () => {
    vi.mocked(loadCatalogue).mockRejectedValueOnce(new Error("catalogue unavailable"));
    render(<BacktestAuthoringWorkspace />);
    expect(await screen.findByText("catalogue unavailable")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Define and run a local backtest" })).toBeVisible();
    expect(loadCatalogue).toHaveBeenCalledTimes(2);
  });

  it("pauses polling while keeping a queued execution manually refreshable", async () => {
    window.history.replaceState(null, "", "/backtests/new?execution_id=execution-1");
    vi.mocked(loadExecution).mockResolvedValue(queued as never);
    render(<BacktestAuthoringWorkspace />);

    expect(await screen.findByRole("heading", { name: "Queued" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Stop polling" }));
    expect(screen.getByRole("button", { name: "Resume polling" })).toBeVisible();
    expect(screen.getByText("Polling is paused. Refresh manually or resume polling.")).toBeVisible();
  });
});
