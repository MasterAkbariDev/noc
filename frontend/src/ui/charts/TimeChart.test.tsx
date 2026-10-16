import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TimeChart, nearestIndex, timePath } from "./TimeChart";

afterEach(() => {
  cleanup();
});

describe("timePath", () => {
  it("starts a new line after a gap, so missing readings are not drawn as a slope", () => {
    const path = timePath(
      [
        [0, 1],
        [15, 2],
        [300, 3],
      ],
      (time) => time,
      (value) => value,
      45,
    );
    expect(path).toBe("M0.0,1.0 L15.0,2.0 M300.0,3.0");
  });
});

describe("nearestIndex", () => {
  it("finds the reading closest to a time and nothing in an empty list", () => {
    expect(
      nearestIndex(
        [
          [0, 1],
          [30, 2],
          [60, 3],
        ],
        40,
      ),
    ).toBe(1);
    expect(nearestIndex([], 40)).toBeNull();
  });
});

describe("TimeChart", () => {
  it("says so when there are no readings", () => {
    render(<TimeChart title="CPU" series={[{ name: "CPU", color: "red", points: [] }]} from={0} to={60} step={15} format={String} empty="Nothing yet." />);

    expect(screen.getByText("Nothing yet.")).toBeTruthy();
    expect(screen.queryByRole("img", { name: "CPU" })).toBeNull();
  });

  it("draws one line per series with a legend and formatted axis labels", () => {
    const { container } = render(
      <TimeChart
        title="Traffic"
        series={[
          { name: "In", color: "red", points: [[0, 10], [15, 20]] },
          { name: "Out", color: "blue", points: [[0, 5], [15, 7]] },
        ]}
        from={0}
        to={15}
        step={15}
        format={(value) => `${value} B/s`}
        max={100}
      />,
    );

    expect(screen.getByRole("img", { name: "Traffic" })).toBeTruthy();
    expect(screen.getByText("In")).toBeTruthy();
    expect(screen.getByText("100 B/s")).toBeTruthy();
    expect(container.querySelectorAll("svg[role=img] path")).toHaveLength(2);
  });
});
