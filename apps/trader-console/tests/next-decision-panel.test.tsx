import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { NextDecisionPanel } from "../src/features/backtest-review/next-decision-panel";
import {
  loadDecisionBasis, loadNextResearchDecisions, createNextResearchDecision,
  type DecisionBasisResponse, type RunDetail, type NextResearchDecisionRecord,
} from "../src/features/backtest-review/client";

vi.mock("../src/features/backtest-review/client", () => ({
  loadDecisionBasis: vi.fn(), loadNextResearchDecisions: vi.fn(), createNextResearchDecision: vi.fn(),
}));
const ref = (artifact_type: string, artifact_id: string, domain_owner: string) => ({
  artifact_type, artifact_id, domain_owner, uri: `research://postgres/${artifact_type}/${artifact_id}`,
  metadata: { payload_sha256: "a".repeat(64) },
});
const evidence = {
  source_run_ref: ref("backtest_run", "run-1", "Experiments"),
  data_ref: ref("dataset_manifest", "data-1", "Data"),
  implementation_refs: [ref("implementation_version", "strategy-1", "Experiments")],
  assumptions: {}, review_refs: [], session_review: null,
  blocked_evidence: {
    outcome_ref: ref("workflow_outcome", "outcome-1", "Orchestration"),
    blockers: [{ code: "evaluation_unavailable", message: "Independent review is unavailable", details: {} }],
    session_ref: null, scientific_review_status: "not_assessed" as const,
  },
};
const basis: DecisionBasisResponse = {
  run_id: "run-1", status: "available", reason: "Verified persisted evidence",
  permitted_outcomes: ["reject", "refine"], evidence, limitations: ["Scientific review remains unassessed"],
};
const detail = { run: { run_id: "run-1" } } as RunDetail;
const record: NextResearchDecisionRecord = {
  ...evidence, artifact_type: "research_next_decision", artifact_id: "decision-receipt-1",
  decision_id: "decision-1", revision: 1, outcome: "reject", rationale: "Evidence is insufficient",
  operator: "human:jared", decided_at: "2026-10-14T12:00:00Z", limitations: ["One run"],
  decision_digest: "b".repeat(64),
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(loadDecisionBasis).mockResolvedValue(basis);
  vi.mocked(loadNextResearchDecisions).mockResolvedValue({ items: [], page: { limit: 20, offset: 0, total: 0, has_more: false } });
  vi.mocked(createNextResearchDecision).mockResolvedValue(record);
});

it("submits exactly the displayed canonical blocked basis and displays its durable receipt", async () => {
  render(<NextDecisionPanel detail={detail} />);
  await screen.findByText("Verified persisted evidence");
  expect(screen.getByText("Independent scientific review: Not assessed")).toBeVisible();
  expect(screen.queryByRole("option", { name: "Continue" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Qualified data artifact ID")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Decision rationale"), { target: { value: "Evidence is insufficient" } });
  fireEvent.change(screen.getByLabelText("Decision limitations"), { target: { value: "One run" } });
  fireEvent.click(screen.getByRole("button", { name: "Record decision" }));
  await screen.findByText("decision-receipt-1");
  expect(createNextResearchDecision).toHaveBeenCalledWith(expect.anything(), "run-1", expect.objectContaining(evidence));
  expect(screen.getByText("Revision 1")).toBeVisible();
});

it("invalidates stale evidence after a rejected command and requires explicit refresh", async () => {
  vi.mocked(createNextResearchDecision).mockRejectedValue(new Error("Evidence payload changed"));
  render(<NextDecisionPanel detail={detail} />);
  await screen.findByText("Verified persisted evidence");
  fireEvent.change(screen.getByLabelText("Decision rationale"), { target: { value: "Reject" } });
  fireEvent.change(screen.getByLabelText("Decision limitations"), { target: { value: "Unassessed" } });
  fireEvent.click(screen.getByRole("button", { name: "Record decision" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Record decision" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Refresh persisted evidence" }));
  await waitFor(() => expect(loadDecisionBasis).toHaveBeenCalledTimes(2));
});

it.each(["unavailable", "incompatible"] as const)("withholds all commands for %s evidence", async (status) => {
  vi.mocked(loadDecisionBasis).mockResolvedValue({ run_id: "run-1", status, reason: "Canonical evidence cannot be verified", permitted_outcomes: [], limitations: [] });
  render(<NextDecisionPanel detail={detail} />);
  await screen.findByText("Canonical evidence cannot be verified");
  expect(screen.getByRole("button", { name: "Record decision" })).toBeDisabled();
  expect(screen.queryByRole("option", { name: "Reject" })).not.toBeInTheDocument();
});

it("fails closed when human authorization prevents loading evidence", async () => {
  vi.mocked(loadDecisionBasis).mockRejectedValue(new Error("Human authorization required"));
  render(<NextDecisionPanel detail={detail} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Human authorization required");
  expect(screen.getByRole("button", { name: "Record decision" })).toBeDisabled();
});

it("requires a bounded successor before recording refine", async () => {
  render(<NextDecisionPanel detail={detail} />);
  await screen.findByText("Verified persisted evidence");
  fireEvent.change(screen.getByLabelText("Next decision outcome"), { target: { value: "refine" } });
  fireEvent.change(screen.getByLabelText("Decision rationale"), { target: { value: "Investigate" } });
  fireEvent.change(screen.getByLabelText("Decision limitations"), { target: { value: "Unassessed" } });
  expect(screen.getByRole("button", { name: "Record decision" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Next experiment question"), { target: { value: "Does the result reproduce?" } });
  fireEvent.change(screen.getByLabelText("Next experiment evaluation start"), { target: { value: "2026-10-15" } });
  fireEvent.change(screen.getByLabelText("Next experiment evaluation end"), { target: { value: "2026-10-16" } });
  fireEvent.change(screen.getByLabelText("Next experiment success criteria"), { target: { value: "Repeat observed measurements" } });
  expect(screen.getByRole("button", { name: "Record decision" })).toBeEnabled();
});
