import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { StoryStep } from "../../api/types";
import { StoryProgress } from "./StoryProgress";

const steps: StoryStep[] = [
  { key: "detected", label: "Alert received", state: "done", at: "2026-10-12T10:00:00Z" },
  { key: "investigated", label: "Investigated", state: "failed", at: null },
  { key: "diagnosed", label: "Diagnosed", state: "current", at: null },
  { key: "decided", label: "Decided what to do", state: "pending", at: null },
  { key: "acted", label: "Action taken", state: "skipped", at: null },
  { key: "outcome", label: "Outcome", state: "pending", at: null },
];

afterEach(() => {
  cleanup();
});

describe("StoryProgress", () => {
  it("gives every step a state word, so colour is not the only signal", () => {
    render(<StoryProgress steps={steps} />);

    expect(screen.getByText("Done")).toBeTruthy();
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.getByText("In progress")).toBeTruthy();
    expect(screen.getAllByText("Not yet")).toHaveLength(2);
    expect(screen.getByText("Skipped")).toBeTruthy();
  });

  it("marks only the current step with aria-current", () => {
    const { container } = render(<StoryProgress steps={steps} />);

    const current = container.querySelectorAll('[aria-current="step"]');
    expect(current).toHaveLength(1);
    expect(current[0]?.textContent).toContain("Diagnosed");
  });

  it("shows a relative time only for the steps that have one", () => {
    const { container } = render(<StoryProgress steps={steps} />);

    expect(container.querySelector("time")?.getAttribute("datetime")).toBe("2026-10-12T10:00:00Z");
    expect(container.querySelectorAll("time")).toHaveLength(1);
  });
});
