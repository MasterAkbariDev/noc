import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IncidentFilters } from "./IncidentFilters";

afterEach(() => {
  cleanup();
});

function renderFilters(overrides: Partial<Parameters<typeof IncidentFilters>[0]> = {}) {
  const handlers = {
    onFilterChange: vi.fn(),
    onSeverityChange: vi.fn(),
    onServerChange: vi.fn(),
    onSearchChange: vi.fn(),
  };
  render(
    <IncidentFilters
      filter="open"
      severity=""
      severities={["critical", "warning"]}
      server=""
      servers={["demo-1", "box-95"]}
      search=""
      {...handlers}
      {...overrides}
    />,
  );
  return handlers;
}

describe("IncidentFilters", () => {
  it("marks only the chosen filter as pressed", () => {
    renderFilters({ filter: "needs-you" });

    expect(screen.getByRole("button", { name: "Needs you" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Open" }).getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByRole("button", { name: "Resolved" }).getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByRole("button", { name: "All" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("reports the filter a chip stands for when clicked", () => {
    const handlers = renderFilters();

    fireEvent.click(screen.getByRole("button", { name: "Resolved" }));

    expect(handlers.onFilterChange).toHaveBeenCalledWith("resolved");
  });

  it("lists every severity offered and reports the one picked", () => {
    const handlers = renderFilters();

    const select = screen.getByLabelText("Severity") as HTMLSelectElement;
    expect(Array.from(select.options).map((option) => option.textContent)).toEqual([
      "All severities",
      "Critical",
      "Warning",
    ]);

    fireEvent.change(select, { target: { value: "critical" } });

    expect(handlers.onSeverityChange).toHaveBeenCalledWith("critical");
  });

  it("shows the search text and reports every change to it", () => {
    const handlers = renderFilters({ search: "disk" });

    const search = screen.getByRole("searchbox", { name: "Search" }) as HTMLInputElement;
    expect(search.value).toBe("disk");

    fireEvent.change(search, { target: { value: "disk full" } });

    expect(handlers.onSearchChange).toHaveBeenCalledWith("disk full");
  });
});
