import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ColumnChart, DonutChart, HBarChart, LineChart, columnPath, donutSegments, niceScale, shareText, sparkPath } from ".";

const POINTS = [
  { key: "2026-10-13", label: "Oct 13", longLabel: "Mon, Oct 13", values: [3, 1] },
  { key: "2026-10-14", label: "Oct 14", longLabel: "Tue, Oct 14", values: [0, 2] },
];

afterEach(() => {
  cleanup();
});

describe("niceScale", () => {
  it("rounds the top to a clean whole number with whole-number ticks", () => {
    expect(niceScale(7)).toEqual({ max: 8, ticks: [0, 2, 4, 6, 8] });
    expect(niceScale(1)).toEqual({ max: 1, ticks: [0, 1] });
    expect(niceScale(1340).ticks.at(-1)).toBe(1500);
  });

  it("handles an empty or zero range", () => {
    expect(niceScale(0)).toEqual({ max: 1, ticks: [0, 1] });
    expect(niceScale(Number.NaN)).toEqual({ max: 1, ticks: [0, 1] });
  });
});

describe("columnPath", () => {
  it("draws nothing for a zero-height bar and rounds only the top", () => {
    expect(columnPath(0, 10, 20, 0)).toBe("");
    const path = columnPath(0, 10, 20, 50);
    expect(path.startsWith("M0,60")).toBe(true);
    expect(path).toContain("Q0,10 4,10");
  });
});

describe("ColumnChart", () => {
  it("shows a legend for two series and a table view with every value", () => {
    render(
      <ColumnChart
        title="Resolved and escalated"
        firstColumn="Day"
        series={[
          { name: "Resolved", color: "red" },
          { name: "Escalated", color: "blue" },
        ]}
        points={POINTS}
      />,
    );
    const legend = screen.getByRole("list", { name: "Legend" });
    expect(within(legend).getByText("Resolved")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show table" }));
    const table = screen.getByRole("table", { name: "Resolved and escalated (table)" });
    expect(within(table).getByText("Mon, Oct 13")).toBeTruthy();
    expect(within(table).getAllByRole("row")).toHaveLength(3);
  });

  it("has no legend box for one series and shows a tooltip on focus", () => {
    render(
      <ColumnChart
        title="Opened"
        firstColumn="Day"
        series={[{ name: "Opened", color: "red" }]}
        points={POINTS.map((point) => ({ ...point, values: [point.values[0] ?? 0] }))}
      />,
    );
    expect(screen.queryByRole("list", { name: "Legend" })).toBeNull();
    fireEvent.focus(screen.getByLabelText("Mon, Oct 13: Opened 3"));
    const tooltip = screen.getByRole("status");
    expect(tooltip.textContent).toContain("Mon, Oct 13");
    expect(tooltip.textContent).toContain("3");
  });
});

describe("LineChart", () => {
  it("labels the last value and offers a table", () => {
    render(
      <LineChart
        title="Tokens"
        name="Tokens"
        color="red"
        firstColumn="Day"
        points={POINTS.map((point) => ({ ...point, values: [point.values[0] === 3 ? 1200 : 3400] }))}
      />,
    );
    expect(screen.getByText("3.4K")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show table" }));
    expect(within(screen.getByRole("table")).getByText("3,400")).toBeTruthy();
  });
});

describe("HBarChart", () => {
  it("lists every item with its value and says when there is nothing", () => {
    const { rerender } = render(
      <HBarChart
        title="Root causes"
        color="red"
        firstColumn="Cause"
        valueColumn="Incidents"
        empty="Nothing yet."
        items={[
          { key: "a", label: "Service crashed", value: 3 },
          { key: "b", label: "<b>Disk</b>", value: 1 },
        ]}
      />,
    );
    const list = screen.getByRole("list", { name: "Root causes" });
    expect(within(list).getByText("Service crashed")).toBeTruthy();
    expect(within(list).getByText("<b>Disk</b>")).toBeTruthy();
    expect(document.querySelector("b")).toBeNull();
    rerender(
      <HBarChart title="Root causes" color="red" firstColumn="Cause" valueColumn="Incidents" empty="Nothing yet." items={[]} />,
    );
    expect(screen.getByText("Nothing yet.")).toBeTruthy();
  });
});

describe("DonutChart", () => {
  const ITEMS = [
    { key: "up", label: "Up", value: 3, color: "green" },
    { key: "down", label: "Down", value: 1, color: "red" },
    { key: "unknown", label: "Unknown", value: 0, color: "gray" },
  ];

  it("splits the ring by share and leaves out empty slices", () => {
    const segments = donutSegments(ITEMS);
    expect(segments.map((segment) => segment.item.key)).toEqual(["up", "down"]);
    expect(segments[1]?.offset).toBeGreaterThan(segments[0]?.dash ?? 0);
    expect(shareText(1, 4)).toBe("25%");
    expect(shareText(0, 0)).toBe("0%");
  });

  it("names the chart with every value, lists them and offers a table", () => {
    render(
      <DonutChart
        title="Server status"
        centerLabel="servers"
        firstColumn="Status"
        valueColumn="Servers"
        empty="Nothing yet."
        items={ITEMS}
      />,
    );

    expect(screen.getByRole("img", { name: "Server status: Up 3, Down 1, Unknown 0" })).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "Legend" })).getByText("75%")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show table" }));
    expect(within(screen.getByRole("table", { name: "Server status (table)" })).getByText("25%")).toBeTruthy();
  });

  it("says when there is nothing to draw", () => {
    render(
      <DonutChart
        title="Server status"
        centerLabel="servers"
        firstColumn="Status"
        valueColumn="Servers"
        empty="Nothing yet."
        items={ITEMS.map((item) => ({ ...item, value: 0 }))}
      />,
    );

    expect(screen.getByText("Nothing yet.")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });
});

describe("sparkPath", () => {
  it("draws one point per value and keeps zero on the baseline", () => {
    const path = sparkPath([0, 5, 10], 100, 20);
    expect(path.split(" ")).toHaveLength(3);
    expect(path.startsWith("M3.0,17.0")).toBe(true);
    expect(path.endsWith("L97.0,3.0")).toBe(true);
  });
});
