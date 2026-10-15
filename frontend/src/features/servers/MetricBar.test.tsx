import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MetricBar, MetricBars } from "./MetricBar";
import { HOSTILE_TEXT } from "./fixtures";

afterEach(() => {
  cleanup();
});

describe("MetricBar", () => {
  it("carries the value as text and as the meter's value text", () => {
    render(<MetricBar label="CPU" value={42} />);

    expect(screen.getByText("42%")).toBeTruthy();
    const meter = screen.getByRole("meter", { name: "CPU" });
    expect(meter.getAttribute("aria-valuetext")).toBe("42%");
    expect(meter.getAttribute("aria-valuenow")).toBe("42");
  });

  it("sets the bar width through the custom property and clamps it", () => {
    render(<MetricBar label="Memory" value={130} />);

    const fill = screen.getByRole("meter", { name: "Memory" }).firstElementChild;
    expect(fill?.getAttribute("style")).toContain("--meter-width: 100%");
  });

  it("shows No data instead of a bar when the value is missing", () => {
    render(<MetricBar label="Disk" value={null} />);

    expect(screen.getByText("No data")).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
  });
});

describe("MetricBars", () => {
  it("says Metrics unavailable rather than showing zeros when there are no metrics", () => {
    render(<MetricBars metrics={null} />);

    expect(screen.getByText("Metrics unavailable")).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
    expect(screen.queryByText("0%")).toBeNull();
  });

  it("names the disk with its mount point", () => {
    render(<MetricBars metrics={{ cpu_percent: 1, memory_percent: 2, disk_percent: 92, disk_mount: "/var" }} />);

    expect(screen.getByRole("meter", { name: "Disk (/var)" })).toBeTruthy();
    expect(screen.getByText("92%")).toBeTruthy();
  });

  it("shows a hostile mount point as text and creates no element", () => {
    const { container } = render(
      <MetricBars metrics={{ cpu_percent: null, memory_percent: null, disk_percent: 10, disk_mount: HOSTILE_TEXT }} />,
    );

    expect(screen.getByRole("meter", { name: `Disk (${HOSTILE_TEXT})` })).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });
});
