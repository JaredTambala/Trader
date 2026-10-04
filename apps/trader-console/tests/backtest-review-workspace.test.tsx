import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BacktestReviewWorkspace } from "../src/features/backtest-review/backtest-review-workspace";
import { loadExperimentRuns, loadExperiments, loadRiskDecisions, loadRunDetail, type RunDetail } from "../src/features/backtest-review/client";

vi.mock("../src/features/backtest-review/client", () => ({
  loadExperimentRuns: vi.fn(),
  loadExperiments: vi.fn(),
  loadRunDetail: vi.fn(),
  loadRiskDecisions: vi.fn(),
}));

const experiment = { experiment_id: "exp-bollinger", run_count: 1, latest_created_at: "2026-09-21T21:25:00Z", statuses: ["completed"], metadata_available: false };
const run = {
  experiment_run_id: "exp-run-1", experiment_id: "exp-bollinger", run_id: "run-1", session_id: "session-1", status: "completed",
  mode: "backtest", created_at: "2026-09-21T21:25:00Z", finished_at: "2026-09-21T21:26:00Z", strategy_id: "bollinger_band",
  strategy_name: "BTC/USD Bollinger Bands", strategy_version: "1", symbols: ["BTC/USD"], asset_class: "crypto", timeframe: "1Min",
  start_ts: "2026-06-21T00:00:00Z", end_ts: "2026-09-21T21:25:00Z", scope_fingerprint: "scope-1", data_scope_id: "btc-3m",
  benchmark_id: "buy_hold", variant_fingerprint: "variant-1", variant_strategy_id: "bollinger_band", variant_strategy_version: "1",
  comparison_projection_available: true, comparison_eligible: true, comparison_exclusion_reason: null,
};

const detail = {
  run,
  scope: { run_id: "run-1", scope_fingerprint: "scope-1", data_scope_id: "btc-3m", benchmark_id: "buy_hold", replay_start: run.start_ts, replay_end: run.end_ts, initial_cash: 100_000 },
  performance: { run_id: "run-1", observed_at: run.end_ts, strategy_total_return: 0.12, benchmark_total_return: 0.08, realized_pnl: 1200, strategy_max_drawdown: -0.04, strategy_sharpe: 1.3, strategy_trade_count: 4, strategy_hit_rate: 0.5, total_fees: 12 },
  equity_curve: [{ run_id: "run-1", ts: run.start_ts, strategy_equity: 100_000, benchmark_equity: 100_000 }, { run_id: "run-1", ts: run.end_ts, strategy_equity: 112_000, benchmark_equity: 108_000 }],
  comparison_curves: [{ run_id: "run-1", ts: run.start_ts, strategy_drawdown: 0, benchmark_drawdown: 0 }, { run_id: "run-1", ts: run.end_ts, strategy_drawdown: -0.04, benchmark_drawdown: -0.06 }],
  trades: [{ run_id: "run-1", fill_ts: run.end_ts, symbol: "BTC/USD", side: "buy", fill_qty: 0.1, fill_price: 60_000, realized_pnl: 0 }],
  review_evidence: [
    { evidence_kind: "evaluation", artifact_type: "parameter_optimization_evaluation_report", artifact_id: "eval-1", status: "available", reason: "Producer artifact is available for the declared claim scope", domain_owner: "Evaluation Agent", producer_tool: "evaluation_generate_parameter_optimization_report", schema_version: "1", source_hash: null, claim_scope: { holdout_run_id: "run-1" }, data_roles: ["sealed_holdout"], limitations: ["Optimisation-derived evidence is not independent confirmation"], blockers: [], independent_confirmation: false, origin_kind: "optimization" },
    { evidence_kind: "multiple_testing", artifact_type: null, artifact_id: null, status: "missing", reason: "No multiple-testing report is linked to this run", domain_owner: null, producer_tool: null, schema_version: null, source_hash: null, claim_scope: {}, data_roles: [], limitations: [], blockers: [], independent_confirmation: false, origin_kind: null },
    { evidence_kind: "adversarial", artifact_type: "robustness_report", artifact_id: "robust-1", status: "blocked", reason: "Stress variants are missing", domain_owner: "Adversarial Agent", producer_tool: "adversarial_run_robustness", schema_version: "1", source_hash: null, claim_scope: { run_id: "run-1" }, data_roles: ["protected_holdout"], limitations: [], blockers: ["Stress variants are missing"], independent_confirmation: false, origin_kind: "independent_review" },
  ],
  positions: [], warnings: [], provenance: [{ run_id: "run-1", provenance_key: "source", provenance_value: "fixture", observed_at: run.end_ts }], indicator_series: [{ run_id: "run-1", symbol: "BTC/USD", indicator_name: "middle", series_id: "middle", series_label: "Middle", pane: "price", scale_group: "price", unit: "price", series_kind: "line", bar_ts: run.end_ts, value: 60_000 }], signal_markers: [], risk_composition: [{ run_id: "run-1", session_id: "session-1", catalogue_version: "standard-1", composition_fingerprint: "risk-fingerprint", manager_position: 0, manager_id: "max_orders_per_run", manager_type: "trader_standard.risk.MaxOrdersPerRunRiskManager", parameters: { limit: 10 } }], risk_summary: { run_id: "run-1", composition_fingerprint: "risk-fingerprint", risk_evidence_status: "recorded", evaluated_count: 1, approved_count: 1, transformed_count: 0, rejected_count: 0, blocked_count: 0 }, risk_decisions: [{ risk_decision_id: "riskdec-1", composition_fingerprint: "risk-fingerprint", run_id: "run-1", session_id: "session-1", cycle_id: "cycle-1", client_order_id: "order-1", decision_ts: run.end_ts, manager_id: "max_orders_per_run", manager_type: "trader_standard.risk.MaxOrdersPerRunRiskManager", manager_position: 0, outcome: "approved", reason_code: "approved", before_qty: 0.1, after_qty: 0.1, before_order: { qty: 0.1 }, after_order: { qty: 0.1 } }], signals: [{ run_id: "run-1", generated_at: run.end_ts, symbol: "BTC/USD", signal_name: "bollinger", signal_value: 1, target_qty: 0.1 }], orders: [{ run_id: "run-1", created_at: run.end_ts, symbol: "BTC/USD", side: "buy", qty: 0.1, status: "accepted" }], fills: [{ run_id: "run-1", fill_ts: run.end_ts, symbol: "BTC/USD", fill_qty: 0.1, fill_price: 60_000, fee_amount: 1 }], assumptions: { run_id: "run-1", fill_model: "next_bar", latency_ms: 0, fee_bps: 1, fee_fixed_per_order: 0, slippage_bps: 2 }, exposure: { run_id: "run-1", avg_net_exposure: 0.5, avg_invested_pct: 0.5, final_gross_notional: 6_000, position_count: 1 }, evidence_coverage: null, comparison_summary: null,
} satisfies RunDetail;

beforeEach(() => {
  vi.mocked(loadExperiments).mockResolvedValue({ items: [experiment], page: { limit: 100, offset: 0, total: 1, has_more: false } });
  vi.mocked(loadExperimentRuns).mockResolvedValue({ items: [run], page: { limit: 100, offset: 0, total: 1, has_more: false } });
  vi.mocked(loadRunDetail).mockResolvedValue(detail);
  vi.mocked(loadRiskDecisions).mockResolvedValue({ items: detail.risk_decisions, page: { limit: 25, offset: 0, total: detail.risk_decisions.length, has_more: false } });
});

describe("single-backtest review workflow", () => {
  it("selects a run and renders scoped performance, curves and execution evidence", async () => {
    render(<BacktestReviewWorkspace />);
    expect(await screen.findByRole("heading", { name: "BTC/USD Bollinger Bands" })).toBeVisible();
    expect(screen.getByText("Completed")).toBeVisible();
    expect(screen.getByText("12%")).toBeVisible();
    expect(screen.getByRole("img", { name: "Strategy and benchmark equity chart" })).toBeVisible();
    expect(screen.getByText("Executed trades")).toBeVisible();
    expect(screen.getAllByText("BTC/USD").length).toBeGreaterThan(0);
    expect(screen.getByText("Assumptions and exposure")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Composition and decisions" })).toBeVisible();
    expect(screen.getAllByText("max_orders_per_run").length).toBeGreaterThan(0);
    expect(screen.getByText('{"limit":10}')).toBeVisible();
    expect(await screen.findByRole("link", { name: "Open risk decision for cycle cycle-1" })).toHaveAttribute("href", "/backtests?experiment_id=exp-bollinger&run_id=run-1&cycle_id=cycle-1&client_order_id=order-1");
    expect(screen.getByRole("combobox", { name: "Risk manager filter" })).toBeVisible();
    expect(screen.getByText("fixture")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Claims and limitations" })).toBeVisible();
    expect(screen.getByText("Optimisation output is shown for provenance and selection context; it is not independent confirmation.")).toBeVisible();
    expect(screen.getByText("No multiple-testing report is linked to this run")).toBeVisible();
    fireEvent.change(screen.getByRole("combobox", { name: "Risk outcome filter" }), { target: { value: "rejected" } });
    await waitFor(() => expect(loadRiskDecisions).toHaveBeenLastCalledWith(
      expect.anything(),
      "run-1",
      expect.objectContaining({ outcome: "rejected", limit: 25, offset: 0 }),
    ));
    await screen.getByRole("button", { name: "Lifecycle events" }).click();
    expect(screen.getByText("Signal lifecycle")).toBeVisible();
    expect(screen.getByText("Order lifecycle")).toBeVisible();
  });

  it("withholds metrics when the producer did not publish scope evidence", async () => {
    vi.mocked(loadRunDetail).mockResolvedValue({ ...detail, scope: null });
    render(<BacktestReviewWorkspace />);
    expect(await screen.findByText(/Scope evidence unavailable/)).toBeVisible();
    expect(screen.queryByText("Scoped result summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Strategy return")).not.toBeInTheDocument();
  });

  it("labels legacy runs whose risk evidence is unavailable", async () => {
    vi.mocked(loadRunDetail).mockResolvedValue({
      ...detail,
      risk_composition: [],
      risk_summary: { run_id: "run-1", composition_fingerprint: null, risk_evidence_status: "unavailable", evaluated_count: 0, approved_count: 0, transformed_count: 0, rejected_count: 0, blocked_count: 0 },
      risk_decisions: [],
    });
    render(<BacktestReviewWorkspace />);
    expect(await screen.findByRole("heading", { name: "Risk evidence unavailable" })).toBeVisible();
    expect(screen.getByText(/absence of a fill is not treated as a risk block/)).toBeVisible();
  });

  it("separates explicit risk blocks from broker rejection evidence", async () => {
    const blockedDetail = {
      ...detail,
      signals: [],
      signal_markers: [],
      fills: [],
      orders: [{ run_id: "run-1", client_order_id: "broker-order", status: "rejected", created_at: run.end_ts }],
      risk_decisions: [{ ...detail.risk_decisions[0], client_order_id: "risk-order", outcome: "rejected", reason_code: "limit_exceeded" }],
      risk_summary: { ...detail.risk_summary, evaluated_count: 1, approved_count: 0, rejected_count: 1, blocked_count: 1 },
    } as RunDetail;
    vi.mocked(loadRunDetail).mockResolvedValue(blockedDetail);
    vi.mocked(loadRiskDecisions).mockResolvedValue({ items: blockedDetail.risk_decisions, page: { limit: 25, offset: 0, total: 1, has_more: false } });

    render(<BacktestReviewWorkspace />);

    expect(await screen.findByText("Risk block recorded")).toBeVisible();
    expect(screen.getByText("Broker rejection recorded")).toBeVisible();
  });
});
