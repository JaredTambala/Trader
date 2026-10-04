import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "../src/generated/api";
import { ConnectionPanel } from "../src/features/connection/connection-panel";
import { loadContext, loadLiveness, loadReadiness } from "../src/features/connection/client";

vi.mock("../src/features/connection/client", () => ({ loadContext: vi.fn(), loadLiveness: vi.fn(), loadReadiness: vi.fn() }));
const context: components["schemas"]["ConsoleScope"] = {
  scope_id: "console-demo", display_name: "Local Console demo", environment: "synthetic_demo",
  broker_account_binding: "not_applicable", broker_account_display_label: null,
  data_source_kind: "postgresql", isolation_kind: "isolated_database", presentation_timezone: "UTC",
};
const ready: components["schemas"]["ReadinessResponse"] = { status: "ready", scope_id: "console-demo", issues: [], contract_version: 1 };

beforeEach(() => {
  vi.mocked(loadContext).mockReset().mockResolvedValue(context);
  vi.mocked(loadLiveness).mockReset().mockResolvedValue({ status: "alive", service: "trader-console-api" });
  vi.mocked(loadReadiness).mockReset().mockResolvedValue(ready);
});

describe("first-screen workflow", () => {
  it("shows synthetic identity and independent connectivity without invented account data", async () => {
    render(<ConnectionPanel />);
    expect(await screen.findByText("Compatible")).toBeVisible();
    expect(screen.getByText("Synthetic demo")).toBeVisible();
    expect(screen.getByText("Not applicable")).toBeVisible();
    expect(screen.getByText("Available")).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeVisible();
    expect(screen.getByRole("link", { name: /Connection/ })).toHaveAttribute("aria-current", "page");
    expect(loadContext).toHaveBeenCalledTimes(1);
  });

  it("keeps a missing paper label unspecified", async () => {
    vi.mocked(loadContext).mockResolvedValue({ ...context, environment: "paper", broker_account_binding: "configured" });
    render(<ConnectionPanel />);
    expect(await screen.findByText("Not specified")).toBeVisible();
    expect(screen.getByText("Paper")).toBeVisible();
  });

  it("shows loading without prematurely claiming database availability", async () => {
    vi.mocked(loadReadiness).mockImplementation(() => new Promise(() => {}));
    render(<ConnectionPanel />);
    expect(await screen.findByText("Local Console demo")).toBeVisible();
    expect(screen.getByRole("button", { name: /Checking/ })).toBeDisabled();
    expect(screen.queryByText("Compatible")).not.toBeInTheDocument();
    expect(screen.getByText("Available")).toBeVisible();
  });

  it("renders schema issues safely and recovers through keyboard Retry", async () => {
    vi.mocked(loadReadiness).mockResolvedValueOnce({ ...ready, status: "unavailable", issues: ["schema_metadata_missing", "schema_catalog_mismatch:sessions", "unexpected_<script>_issue", "__proto__"] });
    const user = userEvent.setup();
    render(<ConnectionPanel />);
    expect(await screen.findByText(/missing its Console schema metadata/)).toBeVisible();
    expect(screen.getByText("Schema check reported: unexpected_<script>_issue")).toBeVisible();
    expect(screen.getByText("Schema check reported: __proto__")).toBeVisible();
    expect(screen.getByText(/relation does not match the supported schema: sessions/)).toBeVisible();
    const retry = screen.getByRole("button", { name: /Retry/ });
    for (let index = 0; index < 8 && document.activeElement !== retry; index += 1) await user.tab();
    expect(retry).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Compatible")).toBeVisible();
    expect(loadReadiness).toHaveBeenCalledTimes(2);
  });

  it("shows unavailable context on an initial API failure", async () => {
    vi.mocked(loadContext).mockRejectedValue(new Error("network"));
    vi.mocked(loadLiveness).mockRejectedValue(new Error("network"));
    vi.mocked(loadReadiness).mockRejectedValue(new Error("network"));
    render(<ConnectionPanel />);
    expect(await screen.findByText("Context unavailable")).toBeVisible();
    expect(screen.getByText("Unknown environment")).toBeVisible();
    expect(screen.queryByText("Synthetic demo")).not.toBeInTheDocument();
  });

  it("preserves known context with an explicit warning during a failed refresh", async () => {
    const user = userEvent.setup();
    render(<ConnectionPanel />);
    await screen.findByText("Compatible");
    vi.mocked(loadContext).mockRejectedValueOnce(new Error("network"));
    vi.mocked(loadReadiness).mockRejectedValueOnce(new Error("network"));
    await user.click(screen.getByRole("button", { name: /Refresh/ }));
    expect(await screen.findByText(/Showing last known configured context/)).toBeVisible();
    expect(screen.getByText("Local Console demo")).toBeVisible();
    expect(screen.queryByText("Compatible")).not.toBeInTheDocument();
  });

  it("aborts in-flight work when the screen unmounts", async () => {
    vi.mocked(loadReadiness).mockImplementation(() => new Promise(() => {}));
    const view = render(<ConnectionPanel />);
    await waitFor(() => expect(loadReadiness).toHaveBeenCalled());
    const signal = vi.mocked(loadReadiness).mock.calls[0]![0];
    view.unmount();
    expect(signal.aborted).toBe(true);
  });

  it("turns a timed-out request into a retryable error", async () => {
    vi.useFakeTimers();
    vi.mocked(loadReadiness).mockImplementation(signal => new Promise((_, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    render(<ConnectionPanel />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(screen.getByRole("button", { name: /Retry/ })).toBeEnabled();
    expect(screen.getByText(/Database status could not be checked/)).toBeVisible();
  });
});
