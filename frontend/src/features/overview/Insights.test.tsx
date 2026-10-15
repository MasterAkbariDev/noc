import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { OutcomeChart, RootCauseChart, topWithOther } from "./Insights";
import { metricsFixture } from "./testData";

afterEach(() => {
  cleanup();
});

describe("topWithOther", () => {
  it("keeps the largest items and folds the rest into Other", () => {
    const items = [
      { label: "a", count: 1 },
      { label: "b", count: 5 },
      { label: "c", count: 3 },
      { label: "d", count: 2 },
    ];

    expect(topWithOther(items, 2)).toEqual([
      { label: "b", count: 5 },
      { label: "c", count: 3 },
      { label: "other", count: 3 },
    ]);
    expect(topWithOther(items, 4)).toHaveLength(4);
  });
});

describe("dashboard insight charts", () => {
  it("shows root causes and outcomes in plain words", () => {
    render(
      <>
        <RootCauseChart metrics={metricsFixture()} />
        <OutcomeChart metrics={metricsFixture()} />
      </>,
    );

    expect(within(screen.getByRole("list", { name: "Top root causes" })).getByText("Disk full logs")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Where incidents ended: Resolved 2, Needs you 1" })).toBeTruthy();
  });
});
