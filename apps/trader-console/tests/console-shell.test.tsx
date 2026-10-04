import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { usePathname } from "next/navigation";
import { ConsoleShell } from "../src/features/shell/console-shell";

vi.mock("next/navigation", () => ({ usePathname: vi.fn() }));

const mockedUsePathname = vi.mocked(usePathname);

describe("Console sidebar navigation", () => {
  beforeEach(() => {
    mockedUsePathname.mockReturnValue("/backtests");
  });

  it("marks the current workflow and keeps every Console route keyboard-addressable", () => {
    render(<ConsoleShell><main>Review content</main></ConsoleShell>);

    expect(screen.getByRole("navigation", { name: "Primary" })).toBeVisible();
    expect(screen.getByRole("link", { name: /Backtest review/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Market data/ })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: /Connection/ })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: /Comparisons/ })).toHaveAttribute("href", "/comparisons");
  });

  it("marks authoring separately from published run review", () => {
    mockedUsePathname.mockReturnValue("/backtests/new");
    render(<ConsoleShell><main>Authoring content</main></ConsoleShell>);

    expect(screen.getByRole("link", { name: /New backtest/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Backtest review/ })).not.toHaveAttribute("aria-current");
  });
});
