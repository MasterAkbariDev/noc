import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ComponentHealth, ComponentStatus } from "../../api/types";
import { ComponentGrid } from "./ComponentGrid";

const HOSTILE_SUMMARY = '<img src=x onerror="alert(1)"><script>alert(2)</script>Worker stopped';

function component(overrides: Partial<ComponentHealth> & Pick<ComponentHealth, "key" | "status">): ComponentHealth {
  return {
    label: overrides.key,
    summary: "All good",
    details: {},
    since: null,
    ...overrides,
  };
}

function renderGrid(components: ComponentHealth[]) {
  return render(<ComponentGrid components={components} />);
}

describe("ComponentGrid", () => {
  it.each<[ComponentStatus, string]>([
    ["ok", "Healthy"],
    ["degraded", "Degraded"],
    ["down", "Down"],
    ["unknown", "Unknown"],
  ])("shows a %s component with the word %s", (status, word) => {
    renderGrid([component({ key: "worker", label: "Worker", status, summary: "Worker summary" })]);

    const card = screen.getByRole("region", { name: "Worker" });
    expect(within(card).getByText(word)).toBeTruthy();
    expect(within(card).getByText("Worker summary")).toBeTruthy();
  });

  it("lists one card per component in the order the API gives", () => {
    renderGrid([
      component({ key: "worker", label: "Worker", status: "ok" }),
      component({ key: "database", label: "Database", status: "down" }),
    ]);

    const headings = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(headings).toEqual(["Worker", "Database"]);
  });

  it("shows each detail as a term and a value", () => {
    renderGrid([
      component({
        key: "prometheus",
        label: "Prometheus",
        status: "degraded",
        details: { up: "2/3" },
      }),
    ]);

    expect(screen.getByText("up")).toBeTruthy();
    expect(screen.getByText("2/3")).toBeTruthy();
  });

  it("shows the time a component has been in its state, with the absolute time on hover", () => {
    const { container } = renderGrid([
      component({
        key: "egress",
        label: "Egress",
        status: "down",
        since: "2026-10-12T10:00:00Z",
      }),
    ]);

    const time = container.querySelector("time");
    expect(time?.getAttribute("datetime")).toBe("2026-10-12T10:00:00Z");
    expect(time?.getAttribute("title")).not.toBe("");
  });

  it("shows untrusted summary text as text and creates no element from it", () => {
    const { container } = renderGrid([
      component({ key: "worker", label: "Worker", status: "degraded", summary: HOSTILE_SUMMARY }),
    ]);

    expect(screen.getByText(HOSTILE_SUMMARY)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
});
